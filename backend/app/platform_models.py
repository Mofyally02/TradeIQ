from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import String, utc_now


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("theme IN ('light', 'dark', 'system')", name="ck_user_preferences_theme"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    theme: Mapped[str] = mapped_column(String(16), default="system")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TraderProfile(Base):
    __tablename__ = "trader_profiles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    experience_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_instruments: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_sessions: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"
    __table_args__ = (UniqueConstraint("user_id", "integration_type"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    integration_type: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TradingAccount(Base):
    __tablename__ = "trading_accounts"
    __table_args__ = (
        Index("ix_trading_accounts_user_created", "user_id", "created_at"),
        UniqueConstraint("user_id", "name", name="uq_trading_accounts_user_name"),
        CheckConstraint(
            "environment IN ('demo', 'live', 'evaluation')",
            name="ck_trading_accounts_environment",
        ),
        CheckConstraint("length(currency) = 3", name="ck_trading_accounts_currency_length"),
    )

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    external_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    broker: Mapped[str | None] = mapped_column(String(120), nullable=True)
    server_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    account_type: Mapped[str] = mapped_column(String(32), default="standard")
    environment: Mapped[str] = mapped_column(String(16), default="demo")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    leverage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AccountConnection(Base):
    __tablename__ = "account_connections"

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    connector_type: Mapped[str] = mapped_column(String(32), default="mt5")
    status: Mapped[str] = mapped_column(String(24), default="not_configured")
    connector_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_account_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_cursor: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"
    __table_args__ = (Index("ix_account_snapshots_account_observed", "account_id", "observed_at"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE"), index=True
    )
    balance: Mapped[float] = mapped_column(Numeric(20, 6))
    equity: Mapped[float] = mapped_column(Numeric(20, 6))
    margin: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    free_margin: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="mt5")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_user_opened", "user_id", "opened_at"),
        Index("ix_trades_user_outcome", "user_id", "outcome"),
        CheckConstraint("direction IN ('Long', 'Short')", name="ck_trades_direction"),
        CheckConstraint("outcome IN ('win', 'loss', 'flat', 'open')", name="ck_trades_outcome"),
        CheckConstraint("source IN ('user', 'mt5')", name="ck_trades_source"),
        CheckConstraint(
            "outcome = 'open' OR (pnl IS NOT NULL AND closed_at IS NOT NULL)",
            name="ck_closed_trade_fields",
        ),
        UniqueConstraint("account_id", "external_id", name="uq_trades_account_external_id"),
    )

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trade_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(5))
    strategy: Mapped[str] = mapped_column(String(120), default="Uncategorized")
    setup: Mapped[str | None] = mapped_column(String(120), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="open")
    pnl: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    r_multiple: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    size: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    mae_r: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    mfe_r: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    emotional_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confluences: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    rule_breaks: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="user")
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TradeEvent(Base):
    __tablename__ = "trade_events"
    __table_args__ = (Index("ix_trade_events_trade_occurred", "trade_id", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    trade_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("trades.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TradeReview(Base):
    __tablename__ = "trade_reviews"

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    trade_id: Mapped[UUID] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_adherence: Mapped[str] = mapped_column(String(8))
    learning: Mapped[str] = mapped_column(Text)
    next_action: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TradeJournalSection(Base):
    __tablename__ = "trade_journal_sections"
    __table_args__ = (UniqueConstraint("trade_id", "section_key"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    trade_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("trades.id", ondelete="CASCADE"), index=True)
    section_key: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict[str, object] | list[object]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class JournalTag(Base):
    __tablename__ = "journal_tags"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))


class TradeTag(Base):
    __tablename__ = "trade_tags"
    __table_args__ = (UniqueConstraint("trade_id", "tag_id"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    trade_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("trades.id", ondelete="CASCADE"), index=True)
    tag_id: Mapped[UUID] = mapped_column(
        ForeignKey("journal_tags.id", ondelete="CASCADE"), index=True
    )


class RiskProfile(Base):
    __tablename__ = "risk_profiles"
    __table_args__ = (UniqueConstraint("user_id", "account_id"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    max_daily_loss: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    max_risk_per_trade: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    max_trades_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PerformanceRoadmap(Base):
    __tablename__ = "performance_roadmaps"
    __table_args__ = (
        Index("ix_performance_roadmaps_user_generated", "user_id", "generated_at"),
        CheckConstraint(
            "progress_status IN ('pending', 'in_progress', 'completed', 'adjusted')",
            name="ck_performance_roadmaps_progress_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    trade_count: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON)
    recommendations: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    progress_status: Mapped[str] = mapped_column(String(24), default="pending")
    progress_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DevelopmentGoal(Base):
    __tablename__ = "development_goals"
    __table_args__ = (
        Index("ix_development_goals_user_status", "user_id", "status"),
        CheckConstraint("direction IN ('increase', 'decrease')", name="ck_development_goals_direction"),
        CheckConstraint(
            "status IN ('active', 'achieved', 'paused', 'dropped')",
            name="ck_development_goals_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    metric: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(12))
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_sample: Mapped[int] = mapped_column(Integer, default=0)
    target_value: Mapped[float] = mapped_column(Float)
    start_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DevelopmentExperiment(Base):
    __tablename__ = "development_experiments"
    __table_args__ = (
        Index("ix_development_experiments_user_status", "user_id", "status"),
        CheckConstraint(
            "status IN ('planned', 'running', 'concluded', 'abandoned')",
            name="ck_development_experiments_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("development_goals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    hypothesis: Mapped[str] = mapped_column(Text)
    rule: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    min_trades: Mapped[int] = mapped_column(Integer, default=20)
    status: Mapped[str] = mapped_column(String(16), default="planned")
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AccountRuleSet(Base):
    __tablename__ = "account_rule_sets"

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    rules: Mapped[dict[str, str]] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class MT5Order(Base):
    __tablename__ = "mt5_orders"
    __table_args__ = (UniqueConstraint("account_id", "external_order_id"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE"), index=True
    )
    external_order_id: Mapped[str] = mapped_column(String(128))
    order_type: Mapped[str] = mapped_column(String(32))
    volume: Mapped[float] = mapped_column(Numeric(20, 8))
    price: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    state: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(24), default="mt5")
    metadata_json: Mapped[dict[str, str] | None] = mapped_column("metadata", JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MT5Deal(Base):
    __tablename__ = "mt5_deals"
    __table_args__ = (UniqueConstraint("account_id", "external_deal_id"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE"), index=True
    )
    external_deal_id: Mapped[str] = mapped_column(String(128))
    position_identifier: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    external_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(16), default="in")
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(5))
    volume: Mapped[float] = mapped_column(Numeric(20, 8))
    price: Mapped[float] = mapped_column(Numeric(20, 8))
    pnl: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    commission: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    swap: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="mt5")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, str] | None] = mapped_column("metadata", JSON, nullable=True)


class MT5Position(Base):
    __tablename__ = "mt5_positions"
    __table_args__ = (UniqueConstraint("account_id", "external_position_id"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE"), index=True
    )
    external_position_id: Mapped[str] = mapped_column(String(128))
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(5))
    volume: Mapped[float] = mapped_column(Numeric(20, 8))
    entry_price: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    current_price: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    floating_pnl: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    state: Mapped[str] = mapped_column(String(24))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(24), default="mt5")


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (Index("ix_sync_runs_account_started", "account_id", "started_at"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("trading_accounts.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(24))
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TradingViewAlert(Base):
    __tablename__ = "tradingview_alerts"
    __table_args__ = (UniqueConstraint("source", "external_alert_id"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(24), default="tradingview")
    external_alert_id: Mapped[str] = mapped_column(String(128))
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str | None] = mapped_column(String(16), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    processing_status: Mapped[str] = mapped_column(String(24), default="received")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TradeAlertLink(Base):
    __tablename__ = "trade_alert_links"
    __table_args__ = (UniqueConstraint("alert_id", "trade_id"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    alert_id: Mapped[UUID] = mapped_column(
        ForeignKey("tradingview_alerts.id", ondelete="CASCADE"), index=True
    )
    trade_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("trades.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    matched_by: Mapped[str] = mapped_column(String(24), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trade_plans.id", ondelete="CASCADE"), nullable=True, index=True
    )
    trade_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), nullable=True, index=True
    )
    object_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    notification_type: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="user")
    details: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DeviceConnector(Base):
    """One secret per user; every MT5 terminal the user installs the TradeIQ EA on pushes with it."""

    __tablename__ = "device_connectors"

    user_id: Mapped[UUID] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    encrypted_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DetectedAccount(Base):
    """An MT5 login seen by a user's terminal that has not been connected to a TradeIQ account yet."""

    __tablename__ = "detected_accounts"
    __table_args__ = (UniqueConstraint("user_id", "login", name="uq_detected_accounts_user_login"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    login: Mapped[str] = mapped_column(String(64))
    server: Mapped[str | None] = mapped_column(String(120), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    balance: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    equity: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AdminRole(Base):
    __tablename__ = "admin_roles"

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(48), unique=True)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AdminMfa(Base):
    __tablename__ = "admin_mfa"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_secret: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AdminPermission(Base):
    __tablename__ = "admin_permissions"

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(255))


class AdminRolePermission(Base):
    __tablename__ = "admin_role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("admin_roles.id", ondelete="CASCADE"), index=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("admin_permissions.id", ondelete="CASCADE"), index=True
    )


class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "scope_type", "scope_id"),
        CheckConstraint(
            "scope_type IN ('platform', 'account')", name="ck_user_role_scope_type"
        ),
    )

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("admin_roles.id", ondelete="CASCADE"), index=True
    )
    scope_type: Mapped[str] = mapped_column(String(16), default="platform")
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assigned_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"
    __table_args__ = (Index("ix_admin_audit_actor_created", "actor_user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(48))
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(24), default="success")
    details: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PlatformIncident(Base):
    __tablename__ = "platform_incidents"
    __table_args__ = (
        Index("ix_platform_incidents_status_created", "status", "created_at"),
        CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'accepted_exception')",
            name="ck_platform_incidents_status",
        ),
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="ck_platform_incidents_severity"),
    )

    id: Mapped[UUID] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    category: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open")
    assigned_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
