"""Regression tests for inventory stock consistency.

Covers the bug where inbound movements bumped ``parts.stock`` by the
submitted quantity instead of deriving it from the actual in_stock
PartItems — causing the web to show non-zero stock when the real
inventory was 0.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import Part, PartItem, StockMovement
from app.services import feishu_sync, inventory


class _Payload:
    """Minimal stand-in for the movement payload used by parts.py."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _part(db: Session, brand: str, model: str, spec: str, stock: int = 0) -> Part:
    p = Part(
        id=str(uuid.uuid4()),
        category="disk",
        brand=brand,
        model=model,
        spec=spec,
        stock=stock,
        safety_stock=0,
        unit="块",
        location="A区",
        status="in_stock",
    )
    db.add(p)
    db.flush()
    return p


def _inbound(db: Session, part: Part, quantity: int, items: list[dict] | None = None):
    payload = _Payload(
        part_id=part.id,
        type="inbound",
        quantity=quantity,
        operator="tester",
        related_server_id=None,
        part_item_id=None,
        reason="测试入库",
        items=items or [],
    )
    return inventory.apply_movement(db, payload, "tester")


# ── inbound stock derivation ─────────────────────────────────────────


def test_inbound_items_win_over_quantity(db: Session):
    """Quantity < pasted SNs: stock follows the created items."""
    p = _part(db, "Samsung", "PM9A3", "960GB")
    _inbound(db, p, quantity=1, items=[{"sn": "SN-A"}, {"sn": "SN-B"}, {"sn": "SN-C"}])
    db.commit()
    db.refresh(p)
    assert p.stock == 3
    assert db.query(PartItem).filter(PartItem.part_id == p.id).count() == 3


def test_inbound_quantity_without_items_creates_placeholders(db: Session):
    """Quantity-only inbound creates placeholder items; stock stays consistent."""
    p = _part(db, "Samsung", "PM9A3", "960GB")
    _inbound(db, p, quantity=5, items=[])
    db.commit()
    db.refresh(p)
    assert p.stock == 5
    items = db.query(PartItem).filter(PartItem.part_id == p.id).all()
    assert len(items) == 5
    assert all(i.sn is None for i in items)


def test_inbound_matching_quantity(db: Session):
    p = _part(db, "Samsung", "PM9A3", "960GB")
    _inbound(db, p, quantity=2, items=[{"sn": "SN-1"}, {"sn": "SN-2"}])
    db.commit()
    db.refresh(p)
    assert p.stock == 2


def test_outbound_drains_stock_to_zero(db: Session):
    """After every item leaves the warehouse, stock must be 0."""
    p = _part(db, "Samsung", "PM9A3", "960GB")
    _inbound(db, p, quantity=2, items=[{"sn": "SN-1"}, {"sn": "SN-2"}])
    db.commit()

    for item in db.query(PartItem).filter(PartItem.part_id == p.id).all():
        payload = _Payload(
            part_id=p.id,
            type="outbound",
            quantity=1,
            operator="tester",
            related_server_id=None,
            part_item_id=item.id,
            reason="测试出库",
        )
        inventory.apply_movement(db, payload, "tester")
    db.commit()
    db.refresh(p)
    assert p.stock == 0
    assert db.query(StockMovement).filter(StockMovement.type == "outbound").count() == 2


# ── feishu re-parenting keeps both parts consistent ──────────────────


def test_feishu_reparent_syncs_old_and_new_part_stock(db: Session):
    """An item re-parented to another Part must update both stock counters."""
    a = _part(db, "Samsung", "PM9A3", "960GB", stock=1)
    b = _part(db, "Micron", "M600", "960GB", stock=0)
    db.add(
        PartItem(
            id=str(uuid.uuid4()),
            part_id=a.id,
            sn="MOVE-001",
            location="A区",
            status="in_stock",
        )
    )
    db.commit()

    result = feishu_sync.sync_part_item(
        db,
        {
            "sn": "MOVE-001",
            "category": "硬盘",
            "brand": b.brand,
            "model": b.model,
            "spec": b.spec,
        },
    )
    assert result["status"] == "success"

    db.refresh(a)
    db.refresh(b)
    assert a.stock == 0  # item left part A
    assert b.stock == 1  # item now counted under part B
