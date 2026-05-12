from sqlalchemy.orm import Session

from app.db.models import AuditLog, Part, StockMovement
import uuid


def apply_movement(db: Session, payload, operator: str) -> StockMovement:
    part: Part | None = db.get(Part, payload.part_id)
    if not part:
        raise ValueError("备件不存在")

    delta = payload.quantity if payload.type in ("inbound", "return") else -payload.quantity
    new_stock = part.stock + delta
    if new_stock < 0:
        raise ValueError("库存不足")
    part.stock = new_stock

    mv = StockMovement(
        id=str(uuid.uuid4()),
        part_id=part.id,
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
            action=f"inventory.{payload.type}",
            target=f"part:{part.brand} {part.model}",
            detail=payload.reason,
            level="warn" if payload.type == "scrap" else "info",
        )
    )
    db.flush()
    return mv
