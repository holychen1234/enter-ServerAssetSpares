import { useNavigate, useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getBmcStatus, getServer, listMovements } from "@/lib/api/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import { BmcLiveCard } from "@/components/cmdb/BmcLiveCard";
import { ArrowLeft, Server as ServerIcon, RefreshCw } from "lucide-react";

export default function ServerDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data: server, isLoading } = useQuery({
    queryKey: ["server", id],
    queryFn: () => getServer(id),
    enabled: !!id,
  });
  const { data: status, isFetching, refetch } = useQuery({
    queryKey: ["bmc", id],
    queryFn: () => getBmcStatus(id),
    enabled: !!id,
    refetchInterval: 15000,
  });
  const { data: movements = [] } = useQuery({
    queryKey: ["movements"],
    queryFn: listMovements,
  });
  const related = movements.filter((m) => m.relatedServerId === id);

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">加载中…</div>;
  }
  if (!server) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ArrowLeft className="mr-1 h-4 w-4" /> 返回
        </Button>
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">服务器不存在</CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate("/servers")}>
        <ArrowLeft className="mr-1 h-4 w-4" /> 返回列表
      </Button>

      <PageHeader
        title={server.hostname}
        description={`${server.manufacturer} ${server.model} · ${server.location.idc} ${server.location.rack} ${server.location.uPosition}`}
        icon={<ServerIcon className="h-5 w-5" />}
        actions={
          <>
            <StatusBadge kind="server" value={server.status} />
            <Button
              variant="outline"
              size="sm"
              onClick={() => getBmcStatus(id, { force: true }).then(() => refetch())}
            >
              <RefreshCw className={`mr-1 h-4 w-4 ${isFetching ? "animate-spin" : ""}`} /> 刷新 BMC
            </Button>
          </>
        }
      />

      <Tabs defaultValue="info" className="space-y-4">
        <TabsList>
          <TabsTrigger value="info">基本信息</TabsTrigger>
          <TabsTrigger value="bmc">BMC 实时状态</TabsTrigger>
          <TabsTrigger value="parts">关联备件</TabsTrigger>
          <TabsTrigger value="logs">操作日志</TabsTrigger>
        </TabsList>

        <TabsContent value="info">
          <div className="grid gap-4 lg:grid-cols-2">
            <InfoCard title="资产信息">
              <Row label="主机名" value={server.hostname} />
              <Row label="序列号" value={server.sn} mono />
              <Row label="资产编号" value={server.assetTag} mono />
              <Row label="厂商 / 型号" value={`${server.manufacturer} · ${server.model}`} />
              <Row label="负责人" value={server.owner} />
              <Row
                label="标签"
                value={
                  <div className="flex flex-wrap gap-1">
                    {server.tags.map((t) => <Badge key={t} variant="secondary">{t}</Badge>)}
                    {server.tags.length === 0 && <span className="text-muted-foreground">—</span>}
                  </div>
                }
              />
              <Row label="备注" value={server.remark || "—"} />
            </InfoCard>

            <InfoCard title="硬件配置">
              <Row label="CPU" value={`${server.cpuCount} × ${server.cpuModel}`} />
              <Row label="内存" value={`${server.memoryGB} GB`} />
              <Row label="硬盘数量" value={`${server.diskCount} 块`} />
            </InfoCard>

            <InfoCard title="位置">
              <Row label="IDC" value={server.location.idc} />
              <Row label="机柜" value={server.location.rack} />
              <Row label="U 位" value={server.location.uPosition} />
            </InfoCard>

            <InfoCard title="网络接入">
              <Row label="业务 IP" value={server.bizIp} mono />
              <Row label="BMC IP" value={server.mgmtIp} mono />
              <Row label="BMC 协议" value={server.bmcProtocol.toUpperCase()} />
              <Row label="BMC 用户" value={server.bmcUser} mono />
            </InfoCard>

            <InfoCard title="生命周期">
              <Row label="采购日期" value={server.purchaseDate} />
              <Row label="保修截止" value={server.warrantyEnd} />
              <Row label="最后更新" value={new Date(server.updatedAt).toLocaleString()} />
            </InfoCard>
          </div>
        </TabsContent>

        <TabsContent value="bmc">
          {status ? (
            <BmcLiveCard status={status} loading={isFetching} />
          ) : (
            <Card><CardContent className="p-8 text-center text-muted-foreground">加载 BMC 数据中…</CardContent></Card>
          )}
        </TabsContent>

        <TabsContent value="parts">
          <Card className="shadow-card-soft">
            <CardHeader><CardTitle className="text-base">该服务器历史耗材</CardTitle></CardHeader>
            <CardContent>
              {related.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">暂无关联备件出库记录</p>
              ) : (
                <div className="divide-y divide-border">
                  {related.map((m) => (
                    <div key={m.id} className="flex items-center justify-between py-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <StatusBadge kind="movement" value={m.type} />
                          <Link to={`/inventory/parts/${m.partId}`} className="text-sm font-medium text-foreground hover:text-primary">
                            {m.partModel}
                          </Link>
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">{m.operator} · {m.reason}</p>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-sm font-medium">x{m.quantity}</div>
                        <div className="text-[10px] text-muted-foreground">{new Date(m.time).toLocaleString()}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="logs">
          <Card className="shadow-card-soft">
            <CardHeader><CardTitle className="text-base">操作日志（演示）</CardTitle></CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <p>该 Tab 在生产版会展示对该服务器的所有操作记录（创建、更新、BMC 告警、备件挂载等）。</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="shadow-card-soft">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="divide-y divide-border">{children}</CardContent>
    </Card>
  );
}

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`text-right text-foreground ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}
