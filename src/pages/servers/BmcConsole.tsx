import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getServer } from "@/lib/api/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { Button } from "@/components/ui/button";
import { Monitor, ExternalLink, Loader2, AlertTriangle } from "lucide-react";

export default function BmcConsole() {
  const { id } = useParams<{ id: string }>();

  const { data: server, isLoading, error } = useQuery({
    queryKey: ["server", id],
    queryFn: () => getServer(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !server) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-20 text-muted-foreground">
        <AlertTriangle className="h-8 w-8" />
        <p>无法获取服务器信息</p>
      </div>
    );
  }

  if (!server.mgmtIp) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-20 text-muted-foreground">
        <AlertTriangle className="h-8 w-8" />
        <p>该服务器未配置 BMC 管理口 IP</p>
      </div>
    );
  }

  const bmcUrl = `https://${server.mgmtIp}`;

  return (
    <div className="flex h-full flex-col gap-4">
      <PageHeader
        title={`带外控制台 · ${server.hostname}`}
        description={`${server.bmcProtocol.toUpperCase()} · ${server.mgmtIp}`}
        icon={<Monitor className="h-5 w-5" />}
        actions={
          <Button variant="outline" asChild>
            <a href={bmcUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="mr-1 h-4 w-4" />
              新窗口打开
            </a>
          </Button>
        }
      />
      <div className="flex-1 overflow-hidden rounded-lg border border-border">
        <iframe
          src={bmcUrl}
          title={`BMC Console - ${server.hostname}`}
          className="h-full w-full"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        />
      </div>
    </div>
  );
}
