#!/usr/bin/env bash
# ================================================================
# 下载 MCP 离线 wheel 包（在联网开发机上运行一次即可）
# ================================================================
# 产出: reference-backend/wheels/ 目录，包含 mcp 及全部依赖
#
# 用法:
#   ./download-wheels.sh              # 下载最新版
#   ./download-wheels.sh --clean       # 清空重新下载
# ================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WHEELS_DIR="$SCRIPT_DIR/wheels"

if [ "${1:-}" = "--clean" ]; then
    rm -rf "$WHEELS_DIR"
fi

mkdir -p "$WHEELS_DIR"

echo "[INFO]  下载 mcp 及全部依赖到 $WHEELS_DIR ..."
pip download "mcp>=1.27" -d "$WHEELS_DIR"

echo ""
echo "[ OK ]  下载完成 ($(ls "$WHEELS_DIR" | wc -l) 个文件, $(du -sh "$WHEELS_DIR" | cut -f1))"
echo ""
echo "  将此目录和项目一起打包即可离线部署："
echo "    cd .. && ./make-update-zip.sh"
