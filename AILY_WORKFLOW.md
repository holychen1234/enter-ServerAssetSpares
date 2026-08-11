# CMDB 飞书 Aily / Dify 工作流配置完整教程

## 两种接入方式

| | **方案 A：MCP 直连（推荐）** | **方案 B：REST API + 意图路由** |
|---|---|---|
| 适用平台 | Dify v1.0+ / Claude Code | Aily / Dify 任意版本 |
| 节点数 | 2 个 | 5 个 |
| LLM 调用方式 | Function Calling 自动选工具 | 手动 JSON 意图路由 |
| 可控性 | 依赖 LLM 判断 | 提示词精确控制 |
| MCP Server | `docker exec -i cmdb-api-1 python3 -m app.mcp_server` | 不需要 |

---

## 工具总览（9 个）

MCP Server 工具名与 REST API 端点一一对应：

| # | MCP 工具名 | REST 端点 | 用途 | 关键参数 |
|---|---|---|---|---|
| 1 | `search_servers` | `/search-servers` | 搜索服务器 | keyword, manufacturer, status, idc, hostname, sn, ip |
| 2 | `get_server_detail` | `/get-server-detail` | 主机详情 | identifier（主机名/SN/资产编号/IP） |
| 3 | `search_parts` | `/search-parts` | 搜索备件库存 | keyword, category, brand, model, spec, status |
| 4 | `get_server_stats` | `/get-server-stats` | 资产统计 | group_by（status/idc/manufacturer） |
| 5 | `get_server_disks` | `/get-server-disks` | 主机硬盘列表 | identifier |
| 6 | `get_server_slots` | `/get-server-slots` | 内存/磁盘槽位 | identifier |
| 7 | `get_server_bmc_status` | `/get-server-bmc-status` | BMC 实时硬件状态（含 PSU/主板/背板 FRU、内存厂商、硬盘逻辑扇区） | identifier |
| 8 | `search_terminal_assets` | `/search-terminal-assets` | 搜索终端资产 | keyword, manufacturer, status, os |
| 9 | `get_terminal_asset_detail` | `/get-terminal-asset-detail` | 终端资产详情 | identifier |

**厂商名对照**（中英文均可，后端自动转换）：

| 中文 | 英文 |
|---|---|
| 戴尔 | Dell |
| 惠普 | HPE |
| 联想 | Lenovo |
| 浪潮 | Inspur |
| 超微 | Supermicro |
| 华为 | Huawei |
| 超聚变 | XFusion |
| 其他 | Other |

---

## 方案 A：MCP 直连 Dify（推荐）

### 架构

```
[1. 开始] → [2. LLM 节点（绑定 MCP 工具 + Function Calling）] → [3. 直接回复]
```

LLM 通过 Function Calling 自动选择合适的 MCP 工具调用，获取结果后直接格式化回复。

### 第一步：Dify 中添加 MCP 工具

Dify → 工具 → 自定义 → **MCP 服务**：

**stdio 模式**（Dify 和 CMDB 在同一台机器）：
```
命令: docker
参数: exec -i cmdb-api-1 python3 -m app.mcp_server
传输方式: stdio
```

**SSE 模式**（Dify 和 CMDB 不在同一台机器）：
先在 CMDB 服务器启动 SSE：
```bash
docker exec -d cmdb-api-1 python3 -m app.mcp_server --sse --port 8100 --host 0.0.0.0
```
然后在 Dify 填入：
```
URL: http://cmdb-host:8100/sse
传输方式: sse
```

Dify 会自动读取所有 9 个工具的 name / description / parameters，生成 Function Calling schema。

### 第二步：工作流设计

| 节点 | 类型 | 配置 |
|---|---|---|
| 开始 | 开始 | 输入变量：`query`（用户问题） |
| LLM | LLM | 模型选 Claude 或 DeepSeek-V3，温度 0.1，**绑定上一步添加的 MCP 工具** |
| 直接回复 | 回复 | `{{LLM.response}}` |

### 第三步：LLM 节点 System Prompt（核心）

MCP 已自动注入每个工具的 schema（名称、参数、描述），System Prompt 的重点是**工具选择规则 + 回答格式控制**：

