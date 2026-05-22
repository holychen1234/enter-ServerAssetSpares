"""AI query endpoints for Feishu Aily integration.

Aily calls these tools via HTTP with an X-API-Key header.
Each endpoint is designed as a discrete "tool" with clear
input/output schemas so Aily can route user questions correctly."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.serializers import part_to_dict, server_to_dict
from app.db.base import get_db
from app.db.models import Part, Server
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
    limit: int = Query(default=20, ge=1, le=100, description="返回条数上限"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """搜索主机资产。Aily use this when user asks about servers by name,
    SN, IP, model, manufacturer, location, or any keyword combination."""
    q = db.query(Server)

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
    identifier: str = Query(..., description="主机名或SN序列号"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """获取单台主机完整信息。Aily use this when user asks for detailed
    info about a specific server, e.g. CPU model, memory size, disk count."""
    s = (
        db.query(Server)
        .filter((Server.hostname == identifier) | (Server.sn == identifier))
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
