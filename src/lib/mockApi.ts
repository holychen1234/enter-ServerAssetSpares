// Mock API layer. All UI components call functions from this file.
// Replace internal implementations with real `fetch` calls when the
// backend is ready — UI signatures remain unchanged.

import { mockServers } from "@/mocks/servers";
import { mockParts, mockMovements } from "@/mocks/parts";
import { mockUsers, mockAuditLogs } from "@/mocks/users";
import type {
  Server,
  Part,
  StockMovement,
  AppUser,
  AuditEntry,
  BmcStatus,
  Health,
} from "@/types/cmdb";

const wait = (ms = 300) => new Promise((r) => setTimeout(r, ms));

let serversDb: Server[] = [...mockServers];
let partsDb: Part[] = [...mockParts];
let movementsDb: StockMovement[] = [...mockMovements];
let usersDb: AppUser[] = [...mockUsers];
const auditDb: AuditEntry[] = [...mockAuditLogs];

const uid = (prefix: string) =>
  `${prefix}-${Math.random().toString(36).slice(2, 8)}`;

// ---------- Servers ----------
export async function listServers(): Promise<Server[]> {
  await wait(200);
  return [...serversDb];
}

export async function getServer(id: string): Promise<Server | undefined> {
  await wait(150);
  return serversDb.find((s) => s.id === id);
}

