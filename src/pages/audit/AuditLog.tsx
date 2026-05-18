import { useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { listAuditLogs } from "@/lib/api/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  RotateCcw,
  ScrollText,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AuditEntry, AuditFilters } from "@/types/cmdb";

const LEVEL_CLASS: Record<AuditEntry["level"], string> = {
  info: "bg-info/10 text-info border-info/30",
  warn: "bg-warning/10 text-warning border-warning/30",
  danger: "bg-danger/10 text-danger border-danger/30",
};

const ACTION_GROUPS: { label: string; value: string }[] = [
  { label: "全部模块", value: "" },
  { label: "主机", value: "server." },
  { label: "备件", value: "part." },
  { label: "出入库", value: "movement." },
  { label: "用户", value: "user." },
];

const PAGE_SIZE_OPTIONS = [25, 50, 100];

function toCsv(rows: AuditEntry[]): string {
  const header = ["time", "level", "actor", "action", "target", "detail"];
  const escape = (v: string) => {
    if (/[",\n]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
    return v;
  };
  const lines = [header.join(",")];
  for (const r of rows) {
    lines.push(
      [
        new Date(r.time).toISOString(),
        r.level,
        r.actor,
        r.action,
        r.target,
        r.detail,
      ]
        .map((v) => escape(String(v ?? "")))
        .join(","),
    );
  }
  return lines.join("\n");
}

function downloadBlob(filename: string, body: string, mime: string) {
  const blob = new Blob([body], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

interface DraftFilters {
  q: string;
  level: "" | AuditEntry["level"];
  actionGroup: string;
  actor: string;
  start: string;
  end: string;
}

const EMPTY_DRAFT: DraftFilters = {
  q: "",
  level: "",
  actionGroup: "",
  actor: "",
  start: "",
  end: "",
};

export default function AuditLog() {
  // Two layers of state:
  // - `draft`: what the user is typing in the toolbar (controlled inputs)
  // - `applied`: the actual filters used for the query (only updated on
  //   "搜索" or when a Select changes). This avoids spamming the backend.
  const [draft, setDraft] = useState<DraftFilters>(EMPTY_DRAFT);
  const [applied, setApplied] = useState<DraftFilters>(EMPTY_DRAFT);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [active, setActive] = useState<AuditEntry | null>(null);

  const filters: AuditFilters = useMemo(() => {
    const f: AuditFilters = { limit: pageSize, offset: page * pageSize };
    if (applied.q) f.q = applied.q;
    if (applied.level) f.level = applied.level;
    if (applied.actionGroup) f.action = applied.actionGroup;
    if (applied.actor) f.actor = applied.actor;
    if (applied.start) {
      // datetime-local → ISO with local TZ; backend parses fromisoformat
      f.start = new Date(applied.start).toISOString();
    }
    if (applied.end) {
      f.end = new Date(applied.end).toISOString();
    }
    return f;
  }, [applied, page, pageSize]);

  const { data, isFetching, isLoading } = useQuery({
    queryKey: ["audit", filters],
    queryFn: () => listAuditLogs(filters),
    placeholderData: keepPreviousData,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const apply = () => {
    setApplied(draft);
    setPage(0);
  };
  const reset = () => {
    setDraft(EMPTY_DRAFT);
    setApplied(EMPTY_DRAFT);
    setPage(0);
  };
  const exportCsv = async () => {
    // Export the *currently applied* filter set, up to 500 latest matches.
    const all = await listAuditLogs({ ...filters, limit: 500, offset: 0 });
    downloadBlob(
      `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`,
      toCsv(all.items),
      "text/csv;charset=utf-8",
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="操作日志"
        description="平台所有用户操作与系统告警审计 · 支持按模块/级别/时间过滤、CSV 导出"
        icon={<ScrollText className="h-5 w-5" />}
        actions={
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={total === 0}>
            <Download className="mr-1 h-4 w-4" /> 导出 CSV
          </Button>
        }
      />

      <Card className="shadow-card-soft">
        <div className="grid gap-3 border-b border-border p-4 md:grid-cols-6">
          <div className="md:col-span-2">
            <Label className="text-xs font-medium text-muted-foreground">关键词</Label>
            <div className="mt-1.5 flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-8"
                  placeholder="操作人 / 动作 / 对象 / 详情"
                  value={draft.q}
                  onChange={(e) => setDraft({ ...draft, q: e.target.value })}
                  onKeyDown={(e) => e.key === "Enter" && apply()}
                />
              </div>
            </div>
          </div>

          <div>
            <Label className="text-xs font-medium text-muted-foreground">模块</Label>
            <Select
              value={draft.actionGroup || "_all"}
              onValueChange={(v) => {
                const next = { ...draft, actionGroup: v === "_all" ? "" : v };
                setDraft(next);
                setApplied(next);
                setPage(0);
              }}
            >
              <SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger>
              <SelectContent>
                {ACTION_GROUPS.map((g) => (
                  <SelectItem key={g.value || "_all"} value={g.value || "_all"}>
                    {g.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs font-medium text-muted-foreground">级别</Label>
            <Select
              value={draft.level || "_all"}
              onValueChange={(v) => {
                const next = { ...draft, level: v === "_all" ? "" : (v as AuditEntry["level"]) };
                setDraft(next);
                setApplied(next);
                setPage(0);
              }}
            >
              <SelectTrigger className="mt-1.5"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_all">全部级别</SelectItem>
                <SelectItem value="info">Info</SelectItem>
                <SelectItem value="warn">Warn</SelectItem>
                <SelectItem value="danger">Danger</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs font-medium text-muted-foreground">起始时间</Label>
            <Input
              type="datetime-local"
              className="mt-1.5"
              value={draft.start}
              onChange={(e) => setDraft({ ...draft, start: e.target.value })}
            />
          </div>

          <div>
            <Label className="text-xs font-medium text-muted-foreground">截止时间</Label>
            <Input
              type="datetime-local"
              className="mt-1.5"
              value={draft.end}
              onChange={(e) => setDraft({ ...draft, end: e.target.value })}
            />
          </div>

          <div className="flex items-end gap-2 md:col-span-6">
            <Button onClick={apply} size="sm">
              <Search className="mr-1 h-4 w-4" /> 搜索
            </Button>
            <Button variant="outline" size="sm" onClick={reset}>
              <RotateCcw className="mr-1 h-4 w-4" /> 重置
            </Button>
            <span className="ml-auto text-xs text-muted-foreground">
              {isFetching && !isLoading ? "刷新中…" : `共 ${total} 条结果`}
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[180px]">时间</TableHead>
                <TableHead className="w-[80px]">级别</TableHead>
                <TableHead className="w-[120px]">操作人</TableHead>
                <TableHead className="w-[160px]">动作</TableHead>
                <TableHead>对象</TableHead>
                <TableHead>详情</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                    加载中…
                  </TableCell>
                </TableRow>
              )}
              {!isLoading && items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                    无符合条件的日志
                  </TableCell>
                </TableRow>
              )}
              {items.map((l) => (
                <TableRow
                  key={l.id}
                  className="cursor-pointer hover:bg-muted/40"
                  onClick={() => setActive(l)}
                >
                  <TableCell>
                    <span className="text-xs text-muted-foreground">
                      {new Date(l.time).toLocaleString()}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span
                      className={cn(
                        "inline-block rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
                        LEVEL_CLASS[l.level],
                      )}
                    >
                      {l.level}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-xs">{l.actor}</span>
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-xs text-primary">{l.action}</span>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm">{l.target}</span>
                  </TableCell>
                  <TableCell>
                    <span className="line-clamp-1 text-xs text-muted-foreground">
                      {l.detail}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border p-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span>每页</span>
            <Select
              value={String(pageSize)}
              onValueChange={(v) => {
                setPageSize(Number(v));
                setPage(0);
              }}
            >
              <SelectTrigger className="h-7 w-[70px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span>条</span>
          </div>
          <div className="flex items-center gap-2">
            <span>
              第 {page + 1} / {totalPages} 页
            </span>
            <Button
              variant="outline"
              size="icon"
              className="h-7 w-7"
              disabled={page <= 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-7 w-7"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </Card>

      <Sheet open={!!active} onOpenChange={(v) => !v && setActive(null)}>
        <SheetContent className="w-full sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>日志详情</SheetTitle>
            <SheetDescription>单条审计记录的完整字段</SheetDescription>
          </SheetHeader>
          {active && (
            <div className="mt-6 space-y-4 text-sm">
              <DetailRow label="时间" value={new Date(active.time).toLocaleString()} />
              <DetailRow
                label="级别"
                value={
                  <span
                    className={cn(
                      "inline-block rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider",
                      LEVEL_CLASS[active.level],
                    )}
                  >
                    {active.level}
                  </span>
                }
              />
              <DetailRow label="操作人" value={<span className="font-mono">{active.actor}</span>} />
              <DetailRow
                label="动作"
                value={<span className="font-mono text-primary">{active.action}</span>}
              />
              <DetailRow label="对象" value={active.target} />
              <div>
                <p className="text-xs text-muted-foreground">详情</p>
                <pre className="mt-1 whitespace-pre-wrap break-words rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">
                  {active.detail || "—"}
                </pre>
              </div>
              <DetailRow label="日志 ID" value={<span className="font-mono text-[11px]">{active.id}</span>} />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border pb-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right text-foreground">{value}</span>
    </div>
  );
}
