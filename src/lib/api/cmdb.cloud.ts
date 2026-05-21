// Real backend layer. Exposes the same function signatures the pages
// were already using against the previous mock layer, so swapping is a
// one-line import change.
import { supabase } from "@/integrations/supabase/client";
import type {
  AppUser,
  AuditEntry,
  BmcStatus,
  Part,
  Server,
  StockMovement,
} from "@/types/cmdb";
import {
  partToRow,
  rowToAudit,
  rowToMovement,
  rowToPart,
  rowToProfile,
  rowToServer,
  serverToRow,
} from "./mappers";

// ---------- helper ----------
async function currentActorName(): Promise<string> {
  const { data } = await supabase.auth.getUser();
  const meta = data.user?.user_metadata as Record<string, unknown> | undefined;
  return (
    (meta?.username as string) ||
    (meta?.name as string) ||
    data.user?.email ||
    "system"
  );
}

async function writeAudit(
  action: string,
  target: string,
  detail: string,
  level: AuditEntry["level"] = "info",
) {
  const actor = await currentActorName();
  await supabase
    .from("audit_logs")
    .insert({ actor, action, target, detail, level });
}

// ---------- Servers ----------
export async function listServers(): Promise<Server[]> {
  const { data, error } = await supabase
    .from("servers")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []).map(rowToServer);
}

export async function getServer(id: string): Promise<Server | undefined> {
  const { data, error } = await supabase
    .from("servers")
    .select("*")
    .eq("id", id)
    .maybeSingle();
  if (error) throw error;
  return data ? rowToServer(data) : undefined;
}

export async function createServer(
  data: Omit<Server, "id" | "createdAt" | "updatedAt">,
): Promise<Server> {
  const { data: row, error } = await supabase
    .from("servers")
    .insert(serverToRow(data))
    .select("*")
    .single();
  if (error) throw error;
  await writeAudit(
    "server.create",
    `srv:${row.hostname}`,
    `录入主机 ${row.hostname}`,
  );
  return rowToServer(row);
}

export async function updateServer(
  id: string,
  patch: Partial<Server>,
): Promise<Server> {
  // map only provided fields
  const dbPatch: Record<string, unknown> = {};
  if (patch.hostname !== undefined) dbPatch.hostname = patch.hostname;
  if (patch.sn !== undefined) dbPatch.sn = patch.sn;
  if (patch.assetTag !== undefined) dbPatch.asset_tag = patch.assetTag;
  if (patch.manufacturer !== undefined) dbPatch.manufacturer = patch.manufacturer;
  if (patch.model !== undefined) dbPatch.model = patch.model;
  if (patch.cpuModel !== undefined) dbPatch.cpu_model = patch.cpuModel;
  if (patch.cpuCount !== undefined) dbPatch.cpu_count = patch.cpuCount;
  if (patch.memoryGB !== undefined) dbPatch.memory_gb = patch.memoryGB;
  if (patch.diskCount !== undefined) dbPatch.disk_count = patch.diskCount;
  if (patch.location) {
    dbPatch.idc = patch.location.idc;
    dbPatch.rack = patch.location.rack;
    dbPatch.u_position = patch.location.uPosition;
  }
  if (patch.mgmtIp !== undefined) dbPatch.mgmt_ip = patch.mgmtIp;
  if (patch.bizIp !== undefined) dbPatch.biz_ip = patch.bizIp;
  if (patch.bmcProtocol !== undefined) dbPatch.bmc_protocol = patch.bmcProtocol;
  if (patch.bmcUser !== undefined) dbPatch.bmc_user = patch.bmcUser;
  // Only update bmc_password when explicitly set to a non-empty string.
  if (patch.bmcPassword !== undefined && patch.bmcPassword !== "") {
    dbPatch.bmc_password = patch.bmcPassword;
  }
  if (patch.status !== undefined) dbPatch.status = patch.status;
  if (patch.owner !== undefined) dbPatch.owner = patch.owner;
  if (patch.purchaseDate !== undefined) dbPatch.purchase_date = patch.purchaseDate || null;
  if (patch.warrantyEnd !== undefined) dbPatch.warranty_end = patch.warrantyEnd || null;
  if (patch.tags !== undefined) dbPatch.tags = patch.tags;
  if (patch.remark !== undefined) dbPatch.remark = patch.remark ?? null;

  const { data: row, error } = await supabase
    .from("servers")
    .update(dbPatch)
    .eq("id", id)
    .select("*")
    .single();
  if (error) throw error;
  await writeAudit("server.update", `srv:${row.hostname}`, "更新主机信息");
  return rowToServer(row);
}

