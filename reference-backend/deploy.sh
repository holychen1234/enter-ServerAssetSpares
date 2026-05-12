#!/usr/bin/env bash
#
# CMDB private-deployment one-shot installer.
# Requires: Linux + Docker 24+ + docker compose plugin.
#
# Usage:
#   ./deploy.sh           # build & start (creates .env from example if missing)
#   ./deploy.sh down      # stop containers, keep data
#   ./deploy.sh reset     # stop + drop database volume (DESTRUCTIVE)
#   ./deploy.sh logs      # tail combined logs

set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

CMD="${1:-up}"

case "$CMD" in
  up)
    if [ ! -f .env ]; then
      echo ">> .env not found, copying from .env.example"
      cp .env.example .env
    fi
    # shellcheck disable=SC1091
    set -a; source .env; set +a
    echo ">> docker compose up -d --build"
    docker compose up -d --build
    docker compose ps
    HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<本机IP>")
    cat <<EOF

================================================================
 CMDB 私有化部署完成
----------------------------------------------------------------
 控制台:        http://${HOST_IP}:${WEB_PORT:-8080}
 API 文档:      http://${HOST_IP}:${WEB_PORT:-8080}/api/docs
 健康检查:      http://${HOST_IP}:${WEB_PORT:-8080}/healthz

 默认账号:
   admin    / admin123     管理员
   operator / 123456       运维
   viewer   / 123456       只读

 常用命令:
   ./deploy.sh logs     查看日志
   ./deploy.sh down     停止 (保留数据)
   ./deploy.sh reset    清空数据库重置
================================================================
EOF
    ;;
  down)
    docker compose down
    ;;
  reset)
    read -r -p "将清空 MySQL 数据卷，是否继续? [y/N] " ans
    if [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]]; then
      docker compose down -v
    else
      echo "已取消"
    fi
    ;;
  logs)
    docker compose logs -f --tail=200
    ;;
  *)
    echo "Usage: $0 {up|down|reset|logs}" >&2
    exit 1
    ;;
esac
