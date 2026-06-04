import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, DataError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.serializers import terminal_asset_to_dict
from app.auth import get_current_user, require_writer
from app.db.base import get_db
from app.db.models import AuditLog, Profile, TerminalAsset

router = APIRouter()


def _apply_payload(ta: TerminalAsset, body: dict):
    mapping = {
        "hostname": "hostname",
        "sn": "sn",
        "assetTag": "asset_tag",
        "manufacturer": "manufacturer",
        "model": "model",
        "cpuModel": "cpu_model",
        "cpuCount": "cpu_count",
        "memoryGB": "memory_gb",
        "diskType": "disk_type",
        "diskCapacityGB": "disk_capacity_gb",
        "macAddress": "mac_address",
        "os": "os",
        "osVersion": "os_version",
        "bizIp": "biz_ip",
        "userName": "user_name",
        "department": "department",
        "officeBuilding": "office_building",
        "floor": "floor",
        "seat": "seat",
        "status": "status",
        "purchaseDate": "purchase_date",
        "warrantyEnd": "warranty_end",
        "tags": "tags",
        "remark": "remark",
    }
    for k, attr in mapping.items():
        if k in body and body[k] is not None:
            setattr(ta, attr, body[k])


@router.get("/terminal-assets")
def list_terminal_assets(
    db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    rows = db.query(TerminalAsset).order_by(TerminalAsset.created_at.desc()).all()
    return [terminal_asset_to_dict(r) for r in rows]


@router.post("/terminal-assets")
def create_terminal_asset(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ta = TerminalAsset(id=str(uuid.uuid4()))
    _apply_payload(ta, body)
    db.add(ta)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="terminal_asset.create",
            target=f"ta:{ta.hostname}",
            detail=f"录入终端资产 {ta.hostname}",
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
    db.refresh(ta)
    return terminal_asset_to_dict(ta)


@router.post("/terminal-assets/batch-delete", status_code=204)
def batch_delete_terminal_assets(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ids: list[str] = (body or {}).get("ids") or []
    if not ids:
        raise HTTPException(400, "ids 不能为空")
    if len(ids) > 200:
        raise HTTPException(400, "单次最多删除 200 台终端")

    tas = db.query(TerminalAsset).filter(TerminalAsset.id.in_(ids)).all()
    hostnames = [t.hostname for t in tas]

    for t in tas:
        db.delete(t)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="terminal_asset.batch_delete",
            target=f"ta:{len(hostnames)}台终端",
            detail=", ".join(hostnames),
            level="warn",
        )
    )
    db.commit()


@router.get("/terminal-assets/{tid}")
def get_terminal_asset(
    tid: str, db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    ta = db.get(TerminalAsset, tid)
    if not ta:
        raise HTTPException(404, "terminal_asset not found")
    return terminal_asset_to_dict(ta)


@router.patch("/terminal-assets/{tid}")
def update_terminal_asset(
    tid: str,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ta = db.get(TerminalAsset, tid)
    if not ta:
        raise HTTPException(404, "terminal_asset not found")
    _apply_payload(ta, body)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="terminal_asset.update",
            target=f"ta:{ta.hostname}",
            detail="更新终端资产信息",
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
    db.refresh(ta)
    return terminal_asset_to_dict(ta)


@router.delete("/terminal-assets/{tid}", status_code=204)
def delete_terminal_asset(
    tid: str,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ta = db.get(TerminalAsset, tid)
    if not ta:
        raise HTTPException(404, "terminal_asset not found")
    hostname = ta.hostname
    db.delete(ta)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="terminal_asset.delete",
            target=f"ta:{hostname}",
            detail="删除终端资产",
            level="warn",
        )
    )
    db.commit()
