import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.serializers import (
    item_to_dict,
    movement_to_dict,
    part_to_dict,
)
from app.auth import get_current_user, require_writer
from app.db.base import get_db
from app.db.models import AuditLog, Part, PartItem, Profile, Server, StockMovement
from app.services import inventory as inv_svc

router = APIRouter()


def _item_count(db: Session, part_id: str) -> int:
    return (
        db.query(PartItem)
        .filter(PartItem.part_id == part_id)
        .count()
    )


# ── Part CRUD ────────────────────────────────────────────────────


@router.get("/parts")
def list_parts(
    db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    parts = db.query(Part).order_by(Part.created_at.desc()).all()
    if not parts:
        return []
    part_ids = [p.id for p in parts]
    from sqlalchemy import func
    # Batch-load item counts
    counts = dict(
        db.query(PartItem.part_id, func.count(PartItem.id))
        .filter(PartItem.part_id.in_(part_ids))
        .group_by(PartItem.part_id)
        .all()
    )
    # Batch-load status breakdown
    status_rows = (
        db.query(PartItem.part_id, PartItem.status, func.count(PartItem.id))
        .filter(PartItem.part_id.in_(part_ids))
        .group_by(PartItem.part_id, PartItem.status)
        .all()
    )
    status_by_part: dict[str, dict] = {}
    for pid, status, cnt in status_rows:
        status_by_part.setdefault(pid, {})[status] = cnt
    return [
        part_to_dict(p, item_count=counts.get(p.id, 0), status_counts=status_by_part.get(p.id, {}))
        for p in parts
    ]


@router.get("/parts/{pid}")
def get_part(
    pid: str,
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    p = db.get(Part, pid)
    if not p:
        raise HTTPException(404, "part not found")
    return part_to_dict(p, item_count=_item_count(db, p.id))


@router.post("/parts")
def create_part(
    body: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    items_data: list[dict] = body.get("items") or []
    p = Part(
        id=str(uuid.uuid4()),
        category=body["category"],
        brand=body["brand"],
        model=body["model"],
        spec=body["spec"],
        sn=body.get("sn"),
        stock=0,  # will be set after creating items
        safety_stock=body.get("safetyStock", 0),
        unit=body.get("unit", "块"),
        location=body["location"],
        status=body.get("status", "in_stock"),
        remark=body.get("remark"),
    )
    db.add(p)
    db.flush()  # get p.id for FK

    for item_data in items_data:
        it = PartItem(
            id=str(uuid.uuid4()),
            part_id=p.id,
            sn=item_data.get("sn"),
            location=item_data.get("location") or p.location,
            status="in_stock",
            remark=item_data.get("remark"),
        )
        db.add(it)
    p.stock = len(items_data)

    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="part.create",
            target=f"part:{p.brand} {p.model}",
            detail=f"新建备件 ({p.stock} 件)",
        )
    )
    db.commit()
    db.refresh(p)
    return part_to_dict(p, item_count=p.stock)


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
    # stock is derived from PartItem count — ignore if caller sends it
    # Explicit camelCase → snake_case mapping so the relationship between
    # the JSON body keys and ORM attributes is unambiguous.
    field_map = {
        "category": "category",
        "brand": "brand",
        "model": "model",
        "spec": "spec",
        "sn": "sn",
        "safetyStock": "safety_stock",
        "unit": "unit",
        "location": "location",
        "status": "status",
        "remark": "remark",
    }
    for json_key, attr in field_map.items():
        if json_key in body and body[json_key] is not None:
            setattr(p, attr, body[json_key])
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
    return part_to_dict(p, item_count=_item_count(db, p.id))


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
    # Clear part_item_id references before deleting items
    db.query(StockMovement).filter(
        StockMovement.part_id == pid
    ).update({StockMovement.part_item_id: None})
    db.query(PartItem).filter(PartItem.part_id == pid).delete()
    db.query(StockMovement).filter(StockMovement.part_id == pid).delete()
    db.delete(p)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="part.delete",
            target=label,
            detail="删除备件及其所有单件",
            level="warn",
        )
    )
    db.commit()


# ── PartItem CRUD ─────────────────────────────────────────────────


