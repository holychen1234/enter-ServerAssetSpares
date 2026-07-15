"""Feishu Bitable sync endpoints for spare parts inventory management.

Each endpoint receives a webhook payload from a Feishu Bitable workflow,
processes the data, and returns a JSON response that the Feishu workflow
writes back to the row's system-managed columns.

All endpoints are **unauthenticated** (same pattern as ``/api/ai/*``) so
Feishu workflows can call them without configuring auth headers.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services import feishu_sync as sync_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu", tags=["feishu"])


@router.post("/sync-part-item")
def sync_part_item(
    body: dict,
    db: Session = Depends(get_db),
):
    """Receive a spare-part item row from Feishu Bitable Table 1
    (备件库存清单) and sync it to CMDB.

    **Expected payload fields (Chinese column names):**

    - ``sn`` (required) — PartItem serial number
    - ``category`` (required) — 硬盘 / 内存 / 网卡 / 光模块 / 其他
    - ``brand`` (required) — manufacturer brand
    - ``model`` (required) — part model number
    - ``spec`` (required) — detailed spec string
    - ``unit`` — 块 / 条 / 个
    - ``safetyStock`` — low-stock threshold (default 0)
    - ``location`` — storage location
    - ``remark`` — free-text notes
    - ``operator`` — who performed the inbound
    - ``reason`` — inbound reason description

    **Response** (always HTTP 200)::

        {
          "status": "success" | "failed",
          "cmdbPartId": "<uuid>" | null,
          "cmdbItemId": "<uuid>" | null,
          "isNewItem": true | false,
          "message": "human-readable result"
        }

    The Feishu workflow writes *cmdbPartId*, *cmdbItemId*, *status*,
    *time*, and *message* back to the row's system-managed columns.
    """
    try:
        return sync_svc.sync_part_item(db, body)
    except Exception:
        logger.exception("Feishu /sync-part-item unexpected error")
        return {
            "status": "failed",
            "cmdbPartId": None,
            "cmdbItemId": None,
            "isNewItem": False,
            "message": "同步失败: 服务器内部错误，请稍后重试",
        }


@router.post("/outbound")
def sync_outbound(
    body: dict,
    db: Session = Depends(get_db),
):
    """Process an outbound or scrap operation from Feishu Bitable Table 2
    (出库/报废记录).

    **Expected payload fields (Chinese column names):**

    - ``sn`` (required) — PartItem serial number to operate on
    - ``operationType`` (required) — 出库 / 报废
    - ``operator`` (required) — who performed the operation
    - ``reason`` (required) — reason description
    - ``targetServer`` — server hostname (outbound only)
    - ``remark`` — free-text notes

    **Response** (always HTTP 200)::

        {
          "status": "success" | "failed",
          "movementId": "<uuid>" | null,
          "cmdbItemId": "<uuid>" | null,
          "oldStatus": "在库" | "在用" | ... | null,
          "message": "human-readable result"
        }

    The Feishu workflow writes *movementId*, *cmdbItemId*, *status*,
    *time*, *oldStatus*, and *message* back to the row's system columns.
    """
    try:
        return sync_svc.sync_outbound(db, body)
    except Exception:
        logger.exception("Feishu /feishu/outbound unexpected error")
        return {
            "status": "failed",
            "movementId": None,
            "cmdbItemId": None,
            "oldStatus": None,
            "message": "同步失败: 服务器内部错误，请稍后重试",
        }
