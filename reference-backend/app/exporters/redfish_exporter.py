"""
Prometheus Redfish exporter — exposes component health status for all
servers via a single ``/metrics/redfish`` endpoint.

Metrics:
  redfish_up, redfish_server_health,
  redfish_cpu_health, redfish_memory_health,
  redfish_drive_health, redfish_storage_controller_health

A background asyncio task refreshes every server on a configurable interval
(``REDFISH_EXPORTER_INTERVAL``, default 300 s).  The metrics endpoint reads
an in-memory cache and returns in sub-millisecond time — Prometheus never
triggers a live BMC poll itself, so the scrape never times out even with
hundreds of servers.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.db.base import SessionLocal
from app.db.models import Server
from app.services import bmc as bmc_svc
from app.settings import settings

_log = logging.getLogger("redfish.exporter")

router = APIRouter(tags=["prometheus"])

# ── Global cache ─────────────────────────────────────────────────
# key = server.id (UUID string)


@dataclass
class _CacheEntry:
    payload: dict  # get_status() return dict
    ts: float      # time.time() when refreshed
    ok: bool       # True = successful scrape
    error: str = ""


_cache: dict[str, _CacheEntry] = {}

# ── Background refresh state ─────────────────────────────────────

_refresh_task: asyncio.Task | None = None
_running = False

# ── Helpers ──────────────────────────────────────────────────────


def _get_servers_with_creds() -> List[Server]:
    """Return all servers that have BMC credentials configured."""
    db = SessionLocal()
    try:
        return (
            db.query(Server)
            .filter(
                Server.mgmt_ip.isnot(None),
                Server.mgmt_ip != "",
                Server.bmc_user.isnot(None),
                Server.bmc_user != "",
                Server.bmc_password.isnot(None),
                Server.bmc_password != "",
            )
            .all()
        )
    finally:
        db.close()


def _prom_label(value: str | None) -> str:
    """Escape a Prometheus label value (backslash, double-quote, newline)."""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _server_labels(s: Server) -> str:
    """Return the shared label set for a server."""
    return (
        f'hostname="{_prom_label(s.hostname)}",'
        f'sn="{_prom_label(s.sn)}",'
        f'manufacturer="{_prom_label(s.manufacturer)}",'
        f'mgmt_ip="{_prom_label(s.mgmt_ip)}"'
    )


def _health_int(h: str | None) -> int:
    """Map Redfish Health string → Prometheus numeric gauge value."""
    if h == "Critical":
        return 2
    if h == "Warning":
        return 1
    return 0  # OK or anything else


def _format_metrics() -> str:
    """Dump the entire cache as Prometheus exposition format.

    Only health-status metrics are exposed (CPU, memory, drives,
    storage controllers, and overall server health).  Operational
    data such as temperatures, fan speeds, power consumption and
    slot counts are intentionally omitted to keep the alert surface
    focused.
    """
    lines: list[str] = []

    for _server_id, entry in sorted(_cache.items()):
        labels = entry.payload.get("__labels__") or ""
        if not labels:
            continue

        # ── redfish_up ──
        lines.append(f"redfish_up{{{labels}}} {1 if entry.ok else 0}")
        lines.append(f"redfish_scrape_timestamp_seconds{{{labels}}} {entry.ts:.3f}")
        if entry.error:
            err = _prom_label(entry.error)
            lines.append(f'redfish_scrape_error{{{labels}}} "{err}"')

        if not entry.ok or not entry.payload:
            continue

        p = entry.payload

        # ── server overall health ──
        overall = p.get("health", "OK")
        lines.append(
            f"redfish_server_health{{{labels}}} {_health_int(overall)}"
        )

        # ── CPU health (per physical processor) ──
        for cpu in p.get("processors") or []:
            cpu_labels = (
                f'{labels},'
                f'name="{_prom_label(cpu.get("name"))}",'
                f'model="{_prom_label(cpu.get("model"))}"'
            )
            lines.append(
                f"redfish_cpu_health{{{cpu_labels}}} "
                f"{_health_int(cpu.get('status'))}"
            )

        # ── memory health (per DIMM) ──
        for m in p.get("memoryModules") or []:
            m_labels = (
                f'{labels},'
                f'slot="{_prom_label(m.get("slot"))}",'
                f'type="{_prom_label(m.get("memoryType"))}",'
                f'model="{_prom_label(m.get("model"))}"'
            )
            lines.append(
                f"redfish_memory_health{{{m_labels}}} "
                f"{_health_int(m.get('status'))}"
            )

        # ── drive health (per physical disk) ──
        for d in p.get("drives") or []:
            d_labels = (
                f'{labels},'
                f'slot="{_prom_label(d.get("name"))}",'
                f'model="{_prom_label(d.get("model"))}",'
                f'sn_drive="{_prom_label(d.get("sn"))}",'
                f'media="{_prom_label(d.get("mediaType"))}"'
            )
            lines.append(
                f"redfish_drive_health{{{d_labels}}} "
                f"{_health_int(d.get('status'))}"
            )

        # ── storage / RAID controller health ──
        for ctrl in p.get("storageControllers") or []:
            c_labels = (
                f'{labels},'
                f'name="{_prom_label(ctrl.get("name"))}",'
                f'model="{_prom_label(ctrl.get("model"))}"'
            )
            lines.append(
                f"redfish_storage_controller_health{{{c_labels}}} "
                f"{_health_int(ctrl.get('status'))}"
            )

    return "\n".join(lines) + "\n"


# ── Background refresh loop ──────────────────────────────────────


def _vendor_timeout(manufacturer: str | None) -> float:
    """Return the timeout that matches what ``get_status`` uses internally.

    The exporter's outer ``wait_for`` must be >= the inner timeout in
    ``get_status``, otherwise the exporter always cancels the BMC poll
    before it can complete.  We use the same formula as ``get_status``
    plus a 10 s safety margin.
    """
    base = settings.redfish_timeout_seconds + 20   # 80 s default — covers 70 s inner
    if manufacturer and "inspur" in manufacturer.lower():
        base = max(base, 160)                       # Inspur needs ≥ 150 s
    return base


async def _refresh_one(s: Server):
    """Poll one server and update its cache entry.

    The timeout is vendor-aware so the exporter doesn't cancel a BMC
    poll that would have succeeded given a little more time.
    """
    timeout = _vendor_timeout(s.manufacturer)
    try:
        status = await asyncio.wait_for(
            bmc_svc.get_status(s, force_refresh=True),
            timeout=timeout,
        )
        # Stash labels in the payload so the formatter doesn't need a DB connection
        status["__labels__"] = _server_labels(s)
        _cache[s.id] = _CacheEntry(payload=status, ts=time.time(), ok=True)
    except asyncio.TimeoutError:
        _log.warning(
            "refresh timed out for %s (%s) after %ds",
            s.hostname, s.mgmt_ip, timeout,
        )
        old = _cache.get(s.id)
        _cache[s.id] = _CacheEntry(
            payload=old.payload if (old and old.ok) else {"__labels__": _server_labels(s)},
            ts=time.time(),
            ok=False,
            error=f"timeout after {timeout:.0f}s",
        )
    except Exception:
        _log.warning("refresh failed for %s (%s)", s.hostname, s.mgmt_ip, exc_info=True)
        old = _cache.get(s.id)
        _cache[s.id] = _CacheEntry(
            payload=old.payload if (old and old.ok) else {"__labels__": _server_labels(s)},
            ts=time.time(),
            ok=False,
            error=f"refresh failed",
        )


async def _refresh_loop():
    """Poll all servers, spreading them evenly across the interval.

    Instead of launching all servers at once (thundering herd), each
    server is polled at a steady rate of interval/n seconds apart.
    This smooths network load and prevents the BMC network from
    saturating — the primary cause of timeouts at scale.
    """
    global _running
    _running = True
    interval = max(settings.redfish_exporter_interval_seconds, 30)

    _log.info("redfish exporter refresh loop started (interval=%ds)", interval)

    while _running:
        t0 = time.time()
        db_servers = _get_servers_with_creds()
        n = len(db_servers)
        _log.info("refresh round: %d servers with credentials", n)

        if n == 0:
            if _running:
                await asyncio.sleep(interval)
            continue

        # Spread polls evenly: sleep interval/n between each launch.
        # Individual polls run concurrently (no semaphore) because the
        # per-host lock in bmc.py already serialises same-host access.
        # The steady launch rate prevents network saturation.
        delay_per_server = max(1.0, interval / n)
        pending: set[asyncio.Task] = set()

        for s in db_servers:
            if not _running:
                break
            # Reap completed tasks to keep the set small
            done = {t for t in pending if t.done()}
            pending -= done

            pending.add(asyncio.create_task(_refresh_one(s)))
            await asyncio.sleep(delay_per_server)

        # Wait for stragglers
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        elapsed = time.time() - t0
        ok = sum(1 for e in _cache.values() if e.ok)
        _log.info("refresh round done in %.1fs: %d/%d ok", elapsed, ok, n)

        if _running:
            remaining = max(0, interval - (time.time() - t0))
            if remaining > 0:
                await asyncio.sleep(remaining)


def _spawn_refresh():
    """Spawn the background refresh task (called from the lifespan startup)."""
    global _refresh_task
    _refresh_task = asyncio.create_task(_refresh_loop())


async def stop():
    """Gracefully stop the background refresh loop."""
    global _running, _refresh_task
    _running = False
    if _refresh_task:
        _refresh_task.cancel()
        try:
            await _refresh_task
        except asyncio.CancelledError:
            pass
        _refresh_task = None
    _log.info("redfish exporter stopped")


# ── Metrics endpoint ─────────────────────────────────────────────


@router.get("/metrics/redfish", response_class=PlainTextResponse)
async def metrics_redfish(request: Request):
    """Return all cached Redfish metrics in Prometheus exposition format.

    An optional ``?token=...`` query parameter is checked against
    ``REDFISH_EXPORTER_TOKEN`` when the setting is non-empty."""
    # Optional token check
    token = settings.redfish_exporter_token
    if token:
        req_token = request.query_params.get("token", "")
        if req_token != token:
            return PlainTextResponse("unauthorized\n", status_code=401)
    return PlainTextResponse(_format_metrics())
