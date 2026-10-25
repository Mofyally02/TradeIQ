from datetime import UTC, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import CurrentUser, Database
from app.platform_models import RiskProfile, Trade, TradingAccount, UserPreference
from app.schemas import RiskProfileRead, RiskProfileUpdate

router = APIRouter(tags=["Risk"])


def get_daily_account_status(db: Database, user_id: UUID) -> list[dict[str, object]]:
    accounts = db.scalars(
        select(TradingAccount).where(
            TradingAccount.user_id == user_id,
            TradingAccount.archived_at.is_(None),
        )
    ).all()
    preferences = db.get(UserPreference, user_id)
    timezone = preferences.timezone if preferences else "UTC"
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=500, detail="Stored account timezone is invalid") from error
    today = datetime.now(zone).date()
    start = datetime.combine(today, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(today, time.max, tzinfo=zone).astimezone(UTC)
    result = []
    for account in accounts:
        profile = db.scalar(select(RiskProfile).where(RiskProfile.account_id == account.id))
        trades = db.scalars(
            select(Trade).where(
                Trade.user_id == user_id,
                Trade.account_id == account.id,
                Trade.closed_at >= start,
                Trade.closed_at <= end,
                Trade.outcome.in_(["win", "loss", "flat"]),
                Trade.pnl.is_not(None),
            )
        ).all()
        realized_pnl = sum(float(trade.pnl or 0) for trade in trades)
        total_trades_today = db.scalar(
            select(func.count()).select_from(Trade).where(
                Trade.user_id == user_id,
                Trade.account_id == account.id,
                Trade.opened_at >= start,
                Trade.opened_at <= end,
            )
        ) or 0
        violations = []
        if (
            profile
            and profile.max_daily_loss is not None
            and realized_pnl <= -float(profile.max_daily_loss)
        ):
            violations.append(
                {
                    "rule": "max_daily_loss",
                    "threshold": float(profile.max_daily_loss),
                    "actual": realized_pnl,
                }
            )
        if (
            profile
            and profile.max_trades_per_day is not None
            and total_trades_today > profile.max_trades_per_day
        ):
            violations.append(
                {
                    "rule": "max_trades_per_day",
                    "threshold": profile.max_trades_per_day,
                    "actual": total_trades_today,
                }
            )
        result.append(
            {
                "account_id": str(account.id),
                "account_name": account.name,
                "as_of": datetime.now(UTC),
                "timezone": timezone,
                "closed_trades_today": len(trades),
                "trade_count_today": total_trades_today,
                "realized_pnl_today": realized_pnl,
                "risk_profile_configured": profile is not None,
                "violations": violations,
            }
        )
    return result


@router.get("/risk/profiles", response_model=list[RiskProfileRead])
def list_risk_profiles(current_user: CurrentUser, db: Database) -> list[RiskProfile]:
    return db.scalars(
        select(RiskProfile)
        .where(RiskProfile.user_id == current_user.id)
        .order_by(RiskProfile.updated_at.desc())
    ).all()


@router.put("/accounts/{account_id}/risk-profile", response_model=RiskProfileRead)
def update_account_risk_profile(
    account_id: UUID,
    payload: RiskProfileUpdate,
    current_user: CurrentUser,
    db: Database,
) -> RiskProfile:
    account = db.scalar(
        select(TradingAccount).where(
            TradingAccount.id == account_id,
            TradingAccount.user_id == current_user.id,
            TradingAccount.archived_at.is_(None),
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Trading account not found")
    profile = db.scalar(select(RiskProfile).where(RiskProfile.account_id == account.id))
    if profile is None:
        profile = RiskProfile(user_id=current_user.id, account_id=account.id)
        db.add(profile)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one risk limit")
    for key, value in changes.items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/risk/status")
def risk_status(current_user: CurrentUser, db: Database) -> list[dict[str, object]]:
    return get_daily_account_status(db, current_user.id)


@router.get("/risk/violations")
def risk_violations(current_user: CurrentUser, db: Database) -> list[dict[str, object]]:
    return [
        {**item, "violations": item["violations"]}
        for item in get_daily_account_status(db, current_user.id)
        if item["violations"]
    ]