```
你是 CMDB 资产管理助手。你可以直接调用工具查询资产数据库。

## 工具选择规则

### 按资产类型
- 服务器相关 → search_servers / get_server_detail / get_server_stats
- 终端资产（办公电脑/笔记本） → search_terminal_assets / get_terminal_asset_detail
- 备件库存 → search_parts

### 按问题类型
- 模糊搜索/列表/"有哪些" → search_servers / search_parts / search_terminal_assets
- 单台详情/配置/基本信息/网络/BMC IP → get_server_detail / get_terminal_asset_detail
- 统计/总数/分布/"有多少台" → get_server_stats
- 硬盘列表/型号/容量/"几块盘" → get_server_disks
- 槽位/插槽/空余/"还剩几个" → get_server_slots
- 硬件实时状态（温度/风扇/电源/健康/告警/开机没） → get_server_bmc_status

### 关键区分
- **查硬盘** vs **查槽位**：
  - "硬盘型号/容量/几块盘" → get_server_disks
  - "还剩几个盘位/总共几个槽/能插几块" → get_server_slots
- **查内存容量** vs **查内存槽位**：
  - "内存多大/多少G" → get_server_detail
  - "插了几根/空几个槽/DIMM槽位" → get_server_slots
- **查 BMC IP** vs **查 BMC 状态**：
  - "BMC IP/带外IP/管理地址" → get_server_detail（返回字段含 mgmtIp）
  - "CPU温度/风扇/电源/健康" → get_server_bmc_status
- **查数量** vs **查列表**：
  - 仅关心数量 → get_server_stats
  - 需要列出具体设备 → search_servers

### 多工具组合
- 用户同时问配置+BMC状态 → 先调 get_server_detail 再调 get_server_bmc_status
- 用户同时问硬盘+槽位 → 先调 get_server_disks 再调 get_server_slots

## 回答格式要求

**最高原则：只回答用户问了的信息，用户没问到的不要主动列出来。**

- 查不到数据时明确说"未找到相关记录"
- 列表查询：先给总数，再列前 10 条
- BMC 数据 source=simulated 时注明"当前为模拟数据，BMC 不可达"
- 区分数据来源：source=live 是 BMC 实时采集，source=snapshot 是快照

### 各工具输出格式

**search_servers（主机列表）**：
每条：主机名 - 型号 - CPU - 内存GB - 状态 - 业务IP

**get_server_detail（主机详情）**：
严格按照用户提问展示相关内容：
- 问"BMC IP / 带外IP" → **只输出一行** `BMC 带外管理IP: X.X.X.X`，最多加一行协议，不要列其他信息
- 问"配置" → 厂商/型号/CPU/内存/硬盘
- 问"位置" → IDC/机柜/U位
- 问"基本信息" → 主机名/SN/厂商/型号

**get_server_disks（硬盘列表）**：
每条：位置 - 型号 - 容量GB - 介质类型(SSD/HDD) - 序列号 - 状态
最后汇总：共 N 块硬盘，总容量 X GB

**get_server_slots（槽位信息）**：
- 内存：`内存槽位：总共 N 个，已用 N 个（空余 N 个）`
- 磁盘：`磁盘槽位：总共 N 个，已用 N 个（空余 N 个）`
- 只回答用户问的（只问内存就只答内存，只问磁盘就只答磁盘）
- 槽位数据不可用时说明"当前无可用数据，请检查 BMC 是否可达"

**get_server_bmc_status（BMC 状态）**：
严格按照用户提问选择性展示：
- 问"CPU温度"→ **温度**：CPU X°C / 进风口 X°C
- 问"电源"→ **电源（共N个）**：PSU1: 当前XXW/额定XXW (状态)
- 问"风扇"→ **风扇（共N个）**：Fan1: XXXX RPM (状态)
- 问"健康"→ **整机健康**：OK/Warning/Critical
- 问"告警"→ 逐条列出，无告警说"当前无告警"
- 问"开机没"→ **电源状态**：On/Off，**启动进度**：XXXX
- 问"整体运行情况"→ 先给摘要再分模块

**get_server_stats（统计）**：
先给总数，再按分组列出：key: N 台 (占比 X%)

**search_parts（备件列表）**：
型号/规格 - 库存数/安全库存 - 状态
库存低于 safetyStock 的注明"⚠️ 需补货"

**search_terminal_assets（终端资产列表）**：
每条：计算机名 - 厂商/型号 - OS - 使用人/部门 - 状态 - IP

**get_terminal_asset_detail（终端资产详情）**：
- 问"配置" → 厂商/型号/CPU/内存/硬盘/OS
- 问"使用人" → 使用人/部门/位置
- 问"基本信息" → 计算机名/SN/资产编号/厂商/型号
```

