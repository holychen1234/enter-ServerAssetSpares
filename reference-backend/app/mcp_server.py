"""MCP server for CMDB AI tools.

Exposes the same query tools as the /api/ai/* REST endpoints so that
Claude Code (or any MCP client) can call them directly via stdio,
without going through HTTP.

Usage:
    PYTHONPATH=. python3 -m app.mcp_server          # stdio (for Claude Code)
    PYTHONPATH=. python3 -m app.mcp_server --sse    # SSE transport (optional)
"""

import json
import logging
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func

from app.db.base import SessionLocal
from app.db.models import Part, Server, TerminalAsset
from app.api.serializers import server_to_dict, terminal_asset_to_dict
from app.services import bmc as bmc_svc

# ── stderr-only logging so stdout stays clean for MCP JSON-RPC ──
logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(levelname)-5s  %(name)s  %(message)s",
)
logger = logging.getLogger("cmdb.mcp")

# ── Helpers (same logic as ai_query.py) ─────────────────────────────

MANUFACTURER_ALIASES: dict[str, str] = {
    "戴尔": "Dell",      "dell": "Dell",
    "惠普": "HPE",       "hpe": "HPE",       "h3c": "HPE",
    "联想": "Lenovo",    "lenovo": "Lenovo",
    "浪潮": "Inspur",    "inspur": "Inspur",
    "超微": "Supermicro","supermicro": "Supermicro",
    "华为": "Huawei",    "huawei": "Huawei",
    "超聚变": "XFusion", "xfusion": "XFusion",
    "其他": "Other",     "other": "Other",
}


def _normalize_manufacturer(raw: str) -> Optional[str]:
    """Convert Chinese / case-inconsistent manufacturer names to standard English."""
    if not raw or not raw.strip():
        return None
    return MANUFACTURER_ALIASES.get(raw.strip().lower()) or MANUFACTURER_ALIASES.get(raw.strip())


def _server_brief(s: Server) -> dict:
    return {
        "hostname": s.hostname,
        "sn": s.sn,
        "assetTag": s.asset_tag,
        "manufacturer": s.manufacturer,
        "model": s.model,
        "cpuModel": s.cpu_model,
        "cpuCount": s.cpu_count,
        "memoryGB": s.memory_gb,
        "diskCount": s.disk_count,
        "status": s.status,
        "mgmtIp": s.mgmt_ip,
        "bizIp": s.biz_ip,
        "location": {"idc": s.idc, "rack": s.rack, "uPosition": s.u_position},
        "owner": s.owner or "",
    }


def _part_brief(p: Part) -> dict:
    return {
        "category": p.category,
        "brand": p.brand,
        "model": p.model,
        "spec": p.spec,
        "sn": p.sn,
        "stock": p.stock,
        "safetyStock": p.safety_stock,
        "unit": p.unit,
        "location": p.location,
        "status": p.status,
    }


def _terminal_asset_brief(ta: TerminalAsset) -> dict:
    return {
        "hostname": ta.hostname,
        "sn": ta.sn,
        "assetTag": ta.asset_tag,
        "manufacturer": ta.manufacturer,
        "model": ta.model,
        "os": ta.os,
        "bizIp": ta.biz_ip or "",
        "userName": ta.user_name or "",
        "status": ta.status,
    }


def _server_match_query(identifier: str, db):
    """Return the first Server matching hostname / SN / asset_tag / mgmt_ip / biz_ip."""
    return (
        db.query(Server)
        .filter(
            (Server.hostname == identifier)
            | (Server.sn == identifier)
            | (Server.asset_tag == identifier)
            | (Server.mgmt_ip == identifier)
            | (Server.biz_ip == identifier)
        )
        .first()
    )


# ── MCP Server ──────────────────────────────────────────────────────

mcp = FastMCP(
    "cmdb-ai-tools",
    instructions=(
        "CMDB 资产查询工具集。支持搜索主机资产、备件库存、终端资产，"
        "以及通过 BMC Redfish 获取服务器硬件实时状态（CPU温度、风扇、"
        "电源、内存DIMM、磁盘、告警等）。"
    ),
)


# ── Tool 1: search-servers ──────────────────────────────────────────

