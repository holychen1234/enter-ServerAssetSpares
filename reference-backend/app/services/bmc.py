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

# Per-host semaphores to limit concurrent HTTP requests to a single BMC.
# Inspur BMCs get semaphore(1) because their lighttpd cannot handle
# concurrent TLS connections (drops with httpcore.ConnectError).
# Other vendors default to semaphore(3) (most BMCs cap at 4–8 sessions).
_HOST_SEMAPHORES: dict[str, asyncio.Semaphore] = {}


def _get_bmc_semaphore(base: str, manufacturer: str = "") -> asyncio.Semaphore:
    """Return the semaphore for a BMC host, creating it on first access."""
    host = base.removeprefix("https://").removeprefix("http://")
    if host not in _HOST_SEMAPHORES:
        concurrency = 1 if (manufacturer and "inspur" in manufacturer.lower()) else 3
        _HOST_SEMAPHORES[host] = asyncio.Semaphore(concurrency)
    return _HOST_SEMAPHORES[host]


# ---------------------------------------------------------------------------
# Persistent per-host HTTP connection pool + Redfish session cache
# ---------------------------------------------------------------------------
# Previously every _collect_redfish() call created a brand-new
# httpx.AsyncClient, forcing a full TLS handshake (3-10 s on BMCs) on
# every single poll.  With 50+ servers polled every 5 minutes that is
# 50+ TLS handshakes per cycle — the dominant source of timeouts.
#
# The shared client reuses keep-alive connections so subsequent polls
# to the same BMC skip the TLS handshake entirely.  A per-host Lock
# serialises poll lifecycles (preventing header/auth races on the
# shared client) while the per-host Semaphore still limits concurrent
# in-flight HTTP requests within a single poll.

_host_clients: dict[str, httpx.AsyncClient] = {}
_host_locks: dict[str, asyncio.Lock] = {}

# Redfish session tokens are cached per host with a TTL shorter than
# the BMC's own session timeout (typically 30 min).  This avoids 2
# extra HTTP round-trips (POST create + DELETE teardown) on every poll.
SESSION_CACHE_TTL = 1500  # 25 minutes


@dataclass
class _SessionInfo:
    token: str
    uri: str | None
    expires_at: float


_session_cache: dict[str, _SessionInfo] = {}


def _get_host_client_and_lock(
    base: str, manufacturer: str = ""
) -> tuple[httpx.AsyncClient, asyncio.Lock]:
    """Return (shared httpx client, per-host lock) for a BMC host.

    The client is created once and persisted so TCP+TLS connections are
    reused across polls via HTTP keep-alive.  The lock serialises poll
    lifecycles so auth headers on the shared client don't race.
    """
    if base not in _host_clients:
        concurrency = 1 if (manufacturer and "inspur" in manufacturer.lower()) else 3
        _host_clients[base] = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.redfish_timeout_seconds),
            verify=False,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=concurrency + 2,
                max_keepalive_connections=concurrency,
                keepalive_expiry=120,
            ),
        )
        _host_locks[base] = asyncio.Lock()
    return _host_clients[base], _host_locks[base]


async def _get_or_create_session(
    client: httpx.AsyncClient, base: str, user: str, password: str
) -> tuple[str | None, str | None]:
    """Return a cached Redfish session token, creating one if needed."""
    cached = _session_cache.get(base)
    if cached and time.time() < cached.expires_at:
        return cached.token, cached.uri

    token, uri = await _redfish_session_auth(client, base, user, password)
    if token:
        _session_cache[base] = _SessionInfo(
            token=token, uri=uri, expires_at=time.time() + SESSION_CACHE_TTL
        )
    return token, uri


def _invalidate_session(base: str) -> None:
    """Drop a cached session (e.g. when auth fails mid-poll)."""
    _session_cache.pop(base, None)


async def cleanup_clients() -> None:
    """Close all persistent HTTP clients (called on app shutdown)."""
    for client in _host_clients.values():
        await client.aclose()
    _host_clients.clear()
    _host_locks.clear()
    _session_cache.clear()


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
        "processors": [],
        "storageControllers": [],
        "memorySlots": None,
        "diskSlots": (
            {"total": server.disk_slot_count, "used": disk_count}
            if server.disk_slot_count > 0
            else None
        ),
        "recentLogs": recent_logs,
    }


# ---------------------------------------------------------------------------
# Slot detection strategies (vendor-extensible pattern)
#
# Each vendor implements a subclass of ``SlotDetectionStrategy``.  To add a
# new vendor you only need to:
#   1. Subclass ``SlotDetectionStrategy``
#   2. Register it in ``SLOT_STRATEGIES``
# No other code changes are required.
# ---------------------------------------------------------------------------
class SlotDetectionStrategy:
    """Base strategy for detecting memory/disk slot totals.

    Subclasses override the methods they can support.  The default
    returns 0 (unknown) for totals and an empty list for backplane info.
    """

    async def get_memory_slot_total(
        self,
        client: httpx.AsyncClient,
        base: str,
        system_path: str,
        chassis_path: str,
    ) -> int:
        return 0

    async def get_disk_slot_total(
        self,
        client: httpx.AsyncClient,
        base: str,
        chassis_path: str,
    ) -> int:
        return 0

    async def get_disk_backplane_info(
        self,
        client: httpx.AsyncClient,
        base: str,
        chassis_path: str,
    ) -> list[dict]:
        return []


