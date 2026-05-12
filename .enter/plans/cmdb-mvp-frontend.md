# Round 2: 真后端落地方案（Enter Cloud + 内网 MySQL 参考实现）

## Context（背景）

第一轮已交付前端 UI 原型（含登录、仪表盘、服务器/备件 CRUD、BMC 实时面板、用户与审计），全部走 `src/lib/mockApi.ts` 内存伪 API。

本轮目标：**用真实后端替掉 `mockApi`，完成可在 Enter 平台内闭环验证的功能版本**，并**同步输出一份基于 MySQL + FastAPI + docker-compose 的内网参考后端源码**，方便你后续在公司内网做私有化部署。

最终架构分两条线：

| 线路 | 平台内闭环（本轮主战场） | 内网私有化（本轮交付参考实现，下期对接） |
|------|--------------------------|------------------------------------------|
| 数据库 | Enter Cloud（Postgres） | MySQL 8 |
| API | Enter Cloud Edge Function（Deno） | FastAPI（Python） |
| 认证 | Supabase Auth (邮箱+密码) | FastAPI JWT（参考实现） |
| BMC 采集 | Edge Function 代理 Redfish | FastAPI APScheduler 周期采集 |
| 部署 | Enter Cloud 托管 | Docker Compose 一键部署 |

前端代码只对接 Enter Cloud 一份 API 抽象层；内网版后续只需把 `lib/api/*` 的 baseURL 切到 FastAPI 即可，UI 零改动。

---

## 一、启用 Enter Cloud（首步）

调用 `supabase_enable` 弹窗让你授权。授权后即可：
- 写迁移脚本建表
- 写 Edge Function（BMC 代理）
- 启用 Auth（邮箱密码登录）
- 让前端用 `@supabase/supabase-js` 直连

> 注：Enter Cloud 本质是 self-hosted Supabase，必须用 Postgres。MySQL 只在**参考后端**里出现，不影响本平台运行。

---

## 二、数据库 Schema（Postgres / Supabase）

迁移文件位置：`supabase/migrations/<ts>_init_cmdb.sql`

### 表设计

```sql
-- 角色枚举
create type app_role as enum ('admin','operator','viewer');

-- profiles：扩展 auth.users
create table profiles (
  id uuid primary key references auth.users on delete cascade,
  username text not null unique,
  name text not null,
  role app_role not null default 'viewer',
  enabled boolean not null default true,
  last_login timestamptz,
  created_at timestamptz default now()
);

-- 服务器
create type server_status as enum ('online','offline','maintenance','retired');
create type bmc_protocol as enum ('redfish','ipmi');

create table servers (
  id uuid primary key default gen_random_uuid(),
  hostname text not null,
  sn text not null unique,
  asset_tag text not null unique,
  manufacturer text not null,
  model text not null,
  cpu_model text not null,
  cpu_count int not null,
  memory_gb int not null,
  disk_count int not null default 0,
  idc text not null,
  rack text not null,
  u_position text not null,
  mgmt_ip text not null,
  biz_ip text not null,
  bmc_protocol bmc_protocol not null,
  bmc_user text not null,
  bmc_password text,            -- 密文存储（pgcrypto），edge 函数 service_role 才能读
  status server_status not null default 'online',
  owner text,
  purchase_date date,
  warranty_end date,
  tags text[] default '{}',
  remark text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index on servers (status);
create index on servers (idc);

-- 备件
create type part_category as enum ('disk','memory','nic','optical','other');
create type part_status as enum ('in_stock','allocated','in_use','scrapped');

create table parts (
  id uuid primary key default gen_random_uuid(),
  category part_category not null,
  brand text not null,
  model text not null,
  spec text not null,
  sn text,
  stock int not null default 0 check (stock >= 0),
  safety_stock int not null default 0,
  unit text not null default '块',
  location text not null,
  status part_status not null default 'in_stock',
  remark text,
  created_at timestamptz default now()
);

-- 出入库流水
create type movement_type as enum ('inbound','outbound','return','scrap');

create table stock_movements (
  id uuid primary key default gen_random_uuid(),
  part_id uuid not null references parts on delete restrict,
  type movement_type not null,
  quantity int not null check (quantity > 0),
  operator text not null,
  related_server_id uuid references servers on delete set null,
  reason text not null,
  created_at timestamptz default now()
);
create index on stock_movements (part_id);
create index on stock_movements (related_server_id);

-- 审计日志
create type audit_level as enum ('info','warn','danger');

create table audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor text not null,
  action text not null,
  target text not null,
  detail text,
  level audit_level not null default 'info',
  created_at timestamptz default now()
);
create index on audit_logs (created_at desc);
```

