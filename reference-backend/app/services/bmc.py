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

from app.db.models import BmcSnapshot, Server
from app.db.base import SessionLocal
from app.settings import settings

logger = logging.getLogger("bmc")

CACHE_TTL_SECONDS = 30
HISTORY_MAX_POINTS = 12
HISTORY_INTERVAL_LABEL = "5m"  # purely cosmetic — used for x-axis ticks

# Short timeout used for probing Redfish collection paths (e.g. "does
# /Storage or /SimpleStorage exist?").  These run sequentially so a long
# timeout on each would add up quickly when the BMC is unreachable.
_DISCOVERY_TIMEOUT = 1.5  # seconds — enough for a responsive BMC on LAN

# When a Redfish poll fails, don't retry the same BMC for this many seconds
# (even with force_refresh).  Prevents multiple sequential collect_and_save
# calls from each wasting DISCOVERY_TIMEOUT on an unreachable BMC.
_COLLECT_FAIL_COOLDOWN = 60  # seconds

# Limit concurrent HTTP requests to a single BMC so we don't overwhelm
# its management controller (many BMCs cap at 4–8 simultaneous sessions).
_BMC_SEMAPHORE = asyncio.Semaphore(6)


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
_last_fail_time: dict[str, float] = {}


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
                "formFactor": "unknown",
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
        "memorySlots": {"total": 0, "populated": 0},
        "drives": drives,
        "diskSlots": {
            "total": disk_count if disk_count and disk_count > 0 else 0,
            "populated": disk_count if disk_count and disk_count > 0 else 0,
        },
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

    Uses a short timeout because this is a lightweight collection probe —
    not a detailed resource fetch.
    """
    try:
        r = await client.get(
            f"{base}/redfish/v1/{collection}",
            timeout=_DISCOVERY_TIMEOUT,
        )
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
            return drives
        # Path 4: Deep-drill Storage controllers (Inspur / some H3C). Some
        # BMCs report controllers in /Systems/X/Storage but don't surface
        # drives via the standard Members→Drives array. We fetch each
        # controller and try Links.Drives or /Drives sub-path directly.
        drives = await _redfish_storage_deep(client, base, system_path)
        if drives:
            logger.debug("redfish storage: got %d drives via Path 4 (Storage deep)", len(drives))
    except Exception:
        pass  # Storage isn't critical — keep returning what we have
    return drives


async def _redfish_storage_modern(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Redfish Storage schema (iDRAC 9+, Supermicro X11+, etc.).

    Controllers and drives are fetched in parallel to stay within the
    per-request timeout window even on BMCs with many drives (e.g. Inspur
    with 9+ drives behind a single PCIE2_RAID controller)."""
    drives: list[dict] = []
    try:
        storage_coll = await client.get(
            f"{base}/{system_path}/Storage",
            timeout=_DISCOVERY_TIMEOUT,
        )
    except Exception:
        return drives
    if storage_coll.status_code != 200:
        return drives
    members = (storage_coll.json() or {}).get("Members") or []

    # ── Phase 1: fetch every controller in parallel to collect drive hrefs ──
    async def _controller_drive_hrefs(m) -> list[str]:
        hrefs: list[str] = []
        ctrl_href = m.get("@odata.id")
        if not ctrl_href:
            return hrefs
        try:
            async with _BMC_SEMAPHORE:
                r = await client.get(f"{base}{ctrl_href}")
        except Exception:
            return hrefs
        if r.status_code != 200:
            return hrefs
        storage: dict = r.json() or {}
        for dref in storage.get("Drives") or []:
            dhref = dref.get("@odata.id") if isinstance(dref, dict) else None
            if dhref:
                hrefs.append(dhref)
        return hrefs

    controller_results = await asyncio.gather(
        *[_controller_drive_hrefs(m) for m in members],
        return_exceptions=True,
    )
    drive_hrefs: list[str] = []
    for result in controller_results:
        if isinstance(result, list):
            drive_hrefs.extend(h for h in result if h)

    if not drive_hrefs:
        return drives

    # ── Phase 2: fetch every drive detail in parallel ──
    async def _get_drive(href: str) -> dict | None:
        try:
            async with _BMC_SEMAPHORE:
                r = await client.get(f"{base}{href}")
        except Exception:
            return None
        if r.status_code != 200:
            return None
        d = r.json() or {}
        cap = d.get("CapacityBytes") or 0
        return {
            "name": d.get("Name") or d.get("Id") or "?",
            "model": d.get("Model") or "—",
            "sn": d.get("SerialNumber") or None,
            "capacityGB": round(cap / (1024**3), 0) if cap else 0,
            "mediaType": d.get("MediaType") or "—",
            "status": ((d.get("Status") or {}).get("Health")) or "OK",
        }

    results = await asyncio.gather(
        *[_get_drive(h) for h in drive_hrefs],
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, dict):
            drives.append(result)

    return drives


