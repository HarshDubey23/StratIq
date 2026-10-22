from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Project, User

COOKIE_NAME = "siq_session"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8")[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user_id: str) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=s.jwt_ttl_hours)).timestamp())}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> str | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        return None


def set_session_cookie(response, token: str) -> None:
    s = get_settings()
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=s.cookie_secure, samesite="lax",
                        max_age=s.jwt_ttl_hours * 3600, path="/")


def clear_session_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    auth = request.headers.get("authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:]
    uid = decode_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return user


def owned_project(project_id: str, user: User, db: Session) -> Project:
    """Ownership check. Returns 404 (not 403) so identifiers cannot be probed."""
    p = db.get(Project, project_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return p
