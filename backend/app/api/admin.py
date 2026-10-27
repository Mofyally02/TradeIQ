import base64
import hashlib
import hmac
import re
import secrets
import struct
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, Database
from app.core.config import get_settings
from app.models import User, UserSession
from app.platform_models import (
    AccountConnection,
    AccountSnapshot,
    AdminAuditLog,
    AdminMfa,
    AdminPermission,
    AdminRole,
    AdminRolePermission,
    MT5Deal,
    PerformanceRoadmap,
    PlatformIncident,
    SyncRun,
    Trade,
    TradeReview,
    TradingAccount,
    UserRoleAssignment,
)
from app.services.credentials import decrypt_secret, encrypt_secret
from app.services.metaapi import metaapi_client
from app.services.mt5_method import (
    default_method,
    effective_method,
    set_default_method,
)

Method = Literal["metaapi", "ea"]

ADMIN_PERMISSIONS = (
    "overview.read",
    "users.read",
    "users.manage_roles",
    "users.manage_status",
    "accounts.read",
    "connectors.read",
    "sync.read",
    "data_quality.read",
    "data_quality.resolve",
    "journal_quality.read",
    "intelligence.read",
    "taxonomy.manage",
    "risk_rules.manage",
    "development.manage",
    "experiments.manage",
    "incidents.manage",
    "audit.read",
    "settings.manage",
)


def _role_names(db: Database, user: User) -> list[str]:
    if user.role == "admin":
        return ["super_admin"]
    now = datetime.now(UTC)
    rows = db.execute(
        select(AdminRole.name, UserRoleAssignment.expires_at)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == AdminRole.id)
        .where(
            UserRoleAssignment.user_id == user.id,
            UserRoleAssignment.scope_type == "platform",
        )
    ).all()
    return [
        name
        for name, expires_at in rows
        if expires_at is None
        or (expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at) > now
    ]


def _permissions(db: Database, user: User) -> list[str]:
    if user.role == "admin":
        return list(ADMIN_PERMISSIONS)
    return list(
        db.scalars(
            select(AdminPermission.key)
            .join(AdminRolePermission, AdminRolePermission.permission_id == AdminPermission.id)
            .join(AdminRole, AdminRole.id == AdminRolePermission.role_id)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == AdminRole.id)
            .where(
                UserRoleAssignment.user_id == user.id,
                UserRoleAssignment.scope_type == "platform",
                (UserRoleAssignment.expires_at.is_(None))
                | (UserRoleAssignment.expires_at > datetime.now(UTC)),
            )
            .distinct()
        ).all()
    )


def require_admin(
    current_user: CurrentUser,
    db: Database,
    session_token: Annotated[
        str | None, Cookie(alias=get_settings().session_cookie_name)
    ] = None,
) -> User:
    if not _role_names(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    record = db.get(AdminMfa, current_user.id)
    if record is None or not record.enabled:
        raise HTTPException(
            status_code=428,
            detail={"code": "admin_mfa_setup_required", "message": "Admin MFA enrollment required"},
        )
    session = _session_for(db, current_user, session_token)
    if session.mfa_verified_at is None:
        raise HTTPException(
            status_code=428,
            detail={"code": "admin_mfa_verification_required", "message": "Verify admin MFA"},
        )
    verified_at = session.mfa_verified_at
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    if (datetime.now(UTC) - verified_at).total_seconds() > 12 * 60 * 60:
        raise HTTPException(
            status_code=428,
            detail={"code": "admin_mfa_verification_required", "message": "Verify admin MFA"},
        )
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]
router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])
mfa_router = APIRouter(prefix="/admin/mfa", tags=["Admin MFA"])


def require_permission(permission: str):
    def check(admin: AdminUser, db: Database) -> User:
        if permission not in _permissions(db, admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing administrative permission: {permission}",
            )
        return admin

    return Depends(check)


class MethodUpdate(BaseModel):
    method: Method | None


class DefaultMethodUpdate(BaseModel):
    method: Method


class ReasonPayload(BaseModel):
    reason: str = Field(min_length=8, max_length=1000)


