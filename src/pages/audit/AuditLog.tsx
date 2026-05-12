import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listAuditLogs } from "@/lib/mockApi";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { DataTableToolbar } from "@/components/cmdb/DataTableToolbar";
import { Card } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ScrollText } from "lucide-react";
import { cn } from "@/lib/utils";

const LEVEL: Record<string, string> = {
  info: "bg-info/10 text-info border-info/30",
  warn: "bg-warning/10 text-warning border-warning/30",
  danger: "bg-danger/10 text-danger border-danger/30",
};

export default function AuditLog() {
  const { data: logs = [] } = useQuery({ queryKey: ["audit"], queryFn: listAuditLogs });
  const [search, setSearch] = useState("");
  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase();
    if (!kw) return logs;
    return logs.filter((l) => [l.actor, l.action, l.target, l.detail].join(" ").toLowerCase().includes(kw));
  }, [logs, search]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="操作日志"
        description="平台所有用户操作与系统告警审计"
        icon={<ScrollText className="h-5 w-5" />}
      />
      <Card className="shadow-card-soft">
        <div className="border-b border-border p-4">
          <DataTableToolbar search={search} onSearchChange={setSearch} placeholder="搜索 操作人 / 动作 / 对象 / 描述" />
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间</TableHead>
                <TableHead>级别</TableHead>
                <TableHead>操作人</TableHead>
                <TableHead>动作</TableHead>
                <TableHead>对象</TableHead>
                <TableHead>详情</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && (
                <TableRow><TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">暂无日志</TableCell></TableRow>
              )}
              {filtered.map((l) => (
                <TableRow key={l.id}>
                  <TableCell><span className="text-xs text-muted-foreground">{new Date(l.time).toLocaleString()}</span></TableCell>
                  <TableCell>
                    <span className={cn("inline-block rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider", LEVEL[l.level])}>
                      {l.level}
                    </span>
                  </TableCell>
                  <TableCell><span className="font-mono text-xs">{l.actor}</span></TableCell>
                  <TableCell><span className="font-mono text-xs text-primary">{l.action}</span></TableCell>
                  <TableCell><span className="text-sm">{l.target}</span></TableCell>
                  <TableCell><span className="text-xs text-muted-foreground">{l.detail}</span></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}
