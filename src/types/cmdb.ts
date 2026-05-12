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
  bmcProtocol: BmcProtocol;
  bmcUser: string;
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

export interface BmcStatus {
  serverId: string;
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
}

export type PartCategory = "disk" | "memory" | "nic" | "optical" | "other";
export type PartStatus = "in_stock" | "allocated" | "in_use" | "scrapped";

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
  lastLogin?: string;
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