class UserStatusUpdate(ReasonPayload):
    status: Literal["active", "suspended"]


class RoleAssignmentUpdate(ReasonPayload):
    roles: list[Literal[
        "platform_ops",
        "data_quality",
        "intelligence_admin",
        "support_agent",
        "read_only_auditor",
    ]] = Field(max_length=5)


class IncidentCreate(BaseModel):
    category: str = Field(min_length=1, max_length=48)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1, max_length=5000)


class IncidentUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved", "accepted_exception"]
    resolution_reason: str | None = Field(default=None, max_length=2000)
    assigned_to: UUID | None = None


class MfaCodePayload(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


def _audit(
    db: Database,
    actor: User,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    reason: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            actor_user_id=actor.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=reason,
            outcome="success",
            details=details,
        )
    )


def _safe_error(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(
        r"(?i)(authorization|password|token|secret|credential)(\s*[:=]\s*|\s+)[^\s,;]+",
        r"\1\2[redacted]",
        value[:1000],
    )


def _totp(secret: str, timestamp: int | None = None) -> str:
    counter = int((timestamp if timestamp is not None else datetime.now(UTC).timestamp()) // 30)
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def _verify_totp(secret: str, code: str) -> bool:
    if not re.fullmatch(r"\d{6}", code):
        return False
    current = int(datetime.now(UTC).timestamp())
    return any(
        hmac.compare_digest(_totp(secret, current + shift * 30), code)
        for shift in (-1, 0, 1)
    )


def _session_for(db: Database, user: User, session_token: str | None) -> UserSession:
    if not session_token:
        raise HTTPException(status_code=401, detail="Admin session is not available")
    token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    session = db.get(UserSession, token_hash)
    if session is None or session.user_id != user.id or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Admin session is invalid")
    return session


def _assert_admin_identity(db: Database, user: User) -> None:
    if not _role_names(db, user):
        raise HTTPException(status_code=403, detail="Admin access required")


def _check_mfa_lock(record: AdminMfa) -> None:
    locked_until = record.locked_until
    if locked_until and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    if locked_until and locked_until > datetime.now(UTC):
        raise HTTPException(status_code=429, detail="Authenticator temporarily locked")


def _record_mfa_failure(db: Database, record: AdminMfa) -> None:
    from datetime import timedelta

    record.failed_attempts += 1
    if record.failed_attempts >= 5:
        record.locked_until = datetime.now(UTC) + timedelta(minutes=15)
    db.commit()


@mfa_router.post("/setup")
def setup_admin_mfa(current_user: CurrentUser, db: Database) -> dict[str, str]:
    _assert_admin_identity(db, current_user)
    existing = db.get(AdminMfa, current_user.id)
    if existing is not None and existing.enabled:
        raise HTTPException(status_code=409, detail="Admin MFA is already enabled")
    if existing is not None:
        _check_mfa_lock(existing)
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    record = existing or AdminMfa(user_id=current_user.id, encrypted_secret="")
    record.encrypted_secret = encrypt_secret(secret)
    record.enabled = False
    db.add(record)
    _audit(
        db,
        current_user,
        "admin.mfa.setup",
        "admin_mfa",
        str(current_user.id),
        details={"secret_issued": True},
    )
    db.commit()
    uri = (
        f"otpauth://totp/{quote('MofyAlly EDGE:' + current_user.email)}"
        f"?secret={secret}&issuer={quote('MofyAlly EDGE')}&algorithm=SHA1&digits=6&period=30"
    )
    return {"secret": secret, "otpauth_uri": uri}


@mfa_router.post("/confirm")
def confirm_admin_mfa(
    payload: MfaCodePayload,
    current_user: CurrentUser,
    db: Database,
    session_token: Annotated[
        str | None, Cookie(alias=get_settings().session_cookie_name)
    ] = None,
) -> dict[str, str]:
    _assert_admin_identity(db, current_user)
    record = db.get(AdminMfa, current_user.id)
    if record is None or record.enabled:
        raise HTTPException(status_code=409, detail="Start an MFA setup before confirming")
    _check_mfa_lock(record)
    if not _verify_totp(decrypt_secret(record.encrypted_secret), payload.code):
        _record_mfa_failure(db, record)
        raise HTTPException(status_code=401, detail="Authenticator code is invalid")
    record.enabled = True
    record.enabled_at = datetime.now(UTC)
    record.failed_attempts = 0
    record.locked_until = None
    session = _session_for(db, current_user, session_token)
    session.mfa_verified_at = datetime.now(UTC)
    _audit(db, current_user, "admin.mfa.enabled", "admin_mfa", str(current_user.id))
    db.commit()
    return {"status": "enabled"}


@mfa_router.post("/verify")
def verify_admin_mfa(
    payload: MfaCodePayload,
    current_user: CurrentUser,
    db: Database,
    session_token: Annotated[
        str | None, Cookie(alias=get_settings().session_cookie_name)
    ] = None,
) -> dict[str, str]:
    _assert_admin_identity(db, current_user)
    record = db.get(AdminMfa, current_user.id)
    if record is None or not record.enabled:
        raise HTTPException(status_code=428, detail="Admin MFA enrollment is required")
    _check_mfa_lock(record)
    if not _verify_totp(decrypt_secret(record.encrypted_secret), payload.code):
        _record_mfa_failure(db, record)
        raise HTTPException(status_code=401, detail="Authenticator code is invalid")
    record.failed_attempts = 0
    record.locked_until = None
    session = _session_for(db, current_user, session_token)
    session.mfa_verified_at = datetime.now(UTC)
    db.commit()
    return {"status": "verified"}


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


@router.get("/me")
def admin_me(admin: AdminUser, db: Database) -> dict[str, object]:
    return {
        "id": str(admin.id),
        "email": admin.email,
        "full_name": admin.full_name,
        "roles": _role_names(db, admin),
        "permissions": _permissions(db, admin),
        "mfa_enabled": True,
    }


@router.get("/overview", dependencies=[require_permission("overview.read")])
def overview(db: Database, admin: AdminUser) -> dict[str, object]:
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
        "active_users": db.scalar(
            select(func.count()).select_from(User).where(User.status == "active")
        )
        or 0,
        "suspended_users": db.scalar(
            select(func.count()).select_from(User).where(User.status == "suspended")
        )
        or 0,
        "sync_runs_failed": db.scalar(
            select(func.count()).select_from(SyncRun).where(SyncRun.status == "failed")
        )
        or 0,
        "open_incidents": db.scalar(
            select(func.count()).select_from(PlatformIncident).where(
                PlatformIncident.status.in_(["open", "investigating"])
            )
        )
        or 0,
        "accounts_by_connector": by_type,
        "default_method": default_method(db),
        "metaapi_configured": bool(get_settings().metaapi_token),
        "public_api_url": get_settings().public_api_url,
    }


@router.get("/settings", dependencies=[require_permission("settings.manage")])
def get_platform_settings(db: Database) -> dict[str, object]:
    return {
        "default_method": default_method(db),
        "metaapi_configured": bool(get_settings().metaapi_token),
        "public_api_url": get_settings().public_api_url,
    }


@router.put("/settings", dependencies=[require_permission("settings.manage")])
def update_platform_settings(
    payload: DefaultMethodUpdate, db: Database, admin: AdminUser
) -> dict[str, object]:
    previous = default_method(db)
    set_default_method(db, payload.method)
    _audit(
        db,
        admin,
        "platform.settings.update",
        "platform_setting",
        "mt5_method",
        details={"before": previous, "after": payload.method},
    )
    db.commit()
    return get_platform_settings(db)


@router.get("/users", dependencies=[require_permission("users.read")])
def list_users(
    db: Database,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, object]]:
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
                "last_error": _safe_error(connection.last_error),
            }
        )
    return [
        {
            "id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "created_at": iso(user.created_at),
            "status": user.status,
            "roles": _role_names(db, user),
            "method_override": user.mt5_method,
            "method": effective_method(db, user),
            "accounts": accounts_by_user.get(str(user.id), []),
        }
        for user in users
        if q is None
        or q.lower() in user.email.lower()
        or q.lower() in (user.full_name or "").lower()
    ][:offset + limit][offset:]