export async function deleteServer(id: string): Promise<void> {
  const { data: row } = await supabase
    .from("servers")
    .select("hostname")
    .eq("id", id)
    .maybeSingle();
  const { error } = await supabase.from("servers").delete().eq("id", id);
  if (error) throw error;
  if (row)
    await writeAudit("server.delete", `srv:${row.hostname}`, "删除主机", "warn");
}

export async function batchDeleteServers(ids: string[]): Promise<void> {
  // Fetch hostnames for audit before deleting
  const { data: rows } = await supabase
    .from("servers")
    .select("id, hostname")
    .in("id", ids);
  const hostnames = (rows || []).map((r: { hostname: string }) => r.hostname);
  const { error } = await supabase.from("servers").delete().in("id", ids);
  if (error) throw error;
  if (hostnames.length > 0) {
    await writeAudit(
      "server.batch_delete",
      `srv:${hostnames.length}台主机`,
      hostnames.join(", "),
      "warn",
    );
  }
}

// ---------- BMC live status ----------
export async function getBmcStatus(
  serverId: string,
  _opts: { force?: boolean } = {},
): Promise<BmcStatus> {
  // The edge function always pulls fresh from the BMC — there is no
  // server-side cache to bypass — so `force` is accepted for API parity
  // with the on-prem client but otherwise ignored.
  const { data, error } = await supabase.functions.invoke("bmc-status", {
    body: { serverId },
  });
  if (error) throw error;
  return data as BmcStatus;
}

// ---------- Parts ----------
export async function listParts(): Promise<Part[]> {
  const { data, error } = await supabase
    .from("parts")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []).map(rowToPart);
}

export async function getPart(id: string): Promise<Part | undefined> {
  const { data, error } = await supabase
    .from("parts")
    .select("*")
    .eq("id", id)
    .maybeSingle();
  if (error) throw error;
  return data ? rowToPart(data) : undefined;
}

export async function createPart(
  data: Omit<Part, "id" | "createdAt">,
): Promise<Part> {
  const { data: row, error } = await supabase
    .from("parts")
    .insert(partToRow(data))
    .select("*")
    .single();
  if (error) throw error;
  await writeAudit("part.create", `part:${row.brand} ${row.model}`, "新建备件");
  return rowToPart(row);
}

export async function updatePart(
  id: string,
  patch: Partial<Part>,
): Promise<Part> {
  const dbPatch: Record<string, unknown> = {};
  if (patch.category !== undefined) dbPatch.category = patch.category;
  if (patch.brand !== undefined) dbPatch.brand = patch.brand;
  if (patch.model !== undefined) dbPatch.model = patch.model;
  if (patch.spec !== undefined) dbPatch.spec = patch.spec;
  if (patch.sn !== undefined) dbPatch.sn = patch.sn ?? null;
  if (patch.stock !== undefined) dbPatch.stock = patch.stock;
  if (patch.safetyStock !== undefined) dbPatch.safety_stock = patch.safetyStock;
  if (patch.unit !== undefined) dbPatch.unit = patch.unit;
  if (patch.location !== undefined) dbPatch.location = patch.location;
  if (patch.status !== undefined) dbPatch.status = patch.status;
  if (patch.remark !== undefined) dbPatch.remark = patch.remark ?? null;

  const { data: row, error } = await supabase
    .from("parts")
    .update(dbPatch)
    .eq("id", id)
    .select("*")
    .single();
  if (error) throw error;
  await writeAudit("part.update", `part:${row.brand} ${row.model}`, "更新备件");
  return rowToPart(row);
}

export async function deletePart(id: string): Promise<void> {
  const { data: row } = await supabase
    .from("parts")
    .select("brand, model")
    .eq("id", id)
    .maybeSingle();
  const { error } = await supabase.from("parts").delete().eq("id", id);
  if (error) throw error;
  if (row)
    await writeAudit(
      "part.delete",
      `part:${row.brand} ${row.model}`,
      "删除备件",
      "warn",
    );
}

// ---------- Movements ----------
export async function listMovements(): Promise<StockMovement[]> {
  const { data, error } = await supabase
    .from("stock_movements")
    .select("*, parts(brand, model, category), servers(hostname)")
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []).map((r) => rowToMovement(r));
}

