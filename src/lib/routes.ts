/** Route path constants — single source of truth for all navigation. */
export const ROUTES = {
  DASHBOARD: "/dashboard",
  SERVERS: "/servers",
  SERVER_DETAIL: (id: string) => `/servers/${id}`,
  TERMINAL_ASSETS: "/terminal-assets",
  TERMINAL_ASSET_DETAIL: (id: string) => `/terminal-assets/${id}`,
  PARTS: "/inventory/parts",
  PART_DETAIL: (id: string) => `/inventory/parts/${id}`,
  INBOUND: "/inventory/inbound",
  OUTBOUND: "/inventory/outbound",
  AUDIT: "/audit",
  CHANGE_PASSWORD: "/change-password",
  USERS: "/system/users",
  ROLES: "/system/roles",
} as const;
