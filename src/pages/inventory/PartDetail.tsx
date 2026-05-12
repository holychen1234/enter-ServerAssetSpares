import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getPart, listMovements } from "@/lib/mockApi";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import { ArrowLeft, Boxes, AlertTriangle } from "lucide-react";

const CATEGORY_LABEL: Record<string, string> = {
  disk: "硬盘", memory: "内存", nic: "网卡", optical: "光模块", other: "其他",
};

export default function PartDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data: part, isLoading } = useQuery({ queryKey: ["part", id], queryFn: () => getPart(id), enabled: !!id });
  const { data: movements = [] } = useQuery({ queryKey: ["movements"], queryFn: listMovements });
  const related = movements.filter((m) => m.partId === id);

  if (isLoading) return <div className="text-sm text-muted-foreground">加载中…</div>;
  if (!part) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ArrowLeft className="mr-1 h-4 w-4" /> 返回
        </Button>
        <Card><CardContent className="p-8 text-center text-muted-foreground">备件不存在</CardContent></Card>
      </div>
    );
  }

  const low = part.stock < part.safetyStock;

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate("/inventory/parts")}>
        <ArrowLeft className="mr-1 h-4 w-4" /> 返回备件列表
      </Button>

      <PageHeader
        title={`${part.brand} ${part.model}`}
        description={`${CATEGORY_LABEL[part.category]} · ${part.spec}`}
        icon={<Boxes className="h-5 w-5" />}
        actions={<StatusBadge kind="part" value={part.status} />}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="shadow-card-soft">
          <CardHeader className="pb-2"><CardTitle className="text-base">库存</CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <span className={`font-mono text-4xl font-semibold ${low ? "text-danger" : "text-foreground"}`}>{part.stock}</span>
              <span className="text-sm text-muted-foreground">{part.unit}</span>
            </div>
            <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
              安全库存 {part.safetyStock} {part.unit}
              {low && <span className="ml-2 inline-flex items-center gap-1 text-danger"><AlertTriangle className="h-3 w-3" /> 库存预警</span>}
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-card-soft lg:col-span-2">
          <CardHeader className="pb-2"><CardTitle className="text-base">基本信息</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <Item label="品牌" value={part.brand} />
            <Item label="型号" value={part.model} mono />
            <Item label="规格" value={part.spec} />
            <Item label="单位" value={part.unit} />
            <Item label="存放位置" value={part.location} />
            {part.sn && <Item label="SN" value={part.sn} mono />}
            {part.remark && <Item label="备注" value={part.remark} className="col-span-2" />}
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-card-soft">
        <CardHeader className="pb-2"><CardTitle className="text-base">出入库历史</CardTitle></CardHeader>
        <CardContent>
          {related.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">暂无出入库记录</p>
          ) : (
            <div className="divide-y divide-border">
              {related.map((m) => (
                <div key={m.id} className="flex items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <StatusBadge kind="movement" value={m.type} />
                    <div>
                      <div className="text-sm font-medium text-foreground">
                        {m.relatedServerHostname ? (
                          <Link to={`/servers/${m.relatedServerId}`} className="hover:text-primary">{m.relatedServerHostname}</Link>
                        ) : "—"}
                      </div>
                      <div className="text-xs text-muted-foreground">{m.operator} · {m.reason}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono font-medium">x{m.quantity}</div>
                    <div className="text-[10px] text-muted-foreground">{new Date(m.time).toLocaleString()}</div>
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

function Item({ label, value, mono, className }: { label: string; value: React.ReactNode; mono?: boolean; className?: string }) {
  return (
    <div className={className}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-sm text-foreground ${mono ? "font-mono" : ""}`}>{value}</div>
    </div>
  );
}
