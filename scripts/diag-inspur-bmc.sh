#!/usr/bin/env bash
# =============================================================================
# Inspur（浪潮）BMC 硬盘数据诊断脚本
# 用法:
#   BMC_IP=10.x.x.x BMC_USER=admin BMC_PASS=xxx bash diag-inspur-bmc.sh
#
# 模拟 reference-backend/app/services/bmc.py 的完整 Redfish 调用链：
#   Session Auth → Systems/Chassis 发现 → Storage 现代路径 → Drive 详情
# =============================================================================

set -euo pipefail

: "${BMC_IP:?请设置环境变量 BMC_IP}"
: "${BMC_USER:?请设置环境变量 BMC_USER}"
: "${BMC_PASS:?请设置环境变量 BMC_PASS}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================================================${NC}"
echo -e "${CYAN}  浪潮 Inspur BMC 硬盘数据采集诊断${NC}"
echo -e "${CYAN}  Target: ${BMC_IP}${NC}"
echo -e "${CYAN}========================================================================${NC}"

# ═════════════════════════════════════════════════════════════════════════
# Step 1: Session 认证
# ═════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}━━━ Step 1: Session 认证 (_redfish_session_auth) ━━━${NC}"

SESSION_RESP=$(curl -sk -D - -X POST "https://${BMC_IP}/redfish/v1/SessionService/Sessions" \
  -H "Content-Type: application/json" \
  -d "{\"UserName\":\"${BMC_USER}\",\"Password\":\"${BMC_PASS}\"}" 2>&1)

HTTP_STATUS=$(echo "$SESSION_RESP" | grep "^HTTP" | tail -1 | awk '{print $2}')
X_AUTH_TOKEN=$(echo "$SESSION_RESP" | grep -i "^x-auth-token:" | sed 's/.*:[[:space:]]*//' | tr -d '\r')
LOCATION=$(echo "$SESSION_RESP" | grep -i "^location:" | sed 's/.*:[[:space:]]*//' | tr -d '\r')
SET_COOKIE=$(echo "$SESSION_RESP" | grep -i "^set-cookie:" | tr -d '\r')

echo "  HTTP Status:    ${HTTP_STATUS}"
echo "  X-Auth-Token:   ${X_AUTH_TOKEN:-<未返回>}"
echo "  Location:       ${LOCATION:-<未返回>}"
echo "  Set-Cookie:     ${SET_COOKIE:-<未返回>}"

if [ -n "$X_AUTH_TOKEN" ]; then
    echo -e "  → ${GREEN}Token 获取成功，代码使用 X-Auth-Token header${NC}"
    SESSION_TOKEN="$X_AUTH_TOKEN"
elif [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "201" ]; then
    echo -e "  → ${YELLOW}Session 创建成功但无 X-Auth-Token，代码回退 Basic Auth${NC}"
    if [ -n "$SET_COOKIE" ]; then
        echo -e "  → ${YELLOW}⚠ Inspur 可能使用 Cookie 认证！代码不支持此模式${NC}"
    fi
else
    echo -e "  → ${YELLOW}Session 认证失败 (HTTP ${HTTP_STATUS})，回退 Basic Auth${NC}"
fi

# ═════════════════════════════════════════════════════════════════════════
# Step 2: 集合成员发现 (_redfish_first_member)
# ═════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}━━━ Step 2: 集合成员发现 (_redfish_first_member) ━━━${NC}"

echo "--- GET /redfish/v1/Chassis ---"
CHASSIS_OUT=$(curl -sk -u "${BMC_USER}:${BMC_PASS}" \
  "https://${BMC_IP}/redfish/v1/Chassis" 2>/dev/null)
