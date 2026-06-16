import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, DataError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.serializers import item_to_dict, server_to_dict
from app.auth import get_current_user, require_writer
from app.db.base import get_db
from app.db.models import AuditLog, Part, PartItem, Profile, Server
from app.services import bmc as bmc_svc

router = APIRouter()


def _apply_payload(s: Server, body: dict):
    mapping = {
        "hostname": "hostname",
        "sn": "sn",
        "assetTag": "asset_tag",
        "manufacturer": "manufacturer",
        "model": "model",
        "cpuModel": "cpu_model",
        "cpuCount": "cpu_count",
        "memoryGB": "memory_gb",
        "diskCount": "disk_count",
        "diskSlotCount": "disk_slot_count",
        "mgmtIp": "mgmt_ip",
        "bizIp": "biz_ip",
        "bmcProtocol": "bmc_protocol",
        "bmcUser": "bmc_user",
        "status": "status",
        "owner": "owner",
        "purchaseDate": "purchase_date",
        "warrantyEnd": "warranty_end",
        "tags": "tags",
        "remark": "remark",
    }
    for k, attr in mapping.items():
        if k in body and body[k] is not None:
            setattr(s, attr, body[k])
    if "location" in body and body["location"]:
        loc = body["location"]
        s.idc = loc.get("idc", s.idc)
        s.rack = loc.get("rack", s.rack)
        s.u_position = loc.get("uPosition", s.u_position)
    # BMC password: only persist when caller explicitly sends a non-empty
    # string. Empty string / missing key = "keep existing password".
    pwd = body.get("bmcPassword")
    if isinstance(pwd, str) and pwd != "":
        s.bmc_password = pwd


@router.get("/servers")
def list_servers(
    db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    rows = db.query(Server).order_by(Server.created_at.desc()).all()
    return [server_to_dict(r) for r in rows]


@router.post("/servers")
def create_server(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    s = Server(id=str(uuid.uuid4()))
    _apply_payload(s, body)
    db.add(s)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="server.create",
            target=f"srv:{s.hostname}",
            detail=f"录入服务器 {s.hostname}",
        )
    )
    try:
        db.commit()
    except (IntegrityError, DataError, ProgrammingError) as exc:
        db.rollback()
        detail = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
        raise HTTPException(422, f"数据库错误: {detail}")
    except Exception:
        db.rollback()
        raise
    db.refresh(s)
    return server_to_dict(s)


@router.post("/servers/batch-delete", status_code=204)
def batch_delete_servers(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ids: list[str] = (body or {}).get("ids") or []
    if not ids:
        raise HTTPException(400, "ids 不能为空")
    if len(ids) > 200:
        raise HTTPException(400, "单次最多删除 200 台主机")

    servers = db.query(Server).filter(Server.id.in_(ids)).all()
    hostnames = [s.hostname for s in servers]

    for s in servers:
        db.delete(s)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="server.batch_delete",
            target=f"srv:{len(hostnames)}台主机",
            detail=", ".join(hostnames),
            level="warn",
        )
    )
    db.commit()


@router.get("/servers/{sid}")
def get_server(
    sid: str, db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")
    return server_to_dict(s)


@router.patch("/servers/{sid}")
def update_server(
    sid: str,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")
    _apply_payload(s, body)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="server.update",
            target=f"srv:{s.hostname}",
            detail="更新服务器信息",
        )
    )
    try:
        db.commit()
    except (IntegrityError, DataError, ProgrammingError) as exc:
        db.rollback()
        detail = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
        raise HTTPException(422, f"数据库错误: {detail}")
    except Exception:
        db.rollback()
        raise
    db.refresh(s)
    return server_to_dict(s)


@router.delete("/servers/{sid}", status_code=204)
def delete_server(
    sid: str,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")
    hostname = s.hostname
    db.delete(s)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="server.delete",
            target=f"srv:{hostname}",
            detail="删除服务器",
            level="warn",
        )
    )
    db.commit()


@router.get("/servers/{sid}/bmc")
async def server_bmc(
    sid: str,
    refresh: bool = False,
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")

    # On explicit refresh: poll BMC live and persist a fresh snapshot.
    if refresh:
        snap = await bmc_svc.collect_and_save(s)
        if snap:
            return {**bmc_svc.snapshot_to_status(snap, s), "lastCollectedAt": snap.collected_at.isoformat()}
        # BMC unreachable — fall back to latest persisted snapshot.
        snap = bmc_svc.get_latest_snapshot(sid)

    # Normal request: serve from persisted snapshot.
    if not refresh:
        snap = bmc_svc.get_latest_snapshot(sid)

    if snap:
        return {**bmc_svc.snapshot_to_status(snap, s), "lastCollectedAt": snap.collected_at.isoformat()}

    # No snapshot exists yet — poll live and persist so subsequent requests are instant.
    snap = await bmc_svc.collect_and_save(s)
    if snap:
        return {**bmc_svc.snapshot_to_status(snap, s), "lastCollectedAt": snap.collected_at.isoformat()}

    # Last resort: live one-off.  collect_and_save already tried the BMC
    # and failed — get_status (without force_refresh) respects the cooldown
    # and returns either a cached live payload or a simulated fallback.
    status = await bmc_svc.get_status(s)
    return {**status, "lastCollectedAt": None}


@router.post("/servers/{sid}/bmc/refresh")
async def server_bmc_refresh(
    sid: str,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    """Manually trigger a BMC poll + persist the snapshot."""
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")
    snap = await bmc_svc.collect_and_save(s)
    if not snap:
        raise HTTPException(502, "BMC 不可达，无法刷新数据")
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="bmc.refresh",
            target=f"srv:{s.hostname}",
            detail="手动刷新 BMC 实时数据",
        )
    )
    db.commit()
    return {**bmc_svc.snapshot_to_status(snap, s), "lastCollectedAt": snap.collected_at.isoformat()}


@router.get("/servers/{sid}/installed-items")
def server_installed_items(
    sid: str,
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")
    items = (
        db.query(PartItem)
        .filter(PartItem.installed_server_id == sid)
        .order_by(PartItem.created_at.desc())
        .all()
    )
    out = []
    for it in items:
        d = item_to_dict(it, s.hostname)
        # add part model info
        p = db.get(Part, it.part_id)
        d["partBrand"] = p.brand if p else ""
        d["partModel"] = p.model if p else ""
        d["partSpec"] = p.spec if p else ""
        d["partCategory"] = p.category if p else ""
        out.append(d)
    return out