class _DellSlotStrategy(SlotDetectionStrategy):
    """Dell PowerEdge — OEM properties under ``Oem.Dell``."""

    async def get_memory_slot_total(self, client, base, system_path, chassis_path):
        try:
            r = await client.get(f"{base}/{system_path}")
            if r.status_code == 200:
                data = r.json() or {}
                return int(_deep_get(data, "Oem", "Dell", "DellSystem", "MaxDIMMSlots") or 0)
        except Exception:
            pass
        return 0

    async def get_disk_slot_total(self, client, base, chassis_path):
        # Dell StorageEnclosure chassis carry SlotCount in OEM.
        # Discover them from the Chassis collection instead of Links
        # (some Dell BMCs don't populate ContainsChassis on the main Chassis).
        try:
            coll = await client.get(f"{base}/redfish/v1/Chassis")
            if coll.status_code != 200:
                return 0
            members = (coll.json() or {}).get("Members") or []
            total = 0
            for m in members:
                href = m.get("@odata.id")
                if not href:
                    continue
                try:
                    enc = await client.get(f"{base}{href}")
                    if enc.status_code != 200:
                        continue
                    enc_data = enc.json() or {}
                    if enc_data.get("ChassisType") != "StorageEnclosure":
                        continue
                    sc = _deep_get(enc_data, "Oem", "Dell", "DellChassisEnclosure", "SlotCount")
                    if sc:
                        total += int(sc)
                except Exception:
                    continue
            return total
        except Exception:
            return 0

    async def get_disk_backplane_info(self, client, base, chassis_path):
        # Dell StorageEnclosure carries SlotCount; form factor may be
        # inferred from enclosure name or missing altogether.
        info: list[dict] = []
        try:
            coll = await client.get(f"{base}/redfish/v1/Chassis")
            if coll.status_code != 200:
                return info
            members = (coll.json() or {}).get("Members") or []
            for m in members:
                href = m.get("@odata.id")
                if not href:
                    continue
                try:
                    enc = await client.get(f"{base}{href}")
                    if enc.status_code != 200:
                        continue
                    enc_data = enc.json() or {}
                    if enc_data.get("ChassisType") != "StorageEnclosure":
                        continue
                    sc = _deep_get(enc_data, "Oem", "Dell", "DellChassisEnclosure", "SlotCount")
                    # Try to extract form factor from enclosure name (e.g. "BP14G+ 0:1"
                    # usually means 2.5" — Dell backplane naming)
                    name = enc_data.get("Name") or ""
                    # Purely informational; default to empty if unclear
                    ff = ""
                    if "BP14G" in name or "BP14" in name:
                        ff = "2.5"
                    elif "BP12G" in name or "BP12" in name:
                        ff = "3.5"
                    if sc:
                        info.append({"formFactor": ff, "slots": int(sc)})
                except Exception:
                    continue
        except Exception:
            pass
        return info


class _XFusionSlotStrategy(SlotDetectionStrategy):
    """XFusion (超聚变) — OEM properties under ``Oem.xFusion``."""

    async def get_memory_slot_total(self, client, base, system_path, chassis_path):
        try:
            r = await client.get(f"{base}/{chassis_path}")
            if r.status_code == 200:
                data = r.json() or {}
                return int(_deep_get(data, "Oem", "xFusion", "DeviceMaxNum", "MemoryNum") or 0)
        except Exception:
            pass
        return 0

    async def get_disk_slot_total(self, client, base, chassis_path):
        backplanes = await self.get_disk_backplane_info(client, base, chassis_path)
        return sum(bp.get("slots", 0) for bp in backplanes)

    async def get_disk_backplane_info(self, client, base, chassis_path):
        """Parse backplane Description strings like '8*2.5' to extract
        per-backplane slot count and form factor."""
        info: list[dict] = []
        try:
            r = await client.get(f"{base}/{chassis_path}/Boards")
            if r.status_code != 200:
                return info
            members = (r.json() or {}).get("Members") or []
            for m in members:
                href = m.get("@odata.id")
                if not href:
                    continue
                try:
                    bp = await client.get(f"{base}{href}")
                    if bp.status_code != 200:
                        continue
                    bp_data = bp.json() or {}
                    # Check DeviceType / BoardProduct for backplane indicator
                    desc = bp_data.get("Description") or ""
                    device_type = bp_data.get("DeviceType") or ""
                    board_product = (
                        (bp_data.get("board") or {}).get("Board Product") or ""
                    )
                    if "Backplane" in device_type or "DiskBackplane" in device_type or "BP" in board_product:
                        # Parse "N*F.F" pattern from Description
                        m2 = re.search(r"(\d+)\*(\d+\.?\d*)", desc)
                        if m2:
                            info.append({
                                "formFactor": m2.group(2),
                                "slots": int(m2.group(1)),
                            })
                except Exception:
                    continue
        except Exception:
            pass
        return info


class _InspurSlotStrategy(SlotDetectionStrategy):
    """Inspur (浪潮) — OEM properties under ``Oem.Public``."""

    async def get_memory_slot_total(self, client, base, system_path, chassis_path):
        try:
            r = await client.get(f"{base}/{chassis_path}")
            if r.status_code == 200:
                data = r.json() or {}
                return int(_deep_get(data, "Oem", "Public", "DeviceMaxNum", "MemoryNum") or 0)
        except Exception:
            pass
        return 0

    # Inspur disk slot total CANNOT be auto-detected (DeviceMaxNum.DiskNum=0,
    # DriveSlots returns 1010, backplanes carry no slot count).  Return 0 to
    # signal "unknown — use server.disk_slot_count fallback".


