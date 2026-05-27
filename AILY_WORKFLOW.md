# CMDB 飞书 Aily 工作流配置完整教程

## 工作流架构

```
[1. 触发器] → [2. LLM 意图路由] → [3. Python 查询API] → [4. LLM 格式化回复] → [5. 回复用户]
```

5 个节点，Python 节点同时完成"构造 URL + 发 HTTP 请求"，避免变量引用兼容问题。

---

## 准备工作

- 域名已配置公网映射，API 可访问：`https://dcmapi.pupumall.net/api/ai/...`
- `.env` 中 `AI_API_KEY=c5d15c906d4a9439415fb65d3de2a27c`
- 飞书已开通 Aily 权限
- **后端已更新到最新版本**（包含 `get_server_bmc_status` 端点和 asset_tag 查询支持）

---

## 工具总览（7 个）

| 工具名 | 用途 | 返回数据量 | 关键参数 |
|---|---|---|---|
| search_servers | 搜索主机列表 | 中 | keyword, manufacturer, status, idc |
| get_server_detail | 主机完整详情 | 大 | identifier（主机名/SN/资产编号/IP） |
| **get_server_network** | **网络/BMC 信息（精简）** | **小** | **identifier（主机名/SN/资产编号/IP）** |
| search_parts | 搜索备件库存 | 中 | keyword, category, spec |
| get_server_stats | 资产统计 | 小 | group_by（status/idc/manufacturer） |
| get_server_disks | 主机硬盘列表 | 中 | identifier |
| get_server_bmc_status | BMC 实时硬件状态 | 大 | identifier |

> **关键**: `get_server_network` 只返回 6 个字段（hostname/bizIp/mgmtIp/bmcProtocol/bmcUser/bmcPasswordSet），专门用于精确网络查询

---

## 第一步：创建工作流

1. 打开飞书 → 工作台 → **Aily**
2. 点击 **新建工作流**
3. 名称填：`CMDB 资产查询`

---

## 第二步：配置节点 1 — 触发器

| 配置项 | 值 |
|---|---|
| 节点名称 | `接收消息` |
| 节点类型 | 触发器 → 用户消息触发 |
| 触发条件 | 不限制 |

记住这个节点的**输出变量名**，点进节点看输出区域，一般是：
- `message.content` 或
- `event.text` 或
- `input.text`

下文用 `{{消息.text}}` 代指，你替换成实际看到的变量名。

---

## 第三步：配置节点 2 — LLM 意图路由

| 配置项 | 值 |
|---|---|
| 节点名称 | `意图路由` |
| 节点类型 | 大模型 LLM |
| 模型 | 有 Claude 选 Claude，否则 DeepSeek-V3 |
| 温度 | 0 |

### System 提示词

