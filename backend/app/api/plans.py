from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.accounts import get_owned_account
from app.api.deps import CurrentUser, Database
from app.models import PlanState, TradePlan, TradePlanVersion
from app.schemas import (
    PlanStateValue,
    TradePlanCreate,
    TradePlanList,
    TradePlanRead,
    TradePlanUpdate,
)

router = APIRouter(prefix="/plans", tags=["Trade plans"])


def get_owned_plan(db: Session, user_id: UUID, plan_id: UUID) -> TradePlan:
    plan = db.scalar(select(TradePlan).where(TradePlan.id == plan_id, TradePlan.user_id == user_id))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade plan not found")
    return plan


def add_version(db: Session, plan: TradePlan) -> None:
    latest = db.scalar(
        select(TradePlanVersion.version_number)
        .where(TradePlanVersion.plan_id == plan.id)
        .order_by(TradePlanVersion.version_number.desc())
        .limit(1)
    )
    db.add(
        TradePlanVersion(
            plan_id=plan.id,
            version_number=(latest or 0) + 1,
            snapshot={
                "symbol": plan.symbol,
                "direction": plan.direction,
                "strategy": plan.strategy,
                "thesis": plan.thesis,
                "state": plan.state.value,
                "entry_zone": plan.entry_zone,
                "stop_loss": float(plan.stop_loss) if plan.stop_loss is not None else None,
                "targets": plan.targets,
            },
        )
    )


@router.get("", response_model=TradePlanList)
def list_plans(
    current_user: CurrentUser,
    db: Database,
    state: PlanStateValue | None = None,
    account_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TradePlanList:
    query = select(TradePlan).where(TradePlan.user_id == current_user.id)
    if account_id is not None:
        query = query.where(TradePlan.account_id == str(account_id))
    if state is not None:
        query = query.where(TradePlan.state == PlanState(state.value))
    query = query.order_by(TradePlan.created_at.desc(), TradePlan.id.desc())
    items = db.scalars(query.limit(limit).offset(offset)).all()
    return TradePlanList(items=items, limit=limit, offset=offset)


@router.post("", response_model=TradePlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: TradePlanCreate,
    current_user: CurrentUser,
    db: Database,
) -> TradePlan:
    if payload.account_id is not None:
        get_owned_account(db, current_user.id, payload.account_id)
    plan = TradePlan(
        user_id=current_user.id,
        account_id=str(payload.account_id) if payload.account_id else None,
        symbol=payload.symbol,
        direction=payload.direction.value,
        strategy=payload.strategy,
        thesis=payload.thesis,
        entry_zone=payload.entry_zone,
        stop_loss=payload.stop_loss,
        targets=payload.targets,
        state=PlanState.PLANNED,
    )
    db.add(plan)
    db.flush()
    add_version(db, plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/{plan_id}", response_model=TradePlanRead)
def read_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> TradePlan:
    return get_owned_plan(db, current_user.id, plan_id)


@router.patch("/{plan_id}", response_model=TradePlanRead)
def update_plan(
    plan_id: UUID,
    payload: TradePlanUpdate,
    current_user: CurrentUser,
    db: Database,
) -> TradePlan:
    plan = get_owned_plan(db, current_user.id, plan_id)
    if plan.state != PlanState.PLANNED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only planned ideas can be edited"
        )
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one field to update",
        )
    if any(value is None for value in changes.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Plan fields cannot be null"
        )
    for field, value in changes.items():
        setattr(plan, field, value.value if hasattr(value, "value") else value)
    plan.updated_at = datetime.now(UTC)
    add_version(db, plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/{plan_id}/versions")
def list_plan_versions(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> list[dict[str, object]]:
    plan = get_owned_plan(db, current_user.id, plan_id)
    versions = db.scalars(
        select(TradePlanVersion)
        .where(TradePlanVersion.plan_id == plan.id)
        .order_by(TradePlanVersion.version_number)
    ).all()
    return [
        {
            "id": str(version.id),
            "version_number": version.version_number,
            "snapshot": version.snapshot,
            "created_at": version.created_at,
        }
        for version in versions
    ]


@router.post("/{plan_id}/versions", status_code=status.HTTP_201_CREATED)
def create_plan_version(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> dict[str, object]:
    plan = get_owned_plan(db, current_user.id, plan_id)
    add_version(db, plan)
    db.commit()
    version = db.scalar(
        select(TradePlanVersion)
        .where(TradePlanVersion.plan_id == plan.id)
        .order_by(TradePlanVersion.version_number.desc())
        .limit(1)
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save plan version",
        )
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "snapshot": version.snapshot,
        "created_at": version.created_at,
    }


@router.post("/{plan_id}/discard", response_model=TradePlanRead)
def discard_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> TradePlan:
    plan = get_owned_plan(db, current_user.id, plan_id)
    if plan.state != PlanState.PLANNED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only planned ideas can be discarded"
        )
    plan.state = PlanState.DISCARDED
    plan.updated_at = datetime.now(UTC)
    add_version(db, plan)
    db.commit()
    db.refresh(plan)
    return plan
