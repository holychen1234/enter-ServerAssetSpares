#!/usr/bin/env bash
# ================================================================
# 制作离线升级 zip 包（在开发机上运行）
# ================================================================
# 此脚本会构建前端 dist/，然后打包成可在私有化环境直接使用的 zip。
# 输出: cmdb-update-YYYYMMDD-HHMMSS.zip
# ================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC}  $*"; }
err()  { echo -e "${RED}[ERR ]${NC}  $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$SCRIPT_DIR"

TS=$(date +%Y%m%d-%H%M%S)
OUTPUT="cmdb-update-${TS}.zip"

# ---- 构建前端 ----
log "构建前端..."
if command -v pnpm &>/dev/null && command -v node &>/dev/null; then
    VITE_API_MODE=internal pnpm install --no-frozen-lockfile
    VITE_API_MODE=internal pnpm run build:prod
elif command -v docker &>/dev/null; then
    docker run --rm \
        -v "$SCRIPT_DIR":/app -w /app \
        -e VITE_API_MODE=internal \
        -e VITE_INTERNAL_API_BASE=/api \
        node:20-alpine sh -c "
            corepack enable && \
            corepack prepare pnpm@8.6.12 --activate && \
            pnpm install --no-frozen-lockfile && \
            pnpm run build:prod
        "
else
    err "需要 pnpm/node 或 Docker"
    exit 1
fi
ok "前端构建完成"

# ---- 打包 ----
log "打包 $OUTPUT ..."

# 可选：运行 reference-backend/download-wheels.sh 预下载 mcp 离线包
# 如果私有化环境无法联网，打包前先执行：
#   cd reference-backend && ./download-wheels.sh && cd ..
if [ -d reference-backend/wheels ]; then
    log "已包含离线 wheels ($(ls reference-backend/wheels/*.whl 2>/dev/null | wc -l) 个文件)"
else
    warn "未找到 wheels 目录，私有化环境需手动安装 mcp（需联网）"
    warn "如需离线安装，请先运行: cd reference-backend && ./download-wheels.sh"
fi

zip -r "$OUTPUT" \
    src/ \
    reference-backend/ \
    public/ \
    dist/ \
    supabase/ \
    index.html \
    package.json pnpm-lock.yaml \
    vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json \
    tailwind.config.ts postcss.config.js components.json eslint.config.js \
    update.sh \
    -x "*/node_modules/*" "*/.git/*" "*/backups/*" "*/__pycache__/*" "*.pyc"

ok "打包完成: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
echo ""
echo "将此文件上传到私有化环境后执行:"
echo "  ./update.sh $OUTPUT"