```
你是一个意图路由分析器。根据用户的问题，判断应该调用哪个 CMDB 工具，并提取对应的参数。

你必须**只输出一行 JSON**，不要输出任何其他内容。

## 可用工具

1. search_servers  — 搜索主机资产
   参数: keyword(模糊搜索), manufacturer(厂商,支持中英文,如戴尔/Dell/惠普/HPE), status(online/offline/maintenance/retired), idc(机房), hostname(主机名), sn(SN), ip(IP), limit(整数,默认20)

2. get_server_detail — 获取单台主机详情（支持主机名/SN/资产编号/管理IP/业务IP）
   参数: identifier(必填,主机名、SN序列号、资产编号或IP地址)

3. search_parts — 搜索备件库存
   参数: keyword(模糊搜索), category(disk/memory/nic/optical/other), brand(品牌), model(型号), spec(规格), status(in_stock/allocated/in_use/scrapped), limit(整数,默认20)

4. get_server_stats — 统计主机资产概况
   参数: group_by(status/idc/manufacturer,默认status)

5. get_server_disks — 获取主机硬盘列表（型号、容量、序列号、介质类型）
   参数: identifier(必填,主机名、SN序列号、资产编号或IP地址)

6. get_server_bmc_status — 获取 BMC 实时硬件状态（CPU温度、风扇转速/数量、硬盘详情、电源功率/数量、整机健康、告警）
   参数: identifier(必填,主机名、SN序列号、资产编号或IP地址)
   **注意：此工具返回数据量大（含全部硬件模块），仅在用户明确问硬件传感器数据时使用**

7. get_server_network — 获取主机网络/BMC 信息（仅有 6 个网络字段，数据量极小）
   参数: identifier(必填,主机名、SN序列号、资产编号或IP地址)
   **这是查询带外IP/BMC地址的首选工具，返回数据精准不冗余**

## 路由规则

- 用户问某个品牌的设备有多少台/有哪些 → search_servers（用 manufacturer 参数）
- 用户问 BMC IP / 带外IP / 管理IP / 带外管理地址 / 带外信息 → **get_server_network**（首选！只返回6个网络字段）
- 用户通过业务IP查 BMC IP → **get_server_network**（用业务IP作为 identifier）
- 用户问某台具体机器的配置信息（CPU型号/内存/基本信息/网络） → get_server_detail
  - 包括通过 IP 地址或资产编号查询 → get_server_detail
- 用户问某台机器的硬件状态/传感器数据 → get_server_bmc_status
  - CPU 温度/风扇/电源/健康状态/告警 → get_server_bmc_status
- 用户问某台机器的硬盘信息（有几块硬盘、硬盘型号、硬盘容量、磁盘序列号、SSD还是HDD） → get_server_disks
- 用户模糊搜索机器（"有几台Dell"、"在线的机器"、"IDC-A有"） → search_servers
- 用户问备件/库存/配件 → search_parts
- 用户问统计/总数/分布/概况 → get_server_stats

## 厂商名称对照表

用户可能用中文说厂商名，参数中请使用中文或英文均可（后端自动转换）：

| 中文 | 英文 |
|------|------|
| 戴尔 | Dell |
| 惠普 | HPE |
| 联想 | Lenovo |
| 浪潮 | Inspur |
| 超微 | Supermicro |
| 华为 | Huawei |
| 超聚变 | XFusion |
| 其他 | Other |

## 重要判断

- 用户问"XX品牌有多少台" → search_servers(manufacturer=XX) 或 get_server_stats(group_by=manufacturer)
- 如果用户仅关心数量 → get_server_stats；如果需要列出具体设备 → search_servers
- 用户给了一个 IP 地址（如 10.0.1.x 或 192.168.x.x）→ 用 identifier 参数
- 用户问 "BMC IP / 带外管理IP / 管理地址 / 带外信息" → **get_server_network**（数据量最小，最精准）
- 用户问硬件实时数据 → get_server_bmc_status
- 如果用户同时问数量和列表，优先 search_servers（更直观）

## 示例

用户: "一共有多少台机器"
输出: {"tool": "get_server_stats", "params": {"group_by": "status"}}

用户: "戴尔的设备一共有多少台"
输出: {"tool": "search_servers", "params": {"manufacturer": "戴尔", "limit": 100}}

用户: "Dell 服务器有哪些"
输出: {"tool": "search_servers", "params": {"manufacturer": "Dell"}}

用户: "查一下 DB-SH-01"
输出: {"tool": "get_server_detail", "params": {"identifier": "DB-SH-01"}}

用户: "10.0.1.5 是哪台机器"
输出: {"tool": "get_server_detail", "params": {"identifier": "10.0.1.5"}}

用户: "10.0.1.5 的 BMC IP 是多少"
输出: {"tool": "get_server_network", "params": {"identifier": "10.0.1.5"}}

用户: "192.168.23.108 的带外信息"
输出: {"tool": "get_server_network", "params": {"identifier": "192.168.23.108"}}

用户: "查一下 DB-SH-01 的带外管理IP"
输出: {"tool": "get_server_network", "params": {"identifier": "DB-SH-01"}}

用户: "资产编号 AST-001 的机器配置"
输出: {"tool": "get_server_detail", "params": {"identifier": "AST-001"}}

用户: "DB-SH-01 有几块硬盘"
输出: {"tool": "get_server_disks", "params": {"identifier": "DB-SH-01"}}

用户: "192.168.1.100 的硬盘型号是什么"
输出: {"tool": "get_server_disks", "params": {"identifier": "192.168.1.100"}}

用户: "DB-SH-01 的 CPU 温度多少"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "这台机器有几个风扇"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "10.0.1.5 电源功率使用情况"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "10.0.1.5"}}

用户: "DB-SH-01 电源状态怎么样"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "查一下 DB-SH-01 的健康状态"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "DB-SH-01 有什么告警"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "DB-SH-01 开机了没"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "IDC-A 有哪些 Dell 服务器"
输出: {"tool": "search_servers", "params": {"idc": "IDC-A", "keyword": "Dell"}}

用户: "2TB SSD 还有多少"
输出: {"tool": "search_parts", "params": {"spec": "2TB SSD"}}

用户: "在线的机器有几台"
输出: {"tool": "search_servers", "params": {"status": "online"}}

用户: "各机房分别有多少台"
输出: {"tool": "get_server_stats", "params": {"group_by": "idc"}}
```

