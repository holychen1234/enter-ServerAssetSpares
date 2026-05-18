import { PageHeader } from "@/components/cmdb/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ShieldCheck, Check, X } from "lucide-react";

const PERMS = [
  { key: "主机查询", admin: true, operator: true, viewer: true },
  { key: "主机新增 / 编辑 / 删除", admin: true, operator: true, viewer: false },
  { key: "BMC 实时状态查看", admin: true, operator: true, viewer: true },
  { key: "BMC 远程控制（重启 / 关机）", admin: true, operator: false, viewer: false },
  { key: "备件查询", admin: true, operator: true, viewer: true },
  { key: "备件入库 / 出库 / 报废", admin: true, operator: true, viewer: false },
  { key: "用户管理", admin: true, operator: false, viewer: false },
  { key: "角色配置", admin: true, operator: false, viewer: false },
  { key: "审计日志查看", admin: true, operator: true, viewer: true },
];

function Cell({ ok }: { ok: boolean }) {
  return ok ? (
    <Check className="mx-auto h-4 w-4 text-success" />
  ) : (
    <X className="mx-auto h-4 w-4 text-muted-foreground" />
  );
}

export default function RoleList() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="角色权限"
        description="平台内置三种角色：admin / operator / viewer"
        icon={<ShieldCheck className="h-5 w-5" />}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        {[
          { name: "admin", label: "管理员", desc: "拥有平台所有权限，含用户/角色管理与 BMC 远程控制" },
          { name: "operator", label: "操作员", desc: "可维护主机与备件数据，记录出入库" },
          { name: "viewer", label: "只读", desc: "仅可查看资产、备件与审计日志" },
        ].map((r) => (
          <Card key={r.name} className="shadow-card-soft">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-base">
                <span>{r.label}</span>
                <span className="font-mono text-xs text-muted-foreground">{r.name}</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">{r.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="shadow-card-soft">
        <CardHeader><CardTitle className="text-base">权限矩阵</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-2.5 pr-4 font-medium">权限项</th>
                  <th className="px-3 py-2.5 text-center font-medium">admin</th>
                  <th className="px-3 py-2.5 text-center font-medium">operator</th>
                  <th className="px-3 py-2.5 text-center font-medium">viewer</th>
                </tr>
              </thead>
              <tbody>
                {PERMS.map((p) => (
                  <tr key={p.key} className="border-b border-border last:border-0">
                    <td className="py-2.5 pr-4 text-foreground">{p.key}</td>
                    <td className="px-3 py-2.5 text-center"><Cell ok={p.admin} /></td>
                    <td className="px-3 py-2.5 text-center"><Cell ok={p.operator} /></td>
                    <td className="px-3 py-2.5 text-center"><Cell ok={p.viewer} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
