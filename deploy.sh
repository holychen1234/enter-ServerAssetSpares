#!/usr/bin/env bash
# ================================================================
# 主机资产管理平台 — 一键部署脚本
# ================================================================
# 前置条件: Linux + Docker 24+ + docker compose v2
#
# 用法:
#   ./deploy.sh              部署（首次自动初始化）
#   ./deploy.sh down          停止服务（保留数据）
#   ./deploy.sh reset         停止 + 清空数据库（危险操作）
#   ./deploy.sh logs          实时日志
#   ./deploy.sh status        服务状态
#   ./deploy.sh backup        导出 MySQL 备份
#   ./deploy.sh restore FILE  从备份恢复
#   ./deploy.sh mock-on       启动 Redfish Mock（开发/演示）
#   ./deploy.sh mock-off      停止 Redfish Mock
# ================================================================

set -euo pipefail

# ---- 目录定位 ----
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/reference-backend"
COMPOSE_FILE="$BACKEND_DIR/docker-compose.yml"
ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"
BACKUP_DIR="$SCRIPT_DIR/backups"

CMD="${1:-up}"

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERR ]${NC}  $*" >&2; }

# ---- 前置检查 ----
check_prereqs() {
    local missing=0

    if ! command -v docker &>/dev/null; then
        err "未找到 docker，请先安装 Docker 24+"
        err "  curl -fsSL https://get.docker.com | bash"
        missing=1
    fi

    if ! docker compose version &>/dev/null; then
        err "未找到 docker compose v2 插件"
        err "  sudo apt install docker-compose-v2    (Ubuntu/Debian)"
        err "  sudo yum install docker-compose-plugin (RHEL/CentOS)"
        missing=1
    fi

    return $missing
}

# ---- 环境初始化 ----
init_env() {
    if [ ! -f "$ENV_FILE" ]; then
        log "首次部署，从 .env.example 创建 .env"
        cp "$ENV_EXAMPLE" "$ENV_FILE"
    fi

    # 权限加固
    chmod 600 "$ENV_FILE"
    ok ".env 权限已设为 600"

    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a

    # JWT_SECRET 自动生成
    if [[ "${JWT_SECRET:-change-me-in-production-please-use-a-long-random-string}" == "change-me-in-production-please-use-a-long-random-string" ]]; then
        local new_secret
        new_secret=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
        sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$new_secret/" "$ENV_FILE"
        ok "JWT_SECRET 已自动生成"
    fi
}

# ---- Docker Compose 包装 ----
compose_cmd() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

# ---- 部署 ----
do_up() {
    check_prereqs || exit 1
    init_env

    log "构建镜像并启动服务..."
    compose_cmd up -d --build

    echo ""
    ok "部署完成"
    echo ""

    local ip
    ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "服务器IP")
    local port="${WEB_PORT:-8080}"

    echo "  ╔════════════════════════════════════════════════╗"
    echo "  ║        主机资产管理平台                       ║"
    echo "  ╠════════════════════════════════════════════════╣"
    echo "  ║  控制台:   http://${ip}:${port}                  ║"
    echo "  ║  API 文档: http://${ip}:${port}/api/docs         ║"
    echo "  ║  健康检查: http://${ip}:${port}/healthz          ║"
    echo "  ╠════════════════════════════════════════════════╣"
    echo "  ║  默认账号:                                     ║"
    echo "  ║    admin    / admin123      (管理员)           ║"
    echo "  ║    operator / 123456        (运维工程师)       ║"
    echo "  ║    viewer   / 123456        (只读访客)         ║"
    echo "  ╠════════════════════════════════════════════════╣"
    echo "  ║  常用命令:                                     ║"
    echo "  ║    ./deploy.sh logs      查看日志              ║"
    echo "  ║    ./deploy.sh status    服务状态              ║"
    echo "  ║    ./deploy.sh backup    备份数据库            ║"
    echo "  ║    ./deploy.sh down      停止服务              ║"
    echo "  ╚════════════════════════════════════════════════╝"
    echo ""
    warn "重要提示:"
    echo "  • 请用 ./deploy.sh backup 定期备份数据库"
    echo "  • 生产环境建议前面套一层 HTTPS（参考 reference-backend/nginx/default-https.conf.example）"
    echo "  • Redfish Mock 默认不启动，生产环境无需它"
}