class _GenericSlotStrategy(SlotDetectionStrategy):
    """Fallback: try Dell → XFusion → Inspur paths in order."""

    _delegates: list[SlotDetectionStrategy] = []

    def __init__(self):
        if not self._delegates:
            self._delegates = [
                _DellSlotStrategy(),
                _XFusionSlotStrategy(),
                _InspurSlotStrategy(),
            ]

    async def get_memory_slot_total(self, client, base, system_path, chassis_path):
        for d in self._delegates:
            v = await d.get_memory_slot_total(client, base, system_path, chassis_path)
            if v > 0:
                return v
        return 0

    async def get_disk_slot_total(self, client, base, chassis_path):
        for d in self._delegates:
            v = await d.get_disk_slot_total(client, base, chassis_path)
            if v > 0:
                return v
        return 0

    async def get_disk_backplane_info(self, client, base, chassis_path):
        for d in self._delegates:
            info = await d.get_disk_backplane_info(client, base, chassis_path)
            if info:
                return info
        return []


# Registry: manufacturer name → strategy instance.
# Keys should match the values stored in the ``servers.manufacturer`` column.
SLOT_STRATEGIES: dict[str, SlotDetectionStrategy] = {
    "Dell": _DellSlotStrategy(),
    "XFusion": _XFusionSlotStrategy(),
    "Inspur": _InspurSlotStrategy(),
}
_FALLBACK_STRATEGY = _GenericSlotStrategy()


def _get_slot_strategy(manufacturer: str) -> SlotDetectionStrategy:
    """Resolve the slot-detection strategy for a given manufacturer."""
    if not manufacturer:
        return _FALLBACK_STRATEGY
    # Case-insensitive lookup
    for key, strategy in SLOT_STRATEGIES.items():
        if key.lower() == manufacturer.lower():
            return strategy
    return _FALLBACK_STRATEGY


def _compute_slot_usage(
    drives: list[dict] | None,
    memory_modules: list[dict] | None,
) -> tuple[dict, dict]:
    """Count real (non-placeholder) drives and memory modules.

    Returns ``(memory_slots_used_dict, disk_slots_used_dict)`` where each
    dict only contains the ``"used"`` key.
    """
    # A drive is "real" if it has a model, SN, or positive capacity.
    disk_used = 0
    for d in (drives or []):
        model = d.get("model", "")
        sn = d.get("sn")
        cap = d.get("capacityGB", 0)
        if (model and model != "—") or sn or (cap and cap > 0):
            disk_used += 1

    # Memory modules: all members returned by the BMC are treated as occupied
    # (empty slots don't appear in the Memory collection).
    mem_used = len(memory_modules or [])

    return {"used": mem_used}, {"used": disk_used}


def _build_slot_info(
    total: int,
    used: int,
    backplanes: list[dict] | None = None,
) -> dict | None:
    """Build a ``memorySlots`` / ``diskSlots`` dict for the frontend.

    Returns ``None`` when there is no data at all (both total and used are 0).
    """
    if total == 0 and used == 0:
        return None
    result: dict[str, Any] = {"total": total, "used": used}
    if backplanes:
        result["backplanes"] = backplanes
        # If all backplanes share the same form factor, add a top-level
        # shorthand so the UI can render a compact label.
        form_factors = {bp.get("formFactor", "") for bp in backplanes}
        if len(form_factors) == 1 and "" not in form_factors:
            result["formFactor"] = next(iter(form_factors))
    return result


# ---------------------------------------------------------------------------
# Redfish
# ---------------------------------------------------------------------------
async def _tcp_reachable(mgmt_ip: str, port: int = 443, timeout: float = 5.0) -> bool:
    """Quick TCP pre-check — returns False in ~5s if the BMC is firewalled."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(mgmt_ip, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def _deep_get(d: dict, *keys: str) -> Any:
    """Safely traverse a nested dict path, returning None on any miss."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d
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


def _parse_drive_capacity_gb(d: dict) -> int:
    """Extract drive capacity in GB from a Redfish Drive resource.

    Tries ``CapacityBytes`` (standard) first, then falls back to the
    deprecated ``CapacityMiB`` field still used by some Inspur / H3C
    firmware for drives exposed through the chassis path."""
    cap_bytes = d.get("CapacityBytes")
    if isinstance(cap_bytes, (int, float)) and cap_bytes > 0:
        return round(cap_bytes / (1024**3), 0)
    cap_mib = d.get("CapacityMiB")
    if isinstance(cap_mib, (int, float)) and cap_mib > 0:
        return round(cap_mib / 1024, 1)
    return 0


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


def _dedup_drives(*lists: list[dict]) -> list[dict]:
    """Merge drive lists, deduplicating by (name, sn) so the same physical
    drive found via multiple Redfish paths is only counted once."""
    seen: set[tuple[str, str | None]] = set()
    merged: list[dict] = []
    for lst in lists:
        for d in lst:
            key = (d.get("name", ""), d.get("sn"))
            if key not in seen:
                seen.add(key)
                merged.append(d)
    return merged


