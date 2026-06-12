import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import {
  Activity,
  AlertTriangle,
  Cpu,
  HardDrive,
  MemoryStickIcon as MemoryIcon,
  Power,
  Radio,
  ScrollText,
  Thermometer,
  Wind,
  Zap,
} from "lucide-react";
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
import { toDate } from "@/lib/time";

interface Props {
  status: BmcStatus;
  loading?: boolean;
  /** Map of drive SN → PartItem info for cross-reference. */
  itemSnMap?: Record<string, { itemId: string; partId: string }>;
}

function SourceBadge({ status }: { status: BmcStatus }) {
  const isLive = status.source === "live";
  const isSnapshot = !!status.lastCollectedAt;
  return (
    <Badge
      variant={isLive ? "default" : "secondary"}
      className={
        isLive
          ? "gap-1 bg-success/15 text-success hover:bg-success/20"
          : "gap-1 bg-warning/15 text-warning hover:bg-warning/20"
      }
    >
      <Radio className={`h-3 w-3 ${isLive && !isSnapshot ? "animate-pulse" : ""}`} />
      {isSnapshot ? "持久快照" : isLive ? "BMC 实时" : "模拟数据"}
      <span className="ml-1 text-[10px] uppercase opacity-70">
        {status.protocol}
      </span>
    </Badge>
  );
}

function healthColor(h: string) {
  if (h === "OK") return "bg-success/10 text-success border-success/30";
  if (h === "Warning") return "bg-warning/10 text-warning border-warning/30";
  return "bg-danger/10 text-danger border-danger/30";
}

/** Format MiB → human-readable (GiB when ≥ 1 GiB, else MiB). */
function formatMemorySize(mib: number): string {
  if (mib >= 1024) return `${(mib / 1024).toFixed(0)} GiB`;
  return `${mib} MiB`;
}