async def release_other_method(db: Database, user: User, method: str) -> int:
    """Reset connections that use the method the user is being switched away from."""
    released = 0
    for _, connection in db.execute(
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
async def set_user_method(
    user_id: UUID,
    payload: MethodUpdate,
    db: Database,
    admin: AdminUser,
    _: None = require_permission("settings.manage"),
) -> dict[str, object]:
    user = db.get(User, str(user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    previous_method = effective_method(db, user)
    user.mt5_method = payload.method
    released = await release_other_method(db, user, effective_method(db, user))
    _audit(
        db,
        admin,
        "user.mt5_method.update",
        "user",
        str(user.id),
        details={
            "previous_method": previous_method,
            "method": effective_method(db, user),
            "accounts_reset": released,
        },
    )
    db.commit()
    return {
        "method": effective_method(db, user),
        "method_override": user.mt5_method,
        "accounts_reset": released,
    }


@router.get("/health", dependencies=[require_permission("overview.read")])
def admin_health(db: Database) -> dict[str, object]:
    try:
        db.execute(select(1))
        database_status = "healthy"
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database readiness check failed") from error
    settings = get_settings()
    return {
        "status": "healthy",
        "database": database_status,
        "metaapi_configured": bool(settings.metaapi_token),
        "public_api_configured": bool(settings.public_api_url),
        "worker_status": "not_reported",
        "limitations": ["Background-worker heartbeat is not currently persisted."],
    }


@router.get("/accounts", dependencies=[require_permission("accounts.read")])
def admin_accounts(
    db: Database,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, object]]:
    query = (
        select(TradingAccount, User, AccountConnection)
        .join(User, User.id == TradingAccount.user_id)
        .outerjoin(AccountConnection, AccountConnection.account_id == TradingAccount.id)
        .where(TradingAccount.archived_at.is_(None))
        .order_by(TradingAccount.created_at.desc())
    )
    if q:
        search = f"%{q.lower()}%"
        query = query.where(
            func.lower(TradingAccount.name).like(search)
            | func.lower(func.coalesce(TradingAccount.external_account_id, "")).like(search)
            | func.lower(func.coalesce(TradingAccount.server_name, "")).like(search)
            | func.lower(User.email).like(search)
        )
    rows = db.execute(query.limit(limit).offset(offset)).all()
    result: list[dict[str, object]] = []
    for account, user, connection in rows:
        latest_snapshot = db.scalar(
            select(AccountSnapshot)
            .where(AccountSnapshot.account_id == account.id)
            .order_by(AccountSnapshot.observed_at.desc())
            .limit(1)
        )
        result.append(
            {
                "id": str(account.id),
                "owner_id": str(user.id),
                "owner_email": user.email,
                "name": account.name,
                "broker": account.broker,
                "server": account.server_name,
                "login": account.external_account_id,
                "currency": account.currency,
                "environment": account.environment,
                "connector": connection.connector_type if connection else "not_configured",
                "status": connection.status if connection else "not_configured",
                "last_synced_at": iso(connection.last_synced_at) if connection else None,
                "last_error": _safe_error(connection.last_error if connection else None),
                "last_snapshot_at": iso(latest_snapshot.observed_at) if latest_snapshot else None,
            }
        )
    return result


@router.get("/connectors", dependencies=[require_permission("connectors.read")])
def admin_connectors(db: Database) -> list[dict[str, object]]:
    rows = db.execute(
        select(TradingAccount, User, AccountConnection)
        .join(User, User.id == TradingAccount.user_id)
        .outerjoin(AccountConnection, AccountConnection.account_id == TradingAccount.id)
        .where(TradingAccount.archived_at.is_(None))
        .order_by(TradingAccount.name)
    ).all()
    now = datetime.now(UTC)
    result = []
    for account, user, connection in rows:
        synced_at = connection.last_synced_at if connection else None
        if synced_at and synced_at.tzinfo is None:
            synced_at = synced_at.replace(tzinfo=UTC)
        stale = synced_at is None or (now - synced_at.astimezone(UTC)).total_seconds() > 900
        result.append(
            {
                "account_id": str(account.id),
                "account_name": account.name,
                "owner_email": user.email,
                "connector": connection.connector_type if connection else "not_configured",
                "status": connection.status if connection else "not_configured",
                "last_heartbeat_at": iso(synced_at),
                "health": (
                    "error"
                    if connection and connection.status == "error"
                    else "stale"
                    if stale and connection and connection.status == "connected"
                    else connection.status
                    if connection
                    else "not_configured"
                ),
                "safe_diagnostic": _safe_error(connection.last_error if connection else None),
            }
        )
    return result


@router.get("/sync-runs", dependencies=[require_permission("sync.read")])
def admin_sync_runs(
    db: Database,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    account_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, object]]:
    query = (
        select(SyncRun, TradingAccount, User)
        .join(TradingAccount, TradingAccount.id == SyncRun.account_id)
        .join(User, User.id == TradingAccount.user_id)
        .order_by(SyncRun.started_at.desc())
    )
    if status_filter:
        query = query.where(SyncRun.status == status_filter)
    if account_id:
        query = query.where(SyncRun.account_id == account_id)
    return [
        {
            "id": str(run.id),
            "account_id": str(account.id),
            "account_name": account.name,
            "owner_email": user.email,
            "status": run.status,
            "records_processed": run.records_processed,
            "error": _safe_error(run.error),
            "started_at": iso(run.started_at),
            "completed_at": iso(run.completed_at),
        }
        for run, account, user in db.execute(query.limit(limit).offset(offset)).all()
    ]


@router.get("/reconciliation-issues", dependencies=[require_permission("data_quality.read")])
def reconciliation_issues(
    db: Database, limit: int = Query(default=100, ge=1, le=500)
) -> dict[str, object]:
    linked_trade = (
        select(Trade.id)
        .where(
            Trade.account_id == MT5Deal.account_id,
            Trade.external_id == MT5Deal.position_identifier,
        )
        .correlate(MT5Deal)
        .exists()
    )
    rows = db.execute(
        select(MT5Deal, TradingAccount, User)
        .join(TradingAccount, TradingAccount.id == MT5Deal.account_id)
        .join(User, User.id == TradingAccount.user_id)
        .where(
            MT5Deal.position_identifier.is_not(None),
            ~linked_trade,
        )
        .order_by(MT5Deal.occurred_at.desc())
        .limit(limit)
    ).all()
    return {
        "issues": [
            {
                "id": str(deal.id),
                "type": "deal_without_trade_episode",
                "status": "potential",
                "account_id": str(account.id),
                "account_name": account.name,
                "owner_email": user.email,
                "source_identifier": deal.external_deal_id,
                "position_identifier": deal.position_identifier,
                "symbol": deal.symbol,
                "occurred_at": iso(deal.occurred_at),
                "reason": "No trade episode currently references this MT5 position identifier.",
            }
            for deal, account, user in rows
        ],
        "limitations": [
            "These are automated mapping candidates, not confirmed discrepancies.",
            "No records are changed or marked resolved by this diagnostic.",
        ],
    }


@router.get("/journal-quality", dependencies=[require_permission("journal_quality.read")])
def journal_quality(db: Database) -> dict[str, object]:
    closed = select(Trade).where(Trade.outcome.in_(["win", "loss", "flat"]))
    total = db.scalar(select(func.count()).select_from(closed.subquery())) or 0
    reviewed = db.scalar(
        select(func.count()).select_from(
            select(TradeReview.id)
            .join(Trade, Trade.id == TradeReview.trade_id)
            .where(Trade.outcome.in_(["win", "loss", "flat"]))
            .subquery()
        )
    ) or 0
    has_plan = db.scalar(
        select(func.count()).select_from(
            select(Trade.id)
            .where(Trade.outcome.in_(["win", "loss", "flat"]), Trade.plan_id.is_not(None))
            .subquery()
        )
    ) or 0
    has_strategy = db.scalar(
        select(func.count()).select_from(
            select(Trade.id)
            .where(
                Trade.outcome.in_(["win", "loss", "flat"]),
                Trade.strategy != "Uncategorized",
            )
            .subquery()
        )
    ) or 0
    has_stop = db.scalar(
        select(func.count()).select_from(
            select(Trade.id)
            .where(Trade.outcome.in_(["win", "loss", "flat"]), Trade.stop_loss.is_not(None))
            .subquery()
        )
    ) or 0
    return {
        "closed_trades": total,
        "reviewed_trades": reviewed,
        "review_coverage_pct": reviewed / total * 100 if total else None,
        "with_pretrade_plan": has_plan,
        "plan_coverage_pct": has_plan / total * 100 if total else None,
        "with_strategy": has_strategy,
        "strategy_coverage_pct": has_strategy / total * 100 if total else None,
        "with_recorded_stop": has_stop,
        "stop_coverage_pct": has_stop / total * 100 if total else None,
        "privacy": "Aggregate counts only; private notes and reflections are not returned.",
    }


@router.get("/intelligence/health", dependencies=[require_permission("intelligence.read")])
def intelligence_health(db: Database) -> dict[str, object]:
    return {
        "engine": "deterministic_per_user_analytics",
        "external_model_enabled": False,
        "saved_roadmaps": db.scalar(
            select(func.count()).select_from(PerformanceRoadmap)
        )
        or 0,
        "persisted_analysis_runs": False,
        "limitations": [
            (
                "Background job queue, run latency and insight evaluation results "
                "are not persisted yet."
            ),
            "No shared trader-performance statistics are used.",
        ],
    }


@router.get("/incidents", dependencies=[require_permission("incidents.manage")])
def list_incidents(
    db: Database,
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, object]]:
    query = select(PlatformIncident).order_by(PlatformIncident.created_at.desc())
    if status_filter:
        query = query.where(PlatformIncident.status == status_filter)
    return [
        {
            "id": str(row.id),
            "category": row.category,
            "severity": row.severity,
            "title": row.title,
            "description": row.description,
            "status": row.status,
            "assigned_to": str(row.assigned_to) if row.assigned_to else None,
            "resolution_reason": row.resolution_reason,
            "created_at": iso(row.created_at),
            "resolved_at": iso(row.resolved_at),
        }
        for row in db.scalars(query.limit(limit).offset(offset)).all()
    ]