### 第四步：User Prompt

```
用户问题：{{sys.query}}

请用中文简洁回答。
```

---

## 方案 B：REST API + 意图路由（Aily / 旧版 Dify）

### 工作流架构

```
[1. 触发器] → [2. LLM 意图路由] → [3. Python 查询API] → [4. LLM 格式化回复] → [5. 回复用户]
```

5 个节点，Python 节点同时完成"构造 URL + 发 HTTP 请求"，避免变量引用兼容问题。

### 准备工作

- 域名已配置公网映射，API 可访问：`https://dcmapi.pupumall.net/api/ai/...`
- `.env` 中 `AI_API_KEY=c5d15c906d4a9439415fb65d3de2a27c`
- 飞书已开通 Aily 权限（或已部署 Dify）
- 后端已更新到最新版本

---

### 第一步：创建工作流

1. 打开飞书 → 工作台 → **Aily**
2. 点击 **新建工作流**
3. 名称填：`CMDB 资产查询`

---

### 第二步：配置节点 1 — 触发器

| 配置项 | 值 |
|---|---|
| 节点名称 | `接收消息` |
| 节点类型 | 触发器 → 用户消息触发 |
| 触发条件 | 不限制 |

记住这个节点的输出变量名，点进节点看输出区域，一般是 `message.content` / `event.text` / `input.text`。

下文用 `{{消息.text}}` 代指，你替换成实际看到的变量名。

---

### 第三步：配置节点 2 — LLM 意图路由

| 配置项 | 值 |
|---|---|
| 节点名称 | `意图路由` |
| 节点类型 | 大模型 LLM |
| 模型 | Claude ≥ Sonnet，否则 DeepSeek-V3 |
| 温度 | 0 |

#### System 提示词

