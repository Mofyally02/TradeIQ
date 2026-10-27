from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, Database
from app.platform_models import (
    AccountSnapshot,
    MT5Deal,
    MT5Order,
    PerformanceRoadmap,
    Trade,
    TradeEvent,
    TradingAccount,
    UserPreference,
)
from app.schemas import PerformanceRoadmapProgressUpdate
from app.services.performance import (
    cohort_metrics,
    currency_map,
    detect_revenge_trades,
    get_closed_trades,
    get_recent_loss_trades,
    load_reviews,
    load_tags,
    metrics_for,
    verify_owned_account,
)

router = APIRouter(prefix="/performance", tags=["Performance intelligence"])


def _date_window(
    start_date: date | None, end_date: date | None, timezone: str
) -> tuple[datetime | None, datetime | None, ZoneInfo]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not be after end_date")
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=422, detail="Timezone is not recognized") from error
    start = (
        datetime.combine(start_date, time.min, tzinfo=zone).astimezone(UTC) if start_date else None
    )
    end = (
        datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
        if end_date
        else None
    )
    return start, end, zone


def _load_data(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None,
    start_date: date | None,
    end_date: date | None,
    timezone: str | None,
) -> tuple[list[Trade], dict[str, str], dict[str, Any], dict[str, list[str]], ZoneInfo]:
    if account_id is not None and not verify_owned_account(db, current_user.id, account_id):
        raise HTTPException(status_code=404, detail="Trading account not found")
    preference = db.get(UserPreference, current_user.id)
    selected_timezone = timezone or (preference.timezone if preference else "UTC")
    start, end, zone = _date_window(start_date, end_date, selected_timezone)
    trades = get_closed_trades(db, current_user.id, account_id, start, end)

    currencies = currency_map(db, current_user.id, trades)
    reviews = load_reviews(db, current_user.id, trades)
    tags = load_tags(db, current_user.id, trades)
    return trades, currencies, reviews, tags, zone


