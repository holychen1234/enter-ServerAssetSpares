import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getNetworkDevice, listAuditLogs } from "@/lib/api/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Router, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

const deviceTypeLabel: Record<string, string> = {
  switch: "交换机",
  router: "路由器",
  firewall: "防火墙",
  load_balancer: "负载均衡",
};

const protocolLabel: Record<string, string> = {
  ssh: "SSH",
  snmp: "SNMP",
  telnet: "Telnet",
};

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">{title}</CardTitle></CardHeader>
      <CardContent className="space-y-2">{children}</CardContent>
    </Card>
  );
}

function Row({ label, value, mono }: { label: string; value?: string | number | null; mono?: boolean }) {
  if (value === "" || value === undefined || value === null) return null;
  return (
    <div className="flex items-start justify-between gap-2 text-sm">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={`text-right ${mono ? "font-mono" : "text-foreground"}`}>{String(value)}</span>
    </div>
  );
}

export default function NetworkDeviceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: device, isLoading } = useQuery({
    queryKey: ["network-device", id],
    queryFn: () => getNetworkDevice(id!),
    enabled: !!id,
  });

  const { data: auditPage } = useQuery({
    queryKey: ["audit-logs", id],
    queryFn: () => listAuditLogs({ target: `ndev:${device?.hostname ?? ""}`, limit: 50 }),
    enabled: !!device?.hostname,
  });
  const logs = auditPage?.items ?? [];

  if (isLoading) {
    return <div className="flex items-center justify-center py-20 text-muted-foreground">加载中…</div>;
  }
  if (!device) {
    return <div className="flex items-center justify-center py-20 text-muted-foreground">设备不存在</div>;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={device.hostname}
        description={`${device.manufacturer} ${device.model} · ${deviceTypeLabel[device.deviceType] || device.deviceType}`}
        icon={<Router className="h-5 w-5" />}
        badge={<StatusBadge kind="server" value={device.status} />}
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate("/network-devices")}>
            <ArrowLeft className="mr-1 h-4 w-4" /> 返回列表
          </Button>
        }
      />

      <Tabs defaultValue="info">
        <TabsList>
          <TabsTrigger value="info">基本信息</TabsTrigger>
          <TabsTrigger value="logs">操作日志</TabsTrigger>
        </TabsList>

        <TabsContent value="info" className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <InfoCard title="设备信息">
            <Row label="设备名" value={device.hostname} mono />
            <Row label="SN" value={device.sn} mono />
            <Row label="资产编号" value={device.assetTag} mono />
            <Row label="设备类型" value={deviceTypeLabel[device.deviceType] || device.deviceType} />
            <Row label="厂商" value={device.manufacturer} />
            <Row label="型号" value={device.model} />
            <Row label="固件版本" value={device.firmwareVersion} />
            <Row label="负责人" value={device.owner} />
          </InfoCard>
          <InfoCard title="硬件配置">
            <Row label="CPU 型号" value={device.cpuModel} />
            <Row label="CPU 数量" value={device.cpuCount} />
            <Row label="内存" value={device.memoryGB ? `${device.memoryGB} GB` : ""} />
            <Row label="存储" value={device.flashGB ? `${device.flashGB} GB` : ""} />
            <Row label="端口数量" value={device.portCount} />
          </InfoCard>
          <InfoCard title="管理信息">
            <Row label="管理 IP" value={device.mgmtIp} mono />
            <Row label="管理协议" value={protocolLabel[device.mgmtProtocol] || device.mgmtProtocol} />
            <Row label="管理端口" value={device.mgmtPort} />
            <Row label="SNMP 团体字" value={device.snmpCommunity || "未配置"} />
            <Row label="SSH 用户名" value={device.sshUsername || "未配置"} />
            <Row label="SSH 密码" value={device.sshPasswordSet ? "已设置" : "未设置"} />
          </InfoCard>
          <InfoCard title="网络接入">
            <Row label="管理 IP" value={device.mgmtIp} mono />
            <Row label="业务 IP" value={device.bizIp} mono />
            <Row label="VLAN" value={device.vlan} />
          </InfoCard>
          <InfoCard title="位置">
            <Row label="IDC" value={device.idc} />
            <Row label="机柜" value={device.rack} />
            <Row label="U 位" value={device.uPosition} />
          </InfoCard>
          <InfoCard title="生命周期">
            <Row label="采购日期" value={device.purchaseDate} />
            <Row label="保修截止" value={device.warrantyEnd} />
            {device.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {device.tags.map((t) => (
                  <span key={t} className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">{t}</span>
                ))}
              </div>
            )}
            {device.remark && <Row label="备注" value={device.remark} />}
          </InfoCard>
        </TabsContent>

        <TabsContent value="logs" className="mt-4">
          <Card>
            <CardHeader><CardTitle className="text-sm">操作日志</CardTitle></CardHeader>
            <CardContent>
              {logs.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无操作日志</p>
              ) : (
                <div className="space-y-2">
                  {logs.map((l) => (
                    <div key={l.id} className="flex items-start justify-between gap-4 border-b border-border pb-2 text-sm">
                      <div>
                        <span className="font-medium">{l.actor}</span>
                        <span className="text-muted-foreground"> · {l.action} · {l.detail}</span>
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">{new Date(l.time).toLocaleString()}</span>
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
