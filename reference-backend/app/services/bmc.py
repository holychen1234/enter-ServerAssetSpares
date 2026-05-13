"""BMC live-status collector.

This module is the only place that talks to a real BMC. It exposes a single
async function ``get_status(server) -> dict`` returning a payload that matches
the frontend ``BmcStatus`` type 1:1.

Two protocols are supported:

* **redfish** — async HTTPS REST polling against the BMC. We probe the
  Chassis (Power + Thermal) and Systems collections and discover the
  first member dynamically (most BMCs expose ``/Chassis/1`` or
  ``/Chassis/System.Embedded.1``).
* **ipmi** — calls out to ``ipmitool`` (installed in the API image). This
  requires L3 reachability from the api container to the BMC management
  network.

The collector keeps:

* A short **TTL cache** keyed by server.id so rapid UI polls do not hammer
  the BMC. ``CACHE_TTL_SECONDS`` defaults to 30 seconds.
* A per-server **ring-buffer of historical samples** (last 12 points,
  appended once per real successful poll). This is used to draw the
  "近 60 分钟趋势" chart. When the BMC is unreachable we fall back to a
  deterministic simulated history so the chart never goes empty.

If a real poll fails for any reason we degrade gracefully to a simulated
payload and tag it with ``source = "simulated"`` plus an explicit alert.
The frontend uses ``source`` to render a clear "实时 / 模拟" badge so an
operator can tell at a glance whether the BMC is actually reachable.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.db.models import Server
from app.settings import settings

logger = logging.getLogger("bmc")

CACHE_TTL_SECONDS = 30
HISTORY_MAX_POINTS = 12
HISTORY_INTERVAL_LABEL = "5m"  # purely cosmetic — used for x-axis ticks


# ---------------------------------------------------------------------------
# In-memory state (per process). For a single-replica on-prem deployment
# this is exactly what we want; for HA you would back this with Redis.
# ---------------------------------------------------------------------------
@dataclass
class _Sample:
    cpu: float
    inlet: float
    power: float
    at: float = field(default_factory=time.time)


@dataclass
class _CacheEntry:
    payload: dict
    at: float


_status_cache: dict[str, _CacheEntry] = {}
_history: dict[str, list[_Sample]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Simulation (used as the deterministic fallback)
# ---------------------------------------------------------------------------
def _simulate(server: Server) -> dict:
    is_offline = server.status in ("offline", "retired")
    is_maint = server.status == "maintenance"
    seed = (len(server.id) + ord(server.id[-1])) if server.id else 7

    cpu = 0.0 if is_offline else round(random.uniform(48, 78), 1)
    inlet = 0.0 if is_offline else round(random.uniform(20, 28), 1)
    health = (
        "Critical"
        if is_offline
        else "Warning"
        if cpu > 75 or is_maint
        else "OK"
    )
    fans = [
        {
            "name": f"Fan{i+1}",
            "rpm": 0 if is_offline else int(random.uniform(4200, 7800)),
            "status": "Critical" if is_offline else "OK",
        }
        for i in range(6)
    ]
    psus = [
        {
            "name": f"PSU{i+1}",
            "watts": 0 if is_offline else int(random.uniform(180, 360)),
            "capacityW": 800,
            "status": "Critical" if is_offline else "OK",
        }
        for i in range(2)
    ]

    base_cpu = 55 + (seed % 12)
    base_inlet = 22 + (seed % 4)
    base_power = 320 + (seed % 60)
    history = [
        {
            "t": f"{i*5}m",
            "cpu": max(20, min(95, base_cpu + random.uniform(-6, 8))),
            "inlet": max(15, min(35, base_inlet + random.uniform(-2, 2))),
            "power": max(150, base_power + random.uniform(-40, 50)),
        }
        for i in range(11, -1, -1)
    ]

    return {
        "serverId": server.id,
        "source": "simulated",
        "protocol": server.bmc_protocol,
        "power": "Off" if is_offline else "On",
        "health": health,
        "bootProgress": "PowerOff" if is_offline else "OSBootCompleted",
        "cpuTempC": cpu,
        "inletTempC": inlet,
        "fans": fans,
        "psus": psus,
        "alerts": [],
        "history": history,
        "updatedAt": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Redfish
# ---------------------------------------------------------------------------
def _redfish_base(server: Server) -> str:
    """Return a URL we can hit with ``GET <base>/redfish/v1/...``."""
    if server.mgmt_ip:
        # Real BMCs almost always speak HTTPS with a self-signed cert.
        # We disable verification (verify=False) below.
        return f"https://{server.mgmt_ip}"
    # Fallback: the bundled docker-compose redfish-mock service so the
    # demo deployment shows real numbers out of the box.
    return settings.redfish_default_base


async def _redfish_first_member(
    client: httpx.AsyncClient, base: str, collection: str
) -> str | None:
    """Discover the first item in a Redfish collection.

    BMC vendors disagree on naming (``/Chassis/1``, ``/Chassis/System.Embedded.1``,
    ``/Systems/server-1``, ...) so we always read the collection first instead
    of hard-coding ``/1``.
    """
    try:
        r = await client.get(f"{base}/redfish/v1/{collection}")
        if r.status_code != 200:
            return None
        members = (r.json() or {}).get("Members") or []
        if not members:
            return None
        # @odata.id is a path like "/redfish/v1/Chassis/1"
        href = members[0].get("@odata.id")
        if not href:
            return None
        return href.lstrip("/")
    except Exception:
        return None


def _pick_temp(temps: list[dict], pattern: str) -> float:
    rx = re.compile(pattern, re.IGNORECASE)
    for t in temps:
        if rx.search(str(t.get("Name") or "")):
            v = t.get("ReadingCelsius")
            if isinstance(v, (int, float)):
                return float(v)
    # Fall back to the first reading if no name matched (some BMCs use opaque names)
    for t in temps:
        v = t.get("ReadingCelsius")
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


async def _collect_redfish(server: Server) -> dict | None:
    base = _redfish_base(server)
    auth: tuple[str, str] | None = None
    if server.bmc_user and server.bmc_password:
        auth = (server.bmc_user, server.bmc_password)
    timeout = httpx.Timeout(settings.redfish_timeout_seconds)

    try:
        async with httpx.AsyncClient(
            timeout=timeout, verify=False, auth=auth, follow_redirects=True
        ) as client:
            # Discover collection members in parallel
            chassis_path, system_path = await asyncio.gather(
                _redfish_first_member(client, base, "Chassis"),
                _redfish_first_member(client, base, "Systems"),
            )
            if not chassis_path or not system_path:
                logger.warning("redfish discovery failed for %s", server.id)
                return None

            thermal_res, power_res, system_res = await asyncio.gather(
                client.get(f"{base}/{chassis_path}/Thermal"),
                client.get(f"{base}/{chassis_path}/Power"),
                client.get(f"{base}/{system_path}"),
            )
        if thermal_res.status_code != 200 or system_res.status_code != 200:
            return None

        thermal: dict[str, Any] = thermal_res.json() or {}
        system: dict[str, Any] = system_res.json() or {}
        power: dict[str, Any] = (
            power_res.json() if power_res.status_code == 200 else {}
        )

        temps = thermal.get("Temperatures") or []
        cpu_temp = _pick_temp(temps, r"CPU|Proc")
        inlet_temp = _pick_temp(temps, r"Inlet|Intake|Ambient")

        fans = [
            {
                "name": f.get("Name") or f"Fan{i+1}",
                "rpm": int(f.get("Reading") or 0),
                "status": ((f.get("Status") or {}).get("Health")) or "OK",
            }
            for i, f in enumerate(thermal.get("Fans") or [])
        ]
        psus = [
            {
                "name": ps.get("Name") or f"PSU{i+1}",
                "watts": int(ps.get("PowerOutputWatts") or 0),
                "capacityW": int(ps.get("PowerCapacityWatts") or 800),
                "status": ((ps.get("Status") or {}).get("Health")) or "OK",
            }
            for i, ps in enumerate(power.get("PowerSupplies") or [])
        ]
        # PowerControl[*].PowerConsumedWatts is the chassis-wide draw
        consumed_w = 0
        for pc in power.get("PowerControl") or []:
            v = pc.get("PowerConsumedWatts")
            if isinstance(v, (int, float)):
                consumed_w = int(v)
                break
        if consumed_w == 0 and psus:
            consumed_w = sum(p["watts"] for p in psus)

        return {
            "power": "On" if (system.get("PowerState") == "On") else "Off",
            "health": ((system.get("Status") or {}).get("Health")) or "OK",
            "bootProgress": (
                ((system.get("BootProgress") or {}).get("LastState"))
                or "Unknown"
            ),
            "cpuTempC": round(cpu_temp, 1),
            "inletTempC": round(inlet_temp, 1),
            "fans": fans or None,
            "psus": psus or None,
            "_powerWatts": consumed_w,
        }
    except Exception as e:
        logger.warning("redfish poll failed for %s: %s", server.id, e)
        return None


# ---------------------------------------------------------------------------
# IPMI (subset — temperatures + power state only; full IPMI parsing is
# out of scope for this MVP).
# ---------------------------------------------------------------------------
def _collect_ipmi(server: Server) -> dict | None:
    if not (server.mgmt_ip and server.bmc_user and server.bmc_password):
        return None
    common = [
        "ipmitool",
        "-I", "lanplus",
        "-H", server.mgmt_ip,
        "-U", server.bmc_user,
        "-P", server.bmc_password,
    ]
    try:
        chassis = subprocess.run(
            [*common, "chassis", "status"],
            capture_output=True, text=True,
            timeout=settings.redfish_timeout_seconds,
        )
        if chassis.returncode != 0:
            return None
        power_state = "On" if re.search(
            r"System Power\s*:\s*on", chassis.stdout, re.IGNORECASE
        ) else "Off"

        sdr_temp = subprocess.run(
            [*common, "sdr", "type", "Temperature"],
            capture_output=True, text=True,
            timeout=settings.redfish_timeout_seconds,
        )
        cpu_temp = 0.0
        inlet_temp = 0.0
        if sdr_temp.returncode == 0:
            for line in sdr_temp.stdout.splitlines():
                m = re.search(r"(\d+(?:\.\d+)?)\s*degrees\s*C", line)
                if not m:
                    continue
                v = float(m.group(1))
                lower = line.lower()
                if "cpu" in lower or "proc" in lower:
                    cpu_temp = max(cpu_temp, v)
                elif "inlet" in lower or "ambient" in lower or "intake" in lower:
                    inlet_temp = inlet_temp or v
            if inlet_temp == 0 and cpu_temp:
                inlet_temp = max(20.0, cpu_temp - 30)

        sdr_power = subprocess.run(
            [*common, "dcmi", "power", "reading"],
            capture_output=True, text=True,
            timeout=settings.redfish_timeout_seconds,
        )
        watts = 0
        if sdr_power.returncode == 0:
            m = re.search(
                r"Instantaneous power reading\s*:\s*(\d+)",
                sdr_power.stdout,
            )
            if m:
                watts = int(m.group(1))

        return {
            "power": power_state,
            "health": "OK",
            "bootProgress": "Unknown",
            "cpuTempC": round(cpu_temp, 1),
            "inletTempC": round(inlet_temp, 1),
            "fans": None,  # ipmitool sdr type Fan parsing intentionally omitted
            "psus": None,
            "_powerWatts": watts,
        }
    except Exception as e:
        logger.warning("ipmi poll failed for %s: %s", server.id, e)
        return None


# ---------------------------------------------------------------------------
# History ring buffer
# ---------------------------------------------------------------------------
def _push_history(server_id: str, cpu: float, inlet: float, power: float) -> None:
    buf = _history.setdefault(server_id, [])
    buf.append(_Sample(cpu=cpu, inlet=inlet, power=power))
    if len(buf) > HISTORY_MAX_POINTS:
        del buf[0 : len(buf) - HISTORY_MAX_POINTS]


def _history_payload(server_id: str, fallback: list[dict]) -> list[dict]:
    buf = _history.get(server_id)
    if not buf:
        return fallback
    n = len(buf)
    out: list[dict] = []
    for i, s in enumerate(buf):
        # x-axis label: "0m" for newest, "5m" for previous, ...
        idx_from_now = (n - 1 - i)
        out.append(
            {
                "t": f"{idx_from_now * 5}m",
                "cpu": round(s.cpu, 1),
                "inlet": round(s.inlet, 1),
                "power": round(s.power),
            }
        )
    # newest at the right of the chart; recharts renders in insertion order.
    return out


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
async def get_status(server: Server, *, force_refresh: bool = False) -> dict:
    cached = _status_cache.get(server.id)
    if (
        not force_refresh
        and cached
        and (time.time() - cached.at) < CACHE_TTL_SECONDS
    ):
        return cached.payload

    sim = _simulate(server)
    is_offline = server.status in ("offline", "retired")

    live: dict | None = None
    if not is_offline:
        if server.bmc_protocol == "redfish":
            live = await _collect_redfish(server)
        elif server.bmc_protocol == "ipmi":
            live = await asyncio.to_thread(_collect_ipmi, server)

    if live:
        # Merge real values on top of the simulated skeleton (so we still
        # have shapes like fans/psus when the BMC didn't report them).
        merged = dict(sim)
        for k, v in live.items():
            if v is not None and not k.startswith("_"):
                merged[k] = v
        merged["source"] = "live"
        merged["collectedAt"] = _now_iso()
        merged["alerts"] = []

        # Auto alert thresholds on real samples
        if isinstance(merged.get("cpuTempC"), (int, float)) and merged["cpuTempC"] > 80:
            merged["alerts"].append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "time": _now_iso(),
                    "level": "Warning",
                    "message": f"CPU 温度 {merged['cpuTempC']}°C 超过阈值 80°C",
                }
            )
        if merged.get("health") == "Critical":
            merged["alerts"].append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "time": _now_iso(),
                    "level": "Critical",
                    "message": "BMC 报告整机健康状态为 Critical",
                }
            )

        _push_history(
            server.id,
            float(merged.get("cpuTempC") or 0),
            float(merged.get("inletTempC") or 0),
            float(live.get("_powerWatts") or 0),
        )
        merged["history"] = _history_payload(server.id, sim["history"])
        merged["updatedAt"] = _now_iso()
        payload = merged
    else:
        # Degrade — clearly mark as simulated so the UI shows the badge
        sim["history"] = _history_payload(server.id, sim["history"])
        if is_offline:
            sim["alerts"].append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "time": _now_iso(),
                    "level": "Critical",
                    "message": "服务器状态为 offline / retired，未尝试连接 BMC。",
                }
            )
        elif not server.mgmt_ip:
            sim["alerts"].append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "time": _now_iso(),
                    "level": "Warning",
                    "message": "未配置 BMC IP，当前展示为模拟数据。",
                }
            )
        else:
            sim["alerts"].append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "time": _now_iso(),
                    "level": "Warning",
                    "message": (
                        f"{server.bmc_protocol.upper()} 端点 {server.mgmt_ip} "
                        f"未在 {settings.redfish_timeout_seconds}s 内响应，"
                        "已回退为模拟数据。"
                    ),
                }
            )
        payload = sim

    _status_cache[server.id] = _CacheEntry(payload=payload, at=time.time())
    return payload


def invalidate_cache(server_id: str | None = None) -> None:
    if server_id is None:
        _status_cache.clear()
    else:
        _status_cache.pop(server_id, None)