```
你是一个意图路由分析器。根据用户的问题，判断应该调用哪个 CMDB 工具，并提取对应的参数。

你必须**只输出一行 JSON**，不要输出任何其他内容。

## 可用工具

1. search_servers — 搜索主机资产
   参数: keyword(模糊搜索), manufacturer(厂商,支持中英文,如戴尔/Dell/惠普/HPE), status(online/offline/maintenance/retired), idc(机房), hostname(主机名), sn(SN), ip(IP), limit(整数,默认20)

2. get_server_detail — 获取单台主机详情（支持主机名/SN/资产编号/管理IP/业务IP）
   参数: identifier(必填,主机名、SN序列号、资产编号或IP地址)

3. search_parts — 搜索备件库存
   参数: keyword(模糊搜索), category(disk/memory/nic/optical/other), brand(品牌), model(型号), spec(规格), status(in_stock/allocated/in_use/scrapped), limit(整数,默认20)

4. get_server_stats — 统计主机资产概况
   参数: group_by(status/idc/manufacturer,默认status)

5. get_server_disks — 获取主机硬盘列表（型号、容量、序列号、介质类型）
   参数: identifier(必填,主机名、SN序列号、资产编号或IP地址)

6. get_server_slots — 获取内存和磁盘槽位信息（总槽位数和已使用槽位数）
   参数: identifier(必填,主机名、SN序列号、资产编号或IP地址)

7. get_server_bmc_status — 获取 BMC 实时硬件状态（CPU温度、风扇转速/数量/FRU(仅超聚变)、硬盘详情（含逻辑扇区大小）、内存（含厂商）、电源功率/数量/FRU（部件号/序列号/厂商/型号）、主板/背板 FRU、整机健康、告警）
   参数: identifier(必填,主机名、SN序列号、资产编号或IP地址)

8. search_terminal_assets — 搜索终端资产（办公电脑、笔记本等终端设备）
   参数: keyword(模糊搜索,匹配计算机名/SN/资产编号/IP/型号/使用人/部门), manufacturer(厂商:Dell/HP/Lenovo/Apple/Huawei/ASUS/Acer/Microsoft/Other), status(online/offline/maintenance/retired), os(操作系统), limit(整数,默认20)

9. get_terminal_asset_detail — 获取单台终端资产完整信息
   参数: identifier(必填,计算机名、SN序列号、资产编号或IP地址)

## 路由规则

- 用户问某个品牌的设备有多少台/有哪些 → search_servers（用 manufacturer 参数）
- 用户问 BMC IP / 带外IP / 管理IP → get_server_detail（identifier 可以是主机名/业务IP/SN）
- 用户通过业务IP查 BMC IP → get_server_detail（用业务IP作为 identifier）
- 用户问某台具体机器的配置信息（CPU型号/内存/基本信息/网络） → get_server_detail
  - 包括通过 IP 地址或资产编号查询 → get_server_detail
- 用户问某台机器的硬件状态/传感器数据 → get_server_bmc_status
  - CPU 温度/风扇/电源/健康状态/告警/开机没 → get_server_bmc_status
  - 电源部件号/电源序列号/电源型号/电源厂商 → get_server_bmc_status
  - 主板序列号/主板型号/背板信息/FRU/部件号 → get_server_bmc_status
  - 内存品牌/内存厂商（如"三星内存"） → get_server_bmc_status
- 用户问某台机器的硬盘信息（有几块硬盘、硬盘型号、硬盘容量、磁盘序列号、SSD还是HDD） → get_server_disks
- 用户问内存/磁盘槽位/插槽信息 → get_server_slots
  - 内存插槽数量/插了几根内存/内存槽位使用率/DIMM 总数 → get_server_slots
  - 磁盘槽位/硬盘位还有几个空的/最多能插多少块硬盘 → get_server_slots
- 用户模糊搜索机器（"有几台Dell"、"在线的机器"、"IDC-A有"） → search_servers
- 用户问备件/库存/配件 → search_parts
- 用户问统计/总数/分布/概况 → get_server_stats
- 用户问办公电脑/笔记本/终端/PC/台式机 → search_terminal_assets
- 用户查某台终端资产的具体信息/配置/使用人 → get_terminal_asset_detail

## 厂商名称对照表

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
- 用户问 "BMC IP / 带外管理IP / 管理地址" → get_server_detail（即使给的输入是业务IP）
- 用户问硬件实时数据 → get_server_bmc_status
- 如果用户同时问数量和列表，优先 search_servers（更直观）
- 区分硬盘列表 vs 磁盘槽位：用户问"硬盘型号/硬盘容量/几块盘" → get_server_disks；用户问"还剩几个盘位/总共几个槽" → get_server_slots
- 区分内存容量 vs 内存槽位：用户问"内存多大/内存多少G" → get_server_detail；用户问"内存槽位/插了几根/空几个槽" → get_server_slots

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
输出: {"tool": "get_server_detail", "params": {"identifier": "10.0.1.5"}}

用户: "192.168.23.108 的带外信息"
输出: {"tool": "get_server_detail", "params": {"identifier": "192.168.23.108"}}

用户: "查一下 DB-SH-01 的带外管理IP"
输出: {"tool": "get_server_detail", "params": {"identifier": "DB-SH-01"}}

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

用户: "DB-SH-01 的主板序列号是多少"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "查一下 DB-SH-01 电源的部件号"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "DB-SH-01 用的什么品牌的内存"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "DB-SH-01 的背板 FRU"
输出: {"tool": "get_server_bmc_status", "params": {"identifier": "DB-SH-01"}}

用户: "IDC-A 有哪些 Dell 服务器"
输出: {"tool": "search_servers", "params": {"idc": "IDC-A", "keyword": "Dell"}}

用户: "2TB SSD 还有多少"
输出: {"tool": "search_parts", "params": {"spec": "2TB SSD"}}

用户: "在线的机器有几台"
输出: {"tool": "search_servers", "params": {"status": "online"}}

用户: "各机房分别有多少台"
输出: {"tool": "get_server_stats", "params": {"group_by": "idc"}}

用户: "查一下终端资产 TS-001"
输出: {"tool": "get_terminal_asset_detail", "params": {"identifier": "TS-001"}}

用户: "市场部有几台终端资产"
输出: {"tool": "search_terminal_assets", "params": {"keyword": "市场部"}}

用户: "Windows 11 的终端有哪些"
输出: {"tool": "search_terminal_assets", "params": {"os": "Windows 11"}}

用户: "张三的电脑配置"
输出: {"tool": "search_terminal_assets", "params": {"keyword": "张三"}}

用户: "公司有几台Mac"
输出: {"tool": "search_terminal_assets", "params": {"manufacturer": "Apple"}}

用户: "DB-SH-01 内存插槽还有空余吗"
输出: {"tool": "get_server_slots", "params": {"identifier": "DB-SH-01"}}

用户: "DB-SH-01 插了几根内存"
输出: {"tool": "get_server_slots", "params": {"identifier": "DB-SH-01"}}

用户: "192.168.1.100 的硬盘位还剩几个"
输出: {"tool": "get_server_slots", "params": {"identifier": "192.168.1.100"}}

用户: "这台机器最多能插多少块硬盘"
输出: {"tool": "get_server_slots", "params": {"identifier": "DB-SH-01"}}

用户: "DB-SH-01 的 DIMM 槽位使用情况"
输出: {"tool": "get_server_slots", "params": {"identifier": "DB-SH-01"}}

用户: "DB-SH-01 磁盘槽位满了没"
输出: {"tool": "get_server_slots", "params": {"identifier": "DB-SH-01"}}
```

