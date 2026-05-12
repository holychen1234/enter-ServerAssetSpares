import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createServer,
  deleteServer,
  listServers,
  updateServer,
} from "@/lib/mockApi";
import type { Server } from "@/types/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { DataTableToolbar } from "@/components/cmdb/DataTableToolbar";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ServerForm } from "./ServerForm";
import { useAuth } from "@/hooks/use-auth";
import { Server as ServerIcon, Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "@/hooks/use-toast";

export default function ServerList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin", "operator");

  const { data: servers = [], isLoading } = useQuery({
    queryKey: ["servers"],
    queryFn: listServers,
  });

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [idcFilter, setIdcFilter] = useState<string>("all");
  const [editing, setEditing] = useState<Server | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toDelete, setToDelete] = useState<Server | null>(null);

  const idcOptions = useMemo(() => {
    return Array.from(new Set(servers.map((s) => s.location.idc))).sort();
  }, [servers]);

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase();
    return servers.filter((s) => {
      if (statusFilter !== "all" && s.status !== statusFilter) return false;
      if (idcFilter !== "all" && s.location.idc !== idcFilter) return false;
      if (!kw) return true;
      return (
        s.hostname.toLowerCase().includes(kw) ||
        s.sn.toLowerCase().includes(kw) ||
        s.assetTag.toLowerCase().includes(kw) ||
        s.mgmtIp.includes(kw) ||
        s.bizIp.includes(kw) ||
        s.model.toLowerCase().includes(kw) ||
        s.tags.join(",").toLowerCase().includes(kw)
      );
    });
  }, [servers, search, statusFilter, idcFilter]);

  const mCreate = useMutation({
    mutationFn: createServer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["servers"] });
      toast({ title: "服务器已新增" });
      setFormOpen(false);
    },
  });
  const mUpdate = useMutation({
    mutationFn: (vars: { id: string; patch: Partial<Server> }) =>
      updateServer(vars.id, vars.patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["servers"] });
      toast({ title: "服务器已更新" });
      setFormOpen(false);
    },
  });
  const mDelete = useMutation({
    mutationFn: deleteServer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["servers"] });
      toast({ title: "服务器已删除" });
      setToDelete(null);
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="服务器资产"
        description="管理公司全部服务器，支持搜索、过滤、增删改查"
        icon={<ServerIcon className="h-5 w-5" />}
        actions={
          canEdit && (
            <Button onClick={() => { setEditing(null); setFormOpen(true); }}>
              <Plus className="mr-1 h-4 w-4" /> 新增服务器
            </Button>
          )
        }
      />

      <Card className="shadow-card-soft">
        <div className="border-b border-border p-4">
          <DataTableToolbar
            search={search}
            onSearchChange={setSearch}
            placeholder="搜索 主机名 / SN / 资产编号 / 业务 IP / BMC IP / 型号 / 标签"
            filters={
              <>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-[140px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部状态</SelectItem>
                    <SelectItem value="online">在线</SelectItem>
                    <SelectItem value="offline">离线</SelectItem>
                    <SelectItem value="maintenance">维护中</SelectItem>
                    <SelectItem value="retired">已下架</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={idcFilter} onValueChange={setIdcFilter}>
                  <SelectTrigger className="w-[140px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部 IDC</SelectItem>
                    {idcOptions.map((i) => (
                      <SelectItem key={i} value={i}>{i}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </>
            }
          />
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>主机名</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>厂商 / 型号</TableHead>
                <TableHead>位置</TableHead>
                <TableHead>IP 地址</TableHead>
                <TableHead>规格</TableHead>
                <TableHead>负责人</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow><TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">加载中…</TableCell></TableRow>
              )}
              {!isLoading && filtered.length === 0 && (
                <TableRow><TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">没有匹配的记录</TableCell></TableRow>
              )}
              {filtered.map((s) => (
                <TableRow
                  key={s.id}
                  className="cursor-pointer transition-smooth hover:bg-muted/40"
                  onClick={() => navigate(`/servers/${s.id}`)}
                >
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="font-medium text-foreground">{s.hostname}</span>
                      <span className="font-mono text-xs text-muted-foreground">{s.sn} · {s.assetTag}</span>
                    </div>
                  </TableCell>
                  <TableCell><StatusBadge kind="server" value={s.status} /></TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="text-sm">{s.manufacturer}</span>
                      <span className="text-xs text-muted-foreground">{s.model}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col text-sm">
                      <span>{s.location.idc}</span>
                      <span className="text-xs text-muted-foreground">{s.location.rack} · {s.location.uPosition}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-1.5">
                        <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-primary">业务</span>
                        <span className="font-mono text-sm">{s.bizIp}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-muted-foreground">{s.bmcProtocol}</span>
                        <span className="font-mono text-xs text-muted-foreground">{s.mgmtIp}</span>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="text-xs text-muted-foreground">
                      {s.cpuCount}× CPU · {s.memoryGB}GB · {s.diskCount} 盘
                    </span>
                  </TableCell>
                  <TableCell><span className="text-xs">{s.owner}</span></TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        disabled={!canEdit}
                        onClick={() => { setEditing(s); setFormOpen(true); }}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        disabled={!canEdit}
                        onClick={() => setToDelete(s)}
                      >
                        <Trash2 className="h-4 w-4 text-danger" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      <ServerForm
        open={formOpen}
        initial={editing}
        onClose={() => setFormOpen(false)}
        onSubmit={async (data) => {
          if (editing) {
            await mUpdate.mutateAsync({ id: editing.id, patch: data });
          } else {
            await mCreate.mutateAsync(data);
          }
        }}
      />

      <AlertDialog open={!!toDelete} onOpenChange={(v) => !v && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除服务器</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除 <span className="font-mono text-foreground">{toDelete?.hostname}</span> 吗？该操作不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger text-danger-foreground hover:bg-danger/90"
              onClick={() => toDelete && mDelete.mutate(toDelete.id)}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
