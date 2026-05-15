import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Header, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Profile
from app.settings import settings

# bcrypt 4.x removed `__about__`, which trips passlib 1.7.4 on first call
# and surfaces as a 500 -> the frontend then sees "Internal Server Error"
# instead of JSON. We pin bcrypt==4.0.1 in requirements, but also keep a
# defensive try/except so a future env mismatch fails *cleanly* with 401
# rather than crashing the request.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------- password policy ----------
PASSWORD_MIN_LENGTH = 8
_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def validate_password_strength(raw: str) -> str | None:
    """Return an error message if the password is too weak, else None."""
    if len(raw) < PASSWORD_MIN_LENGTH:
        return f"密码长度至少 {PASSWORD_MIN_LENGTH} 位"
    if not _PASSWORD_PATTERN.match(raw):
        return "密码须包含大写字母、小写字母和数字"
    return None


# ---------- bcrypt helpers ----------

def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(raw, hashed)
    except Exception:
        # Fallback: call bcrypt directly. Both bcrypt 3.x and 4.x expose
        # checkpw / hashpw, so this works regardless of passlib quirks.
        try:
            import bcrypt as _bcrypt

            return _bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False


# ---------- JWT ----------

def create_token(profile: Profile) -> str:
    payload = {
        "sub": profile.id,
        "username": profile.username,
        "role": profile.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


# ---------- auth dependencies ----------

def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Profile:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}")
    user = db.get(Profile, payload["sub"])
    if not user or not user.enabled or user.is_deleted:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user disabled or missing")
    return user


def require_role(*roles: str):
    def _dep(user: Profile = Depends(get_current_user)) -> Profile:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
        return user

    return _dep


require_writer = require_role("admin", "operator")
require_admin = require_role("admin")


# ---------- login rate-limit helper ----------

def check_account_lock(user: Profile) -> None:
    """Raise 423 if the account is temporarily locked."""
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds())
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"账号已被锁定，请 {remaining // 60} 分钟后重试",
        )


def record_failed_login(user: Profile, db: Session) -> None:
    """Increment failed count and lock if threshold reached."""
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
    db.commit()


def reset_failed_login(user: Profile, db: Session) -> None:
    """Clear failed counter and lock on successful login."""
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
