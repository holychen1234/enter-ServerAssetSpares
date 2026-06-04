import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTerminalAsset, listAuditLogs } from "@/lib/api/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { StatusBadge } from "@/components/cmdb/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Monitor, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

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

export default function TerminalAssetDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: ta, isLoading } = useQuery({
    queryKey: ["terminal-asset", id],
    queryFn: () => getTerminalAsset(id!),
    enabled: !!id,
  });

  const { data: auditPage } = useQuery({
    queryKey: ["audit-logs", id],
    queryFn: () => listAuditLogs({ target: `ta:${ta?.hostname ?? ""}`, limit: 50 }),
    enabled: !!ta?.hostname,
  });
  const logs = auditPage?.items ?? [];

  if (isLoading) {
    return <div className="flex items-center justify-center py-20 text-muted-foreground">加载中…</div>;
  }
  if (!ta) {
    return <div className="flex items-center justify-center py-20 text-muted-foreground">终端不存在</div>;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={ta.hostname}
        description={`${ta.manufacturer} ${ta.model} · ${ta.os}${ta.osVersion ? ` ${ta.osVersion}` : ""}`}
        icon={<Monitor className="h-5 w-5" />}
        badge={<StatusBadge kind="server" value={ta.status} />}
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate("/terminal-assets")}>
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
          <InfoCard title="机器信息">
            <Row label="计算机名" value={ta.hostname} mono />
            <Row label="SN" value={ta.sn} mono />
            <Row label="资产编号" value={ta.assetTag} mono />
            <Row label="厂商" value={ta.manufacturer} />
            <Row label="型号" value={ta.model} />
          </InfoCard>
          <InfoCard title="硬件配置">
            <Row label="CPU 型号" value={ta.cpuModel} />
            <Row label="CPU 核心数" value={ta.cpuCount} />
            <Row label="内存" value={`${ta.memoryGB} GB`} />
            <Row label="硬盘类型" value={ta.diskType} />
            <Row label="硬盘容量" value={`${ta.diskCapacityGB} GB`} />
            <Row label="MAC 地址" value={ta.macAddress} mono />
          </InfoCard>
          <InfoCard title="操作系统">
            <Row label="系统" value={ta.os} />
            <Row label="版本" value={ta.osVersion} />
          </InfoCard>
          <InfoCard title="网络">
            <Row label="IP 地址" value={ta.bizIp} mono />
          </InfoCard>
          <InfoCard title="使用者">
            <Row label="使用人" value={ta.userName} />
          </InfoCard>
          <InfoCard title="生命周期">
            <Row label="采购日期" value={ta.purchaseDate} />
            <Row label="保修截止" value={ta.warrantyEnd} />
            {ta.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {ta.tags.map((t) => (
                  <span key={t} className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">{t}</span>
                ))}
              </div>
            )}
            {ta.remark && <Row label="备注" value={ta.remark} />}
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
