from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, Database
from app.platform_models import DevelopmentExperiment, DevelopmentGoal, Trade
from app.schemas import (
    DevelopmentExperimentCreate,
    DevelopmentExperimentUpdate,
    DevelopmentGoalCreate,
    DevelopmentGoalUpdate,
)
from app.services.performance import currency_map, get_closed_trades, metrics_for

router = APIRouter(prefix="/development", tags=["Development goals and experiments"])

BASELINE_DAYS = 90


def _bounds(start: date, end: date | None) -> tuple[datetime, datetime | None]:
    start_at = datetime.combine(start, time.min, tzinfo=UTC)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC) if end else None
    return start_at, end_at


def _window_stats(
    db: Database, user_id: UUID, start: date, end: date | None
) -> tuple[dict[str, Any], list[Trade]]:
    start_at, end_at = _bounds(start, end)
    trades = get_closed_trades(db, user_id, None, start_at, end_at)
    metrics = metrics_for(trades, currency_map(db, user_id, trades))
    broken = sum(1 for trade in trades if trade.rule_breaks)
    metrics["rule_break_rate_pct"] = broken / len(trades) * 100 if trades else None
    return metrics, trades


def _goal_view(db: Database, user_id: UUID, goal: DevelopmentGoal) -> dict[str, Any]:
    metrics, _ = _window_stats(db, user_id, goal.start_date, None)
    current = metrics.get(goal.metric)
    count = metrics["trade_count"]
    progress = None
    if current is not None and goal.baseline_value is not None:
        span = goal.target_value - goal.baseline_value
        if span != 0:
            progress = max(0.0, min(1.0, (current - goal.baseline_value) / span))
        else:
            progress = 1.0
    reached = None
    if current is not None:
        reached = (
            current >= goal.target_value
            if goal.direction == "increase"
            else current <= goal.target_value
        )
    return {
        "id": str(goal.id),
        "title": goal.title,
        "metric": goal.metric,
        "direction": goal.direction,
        "baseline_value": goal.baseline_value,
        "baseline_sample": goal.baseline_sample,
        "target_value": goal.target_value,
        "start_date": goal.start_date.isoformat(),
        "due_date": goal.due_date.isoformat() if goal.due_date else None,
        "status": goal.status,
        "notes": goal.notes,
        "current_value": current,
        "current_sample": count,
        "progress": progress,
        "target_reached": reached,
        "sample_warning": (
            f"Only {count} closed trades since the goal started; treat progress as provisional."
            if count < 30
            else None
        ),
    }


def _experiment_view(db: Database, user_id: UUID, item: DevelopmentExperiment) -> dict[str, Any]:
    metrics, _ = _window_stats(db, user_id, item.start_date, item.end_date)
    count = metrics["trade_count"]
    return {
        "id": str(item.id),
        "goal_id": str(item.goal_id) if item.goal_id else None,
        "title": item.title,
        "hypothesis": item.hypothesis,
        "rule": item.rule,
        "start_date": item.start_date.isoformat(),
        "end_date": item.end_date.isoformat() if item.end_date else None,
        "min_trades": item.min_trades,
        "status": item.status,
        "conclusion": item.conclusion,
        "evidence": {
            "trade_count": count,
            "expectancy_r": metrics["expectancy_r"],
            "win_rate_pct": metrics["win_rate_pct"],
            "profit_factor": metrics["profit_factor"],
            "max_drawdown_r": metrics["max_drawdown_r"],
            "rule_break_rate_pct": metrics["rule_break_rate_pct"],
            "enough_trades": count >= item.min_trades,
            "caveat": (
                f"{count} of {item.min_trades} planned trades logged; "
                "results are descriptive and do not prove the rule caused any change."
            ),
        },
    }


def _owned_goal(db: Database, user_id: UUID, goal_id: UUID) -> DevelopmentGoal:
    goal = db.scalar(
        select(DevelopmentGoal).where(
            DevelopmentGoal.id == goal_id, DevelopmentGoal.user_id == user_id
        )
    )
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


def _owned_experiment(db: Database, user_id: UUID, item_id: UUID) -> DevelopmentExperiment:
    item = db.scalar(
        select(DevelopmentExperiment).where(
            DevelopmentExperiment.id == item_id, DevelopmentExperiment.user_id == user_id
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return item


@router.get("/goals")
def list_goals(current_user: CurrentUser, db: Database) -> list[dict[str, Any]]:
    goals = db.scalars(
        select(DevelopmentGoal)
        .where(DevelopmentGoal.user_id == current_user.id)
        .order_by(DevelopmentGoal.created_at.desc())
    ).all()
    return [_goal_view(db, current_user.id, goal) for goal in goals]


@router.post("/goals", status_code=201)
def create_goal(
    payload: DevelopmentGoalCreate, current_user: CurrentUser, db: Database
) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    baseline, _ = _window_stats(db, current_user.id, today - timedelta(days=BASELINE_DAYS), None)
    goal = DevelopmentGoal(
        user_id=current_user.id,
        title=payload.title,
        metric=payload.metric,
        direction=payload.direction,
        baseline_value=baseline.get(payload.metric),
        baseline_sample=baseline["trade_count"],
        target_value=payload.target_value,
        start_date=today,
        due_date=payload.due_date,
        notes=payload.notes,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _goal_view(db, current_user.id, goal)


@router.patch("/goals/{goal_id}")
def update_goal(
    goal_id: UUID, payload: DevelopmentGoalUpdate, current_user: CurrentUser, db: Database
) -> dict[str, Any]:
    goal = _owned_goal(db, current_user.id, goal_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key in {"title", "target_value", "status"}:
            continue
        setattr(goal, key, value)
    db.commit()
    db.refresh(goal)
    return _goal_view(db, current_user.id, goal)


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: UUID, current_user: CurrentUser, db: Database) -> None:
    db.delete(_owned_goal(db, current_user.id, goal_id))
    db.commit()


@router.get("/experiments")
def list_experiments(current_user: CurrentUser, db: Database) -> list[dict[str, Any]]:
    items = db.scalars(
        select(DevelopmentExperiment)
        .where(DevelopmentExperiment.user_id == current_user.id)
        .order_by(DevelopmentExperiment.created_at.desc())
    ).all()
    return [_experiment_view(db, current_user.id, item) for item in items]


@router.post("/experiments", status_code=201)
def create_experiment(
    payload: DevelopmentExperimentCreate, current_user: CurrentUser, db: Database
) -> dict[str, Any]:
    if payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    if payload.goal_id is not None:
        _owned_goal(db, current_user.id, payload.goal_id)
    item = DevelopmentExperiment(
        user_id=current_user.id,
        status="running" if payload.start_date <= datetime.now(UTC).date() else "planned",
        **payload.model_dump(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _experiment_view(db, current_user.id, item)


@router.patch("/experiments/{experiment_id}")
def update_experiment(
    experiment_id: UUID,
    payload: DevelopmentExperimentUpdate,
    current_user: CurrentUser,
    db: Database,
) -> dict[str, Any]:
    item = _owned_experiment(db, current_user.id, experiment_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key in {"title", "hypothesis", "rule", "status"}:
            continue
        setattr(item, key, value)
    if item.end_date and item.end_date < item.start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    db.commit()
    db.refresh(item)
    return _experiment_view(db, current_user.id, item)


@router.delete("/experiments/{experiment_id}", status_code=204)
def delete_experiment(experiment_id: UUID, current_user: CurrentUser, db: Database) -> None:
    db.delete(_owned_experiment(db, current_user.id, experiment_id))
    db.commit()
