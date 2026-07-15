# AI API 接口文档

> 分支: `enter-main` | 文件: `reference-backend/app/api/ai_query.py` | 路由前缀: `/api/ai`

## 接口总览

| # | 方法 | 端点 | 用途 |
|---|------|------|------|
| 1 | GET | `/api/ai/search-servers` | 搜索主机资产 |
| 2 | GET | `/api/ai/get-server-detail` | 获取单台主机完整信息 |
| 3 | GET | `/api/ai/search-parts` | 搜索备件库存 |
| 4 | GET | `/api/ai/get-server-stats` | 统计主机资产概况 |
| 5 | GET | `/api/ai/get-server-disks` | 获取某台主机的硬盘列表 |
| 6 | GET | `/api/ai/get-server-slots` | 获取主机内存/磁盘槽位信息 |
| 7 | GET | `/api/ai/get-server-bmc-status` | 获取主机 BMC 实时状态 |
| 8 | GET | `/api/ai/search-terminal-assets` | 搜索终端资产 |
| 9 | GET | `/api/ai/get-terminal-asset-detail` | 获取单台终端资产完整信息 |
| 10 | GET | `/api/ai/openapi.json` | 导出 OpenAPI Schema（供 Dify 导入） |

---

## 1. 搜索主机资产

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/search-servers?keyword=浪潮&status=online&limit=5'
```

### 响应

```json
{
    "count": 2,
    "items": [
        {
            "hostname": "inspur-nf5280m6-01",
            "sn": "NF5280M6-SN001",
            "assetTag": "ASSET-001",
            "manufacturer": "Inspur",
            "model": "NF5280M6",
            "cpuModel": "Intel Xeon Gold 6330",
            "cpuCount": 2,
            "memoryGB": 512,
            "diskCount": 8,
            "status": "online",
            "mgmtIp": "172.19.119.220",
            "bizIp": "10.0.1.10",
            "location": {"idc": "ap-beijing-7", "rack": "A01", "uPosition": "10-12"},
            "owner": "ops-team"
        }
    ]
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 任意关键词，匹配主机名/SN/资产编号/IP/型号/厂商/CPU/IDC/备注 |
| `status` | string | 否 | 状态过滤: `online`, `offline`, `maintenance`, `retired` |
| `idc` | string | 否 | 机房过滤 |
| `hostname` | string | 否 | 主机名精确匹配 |
| `sn` | string | 否 | 序列号精确匹配 |
| `ip` | string | 否 | IP 地址匹配（业务IP或管理IP） |
| `manufacturer` | string | 否 | 厂商过滤，支持中英文（`戴尔`/`Dell`, `惠普`/`HPE`, `浪潮`/`Inspur` 等） |
| `limit` | int | 否 | 返回条数上限，默认 20，最大 100 |

---

## 2. 获取单台主机完整信息

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/get-server-detail?identifier=172.19.119.220'
```

### 响应

```json
{
    "found": true,
    "hostname": "inspur-nf5280m6-01",
    "sn": "NF5280M6-SN001",
    "assetTag": "ASSET-001",
    "manufacturer": "Inspur",
    "model": "NF5280M6",
    "cpuModel": "Intel Xeon Gold 6330",
    "cpuCount": 2,
    "memoryGB": 512,
    "diskCount": 8,
    "status": "online",
    "mgmtIp": "172.19.119.220",
    "bizIp": "10.0.1.10",
    "idc": "ap-beijing-7",
    "rack": "A01",
    "uPosition": "10-12",
    "owner": "ops-team",
    "memorySlots": {"total": 32, "used": 16, "formFactor": "DIMM"},
    "diskSlots": {"total": 12, "used": 8, "formFactor": "2.5inch", "backplanes": [{"slot": 0, "drives": 4}]}
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `identifier` | string | **是** | 主机名、SN序列号、资产编号或IP地址 |

---

## 3. 搜索备件库存

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/search-parts?category=disk&spec=SSD&status=in_stock&limit=5'
```

### 响应

```json
{
    "count": 3,
    "items": [
        {
            "category": "disk",
            "brand": "Samsung",
            "model": "PM1733",
            "spec": "1.92TB SSD NVMe",
            "sn": "S4EZNX0R500123",
            "stock": 10,
            "safetyStock": 5,
            "unit": "块",
            "location": "A01-3F-备件库",
            "status": "in_stock"
        }
    ]
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 任意关键词，匹配品牌/型号/规格/SN/备注 |
| `category` | string | 否 | 类别: `disk`, `memory`, `nic`, `optical`, `other` |
| `brand` | string | 否 | 品牌过滤 |
| `model` | string | 否 | 型号过滤 |
| `spec` | string | 否 | 规格过滤，如 `2TB SSD` |
| `status` | string | 否 | 状态: `in_stock`, `allocated`, `in_use`, `scrapped` |
| `limit` | int | 否 | 返回条数上限，默认 20，最大 100 |

---

## 4. 统计主机资产概况

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/get-server-stats?group_by=manufacturer'
```

### 响应

```json
{
    "groupBy": "manufacturer",
    "total": 150,
    "items": [
        {"key": "Inspur", "count": 60},
        {"key": "Dell", "count": 40},
        {"key": "HPE", "count": 25},
        {"key": "Huawei", "count": 15},
        {"key": "XFusion", "count": 10}
    ]
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `group_by` | string | 否 | 统计维度: `status`, `idc`, `manufacturer`（默认 `status`） |

---

## 5. 获取某台主机的硬盘列表

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/get-server-disks?identifier=172.19.119.220'
```

### 响应

```json
{
    "found": true,
    "hostname": "inspur-nf5280m6-01",
    "sn": "NF5280M6-SN001",
    "diskCountDb": 8,
    "source": "snapshot",
    "diskCountBmc": 8,
    "drives": [
        {
            "name": "Disk 0",
            "model": "Samsung PM1733",
            "sn": "S4EZNX0R500123",
            "capacityGB": 1920,
            "mediaType": "SSD",
            "formFactor": "2.5inch",
            "status": "OK"
        }
    ]
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `identifier` | string | **是** | 主机名、SN序列号、资产编号或IP地址 |

---

## 6. 获取主机内存/磁盘槽位信息

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/get-server-slots?identifier=172.19.119.220'
```

### 响应

```json
{
    "found": true,
    "hostname": "inspur-nf5280m6-01",
    "sn": "NF5280M6-SN001",
    "assetTag": "ASSET-001",
    "manufacturer": "Inspur",
    "model": "NF5280M6",
    "source": "snapshot",
    "memorySlots": {"total": 32, "used": 16, "formFactor": "DIMM"},
    "diskSlots": {"total": 12, "used": 8, "formFactor": "2.5inch", "backplanes": [{"slot": 0, "drives": 4}]}
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `identifier` | string | **是** | 主机名、SN序列号、资产编号或IP地址 |

---

## 7. 获取主机 BMC 实时状态

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/get-server-bmc-status?identifier=172.19.119.220'
```

### 响应

```json
{
    "found": true,
    "hostname": "inspur-nf5280m6-01",
    "sn": "NF5280M6-SN001",
    "assetTag": "ASSET-001",
    "manufacturer": "Inspur",
    "model": "NF5280M6",
    "status": "online",
    "mgmtIp": "172.19.119.220",
    "bizIp": "10.0.1.10",
    "bmcProtocol": "redfish",
    "source": "snapshot",
    "collectedAt": "2026-07-03T08:00:00Z",
    "power": {"state": "On", "averageWatts": 450},
    "health": "OK",
    "bootProgress": "OSRunning",
    "cpuTempC": 45,
    "inletTempC": 22,
    "fanCount": 8,
    "fans": [
        {"name": "Fan1A", "rpm": 12000, "status": "OK"},
        {"name": "Fan1B", "rpm": 11800, "status": "OK"}
    ],
    "memoryTotalGiB": 512,
    "memoryModuleCount": 16,
    "memorySlots": {"total": 32, "populated": 16},
    "memoryModules": [
        {"slot": "DIMM_A1", "model": "Samsung M393A4K40DB3-CWE", "sn": "80AD0123456789ABCD", "capacityMiB": 32768, "memoryType": "DDR4", "status": "OK"}
    ],
    "diskCount": 8,
    "diskSlots": {"total": 12, "populated": 8},
    "disks": [
        {"name": "Disk 0", "model": "Samsung PM1733", "sn": "S4EZNX0R500123", "capacityGB": 1920, "mediaType": "SSD", "formFactor": "2.5inch", "status": "OK"}
    ],
    "psuCount": 2,
    "psus": [
        {"name": "PSU1", "watts": 550, "capacityW": 800, "status": "OK"},
        {"name": "PSU2", "watts": 520, "capacityW": 800, "status": "OK"}
    ],
    "alertCount": 0,
    "alerts": []
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `identifier` | string | **是** | 主机名、SN序列号、资产编号或IP地址 |

---

## 8. 搜索终端资产

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/search-terminal-assets?keyword=张三&manufacturer=Dell&limit=5'
```

### 响应

```json
{
    "count": 1,
    "items": [
        {
            "hostname": "NB-ZHANGSAN-01",
            "sn": "DELL-LATITUDE-SN001",
            "assetTag": "TA-001",
            "manufacturer": "Dell",
            "model": "Latitude 5540",
            "os": "Windows 11",
            "bizIp": "10.0.10.50",
            "userName": "张三",
            "status": "online"
        }
    ]
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 否 | 任意关键词，匹配计算机名/SN/资产编号/IP/型号/使用人/部门 |
| `manufacturer` | string | 否 | 厂商过滤: `Dell`, `HP`, `Lenovo`, `Apple`, `Huawei`, `ASUS`, `Acer`, `Microsoft` |
| `status` | string | 否 | 状态: `online`, `offline`, `maintenance`, `retired` |
| `os` | string | 否 | 操作系统过滤 |
| `limit` | int | 否 | 返回条数上限，默认 20，最大 100 |

---

## 9. 获取单台终端资产完整信息

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/get-terminal-asset-detail?identifier=NB-ZHANGSAN-01'
```

### 响应

```json
{
    "found": true,
    "hostname": "NB-ZHANGSAN-01",
    "sn": "DELL-LATITUDE-SN001",
    "assetTag": "TA-001",
    "manufacturer": "Dell",
    "model": "Latitude 5540",
    "os": "Windows 11",
    "cpu": "Intel Core i7-1365U",
    "memoryGB": 32,
    "diskGB": 512,
    "bizIp": "10.0.10.50",
    "macAddress": "AA:BB:CC:DD:EE:FF",
    "userName": "张三",
    "department": "技术部",
    "status": "online",
    "remark": ""
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `identifier` | string | **是** | 计算机名、SN序列号、资产编号或IP地址 |

---

## 10. 导出 OpenAPI Schema（供 Dify 导入）

```bash
curl --location --request GET 'http://dcmapi.pupumall.net/api/ai/openapi.json'
```

### 响应

```json
{
    "openapi": "3.0.2",
    "info": {"title": "FastAPI", "version": "0.1.0"},
    "servers": [{"url": "http://dcmapi.pupumall.net/api/ai", "description": "AI tools"}],
    "paths": {
        "/api/ai/search-servers": {},
        "/api/ai/get-server-detail": {},
        "/api/ai/search-parts": {},
        "/api/ai/get-server-stats": {},
        "/api/ai/get-server-disks": {},
        "/api/ai/get-server-slots": {},
        "/api/ai/get-server-bmc-status": {},
        "/api/ai/search-terminal-assets": {},
        "/api/ai/get-terminal-asset-detail": {}
    }
}
```

---

## 数据来源说明

| 类别 | 端点 | 数据来源 |
|------|------|---------|
| 主机搜索 | `search-servers` | 数据库 |
| 主机详情 | `get-server-detail` | 数据库 + BMC 快照（槽位信息） |
| 备件搜索 | `search-parts` | 数据库 |
| 统计概览 | `get-server-stats` | 数据库聚合 |
| 硬盘详情 | `get-server-disks` | BMC 快照 → 实时采集 |
| 槽位信息 | `get-server-slots` | BMC 快照 → 实时采集 → DB fallback |
| BMC 实时状态 | `get-server-bmc-status` | BMC 快照 → 实时采集 |
| 终端资产搜索 | `search-terminal-assets` | 数据库 |
| 终端资产详情 | `get-terminal-asset-detail` | 数据库 |
| Schema 导出 | `openapi.json` | 元数据（自动生成） |

> **注意**: 所有端点均无鉴权，方便 Dify/Aily 平台直接导入调用。