@mcp.tool()
def search_servers(
    keyword: str = "",
    status: str = "",
    idc: str = "",
    hostname: str = "",
    sn: str = "",
    ip: str = "",
    manufacturer: str = "",
    limit: int = 20,
) -> str:
    """搜索主机资产。支持任意关键词匹配主机名/SN/资产编号/IP/型号/厂商/CPU/IDC/备注，
    以及按状态、机房、厂商（中英文均可）过滤。"""
    db = SessionLocal()
    try:
        q = db.query(Server)

        mfr_normalized = _normalize_manufacturer(manufacturer) if manufacturer else None

        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(
                Server.hostname.ilike(kw)
                | Server.sn.ilike(kw)
                | Server.asset_tag.ilike(kw)
                | Server.mgmt_ip.ilike(kw)
                | Server.biz_ip.ilike(kw)
                | Server.model.ilike(kw)
                | Server.manufacturer.ilike(kw)
                | Server.cpu_model.ilike(kw)
                | Server.idc.ilike(kw)
                | Server.remark.ilike(kw)
            )
        if mfr_normalized:
            q = q.filter(Server.manufacturer == mfr_normalized)
        if status:
            q = q.filter(Server.status == status)
        if idc:
            q = q.filter(Server.idc == idc)
        if hostname:
            q = q.filter(Server.hostname == hostname)
        if sn:
            q = q.filter(Server.sn == sn)
        if ip:
            q = q.filter((Server.mgmt_ip == ip) | (Server.biz_ip == ip))

        rows = q.order_by(Server.hostname).limit(limit).all()
        return json.dumps(
            {"count": len(rows), "items": [_server_brief(r) for r in rows]},
            ensure_ascii=False,
        )
    finally:
        db.close()


# ── Tool 2: get-server-detail ───────────────────────────────────────

@mcp.tool()
def get_server_detail(identifier: str) -> str:
    """获取单台主机完整信息。identifier 可以是主机名、SN序列号、资产编号或IP地址。
    返回该主机的全部字段：配置、位置、网络、BMC信息等。"""
    db = SessionLocal()
    try:
        s = _server_match_query(identifier, db)
        if not s:
            return json.dumps(
                {"found": False, "message": f"未找到主机: {identifier}"},
                ensure_ascii=False,
            )
        return json.dumps({"found": True, **server_to_dict(s)}, ensure_ascii=False)
    finally:
        db.close()


# ── Tool 3: search-parts ────────────────────────────────────────────

@mcp.tool()
def search_parts(
    keyword: str = "",
    category: str = "",
    brand: str = "",
    model: str = "",
    spec: str = "",
    status: str = "",
    limit: int = 20,
) -> str:
    """搜索备件库存。支持按关键词（品牌/型号/规格/SN/备注）、类别、品牌、规格、状态过滤。"""
    db = SessionLocal()
    try:
        q = db.query(Part)

        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(
                Part.brand.ilike(kw)
                | Part.model.ilike(kw)
                | Part.spec.ilike(kw)
                | Part.sn.ilike(kw)
                | Part.remark.ilike(kw)
            )
        if category:
            q = q.filter(Part.category == category)
        if brand:
            q = q.filter(Part.brand == brand)
        if model:
            q = q.filter(Part.model == model)
        if spec:
            q = q.filter(Part.spec.ilike(f"%{spec}%"))
        if status:
            q = q.filter(Part.status == status)

        rows = q.order_by(Part.category, Part.brand, Part.model).limit(limit).all()
        return json.dumps(
            {"count": len(rows), "items": [_part_brief(r) for r in rows]},
            ensure_ascii=False,
        )
    finally:
        db.close()


# ── Tool 4: get-server-stats ────────────────────────────────────────

@mcp.tool()
def get_server_stats(group_by: str = "status") -> str:
    """统计主机资产概况。支持按 status（状态）、idc（机房）、manufacturer（厂商）分组统计。"""
    db = SessionLocal()
    try:
        allowed = {
            "status": Server.status,
            "idc": Server.idc,
            "manufacturer": Server.manufacturer,
        }
        col = allowed.get(group_by)
        if col is None:
            return json.dumps(
                {"error": f"不支持的统计维度: {group_by}，可选: status, idc, manufacturer"},
                ensure_ascii=False,
            )

        rows = (
            db.query(col, func.count(Server.id))
            .group_by(col)
            .order_by(func.count(Server.id).desc())
            .all()
        )
        return json.dumps(
            {
                "groupBy": group_by,
                "total": sum(c for _, c in rows),
                "items": [{"key": k, "count": c} for k, c in rows],
            },
            ensure_ascii=False,
        )
    finally:
        db.close()


