"""AI query endpoints for Feishu Aily / Dify integration.

Aily/Dify calls these tools via HTTP with an X-API-Key header.
Each endpoint is designed as a discrete "tool" with clear
input/output schemas so the AI agent can route user questions correctly."""

import json
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.serializers import part_to_dict, server_to_dict
from app.db.base import get_db
from app.db.models import Part, Server
from app.services import bmc as bmc_svc
from app.settings import settings

router = APIRouter(prefix="/ai", tags=["ai"])


# ── API key auth ──────────────────────────────────────────────

def verify_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
):
    if not settings.ai_api_key:
        raise HTTPException(501, "AI_API_KEY not configured on server")
    if not x_api_key or x_api_key != settings.ai_api_key:
        raise HTTPException(401, "invalid or missing X-API-Key")


# ── helpers ───────────────────────────────────────────────────

# 厂商中英文映射，支持用户用中文名查询
MANUFACTURER_ALIASES: dict[str, str] = {
    "戴尔": "Dell",
    "dell": "Dell",
    "惠普": "HPE",
    "hpe": "HPE",
    "h3c": "HPE",
    "联想": "Lenovo",
    "lenovo": "Lenovo",
    "浪潮": "Inspur",
    "inspur": "Inspur",
    "超微": "Supermicro",
    "supermicro": "Supermicro",
    "华为": "Huawei",
    "huawei": "Huawei",
    "超聚变": "XFusion",
    "xfusion": "XFusion",
    "其他": "Other",
    "other": "Other",
}

def _normalize_manufacturer(raw: str) -> str | None:
    """将中文或大小写不规范的厂商名转为标准英文名，无法识别返回 None。"""
    if not raw or not raw.strip():
        return None
    return MANUFACTURER_ALIASES.get(raw.strip().lower()) or MANUFACTURER_ALIASES.get(raw.strip())


def _server_brief(s) -> dict:
    """Compact server view for list results."""
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


def _part_brief(p) -> dict:
    """Compact part view for list results."""
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


# ── tools ─────────────────────────────────────────────────────

