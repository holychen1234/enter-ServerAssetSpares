import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.serializers import movement_to_dict, part_to_dict
from app.auth import get_current_user, require_writer
from app.db.base import get_db
from app.db.models import AuditLog, Part, Profile, Server, StockMovement
from app.services import inventory as inv_svc

router = APIRouter()


@router.get("/parts")
def list_parts(
    db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    return [part_to_dict(p) for p in db.query(Part).order_by(Part.created_at.desc()).all()]


@router.get("/parts/{pid}")
def get_part(pid: str, db: Session = Depends(get_db), _: Profile = Depends(get_current_user)):
    p = db.get(Part, pid)
    if not p:
        raise HTTPException(404, "part not found")
    return part_to_dict(p)


@router.post("/parts")
def create_part(
    body: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    p = Part(
        id=str(uuid.uuid4()),
        category=body["category"],
        brand=body["brand"],
        model=body["model"],
        spec=body["spec"],
        sn=body.get("sn"),
        stock=body.get("stock", 0),
        safety_stock=body.get("safetyStock", 0),
        unit=body.get("unit", "块"),
        location=body["location"],
        status=body.get("status", "in_stock"),
        remark=body.get("remark"),
    )
    db.add(p)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="part.create",
            target=f"part:{p.brand} {p.model}",
            detail="新建备件",
        )
    )
    db.commit()
    db.refresh(p)
    return part_to_dict(p)


@router.patch("/parts/{pid}")
def update_part(
    pid: str,
    body: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    p = db.get(Part, pid)
    if not p:
        raise HTTPException(404, "part not found")
    for k, attr in (
        ("category", "category"),
        ("brand", "brand"),
        ("model", "model"),
        ("spec", "spec"),
        ("sn", "sn"),
        ("stock", "stock"),
        ("safetyStock", "safety_stock"),
        ("unit", "unit"),
        ("location", "location"),
        ("status", "status"),
        ("remark", "remark"),
    ):
        if k in body and body[k] is not None:
            setattr(p, attr, body[k])
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="part.update",
            target=f"part:{p.brand} {p.model}",
            detail="更新备件",
        )
    )
    db.commit()
    db.refresh(p)
    return part_to_dict(p)


@router.delete("/parts/{pid}", status_code=204)
def delete_part(
    pid: str,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    p = db.get(Part, pid)
    if not p:
        raise HTTPException(404, "part not found")
    label = f"part:{p.brand} {p.model}"
    db.delete(p)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="part.delete",
            target=label,
            detail="删除备件",
            level="warn",
        )
    )
    db.commit()


# ---------- movements ----------


@router.get("/stock-movements")
def list_movements(
    db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    rows = (
        db.query(StockMovement)
        .order_by(StockMovement.created_at.desc())
        .all()
    )
    out = []
    parts_cache: dict[str, Part] = {}
    servers_cache: dict[str, Server] = {}
    for m in rows:
        if m.part_id not in parts_cache:
            parts_cache[m.part_id] = db.get(Part, m.part_id)
        if m.related_server_id and m.related_server_id not in servers_cache:
            servers_cache[m.related_server_id] = db.get(Server, m.related_server_id)
        out.append(
            movement_to_dict(
                m,
                parts_cache.get(m.part_id),
                servers_cache.get(m.related_server_id) if m.related_server_id else None,
            )
        )
    return out


@router.post("/stock-movements")
def create_movement(
    body: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    class _P:
        part_id = body["partId"]
        type = body["type"]
        quantity = body["quantity"]
        operator = body.get("operator", user.username)
        related_server_id = body.get("relatedServerId")
        reason = body["reason"]

    try:
        mv = inv_svc.apply_movement(db, _P, user.username)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(mv)
    part = db.get(Part, mv.part_id)
    server = db.get(Server, mv.related_server_id) if mv.related_server_id else None
    return movement_to_dict(mv, part, server)
