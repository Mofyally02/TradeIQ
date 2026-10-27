from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.platform_models import (
    JournalTag,
    Trade,
    TradeReview,
    TradeTag,
    TradingAccount,
    UserPreference,
)

MIN_RELIABLE_SAMPLE = 30


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def get_closed_trades(
    db: Session,
    user_id: UUID,
    account_id: UUID | None,
    start: datetime | None,
    end: datetime | None,
) -> list[Trade]:
    query = select(Trade).where(
        Trade.user_id == user_id,
        Trade.outcome.in_(["win", "loss", "flat"]),
        Trade.pnl.is_not(None),
        Trade.closed_at.is_not(None),
    )
    if account_id is not None:
        query = query.where(Trade.account_id == account_id)
    if start is not None:
        query = query.where(Trade.closed_at >= start)
    if end is not None:
        query = query.where(Trade.closed_at < end)
    return list(db.scalars(query.order_by(Trade.closed_at, Trade.id)).all())


def get_recent_loss_trades(
    db: Session,
    user_id: UUID,
    account_id: UUID | None,
    candidate_trades: list[Trade],
    window_minutes: int,
) -> list[Trade]:
    if not candidate_trades:
        return []
    opened_at_values = [_as_utc(trade.opened_at) for trade in candidate_trades]
    earliest_open = min(opened_at_values)
    latest_open = max(opened_at_values)
    query = select(Trade).where(
        Trade.user_id == user_id,
        Trade.outcome == "loss",
        Trade.pnl < 0,
        Trade.closed_at >= earliest_open - timedelta(minutes=window_minutes),
        Trade.closed_at <= latest_open,
    )
    if account_id is not None:
        query = query.where(Trade.account_id == account_id)
    return list(db.scalars(query.order_by(Trade.closed_at, Trade.id)).all())


def currency_map(db: Session, user_id: UUID, trades: list[Trade]) -> dict[str, str]:
    account_ids = {trade.account_id for trade in trades if trade.account_id is not None}
    currencies: dict[str, str] = {}
    if account_ids:
        rows = db.execute(
            select(TradingAccount.id, TradingAccount.currency).where(
                TradingAccount.id.in_(account_ids), TradingAccount.user_id == user_id
            )
        ).all()
        currencies.update({str(account_id): currency for account_id, currency in rows})
    preference = db.get(UserPreference, user_id)
    default_currency = preference.currency if preference else "USD"
    currencies["__unassigned__"] = default_currency
    return currencies


def trade_currency(trade: Trade, currencies: dict[str, str]) -> str:
    return currencies.get(str(trade.account_id), currencies["__unassigned__"])


def metrics_for(
    trades: list[Trade], currencies: dict[str, str], timezone: ZoneInfo | None = None
) -> dict[str, Any]:
    count = len(trades)
    wins = [trade for trade in trades if float(trade.pnl or 0) > 0]
    losses = [trade for trade in trades if float(trade.pnl or 0) < 0]
    flats = count - len(wins) - len(losses)
    known_r = [float(trade.r_multiple) for trade in trades if trade.r_multiple is not None]
    currencies_in_sample = {trade_currency(trade, currencies) for trade in trades}
    financial_comparable = len(currencies_in_sample) <= 1
    currency = next(iter(currencies_in_sample), None) if financial_comparable else None
    gross_profit = sum(float(trade.pnl or 0) for trade in wins)
    gross_loss = abs(sum(float(trade.pnl or 0) for trade in losses))

    cumulative_r = 0.0
    peak_r = 0.0
    peak_at: datetime | None = None
    drawdown_peak_at: datetime | None = None
    drawdown_depth = 0.0
    drawdown_episodes: list[tuple[float, float | None]] = []
    current_drawdown_seconds: float | None = None
    latest_r_close: datetime | None = None
    for trade in trades:
        if trade.r_multiple is None or trade.closed_at is None:
            continue
        closed_at = _as_utc(trade.closed_at)
        latest_r_close = closed_at
        cumulative_r += float(trade.r_multiple)
        if cumulative_r >= peak_r:
            if drawdown_peak_at is not None:
                recovery_seconds = (closed_at - drawdown_peak_at).total_seconds()
                drawdown_episodes.append((drawdown_depth, recovery_seconds))
                drawdown_peak_at = None
                drawdown_depth = 0.0
            peak_r = cumulative_r
            peak_at = closed_at
        else:
            drawdown = peak_r - cumulative_r
            if drawdown_peak_at is None:
                drawdown_peak_at = peak_at or closed_at
            drawdown_depth = max(drawdown_depth, drawdown)
    if drawdown_peak_at is not None and latest_r_close is not None:
        drawdown_episodes.append((drawdown_depth, None))
        current_drawdown_seconds = max(0.0, (latest_r_close - drawdown_peak_at).total_seconds())
    max_drawdown_r = max((episode[0] for episode in drawdown_episodes), default=0.0)
    max_drawdown_recovery_seconds = None
    if max_drawdown_r:
        max_drawdown_recovery_seconds = max(
            (
                duration
                for depth, duration in drawdown_episodes
                if depth == max_drawdown_r and duration is not None
            ),
            default=None,
        )
        if drawdown_peak_at is not None and drawdown_depth == max_drawdown_r:
            max_drawdown_recovery_seconds = None

    holding_minutes = [
        (_as_utc(trade.closed_at) - _as_utc(trade.opened_at)).total_seconds() / 60
        for trade in trades
        if trade.closed_at is not None
    ]
    mae_values = [float(trade.mae_r) for trade in trades if trade.mae_r is not None]
    mfe_values = [float(trade.mfe_r) for trade in trades if trade.mfe_r is not None]
    win_r = [float(trade.r_multiple) for trade in wins if trade.r_multiple is not None]
    loss_r = [float(trade.r_multiple) for trade in losses if trade.r_multiple is not None]
    result: dict[str, Any] = {
        "trade_count": count,
        "wins": len(wins),
        "losses": len(losses),
        "flats": flats,
        "win_rate_pct": len(wins) / count * 100 if count else None,
        "profit_factor": (
            gross_profit / gross_loss if financial_comparable and gross_loss else None
        ),
        "net_pnl": (
            sum(float(trade.pnl or 0) for trade in trades) if financial_comparable else None
        ),
        "currency": currency,
        "financial_metrics_comparable": financial_comparable,
        "expectancy_r": mean(known_r) if known_r else None,
        "average_win_r": mean(win_r) if win_r else None,
        "average_loss_r": mean(loss_r) if loss_r else None,
        "r_sample_count": len(known_r),
        "r_missing_count": count - len(known_r),
        "r_sample_reliability": (
            "insufficient" if len(known_r) < MIN_RELIABLE_SAMPLE else "descriptive_only"
        ),
        "r_sample_warning": (
            f"Only {len(known_r)} trades include a recorded R-multiple; "
            f"at least {MIN_RELIABLE_SAMPLE} are suggested for descriptive comparison."
            if len(known_r) < MIN_RELIABLE_SAMPLE
            else None
        ),
        "max_drawdown_r": max_drawdown_r if known_r else None,
        "max_drawdown_recovery_seconds": max_drawdown_recovery_seconds,
        "current_drawdown_seconds": current_drawdown_seconds,
        "average_holding_minutes": mean(holding_minutes) if holding_minutes else None,
        "mae_sample_count": len(mae_values),
        "average_mae_r": mean(mae_values) if mae_values else None,
        "mfe_sample_count": len(mfe_values),
        "average_mfe_r": mean(mfe_values) if mfe_values else None,
        "sample_reliability": (
            "insufficient" if count < MIN_RELIABLE_SAMPLE else "descriptive_only"
        ),
        "sample_warning": (
            f"Only {count} closed trades; treat observed results as provisional until "
            f"at least {MIN_RELIABLE_SAMPLE} trades are available."
            if count < MIN_RELIABLE_SAMPLE
            else None
        ),
    }
    if timezone is not None:
        result["trades_by_hour"] = _bucket_counts(
            trades, lambda trade: str(_as_utc(trade.opened_at).astimezone(timezone).hour)
        )
        result["trades_by_weekday"] = _bucket_counts(
            trades,
            lambda trade: _as_utc(trade.opened_at).astimezone(timezone).strftime("%A"),
        )
    return result


