import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listUsers, updateUser } from "@/lib/api/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { Card } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Switch } from "@/components/ui/switch";
import { Users } from "lucide-react";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import type { Role } from "@/types/cmdb";
import { toast } from "@/hooks/use-toast";

export default function UserList() {
  const qc = useQueryClient();
  const { data: users = [] } = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const m = useMutation({
    mutationFn: (v: { id: string; patch: Partial<{ role: Role; enabled: boolean }> }) => updateUser(v.id, v.patch),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); toast({ title: "用户已更新" }); },
  });

  return (
    <div className="space-y-6">
      <PageHeader title="用户管理" description="管理平台账号、角色与启用状态" icon={<Users className="h-5 w-5" />} />
      <Card className="shadow-card-soft">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>用户名</TableHead>
                <TableHead>姓名</TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>角色</TableHead>
                <TableHead>启用</TableHead>
                <TableHead>最后登录</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id}>
                  <TableCell><span className="font-mono text-sm">{u.username}</span></TableCell>
                  <TableCell><span className="text-sm font-medium">{u.name}</span></TableCell>
                  <TableCell><span className="text-xs text-muted-foreground">{u.email}</span></TableCell>
                  <TableCell>
                    <Select value={u.role} onValueChange={(v) => m.mutate({ id: u.id, patch: { role: v as Role } })}>
                      <SelectTrigger className="w-[120px]"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">admin</SelectItem>
                        <SelectItem value="operator">operator</SelectItem>
                        <SelectItem value="viewer">viewer</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Switch checked={u.enabled} onCheckedChange={(c) => m.mutate({ id: u.id, patch: { enabled: c } })} />
                  </TableCell>
                  <TableCell><span className="text-xs text-muted-foreground">{u.lastLogin ? new Date(u.lastLogin).toLocaleString() : "—"}</span></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}
