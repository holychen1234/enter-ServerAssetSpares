#!/usr/bin/env bash
# ================================================================
# 离线部署脚本（在目标服务器上运行，无需外网）
# ================================================================
# 前提：已解压 cmdb-offline.tar.gz，当前目录包含 cmdb-images.tar
#
# 用法:
#   ./deploy-offline.sh           部署
#   ./deploy-offline.sh down      停止
#   ./deploy-offline.sh logs      日志
#   ./deploy-offline.sh status    状态
#   ./deploy-offline.sh backup    备份
#   ./deploy-offline.sh reset     清空重建
# ================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERR ]${NC}  $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$SCRIPT_DIR"

IMAGES_TAR="cmdb-images.tar"
ENV_FILE="reference-backend/.env"
ENV_EXAMPLE="reference-backend/.env.example"
COMPOSE_FILE="docker-compose.yml"
BACKUP_DIR="backups"

CMD="${1:-up}"

# ---- 前置检查 ----
check_prereqs() {
    local missing=0
    if ! command -v docker &>/dev/null; then
        err "未找到 docker，请先安装 Docker 24+"
        missing=1
    fi
    if ! docker compose version &>/dev/null; then
        err "未找到 docker compose v2 插件"
        missing=1
    fi
    if [ ! -f "$IMAGES_TAR" ]; then
        err "未找到 $IMAGES_TAR，请确保与 cmdb-offline.tar.gz 一同解压"
        missing=1
    fi
    return $missing
}

# ---- 加载镜像 ----
load_images() {
    if docker images mysql:8.0 --format '{{.Tag}}' 2>/dev/null | grep -q .; then
        log "镜像已存在，跳过导入"
        return
    fi
    log "导入 Docker 镜像（可能需要几分钟）..."
    docker load -i "$IMAGES_TAR"
    ok "镜像导入完成"
}

# ---- 初始化 .env ----
init_env() {
    if [ ! -f "$ENV_FILE" ]; then
        log "创建 .env ..."
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
    fi
    chmod 600 "$ENV_FILE"

    set -a; source "$ENV_FILE"; set +a

    if [[ "${JWT_SECRET:-change-me-in-production-please-use-a-long-random-string}" == "change-me-in-production-please-use-a-long-random-string" ]]; then
        local new_secret
        new_secret=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || date +%s | sha256sum | head -c64)
        sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$new_secret/" "$ENV_FILE"
        ok "JWT_SECRET 已自动生成"
    fi
    ok ".env 权限已设为 600"
}

# ---- 部署 ----
do_up() {
    check_prereqs || exit 1
    load_images
    init_env

    log "启动服务..."
    docker compose -f "$COMPOSE_FILE" -p cmdb up -d

    local ip
    ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "服务器IP")
    local port="${WEB_PORT:-8080}"

    echo ""
    ok "部署完成"
    echo "  控制台:   http://${ip}:${port}"
    echo "  API 文档: http://${ip}:${port}/api/docs"
    echo ""
    echo "  默认账号: admin / admin123"
    echo ""
    warn "重要提示:"
    echo "  • 请修改 reference-backend/.env 中的 MYSQL_PASSWORD 和 JWT_SECRET"
    echo "  • 防火墙放行端口: sudo ufw allow ${port}/tcp"
    echo "  • 定期备份: ./deploy-offline.sh backup"
}

do_down() {
    docker compose -f "$COMPOSE_FILE" -p cmdb down
    ok "服务已停止（数据卷保留）"
}

do_logs() {
    docker compose -f "$COMPOSE_FILE" -p cmdb logs -f --tail=200
}

do_status() {
    docker compose -f "$COMPOSE_FILE" -p cmdb ps
}

do_backup() {
    init_env
    mkdir -p "$BACKUP_DIR"
    local ts=$(date +%Y%m%d-%H%M%S)
    local file="$BACKUP_DIR/cmdb-backup-${ts}.sql.gz"
    set -a; source "$ENV_FILE"; set +a
    docker compose -f "$COMPOSE_FILE" -p cmdb exec -T mysql \
        mysqldump -u"${MYSQL_USER:-cmdb}" -p"${MYSQL_PASSWORD:-cmdb123}" \
        --single-transaction --routines --triggers "${MYSQL_DATABASE:-cmdb}" \
        | gzip > "$file"
    ok "备份完成: $file ($(du -h "$file" | cut -f1))"
}

do_reset() {
    warn "此操作将清空所有数据！"
    read -r -p "输入 yes 确认: " ans
    if [[ "$ans" == "yes" ]]; then
        docker compose -f "$COMPOSE_FILE" -p cmdb down -v
        ok "已清空"
    fi
}

# ---- 路由 ----
case "$CMD" in
    up|start)   do_up ;;
    down|stop)  do_down ;;
    logs)       do_logs ;;
    status|ps)  do_status ;;
    backup)     do_backup ;;
    reset)      do_reset ;;
    *)
        echo "用法: $0 {up|down|logs|status|backup|reset}"
        exit 1
        ;;
esac
