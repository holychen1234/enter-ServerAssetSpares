from datetime import datetime, timezone
from typing import Iterable

from app.db.models import (
    AuditLog,
    NetworkDevice,
    Part,
    PartItem,
    Profile,
    Server,
    StockMovement,
    Workstation,
)


def _iso(dt: datetime | None) -> str:
    """Naive UTC → ISO-8601 with +00:00 offset so browsers convert to local time."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


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
        "createdAt": _iso(s.created_at),
        "updatedAt": _iso(s.updated_at),
    }


def network_device_to_dict(nd: NetworkDevice) -> dict:
    return {
        "id": nd.id,
        "hostname": nd.hostname,
        "sn": nd.sn,
        "assetTag": nd.asset_tag,
        "deviceType": nd.device_type,
        "manufacturer": nd.manufacturer,
        "model": nd.model,
        "firmwareVersion": nd.firmware_version or "",
        "cpuModel": nd.cpu_model or "",
        "cpuCount": nd.cpu_count,
        "memoryGB": nd.memory_gb,
        "flashGB": nd.flash_gb,
        "mgmtIp": nd.mgmt_ip,
        "mgmtProtocol": nd.mgmt_protocol,
        "mgmtPort": nd.mgmt_port,
        "snmpCommunity": nd.snmp_community or "",
        "sshUsername": nd.ssh_username or "",
        "sshPasswordSet": bool(nd.ssh_password),
        "bizIp": nd.biz_ip or "",
        "vlan": nd.vlan or "",
        "portCount": nd.port_count,
        "portSpec": nd.port_spec or [],
        "idc": nd.idc,
        "rack": nd.rack,
        "uPosition": nd.u_position,
        "status": nd.status,
        "owner": nd.owner or "",
        "purchaseDate": nd.purchase_date.isoformat() if isinstance(nd.purchase_date, (datetime,)) else (nd.purchase_date or ""),
        "warrantyEnd": nd.warranty_end.isoformat() if isinstance(nd.warranty_end, (datetime,)) else (nd.warranty_end or ""),
        "tags": nd.tags or [],
        "remark": nd.remark,
        "createdAt": _iso(nd.created_at),
        "updatedAt": _iso(nd.updated_at),
    }


def workstation_to_dict(ws: Workstation) -> dict:
    return {
        "id": ws.id,
        "hostname": ws.hostname,
        "sn": ws.sn,
        "assetTag": ws.asset_tag,
        "manufacturer": ws.manufacturer,
        "model": ws.model,
        "cpuModel": ws.cpu_model,
        "cpuCount": ws.cpu_count,
        "memoryGB": ws.memory_gb,
        "diskType": ws.disk_type,
        "diskCapacityGB": ws.disk_capacity_gb,
        "macAddress": ws.mac_address or "",
        "os": ws.os,
        "osVersion": ws.os_version or "",
        "bizIp": ws.biz_ip or "",
        "userName": ws.user_name or "",
        "department": ws.department or "",
        "monitors": ws.monitors or [],
        "officeBuilding": ws.office_building or "",
        "floor": ws.floor or "",
        "seat": ws.seat or "",
        "status": ws.status,
        "purchaseDate": ws.purchase_date.isoformat() if isinstance(ws.purchase_date, (datetime,)) else (ws.purchase_date or ""),
        "warrantyEnd": ws.warranty_end.isoformat() if isinstance(ws.warranty_end, (datetime,)) else (ws.warranty_end or ""),
        "tags": ws.tags or [],
        "remark": ws.remark,
        "createdAt": _iso(ws.created_at),
        "updatedAt": _iso(ws.updated_at),
    }


def item_to_dict(
    it: PartItem,
    server_hostname: str | None = None,
    workstation_hostname: str | None = None,
) -> dict:
    return {
        "id": it.id,
        "partId": it.part_id,
        "sn": it.sn,
        "status": it.status,
        "location": it.location,
        "installedServerId": it.installed_server_id,
        "installedServerHostname": server_hostname,
        "installedWorkstationId": it.installed_workstation_id,
        "installedWorkstationHostname": workstation_hostname,
        "remark": it.remark,
        "createdAt": _iso(it.created_at),
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
        "createdAt": _iso(p.created_at),
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
        "lockedUntil": _iso(u.locked_until) or None,
        "lastLogin": _iso(u.last_login) or None,
    }


def audit_to_dict(a: AuditLog) -> dict:
    return {
        "id": a.id,
        "time": _iso(a.created_at),
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
    workstation: Workstation | None = None,
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
        "relatedWorkstationId": m.related_workstation_id,
        "relatedWorkstationHostname": workstation.hostname if workstation else None,
        "partItemId": m.part_item_id,
        "partItemSn": part_item.sn if part_item else None,
        "reason": m.reason,
        "time": _iso(m.created_at),
    }


def to_list(items: Iterable, fn) -> list:
    return [fn(x) for x in items]
