"""Tests for Feishu Bitable → CMDB spare parts sync.

Covers:
- Table 1: sync_part_item (入库同步) — 8 tests
- Table 2: sync_outbound  (出库/报废) — 8 tests
- Edge Cases — 5 tests
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Part, PartItem, Server, StockMovement
from app.services.feishu_sync import (
    CATEGORY_MAP,
    OPERATION_MAP,
    STATUS_EN_MAP,
    sync_part_item,
    sync_outbound,
)

# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _payload_sync(**overrides) -> dict:
    """Return a minimal valid Table-1 payload."""
    base = {
        "sn": f"TEST-SN-{uuid.uuid4().hex[:8]}",
        "category": "硬盘",
        "brand": "Samsung",
        "model": "PM9A3",
        "spec": "960GB NVMe SSD 2.5\"",
    }
    base.update(overrides)
    return base


def _payload_outbound(sn: str, **overrides) -> dict:
    """Return a minimal valid Table-2 payload."""
    base = {
        "sn": sn,
        "operationType": "出库",
        "operator": "张三",
        "reason": "更换故障硬盘",
    }
    base.update(overrides)
    return base


# ══════════════════════════════════════════════════════════════════════
# Table 1: sync_part_item — 入库同步
# ══════════════════════════════════════════════════════════════════════


class TestSyncPartItem:
    """Tests for POST /feishu/sync-part-item (Table 1)."""

    def test_new_sn_creates_everything(self, db: Session):
        """A brand-new SN creates Part, PartItem, StockMovement, and AuditLog."""
        payload = _payload_sync(sn="NEW-DISK-001")
        result = sync_part_item(db, payload)

        assert result["status"] == "success"
        assert result["isNewItem"] is True
        assert result["cmdbPartId"] is not None
        assert result["cmdbItemId"] is not None

        # Verify Part was created
        part = db.get(Part, result["cmdbPartId"])
        assert part is not None
        assert part.category == "disk"
        assert part.brand == "Samsung"
        assert part.model == "PM9A3"

        # Verify PartItem was created
        item = db.get(PartItem, result["cmdbItemId"])
        assert item is not None
        assert item.sn == "NEW-DISK-001"
        assert item.status == "in_stock"

        # Verify StockMovement was created
        mv = db.query(StockMovement).filter(
            StockMovement.part_item_id == item.id
        ).first()
        assert mv is not None
        assert mv.type == "inbound"
        assert mv.quantity == 1

        # Verify AuditLog was created
        log = db.query(AuditLog).filter(
            AuditLog.action == "inventory.inbound"
        ).first()
        assert log is not None

    def test_missing_required_fields(self, db: Session):
        """Missing 'category' returns status=failed with a clear message."""
        payload = {"sn": "X", "brand": "B", "model": "M", "spec": "S"}
        # category is missing
        result = sync_part_item(db, payload)
        assert result["status"] == "failed"
        assert result["isNewItem"] is False
        assert "category" in result["message"]

    def test_invalid_category(self, db: Session):
        """An unrecognised Chinese category name returns failed."""
        payload = _payload_sync(category="CPU")  # not in CATEGORY_MAP
        result = sync_part_item(db, payload)
        assert result["status"] == "failed"
        assert "CPU" in result["message"]

    def test_existing_sn_updates_item_no_duplicate_movement(
        self, db: Session, sample_part: Part, sample_part_item: PartItem
    ):
        """The same SN sent again updates metadata but does NOT create
        a second inbound StockMovement."""
        payload = _payload_sync(
            sn=sample_part_item.sn,
            brand=sample_part.brand,
            model=sample_part.model,
            spec=sample_part.spec,
            category="硬盘",
        )
        result = sync_part_item(db, payload)
        assert result["status"] == "success"
        assert result["isNewItem"] is False
        assert result["cmdbItemId"] == sample_part_item.id
        assert result["cmdbPartId"] == sample_part.id

        # Should still have only one PartItem for this SN
        count = (
            db.query(PartItem)
            .filter(PartItem.sn == sample_part_item.sn)
            .count()
        )
        assert count == 1

        # Should NOT have created an additional inbound movement
        movements = (
            db.query(StockMovement)
            .filter(StockMovement.part_item_id == sample_part_item.id)
            .all()
        )
        # The existing-item path does not create a StockMovement
        assert len(movements) == 0

    def test_new_sn_matches_existing_part(
        self, db: Session, sample_part: Part
    ):
        """A new SN that matches an existing Part's composite key
        creates a PartItem under that Part (no duplicate Part)."""
        payload = _payload_sync(
            sn="DISK-SN-NEW",
            brand=sample_part.brand,
            model=sample_part.model,
            spec=sample_part.spec,
        )
        result = sync_part_item(db, payload)
        assert result["status"] == "success"
        assert result["isNewItem"] is True
        assert result["cmdbPartId"] == sample_part.id  # re-used existing Part

        # Only one Part with that composite key
        parts = (
            db.query(Part)
            .filter(
                Part.brand == sample_part.brand,
                Part.model == sample_part.model,
                Part.spec == sample_part.spec,
                Part.category == "disk",
            )
            .all()
        )
        assert len(parts) == 1

    def test_new_sn_new_part_creates_both(self, db: Session):
        """A payload whose composite key doesn't match any existing Part
        creates both a new Part and a new PartItem."""
        payload = _payload_sync(
            sn="INTEL-DISK-001",
            brand="Intel",
            model="D7-P5510",
            spec="3.84TB NVMe U.2",
        )
        result = sync_part_item(db, payload)
        assert result["status"] == "success"
        assert result["isNewItem"] is True

        part = db.get(Part, result["cmdbPartId"])
        assert part.brand == "Intel"
        assert part.model == "D7-P5510"
        assert part.stock == 1

    def test_stock_count_updated_after_inbound(self, db: Session):
        """Part.stock reflects the actual number of in_stock PartItems."""
        # First inbound
        r1 = sync_part_item(db, _payload_sync(sn="STOCK-001"))
        assert r1["status"] == "success"
        part = db.get(Part, r1["cmdbPartId"])
        assert part.stock == 1

        # Second inbound — different SN, same Part
        r2 = sync_part_item(
            db,
            _payload_sync(
                sn="STOCK-002",
                brand=part.brand,
                model=part.model,
                spec=part.spec,
            ),
        )
        assert r2["status"] == "success"
        assert r2["cmdbPartId"] == part.id
        db.refresh(part)
        assert part.stock == 2

    def test_default_values_for_optional_fields(self, db: Session):
        """When optional fields are omitted, sensible defaults are used."""
        payload = _payload_sync(sn="DEFAULT-001")
        # No unit, safetyStock, location, remark, operator, reason
        result = sync_part_item(db, payload)
        assert result["status"] == "success"

        part = db.get(Part, result["cmdbPartId"])
        assert part.unit == "块"
        assert part.safety_stock == 0
        assert part.location == ""

        item = db.get(PartItem, result["cmdbItemId"])
        # item.location falls back to part.location (empty), then default ""
        assert item.status == "in_stock"


# ══════════════════════════════════════════════════════════════════════
# Table 2: sync_outbound — 出库/报废
# ══════════════════════════════════════════════════════════════════════


class TestSyncOutbound:
    """Tests for POST /feishu/outbound (Table 2)."""

    def test_outbound_success(
        self,
        db: Session,
        sample_part: Part,
        sample_part_item: PartItem,
        sample_server: Server,
    ):
        """An in_stock item can be outbounded to a target server."""
        payload = _payload_outbound(
            sample_part_item.sn,
            targetServer=sample_server.hostname,
        )
        result = sync_outbound(db, payload)

        assert result["status"] == "success"
        assert result["movementId"] is not None
        assert result["cmdbItemId"] == sample_part_item.id

        # PartItem should now be in_use on the target server
        db.refresh(sample_part_item)
        assert sample_part_item.status == "in_use"
        assert sample_part_item.installed_server_id == sample_server.id

        # Stock should be decremented
        db.refresh(sample_part)
        assert sample_part.stock == 1  # was 2, now 1

        # StockMovement created
        mv = db.get(StockMovement, result["movementId"])
        assert mv is not None
        assert mv.type == "outbound"
        assert mv.related_server_id == sample_server.id

    def test_outbound_item_not_found(self, db: Session):
        """A non-existent SN returns failed."""
        result = sync_outbound(db, _payload_outbound("GHOST-SN"))
        assert result["status"] == "failed"
        assert "未找到" in result["message"]

    def test_outbound_item_not_in_stock(
        self,
        db: Session,
        sample_part: Part,
        sample_part_item_in_use: PartItem,
    ):
        """An item that is already in_use cannot be outbounded again."""
        result = sync_outbound(
            db, _payload_outbound(sample_part_item_in_use.sn)
        )
        assert result["status"] == "failed"
        assert "不在库中" in result["message"]

    def test_outbound_missing_target_server(
        self,
        db: Session,
        sample_part: Part,
        sample_part_item: PartItem,
    ):
        """When targetServer specifies a non-existent hostname, outbound fails."""
        result = sync_outbound(
            db,
            _payload_outbound(
                sample_part_item.sn,
                targetServer="ghost-server",
            ),
        )
        assert result["status"] == "failed"
        assert "未找到目标服务器" in result["message"]

    def test_outbound_without_target_server_allocates(
        self,
        db: Session,
        sample_part: Part,
        sample_part_item: PartItem,
    ):
        """Outbound without targetServer sets item status to 'allocated'."""
        payload = _payload_outbound(sample_part_item.sn)
        # No targetServer
        result = sync_outbound(db, payload)

        assert result["status"] == "success"
        db.refresh(sample_part_item)
        assert sample_part_item.status == "allocated"
        assert sample_part_item.installed_server_id is None

    def test_scrap_success(
        self,
        db: Session,
        sample_part: Part,
        sample_part_item: PartItem,
    ):
        """An in_stock item can be scrapped."""
        payload = _payload_outbound(
            sample_part_item.sn,
            operationType="报废",
            reason="硬盘故障无法修复",
        )
        result = sync_outbound(db, payload)

        assert result["status"] == "success"
        assert result["movementId"] is not None

        db.refresh(sample_part_item)
        assert sample_part_item.status == "scrapped"

        # Stock should be adjusted
        db.refresh(sample_part)
        assert sample_part.stock == 1  # was 2

        # StockMovement created
        mv = db.get(StockMovement, result["movementId"])
        assert mv.type == "scrap"

    def test_scrap_already_scrapped(
        self, db: Session, sample_part_item_scrapped: PartItem
    ):
        """A scrapped item cannot be scrapped again."""
        result = sync_outbound(
            db,
            _payload_outbound(
                sample_part_item_scrapped.sn,
                operationType="报废",
            ),
        )
        assert result["status"] == "failed"
        assert "已报废" in result["message"]

    def test_invalid_operation_type(self, db: Session):
        """An unrecognised operation type returns failed."""
        result = sync_outbound(
            db,
            _payload_outbound("any-sn", operationType="借用"),
        )
        assert result["status"] == "failed"
        assert "不支持的操作类型" in result["message"]

    def test_scrap_without_sn_creates_movement(self, db: Session):
        """Scrap without an SN creates a StockMovement + AuditLog directly."""
        payload = {
            "operationType": "报废",
            "operator": "张三",
            "reason": "硬盘故障无法修复",
            "category": "硬盘",
            "brand": "Seagate",
            "model": "ST1000",
            "spec": "1TB SATA",
            "remark": "飞书工单 #999",
        }
        result = sync_outbound(db, payload)

        assert result["status"] == "success"
        assert result["movementId"] is not None
        assert result["cmdbItemId"] is None
        assert "未关联备件库库存" in result["message"]

        # Verify StockMovement was created
        mv = db.get(StockMovement, result["movementId"])
        assert mv is not None
        assert mv.type == "scrap"
        assert mv.part_item_id is None  # no PartItem tracking
        assert mv.quantity == 1
        assert mv.operator == "张三"

        # Verify Part was created from payload fields
        part = db.get(Part, mv.part_id)
        assert part is not None
        assert part.brand == "Seagate"
        assert part.model == "ST1000"

        # Verify AuditLog was created
        log = (
            db.query(AuditLog)
            .filter(AuditLog.action == "inventory.scrap")
            .first()
        )
        assert log is not None
        assert "SN=未提供" in log.detail

    def test_scrap_unknown_sn_creates_movement(self, db: Session):
        """Scrap with an SN not in the system creates a StockMovement
        (not just an AuditLog as before)."""
        payload = {
            "sn": "GHOST-SN-999",
            "operationType": "报废",
            "operator": "李四",
            "reason": "老旧设备淘汰",
            "category": "网卡",
            "brand": "Mellanox",
            "model": "CX5",
            "spec": "100GbE",
            "remark": "批量报废",
        }
        result = sync_outbound(db, payload)

        assert result["status"] == "success"
        assert result["movementId"] is not None
        assert result["cmdbItemId"] is None

        mv = db.get(StockMovement, result["movementId"])
        assert mv is not None
        assert mv.type == "scrap"
        assert mv.part_item_id is None
        assert mv.reason == "老旧设备淘汰"

        # AuditLog should mention the SN
        log = (
            db.query(AuditLog)
            .filter(AuditLog.action == "inventory.scrap")
            .first()
        )
        assert log is not None
        assert "GHOST-SN-999" in log.detail

    def test_scrap_without_sn_minimal_fields(self, db: Session):
        """Scrap without SN and without brand/model still works
        (falls back to '未知' brand and '未知' model)."""
        payload = {
            "operationType": "报废",
            "operator": "王五",
            "reason": "测试最小字段报废",
        }
        result = sync_outbound(db, payload)

        assert result["status"] == "success"
        assert result["movementId"] is not None

        mv = db.get(StockMovement, result["movementId"])
        assert mv is not None
        assert mv.type == "scrap"

        part = db.get(Part, mv.part_id)
        assert part.brand == "未知"
        assert part.model == "未知"

    def test_outbound_without_sn_fails(self, db: Session):
        """Outbound without SN returns failed (SN is still required for outbound)."""
        payload = {
            "operationType": "出库",
            "operator": "张三",
            "reason": "测试",
        }
        result = sync_outbound(db, payload)
        assert result["status"] == "failed"
        assert "SN" in result["message"]

    def test_missing_required_fields(self, db: Session):
        """Missing 'operator' returns failed."""
        payload = {"sn": "any-sn", "operationType": "出库", "reason": "test"}
        # operator is missing
        result = sync_outbound(db, payload)
        assert result["status"] == "failed"
        assert "operator" in result["message"]


# ══════════════════════════════════════════════════════════════════════
# Edge Cases
# ══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge-case and integration tests."""

    def test_whitespace_in_sn_is_trimmed(self, db: Session):
        """Leading/trailing whitespace in SN is stripped."""
        payload = _payload_sync(sn="  EDGE-SN-001  ")
        result = sync_part_item(db, payload)

        assert result["status"] == "success"
        item = db.get(PartItem, result["cmdbItemId"])
        assert item.sn == "EDGE-SN-001"  # trimmed, not "  EDGE-SN-001  "

    def test_brand_not_in_allowlist_still_succeeds(self, db: Session):
        """An unknown brand logs a warning but the sync still succeeds."""
        payload = _payload_sync(
            sn="EDGE-BRAND-001",
            brand="RandomBrand",
            model="XYZ",
            spec="1TB",
        )
        result = sync_part_item(db, payload)
        # Should succeed despite brand not being in the allowlist
        assert result["status"] == "success"

        part = db.get(Part, result["cmdbPartId"])
        assert part.brand == "RandomBrand"

    def test_audit_log_created_for_inbound(self, db: Session):
        """sync_part_item writes an AuditLog record."""
        result = sync_part_item(db, _payload_sync(sn="AUDIT-001"))
        assert result["status"] == "success"

        logs = db.query(AuditLog).filter(
            AuditLog.action == "inventory.inbound"
        ).all()
        assert len(logs) >= 1
        log = logs[-1]
        assert "AUDIT-001" in log.detail
        assert log.level == "info"

    def test_audit_log_created_for_outbound(
        self,
        db: Session,
        sample_part: Part,
        sample_part_item: PartItem,
    ):
        """sync_outbound writes an AuditLog record."""
        payload = _payload_outbound(
            sample_part_item.sn,
            remark="飞书工单 #12345",
        )
        result = sync_outbound(db, payload)
        assert result["status"] == "success"

        logs = (
            db.query(AuditLog)
            .filter(AuditLog.action == "inventory.outbound")
            .all()
        )
        assert len(logs) >= 1
        log = logs[-1]
        assert "飞书工单 #12345" in log.detail

    def test_cross_category_part_isolation(self, db: Session):
        """Same brand+model+spec but different category → different Parts."""
        # Create a disk Part
        r1 = sync_part_item(
            db,
            _payload_sync(
                sn="CROSS-001",
                brand="Intel",
                model="X710",
                spec="DA2",
                category="网卡",
            ),
        )
        assert r1["status"] == "success"
        disk_part_id = r1["cmdbPartId"]

        # Same brand/model/spec but as "memory"
        r2 = sync_part_item(
            db,
            _payload_sync(
                sn="CROSS-002",
                brand="Intel",
                model="X710",
                spec="DA2",
                category="内存",
            ),
        )
        assert r2["status"] == "success"
        assert r2["cmdbPartId"] != disk_part_id  # Different Part!

        # Verify two Parts with different categories exist
        p1 = db.get(Part, disk_part_id)
        p2 = db.get(Part, r2["cmdbPartId"])
        assert p1.category == "nic"
        assert p2.category == "memory"
