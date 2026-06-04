#!/usr/bin/env bash
# ================================================================
# CMDB API 验证脚本
# 测试私有化环境的主机资产及 AI 查询接口
# ================================================================
# 用法:
#   ./verify-api.sh <BASE_URL> [API_KEY]
#
# 示例:
#   ./verify-api.sh http://10.222.60.89:8080
#   ./verify-api.sh http://10.222.60.89:8080 "sk-xxxx"
#
# 前置条件:
#   - 先登录获取 JWT token（脚本自动处理）
#   - AI_API_KEY 在目标环境的 .env 中已配置
# ================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()   { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR ]${NC}  $*"; }

BASE_URL="${1:-}"
API_KEY="${2:-}"

if [ -z "$BASE_URL" ]; then
    echo "用法: $0 <BASE_URL> [API_KEY]"
    echo "示例: $0 http://10.222.60.89:8080"
    exit 1
fi

BASE_URL="${BASE_URL%/}"
API_BASE="${BASE_URL}/api"

# ─── 输出分隔 ───────────────────────────────────────────────────
section() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $*${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ─── 1. 基础连通性检查 ──────────────────────────────────────────
section "1. 基础连通性检查"

log "GET ${BASE_URL}/healthz"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/healthz" 2>&1 || true)

if [ "$HTTP" = "200" ]; then
    BODY=$(curl -s "${BASE_URL}/healthz")
    ok "服务可达 (HTTP ${HTTP}): ${BODY}"
else
    err "服务不可达 (HTTP ${HTTP})，请检查地址和端口"
    exit 1
fi

# ─── 2. JWT 登录获取 token ──────────────────────────────────────
section "2. JWT 认证"

# 使用 seed 数据中的默认账号
USERNAME="${CMDB_USERNAME:-admin}"
PASSWORD="${CMDB_PASSWORD:-admin123}"

log "POST ${BASE_URL}/api/auth/login (username=${USERNAME})"
LOGIN_RESP=$(curl -s -w "\n%{http_code}" \
    -X POST "${API_BASE}/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}")

HTTP=$(echo "$LOGIN_RESP" | tail -1)
BODY=$(echo "$LOGIN_RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
    TOKEN=$(echo "$BODY" | grep -o '"access_token":"[^"]*"' | head -1 | sed 's/"access_token":"//;s/"//')
    USER_INFO=$(echo "$BODY" | grep -o '"username":"[^"]*"' | head -1)
    ok "登录成功: ${USER_INFO} (HTTP ${HTTP})"
elif [ "$HTTP" = "403" ] || [ "$HTTP" = "401" ]; then
    warn "登录失败 (HTTP ${HTTP})，可能是密码已修改"
    warn "请设置环境变量后重试: CMDB_USERNAME=xxx CMDB_PASSWORD=xxx $0 $*"
    TOKEN=""
else
    warn "登录请求异常 (HTTP ${HTTP})"
    TOKEN=""
fi

AUTH_HEADER=()
if [ -n "${TOKEN:-}" ]; then
    AUTH_HEADER=(-H "Authorization: Bearer ${TOKEN}")
fi

# ─── 3. 主机资产 API（JWT 鉴权）─────────────────────────────────
section "3. 主机资产 API (JWT)"

log "GET ${BASE_URL}/api/servers"
SERVERS_RESP=$(curl -s -w "\n%{http_code}" "${API_BASE}/servers" "${AUTH_HEADER[@]:+${AUTH_HEADER[@]}}")
HTTP=$(echo "$SERVERS_RESP" | tail -1)
BODY=$(echo "$SERVERS_RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
    COUNT=$(echo "$BODY" | python3 -c "import sys,json; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "?")
    ok "获取主机列表成功: ${COUNT} 台主机 (HTTP ${HTTP})"
    echo "$BODY" | python3 -c "
import sys, json
servers = json.load(sys.stdin)
print()
print(f'{\"主机名\":<22} {\"状态\":<10} {\"厂商\":<10} {\"型号\":<22} {\"机房\":<10} {\"业务IP\"}')
print('-' * 90)
for s in servers[:15]:
    loc = s.get('location', {})
    print(f'{s[\"hostname\"]:<22} {s[\"status\"]:<10} {s[\"manufacturer\"]:<10} {s[\"model\"]:<22} {loc.get(\"idc\",\"\"):<10} {s[\"bizIp\"]}')
if len(servers) > 15:
    print(f'... 还有 {len(servers)-15} 台未显示')
" 2>/dev/null || echo "$BODY" | head -50
elif [ "$HTTP" = "401" ]; then
    warn "未授权 (HTTP 401)，token 可能过期或无效"
else
    warn "请求失败 (HTTP ${HTTP})"
    echo "$BODY" | head -5
fi

# ─── 4. 单台主机详情 ─────────────────────────────────────────────
section "4. 主机详情 (按 hostname)"

FIRST_HOST=$(echo "$BODY" | python3 -c "
import sys, json
servers = json.load(sys.stdin)
if servers:
    print(servers[0]['hostname'] + '|' + servers[0].get('sn',''))
" 2>/dev/null || echo "")

if [ -n "$FIRST_HOST" ]; then
    HOSTNAME=$(echo "$FIRST_HOST" | cut -d'|' -f1)
    SN=$(echo "$FIRST_HOST" | cut -d'|' -f2)

    log "GET ${BASE_URL}/api/servers?hostname=${HOSTNAME}  (通过列表结果取第一台)"

    DETAIL_RESP=$(curl -s -w "\n%{http_code}" \
        "${API_BASE}/servers" "${AUTH_HEADER[@]:+${AUTH_HEADER[@]}}")
    # 用 hostname 筛选（通过 list 接口做简单过滤）
    DETAIL=$(echo "$DETAIL_RESP" | sed '$d' | python3 -c "
import sys, json
servers = json.load(sys.stdin)
for s in servers:
    if s['hostname'] == '${HOSTNAME}':
        print(json.dumps(s, indent=2, ensure_ascii=False))
        break
" 2>/dev/null)

    if [ -n "$DETAIL" ]; then
        ok "主机 ${HOSTNAME} (SN: ${SN}) 详情:"
        echo "$DETAIL"
    fi
else
    warn "无主机数据，跳过详情查询"
fi

# ─── 5. AI 接口 ─────────────────────────────────────────────────
section "5. AI 查询接口 (X-API-Key)"

if [ -z "$API_KEY" ]; then
    warn "未提供 API_KEY，尝试不带 key 调用（预期返回 401 或 501）"
    warn "如已配置 AI_API_KEY，请设置后重试: $0 ${BASE_URL} \"your-key\""
    AI_HEADER=()
    SKIP_AI_CHECKS=true
else
    AI_HEADER=(-H "X-API-Key: ${API_KEY}")
    SKIP_AI_CHECKS=false
fi

# 5a. search-servers
log "GET ${BASE_URL}/api/ai/search-servers?keyword=&limit=5"
AI_RESP=$(curl -s -w "\n%{http_code}" \
    "${API_BASE}/ai/search-servers?keyword=&limit=5" \
    "${AI_HEADER[@]:+${AI_HEADER[@]}}")
HTTP=$(echo "$AI_RESP" | tail -1)
AI_BODY=$(echo "$AI_RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
    COUNT=$(echo "$AI_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count','?'))" 2>/dev/null || echo "?")
    ok "search-servers: ${COUNT} 台主机 (HTTP ${HTTP})"
    echo "$AI_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d.get('items', [])[:5]:
    loc = s.get('location', {})
    print(f'  {s[\"hostname\"]:<22} {s[\"status\"]:<10} {s[\"manufacturer\"]:<10} {s[\"model\"]:<22} {s[\"cpuModel\"]}')
" 2>/dev/null
elif [ "$HTTP" = "501" ]; then
    warn "search-servers: AI_API_KEY 未在服务端配置 (HTTP 501)"
elif [ "$HTTP" = "401" ]; then
    warn "search-servers: API Key 无效或未提供 (HTTP 401)"
else
    warn "search-servers: HTTP ${HTTP}"
fi

# 5b. get-server-detail
if [ -n "${FIRST_HOST:-}" ] && [ "$SKIP_AI_CHECKS" != "true" ]; then
    log "GET ${BASE_URL}/api/ai/get-server-detail?identifier=${HOSTNAME}"
    AI_RESP=$(curl -s -w "\n%{http_code}" \
        "${API_BASE}/ai/get-server-detail?identifier=${HOSTNAME}" \
        "${AI_HEADER[@]:+${AI_HEADER[@]}}")
    HTTP=$(echo "$AI_RESP" | tail -1)
    AI_BODY=$(echo "$AI_RESP" | sed '$d')

    if [ "$HTTP" = "200" ]; then
        FOUND=$(echo "$AI_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('found',False))" 2>/dev/null || echo "false")
        if [ "$FOUND" = "True" ]; then
            ok "get-server-detail: 找到 ${HOSTNAME}"
        else
            warn "get-server-detail: 未找到 ${HOSTNAME}"
        fi
    else
        warn "get-server-detail: HTTP ${HTTP}"
    fi
fi

# 5c. search-parts
log "GET ${BASE_URL}/api/ai/search-parts?keyword=&limit=5"
AI_RESP=$(curl -s -w "\n%{http_code}" \
    "${API_BASE}/ai/search-parts?keyword=&limit=5" \
    "${AI_HEADER[@]:+${AI_HEADER[@]}}")
HTTP=$(echo "$AI_RESP" | tail -1)
AI_BODY=$(echo "$AI_RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
    COUNT=$(echo "$AI_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count','?'))" 2>/dev/null || echo "?")
    ok "search-parts: ${COUNT} 个备件 (HTTP ${HTTP})"
    echo "$AI_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p in d.get('items', [])[:5]:
    print(f'  {p[\"category\"]:<10} {p[\"brand\"]:<12} {p[\"model\"]:<24} {p[\"spec\"]:<28} 库存={p[\"stock\"]}')
" 2>/dev/null
elif [ "$HTTP" = "501" ]; then
    warn "search-parts: AI_API_KEY 未在服务端配置 (HTTP 501)"
elif [ "$HTTP" = "401" ]; then
    warn "search-parts: API Key 无效或未提供 (HTTP 401)"
else
    warn "search-parts: HTTP ${HTTP}"
fi

# 5d. get-server-stats
log "GET ${BASE_URL}/api/ai/get-server-stats?group_by=status"
AI_RESP=$(curl -s -w "\n%{http_code}" \
    "${API_BASE}/ai/get-server-stats?group_by=status" \
    "${AI_HEADER[@]:+${AI_HEADER[@]}}")
HTTP=$(echo "$AI_RESP" | tail -1)
AI_BODY=$(echo "$AI_RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
    TOTAL=$(echo "$AI_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total','?'))" 2>/dev/null || echo "?")
    ok "get-server-stats: 共 ${TOTAL} 台主机 (HTTP ${HTTP})"
    echo "$AI_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  维度: {d[\"groupBy\"]}, 总数: {d[\"total\"]}')
for it in d.get('items', []):
    print(f'  {it[\"key\"]:<16} {it[\"count\"]} 台')
" 2>/dev/null
elif [ "$HTTP" = "501" ]; then
    warn "get-server-stats: AI_API_KEY 未在服务端配置 (HTTP 501)"
elif [ "$HTTP" = "401" ]; then
    warn "get-server-stats: API Key 无效或未提供 (HTTP 401)"
else
    warn "get-server-stats: HTTP ${HTTP}"
fi

# 5e. OpenAPI schema
log "GET ${BASE_URL}/api/ai/openapi.json"
SCHEMA_RESP=$(curl -s -w "\n%{http_code}" "${API_BASE}/ai/openapi.json")
HTTP=$(echo "$SCHEMA_RESP" | tail -1)

if [ "$HTTP" = "200" ]; then
    ok "openapi.json: 可获取 (HTTP ${HTTP}) — Dify 导入地址: ${API_BASE}/ai/openapi.json"
else
    warn "openapi.json: HTTP ${HTTP}"
fi

# ─── 6. 总结 ─────────────────────────────────────────────────────
section "验证总结"

echo ""
echo "  CMDB 地址:    ${BASE_URL}"
echo "  OpenAPI:      ${API_BASE}/ai/openapi.json"
echo ""
echo "  Dify 接入步骤:"
echo "    1. 在服务端 .env 设置 AI_API_KEY=<your-key>"
echo "    2. 重启容器: docker compose restart api"
echo "    3. Dify → 工具 → 导入 OpenAPI → ${API_BASE}/ai/openapi.json"
echo "    4. 配置 X-API-Key 鉴权"
echo ""