# ── Tool 5: get-server-disks ────────────────────────────────────────

@mcp.tool()
async def get_server_disks(identifier: str) -> str:
    """获取主机硬盘列表（含型号、SN、容量）。数据来源于 BMC Redfish 实时采集，
    非在线/retired 主机回退为模拟数据。identifier 可以是主机名/SN/资产编号/IP。"""
    db = SessionLocal()
    try:
        s = _server_match_query(identifier, db)
        if not s:
            return json.dumps(
                {"found": False, "message": f"未找到主机: {identifier}"},
                ensure_ascii=False,
            )

        snap = bmc_svc.get_latest_snapshot(s.id)
        if snap:
            status = bmc_svc.snapshot_to_status(snap, s)
        else:
            snap = await bmc_svc.collect_and_save(s)
            if snap:
                status = bmc_svc.snapshot_to_status(snap, s)
            else:
                status = {"drives": [], "source": "unreachable"}
        drives = status.get("drives") or []

        return json.dumps(
            {
                "found": True,
                "hostname": s.hostname,
                "sn": s.sn,
                "diskCountDb": s.disk_count,
                "source": status.get("source", "unknown"),
                "diskCountBmc": len(drives),
                "drives": drives,
            },
            ensure_ascii=False,
        )
    finally:
        db.close()


# ── Tool 6: get-server-bmc-status ───────────────────────────────────

@mcp.tool()
async def get_server_bmc_status(identifier: str) -> str:
    """获取主机 BMC 实时硬件状态。包括 CPU 温度、风扇转速/数量、磁盘详情、
    内存 DIMM 详情（槽位/型号/SN/容量/类型/状态）、电源功率/数量、整机健康、
    告警等。优先读取每日快照，无快照时自动实时采集并存库。"""
    db = SessionLocal()
    try:
        s = _server_match_query(identifier, db)
        if not s:
            return json.dumps(
                {"found": False, "message": f"未找到主机: {identifier}"},
                ensure_ascii=False,
            )

        snap = bmc_svc.get_latest_snapshot(s.id)
        if not snap:
            snap = await bmc_svc.collect_and_save(s)
        if snap:
            status = bmc_svc.snapshot_to_status(snap, s)
        else:
            status = {
                "source": "unreachable",
                "drives": [],
                "memoryModules": [],
                "fans": [],
                "psus": [],
                "recentLogs": [],
                "alerts": [],
                "history": [],
                "updatedAt": "",
            }

        return json.dumps(
            {
                "found": True,
                "hostname": s.hostname,
                "sn": s.sn,
                "assetTag": s.asset_tag,
                "manufacturer": s.manufacturer,
                "model": s.model,
                "status": s.status,
                "mgmtIp": s.mgmt_ip,
                "bizIp": s.biz_ip,
                "bmcProtocol": s.bmc_protocol,
                # BMC live data
                "source": status.get("source", "unknown"),
                "collectedAt": status.get("collectedAt"),
                "power": status.get("power"),
                "health": status.get("health"),
                "bootProgress": status.get("bootProgress"),
                "cpuTempC": status.get("cpuTempC"),
                "inletTempC": status.get("inletTempC"),
                # fans
                "fanCount": len(status.get("fans") or []),
                "fans": [
                    {"name": f["name"], "rpm": f["rpm"], "status": f["status"]}
                    for f in (status.get("fans") or [])
                ],
                # memory
                "memoryTotalGiB": (
                    status.get("memorySummary", {}).get("totalGiB")
                    if status.get("memorySummary")
                    else None
                ),
                "memoryModuleCount": len(status.get("memoryModules") or []),
                "memorySlots": status.get("memorySlots")
                or {
                    "total": len(status.get("memoryModules") or []),
                    "populated": len(status.get("memoryModules") or []),
                },
                "memoryModules": [
                    {
                        "slot": m["slot"],
                        "model": m["model"],
                        "sn": m.get("sn"),
                        "capacityMiB": m["capacityMiB"],
                        "memoryType": m["memoryType"],
                        "status": m["status"],
                    }
                    for m in (status.get("memoryModules") or [])
                ],
                # disks
                "diskCount": len(status.get("drives") or []),
                "diskSlots": status.get("diskSlots")
                or {
                    "total": len(status.get("drives") or []),
                    "populated": len(status.get("drives") or []),
                },
                "disks": [
                    {
                        "name": d.get("name"),
                        "model": d.get("model"),
                        "sn": d.get("sn"),
                        "capacityGB": d.get("capacityGB"),
                        "mediaType": d.get("mediaType"),
                        "formFactor": d.get("formFactor", "unknown"),
                        "status": d.get("status"),
                    }
                    for d in (status.get("drives") or [])
                ],
                # power supplies
                "psuCount": len(status.get("psus") or []),
                "psus": [
                    {
                        "name": p["name"],
                        "watts": p["watts"],
                        "capacityW": p["capacityW"],
                        "status": p["status"],
                    }
                    for p in (status.get("psus") or [])
                ],
                # alerts
                "alertCount": len(status.get("alerts") or []),
                "alerts": status.get("alerts") or [],
            },
            ensure_ascii=False,
        )
    finally:
        db.close()