@router.post("/incidents", status_code=201, dependencies=[require_permission("incidents.manage")])
def create_incident(
    payload: IncidentCreate, admin: AdminUser, db: Database
) -> dict[str, object]:
    incident = PlatformIncident(
        **payload.model_dump(),
        created_by=admin.id,
    )
    db.add(incident)
    db.flush()
    _audit(
        db,
        admin,
        "incident.create",
        "platform_incident",
        str(incident.id),
        details={"category": incident.category, "severity": incident.severity},
    )
    db.commit()
    db.refresh(incident)
    return {
        "id": str(incident.id),
        "category": incident.category,
        "severity": incident.severity,
        "title": incident.title,
        "description": incident.description,
        "status": incident.status,
        "created_at": iso(incident.created_at),
    }


@router.patch(
    "/incidents/{incident_id}",
    dependencies=[require_permission("incidents.manage")],
)
def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    admin: AdminUser,
    db: Database,
) -> dict[str, object]:
    incident = db.get(PlatformIncident, str(incident_id))
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if payload.status in {"resolved", "accepted_exception"} and not (
        payload.resolution_reason and payload.resolution_reason.strip()
    ):
        raise HTTPException(
            status_code=422, detail="A resolution reason is required to close an incident"
        )
    previous_status = incident.status
    incident.status = payload.status
    if payload.assigned_to is not None:
        assignee = db.get(User, str(payload.assigned_to))
        if assignee is None or assignee.status != "active":
            raise HTTPException(status_code=422, detail="Assignee is not an active user")
        incident.assigned_to = assignee.id
    if payload.resolution_reason is not None:
        incident.resolution_reason = payload.resolution_reason
    incident.resolved_at = (
        datetime.now(UTC) if payload.status in {"resolved", "accepted_exception"} else None
    )
    _audit(
        db,
        admin,
        "incident.update",
        "platform_incident",
        str(incident.id),
        reason=payload.resolution_reason,
        details={"previous_status": previous_status, "status": payload.status},
    )
    db.commit()
    db.refresh(incident)
    return {
        "id": str(incident.id),
        "status": incident.status,
        "resolution_reason": incident.resolution_reason,
        "resolved_at": iso(incident.resolved_at),
    }