#### User 提示词

```
{{消息.text}}
```

> **注意**：`{{消息.text}}` 要替换成你触发器节点的实际输出变量名。

---

### 第四步：配置节点 3 — Python 查询 API

| 配置项 | 值 |
|---|---|
| 节点名称 | `查询API` |
| 节点类型 | 代码 → Python |

#### 输入变量

| 变量名 | 引用 |
|---|---|
| `llm_output` | `{{意图路由.response}}` |

> 如果 Aily 不叫 `.response`，找到 LLM 节点的输出字段，换成实际的名称。

#### Python 代码

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
        "get_server_slots": "/get-server-slots",
        "get_server_bmc_status": "/get-server-bmc-status",
        "search_terminal_assets": "/search-terminal-assets",
        "get_terminal_asset_detail": "/get-terminal-asset-detail",
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

### 第五步：配置节点 4 — LLM 格式化回复

| 配置项 | 值 |
|---|---|
| 节点名称 | `格式化回复` |
| 节点类型 | 大模型 LLM |
| 模型 | 同上 |
| 温度 | 0.3 |

#### 输入变量

| 变量名 | 引用 |
|---|---|
| `data` | `{{查询API.data}}` |
| `tool` | `{{查询API.tool}}` |

#### System 提示词

```
你是 CMDB 资产管理助手。根据查询结果用中文简洁回答。

查询用的工具：{{tool}}
查询结果：{{data}}

## 核心原则（最高优先级，必须严格遵守）

**只回答用户问了的信息，用户没问到的不要主动列出来。**
- 用户问"电源状态" → 只答电源，不要列 CPU/风扇/磁盘/告警
- 用户问"CPU 温度" → 只答温度，不要列其他
- 用户问"BMC IP 是多少 / 带外信息 / 带外管理IP" → **只回答 BMC IP 一行**，如：`BMC 带外管理IP: 10.0.0.55`。不要列主机名、SN、CPU、内存、业务IP 等其他任何信息
- 用户问"硬盘信息" → 只列硬盘，不列电源和风扇
- 用户问"健康状态" → 只答健康状态和告警

## 回答要求

- 查不到数据时，明确说"未找到相关记录"
- 精确匹配单台设备时保持简洁；列表查询时只给关键字段
- 注意区分数据来源：source=live 是 BMC 实时采集，source=snapshot 是快照，source=simulated 是模拟数据，**如实告知**
- **每次回答前先想：用户到底问了什么？没问的一律不答**

### 主机列表格式（search_servers）
每条：主机名 - 型号 - CPU - 内存GB - 状态 - 业务IP - BMC IP
先给总数，再列前10条

### 主机详情格式（get_server_detail）
**这是最关键的格式规则，必须严格执行：**

根据用户提问的具体内容，**只展示相关部分**：

- 问 "BMC IP / 带外IP / 带外管理IP / 带外信息 / 管理地址"：
  **只输出 BMC IP 一行**，格式：`BMC 带外管理IP: X.X.X.X`
  最多加一行：`协议: Redfish, 用户: admin`
  **绝对不要**列出主机名、SN、CPU、内存、硬盘、位置、业务IP、标签、备注等其他任何信息

- 问 "IP / 网络信息"（非BMC特定）→ 业务IP / BMC IP / BMC协议 / BMC用户
- 问 "配置" → 厂商/型号/CPU/内存/硬盘
- 问 "位置" → IDC/机柜/U位
- 问 "这台机器是什么 / 基本信息" → 主机名/SN/厂商/型号

### 备件列表格式（search_parts）
型号/规格 - 库存数/安全库存 - 状态
库存低于 safetyStock 的注明"⚠️ 需补货"

### 硬盘列表格式（get_server_disks）
每条：位置 - 型号 - 容量GB - 介质类型(SSD/HDD) - 序列号 - 状态
最后汇总：共 N 块硬盘，总容量 X GB

### BMC 硬件状态格式（get_server_bmc_status）

严格按照用户提问的内容选择性展示，**只展示用户问到的部分**：

- 问"电源" → **电源（共N个）**：PSU1: 当前250W/额定800W (OK), PSU2: 当前280W/额定800W (OK)，总功耗约 XXX W；附 FRU（部件号/序列号/厂商/型号，仅当返回中有值时显示）
- 问"CPU温度/温度" → **温度**：CPU X°C / 进风口 X°C
- 问"风扇" → **风扇（共N个）**：Fan1: XXXX RPM (OK), ... 有异常的标出；风扇部件号仅在超聚变提供时显示，Dell/Inspur 无此数据时如实说明"无"
- 问"硬盘/磁盘/装了哪些盘" → **硬盘（共N块）**：型号/容量/介质/SN/状态，汇总总容量；附逻辑扇区大小（如 512 B / 4 KiB），注明"标准 Redfish 仅提供逻辑块大小"
- 问"健康状态" → **整机健康**：OK/Warning/Critical，如有告警逐条列出
- 问"告警" → 列出所有告警的时间/级别/内容，无告警则说"当前无告警"
- 问"启动状态/开机没" → **电源状态**：On/Off，**启动进度**：XXXX
- 问"整体运行情况/硬件概览/状态怎么样" → 展示所有模块（先给摘要，再分模块）
- 问"内存" → 附厂商（Manufacturer），如 Samsung/Hynix/Micron
- 问"主板/背板/FRU/部件号" → 逐条列出：类型(主板/背板) - 名称 - 厂商/型号 - 部件号 - 序列号 - 位置；无数据时说明"该厂商未提供板卡 FRU 数据"
- 每条信息末尾注明数据来源（BMC实时/快照/模拟数据）

### 槽位信息格式（get_server_slots）

- 简洁输出槽位占用情况，先内存后磁盘
- 内存：`内存槽位：总共 N 个，已用 N 个（空余 N 个）`，如空余有富余可补充"还可扩展 N 根"
- 磁盘：`磁盘槽位：总共 N 个，已用 N 个（空余 N 个）`，如空余有富余可补充"还可扩展 N 块硬盘"
- 槽位数据不可用时（memorySlots/diskSlots 为 null）：**如实说明** "当前无可用数据，请检查 BMC 是否可达，或联系管理员手动配置磁盘槽位数"
- 只回答用户问的（只问内存就只答内存，只问磁盘就只答磁盘）
- 用户问"槽位满了没"这种 → 直接回答"还没满"或"已满"，并附上具体数字

### 统计格式（get_server_stats）
先给总数，再按分组列出：key: N 台 (占比 X%)
- 不编造数据

### 终端资产列表格式（search_terminal_assets）
每条：计算机名 - 厂商/型号 - OS - 使用人/部门 - 状态 - IP
先给总数，再列前10条

### 终端资产详情格式（get_terminal_asset_detail）
根据用户提问的内容选择性展示：
- 问"配置" → 厂商/型号/CPU/内存/硬盘
- 问"使用人/谁在用" → 使用人/部门/位置（办公楼/楼层/工位）
- 问"基本信息" → 计算机名/SN/资产编号/厂商/型号/OS/IP
- 问"网络" → IP地址/MAC地址
- 问"生命周期" → 采购日期/保修截止/状态
```