def _bucket_counts(trades: list[Trade], key_for: Any) -> dict[str, int]:
    buckets: dict[str, int] = defaultdict(int)
    for trade in trades:
        buckets[key_for(trade)] += 1
    return dict(sorted(buckets.items()))


def load_reviews(db: Session, user_id: UUID, trades: list[Trade]) -> dict[str, TradeReview]:
    if not trades:
        return {}
    rows = db.scalars(
        select(TradeReview).where(
            TradeReview.user_id == user_id,
            TradeReview.trade_id.in_([trade.id for trade in trades]),
        )
    ).all()
    return {str(review.trade_id): review for review in rows}


def load_tags(db: Session, user_id: UUID, trades: list[Trade]) -> dict[str, list[str]]:
    if not trades:
        return {}
    rows = db.execute(
        select(TradeTag.trade_id, JournalTag.name)
        .join(JournalTag, JournalTag.id == TradeTag.tag_id)
        .where(
            TradeTag.trade_id.in_([trade.id for trade in trades]),
            JournalTag.user_id == user_id,
        )
        .order_by(JournalTag.name)
    ).all()
    result: dict[str, list[str]] = defaultdict(list)
    for trade_id, name in rows:
        result[str(trade_id)].append(name)
    return dict(result)


def cohort_metrics(
    trades_by_key: dict[str, list[Trade]], currencies: dict[str, str]
) -> list[dict[str, Any]]:
    results = []
    for key, trades in sorted(trades_by_key.items()):
        metrics = metrics_for(trades, currencies)
        results.append({"key": key, **metrics})
    return results


def detect_revenge_trades(
    trades: list[Trade],
    window_minutes: int,
    loss_history: list[Trade] | None = None,
) -> list[Trade]:
    losses = sorted(
        (
            (_as_utc(trade.closed_at), str(trade.id))
            for trade in (loss_history if loss_history is not None else trades)
            if trade.closed_at is not None and float(trade.pnl or 0) < 0
        ),
        key=lambda item: item[0],
    )
    opened = sorted(trades, key=lambda trade: (_as_utc(trade.opened_at), str(trade.id)))
    prior_loss_index = 0
    latest_prior_loss: datetime | None = None
    revenge: list[Trade] = []
    window_seconds = window_minutes * 60
    for trade in opened:
        opened_at = _as_utc(trade.opened_at)
        while prior_loss_index < len(losses) and losses[prior_loss_index][0] <= opened_at:
            latest_prior_loss = losses[prior_loss_index][0]
            prior_loss_index += 1
        if (
            latest_prior_loss is not None
            and 0 <= (opened_at - latest_prior_loss).total_seconds() <= window_seconds
        ):
            revenge.append(trade)
    return revenge


def verify_owned_account(db: Session, user_id: UUID, account_id: UUID) -> bool:
    return (
        db.scalar(
            select(TradingAccount.id).where(
                TradingAccount.id == account_id,
                TradingAccount.user_id == user_id,
            )
        )
        is not None
    )
