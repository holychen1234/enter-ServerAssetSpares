import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { CircuitBoard, KeyRound, User2, Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";

const schema = z.object({
  username: z.string().min(1, "请输入用户名"),
  password: z.string().min(1, "请输入密码"),
});

type FormData = z.infer<typeof schema>;

export default function Login() {
  const { signIn, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: Location })?.from?.pathname ?? "/dashboard";

  const form = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "" },
  });

  useEffect(() => {
    if (user) navigate(from, { replace: true });
  }, [user, from, navigate]);

  const onSubmit = async (values: FormData) => {
    setError(null);
    setSubmitting(true);
    try {
      await signIn(values.username, values.password);
      navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-primary p-6">
      <div className="absolute inset-0 opacity-30 [background-image:radial-gradient(hsl(var(--primary-foreground)/0.18)_1px,transparent_1px)] [background-size:32px_32px]" />
      <div className="relative grid w-full max-w-4xl gap-6 lg:grid-cols-2">
        <div className="hidden flex-col justify-between rounded-2xl border border-primary-foreground/20 bg-primary-foreground/5 p-8 text-primary-foreground backdrop-blur lg:flex">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-foreground/15">
              <CircuitBoard className="h-5 w-5" />
            </div>
            <div>
              <div className="text-lg font-semibold">主机资产管理</div>
              <div className="text-xs text-primary-foreground/70">Asset & Inventory Console</div>
            </div>
          </div>
          <div className="space-y-3">
            <h2 className="text-3xl font-semibold leading-tight">
              统一管理服务器资产<br />与备件耗材库存
            </h2>
            <p className="text-sm text-primary-foreground/75">
              支持 Redfish / IPMI 双协议采集 BMC 实时状态，
              覆盖硬盘、内存、网卡、光模块的入库、出库与领用记录。
            </p>
          </div>
          <div className="text-xs text-primary-foreground/60">v0.1.0</div>
        </div>

        <Card className="shadow-elevated">
          <CardContent className="p-8">
            <h1 className="text-xl font-semibold text-foreground">登录控制台</h1>
            <p className="mt-1 text-sm text-muted-foreground">使用账号密码登录管理平台</p>

            <form className="mt-6 space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
              <div className="space-y-2">
                <Label htmlFor="username">用户名</Label>
                <div className="relative">
                  <User2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input id="username" autoComplete="username" {...form.register("username")} className="pl-9" />
                </div>
                {form.formState.errors.username && (
                  <p className="text-xs text-danger">{form.formState.errors.username.message}</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">密码</Label>
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    {...form.register("password")}
                    className="pl-9"
                  />
                </div>
                {form.formState.errors.password && (
                  <p className="text-xs text-danger">{form.formState.errors.password.message}</p>
                )}
              </div>

              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} 登录
              </Button>
            </form>

            
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
