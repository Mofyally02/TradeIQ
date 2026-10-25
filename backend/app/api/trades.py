import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import exists, func, select

from app.api.deps import CurrentUser, Database
from app.models import (
    PlanState,
    TradePlan,
)
from app.platform_models import (
    AuditLog,
    JournalTag,
    MT5Deal,
    MT5Position,
    Trade,
    TradeEvent,
    TradeJournalSection,
    TradeReview,
    TradeTag,
    TradingAccount,
)
from app.schemas import (
    ReviewCreate,
    ReviewRead,
    TradeCreate,
    TradeEventRead,
    TradeJournalSectionRead,
    TradeJournalSectionUpdate,
    TradeList,
    TradeOutcomeValue,
    TradeRead,
    TradeUpdate,
)

router = APIRouter(prefix="/trades", tags=["Trades"])


def get_owned_trade(db: Database, user_id: UUID, trade_id: UUID) -> Trade:
    trade = db.scalar(select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id))
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


def serialize_trade(db: Database, trade: Trade) -> TradeRead:
    tags = db.scalars(
        select(JournalTag.name)
        .join(TradeTag, TradeTag.tag_id == JournalTag.id)
        .where(TradeTag.trade_id == trade.id)
        .order_by(JournalTag.name)
    ).all()
    position = None
    deal_totals = {"gross_pnl": 0.0, "commission": 0.0, "swap": 0.0}
    if trade.source == "mt5" and trade.account_id and trade.external_id:
        position = db.scalar(
            select(MT5Position).where(
                MT5Position.account_id == trade.account_id,
                MT5Position.external_position_id == trade.external_id,
                MT5Position.state == "open",
            )
        )
        totals = db.execute(
            select(
                func.coalesce(func.sum(MT5Deal.pnl), 0),
                func.coalesce(func.sum(MT5Deal.commission), 0),
                func.coalesce(func.sum(MT5Deal.swap), 0),
            ).where(
                MT5Deal.account_id == trade.account_id,
                MT5Deal.position_identifier == trade.external_id,
            )
        ).one()
        deal_totals = {
            "gross_pnl": float(totals[0]),
            "commission": float(totals[1]),
            "swap": float(totals[2]),
        }
    return TradeRead(
        id=trade.id,
        account_id=trade.account_id,
        plan_id=trade.plan_id,
        symbol=trade.symbol,
        direction=trade.direction,
        strategy=trade.strategy,
        outcome=trade.outcome,
        pnl=float(trade.pnl) if trade.pnl is not None else None,
        r_multiple=float(trade.r_multiple) if trade.r_multiple is not None else None,
        entry_price=float(trade.entry_price) if trade.entry_price is not None else None,
        exit_price=float(trade.exit_price) if trade.exit_price is not None else None,
        size=float(trade.size) if trade.size is not None else None,
        stop_loss=(
            float(position.stop_loss)
            if position and position.stop_loss is not None
            else None
        ),
        take_profit=(
            float(position.take_profit)
            if position and position.take_profit is not None
            else None
        ),
        floating_pnl=(
            float(position.floating_pnl)
            if position and position.floating_pnl is not None
            else None
        ),
        gross_pnl=deal_totals["gross_pnl"] if trade.source == "mt5" else None,
        commission=deal_totals["commission"] if trade.source == "mt5" else None,
        swap=deal_totals["swap"] if trade.source == "mt5" else None,
        notes=trade.notes,
        source=trade.source,
        opened_at=trade.opened_at,
        closed_at=trade.closed_at,
        created_at=trade.created_at,
        updated_at=trade.updated_at,
        tags=list(tags),
    )


def replace_tags(db: Database, trade: Trade, user_id: UUID, names: list[str]) -> None:
    normalized = list(dict.fromkeys(name.strip() for name in names))
    if any(not name or len(name) > 64 for name in normalized):
        raise HTTPException(status_code=422, detail="Tags must contain 1 to 64 characters")
    db.query(TradeTag).filter(TradeTag.trade_id == trade.id).delete()
    for name in normalized:
        tag = db.scalar(
            select(JournalTag).where(JournalTag.user_id == user_id, JournalTag.name == name)
        )
        if tag is None:
            tag = JournalTag(user_id=user_id, name=name)
            db.add(tag)
            db.flush()
        db.add(TradeTag(trade_id=trade.id, tag_id=tag.id))


