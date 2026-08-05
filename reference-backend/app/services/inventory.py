import uuid

from sqlalchemy.orm import Session

from app.db.models import AuditLog, Part, PartItem, StockMovement


def _sync_stock(db: Session, part: Part) -> None:
    """Derive Part.stock from in_stock PartItem count."""
    count = (
        db.query(PartItem)
        .filter(PartItem.part_id == part.id, PartItem.status == "in_stock")
        .count()
    )
    part.stock = count


def apply_movement(db: Session, payload, operator: str) -> StockMovement:
    part: Part | None = db.get(Part, payload.part_id)
    if not part:
        raise ValueError("备件不存在")

    if payload.type == "inbound":
        # Create PartItems if item data provided, then bump stock
        items_data: list[dict] = getattr(payload, "items", None) or []
        for item_data in items_data:
            it = PartItem(
                id=str(uuid.uuid4()),
                part_id=part.id,
                sn=item_data.get("sn"),
                location=item_data.get("location") or part.location,
                status="in_stock",
            )
            db.add(it)
        part.stock += payload.quantity
        if part.stock < 0:
            raise ValueError("库存不足")

        mv = StockMovement(
            id=str(uuid.uuid4()),
            part_id=part.id,
            part_item_id=None,
            type=payload.type,
            quantity=payload.quantity,
            operator=operator or payload.operator,
            related_server_id=payload.related_server_id,
            reason=payload.reason,
        )
        db.add(mv)

        db.add(
            AuditLog(
                id=str(uuid.uuid4()),
                actor=operator or payload.operator,
                action="inventory.inbound",
                target=f"part:{part.brand} {part.model}",
                detail=payload.reason,
                level="info",
            )
        )
        db.flush()
        return mv

    # outbound / return / scrap — each targets a single PartItem
    part_item: PartItem | None = None
    part_item_id = getattr(payload, "part_item_id", None)
    if part_item_id:
        part_item = db.get(PartItem, part_item_id)

    if not part_item or part_item.part_id != part.id:
        raise ValueError("请指定要操作的备件单件 (partItemId)")

    if payload.type == "outbound":
        if part_item.status != "in_stock":
            raise ValueError(f"备件 {part_item.sn or part_item.id} 不在库中，无法出库")
        if payload.related_server_id:
            part_item.status = "in_use"
            part_item.installed_server_id = payload.related_server_id
        else:
            part_item.status = "allocated"
            part_item.installed_server_id = None
    elif payload.type == "return":
        if part_item.status not in ("allocated", "in_use"):
            raise ValueError(f"备件 {part_item.sn or part_item.id} 状态不允许归还")
        part_item.status = "in_stock"
        part_item.installed_server_id = None
    elif payload.type == "scrap":
        if part_item.status == "scrapped":
            raise ValueError(f"备件 {part_item.sn or part_item.id} 已报废")
        part_item.status = "scrapped"
        part_item.installed_server_id = None
    else:
        raise ValueError(f"不支持的操作类型: {payload.type}")

    # Always derive stock from the actual in_stock PartItem count so it
    # stays consistent even if a PartItem's status was manually changed
    # via update_part_item before this movement was applied.
    _sync_stock(db, part)

    if part.stock < 0:
        raise ValueError("库存不足")

    mv = StockMovement(
        id=str(uuid.uuid4()),
        part_id=part.id,
        part_item_id=part_item.id,
        type=payload.type,
        quantity=1,
        operator=operator or payload.operator,
        related_server_id=payload.related_server_id,
        reason=payload.reason,
    )
    db.add(mv)

    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=operator or payload.operator,
            action=f"inventory.{payload.type}",
            target=f"part:{part.brand} {part.model}",
            detail=f"{payload.reason} (SN: {part_item.sn or '—'})",
            level="warn" if payload.type == "scrap" else "info",
        )
    )
    db.flush()
    return mv
