from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, Database
from app.api.trades import serialize_trade
from app.platform_models import AccountSnapshot, Trade, TradeReview, TradingAccount
from app.schemas import AnalyticsGroup, DashboardSummary, EquityPoint, TradeList

router = APIRouter(tags=["Dashboard and analytics"])


def closed_trade_query(user_id: UUID):
    return select(Trade).where(
        Trade.user_id == user_id,
        Trade.outcome.in_(["win", "loss", "flat"]),
        Trade.pnl.is_not(None),
    )


def _summary(
    db: Database, user_id: UUID, start: datetime | None = None, end: datetime | None = None
):
    query = closed_trade_query(user_id)
    if start:
        query = query.where(Trade.closed_at >= start)
    if end:
        query = query.where(Trade.closed_at < end)
    closed = db.scalars(query).all()
    wins = [trade for trade in closed if float(trade.pnl or 0) > 0]
    losses = [trade for trade in closed if float(trade.pnl or 0) < 0]
    gross_profit = sum(float(trade.pnl or 0) for trade in wins)
    gross_loss = abs(sum(float(trade.pnl or 0) for trade in losses))
    r_values = [float(trade.r_multiple) for trade in closed if trade.r_multiple is not None]
    open_query = (
        select(func.count())
        .select_from(Trade)
        .where(Trade.user_id == user_id, Trade.outcome == "open")
    )
    if start:
        open_query = open_query.where(Trade.opened_at >= start)
    if end:
        open_query = open_query.where(Trade.opened_at < end)
    pending_review_query = (
        select(func.count())
        .select_from(Trade)
        .outerjoin(TradeReview, TradeReview.trade_id == Trade.id)
        .where(
            Trade.user_id == user_id,
            Trade.outcome.in_(["win", "loss", "flat"]),
            TradeReview.id.is_(None),
        )
    )
    if start:
        pending_review_query = pending_review_query.where(Trade.closed_at >= start)
    if end:
        pending_review_query = pending_review_query.where(Trade.closed_at < end)
    total_pnl = sum(float(trade.pnl or 0) for trade in closed)
    return {
        "closed_trade_count": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "net_pnl": total_pnl,
        "win_rate": len(wins) / len(closed) * 100 if closed else 0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "average_r": sum(r_values) / len(r_values) if r_values else None,
        "open_trade_count": db.scalar(open_query) or 0,
        "pending_review_count": db.scalar(pending_review_query) or 0,
    }


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(current_user: CurrentUser, db: Database) -> dict[str, object]:
    return _summary(db, current_user.id)


@router.get("/dashboard/equity-curve", response_model=list[EquityPoint])
def dashboard_equity_curve(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[dict[str, object]]:
    query = (
        select(AccountSnapshot)
        .join(TradingAccount, TradingAccount.id == AccountSnapshot.account_id)
        .where(TradingAccount.user_id == current_user.id)
    )
    if account_id:
        query = query.where(AccountSnapshot.account_id == account_id)
    snapshots = db.scalars(
        query.order_by(AccountSnapshot.observed_at, AccountSnapshot.id).limit(limit)
    ).all()
    return [
        {
            "observed_at": item.observed_at,
            "balance": float(item.balance),
            "equity": float(item.equity),
            "source": item.source,
        }
        for item in snapshots
    ]


@router.get("/dashboard/recent-trades", response_model=TradeList)
def dashboard_recent_trades(
    current_user: CurrentUser,
    db: Database,
    limit: int = Query(default=10, ge=1, le=100),
) -> TradeList:
    query = select(Trade).where(Trade.user_id == current_user.id)
    rows = db.scalars(query.order_by(Trade.opened_at.desc()).limit(limit)).all()
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    return TradeList(
        items=[serialize_trade(db, trade) for trade in rows],
        limit=limit,
        offset=0,
        total=total,
    )


@router.get("/analytics/performance", response_model=DashboardSummary)
def analytics_performance(
    current_user: CurrentUser,
    db: Database,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str = Query(default="UTC", max_length=64),
) -> dict[str, object]:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=422, detail="Timezone is not recognized") from error
    start = (
        datetime.combine(start_date, time.min, tzinfo=zone).astimezone(UTC) if start_date else None
    )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not be after end_date")
    end = (
        datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
        if end_date
        else None
    )
    return _summary(db, current_user.id, start, end)


@router.get("/analytics/by-strategy", response_model=list[AnalyticsGroup])
def analytics_by_strategy(current_user: CurrentUser, db: Database) -> list[dict[str, object]]:
    rows = db.execute(
        select(Trade.strategy, func.count(Trade.id), func.sum(Trade.pnl))
        .where(
            Trade.user_id == current_user.id,
            Trade.outcome.in_(["win", "loss", "flat"]),
            Trade.pnl.is_not(None),
        )
        .group_by(Trade.strategy)
        .order_by(Trade.strategy)
    ).all()
    output = []
    for strategy, count, net in rows:
        wins = (
            db.scalar(
                select(func.count())
                .select_from(Trade)
                .where(
                    Trade.user_id == current_user.id,
                    Trade.strategy == strategy,
                    Trade.outcome.in_(["win", "loss", "flat"]),
                    Trade.pnl > 0,
                )
            )
            or 0
        )
        output.append(
            {
                "key": strategy,
                "trade_count": count,
                "net_pnl": float(net or 0),
                "win_rate": wins / count * 100 if count else 0,
            }
        )
    return output


@router.get("/analytics/by-session", response_model=list[AnalyticsGroup])
def analytics_by_session(current_user: CurrentUser, db: Database) -> list[dict[str, object]]:
    trades = db.scalars(closed_trade_query(current_user.id).order_by(Trade.opened_at)).all()
    buckets: dict[str, list[Trade]] = {}
    for trade in trades:
        hour = trade.opened_at.hour
        session = (
            "Asia" if hour < 7 else "London" if hour < 12 else "New York" if hour < 17 else "Other"
        )
        buckets.setdefault(session, []).append(trade)
    return [
        {
            "key": key,
            "trade_count": len(rows),
            "net_pnl": sum(float(row.pnl or 0) for row in rows),
            "win_rate": sum(1 for row in rows if float(row.pnl or 0) > 0) / len(rows) * 100,
        }
        for key, rows in sorted(buckets.items())
    ]


@router.get("/analytics/risk")
def analytics_risk(current_user: CurrentUser, db: Database) -> dict[str, object]:
    summary = _summary(db, current_user.id)
    profiles = db.execute(
        select(func.count())
        .select_from(TradingAccount)
        .where(TradingAccount.user_id == current_user.id)
    ).scalar_one()
    return {
        "closed_trade_count": summary["closed_trade_count"],
        "average_r": summary["average_r"],
        "account_count": profiles,
        "definition": "Descriptive only; see /api/v1/risk/status for configured limits.",
    }