export async function createMovement(
  data: Omit<StockMovement, "id" | "time" | "partModel" | "category">,
): Promise<StockMovement> {
  const operator = data.operator || (await currentActorName());
  const { data: row, error } = await supabase
    .from("stock_movements")
    .insert({
      part_id: data.partId,
      type: data.type,
      quantity: data.quantity,
      operator,
      related_server_id: data.relatedServerId ?? null,
      reason: data.reason,
    })
    .select("*, parts(brand, model, category), servers(hostname)")
    .single();
  if (error) throw error;
  return rowToMovement(row);
}

// ---------- Users (profiles) ----------
export async function listUsers(
  filters: import("@/types/cmdb").UserFilters = {},
): Promise<import("@/types/cmdb").UserPage> {
  const limit = Math.min(Math.max(filters.limit ?? 50, 1), 200);
  const offset = Math.max(filters.offset ?? 0, 0);

  let q = supabase
    .from("profiles")
    .select("*", { count: "exact" })
    .eq("is_deleted", false)
    .order("created_at", { ascending: false });

  if (filters.role) q = q.eq("role", filters.role);
  if (filters.enabled !== undefined) q = q.eq("enabled", filters.enabled);
  if (filters.q) {
    const kw = filters.q.replace(/[%_]/g, "");
    q = q.or(`username.ilike.%${kw}%,name.ilike.%${kw}%,email.ilike.%${kw}%`);
  }
  q = q.range(offset, offset + limit - 1);

  const { data, error, count } = await q;
  if (error) throw error;
  return {
    items: (data ?? []).map(rowToProfile),
    total: count ?? (data?.length ?? 0),
  };
}

export async function createUser(
  data: import("@/types/cmdb").CreateUserPayload,
): Promise<AppUser> {
  const { data: row, error } = await supabase
    .from("profiles")
    .insert({
      username: data.username,
      name: data.name,
      email: data.email,
      password_hash: data.password, // Supabase Auth handles hashing
      role: data.role,
      enabled: true,
      password_change_required: true,
    })
    .select("*")
    .single();
  if (error) throw error;
  await writeAudit(
    "user.create",
    `user:${data.username}`,
    `创建用户 ${data.username}（角色：${data.role}）`,
    "warn",
  );
  return rowToProfile(row);
}

export async function updateUser(
  id: string,
  patch: Partial<AppUser>,
): Promise<AppUser> {
  const dbPatch: Record<string, unknown> = {};
  if (patch.username !== undefined) dbPatch.username = patch.username;
  if (patch.name !== undefined) dbPatch.name = patch.name;
  if (patch.email !== undefined) dbPatch.email = patch.email;
  if (patch.role !== undefined) dbPatch.role = patch.role;
  if (patch.enabled !== undefined) dbPatch.enabled = patch.enabled;
  if (patch.passwordChangeRequired !== undefined)
    dbPatch.password_change_required = patch.passwordChangeRequired;
  if (patch.isDeleted !== undefined) dbPatch.is_deleted = patch.isDeleted;
  const { data: row, error } = await supabase
    .from("profiles")
    .update(dbPatch)
    .eq("id", id)
    .select("*")
    .single();
  if (error) throw error;
  await writeAudit(
    "user.update",
    `user:${row.username}`,
    `更新账号信息（角色=${row.role}, 启用=${row.enabled}）`,
    "warn",
  );
  return rowToProfile(row);
}

export async function deleteUser(id: string): Promise<void> {
  const { data: row } = await supabase
    .from("profiles")
    .select("username")
    .eq("id", id)
    .maybeSingle();
  const { error } = await supabase
    .from("profiles")
    .update({ is_deleted: true, enabled: false })
    .eq("id", id);
  if (error) throw error;
  if (row)
    await writeAudit(
      "user.delete",
      `user:${row.username}`,
      `删除用户 ${row.username}（软删除）`,
      "warn",
    );
}

export async function resetUserPassword(
  id: string,
  password: string,
): Promise<void> {
  const { data: row } = await supabase
    .from("profiles")
    .select("username")
    .eq("id", id)
    .maybeSingle();
  const { error } = await supabase
    .from("profiles")
    .update({
      password_hash: password,
      password_change_required: true,
      failed_login_attempts: 0,
      locked_until: null,
    })
    .eq("id", id);
  if (error) throw error;
  if (row)
    await writeAudit(
      "user.password_reset",
      `user:${row.username}`,
      `重置用户 ${row.username} 的密码`,
      "warn",
    );
}

