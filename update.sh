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

# ---- 参数解析 ----
SKIP_BACKUP=false
ZIP_FILE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --no-backup|-n)
            SKIP_BACKUP=true
            shift
            ;;
        *)
            ZIP_FILE="$1"
            shift
            ;;
    esac
done

if [ -z "$ZIP_FILE" ]; then
    echo "用法: $0 [--no-backup|-n] <zip包路径>"
    echo "选项:"
    echo "  -n, --no-backup  跳过数据库备份（加速更新，适合高频小改动）"
    echo ""
    echo "示例:"
    echo "  $0 ./cmdb-update-20260715-095728.zip"
    echo "  $0 -n ./cmdb-update-20260715-095728.zip         # 快速更新，不备份DB"
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

# ---- 备份数据库（可通过 --no-backup 跳过）----
BACKUP_SQL=""
if [ "$SKIP_BACKUP" = true ]; then
    warn "已跳过数据库备份 (--no-backup)"
else
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
fi  # --no-backup 判断结束

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
if [ "$SKIP_BACKUP" != true ] && [ -n "${TS:-}" ]; then
    echo "  如遇问题可回滚数据库:"
    echo "    gunzip -c $BACKUP_DIR/pre-update-${TS}.sql.gz | docker compose -f $COMPOSE_FILE -p $COMPOSE_PROJECT exec -T mysql mysql -u\${MYSQL_USER:-cmdb} -p\${MYSQL_PASSWORD:-cmdb123} \${MYSQL_DATABASE:-cmdb}"
else
    echo "  (本次更新跳过了数据库备份)"
fi
