from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentUser, Database
from app.core.config import get_settings
from app.models import User
from app.platform_models import AccountConnection, MT5Deal, Trade, TradingAccount
from app.services.metaapi import metaapi_client
from app.services.mt5_method import (
    default_method,
    effective_method,
    set_default_method,
)

Method = Literal["metaapi", "ea"]


def require_admin(current_user: CurrentUser) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]
router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


class MethodUpdate(BaseModel):
    method: Method | None


class DefaultMethodUpdate(BaseModel):
    method: Method


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


@router.get("/me")
def admin_me(admin: AdminUser) -> dict[str, str | None]:
    return {"id": str(admin.id), "email": admin.email, "full_name": admin.full_name}


@router.get("/overview")
def overview(db: Database) -> dict[str, object]:
    connections = db.scalars(select(AccountConnection)).all()
    by_type: dict[str, int] = {}
    for item in connections:
        by_type[item.connector_type] = by_type.get(item.connector_type, 0) + 1
    return {
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "accounts": db.scalar(select(func.count()).select_from(TradingAccount)) or 0,
        "connected_accounts": sum(1 for item in connections if item.status == "connected"),
        "failing_accounts": sum(1 for item in connections if item.status == "error"),
        "trades": db.scalar(select(func.count()).select_from(Trade)) or 0,
        "deals": db.scalar(select(func.count()).select_from(MT5Deal)) or 0,
        "accounts_by_connector": by_type,
        "default_method": default_method(db),
        "metaapi_configured": bool(get_settings().metaapi_token),
        "public_api_url": get_settings().public_api_url,
    }


@router.get("/settings")
def get_platform_settings(db: Database) -> dict[str, object]:
    return {
        "default_method": default_method(db),
        "metaapi_configured": bool(get_settings().metaapi_token),
        "public_api_url": get_settings().public_api_url,
    }


@router.put("/settings")
def update_platform_settings(payload: DefaultMethodUpdate, db: Database) -> dict[str, object]:
    set_default_method(db, payload.method)
    db.commit()
    return get_platform_settings(db)


@router.get("/users")
def list_users(db: Database) -> list[dict[str, object]]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    rows = db.execute(
        select(TradingAccount, AccountConnection)
        .join(AccountConnection, AccountConnection.account_id == TradingAccount.id)
        .where(TradingAccount.archived_at.is_(None))
    ).all()
    accounts_by_user: dict[str, list[dict[str, object]]] = {}
    for account, connection in rows:
        accounts_by_user.setdefault(str(account.user_id), []).append(
            {
                "id": str(account.id),
                "name": account.name,
                "login": account.external_account_id,
                "server": account.server_name,
                "connector": connection.connector_type,
                "status": connection.status,
                "last_synced_at": iso(connection.last_synced_at),
                "last_error": connection.last_error,
            }
        )
    return [
        {
            "id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "created_at": iso(user.created_at),
            "method_override": user.mt5_method,
            "method": effective_method(db, user),
            "accounts": accounts_by_user.get(str(user.id), []),
        }
        for user in users
    ]


async def release_other_method(db: Database, user: User, method: str) -> int:
    """Reset connections that use the method the user is being switched away from."""
    released = 0
    for account, connection in db.execute(
        select(TradingAccount, AccountConnection)
        .join(AccountConnection, AccountConnection.account_id == TradingAccount.id)
        .where(TradingAccount.user_id == user.id)
    ).all():
        if connection.connector_type == method or connection.status == "not_configured":
            continue
        if connection.provider_account_id:
            try:
                provider = await metaapi_client().metatrader_account_api.get_account(
                    connection.provider_account_id
                )
                await provider.remove()
            except Exception:
                pass
        connection.connector_type = "mt5"
        connection.status = "not_configured"
        connection.connector_token_hash = None
        connection.provider_account_id = None
        connection.encrypted_password = None
        connection.last_error = None
        released += 1
    return released


@router.put("/users/{user_id}/mt5-method")
async def set_user_method(user_id: UUID, payload: MethodUpdate, db: Database) -> dict[str, object]:
    user = db.get(User, str(user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.mt5_method = payload.method
    released = await release_other_method(db, user, effective_method(db, user))
    db.commit()
    return {"method": effective_method(db, user), "method_override": user.mt5_method, "accounts_reset": released}
