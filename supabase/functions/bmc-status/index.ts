// BMC live-status proxy.
// - For servers with bmc_protocol = 'redfish' AND a reachable Redfish endpoint
//   (mgmt_ip), it queries Chassis (Power+Thermal) and Systems collections,
//   discovering the first member dynamically. If unavailable, falls back to
//   a deterministic simulation so the UI keeps working.
// - For servers with bmc_protocol = 'ipmi', it returns a simulation marked
//   with an info alert telling the operator that an internal IPMI collector
//   is required (cannot run from edge runtime).
//
// Authenticated requests only; uses the caller's JWT to enforce RLS on the
// underlying servers row.
//
// POST body: { serverId: string, redfishBase?: string }

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

type Health = "OK" | "Warning" | "Critical";
type DataSource = "live" | "simulated";

interface BmcStatus {
  serverId: string;
  source: DataSource;
  protocol: string;
  power: "On" | "Off";
  health: Health;
  bootProgress: string;
  cpuTempC: number;
  inletTempC: number;
  fans: { name: string; rpm: number; status: Health }[];
  psus: { name: string; watts: number; capacityW: number; status: Health }[];
  alerts: { id: string; time: string; level: Health; message: string }[];
  history: { t: string; cpu: number; inlet: number; power: number }[];
  updatedAt: string;
  collectedAt?: string;
}

function rand(min: number, max: number) {
  return Math.round((Math.random() * (max - min) + min) * 10) / 10;
}
function uid() {
  return crypto.randomUUID().slice(0, 8);
}
function nowIso() {
  return new Date().toISOString();
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

function simulate(
  serverId: string,
  status: string,
  protocol: string,
): BmcStatus {
  const seed =
    serverId.length + (serverId.charCodeAt(serverId.length - 1) || 0);
  const isOffline = status === "offline" || status === "retired";
  const isMaint = status === "maintenance";
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
    status: (isOffline ? "Critical" : "OK") as Health,
  }));
  const psus = [1, 2].map((n) => ({
    name: `PSU${n}`,
    watts: isOffline ? 0 : Math.round(rand(180, 360)),
    capacityW: 800,
    status: (isOffline ? "Critical" : "OK") as Health,
  }));
  return {
    serverId,
    source: "simulated",
    protocol,
    power: isOffline ? "Off" : "On",
    health,
    bootProgress: isOffline ? "PowerOff" : "OSBootCompleted",
    cpuTempC: cpuTemp,
    inletTempC: inlet,
    fans,
    psus,
    alerts: [],
    history: genHistory(seed),
    updatedAt: nowIso(),
  };
}

async function discoverFirstMember(
  base: string,
  collection: string,
  headers: Record<string, string>,
  signal: AbortSignal,
): Promise<string | null> {
  try {
    const r = await fetch(`${base}/redfish/v1/${collection}`, {
      headers,
      signal,
    });
    if (!r.ok) return null;
    const j = await r.json();
    const m = (j.Members ?? [])[0];
    if (!m?.["@odata.id"]) return null;
    return String(m["@odata.id"]).replace(/^\/+/, "");
  } catch {
    return null;
  }
}

