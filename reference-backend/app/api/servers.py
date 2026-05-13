import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.serializers import server_to_dict
from app.auth import get_current_user, require_writer
from app.db.base import get_db
from app.db.models import AuditLog, Profile, Server
from app.services import bmc as bmc_svc

router = APIRouter()


def _apply_payload(s: Server, body: dict):
    mapping = {
        "hostname": "hostname",
        "sn": "sn",
        "assetTag": "asset_tag",
        "manufacturer": "manufacturer",
        "model": "model",
        "cpuModel": "cpu_model",
        "cpuCount": "cpu_count",
        "memoryGB": "memory_gb",
        "diskCount": "disk_count",
        "mgmtIp": "mgmt_ip",
        "bizIp": "biz_ip",
        "bmcProtocol": "bmc_protocol",
        "bmcUser": "bmc_user",
        "status": "status",
        "owner": "owner",
        "purchaseDate": "purchase_date",
        "warrantyEnd": "warranty_end",
        "tags": "tags",
        "remark": "remark",
    }
    for k, attr in mapping.items():
        if k in body and body[k] is not None:
            setattr(s, attr, body[k])
    if "location" in body and body["location"]:
        loc = body["location"]
        s.idc = loc.get("idc", s.idc)
        s.rack = loc.get("rack", s.rack)
        s.u_position = loc.get("uPosition", s.u_position)
    # BMC password: only persist when caller explicitly sends a non-empty
    # string. Empty string / missing key = "keep existing password".
    pwd = body.get("bmcPassword")
    if isinstance(pwd, str) and pwd != "":
        s.bmc_password = pwd


@router.get("/servers")
def list_servers(
    db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    rows = db.query(Server).order_by(Server.created_at.desc()).all()
    return [server_to_dict(r) for r in rows]


@router.get("/servers/{sid}")
def get_server(
    sid: str, db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")
    return server_to_dict(s)


@router.post("/servers")
def create_server(
    body: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    s = Server(id=str(uuid.uuid4()))
    _apply_payload(s, body)
    db.add(s)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="server.create",
            target=f"srv:{s.hostname}",
            detail=f"录入服务器 {s.hostname}",
        )
    )
    db.commit()
    db.refresh(s)
    return server_to_dict(s)


@router.patch("/servers/{sid}")
def update_server(
    sid: str,
    body: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")
    _apply_payload(s, body)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="server.update",
            target=f"srv:{s.hostname}",
            detail="更新服务器信息",
        )
    )
    db.commit()
    db.refresh(s)
    return server_to_dict(s)


@router.delete("/servers/{sid}", status_code=204)
def delete_server(
    sid: str,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_writer),
):
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")
    hostname = s.hostname
    db.delete(s)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="server.delete",
            target=f"srv:{hostname}",
            detail="删除服务器",
            level="warn",
        )
    )
    db.commit()


@router.get("/servers/{sid}/bmc")
async def server_bmc(
    sid: str,
    refresh: bool = False,
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    s = db.get(Server, sid)
    if not s:
        raise HTTPException(404, "server not found")
    return await bmc_svc.get_status(s, force_refresh=refresh)
