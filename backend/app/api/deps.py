import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.models import User, UserSession

Database = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: Database,
    session_token: Annotated[str | None, Cookie(alias=get_settings().session_cookie_name)] = None,
) -> User:
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
        )
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid or expired"
        )
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at.astimezone(UTC) <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid or expired"
        )
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid or expired"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
