import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  batchDeleteServers,
  createServer,
  deleteServer,
  listServers,
  updateServer,
} from "@/lib/api/cmdb";
import type { Server } from "@/types/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { DataTableToolbar } from "@/components/cmdb/DataTableToolbar";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import { ImportDialog } from "@/components/cmdb/ImportDialog";
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
import { Checkbox } from "@/components/ui/checkbox";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ServerForm } from "./ServerForm";
import { useAuth } from "@/hooks/use-auth";
import {
  Server as ServerIcon,
  Plus,
  Pencil,
  Trash2,
  Monitor,
  Download,
  Upload,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { toast } from "@/hooks/use-toast";
import { exportToCsv, exportToExcel, downloadBlob } from "@/lib/import-export";

type SortField = "hostname" | "status" | "manufacturer";
type SortOrder = "asc" | "desc";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

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
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<Server | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toDelete, setToDelete] = useState<Server | null>(null);
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const [sortField, setSortField] = useState<SortField>("hostname");
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

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

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      let va = "";
      let vb = "";
      switch (sortField) {
        case "hostname":
          va = a.hostname.toLowerCase();
          vb = b.hostname.toLowerCase();
          break;
        case "status":
          va = a.status;
          vb = b.status;
          break;
        case "manufacturer":
          va = a.manufacturer.toLowerCase();
          vb = b.manufacturer.toLowerCase();
          break;
      }
      if (va < vb) return sortOrder === "asc" ? -1 : 1;
      if (va > vb) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });
    return arr;
  }, [filtered, sortField, sortOrder]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));

  // Reset page to 1 when filters or sort change
  const effectivePage = Math.min(page, totalPages);
  const paged = useMemo(() => {
    const start = (effectivePage - 1) * pageSize;
    return sorted.slice(start, start + pageSize);
  }, [sorted, effectivePage, pageSize]);

  const mCreate = useMutation({
    mutationFn: createServer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["servers"] });
      toast({ title: "主机已新增" });
      setFormOpen(false);
    },
  });
  const mUpdate = useMutation({
    mutationFn: (vars: { id: string; patch: Partial<Server> }) =>
      updateServer(vars.id, vars.patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["servers"] });
      toast({ title: "主机已更新" });
      setFormOpen(false);
    },
  });
  const mDelete = useMutation({
    mutationFn: deleteServer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["servers"] });
      toast({ title: "主机已删除" });
      setToDelete(null);
    },
  });
  const mBatchDelete = useMutation({
    mutationFn: batchDeleteServers,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["servers"] });
      toast({ title: `已删除 ${selectedIds.size} 台主机` });
      setSelectedIds(new Set());
      setBatchDeleteOpen(false);
    },
    onError: (err: Error) => {
      toast({ title: "批量删除失败", description: err.message, variant: "destructive" });
    },
  });

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filtered.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filtered.map((s) => s.id)));
    }
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortOrder("asc");
    }
    setPage(1);
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field)
      return <ArrowUpDown className="ml-1 h-3 w-3 text-muted-foreground/40" />;
    if (sortOrder === "asc")
      return <ArrowUp className="ml-1 h-3 w-3 text-primary" />;
    return <ArrowDown className="ml-1 h-3 w-3 text-primary" />;
  };

  const handlePageSizeChange = (v: string) => {
    setPageSize(Number(v));
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="主机资产"
        description="管理公司全部主机，支持搜索、过滤、增删改查"
        icon={<ServerIcon className="h-5 w-5" />}
        actions={
          <div className="flex gap-2">
            {canEdit && (
              <>
                <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                  <Upload className="mr-1 h-4 w-4" /> 导入
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm">
                      <Download className="mr-1 h-4 w-4" /> 导出
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => {
                      const blob = exportToCsv(filtered);
                      downloadBlob(blob, `主机资产_${new Date().toISOString().slice(0, 10)}.csv`);
                    }}>
                      导出 CSV
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => {
                      const blob = exportToExcel(filtered);
                      downloadBlob(blob, `主机资产_${new Date().toISOString().slice(0, 10)}.xlsx`);
                    }}>
                      导出 Excel
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button onClick={() => { setEditing(null); setFormOpen(true); }}>
                  <Plus className="mr-1 h-4 w-4" /> 新增主机
                </Button>
              </>
            )}
          </div>
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

        {selectedIds.size > 0 && (
          <div className="flex items-center gap-3 border-b border-border bg-muted/40 px-4 py-2">
            <span className="text-sm text-muted-foreground">
              已选 <span className="font-medium text-foreground">{selectedIds.size}</span> 台主机
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedIds(new Set())}
            >
              取消选择
            </Button>
            <div className="flex-1" />
            {canEdit && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setBatchDeleteOpen(true)}
              >
                <Trash2 className="mr-1 h-4 w-4" />
                批量删除
              </Button>
            )}
          </div>
        )}

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    checked={
                      filtered.length > 0 &&
                      selectedIds.size === filtered.length
                    }
                    onCheckedChange={toggleSelectAll}
                  />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none"
                  onClick={() => handleSort("hostname")}
                >
                  <span className="inline-flex items-center">
                    主机名 <SortIcon field="hostname" />
                  </span>
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none"
                  onClick={() => handleSort("status")}
                >
                  <span className="inline-flex items-center">
                    状态 <SortIcon field="status" />
                  </span>
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none"
                  onClick={() => handleSort("manufacturer")}
                >
                  <span className="inline-flex items-center">
                    厂商 / 型号 <SortIcon field="manufacturer" />
                  </span>
                </TableHead>
                <TableHead>位置</TableHead>
                <TableHead>IP 地址</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow><TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">加载中…</TableCell></TableRow>
              )}
              {!isLoading && paged.length === 0 && (
                <TableRow><TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">没有匹配的记录</TableCell></TableRow>
              )}
              {paged.map((s) => (
                <TableRow
                  key={s.id}
                  className="cursor-pointer transition-smooth hover:bg-muted/40"
                  onClick={() => navigate(`/servers/${s.id}`)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(s.id)}
                      onCheckedChange={() => toggleSelect(s.id)}
                    />
                  </TableCell>
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
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-muted-foreground">管理</span>
                        <span className="font-mono text-xs text-muted-foreground">{s.mgmtIp}</span>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-1">
                      {s.mgmtIp && (
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => window.open(`https://${s.mgmtIp}`, "_blank", "noopener,noreferrer")}
                          title="带外控制台"
                        >
                          <Monitor className="h-4 w-4" />
                        </Button>
                      )}
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

        {/* Pagination */}
        <div className="flex items-center justify-between border-t border-border px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>每页</span>
            <Select value={String(pageSize)} onValueChange={handlePageSizeChange}>
              <SelectTrigger className="h-8 w-[70px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span>
              条 · 共 {sorted.length} 条记录
            </span>
          </div>

          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              disabled={effectivePage <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>

            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => {
                // Show first, last, and pages around current
                if (totalPages <= 7) return true;
                if (p === 1 || p === totalPages) return true;
                if (Math.abs(p - effectivePage) <= 1) return true;
                return false;
              })
              .reduce<(number | "...")[]>((acc, p, i, arr) => {
                if (i > 0) {
                  const prev = arr[i - 1];
                  if (p - prev > 1) acc.push("...");
                }
                acc.push(p);
                return acc;
              }, [])
              .map((p, i) =>
                p === "..." ? (
                  <span key={`ellipsis-${i}`} className="px-1 text-xs text-muted-foreground">
                    …
                  </span>
                ) : (
                  <Button
                    key={p}
                    variant={p === effectivePage ? "default" : "outline"}
                    size="icon"
                    className="h-8 w-8 text-xs"
                    onClick={() => setPage(p)}
                  >
                    {p}
                  </Button>
                ),
              )}

            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              disabled={effectivePage >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
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
            <AlertDialogTitle>删除主机</AlertDialogTitle>
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

      <AlertDialog open={batchDeleteOpen} onOpenChange={(v) => !v && setBatchDeleteOpen(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>批量删除主机</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除已选的{" "}
              <span className="font-medium text-foreground">{selectedIds.size}</span>{" "}
              台主机吗？该操作不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={mBatchDelete.isPending}
              onClick={() => mBatchDelete.mutate(Array.from(selectedIds))}
            >
              删除 {selectedIds.size} 台主机
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => queryClient.invalidateQueries({ queryKey: ["servers"] })}
      />
    </div>
  );
}