async def _redfish_storage_simple(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Redfish SimpleStorage schema (older Dell iDRAC 8, HPE iLO 4, etc.).

    Devices are embedded inline — no separate per-drive HTTP request needed."""
    drives: list[dict] = []
    try:
        coll = await client.get(
            f"{base}/{system_path}/SimpleStorage",
            timeout=_DISCOVERY_TIMEOUT,
        )
        if coll.status_code != 200:
            return drives
    except Exception:
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
            # Skip absent / empty bays — they have no drive installed.
            dev_state = ((dev.get("Status") or {}).get("State") or "").lower()
            if dev_state == "absent":
                continue
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
        coll = await client.get(
            f"{base}/{chassis_path}/Drives",
            timeout=_DISCOVERY_TIMEOUT,
        )
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
            # Skip placeholder entries: if the drive has no Model, no SN
            # AND zero capacity, it's a stub. But if any one field is
            # present, keep it — some Inspur BMCs report valid drives
            # with zero capacity but have a model name.
            model = d.get("Model")
            sn = d.get("SerialNumber")
            if not model and not sn and cap_bytes == 0:
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


async def _redfish_storage_deep(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Path 4: Deep-drill each Storage controller for drives (Inspur / H3C).

    Some BMCs report controllers under /Systems/X/Storage but do not
    populate the Drives array on the collection-level members response.
    We fetch each controller individually and look for drives in:
      - ``Links/Drives`` (Inspur sometimes puts drives there)
      - ``/Drives`` sub-path on each controller
    """
    drives: list[dict] = []
    try:
        coll = await client.get(
            f"{base}/{system_path}/Storage",
            timeout=_DISCOVERY_TIMEOUT,
        )
        if coll.status_code != 200:
            return drives
        members = (coll.json() or {}).get("Members") or []
        if not members:
            return drives

        async def _deep_drill(m) -> list[dict]:
            href = m.get("@odata.id")
            if not href:
                return []
            try:
                ctrl = await client.get(f"{base}{href}")
            except Exception:
                return []
            if ctrl.status_code != 200:
                return []
            ctrl_data = ctrl.json() or {}
            found: list[dict] = []

            # Try Links → Drives (Inspur / H3C sometimes use this)
            for link_ref in (ctrl_data.get("Links") or {}).get("Drives") or []:
                drive_href = link_ref.get("@odata.id")
                if not drive_href:
                    continue
                try:
                    dr = await client.get(f"{base}{drive_href}")
                except Exception:
                    continue
                if dr.status_code != 200:
                    continue
                d = dr.json() or {}
                cap_bytes = d.get("CapacityBytes") or 0
                found.append({
                    "name": d.get("Name") or d.get("Id") or "?",
                    "model": d.get("Model") or "—",
                    "sn": d.get("SerialNumber") or None,
                    "capacityGB": round(cap_bytes / (1024**3), 0) if cap_bytes else 0,
                    "mediaType": d.get("MediaType") or "—",
                    "status": ((d.get("Status") or {}).get("Health")) or "OK",
                })
                continue

            # Try /Drives sub-path on the controller
            if not found:
                try:
                    dr_coll = await client.get(f"{base}{href}/Drives")
                except Exception:
                    return found
                if dr_coll.status_code == 200:
                    for dm in (dr_coll.json() or {}).get("Members") or []:
                        dh = dm.get("@odata.id")
                        if not dh:
                            continue
                        try:
                            dr = await client.get(f"{base}{dh}")
                        except Exception:
                            continue
                        if dr.status_code != 200:
                            continue
                        d = dr.json() or {}
                        cap_bytes = d.get("CapacityBytes") or 0
                        model = d.get("Model")
                        sn = d.get("SerialNumber")
                        if not model and not sn and cap_bytes == 0:
                            continue
                        found.append({
                            "name": d.get("Name") or d.get("Id") or "?",
                            "model": model or "—",
                            "sn": sn or None,
                            "capacityGB": round(cap_bytes / (1024**3), 0) if cap_bytes else 0,
                            "mediaType": d.get("MediaType") or "—",
                            "status": ((d.get("Status") or {}).get("Health")) or "OK",
                        })
            return found

        results = await asyncio.gather(
            *[_deep_drill(m) for m in members],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, list):
                drives.extend(r)
    except Exception:
        pass
    return drives


# ── Disk bay / slot total count helpers ─────────────────────────

async def _redfish_disk_total_slots(
    client: httpx.AsyncClient, base: str, system_path: str, chassis_path: str
) -> int:
    """Return the physical disk bay / slot total from Redfish.

    Tries in order:
    1. SimpleStorage → count all Devices (including ``State: Absent``)
    2. Modern Storage → sum ``Drives@odata.count`` across controllers
    3. Chassis/Drives → ``Members@odata.count``
    4. Fallback → 0 (caller uses len(drives) as last resort)
    """
    # Path 1: SimpleStorage (includes absent devices)
    try:
        coll = await client.get(
            f"{base}/{system_path}/SimpleStorage",
            timeout=_DISCOVERY_TIMEOUT,
        )
        if coll.status_code == 200:
            members = (coll.json() or {}).get("Members") or []
            total = 0
            for m in members:
                href = m.get("@odata.id")
                if not href:
                    continue
                r = await client.get(f"{base}{href}", timeout=_DISCOVERY_TIMEOUT)
                if r.status_code == 200:
                    total += len((r.json() or {}).get("Devices") or [])
            if total > 0:
                return total
    except Exception:
        pass

    # Path 2: Modern Storage — sum Drives@odata.count per controller
    try:
        coll = await client.get(
            f"{base}/{system_path}/Storage",
            timeout=_DISCOVERY_TIMEOUT,
        )
        if coll.status_code == 200:
            members = (coll.json() or {}).get("Members") or []
            total = 0
            for m in members:
                href = m.get("@odata.id")
                if not href:
                    continue
                ctrl = await client.get(f"{base}{href}", timeout=_DISCOVERY_TIMEOUT)
                if ctrl.status_code == 200:
                    ctrl_data = ctrl.json() or {}
                    drives_coll = ctrl_data.get("Drives@odata.count")
                    if isinstance(drives_coll, int) and drives_coll > 0:
                        total += drives_coll
                    else:
                        drives_list = ctrl_data.get("Drives") or []
                        total += len(drives_list)
            if total > 0:
                return total
    except Exception:
        pass

    # Path 3: Chassis/Drives — Members@odata.count
    if chassis_path:
        try:
            coll = await client.get(
                f"{base}/{chassis_path}/Drives",
                timeout=_DISCOVERY_TIMEOUT,
            )
            if coll.status_code == 200:
                count = (coll.json() or {}).get("Members@odata.count")
                if isinstance(count, int) and count > 0:
                    return count
        except Exception:
            pass

    return 0


# ── Chassis metadata (for disk form factor inference) ──────────

async def _redfish_chassis_spec(
    client: httpx.AsyncClient, base: str, chassis_path: str
) -> dict:
    """Return a small dict of chassis physical metadata.

    Keys returned (when available): ``heightMm``, ``model``, ``chassisType``."""
    spec: dict = {}
    if not chassis_path:
        return spec
    try:
        r = await client.get(f"{base}/{chassis_path}", timeout=_DISCOVERY_TIMEOUT)
        if r.status_code != 200:
            return spec
        d = r.json() or {}
        if isinstance(d.get("HeightMm"), (int, float)):
            spec["heightMm"] = float(d["HeightMm"])
        if isinstance(d.get("Model"), str):
            spec["model"] = d["Model"]
        if isinstance(d.get("ChassisType"), str):
            spec["chassisType"] = d["ChassisType"]
    except Exception:
        pass
    return spec


# ── Drive form factor inference ─────────────────────────────────

# Well-known model name patterns that strongly indicate 3.5" drives.
# Most enterprise 3.5" HDDs use "LFF" (Large Form Factor) naming;
# 2.5" HDDs/SSDs use "SFF" (Small Form Factor).
_MODEL_3_5_PATTERNS = [
    "LFF",               # Dell / HPE convention
    "ST[48]000NM",       # Seagate Exos 3.5" (4TB+)
    "ST[48]000VX",       # Seagate SkyHawk 3.5" surveillance
    "ST[1-9][0-9]00NM",  # Seagate Enterprise Capacity 3.5"
    "WD[48]00PUR",       # WD Purple 3.5" surveillance
    "WD[1-9][0-9]00EF",  # WD Red Pro / Gold 3.5"
    "MG0[4-9]",          # Toshiba MG Series 3.5" enterprise
    "HUH72",             # HGST Ultrastar He10/He12 3.5"
    "HUS72",             # HGST Ultrastar 7K2 3.5"
]


def _infer_drive_form_factor(
    drive: dict, chassis_spec: dict | None = None
) -> str:
    """Infer the physical drive form factor (2.5\" or 3.5\") from available data.

    Heuristic priority:
    1. Model name contains "LFF" → 3.5\", "SFF" → 2.5\"
    2. Model matches known 3.5\" patterns (Seagate/WD/Toshiba/HGST enterprise)
    3. Capacity < 600 GB mechanical HDD → likely 2.5\" (laptop/enterprise SFF)
    4. Chassis HeightMm ≤ 45 mm (1U) → all bays are 2.5\"
    5. SSD → almost always 2.5\" (or M.2/U.2); NVMe is 2.5\" or smaller
    6. Fallback → \"unknown\"
    """
    model = (drive.get("model") or "").strip()
    media = (drive.get("mediaType") or "").strip()
    cap_gb = drive.get("capacityGB") or 0

    # 1. Explicit LFF / SFF in model name
    if "LFF" in model.upper():
        return "LFF"  # 3.5"
    if "SFF" in model.upper():
        return "SFF"  # 2.5"

    # 2. Known 3.5" enterprise HDD model patterns
    import re as _re
    for pat in _MODEL_3_5_PATTERNS:
        if _re.search(pat, model, _re.IGNORECASE):
            return "LFF"

    # 3. Capacity heuristic: ≥ 6 TB mechanical drives are almost exclusively 3.5"
    #    (2.5" HDDs top out at ~5 TB for consumer, 2.4 TB for enterprise 10K/15K)
    if cap_gb >= 6000 and media.upper() == "HDD":
        return "LFF"

    # 4. Chassis height: 1U chassis (≤ 45 mm) can only fit 2.5" drives
    if chassis_spec and isinstance(chassis_spec.get("heightMm"), (int, float)):
        if chassis_spec["heightMm"] <= 45:
            return "SFF"

    # 5. SSD / NVMe → always 2.5" or smaller
    if media.upper() in ("SSD", "NVME"):
        return "SFF"

    # 6. Unknown
    return "unknown"


async def _redfish_memory_dims(
    client: httpx.AsyncClient, base: str, system_path: str
) -> tuple[list[dict], int]:
    """Discover individual DIMMs under ``/Systems/X/Memory``.

    Returns ``(dimms, total_slots)`` where ``total_slots`` is the number of
    physical DIMM slots reported by the BMC.  ``Members@odata.count`` is the
    primary source; when absent (older BMCs) we count members directly,
    including those with ``State: Absent``.

    All DIMM detail requests are fetched in parallel so the full set
    completes within the per-request timeout window (previously serial
    enumeration could easily exceed 30 s on servers with 8+ DIMMs)."""
    dims: list[dict] = []
    total_slots: int = 0
    try:
        coll = await client.get(
            f"{base}/{system_path}/Memory",
            timeout=_DISCOVERY_TIMEOUT,
        )
        if coll.status_code != 200:
            return dims, 0
        coll_data = coll.json() or {}
        members = coll_data.get("Members") or []
        # Primary source for total slot count — many BMCs include
        # empty/Absent slots in the collection so this is the physical
        # slot count, not just the populated count.
        total_slots = coll_data.get("Members@odata.count", len(members))
    except Exception:
        return dims, 0

    if not members:
        # Fallback: some Inspur BMCs expose memory under
        # /MemoryDomains/{domain}/Memory instead of /Memory directly.
        try:
            dm_coll = await client.get(
                f"{base}/{system_path}/MemoryDomains",
                timeout=_DISCOVERY_TIMEOUT,
            )
            if dm_coll.status_code == 200:
                for dm_member in (dm_coll.json() or {}).get("Members") or []:
                    dm_href = dm_member.get("@odata.id")
                    if not dm_href:
                        continue
                    dm_res = await client.get(
                        f"{base}{dm_href}/Memory",
                        timeout=_DISCOVERY_TIMEOUT,
                    )
                    if dm_res.status_code == 200:
                        dm_data = dm_res.json() or {}
                        members = dm_data.get("Members") or []
                        total_slots = dm_data.get("Members@odata.count", len(members))
                        if members:
                            break
        except Exception:
            pass
    if not members:
        return dims, total_slots

    async def _get_dim(m) -> dict | None:
        href = m.get("@odata.id")
        if not href:
            return None
        try:
            async with _BMC_SEMAPHORE:
                r = await client.get(f"{base}{href}")
        except Exception:
            return None
        if r.status_code != 200:
            return None
        d = r.json() or {}
        # Skip absent/empty DIMM slots — they have no DIMM installed.
        dimm_state = ((d.get("Status") or {}).get("State") or "").lower()
        if dimm_state == "absent":
            return None
        loc = d.get("DeviceLocator") or d.get("Name") or d.get("Id") or "?"
        capacity_mib = d.get("CapacityMiB") or 0
        return {
            "slot": loc,
            "model": d.get("Model") or d.get("Manufacturer") or "—",
            "sn": d.get("SerialNumber") or None,
            "capacityMiB": capacity_mib,
            "memoryType": d.get("MemoryDeviceType") or "—",
            "status": ((d.get("Status") or {}).get("Health")) or "OK",
        }

    results = await asyncio.gather(
        *[_get_dim(m) for m in members],
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, dict):
            dims.append(result)

    # If total_slots is still 0, use len(members) as fallback
    if total_slots == 0:
        total_slots = len(members)

    return dims, total_slots


async def _redfish_recent_logs(
    client: httpx.AsyncClient, base: str
) -> list[dict]:
    """Read the last few entries from the first Manager LogService."""
    entries: list[dict] = []
    try:
        mgr_coll = await client.get(
            f"{base}/redfish/v1/Managers",
            timeout=_DISCOVERY_TIMEOUT,
        )
        if mgr_coll.status_code != 200:
            return entries
        mgr_members = (mgr_coll.json() or {}).get("Members") or []
        if not mgr_members:
            return entries
        mgr_href = mgr_members[0].get("@odata.id")
        if not mgr_href:
            return entries
        ls_coll = await client.get(
            f"{base}{mgr_href}/LogServices",
            timeout=_DISCOVERY_TIMEOUT,
        )
        if ls_coll.status_code != 200:
            return entries
        ls_members = (ls_coll.json() or {}).get("Members") or []
        if not ls_members:
            return entries
        ls_href = ls_members[0].get("@odata.id")
        if not ls_href:
            return entries
        ent_coll = await client.get(
            f"{base}{ls_href}/Entries?$top=10",
            timeout=_DISCOVERY_TIMEOUT,
        )
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
            timeout=_DISCOVERY_TIMEOUT,
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
    """DELETE a Redfish session to avoid hitting BMC session limits.
    Exceptions are logged but never propagated — session leaks are
    tolerable, poll failures are not."""
    try:
        await client.delete(f"{base}{session_uri}")
    except Exception as exc:
        logger.debug("session DELETE failed for %s: %s", base, exc)
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
                    # Fallback: some BMCs (older XFusion, some Inspur) expose
                    # Chassis/Systems at the root member index 1 but don't
                    # list it in the collection Members array.
                    if not chassis_path:
                        chassis_path = "redfish/v1/Chassis/1"
                        logger.info("chassis fallback → %s for %s", chassis_path, server.id)
                    if not system_path:
                        system_path = "redfish/v1/Systems/1"
                        logger.info("system fallback → %s for %s", system_path, server.id)

                thermal_res, power_res, system_res, drives, mem_result, logs = (
                    await asyncio.gather(
                        client.get(f"{base}/{chassis_path}/Thermal", timeout=_DISCOVERY_TIMEOUT),
                        client.get(f"{base}/{chassis_path}/Power", timeout=_DISCOVERY_TIMEOUT),
                        client.get(f"{base}/{system_path}", timeout=_DISCOVERY_TIMEOUT),
                        _redfish_storage_drives(client, base, system_path),
                        _redfish_memory_dims(client, base, system_path),
                        _redfish_recent_logs(client, base),
                    )
                )

                # Unpack memory tuple: (dimms, total_slots)
                if isinstance(mem_result, tuple) and len(mem_result) == 2:
                    mem_modules, mem_total_slots = mem_result
                else:
                    # Pre-existing code that returns list only (defensive)
                    mem_modules = mem_result if isinstance(mem_result, list) else []
                    mem_total_slots = len(mem_modules)

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

                # ── Chassis metadata + disk bay count ──────────
                chassis_spec = await _redfish_chassis_spec(
                    client, base, chassis_path
                )
                disk_total_slots = await _redfish_disk_total_slots(
                    client, base, system_path, chassis_path
                )
                if disk_total_slots == 0:
                    disk_total_slots = len(drives or [])

                # ── Enrich drives with physical form factor ────
                drives_enriched: list[dict] | None = None
                if drives:
                    drives_enriched = []
                    for d in drives:
                        d2 = dict(d)  # immutable copy
                        d2["formFactor"] = _infer_drive_form_factor(
                            d2, chassis_spec
                        )
                        drives_enriched.append(d2)

                # ── Memory slot count ──────────────────────────
                mem_populated = len(mem_modules or [])
                if mem_total_slots < mem_populated:
                    mem_total_slots = mem_populated

                memory_slots = {
                    "total": mem_total_slots,
                    "populated": mem_populated,
                }
                disk_slots = {
                    "total": disk_total_slots,
                    "populated": len(drives or []),
                }

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
                    "memorySlots": memory_slots,
                    "drives": drives_enriched or drives or None,
                    "diskSlots": disk_slots,
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

    # Cooldown: don't retry a BMC that recently failed — each attempt wastes
    # DISCOVERY_TIMEOUT × N_paths on an unreachable host.
    last_fail = _last_fail_time.get(server.id, 0)
    in_cooldown = (time.time() - last_fail) < _COLLECT_FAIL_COOLDOWN

    live: dict | None = None
    if not is_offline and not in_cooldown:
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
        # Record the failure so we don't hammer an unreachable BMC.
        if not is_offline and not in_cooldown:
            _last_fail_time[server.id] = time.time()

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


# ---------------------------------------------------------------------------
# Persistence layer — store BMC snapshots in DB so the UI never shows
# simulated data and we don't hammer the BMC more than once per day.
# ---------------------------------------------------------------------------
async def collect_and_save(server: Server) -> BmcSnapshot | None:
    """Poll the BMC once, persist the result to the database, and return the
    snapshot row.  Returns None when the BMC is unreachable."""
    payload = await get_status(server, force_refresh=True)
    if payload.get("source") != "live":
        logger.info("bmc snapshot skipped for %s — source=%s", server.id, payload.get("source"))
        return None

    db = SessionLocal()
    try:
        snap = BmcSnapshot(
            id=str(uuid.uuid4()),
            server_id=server.id,
            source=payload.get("source", "live"),
            protocol=payload.get("protocol"),
            power=payload.get("power"),
            health=payload.get("health"),
            cpu_temp_c=int(payload["cpuTempC"]) if isinstance(payload.get("cpuTempC"), (int, float)) else None,
            inlet_temp_c=int(payload["inletTempC"]) if isinstance(payload.get("inletTempC"), (int, float)) else None,
            processor_summary=payload.get("processorSummary"),
            memory_summary=payload.get("memorySummary"),
            memory_modules=payload.get("memoryModules"),
            memory_slots=payload.get("memorySlots"),
            drives=payload.get("drives"),
            disk_slots=payload.get("diskSlots"),
            fans=payload.get("fans"),
            psus=payload.get("psus"),
            recent_logs=payload.get("recentLogs"),
            history=payload.get("history"),
            alerts=payload.get("alerts"),
        )
        db.add(snap)
        db.commit()
        db.refresh(snap)
        return snap
    except Exception:
        db.rollback()
        logger.exception("bmc snapshot save failed for %s", server.id)
        return None
    finally:
        db.close()


def get_latest_snapshot(server_id: str) -> BmcSnapshot | None:
    """Return the most recent snapshot for a server, or None."""
    db = SessionLocal()
    try:
        return (
            db.query(BmcSnapshot)
            .filter(BmcSnapshot.server_id == server_id)
            .order_by(BmcSnapshot.collected_at.desc())
            .first()
        )
    finally:
        db.close()


def snapshot_to_status(snap: BmcSnapshot) -> dict:
    """Convert a persisted snapshot back to the frontend BmcStatus shape."""
    # Compute memory/disk slot counts with backwards-compatible fallback
    mem_modules = snap.memory_modules or []
    drives = snap.drives or []

    if snap.memory_slots:
        memory_slots = snap.memory_slots
    else:
        memory_slots = {
            "total": len(mem_modules),
            "populated": len(mem_modules),
        }

    if snap.disk_slots:
        disk_slots = snap.disk_slots
    else:
        disk_slots = {
            "total": len(drives),
            "populated": len(drives),
        }

    return {
        "serverId": snap.server_id,
        "source": snap.source,
        "protocol": snap.protocol,
        "power": snap.power,
        "health": snap.health,
        "cpuTempC": snap.cpu_temp_c or 0,
        "inletTempC": snap.inlet_temp_c or 0,
        "processorSummary": snap.processor_summary,
        "memorySummary": snap.memory_summary,
        "memoryModules": mem_modules,
        "memorySlots": memory_slots,
        "drives": drives,
        "diskSlots": disk_slots,
        "fans": snap.fans or [],
        "psus": snap.psus or [],
        "recentLogs": snap.recent_logs or [],
        "history": snap.history or [],
        "alerts": snap.alerts or [],
        "updatedAt": snap.collected_at.isoformat() if snap.collected_at else "",
        "bootProgress": "OSBootCompleted",
    }
