import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getPart,
  listMovements,
  listPartItems,
  createPartItems,
  updatePartItem,
  deletePartItem,
} from "@/lib/api/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import {
  ArrowLeft,
  Boxes,
  AlertTriangle,
  Plus,
  Trash2,
  Check,
  X,
  Search,
} from "lucide-react";
import type { PartItem } from "@/types/cmdb";
import { useToast } from "@/hooks/use-toast";

const CATEGORY_LABEL: Record<string, string> = {
  disk: "硬盘",
  memory: "内存",
  nic: "网卡",
  optical: "光模块",
  other: "其他",
};

export default function PartDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const { data: part, isLoading } = useQuery({
    queryKey: ["part", id],
    queryFn: () => getPart(id),
    enabled: !!id,
  });
  const { data: movements = [] } = useQuery({
    queryKey: ["movements"],
    queryFn: listMovements,
  });
  const { data: items = [] } = useQuery({
    queryKey: ["part-items", id],
    queryFn: () => listPartItems(id),
    enabled: !!id,
  });

  // multi-item add dialog
  const [addOpen, setAddOpen] = useState(false);
  const [newSns, setNewSns] = useState("");

  const mAdd = useMutation({
    mutationFn: () => {
      const sns = newSns
        .split(/[\n,]/)
        .map((s) => s.trim())
        .filter(Boolean);
      return createPartItems(
        id,
        sns.map((sn) => ({ sn: sn || undefined })),
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["part-items", id] });
      queryClient.invalidateQueries({ queryKey: ["part", id] });
      queryClient.invalidateQueries({ queryKey: ["parts"] });
      setNewSns("");
      setAddOpen(false);
      toast({ title: "单件添加成功" });
    },
    onError: (err: Error) => {
      toast({ title: "添加失败", description: err.message, variant: "destructive" });
    },
  });

  const mUpdate = useMutation({
    mutationFn: ({
      itemId,
      patch,
    }: {
      itemId: string;
      patch: Partial<PartItem>;
    }) => updatePartItem(itemId, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["part-items", id] });
      queryClient.invalidateQueries({ queryKey: ["part", id] });
      queryClient.invalidateQueries({ queryKey: ["parts"] });
    },
    onError: (err: Error) => {
      toast({
        title: "更新失败",
        description: err.message,
        variant: "destructive",
      });
    },
  });

  const mDelete = useMutation({
    mutationFn: (itemId: string) => deletePartItem(itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["part-items", id] });
      queryClient.invalidateQueries({ queryKey: ["part", id] });
      queryClient.invalidateQueries({ queryKey: ["parts"] });
      toast({ title: "单件已删除" });
    },
    onError: (err: Error) => {
      toast({ title: "删除失败", description: err.message, variant: "destructive" });
    },
  });

  const related = movements.filter((m) => m.partId === id);

  // count items by status
  const inStock = items.filter((it) => it.status === "in_stock").length;
  const inUse = items.filter((it) => it.status === "in_use").length;
  const allocated = items.filter((it) => it.status === "allocated").length;
  const scrapped = items.filter((it) => it.status === "scrapped").length;

  if (isLoading)
    return <div className="text-sm text-muted-foreground">加载中…</div>;
  if (!part) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ArrowLeft className="mr-1 h-4 w-4" /> 返回
        </Button>
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            备件不存在
          </CardContent>
        </Card>
      </div>
    );
  }

  const low = part.stock < part.safetyStock;

  return (
    <div className="space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate("/inventory/parts")}
      >
        <ArrowLeft className="mr-1 h-4 w-4" /> 返回备件列表
      </Button>

      <PageHeader
        title={`${part.brand} ${part.model}`}
        description={`${CATEGORY_LABEL[part.category]} · ${part.spec}`}
        icon={<Boxes className="h-5 w-5" />}
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge kind="part" value={part.status} />
            <Button size="sm" onClick={() => setAddOpen(true)}>
              <Plus className="mr-1 h-4 w-4" /> 添加单件
            </Button>
          </div>
        }
      />

      {/* stats cards */}
      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">在库</CardTitle>
          </CardHeader>
          <CardContent>
            <span className="font-mono text-4xl font-semibold text-foreground">
              {inStock}
            </span>
            <span className="ml-1 text-sm text-muted-foreground">
              / 共 {items.length} 件
            </span>
            {low && (
              <div className="mt-1 flex items-center gap-1 text-xs text-danger">
                <AlertTriangle className="h-3 w-3" /> 库存预警 (安全库存{" "}
                {part.safetyStock})
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">使用中</CardTitle>
          </CardHeader>
          <CardContent>
            <span className="font-mono text-4xl font-semibold text-primary">
              {inUse}
            </span>
          </CardContent>
        </Card>
        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">已分配</CardTitle>
          </CardHeader>
          <CardContent>
            <span className="font-mono text-4xl font-semibold text-amber-500">
              {allocated}
            </span>
          </CardContent>
        </Card>
        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">报废</CardTitle>
          </CardHeader>
          <CardContent>
            <span className="font-mono text-4xl font-semibold text-muted-foreground">
              {scrapped}
            </span>
          </CardContent>
        </Card>

        <Card className="shadow-card-soft">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">基本信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <Inf label="品牌" value={part.brand} />
            <Inf label="型号" value={part.model} />
            <Inf label="规格" value={part.spec} />
            <Inf label="位置" value={part.location} />
            <Inf label="单位" value={part.unit} />
          </CardContent>
        </Card>
      </div>

      {/* add item mini dialog */}
      {addOpen && (
        <Card className="shadow-card-soft border-primary/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">添加单件</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground">
                SN 序列号（每行一个，或用逗号分隔）
              </label>
              <textarea
                className="mt-1 w-full rounded border border-input bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
                rows={5}
                placeholder="WD-abc123&#10;WD-def456&#10;WD-ghi789"
                value={newSns}
                onChange={(e) => setNewSns(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={mAdd.isPending}
                onClick={() => mAdd.mutate()}
              >
                添加
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setAddOpen(false);
                  setNewSns("");
                }}
              >
                取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* items table */}
      <Card className="shadow-card-soft">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            单件明细 ({items.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              暂无单件记录，请点击「添加单件」
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="pb-2 font-normal">SN</th>
                    <th className="pb-2 font-normal">状态</th>
                    <th className="pb-2 font-normal">位置</th>
                    <th className="pb-2 font-normal">安装主机</th>
                    <th className="pb-2 font-normal text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it) => (
                    <ItemRow
                      key={it.id}
                      item={it}
                      onUpdate={(patch) =>
                        mUpdate.mutate({ itemId: it.id, patch })
                      }
                      onDelete={() => mDelete.mutate(it.id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* movement history */}
      <Card className="shadow-card-soft">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">出入库历史</CardTitle>
        </CardHeader>
        <CardContent>
          {related.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              暂无出入库记录
            </p>
          ) : (
            <div className="divide-y divide-border">
              {related.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center justify-between py-3"
                >
                  <div className="flex items-center gap-3">
                    <StatusBadge kind="movement" value={m.type} />
                    <div>
                      <div className="text-sm font-medium text-foreground">
                        {m.relatedServerHostname ? (
                          <Link
                            to={`/servers/${m.relatedServerId}`}
                            className="hover:text-primary"
                          >
                            {m.relatedServerHostname}
                          </Link>
                        ) : (
                          "—"
                        )}
                        {m.partItemSn && (
                          <span className="ml-2 font-mono text-xs text-muted-foreground">
                            SN: {m.partItemSn}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {m.operator} · {m.reason}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono font-medium">x{m.quantity}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {new Date(m.time).toLocaleString()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Inf({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-xs text-muted-foreground">{label}</span>{" "}
      <span className="text-sm text-foreground">{value}</span>
    </div>
  );
}

function ItemRow({
  item,
  onUpdate,
  onDelete,
}: {
  item: PartItem;
  onUpdate: (patch: Partial<PartItem>) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [sn, setSn] = useState(item.sn || "");
  const [location, setLocation] = useState(item.location || "");

  const handleSave = () => {
    onUpdate({ sn: sn || undefined, location: location || undefined });
    setEditing(false);
  };

  return (
    <tr className="border-b border-border/50 hover:bg-muted/20">
      <td className="py-2 pr-4 font-mono text-xs">
        {editing ? (
          <Input
            className="h-7 w-32 text-xs"
            value={sn}
            onChange={(e) => setSn(e.target.value)}
            placeholder="输入 SN"
          />
        ) : (
          item.sn || (
            <span className="italic text-muted-foreground">未录入</span>
          )
        )}
      </td>
      <td className="py-2">
        <StatusBadge kind="part" value={item.status} />
      </td>
      <td className="py-2 pr-2 text-xs text-muted-foreground">
        {editing ? (
          <Input
            className="h-7 w-24 text-xs"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        ) : (
          item.location || "—"
        )}
      </td>
      <td className="py-2 text-xs">
        {item.installedServerId && item.installedServerHostname ? (
          <Link
            to={`/servers/${item.installedServerId}`}
            className="font-mono text-primary hover:underline"
          >
            {item.installedServerHostname}
          </Link>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-2 text-right">
        {editing ? (
          <span className="flex items-center justify-end gap-1">
            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={handleSave}>
              <Check className="h-3 w-3 text-green-500" />
            </Button>
            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing(false)}>
              <X className="h-3 w-3" />
            </Button>
          </span>
        ) : (
          <span className="flex items-center justify-end gap-1">
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6"
              onClick={() => setEditing(true)}
            >
              <Search className="h-3 w-3" />
            </Button>
            {item.status === "in_stock" && (
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6"
                onClick={onDelete}
              >
                <Trash2 className="h-3 w-3 text-danger" />
              </Button>
            )}
          </span>
        )}
      </td>
    </tr>
  );
}