async def _redfish_storage_drives(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Discover drives with a primary path + supplement strategy.

    *Path 1* (Storage modern) is the canonical source and runs first.
    When it succeeds we supplement with *Path 3* (Chassis/Drives) because
    some vendors (Inspur / H3C) expose rear-backplane system drives ONLY
    at the chassis level.  We merge both lists with deduplication so
    drives that appear in both paths aren't double-counted.

    Fallback chain (only when Path 1 returns nothing):
    Path 1 → Path 2 (SimpleStorage) → Path 3 (Chassis/Drives) → Path 4 (Deep drill)."""
    all_drives: list[dict] = []
    try:
        # Path 1: modern Storage schema (Dell iDRAC 9+, Supermicro X11+, etc.)
        primary = await _redfish_storage_modern(client, base, system_path)
        if primary:
            logger.info("redfish storage: got %d drives via Path 1 (Storage)", len(primary))
            # Supplement: also try Chassis/Drives for rear-backplane /
            # NVMe system drives that some BMCs only expose at the chassis
            # level (e.g. Inspur rear 2.5" SATA bays, H3C NVMe riser drives).
            supplement = await _redfish_chassis_drives(client, base)
            if supplement:
                logger.info("redfish storage: got %d supplemental drives via Path 3 (Chassis/Drives)", len(supplement))
                all_drives = _dedup_drives(primary, supplement)
            else:
                all_drives = primary
            return all_drives

        # ── Fallback chain (no drives from Path 1) ──
        logger.info("redfish storage: Path 1 returned 0 drives, trying fallbacks")
        # Path 2: SimpleStorage (older Dell iDRAC 8, HPE iLO 4)
        drives = await _redfish_storage_simple(client, base, system_path)
        if drives:
            logger.info("redfish storage: got %d drives via Path 2 (SimpleStorage)", len(drives))
            return drives
        # Path 3: Chassis-level Drives (XFusion, H3C, and other vendors where
        # /Systems/X/Storage returns 404 but /Chassis/X/Drives contains the
        # full drive collection).
        drives = await _redfish_chassis_drives(client, base)
        if drives:
            logger.info("redfish storage: got %d drives via Path 3 (Chassis/Drives)", len(drives))
            return drives
        # Path 4: Deep-drill Storage controllers (Inspur / some H3C). Some
        # BMCs report controllers in /Systems/X/Storage but don't surface
        # drives via the standard Members→Drives array. We fetch each
        # controller and try Links.Drives or /Drives sub-path directly.
        drives = await _redfish_storage_deep(client, base, system_path)
        if drives:
            logger.info("redfish storage: got %d drives via Path 4 (Storage deep)", len(drives))
        if not drives:
            logger.info("redfish storage: all 4 paths returned 0 drives for %s", base)
    except Exception:
        pass  # Storage isn't critical — keep returning what we have
    return all_drives or drives


async def _redfish_storage_controllers_health(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Fetch Storage / RAID controller health from
    ``/Systems/{id}/Storage`` members."""
    controllers: list[dict] = []
    try:
        storage_coll = await client.get(f"{base}/{system_path}/Storage")
    except Exception:
        return controllers
    if storage_coll.status_code != 200:
        return controllers
    members = (storage_coll.json() or {}).get("Members") or []

    async def _get_ctrl(m):
        try:
            resp = await client.get(f"{base}{m['@odata.id']}")
            if resp.status_code != 200:
                return None
            c = resp.json() or {}
            return {
                "name": c.get("Name") or c.get("Id") or "?",
                "model": c.get("Model") or "—",
                "status": ((c.get("Status") or {}).get("Health")) or "OK",
            }
        except Exception:
            return None

    results = await asyncio.gather(
        *[_get_ctrl(m) for m in members], return_exceptions=True
    )
    controllers = [r for r in results if isinstance(r, dict)]
    return controllers


async def _redfish_processors_health(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Fetch processor health from ``/Systems/{id}/Processors`` members."""
    procs: list[dict] = []
    try:
        proc_coll = await client.get(f"{base}/{system_path}/Processors")
    except Exception:
        return procs
    if proc_coll.status_code != 200:
        return procs
    members = (proc_coll.json() or {}).get("Members") or []

    async def _get_proc(m):
        try:
            resp = await client.get(f"{base}{m['@odata.id']}")
            if resp.status_code != 200:
                return None
            p = resp.json() or {}
            return {
                "name": p.get("Name") or p.get("Id") or "?",
                "model": p.get("Model") or "—",
                "status": ((p.get("Status") or {}).get("Health")) or "OK",
            }
        except Exception:
            return None

    results = await asyncio.gather(
        *[_get_proc(m) for m in members], return_exceptions=True
    )
    procs = [r for r in results if isinstance(r, dict)]
    return procs


async def _redfish_storage_modern(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Redfish Storage schema (iDRAC 9+, Supermicro X11+, etc.).

    Controllers and drives are fetched in parallel to stay within the
    per-request timeout window even on BMCs with many drives (e.g. Inspur
    with 9+ drives behind a single PCIE2_RAID controller)."""
    drives: list[dict] = []
    try:
        storage_coll = await client.get(f"{base}/{system_path}/Storage")
    except Exception:
        return drives
    if storage_coll.status_code != 200:
        logger.info(
            "redfish storage: /Storage returned %s for %s",
            storage_coll.status_code, base,
        )
        return drives
    members = (storage_coll.json() or {}).get("Members") or []
    if not members:
        logger.info("redfish storage: /Storage has no Members for %s", base)

    # ── Phase 1: fetch every controller in parallel to collect drive hrefs ──
    async def _controller_drive_hrefs(m) -> list[str]:
        hrefs: list[str] = []
        seen: set[str] = set()
        ctrl_href = m.get("@odata.id")
        if not ctrl_href:
            return hrefs
        try:
            async with _get_bmc_semaphore(base):
                r = await client.get(f"{base}{ctrl_href}")
        except Exception:
            return hrefs
        if r.status_code != 200:
            return hrefs
        storage: dict = r.json() or {}

        # Collect from Drives array (standard Redfish)
        for dref in storage.get("Drives") or []:
            dhref = dref.get("@odata.id") if isinstance(dref, dict) else None
            if dhref and dhref not in seen:
                seen.add(dhref)
                hrefs.append(dhref)

        # Collect from Links.Drives (Inspur / H3C rear-backplane system
        # drives are sometimes only referenced here and NOT in the
        # top-level Drives array).
        for dref in storage.get("Links", {}).get("Drives") or []:
            dhref = dref.get("@odata.id") if isinstance(dref, dict) else None
            if dhref and dhref not in seen:
                seen.add(dhref)
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
            async with _get_bmc_semaphore(base):
                r = await client.get(f"{base}{href}")
        except Exception:
            return None
        if r.status_code != 200:
            return None
        d = r.json() or {}
        # Skip absent / empty bays — Dell iDRAC (and others) report
        # unpopulated slots with Status.State == "Absent" and no model,
        # SN, or capacity.  Including them creates phantom "disks" that
        # look like anomalies in the UI and Prometheus metrics.
        state = (d.get("Status") or {}).get("State")
        if state == "Absent":
            return None
        model = d.get("Model")
        sn = d.get("SerialNumber")
        cap_gb = _parse_drive_capacity_gb(d)
        if not model and not sn and cap_gb == 0:
            return None
        return {
            "name": d.get("Name") or d.get("Id") or "?",
            "model": model or "—",
            "sn": sn or None,
            "capacityGB": cap_gb,
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
            # Skip absent / empty bays
            if ((dev.get("Status") or {}).get("State")) == "Absent":
                continue
            model = dev.get("Model")
            sn = dev.get("SerialNumber")
            cap_gb = _parse_drive_capacity_gb(dev)
            if not model and not sn and cap_gb == 0:
                continue
            drives.append(
                {
                    "name": dev.get("Name") or f"Disk.Bay.{i+1}",
                    "model": model or "—",
                    "sn": sn or None,
                    "capacityGB": cap_gb,
                    "mediaType": "—",
                    "status": ((dev.get("Status") or {}).get("Health")) or "OK",
                }
            )
    return drives


async def _redfish_chassis_drives(
    client: httpx.AsyncClient, base: str
) -> list[dict]:
    """Discover drives via ``/Chassis/X/Drives``.

    Some vendors (XFusion, H3C, Lenovo XCC, etc.) expose drives at the
    chassis level instead of under ``/Systems/X/Storage``. The drive
    schema is the same standard Redfish ``#Drive`` resource so we reuse
    the same field mapping.

    Lenovo XCC in particular has multiple chassis members (e.g. /Chassis/1
    for the system enclosure and /Chassis/3 for the storage backplane).
    Drives are only under the backplane member, so we must iterate ALL
    chassis members instead of just the first one.
    """
    drives: list[dict] = []
    # Fetch ALL chassis members — drives may be under any of them
    # (e.g. Lenovo XCC puts drives under /Chassis/3, not /Chassis/1).
    chassis_members: list[str] = []
    try:
        coll = await client.get(f"{base}/redfish/v1/Chassis")
        if coll.status_code == 200:
            for m in (coll.json() or {}).get("Members") or []:
                href = m.get("@odata.id")
                if href:
                    chassis_members.append(href.lstrip("/"))
    except Exception:
        pass
    if not chassis_members:
        # Fallback: try first member discovery (single-member BMCs)
        chassis_path = await _redfish_first_member(client, base, "Chassis")
        if chassis_path:
            chassis_members = [chassis_path]

    if not chassis_members:
        return drives
    try:
        for chassis_path in chassis_members:
            coll = await client.get(f"{base}/{chassis_path}/Drives")
            if coll.status_code != 200:
                logger.debug(
                    "redfish chassis drives: %s/Drives returned %s",
                    chassis_path, coll.status_code,
                )
                # Lenovo XCC doesn't expose /Chassis/X/Drives but lists
                # all drive @odata.id refs under Chassis.Links.Drives.
                # The drive URLs are standard /Systems/X/Storage/.../Drives/Y
                # resources, just not discoverable via the Storage collection
                # (which returns empty Members on older XCC firmware).
                chassis_resp = await client.get(f"{base}/{chassis_path}")
                if chassis_resp.status_code == 200:
                    links_drives = (
                        (chassis_resp.json() or {})
                        .get("Links", {})
                        .get("Drives", [])
                    )
                    if links_drives:
                        logger.info(
                            "redfish chassis drives: %s/Links.Drives has %d refs",
                            chassis_path, len(links_drives),
                        )
                        for dref in links_drives:
                            dhref = dref.get("@odata.id") if isinstance(dref, dict) else None
                            if not dhref:
                                continue
                            dr = await client.get(f"{base}{dhref}")
                            if dr.status_code != 200:
                                continue
                            d = dr.json() or {}
                            state = (d.get("Status") or {}).get("State")
                            if state == "Absent":
                                continue
                            model = d.get("Model")
                            sn = d.get("SerialNumber")
                            cap_gb = _parse_drive_capacity_gb(d)
                            if not model and not sn and cap_gb == 0:
                                continue
                            drives.append(
                                {
                                    "name": d.get("Name") or d.get("Id") or "?",
                                    "model": model or "—",
                                    "sn": sn or None,
                                    "capacityGB": cap_gb,
                                    "mediaType": d.get("MediaType") or "—",
                                    "status": ((d.get("Status") or {}).get("Health")) or "OK",
                                }
                            )
                continue
            members = (coll.json() or {}).get("Members") or []
            if not members:
                continue
            logger.info(
                "redfish chassis drives: %s/Drives has %d members",
                chassis_path, len(members),
            )
            for m in members:
                href = m.get("@odata.id")
                if not href:
                    continue
                dr = await client.get(f"{base}{href}")
                if dr.status_code != 200:
                    continue
                d = dr.json() or {}
                # Skip absent / empty bays
                state = (d.get("Status") or {}).get("State")
                if state == "Absent":
                    continue
                model = d.get("Model")
                sn = d.get("SerialNumber")
                cap_gb = _parse_drive_capacity_gb(d)
                # Skip placeholder entries: if the drive has no Model, no SN
                # AND zero capacity, it's a stub. But if any one field is
                # present, keep it — some Inspur BMCs report valid drives
                # with zero capacity but have a model name.
                if not model and not sn and cap_gb == 0:
                    continue
                drives.append(
                    {
                        "name": d.get("Name") or d.get("Id") or "?",
                        "model": model or "—",
                        "sn": sn or None,
                        "capacityGB": cap_gb,
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
        coll = await client.get(f"{base}/{system_path}/Storage")
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
                # Skip absent / empty bays
                state = (d.get("Status") or {}).get("State")
                if state == "Absent":
                    continue
                model = d.get("Model")
                sn = d.get("SerialNumber")
                cap_gb = _parse_drive_capacity_gb(d)
                if not model and not sn and cap_gb == 0:
                    continue
                found.append({
                    "name": d.get("Name") or d.get("Id") or "?",
                    "model": model or "—",
                    "sn": sn or None,
                    "capacityGB": cap_gb,
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
                        # Skip absent / empty bays
                        state = (d.get("Status") or {}).get("State")
                        if state == "Absent":
                            continue
                        model = d.get("Model")
                        sn = d.get("SerialNumber")
                        cap_gb = _parse_drive_capacity_gb(d)
                        if not model and not sn and cap_gb == 0:
                            continue
                        found.append({
                            "name": d.get("Name") or d.get("Id") or "?",
                            "model": model or "—",
                            "sn": sn or None,
                            "capacityGB": cap_gb,
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


async def _redfish_memory_dims(
    client: httpx.AsyncClient, base: str, system_path: str
) -> list[dict]:
    """Discover individual DIMMs under ``/Systems/X/Memory``.

    All DIMM detail requests are fetched in parallel so the full set
    completes within the per-request timeout window (previously serial
    enumeration could easily exceed 30 s on servers with 8+ DIMMs)."""
    dims: list[dict] = []
    try:
        coll = await client.get(f"{base}/{system_path}/Memory")
        if coll.status_code != 200:
            return dims
        members = (coll.json() or {}).get("Members") or []
    except Exception:
        return dims

    if not members:
        # Fallback: some Inspur BMCs expose memory under
        # /MemoryDomains/{domain}/Memory instead of /Memory directly.
        try:
            dm_coll = await client.get(f"{base}/{system_path}/MemoryDomains")
            if dm_coll.status_code == 200:
                for dm_member in (dm_coll.json() or {}).get("Members") or []:
                    dm_href = dm_member.get("@odata.id")
                    if not dm_href:
                        continue
                    dm_res = await client.get(f"{base}{dm_href}/Memory")
                    if dm_res.status_code == 200:
                        members = (dm_res.json() or {}).get("Members") or []
                        if members:
                            break
        except Exception:
            pass
    if not members:
        return dims

    async def _get_dim(m) -> dict | None:
        href = m.get("@odata.id")
        if not href:
            return None
        try:
            async with _get_bmc_semaphore(base):
                r = await client.get(f"{base}{href}")
        except Exception:
            return None
        if r.status_code != 200:
            return None
        d = r.json() or {}
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
    has_creds = bool(server.bmc_user and server.bmc_password)

    try:
        client, host_lock = _get_host_client_and_lock(base, server.manufacturer or "")
        async with host_lock:
            try:
                # Pre-create the per-host semaphore so inner functions
                # (_redfish_storage_drives, _redfish_memory_dims, etc.)
                # inherit the correct concurrency limit for this vendor.
                # Must be done BEFORE any HTTP request so the first lookup
                # creates the semaphore with the right manufacturer hint.
                _get_bmc_semaphore(base, server.manufacturer or "")

                # Try cached session first, fall back to Basic auth.
                if has_creds:
                    session_token, session_uri = await _get_or_create_session(
                        client, base, server.bmc_user, server.bmc_password
                    )
                    if session_token:
                        client.headers["X-Auth-Token"] = session_token
                    else:
                        client.auth = (server.bmc_user, server.bmc_password)

                # Save auth state so we can restore it after the poll
                # (the client is shared across polls).
                _saved_headers = dict(client.headers)
                _saved_auth = client.auth

                # Discover collection members.
                # Inspur BMC lighttpd cannot handle concurrent TLS connections,
                # so serialise these two discovery calls for Inspur.
                if server.manufacturer and "inspur" in server.manufacturer.lower():
                    chassis_path = await _redfish_first_member(
                        client, base, "Chassis"
                    )
                    system_path = await _redfish_first_member(
                        client, base, "Systems"
                    )
                else:
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

                # Resolve slot-detection strategy for this vendor
                slot_strategy = _get_slot_strategy(server.manufacturer)

                # Inspur BMC lighttpd cannot handle concurrent TLS connections
                # (drops with httpcore.ConnectError), so we serialise *all*
                # requests for those hosts.  Other vendors keep the parallel
                # gather for speed.
                if server.manufacturer and "inspur" in server.manufacturer.lower():
                    thermal_res = await client.get(
                        f"{base}/{chassis_path}/Thermal"
                    )
                    power_res = await client.get(
                        f"{base}/{chassis_path}/Power"
                    )
                    system_res = await client.get(
                        f"{base}/{system_path}"
                    )
                    drives = await _redfish_storage_drives(
                        client, base, system_path
                    )
                    mem_modules = await _redfish_memory_dims(
                        client, base, system_path
                    )
                    logs = await _redfish_recent_logs(client, base)
                    memory_slot_total = await slot_strategy.get_memory_slot_total(
                        client, base, system_path, chassis_path,
                    )
                    disk_slot_total = await slot_strategy.get_disk_slot_total(
                        client, base, chassis_path,
                    )
                    backplane_info = await slot_strategy.get_disk_backplane_info(
                        client, base, chassis_path,
                    )
                    controllers = await _redfish_storage_controllers_health(
                        client, base, system_path,
                    )
                    processors = await _redfish_processors_health(
                        client, base, system_path,
                    )
                else:
                    thermal_res, power_res, system_res, drives, mem_modules, \
                        logs, memory_slot_total, disk_slot_total, \
                        backplane_info, controllers, processors = (
                        await asyncio.gather(
                            client.get(f"{base}/{chassis_path}/Thermal"),
                            client.get(f"{base}/{chassis_path}/Power"),
                            client.get(f"{base}/{system_path}"),
                            _redfish_storage_drives(
                                client, base, system_path
                            ),
                            _redfish_memory_dims(
                                client, base, system_path
                            ),
                            _redfish_recent_logs(client, base),
                            slot_strategy.get_memory_slot_total(
                                client, base, system_path, chassis_path,
                            ),
                            slot_strategy.get_disk_slot_total(
                                client, base, chassis_path,
                            ),
                            slot_strategy.get_disk_backplane_info(
                                client, base, chassis_path,
                            ),
                            _redfish_storage_controllers_health(
                                client, base, system_path,
                            ),
                            _redfish_processors_health(
                                client, base, system_path,
                            ),
                        )
                    )

                if thermal_res.status_code != 200 or system_res.status_code != 200:
                    # 401 = cached session token is stale/invalid.
                    # Invalidate the cache and retry once with Basic auth.
                    if (
                        has_creds
                        and (thermal_res.status_code == 401 or system_res.status_code == 401)
                    ):
                        logger.info(
                            "redfish 401 for %s — invalidating session, "
                            "retrying with Basic auth", server.id,
                        )
                        _invalidate_session(base)
                        client.headers.pop("X-Auth-Token", None)
                        client.auth = (server.bmc_user, server.bmc_password)

                        # Re-fetch the two critical endpoints
                        thermal_res = await client.get(f"{base}/{chassis_path}/Thermal")
                        system_res = await client.get(f"{base}/{system_path}")

                    if thermal_res.status_code != 200 or system_res.status_code != 200:
                        logger.warning(
                            "redfish http error for %s: thermal=%s system=%s",
                            server.id,
                            thermal_res.status_code,
                            system_res.status_code,
                        )
                        return None
                    # Re-fetch power as well if we just switched to Basic auth
                    if power_res.status_code != 200 and has_creds:
                        power_res = await client.get(f"{base}/{chassis_path}/Power")

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

                # Compute slot usage from collected data
                mem_used, disk_used = _compute_slot_usage(drives, mem_modules)
                # Disk total: prefer auto-detection, fall back to manual
                # server.disk_slot_count (needed for Inspur)
                _disk_total = disk_slot_total or (
                    server.disk_slot_count if server.disk_slot_count > 0 else 0
                )
                memory_slots = _build_slot_info(memory_slot_total, mem_used["used"])
                disk_slots = _build_slot_info(_disk_total, disk_used["used"], backplane_info)

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
                    "memorySlots": memory_slots,
                    "diskSlots": disk_slots,
                    "processors": processors or None,
                    "storageControllers": controllers or None,
                    "recentLogs": logs or None,
                }
            finally:
                # Restore the shared client's auth state so the next
                # poll (possibly for a different server/host) starts clean.
                # Session tokens are cached separately and reused — no
                # need to DELETE them on every poll.
                client.headers.clear()
                client.headers.update(_saved_headers)
                client.auth = _saved_auth
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
        try:
            if server.bmc_protocol == "redfish":
                # Inspur BMCs need more time because we serialise all
                # requests to work around their lighttpd TLS concurrency bug.
                _vendor_timeout = settings.redfish_timeout_seconds + 10
                if server.manufacturer and "inspur" in server.manufacturer.lower():
                    _vendor_timeout = max(_vendor_timeout, 150)
                live = await asyncio.wait_for(
                    _collect_redfish(server),
                    timeout=_vendor_timeout,
                )
            else:
                live = await asyncio.wait_for(
                    asyncio.to_thread(_collect_ipmi, server),
                    timeout=settings.redfish_timeout_seconds + 10,
                )
        except asyncio.TimeoutError:
            logger.warning("get_status timeout for %s (ip=%s)", server.id, server.mgmt_ip)
            live = None

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


# ---------------------------------------------------------------------------
# Failed-host cooldown — used by the weekly auto-poller (main.py) to avoid
# retrying unreachable BMCs on every cycle.  Manual refresh always bypasses
# the cooldown.
# ---------------------------------------------------------------------------
_FAILED_HOSTS: dict[str, float] = {}           # ip → next_retry_timestamp
_FAILED_COUNTS: dict[str, int] = {}             # ip → consecutive failure count
_COOLDOWN_SECONDS: float = 1800.0               # 30 min cooldown after repeated failures
_COOLDOWN_THRESHOLD = 3                          # set cooldown only after N consecutive failures


def _set_cooldown(mgmt_ip: str | None) -> None:
    """Record a failure; only enter cooldown after N consecutive failures.

    A single transient 503 or ReadTimeout should NOT block the BMC for
    30 minutes — the next poll cycle should be allowed to retry.
    Only after repeated failures do we consider the host truly dead.
    """
    if not mgmt_ip:
        return
    count = _FAILED_COUNTS.get(mgmt_ip, 0) + 1
    _FAILED_COUNTS[mgmt_ip] = count
    if count >= _COOLDOWN_THRESHOLD:
        _FAILED_HOSTS[mgmt_ip] = time.time() + _COOLDOWN_SECONDS


def _clear_cooldown(mgmt_ip: str | None) -> None:
    if mgmt_ip:
        _FAILED_HOSTS.pop(mgmt_ip, None)
        _FAILED_COUNTS.pop(mgmt_ip, None)


def _in_cooldown(mgmt_ip: str | None) -> bool:
    if not mgmt_ip:
        return False
    next_retry = _FAILED_HOSTS.get(mgmt_ip)
    return next_retry is not None and time.time() < next_retry


# ---------------------------------------------------------------------------
# Persistence layer — store BMC snapshots in DB so the UI never shows
# simulated data and we don't hammer the BMC more than once per day.
# ---------------------------------------------------------------------------
async def collect_and_save(server: Server) -> BmcSnapshot | None:
    """Poll the BMC once, persist the result to the database, and return the
    snapshot row.  Returns None when the BMC is unreachable."""
    # Single attempt — the connection pool keeps TLS warm so the real
    # timeout is much shorter than before.  Dead hosts are handled by
    # the cooldown mechanism in the weekly poller; retrying here just
    # doubled the effective timeout (70 s + 2 s sleep + 70 s = 142 s
    # per dead host) and blocked the poller from moving on.
    payload = await get_status(server, force_refresh=True)

    if payload.get("source") != "live":
        logger.info("bmc snapshot skipped for %s — source=%s", server.id, payload.get("source"))
        _set_cooldown(server.mgmt_ip)
        return None

    # Successful live poll — clear the cooldown so the weekly poll will
    # try this host again, and the latest data overwrites whatever was
    # stored by the last auto-poll.
    _clear_cooldown(server.mgmt_ip)

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
            drives=payload.get("drives"),
            memory_slots=payload.get("memorySlots"),
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


def snapshot_to_status(snap: BmcSnapshot, server: Server | None = None) -> dict:
    """Convert a persisted snapshot back to the frontend BmcStatus shape.

    When *server* is provided and has ``disk_slot_count > 0``, the
    function patches ``diskSlots.total`` so that a stale snapshot
    (taken before the operator manually entered the bay count) still
    reflects the current configuration.  This is essential for Inspur
    BMCs where Redfish cannot auto-detect the total bay count.
    """
    disk_slots = snap.disk_slots

    # Patch diskSlots from server.disk_slot_count when the snapshot
    # predates the manual configuration (or when the BMC can't detect
    # the total at all, e.g. Inspur).
    if server and server.disk_slot_count and server.disk_slot_count > 0:
        if not disk_slots or disk_slots.get("total", 0) == 0:
            # Count used drives from the snapshot so the bar stays accurate
            used = 0
            for d in (snap.drives or []):
                model = d.get("model", "")
                sn = d.get("sn")
                cap = d.get("capacityGB", 0)
                if (model and model != "—") or sn or (cap and cap > 0):
                    used += 1
            disk_slots = {
                "total": server.disk_slot_count,
                "used": used,
            }
            # Preserve backplane info if present
            if isinstance(snap.disk_slots, dict) and snap.disk_slots.get("backplanes"):
                disk_slots["backplanes"] = snap.disk_slots["backplanes"]

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
        "memoryModules": snap.memory_modules or [],
        "drives": snap.drives or [],
        "memorySlots": snap.memory_slots,
        "diskSlots": disk_slots,
        "fans": snap.fans or [],
        "psus": snap.psus or [],
        "recentLogs": snap.recent_logs or [],
        "history": snap.history or [],
        "alerts": snap.alerts or [],
        "updatedAt": snap.collected_at.isoformat() if snap.collected_at else "",
        "bootProgress": "OSBootCompleted",
    }