@router.get("/search-servers")
def search_servers(
    keyword: str = Query(default="", description="任意关键词，匹配主机名/SN/资产编号/IP/型号/厂商/CPU/IDC/备注"),
    status: str = Query(default="", description="状态过滤: online, offline, maintenance, retired"),
    idc: str = Query(default="", description="机房过滤，如 IDC-A"),
    hostname: str = Query(default="", description="主机名精确匹配"),
    sn: str = Query(default="", description="序列号精确匹配"),
    ip: str = Query(default="", description="IP 地址匹配（业务IP或管理IP）"),
    manufacturer: str = Query(default="", description="厂商过滤，支持中英文（戴尔/Dell, 惠普/HPE, 联想/Lenovo, 浪潮/Inspur, 超微/Supermicro, 华为/Huawei, 超聚变/XFusion）"),
    limit: int = Query(default=20, ge=1, le=100, description="返回条数上限"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """搜索主机资产。Aily use this when user asks about servers by name,
    SN, IP, model, manufacturer, location, or any keyword combination."""
    q = db.query(Server)

    # 厂商名规范化：支持中文（戴尔→Dell）和不区分大小写
    mfr_normalized: str | None = None
    if manufacturer:
        mfr_normalized = _normalize_manufacturer(manufacturer)

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
    # 如果传入 manufacturer 参数，精确过滤。同时把 keyword 中的中文厂商名也做模糊匹配
    # （keyword 的 ilike 已覆盖 manufacturer 字段，但仅当 keyword 非空时才生效；
    #  此处确保即使 keyword 为空，manufacturer 参数也能独立工作。）
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
    return {
        "count": len(rows),
        "items": [_server_brief(r) for r in rows],
    }


@router.get("/get-server-detail")
def get_server_detail(
    identifier: str = Query(..., description="主机名、SN序列号、资产编号或IP地址"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """获取单台主机完整信息。Aily use this when user asks for detailed
    info about a specific server, e.g. CPU model, memory size, disk count.
    identifier can be hostname, SN, asset tag, or IP address."""
    s = (
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
    if not s:
        return {"found": False, "message": f"未找到主机: {identifier}"}
    return {"found": True, **server_to_dict(s)}


@router.get("/search-parts")
def search_parts(
    keyword: str = Query(default="", description="任意关键词，匹配品牌/型号/规格/SN/备注"),
    category: str = Query(default="", description="类别: disk, memory, nic, optical, other"),
    brand: str = Query(default="", description="品牌过滤"),
    model: str = Query(default="", description="型号过滤"),
    spec: str = Query(default="", description="规格过滤，如 2TB SSD"),
    status: str = Query(default="", description="状态: in_stock, allocated, in_use, scrapped"),
    limit: int = Query(default=20, ge=1, le=100, description="返回条数上限"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """搜索备件库存。Aily use this when user asks about spare parts,
    disk models, memory specs, inventory levels, etc."""
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
    return {
        "count": len(rows),
        "items": [_part_brief(r) for r in rows],
    }


@router.get("/get-server-stats")
def get_server_stats(
    group_by: str = Query(default="status", description="统计维度: status, idc, manufacturer"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """统计主机资产概况。Aily use this when user asks about totals,
    counts by status, distribution by IDC, manufacturer breakdown, etc."""
    allowed = {"status": Server.status, "idc": Server.idc, "manufacturer": Server.manufacturer}
    col = allowed.get(group_by)
    if col is None:
        return {"error": f"不支持的统计维度: {group_by}，可选: status, idc, manufacturer"}

    rows = (
        db.query(col, func.count(Server.id))
        .group_by(col)
        .order_by(func.count(Server.id).desc())
        .all()
    )
    return {
        "groupBy": group_by,
        "total": sum(c for _, c in rows),
        "items": [{"key": k, "count": c} for k, c in rows],
    }


@router.get("/get-server-disks")
async def get_server_disks(
    identifier: str = Query(..., description="主机名、SN序列号、资产编号或IP地址"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """获取某台主机的硬盘列表（含型号、SN、容量）。
    数据来源于 BMC Redfish 实时采集，非离线/retired 主机回退为模拟数据。
    identifier can be hostname, SN, asset tag, or IP address."""
    s = (
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
    if not s:
        return {"found": False, "message": f"未找到主机: {identifier}"}

    status = await bmc_svc.get_status(s)
    drives = status.get("drives") or []

    return {
        "found": True,
        "hostname": s.hostname,
        "sn": s.sn,
        "diskCountDb": s.disk_count,
        "source": status.get("source", "unknown"),
        "diskCountBmc": len(drives),
        "drives": drives,
    }


@router.get("/get-server-bmc-status")
async def get_server_bmc_status(
    identifier: str = Query(..., description="主机名、SN序列号、资产编号或IP地址"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """获取主机 BMC 实时状态。包括 CPU 温度、风扇状态/转速/数量、磁盘型号/
    序列号/容量/状态、电源功率/数量/状态、整机健康状态等。
    数据来源于 BMC Redfish/IPMI 实时采集，非在线主机回退为模拟数据。"""
    s = (
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
    if not s:
        return {"found": False, "message": f"未找到主机: {identifier}"}

    status = await bmc_svc.get_status(s)

    return {
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
        # ── BMC live data ──
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
            {
                "name": f["name"],
                "rpm": f["rpm"],
                "status": f["status"],
            }
            for f in (status.get("fans") or [])
        ],
        # disks
        "diskCount": len(status.get("drives") or []),
        "disks": [
            {
                "name": d.get("name"),
                "model": d.get("model"),
                "sn": d.get("sn"),
                "capacityGB": d.get("capacityGB"),
                "mediaType": d.get("mediaType"),
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
    }


@router.get("/get-server-network")
def get_server_network(
    identifier: str = Query(..., description="主机名、SN序列号、资产编号或IP地址"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """获取主机网络/BMC信息。仅返回网络相关字段，数据量小，适合
    用户问「带外IP」「BMC地址」「管理IP是多少」等精确查询。"""
    s = (
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
    if not s:
        return {"found": False, "message": f"未找到主机: {identifier}"}
    return {
        "found": True,
        "hostname": s.hostname,
        "bizIp": s.biz_ip,
        "mgmtIp": s.mgmt_ip,
        "bmcProtocol": s.bmc_protocol,
        "bmcUser": s.bmc_user,
        "bmcPasswordSet": bool(s.bmc_password),
    }


# ── OpenAPI schema (no auth — Dify needs to fetch it for import) ─

@router.get("/openapi.json", include_in_schema=False)
def openapi_schema():
    """Serve the OpenAPI 3.0 spec for Dify tool import."""
    schema_path = os.path.join(os.path.dirname(__file__), "ai_openapi.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        return JSONResponse(content=json.load(f))
