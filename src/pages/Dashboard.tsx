import { useQuery } from "@tanstack/react-query";
import { listServers, listNetworkDevices, listWorkstations, listParts, listMovements, listAuditLogs } from "@/lib/api/cmdb";
import { StatCard } from "@/components/cmdb/StatCard";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import {
  LayoutDashboard,
  Server,
  CheckCircle2,
  AlertTriangle,
  Boxes,
  PackageMinus,
  Router,
  Monitor,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";
import { Link } from "react-router-dom";

const STATUS_COLORS: Record<string, string> = {
  online: "hsl(var(--success))",
  offline: "hsl(var(--danger))",
  maintenance: "hsl(var(--warning))",
  retired: "hsl(var(--muted-foreground))",
};

const CATEGORY_LABELS: Record<string, string> = {
  disk: "硬盘",
  memory: "内存",
  nic: "网卡",
  optical: "光模块",
  other: "其他",
};

export default function Dashboard() {
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers });
  const { data: networkDevices = [] } = useQuery({ queryKey: ["network-devices"], queryFn: listNetworkDevices });
  const { data: workstations = [] } = useQuery({ queryKey: ["workstations"], queryFn: listWorkstations });
  const { data: parts = [] } = useQuery({ queryKey: ["parts"], queryFn: listParts });
  const { data: movements = [] } = useQuery({ queryKey: ["movements"], queryFn: listMovements });
  const { data: auditPage } = useQuery({
    queryKey: ["audit", "dashboard"],
    queryFn: () => listAuditLogs({ limit: 6 }),
  });
  const logs = auditPage?.items ?? [];

  const serverTotal = servers.length;
  const serverOnline = servers.filter((s) => s.status === "online").length;
  const serverAlerts = servers.filter((s) => s.status === "offline" || s.status === "maintenance").length;
  const ndevTotal = networkDevices.length;
  const wsTotal = workstations.length;
  const lowStock = parts.filter((p) => p.stock < p.safetyStock).length;

  const statusData = (["online", "offline", "maintenance", "retired"] as const).map((k) => ({
    name: k,
    label: { online: "在线", offline: "离线", maintenance: "维护", retired: "下架" }[k],
    value: servers.filter((s) => s.status === k).length,
  }));

  const stockData = (["disk", "memory", "nic", "optical", "other"] as const).map((c) => ({
    name: CATEGORY_LABELS[c],
    库存: parts.filter((p) => p.category === c).reduce((acc, p) => acc + p.stock, 0),
    安全库存: parts.filter((p) => p.category === c).reduce((acc, p) => acc + p.safetyStock, 0),
  }));

  const brandData = Object.entries(
    servers.reduce<Record<string, number>>((acc, s) => {
      acc[s.manufacturer] = (acc[s.manufacturer] ?? 0) + 1;
      return acc;
    }, {}),
  )
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
  const BRAND_COLORS = [
    "hsl(var(--chart-1))",
    "hsl(var(--chart-2))",
    "hsl(var(--chart-3))",
    "hsl(var(--chart-4))",
    "hsl(var(--chart-5))",
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="仪表盘"
        description="服务器、网络设备、终端PC 与备件库存全局概览"
        icon={<LayoutDashboard className="h-5 w-5" />}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <StatCard label="服务器" value={serverTotal} delta="主机资产总数" icon={Server} />
        <StatCard label="在线" value={serverOnline} delta={`占比 ${Math.round((serverOnline / Math.max(1, serverTotal)) * 100)}%`} icon={CheckCircle2} tone="success" />
        <StatCard label="告警 / 维护" value={serverAlerts} delta="离线或维护中" icon={AlertTriangle} tone="warning" />
        <StatCard label="网络设备" value={ndevTotal} delta="交换机/路由器等" icon={Router} />
        <StatCard label="终端PC" value={wsTotal} delta="办公电脑/笔记本" icon={Monitor} />
        <StatCard label="库存预警" value={lowStock} delta="低于安全库存的备件" icon={PackageMinus} tone="danger" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">主机状态分布</CardTitle>
          </CardHeader>
          <CardContent className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={statusData} dataKey="value" nameKey="label" innerRadius={50} outerRadius={80} paddingAngle={2}>
                  {statusData.map((entry) => (
                    <Cell key={entry.name} fill={STATUS_COLORS[entry.name]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-base">
              <span>主机品牌分布</span>
              <span className="text-xs font-normal text-muted-foreground">{brandData.length} 个厂商</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={brandData} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 0 }}>
                <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
                <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="value" name="数量" radius={[0, 4, 4, 0]}>
                  {brandData.map((entry, i) => (
                    <Cell key={entry.name} fill={BRAND_COLORS[i % BRAND_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <div>
        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">备件库存 vs 安全库存</CardTitle>
          </CardHeader>
          <CardContent className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stockData} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
                <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
                <YAxis tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="库存" fill="hsl(var(--chart-1))" radius={[4, 4, 0, 0]} />
                <Bar dataKey="安全库存" fill="hsl(var(--chart-4))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Boxes className="h-4 w-4 text-primary" /> 最近出入库记录
            </CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border">
            {movements.slice(0, 5).map((m) => (
              <div key={m.id} className="flex items-center justify-between py-2.5">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <StatusBadge kind="movement" value={m.type} />
                    <span className="truncate text-sm font-medium text-foreground">{m.partModel}</span>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {m.operator} · {m.relatedServerHostname ?? "—"} · {m.reason}
                  </p>
                </div>
                <div className="text-right">
                  <div className="font-mono text-sm font-medium text-foreground">x{m.quantity}</div>
                  <div className="text-[10px] text-muted-foreground">{new Date(m.time).toLocaleString()}</div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-warning" /> 近期审计日志
            </CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border">
            {logs.slice(0, 6).map((l) => (
              <div key={l.id} className="py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className={
                        l.level === "danger"
                          ? "h-2 w-2 rounded-full bg-danger"
                          : l.level === "warn"
                            ? "h-2 w-2 rounded-full bg-warning"
                            : "h-2 w-2 rounded-full bg-info"
                      }
                    />
                    <span className="font-mono text-xs text-muted-foreground">{l.action}</span>
                    <Link to="/audit" className="truncate text-sm font-medium text-foreground hover:text-primary">
                      {l.target}
                    </Link>
                  </div>
                  <span className="whitespace-nowrap text-[10px] text-muted-foreground">
                    {new Date(l.time).toLocaleString()}
                  </span>
                </div>
                <p className="mt-0.5 pl-4 text-xs text-muted-foreground">{l.detail}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