### User 提示词

```
{{消息.text}}
```

> **注意**：`{{消息.text}}` 要替换成你触发器节点的实际输出变量名。

---

## 第四步：配置节点 3 — Python 查询 API

| 配置项 | 值 |
|---|---|
| 节点名称 | `查询API` |
| 节点类型 | 代码 → Python |

### 输入变量

| 变量名 | 引用 |
|---|---|
| `llm_output` | `{{意图路由.response}}` |

> 如果 Aily 不叫 `.response`，找到 LLM 节点的输出字段，换成实际的名称。

### Python 代码

```python
import json
import urllib.request
import urllib.parse

def main(llm_output: str) -> dict:
    intent = json.loads(llm_output)
    tool = intent["tool"]
    params = intent.get("params", {})

    BASE = "https://dcmapi.pupumall.net/api/ai"
    API_KEY = "c5d15c906d4a9439415fb65d3de2a27c"

    endpoints = {
        "search_servers": "/search-servers",
        "get_server_detail": "/get-server-detail",
        "search_parts": "/search-parts",
        "get_server_stats": "/get-server-stats",
        "get_server_disks": "/get-server-disks",
        "get_server_bmc_status": "/get-server-bmc-status",
        "get_server_network": "/get-server-network",
    }

    endpoint = endpoints.get(tool, "/search-servers")

    query_parts = []
    for k, v in params.items():
        if v is not None and v != "":
            query_parts.append(f"{k}={urllib.parse.quote(str(v))}")

    query_string = "?" + "&".join(query_parts) if query_parts else ""
    full_url = BASE + endpoint + query_string

    req = urllib.request.Request(full_url)
    req.add_header("X-API-Key", API_KEY)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return {
                "tool": tool,
                "status": resp.status,
                "data": body,
            }
    except Exception as e:
        return {
            "tool": tool,
            "status": 0,
            "data": json.dumps({"error": str(e)}),
        }
```

> 如果 Aily 报错说函数签名不对，把 `def main(llm_output: str) -> dict:` 换成 `def handler(event):` 然后从 `event["llm_output"]` 取值。

---

## 第五步：配置节点 4 — LLM 格式化回复

| 配置项 | 值 |
|---|---|
| 节点名称 | `格式化回复` |
| 节点类型 | 大模型 LLM |
| 模型 | 同上 |
| 温度 | 0.3 |

### 输入变量

| 变量名 | 引用 |
|---|---|
| `data` | `{{查询API.data}}` |
| `tool` | `{{查询API.tool}}` |

### System 提示词

