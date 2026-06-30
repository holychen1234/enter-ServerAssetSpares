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
        "你是 CMDB 资产管理助手，可以查询服务器资产、终端资产（办公电脑）、"
        "备件库存，以及通过 BMC Redfish 实时采集服务器硬件状态。\n\n"
        "## 工具选择规则\n"
        "- 查配置/基本信息/网络/BMC IP → get_server_detail\n"
        "- 查硬件实时状态（温度/风扇/电源/健康/告警） → get_server_bmc_status\n"
        "- 查硬盘列表/型号/容量 → get_server_disks\n"
        "- 查内存/磁盘槽位占用（还剩几个空位） → get_server_slots\n"
        "- 模糊搜索/列表 → search_servers / search_parts / search_terminal_assets\n"
        "- 统计/分布/总数 → get_server_stats\n\n"
        "## 回答原则\n"
        "- 只回答用户问了的信息，没问的不要主动列\n"
        "- 列表查询先给总数再列前10条，查不到说"未找到相关记录"\n"
        "- BMC 数据 source=simulated 时注明"当前为模拟数据，BMC 不可达"\n"
        "- 厂商名支持中英文：戴尔=Dell, 惠普=HPE, 联想=Lenovo, 浪潮=Inspur, 超微=Supermicro, 华为=Huawei"
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
    """搜索主机资产。

    用关键词模糊匹配主机名/SN/资产编号/IP/型号/厂商/CPU型号/IDC/备注。
    支持按状态(online/offline/maintenance/retired)、机房(IDC-A等)、
    厂商(戴尔/Dell, 惠普/HPE, 联想/Lenovo, 浪潮/Inspur等中英文均可)过滤。

    适用场景：
    - "Dell 服务器有哪些" → search_servers(manufacturer="Dell")
    - "IDC-A 有哪些在线机器" → search_servers(idc="IDC-A", status="online")
    - "DB-SH 开头的机器" → search_servers(keyword="DB-SH")
    - "10.0.1.x 网段的机器" → search_servers(keyword="10.0.1")
    """
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
    """获取单台主机完整信息。

    identifier 可以是主机名、SN序列号、资产编号、管理IP或业务IP。
    返回该主机的全部字段：配置(CPU/内存/磁盘)、位置(IDC/机柜/U位)、
    网络(业务IP/管理IP/BMC协议)、归属、备注等。

    适用场景：
    - "DB-SH-01 的配置" → get_server_detail("DB-SH-01")
    - "10.0.1.5 是哪台机器" → get_server_detail("10.0.1.5")
    - "资产编号 AST-001 的机器" → get_server_detail("AST-001")
    - "10.0.1.5 的 BMC IP 是多少" → get_server_detail("10.0.1.5")
    - "SN:ABC123 的内存多大" → get_server_detail("ABC123")
    """
    db = SessionLocal()
    try:
        s = _server_match_query(identifier, db)
        if not s:
            return json.dumps(
                {"found": False, "message": f"未找到主机: {identifier}"},
                ensure_ascii=False,
            )
        result = {"found": True, **server_to_dict(s)}
        # Enrich with slot utilization from BMC snapshot (lightweight — no live poll)
        snap = bmc_svc.get_latest_snapshot(s.id)
        if snap:
            status = bmc_svc.snapshot_to_status(snap, s)
            result["memorySlots"] = status.get("memorySlots")
            result["diskSlots"] = status.get("diskSlots")
        else:
            if s.disk_slot_count > 0:
                result["diskSlots"] = {"total": s.disk_slot_count, "used": s.disk_count}
            else:
                result["diskSlots"] = None
            result["memorySlots"] = None
        return json.dumps(result, ensure_ascii=False)
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
    """搜索备件库存。

    按关键词（品牌/型号/规格/SN/备注）、类别(disk/memory/nic/optical/other)、
    品牌、型号、规格(如 2TB SSD)、状态(in_stock/allocated/in_use/scrapped)过滤。

    适用场景：
    - "2TB SSD 还有多少" → search_parts(spec="2TB SSD")
    - "内存条库存" → search_parts(category="memory")
    - "希捷的硬盘" → search_parts(brand="Seagate")
    """
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
    """统计主机资产概况。

    按 status(状态)、idc(机房)、或 manufacturer(厂商)分组统计数量。

    适用场景：
    - "一共有多少台机器" → get_server_stats(group_by="status")
    - "各机房分别有多少台" → get_server_stats(group_by="idc")
    - "各厂商分布" → get_server_stats(group_by="manufacturer")
    """
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
    """获取主机硬盘列表（含型号、SN、容量、介质类型）。

    数据来源于 BMC Redfish 实时采集，非在线/retired 主机回退为模拟数据。
    identifier 可以是主机名、SN、资产编号或IP地址。

    适用场景：
    - "DB-SH-01 有几块硬盘" → get_server_disks("DB-SH-01")
    - "192.168.1.100 的硬盘型号是什么" → get_server_disks("192.168.1.100")
    - "这台机器装了哪些盘" → get_server_disks("hostname")

    注意：用户问"还剩几个盘位/槽位"用 get_server_slots，问硬盘型号/容量用本工具。
    """
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


