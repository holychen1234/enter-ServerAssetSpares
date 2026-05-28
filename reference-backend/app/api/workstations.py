import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, DataError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.serializers import workstation_to_dict
from app.auth import get_current_user, require_writer
from app.db.base import get_db
from app.db.models import AuditLog, Profile, Workstation

router = APIRouter()


def _apply_payload(ws: Workstation, body: dict):
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
        "monitors": "monitors",
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
            setattr(ws, attr, body[k])


@router.get("/workstations")
def list_workstations(
    db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    rows = db.query(Workstation).order_by(Workstation.created_at.desc()).all()
    return [workstation_to_dict(r) for r in rows]


@router.post("/workstations")
def create_workstation(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ws = Workstation(id=str(uuid.uuid4()))
    _apply_payload(ws, body)
    db.add(ws)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="workstation.create",
            target=f"ws:{ws.hostname}",
            detail=f"录入终端PC {ws.hostname}",
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
    db.refresh(ws)
    return workstation_to_dict(ws)


@router.post("/workstations/batch-delete", status_code=204)
def batch_delete_workstations(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ids: list[str] = (body or {}).get("ids") or []
    if not ids:
        raise HTTPException(400, "ids 不能为空")
    if len(ids) > 200:
        raise HTTPException(400, "单次最多删除 200 台终端")

    wss = db.query(Workstation).filter(Workstation.id.in_(ids)).all()
    hostnames = [w.hostname for w in wss]

    for w in wss:
        db.delete(w)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="workstation.batch_delete",
            target=f"ws:{len(hostnames)}台终端",
            detail=", ".join(hostnames),
            level="warn",
        )
    )
    db.commit()


@router.get("/workstations/{wid}")
def get_workstation(
    wid: str, db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    ws = db.get(Workstation, wid)
    if not ws:
        raise HTTPException(404, "workstation not found")
    return workstation_to_dict(ws)


@router.patch("/workstations/{wid}")
def update_workstation(
    wid: str,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ws = db.get(Workstation, wid)
    if not ws:
        raise HTTPException(404, "workstation not found")
    _apply_payload(ws, body)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="workstation.update",
            target=f"ws:{ws.hostname}",
            detail="更新终端PC信息",
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
    db.refresh(ws)
    return workstation_to_dict(ws)


@router.delete("/workstations/{wid}", status_code=204)
def delete_workstation(
    wid: str,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ws = db.get(Workstation, wid)
    if not ws:
        raise HTTPException(404, "workstation not found")
    hostname = ws.hostname
    db.delete(ws)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="workstation.delete",
            target=f"ws:{hostname}",
            detail="删除终端PC",
            level="warn",
        )
    )
    db.commit()