### 库存联动触发器
`stock_movements` insert 时自动加减 `parts.stock`；inbound/return → +qty，outbound/scrap → -qty；负库存抛错。同时落一条 `audit_logs`。

### Row Level Security（RLS）
启用所有表 RLS，策略来源都是 `profiles.role`：

| 表 | viewer | operator | admin |
|----|--------|----------|-------|
| servers | select | select / insert / update / delete | + |
| parts | select | select / insert / update / delete | + |
| stock_movements | select | select / insert | + delete |
| profiles | select 自己 | select 自己 | all |
| audit_logs | select | select | + |

辅助函数：
```sql
create function current_role() returns app_role
language sql stable security definer as $$
  select role from profiles where id = auth.uid();
$$;
```

### 种子数据
`supabase/migrations/<ts>_seed_cmdb.sql`
将第一轮 `src/mocks/servers.ts` / `src/mocks/parts.ts` 的 8 台服务器 + 10 个备件 + 7 条出入库记录写入数据库（移除 mock 文件）。BMC 密码字段留空，由你在 UI 编辑时录入。

---

## 三、认证

- 启用 Supabase Auth 邮箱+密码登录。
- 触发器：`auth.users` 新建时自动在 `profiles` 插一条 `viewer` 角色记录。
- 三个种子账号通过迁移直接 `insert into auth.users` + `profiles`：
  - `admin@corp.local / admin123` → admin
  - `operator@corp.local / 123456` → operator
  - `viewer@corp.local / 123456` → viewer
- 前端 `AuthProvider` 改为：
  - `signIn` 调 `supabase.auth.signInWithPassword`
  - 监听 `onAuthStateChange`，登录后立即查 `profiles` 拿 role
  - `signOut` 调 `supabase.auth.signOut`
- 路由守卫 `RequireRole` 逻辑保留，数据来源换成真实 profile。

---

## 四、Edge Functions

### `supabase/functions/bmc-status/index.ts`
- 入参：`{ serverId: string }`
- 流程：
  1. 校验调用者已登录（任何角色都可）
  2. 用 service_role 取该 server 的 `mgmt_ip`/`bmc_user`/`bmc_password`/`bmc_protocol`
  3. `bmc_protocol === 'redfish'`：用 `fetch` 调用 Redfish endpoints：
     - `/redfish/v1/Systems/1`（电源/健康）
     - `/redfish/v1/Chassis/1/Thermal`（温度/风扇）
     - `/redfish/v1/Chassis/1/Power`（电源功率）
     - 自签证书时 `Deno.env` 关闭 TLS 校验（仅内网）
  4. `bmc_protocol === 'ipmi'`：返回 `{ status: 'pending', message: 'IPMI 采集需内网 collector，本轮未集成' }` 占位
  5. 标准化为前端 `BmcStatus` JSON 结构返回
