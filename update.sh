#!/usr/bin/env bash
# ================================================================
# 主机资产管理平台 — 离线升级脚本
# ================================================================
# 用法:
#   ./update.sh <github-zip包路径>
#
# 示例:
#   ./update.sh /tmp/enter-ServerAssetSpares-enter-main.zip
#   ./update.sh ./enter-ServerAssetSpares-enter-main.zip
#
# 说明:
#   1. 备份当前 dist/ 和 .env
#   2. 解压 zip → 覆盖代码（保留 .env）
#   3. 前端构建 + 后端镜像重建
#   4. 重启受影响的容器（api + web）
# ================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERR ]${NC}  $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$SCRIPT_DIR"

ZIP_FILE="${1:-}"
if [ -z "$ZIP_FILE" ]; then
    echo "用法: $0 <github-zip包路径>"
    echo "示例: $0 ./enter-ServerAssetSpares-enter-main.zip"
    exit 1
fi
if [ ! -f "$ZIP_FILE" ]; then
    err "文件不存在: $ZIP_FILE"
    exit 1
fi

COMPOSE_PROJECT="cmdb"
COMPOSE_FILE="docker-compose.yml"
BACKUP_DIR="backups"
TMP_DIR=".update-tmp"

# ---- 前置检查 ----
if ! command -v docker &>/dev/null; then
    err "未找到 docker，请先安装 Docker 24+"
    exit 1
fi
if ! docker compose version &>/dev/null; then
    err "未找到 docker compose v2 插件"
    exit 1
fi

# ---- 备份 ----
log "备份数据库..."
mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d-%H%M%S)
ENV_FILE="reference-backend/.env"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
    if docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T mysql \
        mysqldump -u"${MYSQL_USER:-cmdb}" -p"${MYSQL_PASSWORD:-cmdb123}" \
        --single-transaction --routines --triggers "${MYSQL_DATABASE:-cmdb}" \
        2>/dev/null | gzip > "$BACKUP_DIR/pre-update-${TS}.sql.gz"; then
        ok "备份完成: $BACKUP_DIR/pre-update-${TS}.sql.gz"
    else
        warn "数据库备份失败（容器可能未运行），跳过备份继续升级"
    fi
else
    warn ".env 不存在，跳过数据库备份"
fi

# ---- 备份当前 dist 和 .env ----
log "保留运行环境配置..."
cp "$ENV_FILE" .env.bak 2>/dev/null || true
if [ -d "dist" ]; then
    mv dist dist.bak
    ok "当前 dist/ 已备份为 dist.bak（构建失败可回滚）"
fi

# ---- 解压 ----
log "解压 $ZIP_FILE ..."
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
unzip -qo "$ZIP_FILE" -d "$TMP_DIR"

# GitHub zip 会包一层目录，自动找到它
UNPACK_DIR="$TMP_DIR"
if [ -d "$TMP_DIR/enter-ServerAssetSpares-enter-main" ]; then
    UNPACK_DIR="$TMP_DIR/enter-ServerAssetSpares-enter-main"
elif [ -d "$TMP_DIR/enter-ServerAssetSpares-main" ]; then
    UNPACK_DIR="$TMP_DIR/enter-ServerAssetSpares-main"
fi

log "覆盖源代码..."
# 只覆盖受版本控制的关键目录，保留本地配置和备份
for item in src reference-backend public supabase index.html \
    docker-compose.yml \
    package.json pnpm-lock.yaml vite.config.ts tsconfig.json \
    tsconfig.app.json tsconfig.node.json tailwind.config.ts \
    postcss.config.js components.json eslint.config.js; do
    if [ -e "$UNPACK_DIR/$item" ]; then
        rm -rf "$item" 2>/dev/null || true
        cp -a "$UNPACK_DIR/$item" "$item"
    fi
done

# 还原 .env
if [ -f .env.bak ]; then
    cp .env.bak "$ENV_FILE"
    rm .env.bak
    ok ".env 已还原"
fi

ok "源码覆盖完成"

# ---- 更新前端 ----
# 优先使用 zip 包中预构建好的 dist/，避免架构/环境问题
FRONTEND_OK=0
if [ -d "$UNPACK_DIR/dist" ]; then
    log "使用 zip 包中的预构建 dist/..."
    rm -rf dist dist.bak 2>/dev/null || true
    cp -a "$UNPACK_DIR/dist" dist
    ok "已使用预构建前端（跳过编译）"
    FRONTEND_OK=1
elif command -v pnpm &>/dev/null && command -v node &>/dev/null; then
    log "本地构建前端（VITE_API_MODE=internal）..."
    VITE_API_MODE=internal pnpm install --no-frozen-lockfile && \
    VITE_API_MODE=internal pnpm run build:prod && \
    FRONTEND_OK=1
    if [ "$FRONTEND_OK" = "1" ]; then
        ok "前端构建完成"
        rm -rf dist.bak
    fi
