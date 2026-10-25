from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import Database
from app.platform_models import AccountConnection, TradingAccount
from app.services import ea, installer

router = APIRouter(prefix="/mt5/ea", tags=["MT5 Expert Advisor"])

MAX_BODY_BYTES = 2_000_000


def _authorised(account_id: UUID, secret: str, db: Database) -> tuple[TradingAccount, AccountConnection]:
    account = db.get(TradingAccount, str(account_id))
    connection = db.get(AccountConnection, str(account_id)) if account else None
    if account is None or connection is None or not ea.secret_matches(connection, secret):
        raise HTTPException(status_code=404, detail="Not found")
    return account, connection


@router.get("/{account_id}/{secret}/ea.mq5")
def download_ea(account_id: UUID, secret: str, db: Database) -> Response:
    _authorised(account_id, secret, db)
    return Response((installer.EA_DIR / "TradeIQ_Journal.mq5").read_bytes(), media_type="text/plain")


@router.get("/{account_id}/{secret}/bridge.py")
def download_bridge(account_id: UUID, secret: str, db: Database) -> Response:
    _authorised(account_id, secret, db)
    return Response((installer.EA_DIR / "bridge.py").read_bytes(), media_type="text/plain")


@router.get("/{account_id}/{secret}/installer/{os_name}")
def download_installer(account_id: UUID, secret: str, os_name: str, db: Database) -> Response:
    account, _ = _authorised(account_id, secret, db)
    if os_name not in ("mac", "windows"):
        raise HTTPException(status_code=404, detail="Unknown platform")
    url = ea.webhook_url(str(account_id), secret)
    body, filename, media = installer.render_installer(
        os_name, name=account.name, url=url, base=url, login=account.external_account_id, server=account.server_name
    )
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.post("/{account_id}/{secret}")
async def receive_ea_push(account_id: UUID, secret: str, request: Request, db: Database) -> dict[str, Any]:
    """Public webhook called by the TradeIQ Expert Advisor; authenticated by the secret in the URL."""
    account = db.get(TradingAccount, str(account_id))
    connection = db.get(AccountConnection, str(account_id)) if account else None
    if account is None or connection is None or not ea.secret_matches(connection, secret):
        raise HTTPException(status_code=403, detail="Invalid webhook")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        result = ea.ingest(account, connection, data, db)
    except PermissionError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ValueError, KeyError, TypeError) as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Invalid payload: {error}") from error
    return {"status": "ok", **result}
