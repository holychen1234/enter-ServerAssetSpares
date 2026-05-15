import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import (
    check_account_lock,
    create_token,
    get_current_user,
    hash_password,
    record_failed_login,
    require_admin,
    reset_failed_login,
    validate_password_strength,
    verify_password,
)
from app.api.serializers import audit_to_dict, profile_to_dict
from app.db.base import get_db
from app.db.models import AuditLog, Profile

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@router.post("/auth/login")
def login(payload: dict, db: Session = Depends(get_db)):
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    user = db.query(Profile).filter(Profile.username == username).first()

    if not user:
        raise HTTPException(401, "用户名或密码错误")

    # Check lock before verifying password so locked users cannot probe
    check_account_lock(user)

    if not verify_password(password, user.password_hash):
        record_failed_login(user, db)
        raise HTTPException(401, "用户名或密码错误")

    if not user.enabled or user.is_deleted:
        raise HTTPException(403, "账号已被禁用或删除")
    if user.password_change_required:
        # Still issue a token, but include a flag so the frontend can
        # redirect to the change-password page.
        pass

    reset_failed_login(user, db)
    user.last_login = datetime.now(timezone.utc)
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


@router.put("/auth/password")
def change_my_password(
    payload: dict,
    db: Session = Depends(get_db),
    user: Profile = Depends(get_current_user),
):
    """Current user changes their own password (requires old password)."""
    old_password = payload.get("old_password", "")
    new_password = payload.get("new_password", "")

    if not verify_password(old_password, user.password_hash):
        raise HTTPException(400, "原密码错误")

    err = validate_password_strength(new_password)
    if err:
        raise HTTPException(400, err)

    user.password_hash = hash_password(new_password)
    user.password_change_required = 0
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=user.username,
            action="user.password_change",
            target=f"user:{user.username}",
            detail="修改自己的密码",
            level="info",
        )
    )
    db.commit()
    return profile_to_dict(user)


# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------

@router.get("/users")
def list_users(
    q: Optional[str] = Query(None, description="free-text search across username/name/email"),
    role: Optional[str] = Query(None, description="filter by role"),
    enabled: Optional[int] = Query(None, description="filter by enabled status: 1 or 0"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: Profile = Depends(get_current_user),
):
    """Paged + filterable user list. Excludes soft-deleted users by default.

    Returns ``{ items: [...], total: int }``.
    """
    query = db.query(Profile).filter(Profile.is_deleted == 0)

    if role:
        query = query.filter(Profile.role == role)
    if enabled is not None:
        query = query.filter(Profile.enabled == enabled)
    if q:
        kw = f"%{q}%"
        query = query.filter(
            or_(
                Profile.username.ilike(kw),
                Profile.name.ilike(kw),
                Profile.email.ilike(kw),
            )
        )

    total = query.count()
    rows = (
        query.order_by(Profile.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": [profile_to_dict(u) for u in rows], "total": total}


@router.post("/users")
def create_user(
    payload: dict,
    db: Session = Depends(get_db),
    actor: Profile = Depends(require_admin),
):
    """Create a new user. Validates username uniqueness and password strength."""
    username = (payload.get("username") or "").strip()
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    role = payload.get("role", "viewer")

    if not username or not name or not email or not password:
        raise HTTPException(400, "用户名、姓名、邮箱和密码为必填项")

    if role not in ("admin", "operator", "viewer"):
        raise HTTPException(400, "角色无效")

    err = validate_password_strength(password)
    if err:
        raise HTTPException(400, err)

    existing = db.query(Profile).filter(Profile.username == username).first()
    if existing:
        raise HTTPException(409, "用户名已存在")

    user = Profile(
        id=str(uuid.uuid4()),
        username=username,
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        enabled=1,
        password_change_required=1,  # force password change on first login
    )
    db.add(user)
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=actor.username,
            action="user.create",
            target=f"user:{username}",
            detail=f"创建用户 {username}（角色：{role}）",
            level="warn",
        )
    )
    db.commit()
    db.refresh(user)
    return profile_to_dict(user)


@router.patch("/users/{uid}")
def update_user(
    uid: str,
    patch: dict,
    db: Session = Depends(get_db),
    actor: Profile = Depends(require_admin),
):
    """Update user fields. Blocks editing of self-role to prevent lock-out."""
    user = db.get(Profile, uid)
    if not user or user.is_deleted:
        raise HTTPException(404, "用户不存在")

    changed = []
    for f in ("name", "email", "role", "enabled", "password_change_required"):
        if f in patch and patch[f] is not None:
            old_val = getattr(user, f)
            new_val = patch[f]
            setattr(user, f, new_val)
            if old_val != new_val:
                changed.append(f"{f}: {old_val} → {new_val}")

    if changed:
        db.add(
            AuditLog(
                id=str(uuid.uuid4()),
                actor=actor.username,
                action="user.update",
                target=f"user:{user.username}",
                detail="; ".join(changed),
                level="warn",
            )
        )

    db.commit()
    db.refresh(user)
    return profile_to_dict(user)


@router.delete("/users/{uid}")
def delete_user(
    uid: str,
    db: Session = Depends(get_db),
    actor: Profile = Depends(require_admin),
):
    """Soft-delete a user. Cannot delete self."""
    user = db.get(Profile, uid)
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == actor.id:
        raise HTTPException(400, "不能删除自己的账号")
    if user.is_deleted:
        raise HTTPException(400, "用户已被删除")

    user.is_deleted = 1
    user.enabled = 0
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=actor.username,
            action="user.delete",
            target=f"user:{user.username}",
            detail=f"删除用户 {user.username}（软删除）",
            level="warn",
        )
    )
    db.commit()
    return {"ok": True}


@router.put("/users/{uid}/password")
def reset_user_password(
    uid: str,
    payload: dict,
    db: Session = Depends(get_db),
    actor: Profile = Depends(require_admin),
):
    """Admin resets another user's password."""
    new_password = payload.get("password") or ""

    err = validate_password_strength(new_password)
    if err:
        raise HTTPException(400, err)

    user = db.get(Profile, uid)
    if not user or user.is_deleted:
        raise HTTPException(404, "用户不存在")

    user.password_hash = hash_password(new_password)
    user.password_change_required = 1
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=actor.username,
            action="user.password_reset",
            target=f"user:{user.username}",
            detail=f"重置用户 {user.username} 的密码",
            level="warn",
        )
    )
    db.commit()
    return {"ok": True}


@router.put("/users/{uid}/unlock")
def unlock_user(
    uid: str,
    db: Session = Depends(get_db),
    actor: Profile = Depends(require_admin),
):
    """Admin manually unlocks a temporarily locked account."""
    user = db.get(Profile, uid)
    if not user or user.is_deleted:
        raise HTTPException(404, "用户不存在")

    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            actor=actor.username,
            action="user.unlock",
            target=f"user:{user.username}",
            detail=f"手动解锁用户 {user.username}",
            level="warn",
        )
    )
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Audit logs (accessible to all authenticated users)
# ---------------------------------------------------------------------------

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