# ── Tool 7: search-terminal-assets ──────────────────────────────────

@mcp.tool()
def search_terminal_assets(
    keyword: str = "",
    manufacturer: str = "",
    status: str = "",
    os: str = "",
    limit: int = 20,
) -> str:
    """搜索终端资产（办公电脑、笔记本等）。支持关键词匹配计算机名/SN/资产编号/IP/型号/使用人，
    以及按厂商、状态、操作系统过滤。"""
    db = SessionLocal()
    try:
        q = db.query(TerminalAsset)

        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(
                TerminalAsset.hostname.ilike(kw)
                | TerminalAsset.sn.ilike(kw)
                | TerminalAsset.asset_tag.ilike(kw)
                | TerminalAsset.biz_ip.ilike(kw)
                | TerminalAsset.model.ilike(kw)
                | TerminalAsset.user_name.ilike(kw)
            )
        if manufacturer:
            mfr_norm = _normalize_manufacturer(manufacturer)
            if mfr_norm:
                q = q.filter(TerminalAsset.manufacturer == mfr_norm)
            else:
                q = q.filter(TerminalAsset.manufacturer == manufacturer)
        if status:
            q = q.filter(TerminalAsset.status == status)
        if os:
            q = q.filter(TerminalAsset.os == os)

        rows = q.order_by(TerminalAsset.hostname).limit(limit).all()
        return json.dumps(
            {"count": len(rows), "items": [_terminal_asset_brief(r) for r in rows]},
            ensure_ascii=False,
        )
    finally:
        db.close()


# ── Tool 8: get-terminal-asset-detail ───────────────────────────────

@mcp.tool()
def get_terminal_asset_detail(identifier: str) -> str:
    """获取单台终端资产完整信息。identifier 可以是计算机名、SN序列号、资产编号或IP地址。"""
    db = SessionLocal()
    try:
        ta = (
            db.query(TerminalAsset)
            .filter(
                (TerminalAsset.hostname == identifier)
                | (TerminalAsset.sn == identifier)
                | (TerminalAsset.asset_tag == identifier)
                | (TerminalAsset.biz_ip == identifier)
            )
            .first()
        )
        if not ta:
            return json.dumps(
                {"found": False, "message": f"未找到终端资产: {identifier}"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"found": True, **terminal_asset_to_dict(ta)}, ensure_ascii=False
        )
    finally:
        db.close()


# ── Entry Point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--sse" in sys.argv:
        # Parse optional --port / --host from argv, e.g. --port 8100 --host 0.0.0.0
        port = 8100
        host = "0.0.0.0"
        args = sys.argv[1:]
        for i, arg in enumerate(args):
            if arg == "--port" and i + 1 < len(args):
                port = int(args[i + 1])
            if arg == "--host" and i + 1 < len(args):
                host = args[i + 1]
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
