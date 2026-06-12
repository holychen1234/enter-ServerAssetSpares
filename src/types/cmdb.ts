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
  /** Last time a snapshot was persisted to the database (ISO 8601). */
  lastCollectedAt?: string | null;
  /** CPU summary from BMC (Redfish ProcessorSummary). */
  processorSummary?: { count: number; model: string };
  /** Memory summary from BMC (Redfish MemorySummary). */
  memorySummary?: { totalGiB: number };
  /** Individual DIMM modules discovered via Redfish /Systems/X/Memory. */
  memoryModules?: {
    slot: string;
    model: string;
    sn?: string;
    capacityMiB: number;
    memoryType: string;
    status: string;
    populated?: boolean;
  }[];
  /** Storage drives discovered via Redfish. */
  drives?: {
    name: string;
    model: string;
    sn?: string;
    capacityGB: number;
    mediaType: string;
    status: string;
  }[];
  /** Summary of memory slot population. */
  memorySlotSummary?: { populated: number; total: number };
  /** Summary of drive bay population. */
  driveBaySummary?: { populated: number; total: number };
  /** Recent BMC log entries (Redfish LogServices). */
  recentLogs?: {
    id: string;
    severity: string;
    message: string;
    createdAt: string;
  }[];
}

// ── TerminalAsset ──────────────────────────────────────────

export type TerminalAssetManufacturer =
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

/** Note: no `monitors` — by design, terminal assets do not track
 *  display accessories during manual entry or batch import. */
export interface TerminalAsset {
  id: string;
  hostname: string;
  sn: string;
  assetTag: string;
  manufacturer: TerminalAssetManufacturer;
  model: string;
  cpuModel: string;
  cpuCount: number;
  memoryGB: number;
  diskType: string;
  diskCapacityGB: number;
  macAddress?: string;
  os: OperatingSystem;
  osVersion?: string;
  bizIp?: string;
  userName?: string;
  status: ServerStatus;
  purchaseDate?: string;
  warrantyEnd?: string;
  tags: string[];
  remark?: string;
  createdAt: string;
  updatedAt: string;
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
