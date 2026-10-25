import hashlib
import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, Database
from app.platform_models import (
    AuditLog,
    IntegrationCredential,
    Trade,
    TradeAlertLink,
    TradingViewAlert,
)
from app.schemas import AlertMatch, AlertRead, TradingViewWebhook

router = APIRouter(tags=["TradingView"])


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.get("/integrations/tradingview/token")
def tradingview_token_status(
    current_user: CurrentUser,
    db: Database,
) -> dict[str, bool]:
    credential = db.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.user_id == current_user.id,
            IntegrationCredential.integration_type == "tradingview",
        )
    )
    return {"configured": credential is not None and credential.revoked_at is None}


@router.post("/integrations/tradingview/token")
def rotate_tradingview_token(
    current_user: CurrentUser,
    db: Database,
    response: Response,
) -> dict[str, str]:
    token = secrets.token_urlsafe(48)
    credential = db.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.user_id == current_user.id,
            IntegrationCredential.integration_type == "tradingview",
        )
    )
    if credential is None:
        credential = IntegrationCredential(
            user_id=current_user.id,
            integration_type="tradingview",
            token_hash=token_digest(token),
        )
        db.add(credential)
    else:
        credential.token_hash = token_digest(token)
        credential.created_at = datetime.now(UTC)
        credential.revoked_at = None
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="integration.tradingview_token_rotated",
            entity_type="integration_credential",
            entity_id=str(credential.id) if credential.id else None,
            source="user",
        )
    )
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {
        "webhook_token": token,
        "webhook_path": "/api/v1/webhooks/tradingview",
    }


@router.delete("/integrations/tradingview/token", status_code=status.HTTP_204_NO_CONTENT)
def revoke_tradingview_token(current_user: CurrentUser, db: Database) -> Response:
    credential = db.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.user_id == current_user.id,
            IntegrationCredential.integration_type == "tradingview",
        )
    )
    if credential is not None:
        credential.revoked_at = datetime.now(UTC)
        db.add(
            AuditLog(
                user_id=current_user.id,
                action="integration.tradingview_token_revoked",
                entity_type="integration_credential",
                entity_id=str(credential.id),
                source="user",
            )
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/webhooks/tradingview",
    response_model=AlertRead,
    status_code=status.HTTP_201_CREATED,
)
def receive_tradingview_alert(
    payload: TradingViewWebhook,
    db: Database,
) -> TradingViewAlert:
    credential = db.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.token_hash == token_digest(payload.webhook_token),
            IntegrationCredential.integration_type == "tradingview",
            IntegrationCredential.revoked_at.is_(None),
        )
    )
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )
    serialized_payload = payload.model_dump(exclude_none=True)
    serialized_payload.pop("alert_id", None)
    explicit_id = payload.alert_id
    alert_id = (
        explicit_id.strip()
        if explicit_id
        else hashlib.sha256(
            json.dumps(serialized_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )
    existing = db.scalar(
        select(TradingViewAlert).where(
            TradingViewAlert.source == "tradingview",
            TradingViewAlert.external_alert_id == alert_id,
        )
    )
    if existing:
        if existing.user_id != credential.user_id:
            raise HTTPException(status_code=409, detail="Alert ID is already in use")
        return existing
    alert = TradingViewAlert(
        user_id=credential.user_id,
        source="tradingview",
        external_alert_id=alert_id,
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        payload=serialized_payload,
        processing_status="received",
        received_at=datetime.now(UTC),
    )
    db.add(alert)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        existing = db.scalar(
            select(TradingViewAlert).where(
                TradingViewAlert.source == "tradingview",
                TradingViewAlert.external_alert_id == alert_id,
            )
        )
        if existing is None or existing.user_id != credential.user_id:
            raise HTTPException(status_code=409, detail="Alert ID is already in use") from error
        return existing
    db.refresh(alert)
    return alert


@router.get("/alerts", response_model=list[AlertRead])
def list_alerts(
    current_user: CurrentUser,
    db: Database,
    limit: int = 50,
) -> list[TradingViewAlert]:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    return db.scalars(
        select(TradingViewAlert)
        .where(TradingViewAlert.user_id == current_user.id)
        .order_by(TradingViewAlert.received_at.desc())
        .limit(limit)
    ).all()


@router.post("/alerts/{alert_id}/match", status_code=status.HTTP_201_CREATED)
def match_alert(
    alert_id: UUID,
    payload: AlertMatch,
    current_user: CurrentUser,
    db: Database,
) -> dict[str, str]:
    alert = db.scalar(
        select(TradingViewAlert).where(
            TradingViewAlert.id == alert_id,
            TradingViewAlert.user_id == current_user.id,
        )
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    trade = db.scalar(
        select(Trade).where(Trade.id == payload.trade_id, Trade.user_id == current_user.id)
    )
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    link = db.scalar(
        select(TradeAlertLink).where(
            TradeAlertLink.alert_id == alert.id,
            TradeAlertLink.trade_id == trade.id,
        )
    )
    if link is None:
        db.add(
            TradeAlertLink(
                alert_id=alert.id,
                trade_id=trade.id,
                user_id=current_user.id,
                matched_by="user",
            )
        )
    alert.processing_status = "matched"
    db.commit()
    return {"alert_id": str(alert.id), "trade_id": str(trade.id), "status": "matched"}


@router.post("/alerts/{alert_id}/dismiss", response_model=AlertRead)
def dismiss_alert(
    alert_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> TradingViewAlert:
    alert = db.scalar(
        select(TradingViewAlert).where(
            TradingViewAlert.id == alert_id,
            TradingViewAlert.user_id == current_user.id,
        )
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.processing_status == "matched":
        raise HTTPException(status_code=409, detail="A matched alert cannot be dismissed")
    alert.processing_status = "dismissed"
    alert.dismissed_at = datetime.now(UTC)
    db.commit()
    db.refresh(alert)
    return alert
