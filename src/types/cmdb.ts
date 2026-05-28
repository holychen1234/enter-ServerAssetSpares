// Core domain types for the CMDB platform.

export type Role = "admin" | "operator" | "viewer";

export type ServerStatus = "online" | "offline" | "maintenance" | "retired";
export type Manufacturer =
  | "Dell"
  | "HPE"
  | "Lenovo"
  | "Inspur"
  | "Supermicro"
  | "Huawei"
  | "XFusion"
  | "Other";

export type BmcProtocol = "redfish" | "ipmi";

export interface ServerLocation {
  idc: string;
  rack: string;
  uPosition: string;
}

export interface Server {
  id: string;
  hostname: string;
  sn: string;
  assetTag: string;
  manufacturer: Manufacturer;
  model: string;
  cpuModel: string;
  cpuCount: number;
  memoryGB: number;
  diskCount: number;
  location: ServerLocation;
  mgmtIp: string;
  bizIp: string;
  bmcProtocol: BmcProtocol;
  bmcUser: string;
  /**
   * BMC password — write-only on the wire. The API never returns the
   * stored value (security), so this is always undefined when reading
   * a server back. When creating/updating, an empty string means
   * "do not change the existing password".
   */
  bmcPassword?: string;
  /** Server-side flag indicating whether a BMC password is on file. */
  bmcPasswordSet?: boolean;
  status: ServerStatus;
  owner: string;
  purchaseDate: string;
  warrantyEnd: string;
  tags: string[];
  remark?: string;
  createdAt: string;
  updatedAt: string;
}

// ── Network Device ──────────────────────────────────────────

export type NetworkDeviceType =
  | "switch"
  | "router"
  | "firewall"
  | "load_balancer";

export type NetworkDeviceManufacturer =
  | "Cisco"
  | "Huawei"
  | "H3C"
  | "Arista"
  | "Juniper"
  | "Ruijie"
  | "Other";

export type MgmtProtocol = "ssh" | "snmp" | "telnet";

export interface NetworkDevice {
  id: string;
  hostname: string;
  sn: string;
  assetTag: string;
  deviceType: NetworkDeviceType;
  manufacturer: NetworkDeviceManufacturer;
  model: string;
  firmwareVersion: string;
  cpuModel: string;
  cpuCount: number;
  memoryGB: number;
  flashGB: number;
  mgmtIp: string;
  mgmtProtocol: MgmtProtocol;
  mgmtPort: number;
  snmpCommunity: string;
  sshUsername: string;
  sshPassword?: string;
  sshPasswordSet?: boolean;
  bizIp: string;
  vlan: string;
  portCount: number;
  portSpec: { name: string; type: string; speed: string; status: string; connectedTo?: string }[];
  idc: string;
  rack: string;
  uPosition: string;
  status: ServerStatus;
  owner: string;
  purchaseDate: string;
  warrantyEnd: string;
  tags: string[];
  remark?: string;
  createdAt: string;
  updatedAt: string;
}

// ── Workstation ─────────────────────────────────────────────

export type WorkstationManufacturer =
  | "Dell"
  | "HP"
  | "Lenovo"
  | "Apple"
  | "Huawei"
  | "ASUS"
  | "Acer"
  | "Microsoft"
  | "Other";

export type OperatingSystem =
  | "Windows 10"
  | "Windows 11"
  | "macOS"
  | "Ubuntu"
  | "CentOS"
  | "Other";

export interface MonitorInfo {
  model: string;
  sizeInch: number;
  resolution: string;
}

export interface Workstation {
  id: string;
  hostname: string;
  sn: string;
  assetTag: string;
  manufacturer: WorkstationManufacturer;
  model: string;
  cpuModel: string;
  cpuCount: number;
  memoryGB: number;
  diskType: string;
  diskCapacityGB: number;
  macAddress: string;
  os: OperatingSystem;
  osVersion: string;
  bizIp: string;
  userName: string;
  department: string;
  monitors: MonitorInfo[];
  officeBuilding: string;
  floor: string;
  seat: string;
  status: ServerStatus;
  purchaseDate: string;
  warrantyEnd: string;
  tags: string[];
  remark?: string;
  createdAt: string;
  updatedAt: string;
}

export type Health = "OK" | "Warning" | "Critical";

/**
 * Source of the data shown in the BMC live card.
 * - "live":      real Redfish / IPMI poll succeeded.
 * - "simulated": BMC unreachable or no real endpoint configured;
 *                values are deterministic mocks for demo / offline use.
 */
