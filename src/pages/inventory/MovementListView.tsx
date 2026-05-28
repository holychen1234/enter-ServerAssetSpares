import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createMovement, listMovements, listParts, listServers, listWorkstations } from "@/lib/api/cmdb";
import type { MovementType } from "@/types/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { DataTableToolbar } from "@/components/cmdb/DataTableToolbar";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Plus } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { MovementForm } from "./MovementForm";
import { toast } from "@/hooks/use-toast";
import { Link } from "react-router-dom";

interface Props {
  type: MovementType | "all";
  title: string;
  description: string;
  defaultMvType: MovementType;
  icon: React.ReactNode;
  allowTypes?: MovementType[];
}

export function MovementListView({ type, title, description, defaultMvType, icon }: Props) {
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin", "operator");
  const { data: movements = [] } = useQuery({ queryKey: ["movements"], queryFn: listMovements });
  const { data: parts = [] } = useQuery({ queryKey: ["parts"], queryFn: listParts });
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers });
  const { data: workstations = [] } = useQuery({ queryKey: ["workstations"], queryFn: listWorkstations });

  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);

  const list = useMemo(() => {
    const kw = search.trim().toLowerCase();
    return movements
      .filter((m) => (type === "all" ? true : type === "outbound" ? (m.type === "outbound" || m.type === "scrap") : m.type === type))
      .filter((m) => !kw || [m.partModel, m.operator, m.reason, m.relatedServerHostname ?? ""].join(" ").toLowerCase().includes(kw));
  }, [movements, type, search]);

  const mMove = useMutation({
    mutationFn: createMovement,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["movements"] });
      qc.invalidateQueries({ queryKey: ["parts"] });
      toast({ title: "记录已提交" });
      setOpen(false);
    },
    onError: (e) => toast({ title: "失败", description: e instanceof Error ? e.message : "", variant: "destructive" }),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        description={description}
        icon={icon}
        actions={
          canEdit && (
            <Button onClick={() => setOpen(true)}>
              <Plus className="mr-1 h-4 w-4" /> 新建记录
            </Button>
          )
        }
      />
      <Card className="shadow-card-soft">
        <div className="border-b border-border p-4">
          <DataTableToolbar search={search} onSearchChange={setSearch} placeholder="搜索 备件 / 操作人 / 服务器 / 原因" />
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间</TableHead>
                <TableHead>类型</TableHead>
                <TableHead>备件</TableHead>
                <TableHead>数量</TableHead>
                <TableHead>关联服务器</TableHead>
                <TableHead>操作人</TableHead>
                <TableHead>原因</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.length === 0 && (
                <TableRow><TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">暂无记录</TableCell></TableRow>
              )}
              {list.map((m) => (
                <TableRow key={m.id}>
                  <TableCell><span className="text-xs text-muted-foreground">{new Date(m.time).toLocaleString()}</span></TableCell>
                  <TableCell><StatusBadge kind="movement" value={m.type} /></TableCell>
                  <TableCell>
                    <Link to={`/inventory/parts/${m.partId}`} className="text-sm font-medium hover:text-primary">
                      {m.partModel}
                    </Link>
                  </TableCell>
                  <TableCell><span className="font-mono text-sm">x{m.quantity}</span></TableCell>
                  <TableCell>
                    {m.relatedServerHostname ? (
                      <Link to={`/servers/${m.relatedServerId}`} className="font-mono text-xs hover:text-primary">
                        {m.relatedServerHostname}
                      </Link>
                    ) : <span className="text-xs text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell><span className="text-xs">{m.operator}</span></TableCell>
                  <TableCell><span className="text-xs text-muted-foreground">{m.reason}</span></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      <MovementForm
        open={open}
        defaultType={defaultMvType}
        parts={parts}
        servers={servers}
        workstations={workstations}
        onClose={() => setOpen(false)}
        onSubmit={(d) => mMove.mutateAsync(d)}
      />
    </div>
  );
}