elif command -v docker &>/dev/null && docker compose version &>/dev/null; then
    HOST_ARCH=$(uname -m)
    DOCKER_ARCH="amd64"
    [ "$HOST_ARCH" = "aarch64" ] && DOCKER_ARCH="arm64"
    log "Docker 构建前端（VITE_API_MODE=internal, $DOCKER_ARCH）..."
    if docker run --rm \
        --platform "linux/$DOCKER_ARCH" \
        -v "$SCRIPT_DIR":/app -w /app \
        -e VITE_API_MODE=internal \
        -e VITE_INTERNAL_API_BASE=/api \
        node:20-alpine sh -c "
            corepack enable && \
            corepack prepare pnpm@8.6.12 --activate && \
            pnpm install --no-frozen-lockfile && \
            pnpm run build:prod
        "; then
        ok "前端构建完成"
        FRONTEND_OK=1
        rm -rf dist.bak
    fi
fi

if [ "$FRONTEND_OK" = "0" ]; then
    if [ -d "dist.bak" ]; then
        warn "构建失败，还原原有 dist/"
        rm -rf dist 2>/dev/null || true
        mv dist.bak dist
        FRONTEND_OK=1
    elif [ -d "dist" ]; then
        ok "使用现有 dist/（未更新前端）"
        FRONTEND_OK=1
    else
        err "dist/ 不存在且无法构建，请上传包含预构建 dist/ 的 zip 包"
        exit 1
    fi
fi

# 清理临时目录（在 dist 检查之后）
rm -rf "$TMP_DIR" dist.bak

