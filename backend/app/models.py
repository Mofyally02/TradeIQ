from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String as _String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class IdString(TypeDecorator):
    """Native UUID column that accepts UUID or str values and returns str."""

    impl = Uuid(as_uuid=False)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else str(value)


def String(length: int | None = None):
    # 36-character identifiers are native UUID columns in the database schema.
    if length == 36:
        return IdString()
    return _String(length)


def utc_now() -> datetime:
    return datetime.now(UTC)


class PlanState(StrEnum):
    PLANNED = "planned"
    DISCARDED = "discarded"
    INVALIDATED = "invalidated"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    mt5_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    plans: Mapped[list["TradePlan"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_expires", "user_id", "expires_at"),)

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship(back_populates="sessions")


class TradePlan(Base):
    __tablename__ = "trade_plans"
    __table_args__ = (
        Index("ix_trade_plans_user_created", "user_id", "created_at"),
        Index("ix_trade_plans_user_state_created", "user_id", "state", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[UUID | None] = mapped_column(
        String(36), ForeignKey("trading_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(5))
    strategy: Mapped[str] = mapped_column(String(120), default="Uncategorized")
    thesis: Mapped[str] = mapped_column(Text)
    entry_zone: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    targets: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, nullable=True)
    state: Mapped[PlanState] = mapped_column(
        Enum(
            PlanState,
            values_callable=lambda enum: [item.value for item in enum],
            native_enum=False,
            create_constraint=True,
            name="trade_plan_state",
        ),
        default=PlanState.PLANNED,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    user: Mapped[User] = relationship(back_populates="plans")
    versions: Mapped[list["TradePlanVersion"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="TradePlanVersion.created_at"
    )


class TradePlanVersion(Base):
    __tablename__ = "trade_plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "version_number"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    plan_id: Mapped[UUID] = mapped_column(
        String(36), ForeignKey("trade_plans.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    plan: Mapped[TradePlan] = relationship(back_populates="versions")
