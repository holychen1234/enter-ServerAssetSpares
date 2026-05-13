// Mapping helpers: DB rows (snake_case) <-> domain types (camelCase).
import type { Database } from "@/integrations/supabase/types";
import type {
  AppUser,
  AuditEntry,
  Manufacturer,
  Part,
  Server,
  StockMovement,
} from "@/types/cmdb";

type ServerRow = Database["public"]["Tables"]["servers"]["Row"];
type PartRow = Database["public"]["Tables"]["parts"]["Row"];
type ProfileRow = Database["public"]["Tables"]["profiles"]["Row"];
type AuditRow = Database["public"]["Tables"]["audit_logs"]["Row"];
type MovementRow = Database["public"]["Tables"]["stock_movements"]["Row"];

export function rowToServer(r: ServerRow): Server {
  return {
    id: r.id,
    hostname: r.hostname,
    sn: r.sn,
    assetTag: r.asset_tag,
    manufacturer: r.manufacturer as Manufacturer,
    model: r.model,
    cpuModel: r.cpu_model,
    cpuCount: r.cpu_count,
    memoryGB: r.memory_gb,
    diskCount: r.disk_count,
    location: { idc: r.idc, rack: r.rack, uPosition: r.u_position },
    mgmtIp: r.mgmt_ip,
    bizIp: r.biz_ip,
    bmcProtocol: r.bmc_protocol,
    bmcUser: r.bmc_user,
    bmcPasswordSet: !!r.bmc_password,
    status: r.status,
    owner: r.owner ?? "",
    purchaseDate: r.purchase_date ?? "",
    warrantyEnd: r.warranty_end ?? "",
    tags: r.tags ?? [],
    remark: r.remark ?? undefined,
    createdAt: r.created_at,
    updatedAt: r.updated_at,
  };
}

export function serverToRow(
  s: Omit<Server, "id" | "createdAt" | "updatedAt">,
): Database["public"]["Tables"]["servers"]["Insert"] {
  return {
    hostname: s.hostname,
    sn: s.sn,
    asset_tag: s.assetTag,
    manufacturer: s.manufacturer,
    model: s.model,
    cpu_model: s.cpuModel,
    cpu_count: s.cpuCount,
    memory_gb: s.memoryGB,
    disk_count: s.diskCount,
    idc: s.location.idc,
    rack: s.location.rack,
    u_position: s.location.uPosition,
    mgmt_ip: s.mgmtIp,
    biz_ip: s.bizIp,
    bmc_protocol: s.bmcProtocol,
    bmc_user: s.bmcUser,
    // Only persist bmc_password when the caller explicitly provides one.
    // Empty string is treated as "do not change".
    ...(s.bmcPassword !== undefined && s.bmcPassword !== ""
      ? { bmc_password: s.bmcPassword }
      : {}),
    status: s.status,
    owner: s.owner,
    purchase_date: s.purchaseDate || null,
    warranty_end: s.warrantyEnd || null,
    tags: s.tags,
    remark: s.remark ?? null,
  };
}

export function rowToPart(r: PartRow): Part {
  return {
    id: r.id,
    category: r.category,
    brand: r.brand,
    model: r.model,
    spec: r.spec,
    sn: r.sn ?? undefined,
    stock: r.stock,
    safetyStock: r.safety_stock,
    unit: r.unit,
    location: r.location,
    status: r.status,
    remark: r.remark ?? undefined,
    createdAt: r.created_at,
  };
}

export function partToRow(
  p: Omit<Part, "id" | "createdAt">,
): Database["public"]["Tables"]["parts"]["Insert"] {
  return {
    category: p.category,
    brand: p.brand,
    model: p.model,
    spec: p.spec,
    sn: p.sn ?? null,
    stock: p.stock,
    safety_stock: p.safetyStock,
    unit: p.unit,
    location: p.location,
    status: p.status,
    remark: p.remark ?? null,
  };
}

export function rowToProfile(r: ProfileRow): AppUser {
  return {
    id: r.id,
    username: r.username,
    name: r.name,
    email: r.email,
    role: r.role,
    enabled: r.enabled,
    lastLogin: r.last_login ?? undefined,
  };
}

export function rowToAudit(r: AuditRow): AuditEntry {
  return {
    id: r.id,
    time: r.created_at,
    actor: r.actor,
    action: r.action,
    target: r.target,
    detail: r.detail ?? "",
    level: r.level,
  };
}

export type MovementRowWithJoin = MovementRow & {
  parts?: Pick<PartRow, "brand" | "model" | "category"> | null;
  servers?: Pick<ServerRow, "hostname"> | null;
};

export function rowToMovement(r: MovementRowWithJoin): StockMovement {
  const partLabel = r.parts ? `${r.parts.brand} ${r.parts.model}` : "";
  return {
    id: r.id,
    partId: r.part_id,
    partModel: partLabel,
    category: (r.parts?.category ?? "other") as Part["category"],
    type: r.type,
    quantity: r.quantity,
    operator: r.operator,
    relatedServerId: r.related_server_id ?? undefined,
    relatedServerHostname: r.servers?.hostname ?? undefined,
    reason: r.reason,
    time: r.created_at,
  };
}
