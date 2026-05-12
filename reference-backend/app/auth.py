from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Header, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Profile
from app.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def create_token(profile: Profile) -> str:
    payload = {
        "sub": profile.id,
        "username": profile.username,
        "role": profile.role,
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


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
    if not user or not user.enabled:
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