# ---- 更新后端代码 ----
# 不重建镜像（避免架构/网络问题），直接将代码注入运行中的容器
log "更新后端代码到 API 容器..."
API_CONTAINER=$(docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" ps -q api 2>/dev/null)
if [ -z "$API_CONTAINER" ]; then
    err "未找到 API 容器，请确保服务正在运行"
    exit 1
fi
# 复制后端代码目录到容器
docker cp reference-backend/app/. "$API_CONTAINER":/app/app/
# 同时复制 alembic 迁移文件，确保容器重启时自动执行新迁移
docker cp reference-backend/alembic/. "$API_CONTAINER":/app/alembic/
docker cp reference-backend/alembic.ini "$API_CONTAINER":/app/alembic.ini
ok "后端代码已注入容器"

# ---- 安装新依赖（mcp 等） ----
log "安装新 Python 依赖..."
# 优先从离线 wheels 安装（私有化环境），无 wheels 时回退在线安装
WHEELS_DIR="reference-backend/wheels"
if [ -d "$WHEELS_DIR" ] && ls "$WHEELS_DIR"/*.whl >/dev/null 2>&1; then
    # 把 wheels 目录复制到容器内再安装
    docker cp "$WHEELS_DIR" "$API_CONTAINER":/tmp/mcp-wheels
    if docker exec "$API_CONTAINER" pip install /tmp/mcp-wheels/*.whl 2>/dev/null; then
        ok "mcp 包已安装（离线 wheels）"
    else
        warn "离线 wheels 安装失败，MCP 服务将不可用"
    fi
    docker exec "$API_CONTAINER" rm -rf /tmp/mcp-wheels
else
    # 在线环境回退
    docker exec "$API_CONTAINER" pip install "mcp>=1.27" 2>/dev/null && \
        ok "mcp 包已安装（在线）" || \
        warn "mcp 包安装失败，MCP 服务将不可用"
fi

# 强制锁定 starlette 版本，防止 mcp 安装时拉升导致 FastAPI 路由注册失败
docker exec "$API_CONTAINER" pip install "starlette>=0.37.2,<0.40.0" 2>/dev/null || true

# ---- 更新 / 启动 MCP SSE 服务 ----
log "启动 MCP SSE 服务..."
MCP_CONTAINER="${COMPOSE_PROJECT}-mcp-1"
API_IMAGE=$(docker inspect "$API_CONTAINER" --format '{{.Config.Image}}' 2>/dev/null || echo "reference-backend-api:latest")

if docker inspect "$MCP_CONTAINER" >/dev/null 2>&1; then
    # 已有容器：注入最新代码并重启
    docker cp reference-backend/app/. "$MCP_CONTAINER":/app/app/
    docker restart "$MCP_CONTAINER"
    ok "MCP 容器已重启"
else
    MCP_SSE_PORT="${MCP_SSE_PORT:-8100}"

    # 先用 sleep 占位启动，确保容器处于运行状态以便后续注入
    docker run -d \
        --name "$MCP_CONTAINER" \
        --network "${COMPOSE_PROJECT}_default" \
        --restart unless-stopped \
        --env-file reference-backend/.env \
        --label "com.docker.compose.project=${COMPOSE_PROJECT}" \
        --label "com.docker.compose.service=mcp" \
        -p "${MCP_SSE_PORT}:8100" \
        "$API_IMAGE" \
        sleep infinity

    # 注入代码和依赖
    docker cp reference-backend/app/. "$MCP_CONTAINER":/app/app/
    if [ -d "$WHEELS_DIR" ] && ls "$WHEELS_DIR"/*.whl >/dev/null 2>&1; then
        docker cp "$WHEELS_DIR" "$MCP_CONTAINER":/tmp/mcp-wheels
        docker exec "$MCP_CONTAINER" pip install /tmp/mcp-wheels/*.whl 2>/dev/null || true
        docker exec "$MCP_CONTAINER" rm -rf /tmp/mcp-wheels
    else
        docker exec "$MCP_CONTAINER" pip install "mcp>=1.27" 2>/dev/null || true
    fi

    # 强制锁定 starlette 版本
    docker exec "$MCP_CONTAINER" pip install "starlette>=0.37.2,<0.40.0" 2>/dev/null || true

    # 停止占位容器 → commit 固化 → 用真实命令重建
    docker stop "$MCP_CONTAINER"
    docker commit "$MCP_CONTAINER" "${COMPOSE_PROJECT}_mcp:latest"
    docker rm "$MCP_CONTAINER"
    docker run -d \
        --name "$MCP_CONTAINER" \
        --network "${COMPOSE_PROJECT}_default" \
        --restart unless-stopped \
        --env-file reference-backend/.env \
        --label "com.docker.compose.project=${COMPOSE_PROJECT}" \
        --label "com.docker.compose.service=mcp" \
        -p "${MCP_SSE_PORT}:8100" \
        "${COMPOSE_PROJECT}_mcp:latest" \
        python3 -m app.mcp_server --sse --host 0.0.0.0 --port 8100
    ok "MCP 容器已创建 (端口 $MCP_SSE_PORT)"
fi

# ---- 更新前端到 web 容器 ----
# dist/ 只在 .dockerignore 中被排除，使用独立构建上下文打包进镜像，
# 避免 readonly 容器文件系统导致 docker cp 失败。
if [ -d "dist" ]; then
    log "重建 web 镜像..."
    WEB_CTX=".web-build-ctx"
    rm -rf "$WEB_CTX"
    mkdir -p "$WEB_CTX"
    cp -a dist "$WEB_CTX/dist"
    mkdir -p "$WEB_CTX/nginx"
    cp reference-backend/nginx/default.conf "$WEB_CTX/nginx/default.conf"

    if docker build -t "${COMPOSE_PROJECT}_web:latest" -f - "$WEB_CTX" <<'DOCKERFILE'
FROM nginx:latest
COPY dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
DOCKERFILE
    then
        rm -rf "$WEB_CTX"
        docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" stop web 2>/dev/null || true
        docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" rm -f web 2>/dev/null || true
        docker rm -f "${COMPOSE_PROJECT}-web-1" 2>/dev/null || true
        WEB_PORT="${WEB_PORT:-8080}"
        docker run -d \
            --name "${COMPOSE_PROJECT}-web-1" \
            --network "${COMPOSE_PROJECT}_default" \
            --restart unless-stopped \
            --label "com.docker.compose.project=${COMPOSE_PROJECT}" \
            --label "com.docker.compose.service=web" \
            -p "${WEB_PORT}:80" \
            "${COMPOSE_PROJECT}_web:latest"
        ok "web 容器已重建"
    else
        rm -rf "$WEB_CTX"
        warn "web 镜像构建失败，跳过 web 更新"
    fi
fi

# ---- 重启 api ----
# 使用 up -d --force-recreate 以应用 docker-compose.yml 变更（如端口映射）
log "重建 API 容器..."
API_IMAGE=$(docker inspect "$API_CONTAINER" --format '{{.Config.Image}}' 2>/dev/null || echo "reference-backend-api:latest")
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" up -d --force-recreate api
ok "API 容器已重建（应用 compose 变更）"

# 重建后需重新注入后端代码（容器已从镜像重建，docker cp 的内容会丢失）
log "重新注入后端代码..."
API_CONTAINER=$(docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" ps -q api 2>/dev/null)
docker cp reference-backend/app/. "$API_CONTAINER":/app/app/
docker cp reference-backend/alembic/. "$API_CONTAINER":/app/alembic/
docker cp reference-backend/alembic.ini "$API_CONTAINER":/app/alembic.ini
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" restart api
ok "后端代码已重新注入并重启"

# ---- 清理 ----
rm -rf dist.bak

echo ""
ok "升级完成"
echo ""
echo "  访问控制台确认功能正常。"
echo "  如遇问题可回滚数据库:"
echo "    gunzip -c $BACKUP_DIR/pre-update-${TS}.sql.gz | docker compose -f $COMPOSE_FILE -p $COMPOSE_PROJECT exec -T mysql mysql -u\${MYSQL_USER:-cmdb} -p\${MYSQL_PASSWORD:-cmdb123} \${MYSQL_DATABASE:-cmdb}"
