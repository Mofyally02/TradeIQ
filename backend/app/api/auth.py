import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Database
from app.core.config import get_settings
from app.models import User, UserSession
from app.schemas import UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["Authentication"])
password_hash = PasswordHash.recommended()


def issue_session(db: Session, user: User, response: Response) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours)
    db.add(
        UserSession(
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    db.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, response: Response, db: Database) -> User:
    user = User(
        full_name=payload.full_name,
        email=str(payload.email), password_hash=password_hash.hash(payload.password),
    )
    db.add(user)
    try:
        db.flush()
        issue_session(db, user, response)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists"
        ) from error
    return user


@router.post("/login", response_model=UserRead)
def login(payload: UserLogin, response: Response, db: Database) -> User:
    user = db.scalar(select(User).where(User.email == str(payload.email)))
    if user is None or not password_hash.verify(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect"
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is currently unavailable. Contact support.",
        )
    issue_session(db, user, response)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    current_user: CurrentUser,
    db: Database,
    session_token: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
) -> Response:
    if session_token:
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        session = db.get(UserSession, token_hash)
        if session is not None and session.user_id == current_user.id:
            session.revoked_at = datetime.now(UTC)
            db.commit()
    response.delete_cookie(
        key=get_settings().session_cookie_name,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> User:
    return current_user
