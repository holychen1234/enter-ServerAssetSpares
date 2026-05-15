import { Navigate } from "react-router-dom";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import ServerList from "./pages/servers/ServerList";
import ServerDetail from "./pages/servers/ServerDetail";
import PartList from "./pages/inventory/PartList";
import PartDetail from "./pages/inventory/PartDetail";
import InboundList from "./pages/inventory/InboundList";
import OutboundList from "./pages/inventory/OutboundList";
import AuditLog from "./pages/audit/AuditLog";
import UserList from "./pages/system/UserList";
import RoleList from "./pages/system/RoleList";
import ChangePassword from "./pages/system/ChangePassword";
import { AppLayout } from "./layouts/AppLayout";
import { RequireAuth, RequireRole } from "./components/auth/RouteGuards";

export const routers = [
  { path: "/", name: "root", element: <Index /> },
  { path: "/login", name: "login", element: <Login /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { path: "dashboard", name: "dashboard", element: <Dashboard /> },
      { path: "servers", name: "servers", element: <ServerList /> },
      { path: "servers/:id", name: "server-detail", element: <ServerDetail /> },
      { path: "inventory", element: <Navigate to="/inventory/parts" replace /> },
      { path: "inventory/parts", name: "parts", element: <PartList /> },
      { path: "inventory/parts/:id", name: "part-detail", element: <PartDetail /> },
      { path: "inventory/inbound", name: "inbound", element: <InboundList /> },
      { path: "inventory/outbound", name: "outbound", element: <OutboundList /> },
      { path: "audit", name: "audit", element: <AuditLog /> },
      { path: "change-password", name: "change-password", element: <ChangePassword /> },
      {
        path: "system/users",
        name: "system-users",
        element: (
          <RequireRole roles={["admin"]}>
            <UserList />
          </RequireRole>
        ),
      },
      {
        path: "system/roles",
        name: "system-roles",
        element: (
          <RequireRole roles={["admin"]}>
            <RoleList />
          </RequireRole>
        ),
      },
    ],
  },
  /* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */
  { path: "*", name: "404", element: <NotFound /> },
];

declare global {
  interface Window {
    __routers__: typeof routers;
  }
}

window.__routers__ = routers;