- 现阶段验证：用 [`dmtf/redfish-mockup-server`](https://github.com/DMTF/Redfish-Mockup-Server) 的公网示例数据，在迁移里给 `bj-prod-web-01` 默认填一个 mock host，使 BMC tab 立刻有真实数据。

### `supabase/functions/audit/index.ts`（轻量包装，可选）
封装写审计的统一入口；前端关键操作（CRUD、出入库）走它。

---

## 五、前端改造

新增/替换文件：

```
src/lib/
  ├── supabase.ts           // 创建 supabase client（环境变量从 src/env.d.ts 现有定义读取）
  └── api/
      ├── servers.ts        // 替代 mockApi 中的 server 部分
      ├── parts.ts
      ├── movements.ts
      ├── users.ts
      ├── audit.ts
      └── bmc.ts            // 调用 edge function bmc-status
src/contexts/AuthContext.tsx // 改为 Supabase Auth 实现
```

删除：`src/lib/mockApi.ts`、`src/mocks/*`（数据已迁库）。

页面层（Dashboard / ServerList / ServerDetail / PartList / PartDetail / Movement* / UserList / AuditLog / Login）只需改 `import` 路径，函数签名保持一致：
- `listServers()`、`createServer(dto)`、`updateServer(id, patch)`、`deleteServer(id)` …
- `getBmcStatus(serverId)` 仍走 `useQuery` + `refetchInterval: 5000`

react-query 的 `queryKey` 不变，缓存与失效逻辑零改动。

### 字段命名映射
DB 用 snake_case，前端用 camelCase。在 `lib/api/*.ts` 里做单点映射（写两个小工具 `toServer(row)` / `toServerDto(model)`），避免 UI 层散落 snake_case。

---

## 六、内网参考后端（同步交付源码，目录 `reference-backend/`）

不在 Enter 平台运行，仅作为可下载的源码包。结构：

```
reference-backend/
├── docker-compose.yml          # mysql8 + api + nginx + collector
├── .env.example
├── README.md                   # 部署步骤
├── api/                        # FastAPI
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic/                # 与 supabase 迁移等价的 MySQL 版本
│   └── app/
│       ├── main.py
│       ├── deps.py             # JWT / role 校验
│       ├── models.py           # SQLAlchemy
│       ├── schemas.py          # pydantic
│       ├── routes/
│       │   ├── auth.py
│       │   ├── servers.py
│       │   ├── parts.py
│       │   ├── movements.py
│       │   ├── users.py
│       │   ├── audit.py
│       │   └── bmc.py          # Redfish (sushy) + IPMI (pyghmi) 双协议
│       └── scheduler.py        # APScheduler：每 5min 轮询 BMC 写缓存
└── nginx/default.conf
```

提供与 Enter Cloud 完全一致的接口契约（路径、字段、状态码），前端切换只需改 `VITE_API_BASE_URL`。

> 说明：参考后端源码本轮仅生成"骨架可运行"版本（建表、CRUD、JWT、Redfish 接口），不会在 Enter 平台启动；你拷到内网 `docker compose up -d` 即可起。

---

## 七、改动文件清单总览

### Enter 平台（必改）
- 启用 Enter Cloud（`supabase_enable`）
- `supabase/migrations/0001_init_cmdb.sql`
- `supabase/migrations/0002_seed_cmdb.sql`
- `supabase/functions/bmc-status/index.ts`
- 新增 `src/lib/supabase.ts`、`src/lib/api/{servers,parts,movements,users,audit,bmc}.ts`
- 改写 `src/contexts/AuthContext.tsx`、`src/contexts/auth-context.ts` 不变
- 删除 `src/lib/mockApi.ts`、`src/mocks/*.ts`
- 9 个页面文件改 import 指向新 api 模块（无逻辑改动）

### 内网参考（同步交付）
- `reference-backend/`（约 25 个文件）

---

## 八、本轮 NOT IN SCOPE（已与你对齐为下期）

- **IPMI 真实采集**：Edge Function 不能调 ipmitool，需要内网 collector 守护进程。本轮 `bmc-status` 对 IPMI 协议返回 `pending` 占位，预留协议字段，下期再上 collector。
- **告警通知（邮件 / 钉钉 / 飞书）**
- **CSV 导入导出**
- **机柜可视化拓扑**
- **BMC 远程电源控制（重启/关机）**
- **MFA / SSO**

---

## 九、验证方式

1. 用三个迁移种子账号分别登录，验证角色守卫与 RLS（viewer 不能 insert/delete）。
2. 在 UI 上新增/编辑/删除一台服务器，刷新后数据从 Postgres 持久化（不再因刷新丢失）。
3. 给 `bj-prod-web-01` 录入 DMTF 公开 mockup 的 BMC 地址，进入详情 BMC tab，能看到从 Edge Function 拉回的真实 Redfish 数据，且 5 秒自动刷新。
4. 出入库后 `parts.stock` 自动变化，`audit_logs` 出现一条记录。
5. 管理员在用户管理把 viewer 改成 operator，该用户重新登录后可以看到编辑按钮。
6. 关掉网络后 BMC tab 显示错误提示而不是死循环。
7. 把 `reference-backend/` 拷到本地 `docker compose up`，访问 http://localhost/api/v1/servers 能看到与 Enter Cloud 一致的字段结构。
8. `pnpm lint`、`pnpm build` 均通过。

---

## 十、执行顺序（落地节奏）

1. `supabase_enable`（等你弹窗授权）
2. 写迁移建表 + 种子 + 触发器 + RLS
3. Auth 改造（前端 AuthContext + 三个种子账号）
4. `lib/api/*` 落地，逐个替换 mockApi 调用，删 mock
5. Edge Function `bmc-status` + 详情页接入
6. 全链路自测（含 lint、build）
7. 输出 `reference-backend/` 源码包

每步独立提交，便于你随时回滚或暂停。