export function BmcLiveCard({ status, loading, itemSnMap }: Props) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {/* ===== Row 1: Overall + CPU/Memory + Chart ===== */}

      <Card className="lg:col-span-1 shadow-card-soft">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4 text-primary" /> 总体状态
            <div className="ml-auto flex items-center gap-2">
              <SourceBadge status={status} />
              {loading && (
                <span className="text-xs text-muted-foreground">刷新中…</span>
              )}
            </div>
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
          <div className="border-t border-border pt-3 text-[11px] text-muted-foreground">
            {status.lastCollectedAt ? (
              <>最近采集：{toDate(status.lastCollectedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</>
            ) : status.source === "live" ? (
              <>实时数据 · {toDate(status.updatedAt).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' })}</>
            ) : (
              <>模拟数据 · {toDate(status.updatedAt).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' })}</>
            )}
          </div>
        </CardContent>
      </Card>

      {/* CPU / Memory — BMC real-time readings, distinct from static asset info */}
      <Card className="lg:col-span-1 shadow-card-soft">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Cpu className="h-4 w-4 text-primary" /> 处理器 / 内存
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {status.processorSummary ? (
            <div className="rounded-lg border border-border bg-muted/40 px-3 py-3">
              <div className="text-xs text-muted-foreground">CPU</div>
              <div className="mt-1 text-sm font-medium text-foreground">
                {status.processorSummary.count}
                <span className="text-muted-foreground">× </span>
                {status.processorSummary.model}
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-border bg-muted/40 px-3 py-3 text-sm text-muted-foreground">
              未获取到 CPU 信息
            </div>
          )}
          {status.memorySummary ? (
            <div className="rounded-lg border border-border bg-muted/40 px-3 py-3">
              <div className="text-xs text-muted-foreground">内存总量</div>
              <div className="mt-1 flex items-baseline gap-1">
                <span className="font-mono text-lg font-medium text-foreground">
                  {status.memorySummary.totalGiB}
                </span>
                <span className="text-sm text-muted-foreground">GiB</span>
                {status.memoryModules && status.memoryModules.length > 0 && (
                  <span className="ml-2 text-xs text-muted-foreground">
                    · {status.memoryModules.length} 根 DIMM
                  </span>
                )}
              </div>
              {status.memorySlots && status.memorySlots.total > 0 && (
                <div className="mt-2 space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>插槽占用</span>
                    <span className="font-mono">
                      {status.memorySlots.populated} / {status.memorySlots.total}
                    </span>
                  </div>
                  <Progress
                    value={(status.memorySlots.populated / status.memorySlots.total) * 100}
                    className="h-1.5"
                  />
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-border bg-muted/40 px-3 py-3 text-sm text-muted-foreground">
              未获取到内存信息
            </div>
          )}
          <div className="text-[11px] text-muted-foreground">
            BMC 实时读取值，可能与静态资产信息存在差异
          </div>
        </CardContent>
      </Card>

      {/* Temperature / power trend */}
      <Card className="lg:col-span-1 shadow-card-soft">
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
                <linearGradient id="powerFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--chart-5))" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="hsl(var(--chart-5))" stopOpacity={0} />
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
              <Area type="monotone" dataKey="power" stroke="hsl(var(--chart-5))" fill="url(#powerFill)" name="功耗 W" />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* ===== Row 2: Disk Drives (full width) ===== */}
      {status.drives && status.drives.length > 0 && (
        <Card className="lg:col-span-3 shadow-card-soft">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <HardDrive className="h-4 w-4 text-primary" /> 硬盘
              <span className="text-xs font-normal text-muted-foreground">
                共 {status.drives.length} 块
              </span>
              {status.diskSlots && status.diskSlots.total > 0 && (
                <>
                  <span className="text-xs font-normal text-muted-foreground">·</span>
                  <span className="text-xs font-normal text-muted-foreground">
                    槽位 {status.diskSlots.populated} / {status.diskSlots.total}
                  </span>
                  <Progress
                    value={(status.diskSlots.populated / status.diskSlots.total) * 100}
                    className="h-1.5 w-20"
                  />
                </>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {status.drives.map((d) => (
                <div
                  key={d.name}
                  className="flex items-center gap-4 px-6 py-3"
                >
                  <span
                    className={
                      "inline-block rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider " +
                      healthColor(d.status)
                    }
                  >
                    {d.status}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-sm font-medium text-foreground">
                        {d.name}
                      </span>
                      <span className="text-xs text-muted-foreground">{d.mediaType}</span>
                      {d.formFactor && d.formFactor !== "unknown" && (
                        <span
                          className={
                            "inline-block rounded border px-1.5 py-0.5 text-[10px] font-medium " +
                            (d.formFactor === "LFF"
                              ? "border-warning/40 bg-warning/10 text-warning"
                              : "border-info/40 bg-info/10 text-info")
                          }
                        >
                          {d.formFactor === "LFF" ? "3.5\"" : "2.5\""}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {d.model}
                      {d.sn && (
                        <span className="ml-2 font-mono text-[10px]">
                          SN:{" "}
                          {itemSnMap?.[d.sn] ? (
                            <Link
                              to={`/inventory/parts/${itemSnMap[d.sn].partId}`}
                              className="text-primary hover:underline"
                            >
                              {d.sn}
                            </Link>
                          ) : (
                            <span className="text-primary">{d.sn}</span>
                          )}
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="text-right font-mono text-sm font-medium text-foreground">
                    {d.capacityGB >= 1000
                      ? `${(d.capacityGB / 1000).toFixed(1)} TB`
                      : `${d.capacityGB} GB`}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ===== Row 3: Memory DIMM Details (full width) ===== */}
      {status.memoryModules && status.memoryModules.length > 0 && (
        <Card className="lg:col-span-3 shadow-card-soft">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <MemoryIcon className="h-4 w-4 text-primary" /> 内存 DIMM
              <span className="text-xs font-normal text-muted-foreground">
                共 {status.memoryModules.length} 根
                {status.memorySummary && (
                  <span className="ml-1">
                    · 合计 {status.memorySummary.totalGiB} GiB
                  </span>
                )}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {status.memoryModules.map((dim) => (
                <div
                  key={dim.slot}
                  className="flex items-center gap-4 px-6 py-3"
                >
                  <span
                    className={
                      "inline-block rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider " +
                      healthColor(dim.status)
                    }
                  >
                    {dim.status}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-sm font-medium text-foreground">
                        {dim.slot}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {dim.memoryType}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {dim.model}
                      {dim.sn && (
                        <span className="ml-2 font-mono text-[10px]">
                          SN:{" "}
                          <span className="text-primary">{dim.sn}</span>
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="text-right font-mono text-sm font-medium text-foreground">
                    {formatMemorySize(dim.capacityMiB)}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ===== Row 4: Fans + PSU ===== */}

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

      {/* ===== Row 5: Recent BMC Logs (full width) ===== */}
      {status.recentLogs && status.recentLogs.length > 0 && (
        <Card className="lg:col-span-3 shadow-card-soft">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <ScrollText className="h-4 w-4 text-info" /> 最近 BMC 日志
              <span className="text-xs font-normal text-muted-foreground">
                共 {status.recentLogs.length} 条
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {status.recentLogs.map((l) => (
                <div key={l.id} className="flex items-start gap-3 px-6 py-3">
                  <span
                    className={
                      "mt-0.5 inline-block rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider " +
                      healthColor(l.severity)
                    }
                  >
                    {l.severity}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-foreground">{l.message}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {l.createdAt ? toDate(l.createdAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : "—"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ===== Row 6: Alerts ===== */}
      {status.alerts.length > 0 && (
        <Card className="lg:col-span-3 shadow-card-soft border-warning/40">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-warning" /> 告警 / 提示
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {status.alerts.map((a) => (
              <div
                key={a.id}
                className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 px-3 py-2"
              >
                <StatusBadge kind="health" value={a.level} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground">{a.message}</p>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {toDate(a.time).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}
                  </p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
