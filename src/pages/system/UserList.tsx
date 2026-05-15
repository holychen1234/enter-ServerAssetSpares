import { useState, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  resetUserPassword,
  unlockUser,
} from "@/lib/api/cmdb";
import { PageHeader } from "@/components/cmdb/PageHeader";
import { Card } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Pagination, PaginationContent, PaginationItem,
  PaginationLink, PaginationNext, PaginationPrevious,
} from "@/components/ui/pagination";
import {
  Users, Search, Plus, Pencil, Trash2, Key, Unlock,
} from "lucide-react";
import type { Role, CreateUserPayload } from "@/types/cmdb";
import { toast } from "@/hooks/use-toast";

const PAGE_SIZE = 15;

export default function UserList() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<Role | "all">("all");
  const [enabledFilter, setEnabledFilter] = useState<number | undefined>(undefined);

  // ---------- data ----------
  const filters = {
    q: search || undefined,
    role: roleFilter !== "all" ? roleFilter : undefined,
    enabled: enabledFilter,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };

  const { data: userPage, isLoading } = useQuery({
    queryKey: ["users", filters],
    queryFn: () => listUsers(filters),
  });

  const users = userPage?.items ?? [];
  const total = userPage?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // ---------- dialogs state ----------
  const [createOpen, setCreateOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editRole, setEditRole] = useState<Role>("viewer");
  const [editEnabled, setEditEnabled] = useState(true);
  const [editPwdReq, setEditPwdReq] = useState(false);
  const [resetPwdUser, setResetPwdUser] = useState<{ id: string; username: string } | null>(null);
  const [resetPwdValue, setResetPwdValue] = useState("");
  const [deleteUserTarget, setDeleteUserTarget] = useState<{ id: string; username: string } | null>(null);

  // ---------- create form ----------
  const [newUsername, setNewUsername] = useState("");
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<Role>("viewer");

  const resetCreateForm = () => {
    setNewUsername("");
    setNewName("");
    setNewEmail("");
    setNewPassword("");
    setNewRole("viewer");
  };

  // ---------- mutations ----------
  const invalidate = () => qc.invalidateQueries({ queryKey: ["users"] });

  const createM = useMutation({
    mutationFn: (data: CreateUserPayload) => createUser(data),
    onSuccess: () => {
      invalidate();
      setCreateOpen(false);
      resetCreateForm();
      toast({ title: "用户创建成功" });
    },
    onError: (e: Error) => toast({ title: "创建失败", description: e.message, variant: "destructive" }),
  });

  const updateM = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<import("@/types/cmdb").AppUser> }) =>
      updateUser(id, patch),
    onSuccess: () => { invalidate(); toast({ title: "用户已更新" }); },
    onError: (e: Error) => toast({ title: "更新失败", description: e.message, variant: "destructive" }),
  });

  const deleteM = useMutation({
    mutationFn: (id: string) => deleteUser(id),
    onSuccess: () => {
      invalidate();
      setDeleteUserTarget(null);
      toast({ title: "用户已删除" });
    },
    onError: (e: Error) => toast({ title: "删除失败", description: e.message, variant: "destructive" }),
  });

  const resetPwdM = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      resetUserPassword(id, password),
    onSuccess: () => {
      invalidate();
      setResetPwdUser(null);
      setResetPwdValue("");
      toast({ title: "密码已重置" });
    },
    onError: (e: Error) => toast({ title: "重置失败", description: e.message, variant: "destructive" }),
  });

  const unlockM = useMutation({
    mutationFn: (id: string) => unlockUser(id),
    onSuccess: () => { invalidate(); toast({ title: "账号已解锁" }); },
    onError: (e: Error) => toast({ title: "解锁失败", description: e.message, variant: "destructive" }),
  });

  // ---------- handlers ----------
  const openEditDialog = useCallback((u: (typeof users)[0]) => {
    setEditingUser(u.id);
    setEditName(u.name);
    setEditEmail(u.email);
    setEditRole(u.role);
    setEditEnabled(u.enabled);
    setEditPwdReq(u.passwordChangeRequired ?? false);
  }, []);

  const handleSaveEdit = () => {
    if (!editingUser) return;
    updateM.mutate({
      id: editingUser,
      patch: {
        name: editName,
        email: editEmail,
        role: editRole,
        enabled: editEnabled,
        passwordChangeRequired: editPwdReq,
      },
    });
    setEditingUser(null);
  };

  const isLocked = (u: (typeof users)[0]) => {
    if (!u.lockedUntil) return false;
    return new Date(u.lockedUntil) > new Date();
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="用户管理"
        description="管理平台账号、角色与启用状态"
        icon={<Users className="h-5 w-5" />}
      />

      {/* ---------- toolbar ---------- */}
      <Card className="p-4 shadow-card-soft">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px] max-w-[360px]">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="搜索用户名 / 姓名 / 邮箱…"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="pl-8"
            />
          </div>

          <Select
            value={roleFilter}
            onValueChange={(v) => { setRoleFilter(v as Role | "all"); setPage(1); }}
          >
            <SelectTrigger className="w-[130px]">
              <SelectValue placeholder="全部角色" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部角色</SelectItem>
              <SelectItem value="admin">admin</SelectItem>
              <SelectItem value="operator">operator</SelectItem>
              <SelectItem value="viewer">viewer</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={enabledFilter === undefined ? "all" : String(enabledFilter)}
            onValueChange={(v) => {
              setEnabledFilter(v === "all" ? undefined : Number(v));
              setPage(1);
            }}
          >
            <SelectTrigger className="w-[130px]">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="1">已启用</SelectItem>
              <SelectItem value="0">已禁用</SelectItem>
            </SelectContent>
          </Select>

          <div className="flex-1" />

          <Dialog open={createOpen} onOpenChange={(v) => { setCreateOpen(v); if (!v) resetCreateForm(); }}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="mr-1.5 h-4 w-4" />
                新增用户
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[440px]">
              <DialogHeader>
                <DialogTitle>新增用户</DialogTitle>
                <DialogDescription>填写以下信息创建新账号。用户首次登录将被要求修改密码。</DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-2">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="new-username">用户名 *</Label>
                    <Input id="new-username" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="new-role">角色</Label>
                    <Select value={newRole} onValueChange={(v) => setNewRole(v as Role)}>
                      <SelectTrigger id="new-role"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">admin</SelectItem>
                        <SelectItem value="operator">operator</SelectItem>
                        <SelectItem value="viewer">viewer</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="new-name">姓名 *</Label>
                  <Input id="new-name" value={newName} onChange={(e) => setNewName(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="new-email">邮箱 *</Label>
                  <Input id="new-email" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="new-password">密码 * <span className="text-xs text-muted-foreground">(8位以上，含大小写字母+数字)</span></Label>
                  <Input id="new-password" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setCreateOpen(false)}>取消</Button>
                <Button
                  onClick={() =>
                    createM.mutate({
                      username: newUsername,
                      name: newName,
                      email: newEmail,
                      password: newPassword,
                      role: newRole,
                    })
                  }
                  disabled={createM.isPending}
                >
                  {createM.isPending ? "创建中…" : "创建"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </Card>

      {/* ---------- table ---------- */}
      <Card className="shadow-card-soft">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>用户名</TableHead>
                <TableHead>姓名</TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>角色</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>最后登录</TableHead>
                <TableHead className="w-[180px]">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                    加载中…
                  </TableCell>
                </TableRow>
              ) : users.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                    暂无用户
                  </TableCell>
                </TableRow>
              ) : (
                users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm">{u.username}</span>
                        {isLocked(u) && (
                          <Badge variant="destructive" className="text-[10px] px-1.5 py-0">锁定</Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm font-medium">{u.name}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">{u.email}</span>
                    </TableCell>
                    <TableCell>
                      <Select
                        value={u.role}
                        onValueChange={(v) =>
                          updateM.mutate({ id: u.id, patch: { role: v as Role } })
                        }
                      >
                        <SelectTrigger className="w-[110px] h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="admin">admin</SelectItem>
                          <SelectItem value="operator">operator</SelectItem>
                          <SelectItem value="viewer">viewer</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={u.enabled}
                        onCheckedChange={(c) =>
                          updateM.mutate({ id: u.id, patch: { enabled: c } })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {u.lastLogin ? new Date(u.lastLogin).toLocaleString() : "—"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        {/* Edit */}
                        <Dialog
                          open={editingUser === u.id}
                          onOpenChange={(v) => {
                            if (v) openEditDialog(u);
                            else setEditingUser(null);
                          }}
                        >
                          <DialogTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8" title="编辑">
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                          </DialogTrigger>
                          <DialogContent className="sm:max-w-[400px]">
                            <DialogHeader>
                              <DialogTitle>编辑用户 — {u.username}</DialogTitle>
                            </DialogHeader>
                            <div className="grid gap-3 py-2">
                              <div className="space-y-1.5">
                                <Label>姓名</Label>
                                <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
                              </div>
                              <div className="space-y-1.5">
                                <Label>邮箱</Label>
                                <Input value={editEmail} onChange={(e) => setEditEmail(e.target.value)} />
                              </div>
                              <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-1.5">
                                  <Label>角色</Label>
                                  <Select value={editRole} onValueChange={(v) => setEditRole(v as Role)}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="admin">admin</SelectItem>
                                      <SelectItem value="operator">operator</SelectItem>
                                      <SelectItem value="viewer">viewer</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </div>
                                <div className="space-y-1.5">
                                  <Label>启用</Label>
                                  <div className="flex items-center h-9">
                                    <Switch checked={editEnabled} onCheckedChange={setEditEnabled} />
                                  </div>
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <Switch checked={editPwdReq} onCheckedChange={setEditPwdReq} id="edit-pwdreq" />
                                <Label htmlFor="edit-pwdreq" className="text-sm cursor-pointer">
                                  下次登录强制修改密码
                                </Label>
                              </div>
                            </div>
                            <DialogFooter>
                              <Button variant="outline" onClick={() => setEditingUser(null)}>取消</Button>
                              <Button onClick={handleSaveEdit}>保存</Button>
                            </DialogFooter>
                          </DialogContent>
                        </Dialog>

                        {/* Reset Password */}
                        <Dialog
                          open={resetPwdUser?.id === u.id}
                          onOpenChange={(v) => { if (!v) { setResetPwdUser(null); setResetPwdValue(""); } }}
                        >
                          <DialogTrigger asChild>
                            <Button
                              variant="ghost" size="icon" className="h-8 w-8"
                              title="重置密码"
                              onClick={() => setResetPwdUser({ id: u.id, username: u.username })}
                            >
                              <Key className="h-3.5 w-3.5" />
                            </Button>
                          </DialogTrigger>
                          <DialogContent className="sm:max-w-[380px]">
                            <DialogHeader>
                              <DialogTitle>重置密码 — {u.username}</DialogTitle>
                              <DialogDescription>
                                输入新密码。用户下次登录将被要求修改密码。
                              </DialogDescription>
                            </DialogHeader>
                            <div className="space-y-1.5 py-2">
                              <Label>新密码</Label>
                              <Input
                                type="password"
                                value={resetPwdValue}
                                onChange={(e) => setResetPwdValue(e.target.value)}
                                placeholder="8位以上，含大小写字母+数字"
                              />
                            </div>
                            <DialogFooter>
                              <Button variant="outline" onClick={() => { setResetPwdUser(null); setResetPwdValue(""); }}>
                                取消
                              </Button>
                              <Button
                                onClick={() => resetPwdM.mutate({ id: u.id, password: resetPwdValue })}
                                disabled={resetPwdM.isPending}
                              >
                                确认重置
                              </Button>
                            </DialogFooter>
                          </DialogContent>
                        </Dialog>

                        {/* Unlock */}
                        {isLocked(u) && (
                          <Button
                            variant="ghost" size="icon" className="h-8 w-8"
                            title="解锁账号"
                            onClick={() => unlockM.mutate(u.id)}
                          >
                            <Unlock className="h-3.5 w-3.5" />
                          </Button>
                        )}

                        {/* Delete */}
                        <AlertDialog
                          open={deleteUserTarget?.id === u.id}
                          onOpenChange={(v) => { if (!v) setDeleteUserTarget(null); }}
                        >
                          <Button
                            variant="ghost" size="icon" className="h-8 w-8 text-destructive"
                            title="删除"
                            onClick={() => setDeleteUserTarget({ id: u.id, username: u.username })}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>确认删除？</AlertDialogTitle>
                              <AlertDialogDescription>
                                用户 <strong>{u.username}</strong> 将被软删除（禁用且无法登录）。
                                此操作可逆，如需恢复请联系管理员。
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel onClick={() => setDeleteUserTarget(null)}>取消</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={() => deleteM.mutate(u.id)}
                                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                              >
                                确认删除
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* ---------- pagination ---------- */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t px-4 py-3">
            <span className="text-sm text-muted-foreground">
              共 {total} 个用户
            </span>
            <Pagination>
              <PaginationContent>
                <PaginationItem>
                  <PaginationPrevious
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    aria-disabled={page <= 1}
                  />
                </PaginationItem>
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
                  .map((p, idx, arr) => (
                    <PaginationItem key={p}>
                      {idx > 0 && arr[idx - 1] !== p - 1 && (
                        <span className="px-2 text-muted-foreground">…</span>
                      )}
                      <PaginationLink
                        isActive={p === page}
                        onClick={() => setPage(p)}
                      >
                        {p}
                      </PaginationLink>
                    </PaginationItem>
                  ))}
                <PaginationItem>
                  <PaginationNext
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    aria-disabled={page >= totalPages}
                  />
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          </div>
        )}
      </Card>
    </div>
  );
}
