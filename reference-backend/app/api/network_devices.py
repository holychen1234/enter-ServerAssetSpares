import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, DataError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.serializers import network_device_to_dict
from app.auth import get_current_user, require_writer
from app.db.base import get_db
from app.db.models import AuditLog, NetworkDevice, Profile

router = APIRouter()


def _apply_payload(nd: NetworkDevice, body: dict):
    mapping = {
        "hostname": "hostname",
        "sn": "sn",
        "assetTag": "asset_tag",
        "deviceType": "device_type",
        "manufacturer": "manufacturer",
        "model": "model",
        "firmwareVersion": "firmware_version",
        "cpuModel": "cpu_model",
        "cpuCount": "cpu_count",
        "memoryGB": "memory_gb",
        "flashGB": "flash_gb",
        "mgmtIp": "mgmt_ip",
        "mgmtProtocol": "mgmt_protocol",
        "mgmtPort": "mgmt_port",
        "snmpCommunity": "snmp_community",
        "sshUsername": "ssh_username",
        "bizIp": "biz_ip",
        "vlan": "vlan",
        "portCount": "port_count",
        "portSpec": "port_spec",
        "idc": "idc",
        "rack": "rack",
        "uPosition": "u_position",
        "status": "status",
        "owner": "owner",
        "purchaseDate": "purchase_date",
        "warrantyEnd": "warranty_end",
        "tags": "tags",
        "remark": "remark",
    }
    for k, attr in mapping.items():
        if k in body and body[k] is not None:
            setattr(nd, attr, body[k])
    pwd = body.get("sshPassword")
    if isinstance(pwd, str) and pwd != "":
        nd.ssh_password = pwd


@router.get("/network-devices")
def list_network_devices(
    db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    rows = db.query(NetworkDevice).order_by(NetworkDevice.created_at.desc()).all()
    return [network_device_to_dict(r) for r in rows]


@router.post("/network-devices")
def create_network_device(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    nd = NetworkDevice(id=str(uuid.uuid4()))
    _apply_payload(nd, body)
    db.add(nd)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="network_device.create",
            target=f"ndev:{nd.hostname}",
            detail=f"录入网络设备 {nd.hostname}",
        )
    )
    try:
        db.commit()
    except (IntegrityError, DataError, ProgrammingError) as exc:
        db.rollback()
        detail = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
        raise HTTPException(422, f"数据库错误: {detail}")
    except Exception:
        db.rollback()
        raise
    db.refresh(nd)
    return network_device_to_dict(nd)


@router.post("/network-devices/batch-delete", status_code=204)
def batch_delete_network_devices(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    ids: list[str] = (body or {}).get("ids") or []
    if not ids:
        raise HTTPException(400, "ids 不能为空")
    if len(ids) > 200:
        raise HTTPException(400, "单次最多删除 200 台设备")

    devices = db.query(NetworkDevice).filter(NetworkDevice.id.in_(ids)).all()
    hostnames = [d.hostname for d in devices]

    for d in devices:
        db.delete(d)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="network_device.batch_delete",
            target=f"ndev:{len(hostnames)}台设备",
            detail=", ".join(hostnames),
            level="warn",
        )
    )
    db.commit()


@router.get("/network-devices/{nid}")
def get_network_device(
    nid: str, db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    nd = db.get(NetworkDevice, nid)
    if not nd:
        raise HTTPException(404, "network device not found")
    return network_device_to_dict(nd)


@router.patch("/network-devices/{nid}")
def update_network_device(
    nid: str,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    nd = db.get(NetworkDevice, nid)
    if not nd:
        raise HTTPException(404, "network device not found")
    _apply_payload(nd, body)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="network_device.update",
            target=f"ndev:{nd.hostname}",
            detail="更新网络设备信息",
        )
    )
    try:
        db.commit()
    except (IntegrityError, DataError, ProgrammingError) as exc:
        db.rollback()
        detail = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
        raise HTTPException(422, f"数据库错误: {detail}")
    except Exception:
        db.rollback()
        raise
    db.refresh(nd)
    return network_device_to_dict(nd)


@router.delete("/network-devices/{nid}", status_code=204)
def delete_network_device(
    nid: str,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    nd = db.get(NetworkDevice, nid)
    if not nd:
        raise HTTPException(404, "network device not found")
    hostname = nd.hostname
    db.delete(nd)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="network_device.delete",
            target=f"ndev:{hostname}",
            detail="删除网络设备",
            level="warn",
        )
    )
    db.commit()