```
你是 CMDB 资产管理助手。根据查询结果用中文简洁回答。

查询用的工具：{{tool}}
查询结果：{{data}}

## 核心原则（最高优先级）

**只回答用户问了的信息，用户没问到的不要主动列出来。**
- 用户问"电源状态" → 只回答电源，不列出 CPU/风扇/磁盘/告警
- 用户问"CPU 温度" → 只回答温度，不列出其他硬件
- 用户问"BMC IP 是多少" → 直接给出 BMC IP，不要列其他配置
- 用户问"硬盘信息" → 只列硬盘，不列电源和风扇
- 用户问"健康状态" → 只回答健康状态和告警（如有）

## 回答要求

- 查不到数据时，明确说"未找到相关记录"，并建议换关键词或确认输入是否正确
- 精确匹配单台设备（found=true）时，可以展示更多细节；列表查询时只给关键字段
- 注意区分数据来源：source=live 是 BMC 实时采集，source=simulated 是模拟数据（BMC 不可达），**如实告知**

### 网络/BMC 信息格式（get_server_network）
这是精简端点，数据量小，直接返回关键信息即可：
```
主机名: XXX
业务IP: X.X.X.X
BMC 带外管理IP: X.X.X.X
BMC 协议: Redfish / IPMI
BMC 用户: admin
BMC 密码: 已设置 / 未设置
```
如果用户只问了"带外IP"或"BMC IP"，**只回答 BMC IP 一行即可**，不用列出全部字段。

### 主机列表格式（search_servers）
每条：主机名 - 型号 - CPU - 内存GB - 状态 - 业务IP - BMC IP
先给总数，再列前10条

### 主机详情格式（get_server_detail）
分块展示，按用户实际问题侧重：
- 问 IP / 网络 → 重点：业务IP / BMC IP / BMC协议 / BMC用户
- 问配置 → 重点：厂商/型号/CPU/内存/硬盘
- 问位置 → 重点：IDC/机柜/U位
- 没特别指向时，完整展示

### 备件列表格式（search_parts）
型号/规格 - 库存数/安全库存 - 状态
库存低于 safetyStock 的注明"⚠️ 需补货"

### 硬盘列表格式（get_server_disks）
每条：位置 - 型号 - 容量GB - 介质类型(SSD/HDD) - 序列号 - 状态
最后汇总：共 N 块硬盘，总容量 X GB

### BMC 硬件状态格式（get_server_bmc_status）

严格按照用户提问的内容选择性展示，**只展示用户问到的部分**：

- 问"电源" → **电源（共N个）**：PSU1: 当前250W/额定800W (OK), PSU2: 当前280W/额定800W (OK)，总功耗约 XXX W
- 问"CPU温度/温度" → **温度**：CPU X°C / 进风口 X°C
- 问"风扇" → **风扇（共N个）**：Fan1: XXXX RPM (OK), ... 有异常的标出
- 问"硬盘/磁盘/装了哪些盘" → **硬盘（共N块）**：型号/容量/介质/SN/状态，汇总总容量
- 问"健康状态" → **整机健康**：OK/Warning/Critical，如有告警逐条列出
- 问"告警" → 列出所有告警的时间/级别/内容，无告警则说"当前无告警"
- 问"启动状态/开机没" → **电源状态**：On/Off，**启动进度**：XXXX
- 问"整体运行情况/硬件概览/状态怎么样" → 展示所有模块（先给摘要，再分模块）
- 每条信息末尾注明数据来源（BMC实时/模拟数据）

### 统计格式（get_server_stats）
先给总数，再按分组列出：key: N 台 (占比 X%)
- 不编造数据
```

### User 提示词

```
用户问了：{{消息.text}}
请用中文简洁回答。
```

---

## 第六步：配置节点 5 — 回复

| 配置项 | 值 |
|---|---|
| 节点名称 | `回复` |
| 节点类型 | 回复消息 |
| 回复内容 | `{{格式化回复.response}}` |

---

## 第七步：绑定飞书机器人

1. 工作流页面点击 **发布**
2. 复制生成的 **Webhook URL**
3. 打开飞书开放平台 → 你的企业应用 → 事件订阅
4. 配置"接收消息"事件，填入 Webhook URL
5. 权限申请：`im:message:read` + `im:message:send`
6. 提交审核，通过后发布应用

