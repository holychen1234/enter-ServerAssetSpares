import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createMovement,
  createPart,
  deletePart,
  listParts,
  listServers,
  listWorkstations,
  updatePart,
} from "@/lib/api/cmdb";
import type { Part, PartCategory } from "@/types/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { DataTableToolbar } from "@/components/cmdb/DataTableToolbar";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Boxes, Plus, Pencil, Trash2, AlertTriangle, ArrowDownToLine, ArrowUpFromLine } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useAuth } from "@/hooks/use-auth";
import { PartForm } from "./PartForm";
import { MovementForm } from "./MovementForm";
import { toast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

const CATEGORY_LABEL: Record<PartCategory | "all", string> = {
  all: "全部",
  disk: "硬盘",
  memory: "内存",
  nic: "网卡",
  optical: "光模块",
  other: "其他",
};

export default function PartList() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { hasRole } = useAuth();
  const canEdit = hasRole("admin", "operator");

  const { data: parts = [], isLoading } = useQuery({ queryKey: ["parts"], queryFn: listParts });
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers });
  const { data: workstations = [] } = useQuery({ queryKey: ["workstations"], queryFn: listWorkstations });

  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<PartCategory | "all">("all");
  const [editing, setEditing] = useState<Part | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toDelete, setToDelete] = useState<Part | null>(null);
  const [mvOpen, setMvOpen] = useState(false);
  const [mvType, setMvType] = useState<"inbound" | "outbound">("inbound");

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase();
    return parts.filter((p) => {
      if (tab !== "all" && p.category !== tab) return false;
      if (!kw) return true;
      return [p.brand, p.model, p.spec, p.location, p.sn ?? ""].join(" ").toLowerCase().includes(kw);
    });
  }, [parts, search, tab]);

  const mCreate = useMutation({
    mutationFn: createPart,
    onSuccess: (data: Part) => {
      qc.invalidateQueries({ queryKey: ["parts"] });
      toast({ title: "备件已新增，请添加单件" });
      setFormOpen(false);
      navigate(`/inventory/parts/${data.id}`);
    },
  });
  const mUpdate = useMutation({
    mutationFn: (v: { id: string; patch: Partial<Part> }) => updatePart(v.id, v.patch),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["parts"] }); toast({ title: "备件已更新" }); setFormOpen(false); },
  });
  const mDelete = useMutation({
    mutationFn: deletePart,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["parts"] }); toast({ title: "已删除" }); setToDelete(null); },
  });
  const mMove = useMutation({
    mutationFn: createMovement,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["parts"] });
      qc.invalidateQueries({ queryKey: ["movements"] });
      toast({ title: "出入库记录已提交" });
      setMvOpen(false);
    },
    onError: (e) => toast({ title: "提交失败", description: e instanceof Error ? e.message : "", variant: "destructive" }),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="备件耗材"
        description="管理硬盘、内存、网卡、光模块等备件，支持出入库与领用"
        icon={<Boxes className="h-5 w-5" />}
        actions={
          canEdit && (
            <>
              <Button variant="outline" onClick={() => { setMvType("inbound"); setMvOpen(true); }}>
                <ArrowDownToLine className="mr-1 h-4 w-4" /> 入库
              </Button>
              <Button variant="outline" onClick={() => { setMvType("outbound"); setMvOpen(true); }}>
                <ArrowUpFromLine className="mr-1 h-4 w-4" /> 出库
              </Button>
              <Button onClick={() => { setEditing(null); setFormOpen(true); }}>
                <Plus className="mr-1 h-4 w-4" /> 新增备件
              </Button>
            </>
          )
        }
      />

      <Card className="shadow-card-soft">
        <div className="border-b border-border p-4">
          <Tabs value={tab} onValueChange={(v) => setTab(v as PartCategory | "all")}>
            <TabsList>
              {(Object.keys(CATEGORY_LABEL) as Array<PartCategory | "all">).map((k) => (
                <TabsTrigger key={k} value={k}>{CATEGORY_LABEL[k]}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
        <div className="border-b border-border p-4">
          <DataTableToolbar
            search={search}
            onSearchChange={setSearch}
            placeholder="搜索 品牌 / 型号 / 规格 / 位置"
          />
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>类别</TableHead>
                <TableHead>品牌 / 型号</TableHead>
                <TableHead>规格</TableHead>
                <TableHead>库存</TableHead>
                <TableHead>位置</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow><TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">加载中…</TableCell></TableRow>
              )}
              {!isLoading && filtered.length === 0 && (
                <TableRow><TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">没有匹配的备件</TableCell></TableRow>
              )}
              {filtered.map((p) => {
                const low = p.stock < p.safetyStock;
                return (
                  <TableRow
                    key={p.id}
                    className={cn("cursor-pointer transition-smooth hover:bg-muted/40", low && "bg-danger/5")}
                    onClick={() => navigate(`/inventory/parts/${p.id}`)}
                  >
                    <TableCell><span className="text-sm">{CATEGORY_LABEL[p.category]}</span></TableCell>
                    <TableCell>
                      <div>
                        <div className="font-medium text-foreground">{p.brand} {p.model}</div>
                        {p.sn && <div className="font-mono text-[10px] text-muted-foreground">SN: {p.sn}</div>}
                      </div>
                    </TableCell>
                    <TableCell><span className="text-sm text-muted-foreground">{p.spec}</span></TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className={cn("font-mono text-base font-semibold", low ? "text-danger" : "text-foreground")}>
                          {p.stock}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {p.itemCount > 0 ? (
                            <>{p.itemCount}件 (在库{p.statusCounts.in_stock || 0}, 在用{p.statusCounts.in_use || 0}, 报废{p.statusCounts.scrapped || 0})</>
                          ) : (
                            <>/ {p.safetyStock} {p.unit}</>
                          )}
                        </span>
                        {low && <AlertTriangle className="h-4 w-4 text-danger" />}
                      </div>
                    </TableCell>
                    <TableCell><span className="text-xs text-muted-foreground">{p.location}</span></TableCell>
                    <TableCell><StatusBadge kind="part" value={p.status} /></TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        <Button size="icon" variant="ghost" disabled={!canEdit}
                          onClick={() => { setEditing(p); setFormOpen(true); }}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button size="icon" variant="ghost" disabled={!canEdit}
                          onClick={() => setToDelete(p)}>
                          <Trash2 className="h-4 w-4 text-danger" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Card>

      <PartForm
        open={formOpen}
        initial={editing}
        onClose={() => setFormOpen(false)}
        onSubmit={async (data) => {
          if (editing) await mUpdate.mutateAsync({ id: editing.id, patch: data });
          else await mCreate.mutateAsync(data);
        }}
      />

      <MovementForm
        open={mvOpen}
        defaultType={mvType}
        parts={parts}
        servers={servers}
        workstations={workstations}
        onClose={() => setMvOpen(false)}
        onSubmit={(d) => mMove.mutateAsync(d)}
      />

      <AlertDialog open={!!toDelete} onOpenChange={(v) => !v && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除备件</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除 <span className="font-mono text-foreground">{toDelete?.brand} {toDelete?.model}</span> 吗？
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
