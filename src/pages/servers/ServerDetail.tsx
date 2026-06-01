import { useMemo } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getBmcStatus, refreshBmcStatus, getServer, listMovements, listAuditLogs, listInstalledItems, lookupItemsBySns } from "@/lib/api/cmdb";
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
    // No auto-refetch — data is persisted daily. Use the manual button instead.
    staleTime: 60000,
  });
  const { data: movements = [] } = useQuery({
    queryKey: ["movements"],
    queryFn: listMovements,
  });
  const { data: installedItems = [] } = useQuery({
    queryKey: ["installed-items", id],
    queryFn: () => listInstalledItems(id),
    enabled: !!id,
  });
  // Audit entries that touched this server. The convention used everywhere
  // in the backend is `target = "srv:<hostname>"`, so we filter by it.
  const { data: auditPage } = useQuery({
    queryKey: ["audit", "server", server?.hostname ?? id],
    queryFn: () =>
      listAuditLogs({ target: `srv:${server?.hostname ?? ""}`, limit: 100 }),
    enabled: !!server?.hostname,
  });
  const serverLogs = auditPage?.items ?? [];
  const related = movements.filter((m) => m.relatedServerId === id);

  // Collect drive SNs for PartItem cross-reference
  const driveSns = useMemo(() => {
    if (!status?.drives) return [];
    return status.drives.map((d) => d.sn).filter(Boolean) as string[];
  }, [status?.drives]);

  const { data: matchedItems = [] } = useQuery({
    queryKey: ["part-items-by-sn", driveSns],
    queryFn: () => lookupItemsBySns(driveSns),
    enabled: driveSns.length > 0,
  });

  const itemSnMap = useMemo(() => {
    const map: Record<string, { itemId: string; partId: string }> = {};
    for (const it of matchedItems) {
      if (it.sn) map[it.sn] = { itemId: it.id, partId: it.partId };
    }
    return map;
  }, [matchedItems]);

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
          <CardContent className="p-8 text-center text-muted-foreground">主机不存在</CardContent>
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
              disabled={isFetching}
              onClick={() => refreshBmcStatus(id).then(() => refetch())}
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
              <Row
                label="硬盘数量"
                value={
                  status?.drives ? (
                    <span className="inline-flex items-center gap-2">
                      {status.drives.length} 块
                      <Badge variant="outline" className="text-[10px] text-success border-success/30 bg-success/10">
                        BMC
                      </Badge>
                    </span>
                  ) : (
                    `${server.diskCount} 块`
                  )
                }
              />
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
              <Row
                label="BMC 密码"
                value={
                  server.bmcPasswordSet ? (
                    <span className="text-success">已设置</span>
                  ) : (
                    <span className="text-warning">未设置</span>
                  )
                }
              />
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
            <BmcLiveCard status={status} loading={isFetching} itemSnMap={itemSnMap} />
          ) : (
            <Card><CardContent className="p-8 text-center text-muted-foreground">加载 BMC 数据中…</CardContent></Card>
          )}
        </TabsContent>

        <TabsContent value="parts" className="space-y-4">
          {/* Currently installed items */}
          <Card className="shadow-card-soft">
            <CardHeader>
              <CardTitle className="text-base">
                当前安装部件
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  共 {installedItems.length} 件
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {installedItems.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  暂无已安装部件记录
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th className="pb-2 font-normal">SN</th>
                        <th className="pb-2 font-normal">类别</th>
                        <th className="pb-2 font-normal">型号</th>
                        <th className="pb-2 font-normal">规格</th>
                        <th className="pb-2 font-normal">状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {installedItems.map((it) => (
                        <tr key={it.id} className="border-b border-border/50">
                          <td className="py-2 pr-3 font-mono text-xs">
                            <Link
                              to={`/inventory/parts/${it.partId}`}
                              className="text-primary hover:underline"
                            >
                              {it.sn || "—"}
                            </Link>
                          </td>
                          <td className="py-2 text-xs">
                            {CAT_LABEL[it.partCategory || "other"]}
                          </td>
                          <td className="py-2 text-xs text-muted-foreground">
                            {it.partBrand} {it.partModel}
                          </td>
                          <td className="py-2 text-xs text-muted-foreground">
                            {it.partSpec}
                          </td>
                          <td className="py-2">
                            <StatusBadge kind="part" value={it.status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Historical movements */}
          <Card className="shadow-card-soft">
            <CardHeader>
              <CardTitle className="text-base">该主机历史耗材记录</CardTitle>
            </CardHeader>
            <CardContent>
              {related.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  暂无关联备件出库记录
                </p>
              ) : (
                <div className="divide-y divide-border">
                  {related.map((m) => (
                    <div
                      key={m.id}
                      className="flex items-center justify-between py-3"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <StatusBadge kind="movement" value={m.type} />
                          <Link
                            to={`/inventory/parts/${m.partId}`}
                            className="text-sm font-medium text-foreground hover:text-primary"
                          >
                            {m.partModel}
                          </Link>
                          {m.partItemSn && (
                            <span className="font-mono text-xs text-muted-foreground">
                              SN: {m.partItemSn}
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {m.operator} · {m.reason}
                        </p>
                      </div>
                      <div className="text-right">
                        <div className="font-mono text-sm font-medium">
                          x{m.quantity}
                        </div>
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
        </TabsContent>

        <TabsContent value="logs">
          <Card className="shadow-card-soft">
            <CardHeader>
              <CardTitle className="text-base">
                操作日志 · {server.hostname}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  共 {serverLogs.length} 条
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {serverLogs.length === 0 ? (
                <p className="px-6 py-8 text-center text-sm text-muted-foreground">
                  暂无与该主机关联的操作记录
                </p>
              ) : (
                <div className="divide-y divide-border">
                  {serverLogs.map((l) => (
                    <div key={l.id} className="flex items-start gap-3 px-6 py-3">
                      <span
                        className={
                          "mt-1 inline-block rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider " +
                          (l.level === "info"
                            ? "bg-info/10 text-info border-info/30"
                            : l.level === "warn"
                              ? "bg-warning/10 text-warning border-warning/30"
                              : "bg-danger/10 text-danger border-danger/30")
                        }
                      >
                        {l.level}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline gap-2">
                          <span className="font-mono text-xs text-primary">{l.action}</span>
                          <span className="font-mono text-[11px] text-muted-foreground">{l.actor}</span>
                          <span className="ml-auto text-[11px] text-muted-foreground">
                            {new Date(l.time).toLocaleString()}
                          </span>
                        </div>
                        <p className="mt-1 text-sm text-foreground">{l.detail || "—"}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
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
