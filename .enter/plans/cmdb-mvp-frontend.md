# CMDB 服务器与备件资产管理平台 — 前端 UI 原型方案

## Context（背景与目标）

公司目前缺少专门的服务器资产与备件耗材管理平台，需要参考开源 CMDB（如 itop、CMDBuild、NocoBase 资产模块）的思路，自建一个更贴合"服务器+备件"场景的轻量平台。最终目标是私有化部署（内网服务器 + Docker Compose）。

本期交付仅包含 **前端 UI 原型 + 模拟数据**，先把所有核心页面跑通，确认交互与信息架构后再接入真实后端（计划下一期使用 Enter Cloud / 自建 FastAPI + PostgreSQL）。

---

## 一、产品信息架构（IA）

平台采用经典的"左侧菜单 + 顶部栏 + 右侧主内容区"布局，使用项目已有的 `src/components/ui/sidebar.tsx`。

```
登录页 (/login)
└── 主框架 (AppLayout)
    ├── 仪表盘            /            概览统计、健康汇总、近期告警
    ├── 服务器资产        /servers     列表、详情、增删改、批量导入
    │   └── 服务器详情    /servers/:id Tab：基本信息 / BMC 实时状态 / 部件清单 / 操作日志
    ├── 备件库存          /inventory   分类（硬盘/内存/网卡/光模块/其他）
    │   ├── 备件列表      /inventory/parts
    │   ├── 入库记录      /inventory/inbound
    │   ├── 出库/领用     /inventory/outbound
    │   └── 备件详情      /inventory/parts/:id
    ├── 操作日志          /audit       全平台审计日志
    └── 系统管理          /system
        ├── 用户管理      /system/users
        └── 角色权限      /system/roles
```

**角色权限（前端模拟）：**
- `admin`：所有权限
- `operator`：资产/备件 CRUD，不可管用户
- `viewer`：只读

---

## 二、技术栈与架构选择

### 前端（本期实现）
- **React 19 + Vite + TypeScript**（已有模板）
- **Tailwind CSS 3 + shadcn/ui**（已有）
- **react-router-dom v7**（已有，扩展 `src/router.tsx`）
- **@tanstack/react-query**（已有）+ `mockApi` 层模拟接口延迟
- **react-hook-form + zod**（已有）做表单校验
- **recharts**（已有）画 BMC 温度/告警趋势
- **lucide-react**（已有）作为图标库（严格禁用 emoji）

### 后端（下一期参考，本期不实现，仅写入 README 规划）
私有化部署优先方案，全部支持 Docker Compose：
- API：**Python FastAPI**（生态丰富，BMC 库齐全）
- DB：**PostgreSQL 16**
- 缓存/队列：**Redis**
- BMC 采集：
  - **Redfish**：`sushy` / `python-redfishclient`
  - **IPMI**：调用宿主机 `ipmitool` 或 `pyghmi`
  - 由后端定时任务（APScheduler/Celery beat）按设备 `bmc_protocol` 字段自动选择
- 反向代理：Nginx
- 一键部署：`docker-compose.yml`（frontend、api、worker、db、redis、nginx）

---

## 三、数据模型（前端 TS 类型 + Mock 数据）

放在 `src/types/cmdb.ts`，Mock 数据放 `src/mocks/`。

```ts
// 服务器
type Server = {
  id: string;
  hostname: string;
  sn: string;             // 序列号
  assetTag: string;       // 资产编号
  manufacturer: 'Dell' | 'HPE' | 'Lenovo' | 'Inspur' | 'Supermicro' | 'Other';
  model: string;
  cpuModel: string;
  cpuCount: number;
  memoryGB: number;
  location: { idc: string; rack: string; uPosition: string };
  mgmtIp: string;         // BMC IP
  bmcProtocol: 'redfish' | 'ipmi';
  bmcUser: string;
  status: 'online' | 'offline' | 'maintenance' | 'retired';
  owner: string;
  purchaseDate: string;
  warrantyEnd: string;
  tags: string[];
  remark?: string;
};

// BMC 实时状态（模拟轮询返回）
type BmcStatus = {
  power: 'On' | 'Off';
  health: 'OK' | 'Warning' | 'Critical';
  cpuTempC: number;
  inletTempC: number;
  fans: { name: string; rpm: number; status: string }[];
  psus: { name: string; watts: number; status: string }[];
  alerts: { time: string; level: string; message: string }[];
};

// 备件
type Part = {
  id: string;
  category: 'disk' | 'memory' | 'nic' | 'optical' | 'other';
  brand: string;
  model: string;
  spec: string;          // 例如 "1.92TB SATA SSD" / "32GB DDR4-3200 RDIMM"
  sn?: string;           // 单件可有 SN
  stock: number;         // 当前库存
  safetyStock: number;   // 安全库存（低于报警）
  location: string;      // 仓库位置
  status: 'in_stock' | 'allocated' | 'in_use' | 'scrapped';
};

// 出入库记录
type StockMovement = {
  id: string;
  partId: string;
  type: 'inbound' | 'outbound' | 'return' | 'scrap';
  quantity: number;
  operator: string;
  relatedServerId?: string;  // 出库时挂到服务器
  reason: string;
  time: string;
};

// 用户
type User = { id: string; username: string; name: string; role: 'admin'|'operator'|'viewer'; enabled: boolean };
```

---

## 四、关键文件改动清单