# ── Tool 6: get-server-slots ─────────────────────────────────────────

@mcp.tool()
async def get_server_slots(identifier: str) -> str:
    """获取主机内存与磁盘槽位信息（总槽位数和已使用槽位数）。

    数据优先来自 BMC 每日快照（毫秒级响应），无快照时尝试实时采集，
    均不可用时回退到数据库字段（仅磁盘槽位有 DB 手动配置兜底）。

    适用场景：
    - "DB-SH-01 插了几根内存" → get_server_slots("DB-SH-01")
    - "DB-SH-01 内存槽位还有空余吗" → get_server_slots("DB-SH-01")
    - "192.168.1.100 的硬盘位还剩几个" → get_server_slots("192.168.1.100")
    - "这台机器最多能插多少块硬盘" → get_server_slots("hostname")
    - "DB-SH-01 磁盘槽位满了没" → get_server_slots("DB-SH-01")

    注意：用户问内存多大/容量用 get_server_detail，问槽位占用用本工具。
    用户问硬盘型号/容量用 get_server_disks，问槽位占用用本工具。
    """
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
            memory_slots = status.get("memorySlots")
            disk_slots = status.get("diskSlots")
            source = "snapshot"
        else:
            snap = await bmc_svc.collect_and_save(s)
            if snap:
                status = bmc_svc.snapshot_to_status(snap, s)
                memory_slots = status.get("memorySlots")
                disk_slots = status.get("diskSlots")
                source = "live"
            else:
                source = "db_fallback"
                if s.disk_slot_count > 0:
                    disk_slots = {"total": s.disk_slot_count, "used": s.disk_count}
                else:
                    disk_slots = None
                memory_slots = None

        return json.dumps(
            {
                "found": True,
                "hostname": s.hostname,
                "sn": s.sn,
                "assetTag": s.asset_tag,
                "manufacturer": s.manufacturer,
                "model": s.model,
                "source": source,
                "memorySlots": memory_slots,
                "diskSlots": disk_slots,
            },
            ensure_ascii=False,
        )
    finally:
        db.close()


# ── Tool 7: get-server-bmc-status ───────────────────────────────────

@mcp.tool()
async def get_server_bmc_status(identifier: str) -> str:
    """获取主机 BMC 实时硬件状态。

    包括 CPU 温度、风扇转速/数量、磁盘详情（型号/SN/容量/介质类型）、
    内存 DIMM 详情（槽位/型号/SN/容量/类型/状态）、电源功率/数量/状态、
    整机健康、告警、启动进度等。优先读取每日快照（毫秒级响应），
    无快照时自动实时采集并存库。

    适用场景：
    - "DB-SH-01 的 CPU 温度多少" → get_server_bmc_status("DB-SH-01")
    - "这台机器有几个风扇" → get_server_bmc_status("hostname")
    - "10.0.1.5 电源功率使用情况" → get_server_bmc_status("10.0.1.5")
    - "DB-SH-01 的健康状态" → get_server_bmc_status("DB-SH-01")
    - "DB-SH-01 有什么告警" → get_server_bmc_status("DB-SH-01")
    - "DB-SH-01 开机了没" → get_server_bmc_status("DB-SH-01")

    注意：用户问具体某类信息时只回答该类，不要列出全部。
    """
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


# ── Tool 8: search-terminal-assets ──────────────────────────────────

@mcp.tool()
def search_terminal_assets(
    keyword: str = "",
    manufacturer: str = "",
    status: str = "",
    os: str = "",
    limit: int = 20,
) -> str:
    """搜索终端资产（办公电脑、笔记本等）。

    按关键词模糊匹配计算机名/SN/资产编号/IP/型号/使用人/部门。
    支持按厂商(Dell/HP/Lenovo/Apple/Huawei/ASUS等)、状态(online/offline/maintenance/retired)、
    操作系统过滤。

    适用场景：
    - "市场部有哪些电脑" → search_terminal_assets(keyword="市场部")
    - "Windows 11 的终端" → search_terminal_assets(os="Windows 11")
    - "张三的电脑" → search_terminal_assets(keyword="张三")
    - "公司有几台 Mac" → search_terminal_assets(manufacturer="Apple")
    """
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


# ── Tool 9: get-terminal-asset-detail ───────────────────────────────

@mcp.tool()
def get_terminal_asset_detail(identifier: str) -> str:
    """获取单台终端资产完整信息。

    identifier 可以是计算机名、SN序列号、资产编号或IP地址。
    返回配置(厂商/型号/CPU/内存/硬盘/OS)、归属(使用人/部门/位置)、
    网络(IP/MAC)、生命周期(采购日期/保修截止/状态)等全部字段。

    适用场景：
    - "TS-001 的配置" → get_terminal_asset_detail("TS-001")
    - "张三的电脑配置" → get_terminal_asset_detail("张三的计算机名")
    - "资产编号 AST-PC-001 的电脑" → get_terminal_asset_detail("AST-PC-001")
    """
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
