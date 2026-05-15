import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  LayoutDashboard,
  Server,
  Boxes,
  ArrowDownToLine,
  ArrowUpFromLine,
  ScrollText,
  Users,
  ShieldCheck,
  LogOut,
  CircuitBoard,
  Key,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useAuth } from "@/hooks/use-auth";
import type { Role } from "@/types/cmdb";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: typeof Server;
  roles?: Role[];
  end?: boolean;
}

const MAIN_NAV: NavItem[] = [
  { to: "/dashboard", label: "仪表盘", icon: LayoutDashboard, end: true },
  { to: "/servers", label: "服务器资产", icon: Server },
];

const INVENTORY_NAV: NavItem[] = [
  { to: "/inventory/parts", label: "备件列表", icon: Boxes },
  { to: "/inventory/inbound", label: "入库记录", icon: ArrowDownToLine },
  { to: "/inventory/outbound", label: "出库 / 领用", icon: ArrowUpFromLine },
];

const SYSTEM_NAV: NavItem[] = [
  { to: "/audit", label: "操作日志", icon: ScrollText },
  { to: "/system/users", label: "用户管理", icon: Users, roles: ["admin"] },
  { to: "/system/roles", label: "角色权限", icon: ShieldCheck, roles: ["admin"] },
];

function NavSection({ label, items }: { label: string; items: NavItem[] }) {
  const { hasRole, user } = useAuth();
  const visible = items.filter((it) => !it.roles || (user && it.roles.includes(user.role)) || hasRole("admin"));
  if (visible.length === 0) return null;
  return (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {visible.map((item) => (
            <SidebarMenuItem key={item.to}>
              <NavLink to={item.to} end={item.end}>
                {({ isActive }) => (
                  <SidebarMenuButton
                    isActive={isActive}
                    className={cn(
                      "transition-smooth",
                      isActive && "bg-sidebar-accent text-sidebar-accent-foreground",
                    )}
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                )}
              </NavLink>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

function UserMenu() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  const initials = user.name.slice(0, 1).toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-9 gap-2 px-2">
          <Avatar className="h-7 w-7">
            <AvatarFallback className="bg-primary text-primary-foreground text-xs">{initials}</AvatarFallback>
          </Avatar>
          <div className="hidden text-left leading-tight sm:block">
            <div className="text-xs font-medium text-foreground">{user.name}</div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{user.role}</div>
          </div>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel>
          <div className="text-sm font-medium">{user.name}</div>
          <div className="text-xs text-muted-foreground">{user.email}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate("/change-password")}>
          <Key className="mr-2 h-4 w-4" /> 修改密码
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => {
            signOut();
            navigate("/login", { replace: true });
          }}
        >
          <LogOut className="mr-2 h-4 w-4" /> 退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppLayout() {
  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader className="border-b border-sidebar-border px-3 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-gradient-primary text-primary-foreground shadow-glow">
              <CircuitBoard className="h-4 w-4" />
            </div>
            <div className="flex flex-col leading-tight group-data-[collapsible=icon]:hidden">
              <span className="text-sm font-semibold text-sidebar-foreground">服务器 CMDB</span>
              <span className="text-[10px] uppercase tracking-wider text-sidebar-foreground/60">Asset Console</span>
            </div>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <NavSection label="资产管理" items={MAIN_NAV} />
          <NavSection label="备件耗材" items={INVENTORY_NAV} />
          <NavSection label="系统" items={SYSTEM_NAV} />
        </SidebarContent>
        <SidebarFooter className="border-t border-sidebar-border px-3 py-2">
          <div className="text-[10px] text-sidebar-foreground/50 group-data-[collapsible=icon]:hidden">
            v0.1.0 · 私有化部署版
          </div>
        </SidebarFooter>
      </Sidebar>
      <main className="flex min-h-screen flex-1 flex-col bg-gradient-surface">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border bg-background/85 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/70">
          <SidebarTrigger />
          <div className="ml-auto flex items-center gap-2">
            <UserMenu />
          </div>
        </header>
        <div className="flex-1 p-4 sm:p-6 animate-fade-in">
          <Outlet />
        </div>
      </main>
    </SidebarProvider>
  );
}