@router.get("/edge-snapshot")
def edge_snapshot(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    trades, currencies, _, _, zone = _load_data(
        current_user, db, account_id, start_date, end_date, timezone
    )
    return {
        "scope": {
            "account_id": str(account_id) if account_id else None,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": str(zone),
        },
        "metrics": metrics_for(trades, currencies, zone),
        "metric_definitions": {
            "expectancy_r": (
                "Arithmetic mean of recorded R-multiples; trades without R are excluded."
            ),
            "profit_factor": (
                "Gross positive realized P&L divided by absolute gross negative realized P&L."
            ),
            "max_drawdown_r": (
                "Largest peak-to-trough decline in cumulative recorded R-multiples."
            ),
            "average_mae_r": (
                "Mean recorded maximum adverse excursion in R; no path is inferred from prices."
            ),
            "average_mfe_r": (
                "Mean recorded maximum favorable excursion in R; no path is inferred from prices."
            ),
        },
    }


def _breakdown(
    current_user: CurrentUser,
    db: Database,
    dimension: Literal["strategy", "setup"],
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    trades, currencies, _, _, zone = _load_data(
        current_user, db, account_id, start_date, end_date, timezone
    )
    grouped: dict[str, list[Trade]] = {}
    for trade in trades:
        value = getattr(trade, dimension)
        key = value.strip() if isinstance(value, str) and value.strip() else "Unspecified"
        grouped.setdefault(key, []).append(trade)
    results = cohort_metrics(grouped, currencies)
    results.sort(
        key=lambda item: (
            item["expectancy_r"] is None,
            -(item["expectancy_r"] or 0),
            item["key"].casefold(),
        )
    )
    qualified = [
        item
        for item in results
        if item["r_sample_count"] >= 30 and item["expectancy_r"] is not None
    ]
    return {
        "strategies": results,
        "setups": results,
        "top_observed_strategy": qualified[0]["key"] if qualified else None,
        "top_observed_setup": qualified[0]["key"] if qualified else None,
        "ranking_note": (
            "Rankings are descriptive and based only on this user's closed trades. "
            "A group is highlighted only with at least 30 recorded R-multiples."
        ),
        "timezone": str(zone),
    }


@router.get("/strategies")
def strategy_analysis(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    result = _breakdown(current_user, db, "strategy", account_id, start_date, end_date, timezone)
    return {
        "strategies": result["strategies"],
        "top_observed_strategy": result["top_observed_strategy"],
        "ranking_note": result["ranking_note"],
        "timezone": result["timezone"],
    }


@router.get("/setups")
def setup_analysis(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    result = _breakdown(current_user, db, "setup", account_id, start_date, end_date, timezone)
    return {
        "setups": result["setups"],
        "top_observed_setup": result["top_observed_setup"],
        "ranking_note": result["ranking_note"],
        "timezone": result["timezone"],
    }


@router.get("/time")
def time_analysis(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    trades, currencies, _, _, zone = _load_data(
        current_user, db, account_id, start_date, end_date, timezone
    )
    by_hour: dict[str, list[Trade]] = {}
    by_weekday: dict[str, list[Trade]] = {}
    for trade in trades:
        opened_at = trade.opened_at
        if opened_at.tzinfo is None or opened_at.utcoffset() is None:
            opened_at = opened_at.replace(tzinfo=UTC)
        local_time = opened_at.astimezone(zone)
        by_hour.setdefault(f"{local_time.hour:02}", []).append(trade)
        by_weekday.setdefault(local_time.strftime("%A"), []).append(trade)
    return {
        "timezone": str(zone),
        "by_hour": cohort_metrics(by_hour, currencies),
        "by_weekday": cohort_metrics(by_weekday, currencies),
        "interpretation_limit": (
            "Hours and weekdays use the selected user timezone and describe this user's "
            "historical trade outcomes; they are not evidence that a time window causes edge."
        ),
    }


@router.get("/behavior")
def behavior_analysis(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = Query(default=None, max_length=64),
    revenge_window_minutes: int = Query(default=60, ge=1, le=1440),
) -> dict[str, Any]:
    trades, currencies, reviews, tags, zone = _load_data(
        current_user, db, account_id, start_date, end_date, timezone
    )

    by_emotion: dict[str, list[Trade]] = {}
    by_rule_break: dict[str, list[Trade]] = {}
    by_confluence: dict[str, list[Trade]] = {}
    by_tag: dict[str, list[Trade]] = {}
    by_adherence: dict[str, list[Trade]] = {}
    for trade in trades:
        trade_id = str(trade.id)
        if trade.emotional_state:
            by_emotion.setdefault(trade.emotional_state, []).append(trade)
        for rule_break in trade.rule_breaks or []:
            by_rule_break.setdefault(rule_break, []).append(trade)
        for confluence in trade.confluences or []:
            by_confluence.setdefault(confluence, []).append(trade)
        for tag in tags.get(trade_id, []):
            by_tag.setdefault(tag, []).append(trade)
        review = reviews.get(trade_id)
        if review is not None:
            by_adherence.setdefault(review.plan_adherence, []).append(trade)

    loss_history = get_recent_loss_trades(
        db, current_user.id, account_id, trades, revenge_window_minutes
    )
    revenge_trades = detect_revenge_trades(
        trades, revenge_window_minutes, loss_history
    )
    clean_trades = [trade for trade in trades if trade not in revenge_trades]
    revenge_group = {
        "window_minutes": revenge_window_minutes,
        "trade_count": len(revenge_trades),
        "metrics": metrics_for(revenge_trades, currencies),
        "comparison_without_flag": metrics_for(clean_trades, currencies),
        "definition": (
            "A trade opened within the selected window after a prior closed losing trade. "
            "This is a timing flag, not a diagnosis of intent."
        ),
    }
    return {
        "timezone": str(zone),
        "revenge_timing": revenge_group,
        "plan_adherence": cohort_metrics(by_adherence, currencies),
        "emotional_state": cohort_metrics(by_emotion, currencies),
        "recorded_rule_breaks": cohort_metrics(by_rule_break, currencies),
        "recorded_confluences": cohort_metrics(by_confluence, currencies),
        "user_tags": cohort_metrics(by_tag, currencies),
        "interpretation_limit": (
            "Cohort differences are associations in the user's records. They do not show "
            "that an emotion, tag, or rule break caused an outcome. Net P&L and profit factor "
            "are omitted when a cohort mixes account currencies."
        ),
    }


REPORT_FIELDS = (
    "trade_count",
    "win_rate_pct",
    "expectancy_r",
    "profit_factor",
    "net_pnl",
    "average_win_r",
    "average_loss_r",
    "max_drawdown_r",
)


def _strategy_groups(trades: list[Trade], currencies: dict[str, str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Trade]] = {}
    for trade in trades:
        key = trade.strategy.strip() if trade.strategy and trade.strategy.strip() else "Unspecified"
        grouped.setdefault(key, []).append(trade)
    return cohort_metrics(grouped, currencies)


@router.get("/report")
def performance_report(
    current_user: CurrentUser,
    db: Database,
    start_date: date,
    end_date: date,
    account_id: UUID | None = None,
    timezone: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    """Period report with an equal-length prior period for comparison."""
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not be after end_date")
    span = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=span - 1)
    trades, currencies, _, _, zone = _load_data(
        current_user, db, account_id, start_date, end_date, timezone
    )
    prior, prior_currencies, _, _, _ = _load_data(
        current_user, db, account_id, previous_start, previous_end, timezone
    )
    current_metrics = metrics_for(trades, currencies)
    prior_metrics = metrics_for(prior, prior_currencies)
    comparison = []
    for field in REPORT_FIELDS:
        now, before = current_metrics.get(field), prior_metrics.get(field)
        comparison.append(
            {
                "metric": field,
                "current": now,
                "previous": before,
                "change": (
                    now - before if isinstance(now, int | float) and isinstance(before, int | float)
                    else None
                ),
            }
        )
    return {
        "generated_at": datetime.now(UTC),
        "scope": {
            "account_id": str(account_id) if account_id else None,
            "timezone": str(zone),
            "current_period": {"start_date": start_date, "end_date": end_date},
            "previous_period": {"start_date": previous_start, "end_date": previous_end},
        },
        "current": current_metrics,
        "previous": prior_metrics,
        "comparison": comparison,
        "strategies": _strategy_groups(trades, currencies),
        "limitations": [
            "Descriptive statistics from this user's closed trades only; not financial advice.",
            "Changes between periods can reflect small samples rather than real improvement.",
            "Metrics that need R-multiples exclude trades without a recorded R.",
        ],
    }


@router.get("/roadmap")
def performance_roadmap(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    trades, currencies, _, _, zone = _load_data(
        current_user, db, account_id, start_date, end_date, timezone
    )
    return _build_roadmap(trades, currencies, account_id, start_date, end_date, zone)


def _build_roadmap(
    trades: list[Trade],
    currencies: dict[str, str],
    account_id: UUID | None,
    start_date: date | None,
    end_date: date | None,
    zone: ZoneInfo,
) -> dict[str, Any]:
    metrics = metrics_for(trades, currencies)
    actions: list[dict[str, Any]] = []
    if metrics["trade_count"] < 30:
        actions.append(
            {
                "priority": 1,
                "focus": "Build a decision-grade sample",
                "recommendation": (
                    "Keep logging the strategy, planned risk, and outcome consistently; "
                    "do not promote or retire a setup based on this small sample."
                ),
                "evidence": {
                    "closed_trades": metrics["trade_count"],
                    "suggested_minimum_for_descriptive_comparison": 30,
                },
                "confidence": "low",
            }
        )
    if metrics["trade_count"] and metrics["r_missing_count"] / metrics["trade_count"] >= 0.25:
        actions.append(
            {
                "priority": 2,
                "focus": "Improve risk-normalized capture",
                "recommendation": (
                    "Record a verified R-multiple for each closed trade. P&L alone cannot "
                    "fairly compare different position sizes or account balances."
                ),
                "evidence": {
                    "trades_without_r": metrics["r_missing_count"],
                    "closed_trades": metrics["trade_count"],
                },
                "confidence": "high",
            }
        )
    rule_cohorts: dict[str, list[Trade]] = {}
    for trade in trades:
        for label in trade.rule_breaks or []:
            rule_cohorts.setdefault(label, []).append(trade)
    negative_breaks = [
        (label, cohort)
        for label, cohort in rule_cohorts.items()
        if len(cohort) >= 5
        and metrics_for(cohort, currencies)["expectancy_r"] is not None
        and metrics_for(cohort, currencies)["expectancy_r"] < 0
    ]
    if negative_breaks and len(actions) < 3:
        label, cohort = max(negative_breaks, key=lambda item: len(item[1]))
        actions.append(
            {
                "priority": len(actions) + 1,
                "focus": f"Review rule-break pattern: {label}",
                "recommendation": (
                    "Compare these trades with your plan in the next review. The recorded "
                    "negative expectancy is an association, not a causal estimate "
                    "or recoverable loss."
                ),
                "evidence": {
                    "tagged_trades": len(cohort),
                    "observed_expectancy_r": metrics_for(cohort, currencies)["expectancy_r"],
                },
                "confidence": "moderate",
            }
        )
    if not actions:
        actions.append(
            {
                "priority": 1,
                "focus": "Keep validating the observed edge",
                "recommendation": (
                    "Review the strategy and behavior cohorts regularly, and log excursions "
                    "and journal context when available. The roadmap does not issue trade signals."
                ),
                "evidence": {
                    "closed_trades": metrics["trade_count"],
                    "recorded_mae": metrics["mae_sample_count"],
                    "recorded_mfe": metrics["mfe_sample_count"],
                },
                "confidence": "descriptive",
            }
        )
    return {
        "generated_at": datetime.now(UTC),
        "scope": {
            "account_id": str(account_id) if account_id else None,
            "start_date": start_date,
            "end_date": end_date,
            "timezone": str(zone),
        },
        "current_focus_areas": actions[:3],
        "limitations": [
            "Recommendations summarize this user's records; they are not financial advice.",
            "Small or incomplete samples can be misleading; no causal claims are made.",
            (
                "Position sizing is not inferred from lots and stop distance without "
                "broker-specific contract specifications and verified account equity."
            ),
            "No model provider receives this user's trade or journal data.",
        ],
    }


@router.post("/roadmaps", status_code=201)
def save_performance_roadmap(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    timezone: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    trades, currencies, _, _, zone = _load_data(
        current_user, db, account_id, start_date, end_date, timezone
    )
    roadmap = _build_roadmap(trades, currencies, account_id, start_date, end_date, zone)
    saved_scope = {
        **roadmap["scope"],
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    }
    saved = PerformanceRoadmap(
        user_id=current_user.id,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        trade_count=len(trades),
        metrics={
            "scope": saved_scope,
            "performance": metrics_for(trades, currencies),
        },
        recommendations=roadmap["current_focus_areas"],
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return {
        "id": str(saved.id),
        "scope": roadmap["scope"],
        "metrics": saved.metrics,
        "recommendations": saved.recommendations,
        "trade_count": saved.trade_count,
        "progress_status": saved.progress_status,
        "progress_notes": saved.progress_notes,
        "generated_at": saved.generated_at,
    }


@router.get("/roadmaps")
def list_performance_roadmaps(
    current_user: CurrentUser,
    db: Database,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(PerformanceRoadmap)
        .where(PerformanceRoadmap.user_id == current_user.id)
        .order_by(PerformanceRoadmap.generated_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": str(row.id),
            "account_id": str(row.account_id) if row.account_id else None,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "trade_count": row.trade_count,
            "metrics": row.metrics,
            "recommendations": row.recommendations,
            "progress_status": row.progress_status,
            "progress_notes": row.progress_notes,
            "generated_at": row.generated_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


@router.patch("/roadmaps/{roadmap_id}")
def update_performance_roadmap_progress(
    roadmap_id: UUID,
    payload: PerformanceRoadmapProgressUpdate,
    current_user: CurrentUser,
    db: Database,
) -> dict[str, Any]:
    saved = db.scalar(
        select(PerformanceRoadmap).where(
            PerformanceRoadmap.id == roadmap_id,
            PerformanceRoadmap.user_id == current_user.id,
        )
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="Performance roadmap not found")
    saved.progress_status = payload.progress_status
    saved.progress_notes = payload.progress_notes
    saved.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(saved)
    return {
        "id": str(saved.id),
        "progress_status": saved.progress_status,
        "progress_notes": saved.progress_notes,
        "updated_at": saved.updated_at,
    }


@router.get("/equity-history")
def equity_history(
    current_user: CurrentUser,
    db: Database,
    account_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    max_points: int = Query(default=500, ge=10, le=5000),
) -> dict[str, Any]:
    if account_id is not None and not verify_owned_account(db, current_user.id, account_id):
        raise HTTPException(status_code=404, detail="Trading account not found")
    start, end, _ = _date_window(start_date, end_date, "UTC")
    accounts = db.scalars(
        select(TradingAccount).where(
            TradingAccount.user_id == current_user.id,
            *([TradingAccount.id == account_id] if account_id else []),
        )
    ).all()
    series = []
    for account in accounts:
        query = select(AccountSnapshot).where(AccountSnapshot.account_id == account.id)
        if start:
            query = query.where(AccountSnapshot.observed_at >= start)
        if end:
            query = query.where(AccountSnapshot.observed_at < end)
        rows = list(db.scalars(query.order_by(AccountSnapshot.observed_at)).all())
        if not rows:
            continue
        step = max(1, -(-len(rows) // max_points))
        sampled = rows[::step]
        if sampled[-1] is not rows[-1]:
            sampled.append(rows[-1])
        peak = 0.0
        max_drawdown_pct = 0.0
        full_peak = 0.0
        for row in rows:
            equity = float(row.equity)
            full_peak = max(full_peak, equity)
            if full_peak > 0:
                max_drawdown_pct = max(max_drawdown_pct, (full_peak - equity) / full_peak * 100)
        points = []
        for row in sampled:
            equity = float(row.equity)
            peak = max(peak, equity)
            points.append(
                {
                    "observed_at": _as_iso(row.observed_at),
                    "balance": float(row.balance),
                    "equity": equity,
                    "drawdown_pct": (equity - peak) / peak * 100 if peak > 0 else 0.0,
                }
            )
        series.append(
            {
                "account_id": str(account.id),
                "account_name": account.name,
                "currency": account.currency,
                "snapshot_count": len(rows),
                "max_drawdown_pct": max_drawdown_pct,
                "current_drawdown_pct": points[-1]["drawdown_pct"],
                "points": points,
            }
        )
    return {
        "series": series,
        "limitations": [
            "Built from terminal snapshots (balance/equity) your connected accounts have reported.",
            "Accounts are never merged because currencies and balances are not comparable.",
        ],
    }


def _as_iso(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


@router.get("/execution-timeline/{trade_id}")
def execution_timeline(trade_id: UUID, current_user: CurrentUser, db: Database) -> dict[str, Any]:
    trade = db.scalar(
        select(Trade).where(Trade.id == str(trade_id), Trade.user_id == current_user.id)
    )
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    events: list[dict[str, Any]] = []
    for event in db.scalars(
        select(TradeEvent).where(TradeEvent.trade_id == trade.id).order_by(TradeEvent.occurred_at)
    ).all():
        events.append(
            {
                "kind": "event",
                "label": event.event_type,
                "source": event.source,
                "at": _as_iso(event.occurred_at),
                "detail": event.payload or {},
            }
        )
    if trade.account_id and trade.external_id:
        deals = db.scalars(
            select(MT5Deal)
            .where(
                MT5Deal.account_id == trade.account_id,
                MT5Deal.position_identifier == trade.external_id,
            )
            .order_by(MT5Deal.occurred_at)
        ).all()
        order_ids = {deal.external_order_id for deal in deals if deal.external_order_id}
        orders = (
            db.scalars(
                select(MT5Order).where(
                    MT5Order.account_id == trade.account_id,
                    MT5Order.external_order_id.in_(order_ids),
                )
            ).all()
            if order_ids
            else []
        )
        for order in orders:
            events.append(
                {
                    "kind": "order",
                    "label": f"{order.order_type} · {order.state}",
                    "source": order.source,
                    "at": _as_iso(order.occurred_at),
                    "detail": {
                        "volume": float(order.volume),
                        "price": float(order.price) if order.price is not None else None,
                        "stop_loss": (
                            float(order.stop_loss) if order.stop_loss is not None else None
                        ),
                        "take_profit": float(order.take_profit)
                        if order.take_profit is not None
                        else None,
                    },
                }
            )
        for deal in deals:
            events.append(
                {
                    "kind": "deal",
                    "label": f"{deal.entry_type} {deal.direction}",
                    "source": deal.source,
                    "at": _as_iso(deal.occurred_at),
                    "detail": {
                        "volume": float(deal.volume),
                        "price": float(deal.price),
                        "pnl": float(deal.pnl) if deal.pnl is not None else None,
                        "commission": (
                            float(deal.commission) if deal.commission is not None else None
                        ),
                        "swap": float(deal.swap) if deal.swap is not None else None,
                    },
                }
            )
    events.sort(key=lambda item: item["at"])
    return {
        "trade_id": str(trade.id),
        "planned": {
            "entry_price": float(trade.entry_price) if trade.entry_price is not None else None,
            "stop_loss": float(trade.stop_loss) if trade.stop_loss is not None else None,
            "take_profit": float(trade.take_profit) if trade.take_profit is not None else None,
        },
        "events": events,
        "has_terminal_data": any(item["kind"] != "event" for item in events),
    }