@router.get("/parts/{pid}/items")
def list_part_items(
    pid: str,
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    p = db.get(Part, pid)
    if not p:
        raise HTTPException(404, "part not found")
    items = (
        db.query(PartItem)
        .filter(PartItem.part_id == pid)
        .order_by(PartItem.created_at.desc())
        .all()
    )
    # resolve server hostnames
    server_ids = {it.installed_server_id for it in items if it.installed_server_id}
    servers: dict[str, str] = {}
    for sid in server_ids:
        s = db.get(Server, sid)
        if s:
            servers[sid] = s.hostname
    return [item_to_dict(it, servers.get(it.installed_server_id)) for it in items]


@router.get("/part-items")
def lookup_item(
    sn: str = Query(..., description="Serial number to look up"),
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    it = db.query(PartItem).filter(PartItem.sn == sn).first()
    if not it:
        raise HTTPException(404, f"未找到 SN={sn} 的备件单件")
    hostname = None
    if it.installed_server_id:
        s = db.get(Server, it.installed_server_id)
        if s:
            hostname = s.hostname
    return item_to_dict(it, hostname)


@router.post("/part-items/lookup-batch")
def lookup_items_batch(
    body: dict,
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    """Batch lookup PartItems by SN list (for BMC cross-reference)."""
    sns: list[str] = body.get("sns") or []
    if not sns:
        return []
    items = db.query(PartItem).filter(PartItem.sn.in_(sns)).all()
    return [item_to_dict(it) for it in items]


@router.get("/part-items/{iid}")
def get_part_item(
    iid: str,
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    it = db.get(PartItem, iid)
    if not it:
        raise HTTPException(404, "part item not found")
    hostname = None
    if it.installed_server_id:
        s = db.get(Server, it.installed_server_id)
        if s:
            hostname = s.hostname
    return item_to_dict(it, hostname)


@router.post("/parts/{pid}/items")
def create_part_items(
    pid: str,
    body: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    p = db.get(Part, pid)
    if not p:
        raise HTTPException(404, "part not found")
    items_data: list[dict] = body.get("items") or []
    if not items_data:
        raise HTTPException(400, "items 不能为空")
    created = []
    for item_data in items_data:
        it = PartItem(
            id=str(uuid.uuid4()),
            part_id=p.id,
            sn=item_data.get("sn"),
            location=item_data.get("location") or p.location,
            status="in_stock",
            remark=item_data.get("remark"),
        )
        db.add(it)
        created.append(it)
    p.stock += len(created)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="part.items.create",
            target=f"part:{p.brand} {p.model}",
            detail=f"添加 {len(created)} 件",
        )
    )
    db.commit()
    return [item_to_dict(it) for it in created]


@router.patch("/part-items/{iid}")
def update_part_item(
    iid: str,
    body: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    it = db.get(PartItem, iid)
    if not it:
        raise HTTPException(404, "part item not found")

    for camel, attr in (
        ("sn", "sn"),
        ("status", "status"),
        ("location", "location"),
        ("installedServerId", "installed_server_id"),
        ("remark", "remark"),
    ):
        if camel in body and body[camel] is not None:
            setattr(it, attr, body[camel])

    # Re-sync parent Part stock when status changes
    p = db.get(Part, it.part_id)
    if p and ("status" in body):
        inv_svc._sync_stock(db, p)

    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="part.item.update",
            target=f"item:{it.sn or iid}",
            detail="更新备件单件",
        )
    )
    db.commit()
    db.refresh(it)
    hostname = None
    if it.installed_server_id:
        s = db.get(Server, it.installed_server_id)
        if s:
            hostname = s.hostname
    return item_to_dict(it, hostname)


@router.delete("/part-items/{iid}", status_code=204)
def delete_part_item(
    iid: str,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    it = db.get(PartItem, iid)
    if not it:
        raise HTTPException(404, "part item not found")
    p = db.get(Part, it.part_id)
    # Nullify movement references
    db.query(StockMovement).filter(
        StockMovement.part_item_id == iid
    ).update({StockMovement.part_item_id: None})
    db.delete(it)
    if p and it.status == "in_stock":
        p.stock = max(0, p.stock - 1)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="part.item.delete",
            target=f"item:{it.sn or iid}",
            detail="删除备件单件",
            level="warn",
        )
    )
    db.commit()


# ── movements ─────────────────────────────────────────────────────


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
    items_cache: dict[str, PartItem] = {}
    for m in rows:
        if m.part_id not in parts_cache:
            parts_cache[m.part_id] = db.get(Part, m.part_id)
        if m.related_server_id and m.related_server_id not in servers_cache:
            servers_cache[m.related_server_id] = db.get(Server, m.related_server_id)
        if m.part_item_id and m.part_item_id not in items_cache:
            items_cache[m.part_item_id] = db.get(PartItem, m.part_item_id)
        out.append(
            movement_to_dict(
                m,
                parts_cache.get(m.part_id),
                servers_cache.get(m.related_server_id) if m.related_server_id else None,
                items_cache.get(m.part_item_id),
            )
        )
    return out


@router.post("/stock-movements")
def create_movement(
    body: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    class _Payload:
        part_id = body["partId"]
        type = body["type"]
        quantity = body["quantity"]
        operator = body.get("operator", user.username)
        related_server_id = body.get("relatedServerId")
        part_item_id = body.get("partItemId")
        reason = body["reason"]
        items = body.get("items")  # inbound: list of {sn, location}

    try:
        mv = inv_svc.apply_movement(db, _Payload, user.username)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(mv)
    part = db.get(Part, mv.part_id)
    server = db.get(Server, mv.related_server_id) if mv.related_server_id else None
    part_item = db.get(PartItem, mv.part_item_id) if mv.part_item_id else None
    return movement_to_dict(mv, part, server, part_item)