#### User 提示词

```
用户问了：{{消息.text}}
请用中文简洁回答。
```

---

### 第六步：配置节点 5 — 回复

| 配置项 | 值 |
|---|---|
| 节点名称 | `回复` |
| 节点类型 | 回复消息 |
| 回复内容 | `{{格式化回复.response}}` |

---

### 第七步：绑定飞书机器人

1. 工作流页面点击 **发布**
2. 复制生成的 **Webhook URL**
3. 打开飞书开放平台 → 你的企业应用 → 事件订阅
4. 配置"接收消息"事件，填入 Webhook URL
5. 权限申请：`im:message:read` + `im:message:send`
6. 提交审核，通过后发布应用

---

### Dify OpenAPI 导入（方案 B 的 Dify 替代方式）

如果使用 Dify 而非飞书 Aily，可以直接导入 OpenAPI 规范：

1. 打开 Dify → 工具 → 自定义工具 → **导入 OpenAPI**
2. URL 填入：`https://dcmapi.pupumall.net/api/ai/openapi.json`
3. 系统自动解析所有 9 个 AI 工具
4. 在 workflow 中直接拖拽使用即可
5. 认证方式选择 **Header** → `X-API-Key` → 填写你的 API Key

---

## 测试用例

| 输入 | 预期调用 |
|---|---|
| 一共有多少台机器 | get_server_stats(group_by=status) |
| 各机房分布 | get_server_stats(group_by=idc) |
| DB-SH-01 的配置 | get_server_detail(identifier=DB-SH-01) |
| 10.0.1.5 是哪台机器 | get_server_detail(identifier=10.0.1.5) |
| 10.0.1.5 的 BMC IP 是多少 | get_server_detail(identifier=10.0.1.5) |
| 192.168.23.108 的带外信息 | get_server_detail(identifier=192.168.23.108) |
| DB-SH-01 的带外管理IP | get_server_detail(identifier=DB-SH-01) |
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
| DB-SH-01 的 CPU 温度多少 | get_server_bmc_status(identifier=DB-SH-01) |
| 这台机器有几个风扇 | get_server_bmc_status(identifier=xxx) |
| 查一下 10.0.1.5 的风扇转速 | get_server_bmc_status(identifier=10.0.1.5) |
| DB-SH-01 电源状态怎么样 | get_server_bmc_status(identifier=DB-SH-01) |
| DB-SH-01 开机了没 | get_server_bmc_status(identifier=DB-SH-01) |
| 这台机器的健康状态 | get_server_bmc_status(identifier=xxx) |
| DB-SH-01 有什么告警 | get_server_bmc_status(identifier=DB-SH-01) |
| DB-SH-01 的主板序列号 | get_server_bmc_status(identifier=DB-SH-01) |
| DB-SH-01 电源部件号 | get_server_bmc_status(identifier=DB-SH-01) |
| DB-SH-01 用的什么品牌内存 | get_server_bmc_status(identifier=DB-SH-01) |
| DB-SH-01 背板 FRU 信息 | get_server_bmc_status(identifier=DB-SH-01) |
| 查一下终端资产 TS-001 的配置 | get_terminal_asset_detail(identifier=TS-001) |
| 市场部有多少台终端资产 | search_terminal_assets(keyword=市场部) |
| Windows 11 的终端有哪些 | search_terminal_assets(os=Windows 11) |
| 戴尔的终端资产 | search_terminal_assets(manufacturer=戴尔) |
| 张三的电脑配置 | search_terminal_assets(keyword=张三) |
| 公司有几台Mac | search_terminal_assets(manufacturer=Apple) |
| DB-SH-01 内存插槽还有空余吗 | get_server_slots(identifier=DB-SH-01) |
| DB-SH-01 插了几根内存 | get_server_slots(identifier=DB-SH-01) |
| 192.168.1.100 的硬盘位还剩几个 | get_server_slots(identifier=192.168.1.100) |
| 这台机器最多能插多少块硬盘 | get_server_slots(identifier=xxx) |
| DB-SH-01 的 DIMM 槽位使用情况 | get_server_slots(identifier=DB-SH-01) |
| DB-SH-01 磁盘槽位满了没 | get_server_slots(identifier=DB-SH-01) |

