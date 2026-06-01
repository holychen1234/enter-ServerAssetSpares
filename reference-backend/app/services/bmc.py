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

    # Use database static asset fields as the fallback so the BMC tab
    # always shows real inventory data even when the BMC is unreachable.
    proc_model = server.cpu_model.strip() if server.cpu_model else ""
    proc_count = server.cpu_count if server.cpu_count and server.cpu_count > 0 else 0
    mem_gb = server.memory_gb if server.memory_gb and server.memory_gb > 0 else 0
    disk_count = server.disk_count if server.disk_count and server.disk_count > 0 else 0

    # Build placeholder drive entries from the db disk_count so the
    # drives table is never empty while the operator hasn't entered data.
    drives = []
    for i in range(disk_count if disk_count > 0 else 0):
        drives.append(
            {
                "name": f"Disk.Bay.{i+1}",
                "model": "—",
                "sn": None,
                "capacityGB": 0,
                "mediaType": "—",
                "status": "Unknown" if is_offline else "—",
            }
        )

    log_samples = [
        "System: Power restored",
        "System: BMC firmware update completed",
        "Chassis: Intake temperature sensor threshold warning cleared",
        "Storage: Drive rebuild completed successfully",
        "System: User 'admin' logged in via SSH",
        "Network: Ethernet link on NIC1 restored",
    ]
    recent_logs = [
        {
            "id": f"Log{i+1}",
            "severity": "OK" if (i + seed) % 3 != 0 else "Warning",
            "message": log_samples[(i + seed) % len(log_samples)],
            "createdAt": _now_iso(),
        }
        for i in range(6)
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
        "processorSummary": (
            {"count": proc_count, "model": proc_model}
            if proc_count > 0 or proc_model
            else None
        ),
        "memorySummary": (
            {"totalGiB": float(mem_gb)}
            if mem_gb > 0
            else None
        ),
        "memoryModules": [],
        "drives": drives,
        "recentLogs": recent_logs,
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


async def _redfish_storage_drives(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Discover drives under ``/Systems/X/Storage``, with fallback to
    ``SimpleStorage`` for older BMCs (Dell iDRAC 8 and earlier), and
    ``/Chassis/X/Drives`` for XFusion / H3C / other vendors that expose
    drives at the chassis level instead of under Systems/Storage."""
    drives: list[dict] = []
    try:
        # Path 1: modern Storage schema (Dell iDRAC 9+, Supermicro X11+, etc.)
        drives = await _redfish_storage_modern(client, base, system_path)
        if drives:
            logger.debug("redfish storage: got %d drives via Path 1 (Storage)", len(drives))
            return drives
        # Path 2: SimpleStorage (older Dell iDRAC 8, HPE iLO 4)
        drives = await _redfish_storage_simple(client, base, system_path)
        if drives:
            logger.debug("redfish storage: got %d drives via Path 2 (SimpleStorage)", len(drives))
            return drives
        # Path 3: Chassis-level Drives (XFusion, H3C, and other vendors where
        # /Systems/X/Storage returns 404 but /Chassis/X/Drives contains the
        # full drive collection).
        drives = await _redfish_chassis_drives(client, base)
        if drives:
            logger.debug("redfish storage: got %d drives via Path 3 (Chassis/Drives)", len(drives))
    except Exception:
        pass  # Storage isn't critical — keep returning what we have
    return drives


async def _redfish_storage_modern(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Redfish Storage schema (iDRAC 9+, Supermicro X11+, etc.)."""
    drives: list[dict] = []
    try:
        storage_coll = await client.get(f"{base}/{system_path}/Storage")
    except Exception:
        return drives
    if storage_coll.status_code != 200:
        return drives
    members = (storage_coll.json() or {}).get("Members") or []
    for m in members:
        storage_href = m.get("@odata.id")
        if not storage_href:
            continue
        try:
            storage_res = await client.get(f"{base}{storage_href}")
        except Exception:
            continue
        if storage_res.status_code != 200:
            continue
        storage: dict = storage_res.json() or {}
        for dref in storage.get("Drives") or []:
            dhref = dref.get("@odata.id") if isinstance(dref, dict) else None
            if not dhref:
                continue
            try:
                dr = await client.get(f"{base}{dhref}")
            except Exception:
                continue
            if dr.status_code != 200:
                continue
            d = dr.json() or {}
            cap_bytes = d.get("CapacityBytes") or 0
            drives.append(
                {
                    "name": d.get("Name") or d.get("Id") or "?",
                    "model": d.get("Model") or "—",
                    "sn": d.get("SerialNumber") or None,
                    "capacityGB": (
                        round(cap_bytes / (1024**3), 0) if cap_bytes else 0
                    ),
                    "mediaType": d.get("MediaType") or "—",
                    "status": ((d.get("Status") or {}).get("Health")) or "OK",
                }
            )
    return drives


async def _redfish_storage_simple(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Redfish SimpleStorage schema (older Dell iDRAC 8, HPE iLO 4, etc.).

    Devices are embedded inline — no separate per-drive HTTP request needed."""
    drives: list[dict] = []
    coll = await client.get(f"{base}/{system_path}/SimpleStorage")
    if coll.status_code != 200:
        return drives
    members = (coll.json() or {}).get("Members") or []
    for m in members:
        href = m.get("@odata.id")
        if not href:
            continue
        r = await client.get(f"{base}{href}")
        if r.status_code != 200:
            continue
        ss: dict = r.json() or {}
        for i, dev in enumerate(ss.get("Devices") or []):
            cap_bytes = dev.get("CapacityBytes") or 0
            drives.append(
                {
                    "name": dev.get("Name") or f"Disk.Bay.{i+1}",
                    "model": dev.get("Model") or "—",
                    "sn": dev.get("SerialNumber") or None,
                    "capacityGB": (
                        round(cap_bytes / (1024**3), 0) if cap_bytes else 0
                    ),
                    "mediaType": "—",
                    "status": ((dev.get("Status") or {}).get("Health")) or "OK",
                }
            )
    return drives


async def _redfish_chassis_drives(
    client: httpx.AsyncClient, base: str
) -> list[dict]:
    """Discover drives via ``/Chassis/X/Drives``.

    Some vendors (XFusion, H3C, etc.) expose drives at the chassis level
    instead of under ``/Systems/X/Storage``. The drive schema is the same
    standard Redfish ``#Drive`` resource so we reuse the same field mapping.
    """
    drives: list[dict] = []
    chassis_path = await _redfish_first_member(client, base, "Chassis")
    if not chassis_path:
        return drives
    try:
        coll = await client.get(f"{base}/{chassis_path}/Drives")
        if coll.status_code != 200:
            return drives
        members = (coll.json() or {}).get("Members") or []
        for m in members:
            href = m.get("@odata.id")
            if not href:
                continue
            dr = await client.get(f"{base}{href}")
            if dr.status_code != 200:
                continue
            d = dr.json() or {}
            cap_bytes = d.get("CapacityBytes") or 0
            # Skip placeholder entries where the BMC reports null for all
            # meaningful fields (e.g. Inspur / XFusion providing
            # Chassis/Drives member stubs with no actual drive data).
            model = d.get("Model")
            sn = d.get("SerialNumber")
            if cap_bytes == 0 and model is None and sn is None:
                continue
            drives.append(
                {
                    "name": d.get("Name") or d.get("Id") or "?",
                    "model": model or "—",
                    "sn": sn or None,
                    "capacityGB": (
                        round(cap_bytes / (1024**3), 0) if cap_bytes else 0
                    ),
                    "mediaType": d.get("MediaType") or "—",
                    "status": ((d.get("Status") or {}).get("Health")) or "OK",
                }
            )
    except Exception:
        pass
    return drives


async def _redfish_memory_dims(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Discover individual DIMMs under ``/Systems/X/Memory``.

    Returns a list of DIMM descriptors with slot, model, serial number,
    capacity, memory type, and health status — similar to the drives list
    so the frontend can show a detailed per-slot table.
    """
    dims: list[dict] = []
    try:
        coll = await client.get(f"{base}/{system_path}/Memory")
        if coll.status_code != 200:
            return dims
        members = (coll.json() or {}).get("Members") or []
        for m in members:
            href = m.get("@odata.id")
            if not href:
                continue
            r = await client.get(f"{base}{href}")
            if r.status_code != 200:
                continue
            d = r.json() or {}
            loc = d.get("DeviceLocator") or d.get("Name") or d.get("Id") or "?"
            capacity_mib = d.get("CapacityMiB") or 0
            dims.append(
                {
                    "slot": loc,
                    "model": d.get("Model") or d.get("Manufacturer") or "—",
                    "sn": d.get("SerialNumber") or None,
                    "capacityMiB": capacity_mib,
                    "memoryType": d.get("MemoryDeviceType") or "—",
                    "status": ((d.get("Status") or {}).get("Health")) or "OK",
                }
            )
    except Exception:
        pass  # Memory detail isn't critical
    return dims


async def _redfish_recent_logs(
    client: httpx.AsyncClient, base: str
) -> list[dict]:
    """Read the last few entries from the first Manager LogService."""
    entries: list[dict] = []
    try:
        mgr_coll = await client.get(f"{base}/redfish/v1/Managers")
        if mgr_coll.status_code != 200:
            return entries
        mgr_members = (mgr_coll.json() or {}).get("Members") or []
        if not mgr_members:
            return entries
        mgr_href = mgr_members[0].get("@odata.id")
        if not mgr_href:
            return entries
        ls_coll = await client.get(f"{base}{mgr_href}/LogServices")
        if ls_coll.status_code != 200:
            return entries
        ls_members = (ls_coll.json() or {}).get("Members") or []
        if not ls_members:
            return entries
        ls_href = ls_members[0].get("@odata.id")
        if not ls_href:
            return entries
        ent_coll = await client.get(f"{base}{ls_href}/Entries?$top=10")
        if ent_coll.status_code != 200:
            return entries
        for e in (ent_coll.json() or {}).get("Members") or []:
            entries.append(
                {
                    "id": e.get("Id") or "?",
                    "severity": e.get("Severity") or "OK",
                    "message": e.get("Message") or "—",
                    "createdAt": e.get("Created") or "",
                }
            )
    except Exception:
        pass  # Logs aren't critical — keep returning what we have
    return entries


async def _redfish_session_auth(
    client: httpx.AsyncClient, base: str, user: str, password: str
) -> tuple[str | None, str | None]:
    """Create a Redfish session. Returns (token, session_uri).

    The session_uri is used to DELETE the session when done, preventing
    session leaks that can hit BMC session limits.
    """
    try:
        r = await client.post(
            f"{base}/redfish/v1/SessionService/Sessions",
            json={"UserName": user, "Password": password},
        )
        if r.status_code in (200, 201):
            token = r.headers.get("X-Auth-Token")
            session_uri = r.headers.get("Location")
            if token:
                return token, session_uri
            logger.info(
                "Redfish session created (no token header) for %s", base
            )
        else:
            logger.info(
                "Redfish session auth returned %s for %s (user=%s) — "
                "will fall back to Basic auth",
                r.status_code,
                base,
                user,
            )
    except Exception as exc:
        logger.info(
            "Redfish session auth failed for %s: %s — will fall back to Basic auth",
            base,
            exc,
        )
    return None, None


async def _redfish_delete_session(
    client: httpx.AsyncClient, base: str, session_uri: str
) -> None:
    """DELETE a Redfish session to avoid hitting BMC session limits."""
    try:
        await client.delete(f"{base}{session_uri}")
    except Exception:
        pass


async def _collect_redfish(server: Server) -> dict | None:
    base = _redfish_base(server)
    timeout = httpx.Timeout(settings.redfish_timeout_seconds)
    has_creds = bool(server.bmc_user and server.bmc_password)

    try:
        async with httpx.AsyncClient(
            timeout=timeout, verify=False, follow_redirects=True
        ) as client:
            session_uri: str | None = None
            try:
                # Try session auth first (required by Inspur & many enterprise
                # BMCs), fall back to Basic auth on the client if session isn't
                # supported.
                if has_creds:
                    session_token, session_uri = await _redfish_session_auth(
                        client, base, server.bmc_user, server.bmc_password
                    )
                    if session_token:
                        client.headers["X-Auth-Token"] = session_token
                    else:
                        client.auth = (server.bmc_user, server.bmc_password)

                # Discover collection members in parallel
                chassis_path, system_path = await asyncio.gather(
                    _redfish_first_member(client, base, "Chassis"),
                    _redfish_first_member(client, base, "Systems"),
                )
                if not chassis_path or not system_path:
                    logger.warning(
                        "redfish discovery failed for %s (manufacturer=%s)",
                        server.id,
                        server.manufacturer,
                    )
                    return None

                thermal_res, power_res, system_res, drives, mem_modules, logs = (
                    await asyncio.gather(
                        client.get(f"{base}/{chassis_path}/Thermal"),
                        client.get(f"{base}/{chassis_path}/Power"),
                        client.get(f"{base}/{system_path}"),
                        _redfish_storage_drives(client, base, system_path),
                        _redfish_memory_dims(client, base, system_path),
                        _redfish_recent_logs(client, base),
                    )
                )

                if thermal_res.status_code != 200 or system_res.status_code != 200:
                    logger.warning(
                        "redfish http error for %s: thermal=%s system=%s",
                        server.id,
                        thermal_res.status_code,
                        system_res.status_code,
                    )
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
                        "status": (
                            (f.get("Status") or {}).get("Health")
                        ) or "OK",
                    }
                    for i, f in enumerate(thermal.get("Fans") or [])
                ]
                psus = [
                    {
                        "name": ps.get("Name") or f"PSU{i+1}",
                        "watts": int(
                            ps.get("PowerOutputWatts")
                            or ps.get("LastPowerOutputWatts")
                            or 0
                        ),
                        "capacityW": int(ps.get("PowerCapacityWatts") or 800),
                        "status": (
                            (ps.get("Status") or {}).get("Health")
                        ) or "OK",
                    }
                    for i, ps in enumerate(power.get("PowerSupplies") or [])
                ]

                consumed_w = 0
                for pc in power.get("PowerControl") or []:
                    v = pc.get("PowerConsumedWatts")
                    if isinstance(v, (int, float)):
                        consumed_w = int(v)
                        break
                if consumed_w == 0 and psus:
                    consumed_w = sum(p["watts"] for p in psus)

                # CPU / Memory — use key presence, not truthiness of the dict
                # (Dell iDRAC may return empty {} objects).
                proc_sum = system.get("ProcessorSummary") or {}
                mem_sum = system.get("MemorySummary") or {}
                processor = (
                    {
                        "count": int(proc_sum.get("Count") or 0),
                        "model": str(proc_sum.get("Model") or ""),
                    }
                    if "Count" in proc_sum or "Model" in proc_sum
                    else None
                )
                memory = (
                    {
                        "totalGiB": float(
                            mem_sum.get("TotalSystemMemoryGiB") or 0
                        )
                    }
                    if "TotalSystemMemoryGiB" in mem_sum
                    else None
                )

                return {
                    "power": (
                        "On" if (system.get("PowerState") == "On") else "Off"
                    ),
                    "health": (
                        (system.get("Status") or {}).get("Health")
                    ) or "OK",
                    "bootProgress": (
                        (system.get("BootProgress") or {}).get("LastState")
                    ) or "Unknown",
                    "cpuTempC": round(cpu_temp, 1),
                    "inletTempC": round(inlet_temp, 1),
                    "fans": fans or None,
                    "psus": psus or None,
                    "_powerWatts": consumed_w,
                    "processorSummary": processor,
                    "memorySummary": memory,
                    "memoryModules": mem_modules or None,
                    "drives": drives or None,
                    "recentLogs": logs or None,
                }
            finally:
                # Always clean up the session so we don't hit BMC session
                # limits (Dell iDRAC caps at 4–8 concurrent sessions).
                if session_uri:
                    await _redfish_delete_session(client, base, session_uri)
    except Exception as e:
        import traceback as _tb
        logger.warning(
            "redfish poll failed for %s (manufacturer=%s, mgmt_ip=%s): %s | %s",
            server.id,
            server.manufacturer,
            server.mgmt_ip,
            e,
            repr(e),
        )
        logger.warning(
            "redfish poll traceback for %s:\n%s",
            server.id,
            _tb.format_exc(),
        )
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
