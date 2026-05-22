from datetime import datetime
from typing import Iterable

from app.db.models import AuditLog, Part, PartItem, Profile, Server, StockMovement


def server_to_dict(s: Server) -> dict:
    return {
        "id": s.id,
        "hostname": s.hostname,
        "sn": s.sn,
        "assetTag": s.asset_tag,
        "manufacturer": s.manufacturer,
        "model": s.model,
        "cpuModel": s.cpu_model,
        "cpuCount": s.cpu_count,
        "memoryGB": s.memory_gb,
        "diskCount": s.disk_count,
        "location": {
            "idc": s.idc,
            "rack": s.rack,
            "uPosition": s.u_position,
        },
        "mgmtIp": s.mgmt_ip,
        "bizIp": s.biz_ip,
        "bmcProtocol": s.bmc_protocol,
        "bmcUser": s.bmc_user,
        # bmc_password is intentionally NOT returned. We only expose a
        # boolean so the UI can show "已设置 / 未设置".
        "bmcPasswordSet": bool(s.bmc_password),
        "status": s.status,
        "owner": s.owner or "",
        "purchaseDate": s.purchase_date.isoformat() if isinstance(s.purchase_date, (datetime,)) else (s.purchase_date or ""),
        "warrantyEnd": s.warranty_end.isoformat() if isinstance(s.warranty_end, (datetime,)) else (s.warranty_end or ""),
        "tags": s.tags or [],
        "remark": s.remark,
        "createdAt": s.created_at.isoformat(),
        "updatedAt": s.updated_at.isoformat(),
    }


def item_to_dict(it: PartItem, server_hostname: str | None = None) -> dict:
    return {
        "id": it.id,
        "partId": it.part_id,
        "sn": it.sn,
        "status": it.status,
        "location": it.location,
        "installedServerId": it.installed_server_id,
        "installedServerHostname": server_hostname,
        "remark": it.remark,
        "createdAt": it.created_at.isoformat(),
    }


def part_to_dict(p: Part, item_count: int | None = None, status_counts: dict | None = None) -> dict:
    return {
        "id": p.id,
        "category": p.category,
        "brand": p.brand,
        "model": p.model,
        "spec": p.spec,
        "sn": p.sn,
        "stock": p.stock,
        "safetyStock": p.safety_stock,
        "unit": p.unit,
        "location": p.location,
        "status": p.status,
        "itemCount": item_count if item_count is not None else p.stock,
        "statusCounts": status_counts or {},
        "remark": p.remark,
        "createdAt": p.created_at.isoformat(),
    }


def profile_to_dict(u: Profile) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "enabled": bool(u.enabled),
        "isDeleted": bool(u.is_deleted),
        "passwordChangeRequired": bool(u.password_change_required),
        "failedLoginAttempts": u.failed_login_attempts or 0,
        "lockedUntil": u.locked_until.isoformat() if u.locked_until else None,
        "lastLogin": u.last_login.isoformat() if u.last_login else None,
    }


def audit_to_dict(a: AuditLog) -> dict:
    return {
        "id": a.id,
        "time": a.created_at.isoformat(),
        "actor": a.actor,
        "action": a.action,
        "target": a.target,
        "detail": a.detail or "",
        "level": a.level,
    }


def movement_to_dict(
    m: StockMovement,
    part: Part | None,
    server: Server | None,
    part_item: PartItem | None = None,
) -> dict:
    return {
        "id": m.id,
        "partId": m.part_id,
        "partModel": f"{part.brand} {part.model}" if part else "",
        "category": part.category if part else "other",
        "type": m.type,
        "quantity": m.quantity,
        "operator": m.operator,
        "relatedServerId": m.related_server_id,
        "relatedServerHostname": server.hostname if server else None,
        "partItemId": m.part_item_id,
        "partItemSn": part_item.sn if part_item else None,
        "reason": m.reason,
        "time": m.created_at.isoformat(),
    }


def to_list(items: Iterable, fn) -> list:
    return [fn(x) for x in items]
