"""BMC live-status collector.

Two protocols are supported:

- redfish: HTTPS REST polling against the server's BMC. We hit Chassis/1
  Thermal & Power and Systems/1 for the high-level summary.
- ipmi:    Calls out to `ipmitool` (must be installed on the API container —
  see Dockerfile). This requires that the API host has L3 reachability to
  the BMC management network.

Both code paths fall back to a deterministic simulation when the underlying
endpoint is unreachable so the UI keeps rendering during demos / offline tests.
"""
import asyncio
import random
import subprocess
import uuid
from datetime import datetime, timezone

import httpx

from app.db.models import Server
from app.settings import settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _simulate(server: Server) -> dict:
    is_offline = server.status in ("offline", "retired")
    is_maint = server.status == "maintenance"
    seed = len(server.id) + ord(server.id[-1])
    cpu = 0 if is_offline else round(random.uniform(48, 78), 1)
    inlet = 0 if is_offline else round(random.uniform(20, 28), 1)
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
    alerts = []
    if is_offline:
        alerts.append(
            {
                "id": uuid.uuid4().hex[:8],
                "time": _now_iso(),
                "level": "Critical",
                "message": "BMC unreachable / 设备离线",
            }
        )
    elif cpu > 75:
        alerts.append(
            {
                "id": uuid.uuid4().hex[:8],
                "time": _now_iso(),
                "level": "Warning",
                "message": f"CPU 温度 {cpu}°C 超过阈值 75°C",
            }
        )
    base_cpu = 55 + (seed % 12)
    base_inlet = 22 + (seed % 4)
    base_power = 320 + (seed % 60)
    history = []
    for i in range(11, -1, -1):
        history.append(
            {
                "t": f"{i*5}m",
                "cpu": max(20, min(95, base_cpu + random.uniform(-6, 8))),
                "inlet": max(15, min(35, base_inlet + random.uniform(-2, 2))),
                "power": max(150, base_power + random.uniform(-40, 50)),
            }
        )

    return {
        "serverId": server.id,
        "power": "Off" if is_offline else "On",
        "health": health,
        "bootProgress": "PowerOff" if is_offline else "OSBootCompleted",
        "cpuTempC": cpu,
        "inletTempC": inlet,
        "fans": fans,
        "psus": psus,
        "alerts": alerts,
        "history": history,
        "updatedAt": _now_iso(),
    }


async def _redfish(server: Server) -> dict | None:
    base = (
        settings.redfish_default_base
        if not server.mgmt_ip
        else f"http://{server.mgmt_ip}"  # adjust to https in production
    )
    auth = (
        (server.bmc_user, server.bmc_password)
        if server.bmc_user and server.bmc_password
        else None
    )
    timeout = settings.redfish_timeout_seconds
    try:
        async with httpx.AsyncClient(
            timeout=timeout, verify=False, auth=auth
        ) as client:
            t, p, s = await asyncio.gather(
                client.get(f"{base}/redfish/v1/Chassis/1/Thermal"),
                client.get(f"{base}/redfish/v1/Chassis/1/Power"),
                client.get(f"{base}/redfish/v1/Systems/1"),
            )
        if t.status_code != 200 or p.status_code != 200 or s.status_code != 200:
            return None
        thermal = t.json()
        power = p.json()
        system = s.json()
        cpu = next(
            (x.get("ReadingCelsius", 0) for x in thermal.get("Temperatures", []) if "CPU" in (x.get("Name") or "")),
            0,
        )
        inlet = next(
            (x.get("ReadingCelsius", 0) for x in thermal.get("Temperatures", []) if "Inlet" in (x.get("Name") or "")),
            0,
        )
        fans = [
            {
                "name": f.get("Name", f"Fan{i+1}"),
                "rpm": int(f.get("Reading") or 0),
                "status": (f.get("Status") or {}).get("Health") or "OK",
            }
            for i, f in enumerate(thermal.get("Fans", []))
        ]
        psus = [
            {
                "name": ps.get("Name", f"PSU{i+1}"),
                "watts": int(ps.get("PowerOutputWatts") or 0),
                "capacityW": int(ps.get("PowerCapacityWatts") or 800),
                "status": (ps.get("Status") or {}).get("Health") or "OK",
            }
            for i, ps in enumerate(power.get("PowerSupplies", []))
        ]
        return {
            "power": "On" if system.get("PowerState") == "On" else "Off",
            "health": (system.get("Status") or {}).get("Health") or "OK",
            "bootProgress": (system.get("BootProgress") or {}).get("LastState") or "Unknown",
            "cpuTempC": cpu,
            "inletTempC": inlet,
            "fans": fans or None,
            "psus": psus or None,
        }
    except Exception:
        return None


def _ipmi(server: Server) -> dict | None:
    """Best-effort ipmitool wrapper. Requires ipmitool installed in the image."""
    if not server.mgmt_ip or not server.bmc_user or not server.bmc_password:
        return None
    try:
        result = subprocess.run(
            [
                "ipmitool",
                "-I", "lanplus",
                "-H", server.mgmt_ip,
                "-U", server.bmc_user,
                "-P", server.bmc_password,
                "sdr", "type", "Temperature",
            ],
            capture_output=True,
            text=True,
            timeout=settings.redfish_timeout_seconds,
        )
        if result.returncode != 0:
            return None
        # very light-weight parse: pull first numeric "<num> degrees C"
        import re
        match = re.search(r"(\d+(?:\.\d+)?)\s*degrees\s*C", result.stdout)
        cpu = float(match.group(1)) if match else 0
        return {"cpuTempC": cpu, "health": "OK"}
    except Exception:
        return None


async def get_status(server: Server) -> dict:
    sim = _simulate(server)
    live = None
    if server.status not in ("offline", "retired"):
        if server.bmc_protocol == "redfish":
            live = await _redfish(server)
        elif server.bmc_protocol == "ipmi":
            live = _ipmi(server)
    if live:
        sim.update({k: v for k, v in live.items() if v is not None})
    else:
        if server.status not in ("offline", "retired"):
            sim["alerts"].append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "time": _now_iso(),
                    "level": "Warning",
                    "message": (
                        f"{server.bmc_protocol.upper()} 端点未响应，当前展示为模拟值。"
                    ),
                }
            )
    sim["serverId"] = server.id
    sim["updatedAt"] = _now_iso()
    return sim
