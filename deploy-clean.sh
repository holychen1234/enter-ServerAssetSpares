#!/usr/bin/env bash
# ================================================================
# 干净部署脚本 — 清空所有旧数据和容器，全新安装
# ================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERR ]${NC}  $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$SCRIPT_DIR"

IMAGES_TAR="cmdb-clean-amd64.tar"
COMPOSE_FILE="docker-compose.yml"
PROJECT="cmdb"

if [ ! -f "$IMAGES_TAR" ]; then
    warn "$IMAGES_TAR 不存在，尝试使用 cmdb-images.tar"
    IMAGES_TAR="cmdb-images.tar"
    [ -f "$IMAGES_TAR" ] || { err "找不到镜像包"; exit 1; }
fi

echo ""
warn "============================================"
warn "  此操作将清空所有旧容器和数据库！"
warn "  数据将不可恢复！"
warn "============================================"
echo ""
read -r -p "输入 'YES' 确认清空重建: " ans
if [ "$ans" != "YES" ]; then
    log "已取消"
    exit 0
fi

# 1. 彻底清空
log "停止并删除所有旧容器和数据卷..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT" down -v 2>/dev/null || true
docker rm -f cmdb-api-1 cmdb-web-1 cmdb-mysql-1 cmdb-mcp-1 2>/dev/null || true

# 2. 删除旧镜像
log "删除旧镜像..."
docker rmi reference-backend-api:latest mysql:8.0 nginx:latest dmtf/redfish-mockup-server:latest 2>/dev/null || true

# 3. 加载新镜像
log "加载 amd64 镜像..."
docker load -i "$IMAGES_TAR"
ok "镜像加载完成"

# 4. 初始化 .env
if [ ! -f reference-backend/.env ]; then
    cp reference-backend/.env.example reference-backend/.env
    chmod 600 reference-backend/.env
    # 生成随机 JWT_SECRET
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets;print(secrets.token_hex(32))")
    sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$JWT_SECRET/" reference-backend/.env
    ok ".env 已创建，JWT_SECRET 已生成"
fi

# 5. 注入最新后端代码到镜像（确保运行的是最新版本）
log "启动服务..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT" up -d

# 6. 注入后端代码
log "注入最新后端代码..."
API_CONTAINER=$(docker compose -f "$COMPOSE_FILE" -p "$PROJECT" ps -q api 2>/dev/null)
if [ -n "$API_CONTAINER" ]; then
    docker cp reference-backend/app/. "$API_CONTAINER":/app/app/
    ok "后端代码已更新到容器"
fi

# 7. 重启使代码生效
docker compose -f "$COMPOSE_FILE" -p "$PROJECT" restart api
ok "API 容器已重启"

# 8. 注入代码到 MCP 容器并重启
MCP_CONTAINER=$(docker compose -f "$COMPOSE_FILE" -p "$PROJECT" ps -q mcp 2>/dev/null)
if [ -n "$MCP_CONTAINER" ]; then
    docker cp reference-backend/app/. "$MCP_CONTAINER":/app/app/
    docker restart "$MCP_CONTAINER"
    ok "MCP 容器已更新并重启"
fi

IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "服务器IP")
PORT="${WEB_PORT:-8080}"

echo ""
echo "========================================"
ok "部署完成！"
echo "  控制台:   http://${IP}:${PORT}"
echo "  默认账号: admin / admin123"
echo ""
echo "  常用命令:"
echo "    ./deploy-offline.sh status   查看状态"
echo "    ./deploy-offline.sh backup   备份数据库"
echo "    ./deploy-offline.sh logs     查看日志"
echo "========================================"