async function tryRedfish(
  base: string,
  user: string | null,
  password: string | null,
): Promise<Partial<BmcStatus> | null> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (user && password) {
    headers.Authorization = `Basic ${btoa(`${user}:${password}`)}`;
  }
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), 4000);
  try {
    const [chassisPath, systemPath] = await Promise.all([
      discoverFirstMember(base, "Chassis", headers, ctrl.signal),
      discoverFirstMember(base, "Systems", headers, ctrl.signal),
    ]);
    if (!chassisPath || !systemPath) return null;

    const [thermalRes, powerRes, systemRes] = await Promise.all([
      fetch(`${base}/${chassisPath}/Thermal`, {
        headers,
        signal: ctrl.signal,
      }),
      fetch(`${base}/${chassisPath}/Power`, {
        headers,
        signal: ctrl.signal,
      }),
      fetch(`${base}/${systemPath}`, { headers, signal: ctrl.signal }),
    ]);
    if (!thermalRes.ok || !systemRes.ok) return null;
    const thermal = await thermalRes.json();
    const system = await systemRes.json();
    const power = powerRes.ok ? await powerRes.json() : {};

    const findTemp = (rx: RegExp) => {
      for (const t of thermal.Temperatures ?? []) {
        if (rx.test(String(t.Name ?? ""))) {
          const v = t.ReadingCelsius;
          if (typeof v === "number") return v;
        }
      }
      for (const t of thermal.Temperatures ?? []) {
        const v = t.ReadingCelsius;
        if (typeof v === "number") return v;
      }
      return 0;
    };
    const cpuTemp = findTemp(/CPU|Proc/i);
    const inlet = findTemp(/Inlet|Intake|Ambient/i);

    type FanItem = {
      Name?: string;
      Reading?: number;
      Status?: { Health?: string };
    };
    type PsuItem = {
      Name?: string;
      PowerOutputWatts?: number;
      PowerCapacityWatts?: number;
      Status?: { Health?: string };
    };

    const fans = (thermal.Fans ?? []).map((f: FanItem, i: number) => ({
      name: f.Name ?? `Fan${i + 1}`,
      rpm: Math.round(f.Reading ?? 0),
      status: (f.Status?.Health as Health) || "OK",
    }));
    const psus = (power.PowerSupplies ?? []).map((p: PsuItem, i: number) => ({
      name: p.Name ?? `PSU${i + 1}`,
      watts: Math.round(p.PowerOutputWatts ?? 0),
      capacityW: p.PowerCapacityWatts ?? 800,
      status: (p.Status?.Health as Health) || "OK",
    }));
    const health = (system.Status?.Health as Health) || "OK";
    const powerState = (system.PowerState as string) === "On" ? "On" : "Off";

    return {
      power: powerState,
      health,
      bootProgress: system.BootProgress?.LastState ?? "Unknown",
      cpuTempC: Math.round(cpuTemp * 10) / 10,
      inletTempC: Math.round(inlet * 10) / 10,
      fans: fans.length ? fans : undefined,
      psus: psus.length ? psus : undefined,
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const auth = req.headers.get("Authorization");
    if (!auth) {
      return new Response(JSON.stringify({ error: "missing auth" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      global: { headers: { Authorization: auth } },
    });

    const body = await req.json().catch(() => ({}));
    const serverId = body.serverId as string | undefined;
    const overrideRedfishBase = body.redfishBase as string | undefined;
    if (!serverId) {
      return new Response(JSON.stringify({ error: "serverId required" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const { data: server, error } = await supabase
      .from("servers")
      .select(
        "id, status, mgmt_ip, bmc_protocol, bmc_user, bmc_password",
      )
      .eq("id", serverId)
      .maybeSingle();
    if (error) {
      return new Response(JSON.stringify({ error: error.message }), {
        status: 403,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    if (!server) {
      return new Response(JSON.stringify({ error: "server not found" }), {
        status: 404,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const isOffline =
      server.status === "offline" || server.status === "retired";
    const simulated = simulate(serverId, server.status, server.bmc_protocol);

    let live: Partial<BmcStatus> | null = null;
    if (server.bmc_protocol === "redfish" && !isOffline) {
      const base =
        overrideRedfishBase ||
        (server.mgmt_ip ? `https://${server.mgmt_ip}` : null);
      if (base) {
        live = await tryRedfish(
          base,
          server.bmc_user ?? null,
          server.bmc_password ?? null,
        );
      }
    }

    let payload: BmcStatus;
    if (live) {
      payload = {
        ...simulated,
        ...live,
        serverId,
        source: "live",
        protocol: server.bmc_protocol,
        alerts: [],
        history: simulated.history,
        updatedAt: nowIso(),
        collectedAt: nowIso(),
      };
      if (typeof payload.cpuTempC === "number" && payload.cpuTempC > 80) {
        payload.alerts.push({
          id: uid(),
          time: nowIso(),
          level: "Warning",
          message: `CPU 温度 ${payload.cpuTempC}°C 超过阈值 80°C`,
        });
      }
      if (payload.health === "Critical") {
        payload.alerts.push({
          id: uid(),
          time: nowIso(),
          level: "Critical",
          message: "BMC 报告整机健康状态为 Critical",
        });
      }
    } else {
      payload = simulated;
      if (isOffline) {
        payload.alerts.push({
          id: uid(),
          time: nowIso(),
          level: "Critical",
          message: "服务器状态为 offline / retired，未尝试连接 BMC。",
        });
      } else if (server.bmc_protocol === "ipmi") {
        payload.alerts.push({
          id: uid(),
          time: nowIso(),
          level: "Warning",
          message:
            "当前为 IPMI 设备，需要内网部署 IPMI 采集器才能获取真实数据。当前展示为模拟值。",
        });
      } else if (!server.mgmt_ip) {
        payload.alerts.push({
          id: uid(),
          time: nowIso(),
          level: "Warning",
          message: "未配置 BMC IP，当前展示为模拟数据。",
        });
      } else {
        payload.alerts.push({
          id: uid(),
          time: nowIso(),
          level: "Warning",
          message: `Redfish 端点 ${server.mgmt_ip} 未响应，已回退为模拟数据。`,
        });
      }
    }

    return new Response(JSON.stringify(payload), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    return new Response(
      JSON.stringify({ error: e instanceof Error ? e.message : "unknown" }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }
});
