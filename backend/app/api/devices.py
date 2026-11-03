import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, Database
from app.core.config import get_settings
from app.platform_models import DetectedAccount
from app.schemas import AccountRead
from app.services import device, installer
from app.services.mt5_method import effective_method

MAX_BODY_BYTES = 2_000_000
logger = logging.getLogger("tradeiq.devices")

public_router = APIRouter(prefix="/mt5/device", tags=["MT5 device connector"])
router = APIRouter(prefix="/devices", tags=["MT5 device connector"])


@public_router.post("/{user_id}/{secret}")
async def receive_device_push(user_id: UUID, secret: str, request: Request, db: Database) -> dict[str, Any]:
    """Public webhook called by the TradeIQ EA on any of the user's terminals."""
    source_ip = request.client.host if request.client else "unknown"
    try:
        connector = device.authenticate(db, str(user_id), secret)
    except HTTPException:
        logger.warning("Rejected MT5 device push user_id=%s source_ip=%s reason=invalid_token", user_id, source_ip)
        raise
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        logger.warning("Rejected MT5 device push user_id=%s source_ip=%s reason=payload_too_large", user_id, source_ip)
        raise HTTPException(status_code=413, detail="Payload too large")
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        result = device.handle_push(db, connector, data)
    except PermissionError as error:
        db.rollback()
        logger.warning("Rejected MT5 device push user_id=%s source_ip=%s reason=account_mismatch", user_id, source_ip)
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ValueError, KeyError, TypeError) as error:
        db.rollback()
        logger.warning("Rejected MT5 device push user_id=%s source_ip=%s reason=invalid_payload error_type=%s", user_id, source_ip, type(error).__name__)
        raise HTTPException(status_code=422, detail=f"Invalid payload: {error}") from error
    return {"status": "ok", **result}


@public_router.get("/{user_id}/{secret}/ea.mq5")
def download_ea(user_id: UUID, secret: str, db: Database) -> Response:
    device.authenticate(db, str(user_id), secret)
    return Response((installer.EA_DIR / "TradeIQ_Journal.mq5").read_bytes(), media_type="text/plain")


@public_router.get("/{user_id}/{secret}/bridge.py")
def download_bridge(user_id: UUID, secret: str, db: Database) -> Response:
    device.authenticate(db, str(user_id), secret)
    return Response((installer.EA_DIR / "bridge.py").read_bytes(), media_type="text/plain")


@public_router.get("/{user_id}/{secret}/installer/{os_name}")
def download_installer(user_id: UUID, secret: str, os_name: str, db: Database) -> Response:
    device.authenticate(db, str(user_id), secret)
    if os_name not in ("mac", "windows"):
        raise HTTPException(status_code=404, detail="Unknown platform")
    url = device.device_url(str(user_id), secret)
    body, filename, media = installer.render_installer(
        os_name, name="all your MT5 accounts", url=url, base=url,
        origin=get_settings().public_api_url.rstrip("/"), login=None, server=None
    )
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.post("/connector")
def issue_connector(current_user: CurrentUser, db: Database) -> dict[str, object]:
    """Issue (or rotate) the user's device secret and return one-click installers."""
    if effective_method(db, current_user) != "ea":
        raise HTTPException(status_code=403, detail="Your account is set up to connect with the MT5 login method.")
    url = device.device_url(str(current_user.id), device.issue_connector(db, current_user))
    return {"webhook_url": url, "installers": {os_name: f"{url}/installer/{os_name}" for os_name in ("mac", "windows")}}


class DetectedRead(BaseModel):
    id: str
    login: str
    server: str | None
    name: str | None
    currency: str | None
    balance: float | None
    equity: float | None


@router.get("/detected", response_model=list[DetectedRead])
def list_detected(current_user: CurrentUser, db: Database) -> list[DetectedRead]:
    rows = db.scalars(
        select(DetectedAccount)
        .where(DetectedAccount.user_id == str(current_user.id), DetectedAccount.status == "pending")
        .order_by(DetectedAccount.last_seen_at.desc())
    ).all()
    return [
        DetectedRead(
            id=str(r.id),
            login=r.login,
            server=r.server,
            name=r.name,
            currency=r.currency,
            balance=float(r.balance) if r.balance is not None else None,
            equity=float(r.equity) if r.equity is not None else None,
        )
        for r in rows
    ]


class ClaimRequest(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    server: str = Field(default="", max_length=120)


def _owned(db: Database, user_id: str, detected_id: UUID) -> DetectedAccount:
    row = db.get(DetectedAccount, str(detected_id))
    if row is None or str(row.user_id) != user_id:
        raise HTTPException(status_code=404, detail="Detected account not found")
    return row


@router.post("/detected/{detected_id}/connect", response_model=AccountRead, status_code=201)
def connect_detected(detected_id: UUID, payload: ClaimRequest, current_user: CurrentUser, db: Database):
    row = _owned(db, str(current_user.id), detected_id)
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="This account was already handled.")
    return device.claim(db, current_user, row, payload.login, payload.server)


@router.post("/detected/{detected_id}/dismiss", status_code=204)
def dismiss_detected(detected_id: UUID, current_user: CurrentUser, db: Database) -> None:
    row = _owned(db, str(current_user.id), detected_id)
    row.status = "dismissed"
    db.commit()
