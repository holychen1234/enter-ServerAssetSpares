#!/usr/bin/env bash
# ================================================================
# 离线部署 — 镜像导出脚本（在能访问 Docker Hub 的机器上运行）
# ================================================================
# 运行此脚本后，将生成的 cmdb-offline.tar.gz 传输到目标服务器，
# 然后运行 deploy-offline.sh 完成部署。
# ================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC}  $*"; }
err()  { echo -e "${RED}[ERR ]${NC}  $*" >&2; }

OUTPUT="cmdb-offline.tar.gz"
IMAGES_TAR="cmdb-images.tar"

# ---- 检查 Docker ----
if ! command -v docker &>/dev/null; then
    err "需要 Docker，请先安装"
    exit 1
fi

# ---- 拉取基础镜像 ----
#log "拉取基础镜像..."
#docker pull mysql:8.0
#docker pull python:3.12-slim
#docker pull node:20-alpine
#docker pull nginx:latest
#docker pull dmtf/redfish-mockup-server:latest
#ok "基础镜像拉取完成"

# ---- 构建应用镜像 ----
log "构建后端镜像 reference-backend-api:latest..."
docker build -t reference-backend-api:latest reference-backend/
ok "后端镜像构建完成"

log "构建前端（VITE_API_MODE=internal，使用 node:20-alpine 容器）..."
docker run --rm \
    -v "$SCRIPT_DIR":/app \
    -w /app \
    -e VITE_API_MODE=internal \
    -e VITE_INTERNAL_API_BASE=/api \
    node:20-alpine sh -c "
        corepack enable && \
        corepack prepare pnpm@8.6.12 --activate && \
        pnpm install --no-frozen-lockfile && \
        pnpm run build:prod
    "
ok "前端构建完成 (dist/)"

# ---- 导出 Docker 镜像 ----
log "导出 Docker 镜像到 $IMAGES_TAR ..."
docker save -o "$IMAGES_TAR" \
    mysql:8.0 \
    python:3.12-slim \
    node:20-alpine \
    nginx:latest \
    reference-backend-api:latest \
    dmtf/redfish-mockup-server:latest
ok "镜像导出完成 ($(du -h "$IMAGES_TAR" | cut -f1))"

# ---- 打包 ----
log "打包离线部署包 $OUTPUT ..."
tar czf "$OUTPUT" \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='backups' \
    "$IMAGES_TAR" \
    dist/ \
    docker-compose.yml \
    reference-backend/.env.example \
    reference-backend/init-db/ \
    reference-backend/nginx/ \
    deploy-offline.sh \
    update.sh

ok "打包完成: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
echo ""
echo "============================================"
echo "  下一步:"
echo "  1. scp $OUTPUT user@目标服务器:/opt/"
echo "  2. ssh user@目标服务器"
echo "  3. cd /opt && tar xzf $OUTPUT"
echo "  4. ./deploy-offline.sh"
echo "============================================"