### 新增
- `src/router.tsx` — 替换为完整路由配置
- `src/layouts/AppLayout.tsx` — 主框架（侧边栏 + 顶部栏 + Outlet）
- `src/layouts/AuthLayout.tsx` — 登录页骨架
- `src/contexts/AuthContext.tsx` — 模拟登录态 + 角色守卫 `RequireRole`
- `src/types/cmdb.ts` — 类型定义
- `src/mocks/servers.ts` / `parts.ts` / `movements.ts` / `users.ts` — Mock 数据
- `src/lib/mockApi.ts` — 包装 Promise + setTimeout 的"伪 API"，便于以后替换为真实 fetch
- `src/hooks/useServers.ts` / `useParts.ts` / `useBmcStatus.ts` — react-query hooks
- 页面（每个文件 ≤200 行，拆分子组件）：
  - `src/pages/Login.tsx`
  - `src/pages/Dashboard.tsx`
  - `src/pages/servers/ServerList.tsx`
  - `src/pages/servers/ServerDetail.tsx` （含 Tabs：Info / BMC / Parts / Logs）
  - `src/pages/servers/ServerForm.tsx` （新增/编辑对话框）
  - `src/pages/inventory/PartList.tsx`
  - `src/pages/inventory/PartDetail.tsx`
  - `src/pages/inventory/InboundList.tsx`
  - `src/pages/inventory/OutboundList.tsx`
  - `src/pages/inventory/MovementForm.tsx`
  - `src/pages/audit/AuditLog.tsx`
  - `src/pages/system/UserList.tsx`
  - `src/pages/system/RoleList.tsx`
  - `src/pages/NotFound.tsx`（保留）
- 复用组件：
  - `src/components/cmdb/StatusBadge.tsx`
  - `src/components/cmdb/HealthIndicator.tsx`
  - `src/components/cmdb/PageHeader.tsx`
  - `src/components/cmdb/DataTableToolbar.tsx`（搜索 + 筛选 + 列控制）
  - `src/components/cmdb/StatCard.tsx`
  - `src/components/cmdb/BmcLiveCard.tsx` （温度环/风扇转速/电源功率 用 recharts）

### 修改
- `src/App.tsx` — 包入 `QueryClientProvider` + `AuthProvider` + `Toaster`
- `src/index.css` — 加入 CMDB 设计令牌（运维向：深色主色 + 状态色 OK/Warn/Crit/Info；自定义阴影/渐变）
- `src/pages/Index.tsx` — 登录后重定向到 `/dashboard`，未登录到 `/login`

### 设计令牌（在 index.css 中新增，用 HSL）
```
--primary           深石板蓝（运维感）
--success / --warning / --danger / --info  四态状态色（OK/警告/严重/信息）
--chart-1..5        recharts 多色板
--gradient-primary  顶部栏渐变
--shadow-elevated   卡片悬浮阴影
```
所有页面只用语义 token，禁止裸写 `text-white` / `bg-white`。

---

## 五、复用与约束

- **复用** 项目已有 `src/components/ui/sidebar.tsx`（包含响应式折叠）作为左侧导航主体。
- **复用** 已有 `Table`、`Dialog`、`Form`、`Tabs`、`Badge`、`Card`、`Sonner` toast 等 shadcn 组件，统一交互体感。
- **复用** `lucide-react` 图标（Server, HardDrive, Cpu, MemoryStick, Network, Cable, Activity, Shield, Users 等）。
- 不新增 npm 包；当前依赖已足够覆盖本期所有功能。
- **mockApi** 全部走 `src/lib/mockApi.ts`，函数签名按真实 REST 设计（`getServers(params)`, `createServer(dto)` …），下一期把内部实现从 mock 切到 `fetch('/api/...')` 即可，UI 层零改动。
- BMC 实时状态：在 `useBmcStatus` 中用 `react-query` 的 `refetchInterval: 5000` 模拟轮询，伪数据带轻微随机抖动让图表"活起来"。

---

## 六、验证方式（交付后你可以这样测）

1. 打开预览 → 自动跳到 `/login`，使用 `admin / admin123`、`operator / 123456`、`viewer / 123456` 三种账号登录。
2. 登录后进入仪表盘，看到资产总数、在线/离线、库存预警、近期告警等卡片。
3. 进入"服务器资产"：
   - 表格支持按 hostname / SN / IP / IDC / 状态 搜索过滤
   - 新增/编辑/删除按钮（viewer 角色按钮变灰）
   - 点击行进入详情，BMC Tab 看到实时温度/风扇/电源（每 5 秒刷新）
4. 进入"备件库存"：
   - 切换硬盘/内存/网卡/光模块分类
   - 新增入库、出库（出库可关联到某台服务器）
   - 库存低于安全库存时行高亮 + 仪表盘出现预警
5. 用 viewer 账号登录，确认 `/system/*` 路由被守卫重定向到 403 提示。
6. 浏览器宽度切到 ≤768px，侧边栏自动折叠为抽屉，主表格变卡片视图。
7. `pnpm lint` 通过。

---

## 七、不在本期范围

- 真实后端 / 数据库 / Edge Function
- 真实 Redfish / IPMI 调用
- 数据导入导出 Excel（占位按钮，下期实现）
- 告警通知（邮件/钉钉/飞书）
- 拓扑图、机柜可视化（评估后下期实现）
- Docker Compose 部署文件（待后端确定后输出）