---

## 常见排错

| 错误 | 原因 | 解决 |
|---|---|---|
| `llm_output is not defined` | 代码节点没绑定输入变量 | 在代码节点配置里添加输入变量，引用上游 LLM 的 response |
| `first path segment in URL cannot contain colon` | HTTP 节点收到了整个对象而非纯 URL | 改用 Python 节点方案，或检查变量引用是否精确到字段 |
| 意图路由返回的内容不是用户问题 | User 提示词没填变量引用 | User 框填 `{{触发器.输出变量名}}`，不是静态文本 |
| 函数签名错误 | Aily Python 入口函数名不匹配 | 尝试 `main` → `handler` → `run` |
| IP 查不到机器 | 后端不支持 IP 查询 | 已支持，所有 identifier 端点同时匹配 hostname/SN/asset_tag/mgmt_ip/biz_ip |
| 资产编号查不到 | 后端未支持 asset_tag | 已支持，更新后端到最新版本 |
| BMC 状态返回 501 | AI_API_KEY 未配置 | 检查后端 .env 中 AI_API_KEY 是否正确设置 |
| 返回数据是 simulated | BMC 不可达 | 正常降级行为，检查目标主机的 BMC IP 和网络连通性 |
| 槽位数据为空 | BMC 快照中无槽位数据 | 检查 BMC 可达性，磁盘槽位可在 DB 中手动配置 disk_slot_count |
| MCP 工具不显示 | MCP Server 未启动或 Dify 连接失败 | 检查 docker exec 命令、网络连通性、stdio/SSE 传输方式是否正确 |