export async function changeMyPassword(
  oldPassword: string,
  newPassword: string,
): Promise<AppUser> {
  // Verify old password first by re-authenticating
  const { data: authUser } = await supabase.auth.getUser();
  if (!authUser.user?.email) throw new Error("未登录");

  const { error: signInErr } = await supabase.auth.signInWithPassword({
    email: authUser.user.email,
    password: oldPassword,
  });
  if (signInErr) throw new Error("原密码错误");

  const { error: updateErr } = await supabase.auth.updateUser({
    password: newPassword,
  });
  if (updateErr) throw updateErr;

  // Update profile record
  await supabase
    .from("profiles")
    .update({ password_change_required: false })
    .eq("id", authUser.user.id);

  const { data: profile } = await supabase
    .from("profiles")
    .select("*")
    .eq("id", authUser.user.id)
    .single();
  if (!profile) throw new Error("用户档案缺失");
  return rowToProfile(profile);
}

export async function unlockUser(id: string): Promise<void> {
  const { error } = await supabase
    .from("profiles")
    .update({ failed_login_attempts: 0, locked_until: null })
    .eq("id", id);
  if (error) throw error;
}

// ---------- Audit ----------
export async function listAuditLogs(
  filters: import("@/types/cmdb").AuditFilters = {},
): Promise<import("@/types/cmdb").AuditPage> {
  const limit = Math.min(Math.max(filters.limit ?? 50, 1), 500);
  const offset = Math.max(filters.offset ?? 0, 0);

  let q = supabase
    .from("audit_logs")
    .select("*", { count: "exact" })
    .order("created_at", { ascending: false });

  if (filters.level) q = q.eq("level", filters.level);
  if (filters.actor) q = q.eq("actor", filters.actor);
  if (filters.action) {
    if (filters.action.endsWith(".")) {
      q = q.like("action", `${filters.action}%`);
    } else {
      q = q.eq("action", filters.action);
    }
  }
  if (filters.target) q = q.ilike("target", `%${filters.target}%`);
  if (filters.start) q = q.gte("created_at", filters.start);
  if (filters.end) q = q.lt("created_at", filters.end);
  if (filters.q) {
    const kw = filters.q.replace(/[%_]/g, "");
    q = q.or(
      `actor.ilike.%${kw}%,action.ilike.%${kw}%,target.ilike.%${kw}%,detail.ilike.%${kw}%`,
    );
  }
  q = q.range(offset, offset + limit - 1);

  const { data, error, count } = await q;
  if (error) throw error;
  return {
    items: (data ?? []).map(rowToAudit),
    total: count ?? (data?.length ?? 0),
  };
}

// ---------- Auth (helper) ----------
export async function signInWithUsername(
  username: string,
  password: string,
): Promise<AppUser> {
  // Convention: <username>@corp.local
  const email = username.includes("@") ? username : `${username}@corp.local`;
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });
  if (error) throw new Error("用户名或密码错误");
  if (!data.user) throw new Error("登录失败");

  const { data: profile, error: pErr } = await supabase
    .from("profiles")
    .select("*")
    .eq("id", data.user.id)
    .maybeSingle();
  if (pErr) throw pErr;
  if (!profile) throw new Error("用户档案缺失");
  if (!profile.enabled) {
    await supabase.auth.signOut();
    throw new Error("账号已被禁用");
  }

  // best-effort last_login update + audit
  await supabase
    .from("profiles")
    .update({ last_login: new Date().toISOString() })
    .eq("id", data.user.id);
  await supabase.from("audit_logs").insert({
    actor: profile.username,
    action: "user.login",
    target: "session",
    detail: "登录系统",
    level: "info",
  });

  return rowToProfile(profile);
}

export async function signOut(): Promise<void> {
  // best-effort: write a logout audit entry while we still have a session
  const { data } = await supabase.auth.getUser();
  if (data.user) {
    const { data: profile } = await supabase
      .from("profiles")
      .select("username")
      .eq("id", data.user.id)
      .maybeSingle();
    if (profile?.username) {
      await supabase.from("audit_logs").insert({
        actor: profile.username,
        action: "user.logout",
        target: "session",
        detail: "退出登录",
        level: "info",
      });
    }
  }
  await supabase.auth.signOut();
}

export async function fetchCurrentProfile(): Promise<AppUser | null> {
  const { data } = await supabase.auth.getUser();
  if (!data.user) return null;
  const { data: profile } = await supabase
    .from("profiles")
    .select("*")
    .eq("id", data.user.id)
    .maybeSingle();
  return profile ? rowToProfile(profile) : null;
}

// Subscribe to backend-side auth events. Cloud uses Supabase realtime auth
// events; internal backend has none, so it returns a no-op unsubscribe.
export function subscribeAuthChanges(
  cb: (hasSession: boolean) => void,
): () => void {
  const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
    cb(!!session);
  });
  return () => sub.subscription.unsubscribe();
}
