import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { changeMyPassword } from "@/lib/api/cmdb";
import { useAuth } from "@/hooks/use-auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LockKeyhole, ArrowLeft } from "lucide-react";
import { toast } from "@/hooks/use-toast";

export default function ChangePassword() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");

  const m = useMutation({
    mutationFn: () => changeMyPassword(oldPwd, newPwd),
    onSuccess: () => {
      toast({ title: "密码修改成功，请重新登录" });
      navigate("/dashboard");
    },
    onError: (e: Error) =>
      toast({ title: "修改失败", description: e.message, variant: "destructive" }),
  });

  const handleSubmit = () => {
    if (!oldPwd || !newPwd || !confirmPwd) {
      toast({ title: "请填写所有字段", variant: "destructive" });
      return;
    }
    if (newPwd !== confirmPwd) {
      toast({ title: "两次输入的新密码不一致", variant: "destructive" });
      return;
    }
    if (newPwd.length < 8) {
      toast({ title: "密码长度至少 8 位", variant: "destructive" });
      return;
    }
    if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(newPwd)) {
      toast({ title: "密码须包含大写字母、小写字母和数字", variant: "destructive" });
      return;
    }
    m.mutate();
  };

  return (
    <div className="mx-auto mt-12 max-w-md space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-2">
        <ArrowLeft className="mr-1.5 h-4 w-4" />
        返回
      </Button>
      <Card className="shadow-card-soft">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <LockKeyhole className="h-5 w-5" />
            修改密码
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {user && (
            <div className="rounded-md bg-muted px-3 py-2 text-sm">
              当前账号：<span className="font-mono font-medium">{user.username}</span>
              {user.passwordChangeRequired && (
                <span className="ml-2 text-xs text-orange-500">（需要修改密码）</span>
              )}
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="old-pwd">原密码</Label>
            <Input
              id="old-pwd"
              type="password"
              value={oldPwd}
              onChange={(e) => setOldPwd(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-pwd">
              新密码{" "}
              <span className="text-xs text-muted-foreground">(8位以上，含大小写字母+数字)</span>
            </Label>
            <Input
              id="new-pwd"
              type="password"
              value={newPwd}
              onChange={(e) => setNewPwd(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="confirm-pwd">确认新密码</Label>
            <Input
              id="confirm-pwd"
              type="password"
              value={confirmPwd}
              onChange={(e) => setConfirmPwd(e.target.value)}
            />
          </div>
          <Button className="w-full" onClick={handleSubmit} disabled={m.isPending}>
            {m.isPending ? "修改中…" : "确认修改"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