@router.get("/audit-logs", dependencies=[require_permission("audit.read")])
def audit_logs(
    db: Database,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    actor_id: UUID | None = None,
) -> list[dict[str, object]]:
    query = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
    if actor_id:
        query = query.where(AdminAuditLog.actor_user_id == actor_id)
    return [
        {
            "id": str(row.id),
            "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "reason": row.reason,
            "outcome": row.outcome,
            "details": row.details,
            "created_at": iso(row.created_at),
        }
        for row in db.scalars(query.limit(limit).offset(offset)).all()
    ]


@router.get("/roles", dependencies=[require_permission("users.manage_roles")])
def admin_roles(db: Database) -> list[dict[str, object]]:
    roles = db.scalars(select(AdminRole).order_by(AdminRole.name)).all()
    return [
        {
            "name": role.name,
            "description": role.description,
            "permissions": db.scalars(
                select(AdminPermission.key)
                .join(AdminRolePermission, AdminRolePermission.permission_id == AdminPermission.id)
                .where(AdminRolePermission.role_id == role.id)
                .order_by(AdminPermission.key)
            ).all(),
        }
        for role in roles
    ]


@router.put(
    "/users/{user_id}/roles",
    dependencies=[require_permission("users.manage_roles")],
)
def assign_admin_roles(
    user_id: UUID,
    payload: RoleAssignmentUpdate,
    admin: AdminUser,
    db: Database,
) -> dict[str, object]:
    target = db.get(User, str(user_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id or target.role == "admin":
        raise HTTPException(
            status_code=409,
            detail="Privileged account roles require the separate approved elevation workflow",
        )
    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == target.id).delete()
    for role_name in set(payload.roles):
        role = db.scalar(select(AdminRole).where(AdminRole.name == role_name))
        if role is None:
            raise HTTPException(status_code=422, detail="Unknown administrator role")
        db.add(
            UserRoleAssignment(
                user_id=target.id,
                role_id=role.id,
                scope_type="platform",
                assigned_by=admin.id,
            )
        )
    target.role = "user"
    _audit(
        db,
        admin,
        "user.admin_roles.replace",
        "user",
        str(target.id),
        reason=payload.reason,
        details={"roles": sorted(set(payload.roles))},
    )
    db.commit()
    return {"user_id": str(target.id), "roles": sorted(set(payload.roles))}


@router.patch(
    "/users/{user_id}/status",
    dependencies=[require_permission("users.manage_status")],
)
def update_user_status(
    user_id: UUID,
    payload: UserStatusUpdate,
    admin: AdminUser,
    db: Database,
) -> dict[str, object]:
    target = db.get(User, str(user_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id or target.role == "admin":
        raise HTTPException(status_code=409, detail="Cannot suspend this privileged account")
    before = target.status
    target.status = payload.status
    if payload.status == "suspended":
        from app.models import UserSession

        sessions = db.scalars(
            select(UserSession).where(
                UserSession.user_id == target.id, UserSession.revoked_at.is_(None)
            )
        ).all()
        for session in sessions:
            session.revoked_at = datetime.now(UTC)
    _audit(
        db,
        admin,
        "user.status.update",
        "user",
        str(target.id),
        reason=payload.reason,
        details={"before": before, "after": target.status},
    )
    db.commit()
    return {"user_id": str(target.id), "status": target.status}
