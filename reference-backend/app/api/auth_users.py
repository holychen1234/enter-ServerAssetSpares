import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
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


@router.post("/auth/logout")
def logout(
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    """Stateless JWT — there is nothing to invalidate server-side, but we
    record an audit entry so the operations log shows session bracketing."""
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="user.logout",
            target="session",
            detail="退出登录",
            level="info",
        )
    )
    db.commit()
    return {"ok": True}


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
def list_audit(
    q: Optional[str] = Query(None, description="free-text across actor/action/target/detail"),
    level: Optional[str] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    target: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    """Paged + filterable audit log feed.

    Returns ``{ items: [...], total: int }`` so the UI can render a real
    paginator and "X 条结果" summary.
    """
    query = db.query(AuditLog)
    if level:
        query = query.filter(AuditLog.level == level)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if action:
        # ``"server."`` → prefix match for whole module; otherwise exact.
        if action.endswith("."):
            query = query.filter(AuditLog.action.like(f"{action}%"))
        else:
            query = query.filter(AuditLog.action == action)
    if target:
        query = query.filter(AuditLog.target.ilike(f"%{target}%"))
    if start:
        try:
            query = query.filter(AuditLog.created_at >= datetime.fromisoformat(start))
        except ValueError:
            raise HTTPException(400, "start must be ISO timestamp")
    if end:
        try:
            query = query.filter(AuditLog.created_at < datetime.fromisoformat(end))
        except ValueError:
            raise HTTPException(400, "end must be ISO timestamp")
    if q:
        kw = f"%{q}%"
        query = query.filter(
            or_(
                AuditLog.actor.ilike(kw),
                AuditLog.action.ilike(kw),
                AuditLog.target.ilike(kw),
                AuditLog.detail.ilike(kw),
            )
        )

    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": [audit_to_dict(a) for a in rows], "total": total}