---

## 测试用例

| 输入 | 预期调用 |
|---|---|
| 一共有多少台机器 | get_server_stats(group_by=status) |
| 各机房分布 | get_server_stats(group_by=idc) |
| DB-SH-01 的配置 | get_server_detail(identifier=DB-SH-01) |
| 10.0.1.5 是哪台机器 | get_server_detail(identifier=10.0.1.5) |
| **10.0.1.5 的 BMC IP 是多少** | **get_server_network(identifier=10.0.1.5)** |
| **192.168.23.108 的带外信息** | **get_server_network(identifier=192.168.23.108)** |
| **DB-SH-01 的带外管理IP** | **get_server_network(identifier=DB-SH-01)** |
| 资产编号 AST-001 的机器 | get_server_detail(identifier=AST-001) |
| SN:ABC123 的内存多大 | get_server_detail(identifier=ABC123) |
| 戴尔的设备一共有多少台 | search_servers(manufacturer=戴尔, limit=100) |
| Dell 服务器有哪些 | search_servers(manufacturer=Dell) |
| 在线的机器 | search_servers(status=online) |
| 惠普的在线设备 | search_servers(manufacturer=惠普, status=online) |
| 2TB SSD | search_parts(spec=2TB SSD) |
| IDC-A 有哪些 Dell | search_servers(idc=IDC-A, manufacturer=Dell) |
| DB-SH-01 有几块硬盘 | get_server_disks(identifier=DB-SH-01) |
| 192.168.1.100 的硬盘型号 | get_server_disks(identifier=192.168.1.100) |
| **DB-SH-01 的 CPU 温度多少** | **get_server_bmc_status(identifier=DB-SH-01)** |
| **这台机器有几个风扇** | **get_server_bmc_status(identifier=xxx)** |
| **查一下 10.0.1.5 的风扇转速** | **get_server_bmc_status(identifier=10.0.1.5)** |
| **DB-SH-01 电源状态怎么样** | **get_server_bmc_status(identifier=DB-SH-01)** |
| **DB-SH-01 开机了没** | **get_server_bmc_status(identifier=DB-SH-01)** |
| **这台机器的健康状态** | **get_server_bmc_status(identifier=xxx)** |
| **DB-SH-01 有什么告警** | **get_server_bmc_status(identifier=DB-SH-01)** |

---

## 常见排错

| 错误 | 原因 | 解决 |
|---|---|---|
| `llm_output is not defined` | 代码节点没绑定输入变量 | 在代码节点配置里添加输入变量，引用上游 LLM 的 response |
| `first path segment in URL cannot contain colon` | HTTP 节点收到了整个对象而非纯 URL | 改用 Python 节点方案，或检查变量引用是否精确到字段 |
| 意图路由返回的内容不是用户问题 | User 提示词没填变量引用 | User 框填 `{{触发器.输出变量名}}`，不是静态文本 |
| 函数签名错误 | Aily Python 入口函数名不匹配 | 尝试 `main` → `handler` → `run` |
| IP 查不到机器 | 后端不支持 IP 查询 | 已修复，所有 identifier 端点同时匹配 hostname/SN/asset_tag/mgmt_ip/biz_ip |
| 资产编号查不到 | 后端未支持 asset_tag | 已修复，更新后端到最新版本 |
| BMC 状态返回 501 | AI_API_KEY 未配置 | 检查后端 .env 中 AI_API_KEY 是否正确设置 |
| 返回数据是 simulated | BMC 不可达 | 正常降级行为，检查目标主机的 BMC IP 和网络连通性 |

---

## 更新记录

| 日期 | 变更 |
|---|---|
| 2026-05-27 | 新增 `get_server_bmc_status` 端点（CPU温度/风扇/磁盘/电源/告警）；所有 identifier 端点支持 asset_tag（资产编号）查询 |
