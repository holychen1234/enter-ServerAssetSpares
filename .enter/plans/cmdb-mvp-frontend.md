# 需求补充：业务 IP 字段 + 仪表盘品牌分布

## Context（背景）

用户提出两点增强：
1. 服务器资产需要新增「业务 IP」字段（与已有的 BMC 管理 IP 区分），用于记录服务器对外/对内的实际业务通信地址。
2. 仪表盘需要新增一张图，按厂商（品牌）展示服务器数量分布。

## 改动清单（最小化）

### 1. 类型 — `src/types/cmdb.ts`
在 `Server` 接口里新增 `bizIp: string` 字段（位置紧挨 `mgmtIp`）。

### 2. Mock 数据 — `src/mocks/servers.ts`
为 8 台示例服务器各补一条业务 IP（`172.16.x.y` 网段，与 `10.x.x.x` 管理网区分）。

### 3. 新增/编辑表单 — `src/pages/servers/ServerForm.tsx`
- zod schema 新增 `bizIp: z.string().min(1, "必填")`
- 默认值 EMPTY 增加 `bizIp: ""`
- `useEffect` 回填初始值时增加 `bizIp: initial.bizIp`
- handleSubmit 提交时把 `bizIp` 传出
- 表单 UI：在「BMC IP」字段旁新增一个 `Field` 输入框，label 为「业务 IP」，placeholder 示例 `172.16.10.11`

### 4. 列表页 — `src/pages/servers/ServerList.tsx`
- 在原「BMC」列基础上把业务 IP 也展示出来：保持单列「IP 地址」并以两行展示
  - 第一行：业务 IP（强调，带「业务」小标签）
  - 第二行：BMC IP（次级，带协议小标签）
- 搜索过滤新增 `s.bizIp.includes(kw)`

### 5. 详情页 — `src/pages/servers/ServerDetail.tsx`
在「BMC 接入」卡片之外，将「网络」单独成卡或在 BMC 卡前新增一行：
- 业务 IP（mono）
- BMC IP（mono）
- 协议、用户

实现方式：在「BMC 接入」InfoCard 顶部插入一行 `Row label="业务 IP" value={server.bizIp} mono`，避免新增卡片造成布局碎裂。

### 6. 仪表盘 — `src/pages/Dashboard.tsx`
新增「服务器品牌分布」图，与现有「服务器状态分布」放在同一行：
- 数据：`servers.reduce` 聚合 `manufacturer → count`
- 形式：水平条形图（`BarChart layout="vertical"`），更适合品牌名展示
- 颜色：使用 `--chart-1` 主色，配合 `--chart-2` ~ `--chart-5` 循环
- 布局调整：原本 `lg:grid-cols-3`（饼图1 + 库存柱状图2）改为：
  - 第一行 3 列：状态饼图 1 + 品牌柱状图 1 + 备件库存柱状图 1
  - 或将品牌图单列一行，避免拥挤

最终采用：把「状态分布饼图 + 品牌分布条形图」放在同一行（`lg:grid-cols-2`），「备件库存柱状图」单独一行铺满。这样三张图都不会过窄。

## 受影响文件
- `src/types/cmdb.ts`
- `src/mocks/servers.ts`
- `src/pages/servers/ServerForm.tsx`
- `src/pages/servers/ServerList.tsx`
- `src/pages/servers/ServerDetail.tsx`
- `src/pages/Dashboard.tsx`

## 验证
1. 仪表盘第一行可见三张统计卡 + 4 张统计卡，下方第一行同时看到「服务器状态分布」饼图与「服务器品牌分布」条形图。
2. 进入「服务器资产」列表，IP 列同时显示业务 IP 与 BMC IP；在搜索框输入业务 IP 片段（如 `172.16`）能过滤到对应行。
3. 点击「新增服务器」，表单含「业务 IP」字段且必填。提交后列表显示新加的业务 IP。
4. 进入服务器详情，「BMC 接入」卡顶部能看到业务 IP；点编辑后业务 IP 字段被正确回填。
5. `pnpm lint` 通过。
