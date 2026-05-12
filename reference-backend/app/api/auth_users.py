import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import (
    create_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from app.api.serializers import audit_to_dict, profile_to_dict
from app.db.base import get_db
from app.db.models import AuditLog, Profile

router = APIRouter()


@router.post("/auth/login")
def login(payload: dict, db: Session = Depends(get_db)):
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    user = db.query(Profile).filter(Profile.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if not user.enabled:
        raise HTTPException(403, "账号已被禁用")
    user.last_login = datetime.utcnow()
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="user.login",
            target="session",
            detail="登录系统",
            level="info",
        )
    )
    db.commit()
    return {
        "access_token": create_token(user),
        "token_type": "bearer",
        "user": profile_to_dict(user),
    }


@router.get("/auth/me")
def me(user: Profile = Depends(get_current_user)):
    return profile_to_dict(user)


@router.get("/users")
def list_users(
    db: Session = Depends(get_db), _: Profile = Depends(get_current_user)
):
    return [profile_to_dict(u) for u in db.query(Profile).order_by(Profile.created_at).all()]


@router.patch("/users/{uid}")
def update_user(
    uid: str,
    patch: dict,
    db: Session = Depends(get_db),
    _: Profile = Depends(require_admin),
):
    user = db.get(Profile, uid)
    if not user:
        raise HTTPException(404, "用户不存在")
    for f in ("name", "email", "role", "enabled"):
        if f in patch and patch[f] is not None:
            setattr(user, f, patch[f])
    db.commit()
    return profile_to_dict(user)


@router.get("/audit-logs")
def list_audit(db: Session = Depends(get_db), _: Profile = Depends(get_current_user)):
    rows = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
        .all()
    )
    return [audit_to_dict(a) for a in rows]
