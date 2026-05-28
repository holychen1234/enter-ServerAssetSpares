import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  batchDeleteWorkstations,
  createWorkstation,
  deleteWorkstation,
  listWorkstations,
  updateWorkstation,
} from "@/lib/api/cmdb";
import type { Workstation } from "@/types/cmdb";
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
import { WorkstationForm } from "./WorkstationForm";
import { useAuth } from "@/hooks/use-auth";
import {
  Monitor,
  Plus,
  Pencil,
  Trash2,
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

type SortField = "hostname" | "status" | "os";
type SortOrder = "asc" | "desc";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export default function WorkstationList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin", "operator");

  const { data: workstations = [], isLoading } = useQuery({
    queryKey: ["workstations"],
    queryFn: listWorkstations,
  });

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [osFilter, setOsFilter] = useState<string>("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<Workstation | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toDelete, setToDelete] = useState<Workstation | null>(null);
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const [sortField, setSortField] = useState<SortField>("hostname");
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const osOptions = useMemo(() => {
    return Array.from(new Set(workstations.map((w) => w.os))).sort();
  }, [workstations]);

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase();
    return workstations.filter((w) => {
      if (statusFilter !== "all" && w.status !== statusFilter) return false;
      if (osFilter !== "all" && w.os !== osFilter) return false;
      if (!kw) return true;
      return (
        w.hostname.toLowerCase().includes(kw) ||
        w.sn.toLowerCase().includes(kw) ||
        w.assetTag.toLowerCase().includes(kw) ||
        (w.bizIp && w.bizIp.includes(kw)) ||
        w.model.toLowerCase().includes(kw) ||
        (w.userName && w.userName.toLowerCase().includes(kw)) ||
        (w.department && w.department.toLowerCase().includes(kw)) ||
        w.tags.join(",").toLowerCase().includes(kw)
      );
    });
  }, [workstations, search, statusFilter, osFilter]);

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
        case "os":
          va = a.os;
          vb = b.os;
          break;
      }
      if (va < vb) return sortOrder === "asc" ? -1 : 1;
      if (va > vb) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });
    return arr;
  }, [filtered, sortField, sortOrder]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const effectivePage = Math.min(page, totalPages);
  const paged = useMemo(() => {
    const start = (effectivePage - 1) * pageSize;
    return sorted.slice(start, start + pageSize);
  }, [sorted, effectivePage, pageSize]);

  const mCreate = useMutation({
    mutationFn: createWorkstation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workstations"] });
      toast({ title: "终端PC已新增" });
      setFormOpen(false);
    },
  });
  const mUpdate = useMutation({
    mutationFn: (vars: { id: string; patch: Partial<Workstation> }) =>
      updateWorkstation(vars.id, vars.patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workstations"] });
      toast({ title: "终端PC已更新" });
      setFormOpen(false);
    },
  });
  const mDelete = useMutation({
    mutationFn: deleteWorkstation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workstations"] });
      toast({ title: "终端PC已删除" });
      setToDelete(null);
    },
  });
  const mBatchDelete = useMutation({
    mutationFn: batchDeleteWorkstations,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workstations"] });
      toast({ title: `已删除 ${selectedIds.size} 台终端PC` });
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
      setSelectedIds(new Set(filtered.map((w) => w.id)));
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
        title="终端PC"
        description="管理公司办公电脑、笔记本等终端设备"
        icon={<Monitor className="h-5 w-5" />}
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
                      downloadBlob(blob, `终端PC_${new Date().toISOString().slice(0, 10)}.csv`);
                    }}>
                      导出 CSV
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => {
                      const blob = exportToExcel(filtered);
                      downloadBlob(blob, `终端PC_${new Date().toISOString().slice(0, 10)}.xlsx`);
                    }}>
                      导出 Excel
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button onClick={() => { setEditing(null); setFormOpen(true); }}>
                  <Plus className="mr-1 h-4 w-4" /> 新增PC
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
            placeholder="搜索 计算机名 / SN / 资产编号 / IP / 型号 / 使用人 / 部门"
            filters={
              <>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-[130px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部状态</SelectItem>
                    <SelectItem value="online">在线</SelectItem>
                    <SelectItem value="offline">离线</SelectItem>
                    <SelectItem value="maintenance">维修中</SelectItem>
                    <SelectItem value="retired">已报废</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={osFilter} onValueChange={setOsFilter}>
                  <SelectTrigger className="w-[140px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部系统</SelectItem>
                    {osOptions.map((o) => (
                      <SelectItem key={o} value={o}>{o}</SelectItem>
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
              已选 <span className="font-medium text-foreground">{selectedIds.size}</span> 台终端
            </span>
            <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
              取消选择
            </Button>
            <div className="flex-1" />
            {canEdit && (
              <Button variant="destructive" size="sm" onClick={() => setBatchDeleteOpen(true)}>
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
                    checked={filtered.length > 0 && selectedIds.size === filtered.length}
                    onCheckedChange={toggleSelectAll}
                  />
                </TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort("hostname")}>
                  <span className="inline-flex items-center">
                    计算机名 <SortIcon field="hostname" />
                  </span>
                </TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort("status")}>
                  <span className="inline-flex items-center">
                    状态 <SortIcon field="status" />
                  </span>
                </TableHead>
                <TableHead>厂商 / 型号</TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort("os")}>
                  <span className="inline-flex items-center">
                    操作系统 <SortIcon field="os" />
                  </span>
                </TableHead>
                <TableHead>使用人 / 部门</TableHead>
                <TableHead>IP</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow><TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">加载中…</TableCell></TableRow>
              )}
              {!isLoading && paged.length === 0 && (
                <TableRow><TableCell colSpan={8} className="py-8 text-center text-sm text-muted-foreground">没有匹配的记录</TableCell></TableRow>
              )}
              {paged.map((w) => (
                <TableRow
                  key={w.id}
                  className="cursor-pointer transition-smooth hover:bg-muted/40"
                  onClick={() => navigate(`/workstations/${w.id}`)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(w.id)}
                      onCheckedChange={() => toggleSelect(w.id)}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="font-medium text-foreground">{w.hostname}</span>
                      <span className="font-mono text-xs text-muted-foreground">{w.sn} · {w.assetTag}</span>
                    </div>
                  </TableCell>
                  <TableCell><StatusBadge kind="server" value={w.status} /></TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="text-sm">{w.manufacturer}</span>
                      <span className="text-xs text-muted-foreground">{w.model}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="text-sm">{w.os}</span>
                      {w.osVersion && (
                        <span className="text-xs text-muted-foreground">{w.osVersion}</span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col text-sm">
                      {w.userName && <span>{w.userName}</span>}
                      {w.department && <span className="text-xs text-muted-foreground">{w.department}</span>}
                      {!w.userName && !w.department && <span className="text-muted-foreground">—</span>}
                    </div>
                  </TableCell>
                  <TableCell>
                    {w.bizIp ? (
                      <span className="font-mono text-sm">{w.bizIp}</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        disabled={!canEdit}
                        onClick={() => { setEditing(w); setFormOpen(true); }}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        disabled={!canEdit}
                        onClick={() => setToDelete(w)}
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

        <div className="flex items-center justify-between border-t border-border px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>每页</span>
            <Select value={String(pageSize)} onValueChange={handlePageSizeChange}>
              <SelectTrigger className="h-8 w-[70px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span>条 · 共 {sorted.length} 条记录</span>
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
                if (totalPages <= 7) return true;
                if (p === 1 || p === totalPages) return true;
                return Math.abs(p - effectivePage) <= 1;
              })
              .reduce<(number | "...")[]>((acc, p, i, arr) => {
                if (i > 0) {
                  if (p - arr[i - 1] > 1) acc.push("...");
                }
                acc.push(p);
                return acc;
              }, [])
              .map((p, i) =>
                p === "..." ? (
                  <span key={`ellipsis-${i}`} className="px-1 text-xs text-muted-foreground">…</span>
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

      <WorkstationForm
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
            <AlertDialogTitle>删除终端PC</AlertDialogTitle>
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
            <AlertDialogTitle>批量删除终端PC</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除已选的{" "}
              <span className="font-medium text-foreground">{selectedIds.size}</span>{" "}
              台终端吗？该操作不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={mBatchDelete.isPending}
              onClick={() => mBatchDelete.mutate(Array.from(selectedIds))}
            >
              删除 {selectedIds.size} 台终端
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => queryClient.invalidateQueries({ queryKey: ["workstations"] })}
      />
    </div>
  );
}