export type BmcDataSource = "live" | "simulated";

export interface BmcStatus {
  serverId: string;
  source: BmcDataSource;
  protocol: BmcProtocol;
  power: "On" | "Off";
  health: Health;
  bootProgress: string;
  cpuTempC: number;
  inletTempC: number;
  fans: { name: string; rpm: number; status: Health }[];
  psus: {
    name: string;
    watts: number;
    capacityW: number;
    status: Health;
  }[];
  alerts: { id: string; time: string; level: Health; message: string }[];
  history: { t: string; cpu: number; inlet: number; power: number }[];
  updatedAt: string;
  /** Last time a real (non-simulated) sample was collected. */
  collectedAt?: string;
  /** CPU summary from BMC (Redfish ProcessorSummary). */
  processorSummary?: { count: number; model: string };
  /** Memory summary from BMC (Redfish MemorySummary). */
  memorySummary?: { totalGiB: number };
  /** Storage drives discovered via Redfish. */
  drives?: {
    name: string;
    model: string;
    sn?: string;
    capacityGB: number;
    mediaType: string;
    status: string;
  }[];
  /** Recent BMC log entries (Redfish LogServices). */
  recentLogs?: {
    id: string;
    severity: string;
    message: string;
    createdAt: string;
  }[];
}

export type PartCategory = "disk" | "memory" | "nic" | "optical" | "other";
export type PartStatus = "in_stock" | "allocated" | "in_use" | "scrapped";
export type PartItemStatus = "in_stock" | "allocated" | "in_use" | "scrapped";

export interface PartItem {
  id: string;
  partId: string;
  sn?: string;
  status: PartItemStatus;
  location?: string;
  installedServerId?: string;
  installedServerHostname?: string;
  partBrand?: string;
  partModel?: string;
  partSpec?: string;
  partCategory?: PartCategory;
  remark?: string;
  createdAt: string;
}

export interface Part {
  id: string;
  category: PartCategory;
  brand: string;
  model: string;
  spec: string;
  sn?: string;
  stock: number;
  safetyStock: number;
  unit: string;
  location: string;
  status: PartStatus;
  itemCount: number;
  statusCounts: Record<string, number>;
  remark?: string;
  createdAt: string;
}

export type MovementType = "inbound" | "outbound" | "return" | "scrap";

export interface StockMovement {
  id: string;
  partId: string;
  partModel: string;
  category: PartCategory;
  type: MovementType;
  quantity: number;
  operator: string;
  relatedServerId?: string;
  relatedServerHostname?: string;
  partItemId?: string;
  partItemSn?: string;
  reason: string;
  time: string;
}

export interface AppUser {
  id: string;
  username: string;
  name: string;
  email: string;
  role: Role;
  enabled: boolean;
  isDeleted?: boolean;
  passwordChangeRequired?: boolean;
  failedLoginAttempts?: number;
  lockedUntil?: string;
  lastLogin?: string;
}

/** Payload for creating a new user. */
export interface CreateUserPayload {
  username: string;
  name: string;
  email: string;
  password: string;
  role: Role;
}

/** Payload for changing own password. */
export interface ChangePasswordPayload {
  old_password: string;
  new_password: string;
}

/** Payload for admin resetting another user's password. */
export interface ResetPasswordPayload {
  password: string;
}

/** Response envelope for paginated user list. */
export interface UserPage {
  items: AppUser[];
  total: number;
}

/** Filters for user list query. */
export interface UserFilters {
  q?: string;
  role?: Role;
  enabled?: number;
  limit?: number;
  offset?: number;
}

export interface AuditEntry {
  id: string;
  time: string;
  actor: string;
  action: string;
  target: string;
  detail: string;
  level: "info" | "warn" | "danger";
}

/** Filters accepted by listAuditLogs(). All fields are optional. */
export interface AuditFilters {
  /** Free-text search across actor / action / target / detail. */
  q?: string;
  level?: AuditEntry["level"];
  /** Match by exact action name, or prefix (e.g. "server."). */
  action?: string;
  /** Match by exact actor (operator username). */
  actor?: string;
  /** Substring match against the `target` field, e.g. "srv:bj-prod". */
  target?: string;
  /** ISO timestamp lower bound (inclusive). */
  start?: string;
  /** ISO timestamp upper bound (exclusive). */
  end?: string;
  limit?: number;
  offset?: number;
}

export interface AuditPage {
  items: AuditEntry[];
  total: number;
}