export async function createServer(
  data: Omit<Server, "id" | "createdAt" | "updatedAt">,
): Promise<Server> {
  await wait(250);
  const server: Server = {
    ...data,
    id: uid("srv"),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  serversDb = [server, ...serversDb];
  return server;
}

export async function updateServer(
  id: string,
  patch: Partial<Server>,
): Promise<Server> {
  await wait(250);
  serversDb = serversDb.map((s) =>
    s.id === id ? { ...s, ...patch, updatedAt: new Date().toISOString() } : s,
  );
  return serversDb.find((s) => s.id === id)!;
}

export async function deleteServer(id: string): Promise<void> {
  await wait(200);
  serversDb = serversDb.filter((s) => s.id !== id);
}

// ---------- BMC realtime status (simulated) ----------
function rand(min: number, max: number) {
  return Math.round((Math.random() * (max - min) + min) * 10) / 10;
}

function genHistory(seed: number) {
  const out = [];
  const baseCpu = 55 + (seed % 12);
  const baseInlet = 22 + (seed % 4);
  const basePower = 320 + (seed % 60);
  for (let i = 11; i >= 0; i--) {
    out.push({
      t: `${i * 5}m`,
      cpu: Math.max(20, Math.min(95, baseCpu + rand(-6, 8))),
      inlet: Math.max(15, Math.min(35, baseInlet + rand(-2, 2))),
      power: Math.max(150, basePower + rand(-40, 50)),
    });
  }
  return out;
}

export async function getBmcStatus(serverId: string): Promise<BmcStatus> {
  await wait(180);
  const seed = serverId.length + (serverId.charCodeAt(serverId.length - 1) || 0);
  const server = serversDb.find((s) => s.id === serverId);
  const isOffline = server?.status === "offline" || server?.status === "retired";
  const isMaint = server?.status === "maintenance";
  const cpuTemp = isOffline ? 0 : rand(48, 78);
  const inlet = isOffline ? 0 : rand(20, 28);
  const health: Health = isOffline
    ? "Critical"
    : cpuTemp > 75
      ? "Warning"
      : isMaint
        ? "Warning"
        : "OK";
  const fans = Array.from({ length: 6 }).map((_, i) => ({
    name: `Fan${i + 1}`,
    rpm: isOffline ? 0 : Math.round(rand(4200, 7800)),
    status: isOffline ? ("Critical" as Health) : ("OK" as Health),
  }));
  const psus = [
    {
      name: "PSU1",
      watts: isOffline ? 0 : Math.round(rand(180, 360)),
      capacityW: 800,
      status: isOffline ? ("Critical" as Health) : ("OK" as Health),
    },
    {
      name: "PSU2",
      watts: isOffline ? 0 : Math.round(rand(180, 360)),
      capacityW: 800,
      status: isOffline ? ("Critical" as Health) : ("OK" as Health),
    },
  ];
  const alerts = isOffline
    ? [
        {
          id: uid("al"),
          time: new Date().toISOString(),
          level: "Critical" as Health,
          message: "BMC unreachable / 设备离线",
        },
      ]
    : cpuTemp > 75
      ? [
          {
            id: uid("al"),
            time: new Date().toISOString(),
            level: "Warning" as Health,
            message: `CPU 温度 ${cpuTemp}°C 超过阈值 75°C`,
          },
        ]
      : [];
  return {
    serverId,
    power: isOffline ? "Off" : "On",
    health,
    bootProgress: isOffline ? "PowerOff" : "OSBootCompleted",
    cpuTempC: cpuTemp,
    inletTempC: inlet,
    fans,
    psus,
    alerts,
    history: genHistory(seed),
    updatedAt: new Date().toISOString(),
  };
}

// ---------- Parts ----------
export async function listParts(): Promise<Part[]> {
  await wait(180);
  return [...partsDb];
}

export async function getPart(id: string): Promise<Part | undefined> {
  await wait(150);
  return partsDb.find((p) => p.id === id);
}

export async function createPart(
  data: Omit<Part, "id" | "createdAt">,
): Promise<Part> {
  await wait(200);
  const part: Part = {
    ...data,
    id: uid("part"),
    createdAt: new Date().toISOString(),
  };
  partsDb = [part, ...partsDb];
  return part;
}

export async function updatePart(
  id: string,
  patch: Partial<Part>,
): Promise<Part> {
  await wait(200);
  partsDb = partsDb.map((p) => (p.id === id ? { ...p, ...patch } : p));
  return partsDb.find((p) => p.id === id)!;
}

export async function deletePart(id: string): Promise<void> {
  await wait(200);
  partsDb = partsDb.filter((p) => p.id !== id);
}

// ---------- Movements ----------
export async function listMovements(): Promise<StockMovement[]> {
  await wait(180);
  return [...movementsDb].sort((a, b) => (a.time < b.time ? 1 : -1));
}

export async function createMovement(
  data: Omit<StockMovement, "id" | "time" | "partModel" | "category">,
): Promise<StockMovement> {
  await wait(220);
  const part = partsDb.find((p) => p.id === data.partId);
  if (!part) throw new Error("备件不存在");
  let stockDelta = 0;
  switch (data.type) {
    case "inbound":
    case "return":
      stockDelta = data.quantity;
      break;
    case "outbound":
    case "scrap":
      stockDelta = -data.quantity;
      break;
  }
  if (part.stock + stockDelta < 0) throw new Error("库存不足");
  partsDb = partsDb.map((p) =>
    p.id === part.id ? { ...p, stock: p.stock + stockDelta } : p,
  );
  const server =
    data.relatedServerId
      ? serversDb.find((s) => s.id === data.relatedServerId)
      : undefined;
  const mv: StockMovement = {
    ...data,
    id: uid("mv"),
    time: new Date().toISOString(),
    partModel: `${part.brand} ${part.model}`,
    category: part.category,
    relatedServerHostname: server?.hostname,
  };
  movementsDb = [mv, ...movementsDb];
  return mv;
}

// ---------- Users ----------
export async function listUsers(): Promise<AppUser[]> {
  await wait(150);
  return [...usersDb];
}

export async function updateUser(
  id: string,
  patch: Partial<AppUser>,
): Promise<AppUser> {
  await wait(180);
  usersDb = usersDb.map((u) => (u.id === id ? { ...u, ...patch } : u));
  return usersDb.find((u) => u.id === id)!;
}

// ---------- Audit ----------
export async function listAuditLogs(): Promise<AuditEntry[]> {
  await wait(180);
  return [...auditDb].sort((a, b) => (a.time < b.time ? 1 : -1));
}

// ---------- Auth (front-end mock) ----------
const AUTH_USERS: Record<string, { password: string; user: AppUser }> = {
  admin: {
    password: "admin123",
    user: usersDb.find((u) => u.username === "admin")!,
  },
  operator: {
    password: "123456",
    user: usersDb.find((u) => u.username === "operator")!,
  },
  viewer: {
    password: "123456",
    user: usersDb.find((u) => u.username === "viewer")!,
  },
};

export async function login(
  username: string,
  password: string,
): Promise<AppUser> {
  await wait(400);
  const entry = AUTH_USERS[username];
  if (!entry || entry.password !== password) {
    throw new Error("用户名或密码错误");
  }
  if (!entry.user.enabled) throw new Error("账号已被禁用");
  return entry.user;
}