---

## 同步维护清单

每次新增或修改工具时，以下文件/配置需同步更新：

| # | 文件 | 更新内容 |
|---|---|---|
| 1 | `mcp_server.py` | 添加/修改 `@mcp.tool()` + docstring |
| 2 | `ai_query.py` | 添加/修改 REST 端点 |
| 3 | `AILY_WORKFLOW.md`（本文件） | 工具表 + 意图路由 Prompt + 格式化 Prompt + 测试用例 |
| 4 | Dify MCP 工具 | Dify 中刷新 MCP 工具列表 |
| 5 | `ai_openapi.json` | 如使用 OpenAPI 导入需同步更新 |
| 6 | `bmc.py` + `models.py` | 新增采集字段时需同步更新持久化模型和采集逻辑 |

> **2026-08-11 注意**：本次 FRU 增强没有新增工具端点，仅丰富了 `get_server_bmc_status` 和 `get_server_detail` 的返回字段。Dify MCP 工具列表和 Python 节点 `endpoints` 字典无需更改。

---

## 更新记录

| 日期 | 变更 |
|---|---|
| 2026-05-27 | 新增 `get_server_bmc_status` 端点；所有 identifier 端点支持 asset_tag 查询 |
| 2026-05-28 | 新增 `search_network_devices` 和 `search_workstations` 端点（develop 分支） |
| 2026-06-04 | 新增 `search_terminal_assets` 和 `get_terminal_asset_detail` 端点；Dify OpenAPI 导入说明 |
| 2026-06-24 | 新增 `get_server_slots` 端点；更新意图路由/格式化提示词 |
| 2026-06-25 | **对齐更新**：MCP Server 新增 `get_server_slots` 工具；全部 tool docstring 增强为中英双语+场景示例；新增方案 A（MCP 直连 Dify）完整文档；网络设备/PC 工具移至 develop 分支独立维护 |
| 2026-08-11 | **BMC FRU 数据**：新增 PSU FRU（部件号/序列号/厂商/型号）、风扇 FRU（仅超聚变 OEM）、内存厂商（Manufacturer）、主板/背板 FRU（Boards/Assembly API）、硬盘逻辑扇区大小（BlockSizeBytes）。更新意图路由规则/格式化提示词/测试用例 |