# ---- 停止 ----
do_down() {
    log "停止全部服务..."
    compose_cmd down
    ok "服务已停止（数据卷保留）"
}

# ---- 重置（清空数据） ----
do_reset() {
    warn "此操作将清空所有 MySQL 数据，不可恢复！"
    read -r -p "确认清空？输入 yes 继续: " ans
    if [[ "$ans" == "yes" ]]; then
        log "停止服务并删除数据卷..."
        compose_cmd down -v
        ok "数据已清空"
    else
        log "已取消"
    fi
}

# ---- 日志 ----
do_logs() {
    compose_cmd logs -f --tail=200
}

# ---- 状态 ----
do_status() {
    compose_cmd ps
    echo ""
    log "各容器资源使用:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
        $(compose_cmd ps -q) 2>/dev/null || true
}

# ---- 备份 ----
do_backup() {
    init_env
    mkdir -p "$BACKUP_DIR"

    local ts
    ts=$(date +%Y%m%d-%H%M%S)
    local file="$BACKUP_DIR/cmdb-backup-${ts}.sql.gz"

    log "导出数据库到 $file ..."
    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a

    compose_cmd exec -T mysql \
        mysqldump -u"${MYSQL_USER:-cmdb}" -p"${MYSQL_PASSWORD:-cmdb123}" \
        --single-transaction --routines --triggers "${MYSQL_DATABASE:-cmdb}" \
        | gzip > "$file"

    ok "备份完成: $file ($(du -h "$file" | cut -f1))"
    echo ""
    log "备份文件列表:"
    ls -lh "$BACKUP_DIR"/*.sql.gz 2>/dev/null || echo "  (无)"
}

# ---- 恢复 ----
do_restore() {
    local file="$1"
    if [ ! -f "$file" ]; then
        err "文件不存在: $file"
        exit 1
    fi

    init_env
    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a

    warn "将从 $file 恢复数据库，当前数据将被覆盖！"
    read -r -p "确认恢复？输入 yes 继续: " ans
    if [[ "$ans" != "yes" ]]; then
        log "已取消"
        return
    fi

    log "恢复数据库..."
    gunzip -c "$file" | compose_cmd exec -T mysql \
        mysql -u"${MYSQL_USER:-cmdb}" -p"${MYSQL_PASSWORD:-cmdb123}" "${MYSQL_DATABASE:-cmdb}"

    ok "恢复完成"
}

# ---- Redfish Mock 开关 ----
do_mock_on() {
    log "启动 Redfish Mock..."
    compose_cmd --profile mock up -d redfish-mock
    ok "Redfish Mock 已启动 (http://localhost:8000)"
}

do_mock_off() {
    log "停止 Redfish Mock..."
    compose_cmd --profile mock rm -sf redfish-mock 2>/dev/null || \
        docker rm -f cmdb-redfish-mock-1 2>/dev/null || true
    ok "Redfish Mock 已停止"
}

# ---- 路由 ----
case "$CMD" in
    up|start)
        do_up
        ;;
    down|stop)
        do_down
        ;;
    reset)
        do_reset
        ;;
    logs)
        do_logs
        ;;
    status|ps)
        do_status
        ;;
    backup)
        do_backup
        ;;
    restore)
        do_restore "${2:-}"
        ;;
    mock-on)
        do_mock_on
        ;;
    mock-off)
        do_mock_off
        ;;
    *)
        echo "用法: $0 {up|down|reset|logs|status|backup|restore|mock-on|mock-off}"
        echo ""
        echo "  up         构建并启动全部服务"
        echo "  down       停止服务（保留数据）"
        echo "  reset      停止 + 清空数据库（危险）"
        echo "  logs       查看实时日志"
        echo "  status     查看服务状态和资源使用"
        echo "  backup     导出 MySQL 备份到 backups/"
        echo "  restore F  从指定备份文件恢复"
        echo "  mock-on    启动 Redfish Mock（开发用）"
        echo "  mock-off   停止 Redfish Mock"
        exit 1
        ;;
esac
