import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import { Activity, Power, Thermometer, Wind, Zap } from "lucide-react";
import type { BmcStatus } from "@/types/cmdb";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Props {
  status: BmcStatus;
  loading?: boolean;
}

export function BmcLiveCard({ status, loading }: Props) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-1 shadow-card-soft">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4 text-primary" /> 总体状态
            {loading && <span className="ml-auto text-xs text-muted-foreground">刷新中…</span>}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">健康</span>
            <StatusBadge kind="health" value={status.health} pulse />
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm text-muted-foreground">
              <Power className="h-4 w-4" /> 电源
            </span>
            <span className="text-sm font-medium text-foreground">{status.power}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">引导阶段</span>
            <span className="font-mono text-xs text-foreground">{status.bootProgress}</span>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-muted-foreground">
                <Thermometer className="h-4 w-4" /> CPU 温度
              </span>
              <span className="font-mono font-medium text-foreground">{status.cpuTempC}°C</span>
            </div>
            <Progress value={Math.min(100, status.cpuTempC)} className="h-2" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-muted-foreground">
                <Thermometer className="h-4 w-4" /> 进风温度
              </span>
              <span className="font-mono font-medium text-foreground">{status.inletTempC}°C</span>
            </div>
            <Progress value={Math.min(100, status.inletTempC * 2)} className="h-2" />
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2 shadow-card-soft">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">指标趋势（近 60 分钟）</CardTitle>
        </CardHeader>
        <CardContent className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={status.history} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
              <defs>
                <linearGradient id="cpuFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="inletFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--chart-3))" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="hsl(var(--chart-3))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
              <XAxis dataKey="t" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
              <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--popover))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Area type="monotone" dataKey="cpu" stroke="hsl(var(--chart-1))" fill="url(#cpuFill)" name="CPU°C" />
              <Area type="monotone" dataKey="inlet" stroke="hsl(var(--chart-3))" fill="url(#inletFill)" name="进风°C" />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2 shadow-card-soft">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Wind className="h-4 w-4 text-info" /> 风扇
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {status.fans.map((f) => (
              <div key={f.name} className="rounded-lg border border-border bg-muted/40 px-3 py-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{f.name}</span>
                  <StatusBadge kind="health" value={f.status} />
                </div>
                <p className="mt-1 font-mono text-lg font-medium text-foreground">{f.rpm}<span className="ml-1 text-xs text-muted-foreground">rpm</span></p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-1 shadow-card-soft">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Zap className="h-4 w-4 text-warning" /> 电源
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {status.psus.map((p) => (
            <div key={p.name} className="rounded-lg border border-border bg-muted/40 px-3 py-2">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{p.name}</span>
                <StatusBadge kind="health" value={p.status} />
              </div>
              <div className="mt-1 flex items-baseline gap-1">
                <span className="font-mono text-lg font-medium text-foreground">{p.watts}</span>
                <span className="text-xs text-muted-foreground">W / {p.capacityW}W</span>
              </div>
              <Progress value={(p.watts / p.capacityW) * 100} className="mt-2 h-1.5" />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
