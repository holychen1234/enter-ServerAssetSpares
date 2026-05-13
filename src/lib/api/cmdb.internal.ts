// Internal (private-deployment) backend client. Talks to the FastAPI service
// shipped under reference-backend/. JSON shapes match Enter Cloud variant 1:1
// because the FastAPI serializers reuse the same camelCase keys.
import type {
  AppUser,
  AuditEntry,
  BmcStatus,
  Part,
  Server,
  StockMovement,
} from "@/types/cmdb";
import { INTERNAL_API_BASE } from "./mode";

const TOKEN_KEY = "cmdb.internal.token";

function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function setToken(t: string | null) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

interface FetchOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  // skip auth header (login endpoint)
  anonymous?: boolean;
}

async function api<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (!opts.anonymous) {
    const t = getToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  }
  const res = await fetch(`${INTERNAL_API_BASE}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  // Tolerate non-JSON responses (e.g. nginx "Internal Server Error" text,
  // FastAPI HTML error pages). Without this, JSON.parse throws a confusing
  // "Unexpected identifier" message and hides the real status code.
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!res.ok) {
    const d = data as { detail?: unknown; message?: unknown; error?: unknown } | undefined;
    const raw = d?.detail ?? d?.message ?? d?.error ?? res.statusText ?? "请求失败";
    const msg =
      typeof raw === "string" ? raw : JSON.stringify(raw);
    throw new Error(`[${res.status}] ${msg}`);
  }
  return data as T;
}

// ---------- Servers ----------
export async function listServers(): Promise<Server[]> {
  return api<Server[]>("/servers");
}

export async function getServer(id: string): Promise<Server | undefined> {
  try {
    return await api<Server>(`/servers/${id}`);
  } catch {
    return undefined;
  }
}

export async function createServer(
  data: Omit<Server, "id" | "createdAt" | "updatedAt">,
): Promise<Server> {
  return api<Server>("/servers", { method: "POST", body: data });
}

export async function updateServer(
  id: string,
  patch: Partial<Server>,
): Promise<Server> {
  return api<Server>(`/servers/${id}`, { method: "PATCH", body: patch });
}

export async function deleteServer(id: string): Promise<void> {
  await api<void>(`/servers/${id}`, { method: "DELETE" });
}

// ---------- BMC ----------
export async function getBmcStatus(serverId: string): Promise<BmcStatus> {
  return api<BmcStatus>(`/servers/${serverId}/bmc`);
}

// ---------- Parts ----------
export async function listParts(): Promise<Part[]> {
  return api<Part[]>("/parts");
}

export async function getPart(id: string): Promise<Part | undefined> {
  try {
    return await api<Part>(`/parts/${id}`);
  } catch {
    return undefined;
  }
}

export async function createPart(
  data: Omit<Part, "id" | "createdAt">,
): Promise<Part> {
  return api<Part>("/parts", { method: "POST", body: data });
}

export async function updatePart(
  id: string,
  patch: Partial<Part>,
): Promise<Part> {
  return api<Part>(`/parts/${id}`, { method: "PATCH", body: patch });
}

export async function deletePart(id: string): Promise<void> {
  await api<void>(`/parts/${id}`, { method: "DELETE" });
}

// ---------- Movements ----------
export async function listMovements(): Promise<StockMovement[]> {
  return api<StockMovement[]>("/stock-movements");
}

export async function createMovement(
  data: Omit<StockMovement, "id" | "time" | "partModel" | "category">,
): Promise<StockMovement> {
  return api<StockMovement>("/stock-movements", {
    method: "POST",
    body: data,
  });
}

// ---------- Users ----------
export async function listUsers(): Promise<AppUser[]> {
  return api<AppUser[]>("/users");
}

export async function updateUser(
  id: string,
  patch: Partial<AppUser>,
): Promise<AppUser> {
  return api<AppUser>(`/users/${id}`, { method: "PATCH", body: patch });
}

// ---------- Audit ----------
export async function listAuditLogs(): Promise<AuditEntry[]> {
  return api<AuditEntry[]>("/audit-logs");
}

// ---------- Auth ----------
interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AppUser;
}

export async function signInWithUsername(
  username: string,
  password: string,
): Promise<AppUser> {
  const res = await api<LoginResponse>("/auth/login", {
    method: "POST",
    body: { username, password },
    anonymous: true,
  });
  setToken(res.access_token);
  return res.user;
}

export async function signOut(): Promise<void> {
  setToken(null);
}

export async function fetchCurrentProfile(): Promise<AppUser | null> {
  if (!getToken()) return null;
  try {
    return await api<AppUser>("/auth/me");
  } catch {
    setToken(null);
    return null;
  }
}

// Internal backend has no realtime auth events. The token lives in
// localStorage; AuthContext does its own initial check on mount. Provide a
// no-op subscriber so the context interface stays uniform.
export function subscribeAuthChanges(
  _cb: (hasSession: boolean) => void,
): () => void {
  return () => {
    /* no-op */
  };
}