@router.get("", response_model=TradeList)
def list_trades(
    current_user: CurrentUser,
    db: Database,
    symbol: str | None = None,
    strategy: str | None = None,
    outcome: TradeOutcomeValue | None = None,
    account_id: UUID | None = None,
    tag: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TradeList:
    filters = [Trade.user_id == current_user.id]
    if symbol:
        filters.append(Trade.symbol == symbol.strip().upper())
    if strategy:
        filters.append(Trade.strategy == strategy)
    if outcome:
        filters.append(Trade.outcome == outcome.value)
    if account_id:
        filters.append(Trade.account_id == account_id)
    if tag:
        filters.append(
            exists(
                select(TradeTag.id)
                .join(JournalTag, JournalTag.id == TradeTag.tag_id)
                .where(TradeTag.trade_id == Trade.id, JournalTag.name == tag)
            )
        )
    if start:
        filters.append(Trade.opened_at >= start)
    if end:
        filters.append(Trade.opened_at < end)
    if start and end and start >= end:
        raise HTTPException(status_code=422, detail="start must be earlier than end")
    query = select(Trade).where(*filters)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(Trade.opened_at.desc(), Trade.id.desc()).limit(limit).offset(offset)
    ).all()
    return TradeList(
        items=[serialize_trade(db, trade) for trade in rows],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.post("", response_model=TradeRead, status_code=status.HTTP_201_CREATED)
def create_trade(
    payload: TradeCreate,
    current_user: CurrentUser,
    db: Database,
) -> TradeRead:
    if (
        payload.account_id
        and db.scalar(
            select(TradingAccount.id).where(
                TradingAccount.id == payload.account_id,
                TradingAccount.user_id == current_user.id,
                TradingAccount.archived_at.is_(None),
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Trading account not found")
    if payload.plan_id:
        plan = db.scalar(
            select(TradePlan).where(
                TradePlan.id == payload.plan_id,
                TradePlan.user_id == current_user.id,
            )
        )
        if plan is None:
            raise HTTPException(status_code=404, detail="Trade plan not found")
        if plan.state != PlanState.PLANNED:
            raise HTTPException(status_code=409, detail="Only an active plan can be linked")
    trade = Trade(
        user_id=current_user.id,
        account_id=payload.account_id,
        plan_id=payload.plan_id,
        symbol=payload.symbol,
        direction=payload.direction.value,
        strategy=payload.strategy,
        outcome=payload.outcome.value,
        pnl=payload.pnl,
        r_multiple=payload.r_multiple,
        entry_price=payload.entry_price,
        exit_price=payload.exit_price,
        size=payload.size,
        notes=payload.notes,
        source="user",
        opened_at=payload.opened_at,
        closed_at=payload.closed_at,
    )
    db.add(trade)
    db.flush()
    replace_tags(db, trade, current_user.id, payload.tags)
    db.add(
        TradeEvent(
            trade_id=trade.id,
            event_type="manual_recorded",
            source="user",
            payload={"outcome": trade.outcome},
            occurred_at=trade.opened_at,
        )
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="trade.created",
            entity_type="trade",
            entity_id=str(trade.id),
            source="user",
        )
    )
    db.commit()
    db.refresh(trade)
    return serialize_trade(db, trade)


@router.get("/{trade_id}", response_model=TradeRead)
def read_trade(trade_id: UUID, current_user: CurrentUser, db: Database) -> TradeRead:
    return serialize_trade(db, get_owned_trade(db, current_user.id, trade_id))


@router.patch("/{trade_id}", response_model=TradeRead)
def update_trade(
    trade_id: UUID,
    payload: TradeUpdate,
    current_user: CurrentUser,
    db: Database,
) -> TradeRead:
    trade = get_owned_trade(db, current_user.id, trade_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")
    if trade.source != "user" and any(key != "notes" for key in changes):
        raise HTTPException(
            status_code=409,
            detail="Imported execution facts are read-only; only user notes may be changed",
        )
    if trade.source == "user":
        updated_outcome = changes.get("outcome", trade.outcome)
        updated_pnl = changes.get("pnl", trade.pnl)
        updated_close = changes.get("closed_at", trade.closed_at)
        if updated_outcome == "open":
            if updated_pnl is not None or updated_close is not None:
                raise HTTPException(
                    status_code=422,
                    detail="Open trades cannot include realized P&L or a close timestamp",
                )
        elif updated_pnl is None or updated_close is None:
            raise HTTPException(
                status_code=422,
                detail="Closed trades require realized P&L and a close timestamp",
            )
        opened_at = (
            trade.opened_at.replace(tzinfo=UTC)
            if trade.opened_at.tzinfo is None
            else trade.opened_at
        )
        if updated_close is not None and updated_close < opened_at:
            raise HTTPException(
                status_code=422,
                detail="Close timestamp cannot precede the open timestamp",
            )
    for key, value in changes.items():
        if value is not None or key in {"notes", "pnl", "r_multiple", "exit_price", "closed_at"}:
            if key == "tags":
                replace_tags(db, trade, current_user.id, value or [])
            else:
                setattr(trade, key, value.value if hasattr(value, "value") else value)
    trade.updated_at = datetime.now(UTC)
    db.add(
        TradeEvent(
            trade_id=trade.id,
            event_type="journal_updated",
            source="user",
            payload={"fields": ",".join(changes)},
            occurred_at=datetime.now(UTC),
        )
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="trade.updated",
            entity_type="trade",
            entity_id=str(trade.id),
            source="user",
            details={"fields": ",".join(changes)},
        )
    )
    db.commit()
    db.refresh(trade)
    return serialize_trade(db, trade)


@router.get("/{trade_id}/events", response_model=list[TradeEventRead])
@router.get("/{trade_id}/timeline", response_model=list[TradeEventRead])
def trade_events(trade_id: UUID, current_user: CurrentUser, db: Database) -> list[TradeEvent]:
    trade = get_owned_trade(db, current_user.id, trade_id)
    return db.scalars(
        select(TradeEvent)
        .where(TradeEvent.trade_id == trade.id)
        .order_by(TradeEvent.occurred_at, TradeEvent.id)
    ).all()


@router.get("/{trade_id}/journal", response_model=list[TradeJournalSectionRead])
def read_trade_journal(
    trade_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> list[TradeJournalSection]:
    trade = get_owned_trade(db, current_user.id, trade_id)
    return db.scalars(
        select(TradeJournalSection)
        .where(TradeJournalSection.trade_id == trade.id)
        .order_by(TradeJournalSection.section_key)
    ).all()


@router.patch("/{trade_id}/journal/{section_key}", response_model=TradeJournalSectionRead)
def save_trade_journal_section(
    trade_id: UUID,
    section_key: str,
    payload: TradeJournalSectionUpdate,
    current_user: CurrentUser,
    db: Database,
) -> TradeJournalSection:
    trade = get_owned_trade(db, current_user.id, trade_id)
    if not section_key.replace("_", "").isalnum() or len(section_key) > 64:
        raise HTTPException(status_code=422, detail="Journal section key is invalid")
    if len(json.dumps(payload.content, ensure_ascii=True)) > 32000:
        raise HTTPException(status_code=413, detail="Journal section content exceeds 32 KB")
    section = db.scalar(
        select(TradeJournalSection).where(
            TradeJournalSection.trade_id == trade.id,
            TradeJournalSection.section_key == section_key,
        )
    )
    if section is None:
        section = TradeJournalSection(
            trade_id=trade.id,
            section_key=section_key,
            content=payload.content,
        )
        db.add(section)
    else:
        section.content = payload.content
        section.updated_at = datetime.now(UTC)
    db.add(
        TradeEvent(
            trade_id=trade.id,
            event_type="journal_section_saved",
            source="user",
            payload={"section_key": section_key},
            occurred_at=datetime.now(UTC),
        )
    )
    db.commit()
    db.refresh(section)
    return section


@router.post(
    "/{trade_id}/reviews",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
)
def create_trade_review(
    trade_id: UUID,
    payload: ReviewCreate,
    current_user: CurrentUser,
    db: Database,
) -> TradeReview:
    trade = get_owned_trade(db, current_user.id, trade_id)
    if trade.outcome == "open":
        raise HTTPException(status_code=409, detail="Open trades cannot be reviewed as closed")
    if db.scalar(select(TradeReview.id).where(TradeReview.trade_id == trade.id)):
        raise HTTPException(status_code=409, detail="A review already exists for this trade")
    review = TradeReview(
        trade_id=trade.id,
        user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(review)
    db.add(
        TradeEvent(
            trade_id=trade.id,
            event_type="review_created",
            source="user",
            payload={"plan_adherence": payload.plan_adherence},
            occurred_at=datetime.now(UTC),
        )
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="trade.review_created",
            entity_type="trade",
            entity_id=str(trade.id),
            source="user",
        )
    )
    db.commit()
    db.refresh(review)
    return review


@router.patch("/{trade_id}/reviews", response_model=ReviewRead)
def update_trade_review(
    trade_id: UUID,
    payload: ReviewCreate,
    current_user: CurrentUser,
    db: Database,
) -> TradeReview:
    trade = get_owned_trade(db, current_user.id, trade_id)
    review = db.scalar(select(TradeReview).where(TradeReview.trade_id == trade.id))
    if review is None:
        raise HTTPException(status_code=404, detail="Trade review not found")
    for field, value in payload.model_dump().items():
        setattr(review, field, value)
    review.updated_at = datetime.now(UTC)
    db.add(
        TradeEvent(
            trade_id=trade.id,
            event_type="review_updated",
            source="user",
            payload={"plan_adherence": payload.plan_adherence},
            occurred_at=datetime.now(UTC),
        )
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="trade.review_updated",
            entity_type="trade",
            entity_id=str(trade.id),
            source="user",
        )
    )
    db.commit()
    db.refresh(review)
    return review


@router.get("/{trade_id}/reviews", response_model=ReviewRead)
def read_trade_review(
    trade_id: UUID,
    current_user: CurrentUser,
    db: Database,
) -> TradeReview:
    trade = get_owned_trade(db, current_user.id, trade_id)
    review = db.scalar(select(TradeReview).where(TradeReview.trade_id == trade.id))
    if review is None:
        raise HTTPException(status_code=404, detail="Trade review not found")
    return review
