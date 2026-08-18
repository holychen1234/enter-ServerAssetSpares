"""Feishu Bitable → CMDB spare parts sync business logic.

Each function receives a parsed JSON payload from a Feishu workflow webhook
and a SQLAlchemy Session.  Known business-logic errors are returned as
structured dicts (``status: "failed"``); unexpected exceptions propagate to
the API layer which wraps them in the same dict shape.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog, Part, PartItem, Server, StockMovement
from app.services import inventory as inv_svc

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────

CATEGORY_MAP: dict[str, str] = dict(
    zip(
        ["硬盘", "内存", "网卡", "光模块", "光转电模块", "其他"],
        ["disk", "memory", "nic", "optical", "optical", "other"],
    )
)

UNIT_MAP: dict[str, str] = {"块": "块", "条": "条", "个": "个"}

OPERATION_MAP: dict[str, str] = dict(
    zip(
        ["出库", "报废"],
        ["outbound", "scrap"],
    )
)

STATUS_EN_MAP: dict[str, str] = dict(
    zip(
        ["在库", "已分配", "在用", "已报废"],
        ["in_stock", "allocated", "in_use", "scrapped"],
    )
)

BRANDS_BY_CATEGORY: dict[str, set[str]] = dict(
    zip(
        ["disk", "memory", "nic", "optical", "other"],
        [
            {
                "DapuStor", "Dell", "HPE", "Huawei", "Inspur", "Intel",
                "Kioxia", "Lenovo", "Memblaze", "Micron", "SK Hynix",
                "Samsung", "Seagate", "Toshiba", "UNIC", "WD", "YMTC",
                "华为", "大普微", "忆联", "浪潮", "紫光", "铠侠", "长江存储",
            },
            {
                "ADATA", "CXMT", "Colorful", "Corsair", "Dell", "G.Skill",
                "Gloway", "HPE", "Kingston", "Lenovo", "Micron", "SK Hynix",
                "Samsung", "UNIC", "YMTC", "七彩虹", "光威", "紫光", "长江存储",
                "长鑫存储",
            },
            {
                "Accelink", "Broadcom", "Chelsio", "H3C", "Huawei", "Inspur",
                "Intel", "Marvell", "Mellanox", "NVIDIA", "Realtek", "光迅",
                "华为", "新华三", "浪潮",
            },
            {
                "Accelink", "Cisco", "Eoptolink", "FS.com", "Finisar", "H3C",
                "HG Genuine", "Huawei", "Innolight", "Intel", "中际旭创",
                "光迅", "华为", "华工正源", "新华三", "新易盛",
            },
            set(),
        ],
    )
)


# ── Helpers ──────────────────────────────────────────────────────────


def _normalize_field(val: Any) -> str:
    """Convert Feishu field values to a plain string.

    Feishu multi-dimensional table single/multi-select columns may
    serialise the value as a list (e.g. ``["硬盘"]``) or an object
    (e.g. ``{"text": "硬盘"}``) instead of a plain string.  This helper
    extracts the first meaningful text regardless of the shape.
    """
    if isinstance(val, str):
        return val
    if isinstance(val, (list, tuple)):
        for item in val:
            s = _normalize_field(item)
            if s:
                return s
        return ""
    if isinstance(val, dict):
        # Try common keys: text, value, name, label
        for k in ("text", "value", "name", "label"):
            v = val.get(k)
            if isinstance(v, str) and v.strip():
                return v
        # Last resort: first string value in the dict
        for v in val.values():
            if isinstance(v, str) and v.strip():
                return v
        return ""
    if val is None:
        return ""
    return str(val)


def _validate_required(payload: dict, *fields: str) -> str | None:
    """Return an error message if any *fields* is missing or empty, else None."""
    for f in fields:
        raw = payload.get(f)
        val = _normalize_field(raw)
        if not val.strip():
            return f"缺少必填字段: {f}（收到: {raw!r}）"
    return None


def _find_or_create_part(
    db: Session,
    brand: str,
    model: str,
    spec: str,
    category_en: str,
    payload: dict,
) -> Part:
    """Look up a Part by composite key; create one if not found."""
    part = (
        db.query(Part)
        .filter(
            Part.brand == brand,
            Part.model == model,
            Part.spec == spec,
            Part.category == category_en,
        )
        .first()
    )
    if part:
        return part

    part = Part(
        id=str(uuid.uuid4()),
        category=category_en,
        brand=brand,
        model=model,
        spec=spec,
        sn=None,
        stock=0,
        safety_stock=int(_normalize_field(payload.get("安全库存")) or 0),
        unit=UNIT_MAP.get(_normalize_field(payload.get("单位")), "块") or "块",
        location=_normalize_field(payload.get("存放位置")) or "",
        status="in_stock",
        remark=None,
    )
    db.add(part)
    db.flush()
    logger.info("Created Part %s (%s %s %s)", part.id, brand, model, category_en)
    return part


def _sync_part_stock(db: Session, part: Part) -> None:
    """Derive Part.stock from actual in_stock PartItem count (same logic as
    ``inventory._sync_stock``)."""
    db.flush()
    count = (
        db.query(PartItem)
        .filter(PartItem.part_id == part.id, PartItem.status == "in_stock")
        .count()
    )
    part.stock = count


# ── Public sync functions ────────────────────────────────────────────


def sync_part_item(db: Session, payload: dict) -> dict[str, Any]:
    """Sync a single spare-part item row from Feishu Bitable Table 1.

    Returns a dict that the Feishu workflow writes back to the row's
    system-managed columns (cmdbPartId, cmdbItemId, sync status, etc.).
    """
    # Validate required fields
    err = _validate_required(payload, "sn", "category", "brand", "model", "spec")
    if err:
        return {
            "status": "failed",
            "cmdbPartId": None,
            "cmdbItemId": None,
            "isNewItem": False,
            "message": err,
        }

    sn: str = _normalize_field(payload.get("sn")).strip()
    category_zh: str = _normalize_field(payload.get("category")).strip()
    brand: str = _normalize_field(payload.get("brand")).strip()
    model: str = _normalize_field(payload.get("model")).strip()
    spec: str = _normalize_field(payload.get("spec")).strip()

    # Map category
    category_en = CATEGORY_MAP.get(category_zh)
    if not category_en:
        supported = "、".join(CATEGORY_MAP.keys())
        return {
            "status": "failed",
            "cmdbPartId": None,
            "cmdbItemId": None,
            "isNewItem": False,
            "message": f"不支持的备件类别: {category_zh}（支持: {supported}）",
        }

    # Brand validation (warning only)
    allowed = BRANDS_BY_CATEGORY.get(category_en, set())
    if allowed and brand not in allowed:
        lower_brand = brand.lower()
        lower_match = any(b.lower() == lower_brand for b in allowed)
        if not lower_match:
            logger.warning(
                "Brand '%s' not in allowed list for category '%s' — allowing anyway",
                brand,
                category_en,
            )

    # Find or create the Part
    part = _find_or_create_part(db, brand, model, spec, category_en, payload)

    # Find or create the PartItem by SN
    item: PartItem | None = (
        db.query(PartItem).filter(PartItem.sn == sn).first()
    )

    is_new_item = False

    if item is None:
        # ── New item: create PartItem + inbound StockMovement ──
        is_new_item = True
        item = PartItem(
            id=str(uuid.uuid4()),
            part_id=part.id,
            sn=sn,
            location=_normalize_field(payload.get("存放位置")) or part.location,
            status="in_stock",
            remark=_normalize_field(payload.get("备注")),
        )
        db.add(item)

        operator = _normalize_field(payload.get("操作人")) or "feishu-sync"
        reason = _normalize_field(payload.get("入库原因")) or "飞书多维表格同步入库"

        mv = StockMovement(
            id=str(uuid.uuid4()),
            part_id=part.id,
            part_item_id=item.id,
            type="inbound",
            quantity=1,
            operator=operator,
            related_server_id=None,
            reason=reason,
        )
        db.add(mv)

        db.add(
            AuditLog(
                id=str(uuid.uuid4()),
                actor=operator,
                action="inventory.inbound",
                target=f"part:{part.brand} {part.model}",
                detail=f"{reason} (SN: {sn})",
                level="info",
            )
        )

        _sync_part_stock(db, part)
        logger.info(
            "Created PartItem %s for Part %s (SN=%s)", item.id, part.id, sn
        )
    else:
        # ── Existing item: update metadata ──
        old_part_id = item.part_id
        item.part_id = part.id

        loc = _normalize_field(payload.get("存放位置"))
        if loc:
            item.location = loc

        rmk = _normalize_field(payload.get("备注"))
        if rmk:
            item.remark = rmk

        if item.status != "in_stock":
            logger.info(
                "Existing PartItem %s (SN=%s) has status=%s — not creating inbound movement",
                item.id,
                sn,
                item.status,
            )

        _sync_part_stock(db, part)

        # If the item was re-parented to a different Part, the old Part's
        # stock must be re-derived too or it silently drifts from reality.
        if old_part_id and old_part_id != part.id:
            old_part = db.get(Part, old_part_id)
            if old_part:
                _sync_part_stock(db, old_part)

    db.commit()

    msg = "入库成功" if is_new_item else "备件已存在，已更新信息"
    return {
        "status": "success",
        "cmdbPartId": part.id,
        "cmdbItemId": item.id,
        "isNewItem": is_new_item,
        "message": msg,
    }


def sync_outbound(db: Session, payload: dict) -> dict[str, Any]:
    """Process an outbound or scrap operation from Feishu Bitable Table 2.

    Calls ``inventory.apply_movement`` so all existing validations and stock
    adjustments are reused exactly.

    For **scrap** operations, *sn* is optional — scraps of items never
    tracked in the spare-parts library are recorded as StockMovement rows
    (with ``part_item_id=NULL``) so they appear in the outbound/scrap
    history without polluting the PartItem inventory.
    """
    # ── Common required fields (sn checked conditionally below) ──
    err = _validate_required(payload, "operationType", "operator", "reason")
    if err:
        return {
            "status": "failed",
            "movementId": None,
            "cmdbItemId": None,
            "oldStatus": None,
            "message": err,
        }

    sn: str = _normalize_field(payload.get("sn")).strip()
    operation_zh: str = _normalize_field(payload.get("operationType")).strip()
    operator: str = _normalize_field(payload.get("operator")).strip()
    reason: str = _normalize_field(payload.get("reason")).strip()
    target_server: str = _normalize_field(payload.get("targetServer")).strip()
    remark: str = _normalize_field(payload.get("remark")).strip()

    # Map operation type
    operation_en = OPERATION_MAP.get(operation_zh)
    if not operation_en:
        supported = "、".join(OPERATION_MAP.keys())
        return {
            "status": "failed",
            "movementId": None,
            "cmdbItemId": None,
            "oldStatus": None,
            "message": f"不支持的操作类型: {operation_zh}（支持: {supported}）",
        }

    # ── Outbound requires SN; scrap does not ──
    if operation_en == "outbound" and not sn:
        return {
            "status": "failed",
            "movementId": None,
            "cmdbItemId": None,
            "oldStatus": None,
            "message": "出库操作必须提供 SN",
        }

    # Find PartItem by SN (if SN provided)
    item: PartItem | None = None
    if sn:
        item = db.query(PartItem).filter(PartItem.sn == sn).first()

    # ══════════════════════════════════════════════════════════════════
    # Path A: PartItem found — existing apply_movement logic
    # ══════════════════════════════════════════════════════════════════
    if item:
        old_status = item.status

        part: Part | None = db.get(Part, item.part_id)
        if not part:
            return {
                "status": "failed",
                "movementId": None,
                "cmdbItemId": item.id,
                "oldStatus": STATUS_EN_MAP.get(old_status, old_status),
                "message": "备件主记录异常，请联系管理员",
            }

        # Pre-validate
        if operation_en == "outbound":
            if item.status != "in_stock":
                return {
                    "status": "failed",
                    "movementId": None,
                    "cmdbItemId": item.id,
                    "oldStatus": STATUS_EN_MAP.get(old_status, old_status),
                    "message": f"备件 {sn} 不在库中（当前状态: {STATUS_EN_MAP.get(item.status, item.status)}），无法出库",
                }
        elif operation_en == "scrap":
            if item.status == "scrapped":
                return {
                    "status": "failed",
                    "movementId": None,
                    "cmdbItemId": item.id,
                    "oldStatus": STATUS_EN_MAP.get(old_status, old_status),
                    "message": f"备件 {sn} 已报废，请勿重复操作",
                }

        # Resolve target server for outbound
        related_server_id = None
        if operation_en == "outbound" and target_server:
            from sqlalchemy import or_

            server = (
                db.query(Server)
                .filter(
                    or_(
                        Server.hostname == target_server,
                        Server.mgmt_ip == target_server,
                        Server.biz_ip == target_server,
                    )
                )
                .first()
            )
            if not server:
                return {
                    "status": "failed",
                    "movementId": None,
                    "cmdbItemId": item.id,
                    "oldStatus": STATUS_EN_MAP.get(old_status, old_status),
                    "message": f"未找到目标服务器: {target_server}（支持按主机名/管理IP/业务IP查找）",
                }
            related_server_id = server.id

        # Build _Payload and delegate to inventory.apply_movement
        _oper = operator
        _rel_srv = related_server_id
        _rsn = reason

        class _Payload:
            part_id = part.id
            type = operation_en
            quantity = 1
            operator = _oper
            related_server_id = _rel_srv
            part_item_id = item.id
            reason = _rsn

        try:
            mv = inv_svc.apply_movement(db, _Payload, operator)
        except ValueError as exc:
            return {
                "status": "failed",
                "movementId": None,
                "cmdbItemId": item.id,
                "oldStatus": STATUS_EN_MAP.get(old_status, old_status),
                "message": str(exc),
            }

        db.add(
            AuditLog(
                id=str(uuid.uuid4()),
                actor=operator,
                action=f"inventory.{operation_en}",
                target=f"part:{part.brand} {part.model}",
                detail=f"Feishu备注: {remark}" if remark else reason,
                level="info",
            )
        )

        db.commit()

        return {
            "status": "success",
            "movementId": mv.id,
            "cmdbItemId": item.id,
            "oldStatus": STATUS_EN_MAP.get(old_status, old_status),
            "message": "操作成功",
        }

    # ══════════════════════════════════════════════════════════════════
    # Path B: No PartItem found
    # ══════════════════════════════════════════════════════════════════

    # ── Outbound without PartItem → error ──
    if operation_en == "outbound":
        return {
            "status": "failed",
            "movementId": None,
            "cmdbItemId": None,
            "oldStatus": None,
            "message": f"未找到 SN={sn} 的备件单件",
        }

    # ── Scrap without PartItem → create StockMovement directly ──
    # Extract part-identifying fields from the payload so we can
    # associate the scrap with a Part even though no PartItem exists.
    category_zh = _normalize_field(payload.get("category")).strip()
    category_en = CATEGORY_MAP.get(category_zh, "other")
    brand = _normalize_field(payload.get("brand")).strip()
    model = _normalize_field(payload.get("model")).strip()
    spec = _normalize_field(payload.get("spec")).strip()

    # Fall back to sensible defaults when payload omits part fields
    if not brand:
        brand = "未知"
    if not model:
        model = sn if sn else "未知"
    if not spec:
        spec = ""

    part = _find_or_create_part(db, brand, model, spec, category_en, payload)

    mv = StockMovement(
        id=str(uuid.uuid4()),
        part_id=part.id,
        part_item_id=None,  # not tracked in PartItem inventory
        type="scrap",
        quantity=1,
        operator=operator,
        related_server_id=None,
        reason=reason,
    )
    db.add(mv)

    sn_label = f"SN={sn}" if sn else "SN=未提供"
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=operator,
            action="inventory.scrap",
            target=f"part:{part.brand} {part.model}",
            detail=f"报废未入库备件 ({sn_label}) — {reason}"
            + (f" / 飞书备注: {remark}" if remark else ""),
            level="warn",
        )
    )

    db.commit()

    return {
        "status": "success",
        "movementId": mv.id,
        "cmdbItemId": None,
        "oldStatus": None,
        "message": "报废记录已创建（未关联备件库库存）",
    }