CHASSIS_PATH=$(echo "$CHASSIS_OUT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
m=(d.get('Members') or [None])[0]
if m: print(m.get('@odata.id','').lstrip('/'))
" 2>/dev/null)
echo "  chassis_path = ${CHASSIS_PATH:-NONE}"

echo "--- GET /redfish/v1/Systems ---"
SYSTEM_OUT=$(curl -sk -u "${BMC_USER}:${BMC_PASS}" \
  "https://${BMC_IP}/redfish/v1/Systems" 2>/dev/null)
SYSTEM_PATH=$(echo "$SYSTEM_OUT" | python3 -c "
import sys,json; d=json.load(sys.stdin)
m=(d.get('Members') or [None])[0]
if m: print(m.get('@odata.id','').lstrip('/'))
" 2>/dev/null)
echo "  system_path = ${SYSTEM_PATH:-NONE}"

if [ -z "$SYSTEM_PATH" ] || [ "$SYSTEM_PATH" = "NONE" ]; then
    echo -e "${RED}✗ Systems 发现失败！${NC}"; exit 1
fi

# ═════════════════════════════════════════════════════════════════════════
# Step 3: _redfish_storage_modern — 核心采集路径
# ═════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}━━━ Step 3: Storage 现代路径 (_redfish_storage_modern) ━━━${NC}"

# 3a: Storage 集合
echo "--- 3a: GET /${SYSTEM_PATH}/Storage ---"
STORAGE_RESP=$(curl -sk -w "\n%{http_code}" -u "${BMC_USER}:${BMC_PASS}" \
  "https://${BMC_IP}/${SYSTEM_PATH}/Storage" 2>/dev/null)
STORAGE_HTTP=$(echo "$STORAGE_RESP" | tail -1)
STORAGE_BODY=$(echo "$STORAGE_RESP" | sed '$d')
echo "  HTTP ${STORAGE_HTTP}"

if [ "$STORAGE_HTTP" != "200" ]; then
    echo -e "  → ${RED}Storage 端点失败，_redfish_storage_modern 返回 []${NC}"
fi

CTRL_PATHS=$(echo "$STORAGE_BODY" | python3 -c "
import sys,json
for m in (json.load(sys.stdin).get('Members') or []):
    print(m.get('@odata.id',''))
" 2>/dev/null)

# 3b: 控制器 Drives 引用
echo "--- 3b: 获取控制器 Drives 引用 ---"
ALL_DRIVE_HREFS=""
while IFS= read -r ctrl; do
    [ -z "$ctrl" ] && continue
    echo "  GET ${ctrl}"
    CTRL_RESP=$(curl -sk -w "\n%{http_code}" -u "${BMC_USER}:${BMC_PASS}" \
      "https://${BMC_IP}${ctrl}" 2>/dev/null)
    CTRL_HTTP=$(echo "$CTRL_RESP" | tail -1)
    CTRL_BODY=$(echo "$CTRL_RESP" | sed '$d')
    echo "    HTTP ${CTRL_HTTP}"
    if [ "$CTRL_HTTP" = "200" ]; then
        HREFS=$(echo "$CTRL_BODY" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for dr in (d.get('Drives') or []):
    href = dr.get('@odata.id','') if isinstance(dr,dict) else str(dr)
    if href.startswith('/redfish'): print(href)
" 2>/dev/null)
        ALL_DRIVE_HREFS="${ALL_DRIVE_HREFS}${HREFS}"$'\n'
        echo "    Drives 引用数: $(echo "$HREFS" | grep -c '^/redfish' || echo 0)"
    fi
done <<< "$CTRL_PATHS"

ALL_DRIVE_HREFS=$(echo "$ALL_DRIVE_HREFS" | grep '^/redfish' | sort -u)
DRIVE_COUNT=$(echo "$ALL_DRIVE_HREFS" | grep -c '^/redfish' || true)
echo "  合计: ${DRIVE_COUNT} 个 Driver @odata.id"

if [ "$DRIVE_COUNT" -eq 0 ]; then
    echo -e "  → ${RED}✗ 零个 Drive 引用！_redfish_storage_modern 返回 []${NC}"
fi

# 3c: 获取单个 Drive 详情（_get_drive）
echo ""
echo "--- 3c: GET 第一个 Drive 详情 (_get_drive) ---"
FIRST_DRIVE=$(echo "$ALL_DRIVE_HREFS" | head -1)

if [ -z "$FIRST_DRIVE" ]; then
    echo -e "${RED}  跳过（无 drive href）${NC}"
else
    DET_RESP=$(curl -sk -w "\n%{http_code}" -u "${BMC_USER}:${BMC_PASS}" \
      "https://${BMC_IP}${FIRST_DRIVE}" 2>/dev/null)
    DET_HTTP=$(echo "$DET_RESP" | tail -1)
    DET_BODY=$(echo "$DET_RESP" | sed '$d')
    echo "  GET ${FIRST_DRIVE}  → HTTP ${DET_HTTP}"

    if [ "$DET_HTTP" = "200" ]; then
        echo "$DET_BODY" | python3 -c "
import sys,json
d=json.load(sys.stdin)
s=d.get('Status') or {}
cap=d.get('CapacityBytes') or 0
gb=round(cap/1073741824,0) if cap else 0
print(f'  Name:          {d.get(\"Name\") or d.get(\"Id\") or \"?\"}')
print(f'  Model:         {d.get(\"Model\") or \"—\"}')
print(f'  SerialNumber:  {d.get(\"SerialNumber\") or None}')
print(f'  CapacityGB:    {gb}')
print(f'  MediaType:     {d.get(\"MediaType\") or \"—\"}')
print(f'  Status.Health: {s.get(\"Health\") or \"OK\"}')
print()
if d.get('Model') and cap > 0:
    print('✓ 数据完整，前端应正常展示')
else:
    print('✗ 关键字段缺失！')
" 2>/dev/null
    else
        echo -e "  → ${RED}请求失败${NC}"
        echo "$DET_BODY" | head -5
    fi
fi

# ═════════════════════════════════════════════════════════════════════════
# Step 4: Chassis/Drives 备选路径
# ═════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}━━━ Step 4: Chassis/Drives 备选路径 (_redfish_chassis_drives) ━━━${NC}"
echo "  (如果 Step 3 返回 []，代码会走到这里)"

if [ -n "$CHASSIS_PATH" ] && [ "$CHASSIS_PATH" != "NONE" ]; then
    echo "  GET /${CHASSIS_PATH}/Drives"
    CHDRV=$(curl -sk -u "${BMC_USER}:${BMC_PASS}" \
      "https://${BMC_IP}/${CHASSIS_PATH}/Drives" 2>/dev/null)
    echo "$CHDRV" | python3 -c "
import sys,json
d=json.load(sys.stdin)
if 'error' in d:
    print(f'  ✗ 不可用: {d[\"error\"]}')
else:
    members=d.get('Members',[])
    print(f'  Members@odata.count: {d.get(\"Members@odata.count\",len(members))}')
    print('  ⚠ 此路径返回的 Drive 所有字段为 null → 显示为 \"— / 0 GB\"')
" 2>/dev/null
else
    echo "  跳过（Chassis 路径未知）"
fi

# ═════════════════════════════════════════════════════════════════════════
# 总结
# ═════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}========================================================================${NC}"
echo -e "${CYAN}  诊断结论${NC}"
echo -e "${CYAN}========================================================================${NC}"
echo ""
echo "  各步全部 200 + 数据完整 → 代码逻辑本身无问题"
echo "  某步返回 401/403/非200 → 该步是根因"
echo "  Step 3c 正常但前端不显示 → 检查 server.disk_count 是否为 0"
