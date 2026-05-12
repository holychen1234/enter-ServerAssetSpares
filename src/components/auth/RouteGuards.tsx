import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/use-auth";
import type { Role } from "@/types/cmdb";
import type { ReactElement } from "react";
import { ShieldAlert } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return null;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

export function RequireRole({ roles, children }: { roles: Role[]; children: ReactElement }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Card className="max-w-md shadow-elevated">
          <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/10 text-danger">
              <ShieldAlert className="h-6 w-6" />
            </div>
            <h2 className="text-lg font-semibold text-foreground">无权访问</h2>
            <p className="text-sm text-muted-foreground">
              当前角色 <span className="font-mono">{user.role}</span> 没有访问该页面的权限。请联系管理员。
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }
  return children;
}
