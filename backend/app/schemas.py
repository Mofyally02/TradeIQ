from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Full name is required")
        return cleaned

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class UserRead(BaseModel):
    id: UUID
    full_name: str | None = None
    email: EmailStr
    role: str = "user"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlanDirection(StrEnum):
    LONG = "Long"
    SHORT = "Short"


class PlanStateValue(StrEnum):
    PLANNED = "planned"
    DISCARDED = "discarded"
    INVALIDATED = "invalidated"


class TradePlanCreate(BaseModel):
    account_id: UUID | None = None
    symbol: str = Field(min_length=1, max_length=32)
    direction: PlanDirection
    strategy: str = Field(default="Uncategorized", min_length=1, max_length=120)
    thesis: str = Field(min_length=1, max_length=10000)
    entry_zone: dict[str, str] | None = None
    stop_loss: float | None = Field(default=None, gt=0)
    targets: list[dict[str, str]] | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Symbol cannot be blank")
        return value

    @field_validator("strategy", "thesis")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class TradePlanUpdate(BaseModel):
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    direction: PlanDirection | None = None
    strategy: str | None = Field(default=None, min_length=1, max_length=120)
    thesis: str | None = Field(default=None, min_length=1, max_length=10000)
    entry_zone: dict[str, str] | None = None
    stop_loss: float | None = Field(default=None, gt=0)
    targets: list[dict[str, str]] | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not value:
            raise ValueError("Symbol cannot be blank")
        return value

    @field_validator("strategy", "thesis")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class TradePlanRead(BaseModel):
    id: UUID
    account_id: UUID | None = None
    symbol: str
    direction: PlanDirection
    strategy: str
    thesis: str
    entry_zone: dict[str, str] | None = None
    stop_loss: float | None = None
    targets: list[dict[str, str]] | None = None
    state: PlanStateValue
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TradePlanList(BaseModel):
    items: list[TradePlanRead]
    limit: int
    offset: int


class ProfileUpdate(BaseModel):
    email: EmailStr | None = None
    experience_level: str | None = Field(default=None, max_length=32)
    goals: str | None = Field(default=None, max_length=5000)
    preferred_instruments: list[str] | None = Field(default=None, max_length=100)
    preferred_sessions: list[str] | None = Field(default=None, max_length=20)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> EmailStr | None:
        return value.lower() if value is not None else None


class ProfileRead(BaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime
    experience_level: str | None = None
    goals: str | None = None
    preferred_instruments: list[str] = Field(default_factory=list)
    preferred_sessions: list[str] = Field(default_factory=list)


class PreferenceUpdate(BaseModel):
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    theme: str | None = Field(default=None, pattern="^(light|dark|system)$")
    notifications_enabled: bool | None = None


class PreferenceRead(BaseModel):
    user_id: UUID
    timezone: str
    currency: str
    theme: str
    notifications_enabled: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountEnvironmentValue(StrEnum):
    DEMO = "demo"
    LIVE = "live"
    EVALUATION = "evaluation"


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    external_account_id: str | None = Field(default=None, max_length=64)
    broker: str | None = Field(default=None, max_length=120)
    server_name: str | None = Field(default=None, max_length=120)
    account_type: str = Field(default="standard", min_length=1, max_length=32)
    environment: AccountEnvironmentValue = AccountEnvironmentValue.DEMO
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    leverage: str | None = Field(default=None, max_length=16)

    @field_validator("name", "account_type")
    @classmethod
    def strip_account_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class AccountRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AccountRead(BaseModel):
    id: UUID
    name: str
    external_account_id: str | None
    broker: str | None
    server_name: str | None
    account_type: str
    environment: AccountEnvironmentValue
    currency: str
    leverage: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountList(BaseModel):
    items: list[AccountRead]
    limit: int
    offset: int


class MetaApiConnectRequest(BaseModel):
    login: int = Field(gt=0, le=2**63 - 1)
    password: SecretStr = Field(min_length=1, max_length=256, repr=False)
    server: str = Field(min_length=1, max_length=120)

    @field_validator("server")
    @classmethod
    def strip_server(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Server cannot be blank")
        return value


class MT5ConnectRequest(BaseModel):
    login: int = Field(gt=0, le=2**63 - 1)
    password: SecretStr = Field(min_length=1, max_length=256, repr=False)
    server: str = Field(min_length=1, max_length=120)
    timeout: int = Field(default=60000, ge=1000, le=300000)

    @field_validator("server")
    @classmethod
    def strip_server(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Server cannot be blank")
        return value


class TradeOutcomeValue(StrEnum):
    WIN = "win"
    LOSS = "loss"
    FLAT = "flat"
    OPEN = "open"


class TradeCreate(BaseModel):
    account_id: UUID | None = None
    plan_id: UUID | None = None
    symbol: str = Field(min_length=1, max_length=32)
    direction: PlanDirection
    strategy: str = Field(default="Uncategorized", min_length=1, max_length=120)
    setup: str | None = Field(default=None, min_length=1, max_length=120)
    outcome: TradeOutcomeValue = TradeOutcomeValue.OPEN
    pnl: float | None = None
    r_multiple: float | None = None
    entry_price: float | None = Field(default=None, gt=0)
    exit_price: float | None = Field(default=None, gt=0)
    size: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    mae_r: float | None = Field(default=None, ge=0)
    mfe_r: float | None = Field(default=None, ge=0)
    emotional_state: str | None = Field(default=None, min_length=1, max_length=64)
    confluences: list[str] = Field(default_factory=list, max_length=30)
    rule_breaks: list[str] = Field(default_factory=list, max_length=30)
    notes: str | None = Field(default=None, max_length=10000)
    opened_at: datetime
    closed_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("symbol")
    @classmethod
    def normalize_trade_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Symbol cannot be blank")
        return value

    @field_validator("emotional_state")
    @classmethod
    def normalize_emotional_state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Emotional state cannot be blank")
        return value

    @field_validator("setup")
    @classmethod
    def normalize_setup(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Setup cannot be blank")
        return value

    @field_validator("confluences", "rule_breaks")
    @classmethod
    def normalize_trade_labels(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values))
        if any(not value or len(value) > 120 for value in normalized):
            raise ValueError("Each label must be 1 to 120 characters")
        return normalized

    @model_validator(mode="after")
    def validate_trade_lifecycle(self) -> "TradeCreate":
        if self.outcome == TradeOutcomeValue.OPEN and self.pnl is not None:
            raise ValueError("Open trades cannot have realized P&L")
        if self.outcome != TradeOutcomeValue.OPEN and self.pnl is None:
            raise ValueError("Closed trades require broker-reported realized P&L")
        if self.outcome != TradeOutcomeValue.OPEN and self.closed_at is None:
            raise ValueError("Closed trades require a close timestamp")
        if self.closed_at and self.closed_at < self.opened_at:
            raise ValueError("Close timestamp cannot precede open timestamp")
        return self

    @field_validator("opened_at", "closed_at")
    @classmethod
    def require_utc_aware_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone offset")
        return value.astimezone(UTC)


class TradeUpdate(BaseModel):
    strategy: str | None = Field(default=None, min_length=1, max_length=120)
    setup: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=10000)
    tags: list[str] | None = Field(default=None, max_length=30)
    outcome: TradeOutcomeValue | None = None
    pnl: float | None = None
    r_multiple: float | None = None
    entry_price: float | None = Field(default=None, gt=0)
    exit_price: float | None = Field(default=None, gt=0)
    size: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    mae_r: float | None = Field(default=None, ge=0)
    mfe_r: float | None = Field(default=None, ge=0)
    emotional_state: str | None = Field(default=None, min_length=1, max_length=64)
    confluences: list[str] | None = Field(default=None, max_length=30)
    rule_breaks: list[str] | None = Field(default=None, max_length=30)
    closed_at: datetime | None = None

    @field_validator("emotional_state")
    @classmethod
    def normalize_emotional_state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Emotional state cannot be blank")
        return value

    @field_validator("setup")
    @classmethod
    def normalize_setup(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Setup cannot be blank")
        return value

    @field_validator("confluences", "rule_breaks")
    @classmethod
    def normalize_trade_labels(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = list(dict.fromkeys(value.strip() for value in values))
        if any(not value or len(value) > 120 for value in normalized):
            raise ValueError("Labels must contain 1 to 64 characters")
        return normalized

    @field_validator("closed_at")
    @classmethod
    def require_utc_aware_close_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone offset")
        return value.astimezone(UTC)


class TradeRead(BaseModel):
    id: UUID
    account_id: UUID | None
    plan_id: UUID | None
    symbol: str
    direction: PlanDirection
    strategy: str
    setup: str | None = None
    outcome: TradeOutcomeValue
    pnl: float | None
    r_multiple: float | None
    entry_price: float | None
    exit_price: float | None
    size: float | None
    stop_loss: float | None = None
    take_profit: float | None = None
    mae_r: float | None = None
    mfe_r: float | None = None
    emotional_state: str | None = None
    confluences: list[str] = Field(default_factory=list)
    rule_breaks: list[str] = Field(default_factory=list)
    floating_pnl: float | None = None
    gross_pnl: float | None = None
    commission: float | None = None
    swap: float | None = None
    notes: str | None
    source: str
    opened_at: datetime
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)
    journaled: bool = False


class TradeList(BaseModel):
    items: list[TradeRead]
    limit: int
    offset: int
    total: int


class ReviewCreate(BaseModel):
    plan_adherence: str = Field(pattern="^(yes|partly|no)$")
    learning: str = Field(min_length=1, max_length=10000)
    next_action: str = Field(min_length=1, max_length=5000)


class ReviewRead(BaseModel):
    id: UUID
    trade_id: UUID
    user_id: UUID
    plan_adherence: str
    learning: str
    next_action: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TradeEventRead(BaseModel):
    id: UUID
    trade_id: UUID
    event_type: str
    source: str
    payload: dict[str, object] | None
    occurred_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RiskProfileUpdate(BaseModel):
    max_daily_loss: float | None = Field(default=None, gt=0)
    max_risk_per_trade: float | None = Field(default=None, gt=0, le=100)
    max_trades_per_day: int | None = Field(default=None, ge=1, le=1000)


class RiskProfileRead(BaseModel):
    id: UUID
    user_id: UUID
    account_id: UUID | None
    max_daily_loss: float | None
    max_risk_per_trade: float | None
    max_trades_per_day: int | None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PerformanceRoadmapProgressUpdate(BaseModel):
    progress_status: str = Field(pattern="^(pending|in_progress|completed|adjusted)$")
    progress_notes: str | None = Field(default=None, max_length=5000)


GOAL_METRICS = (
    "expectancy_r|win_rate_pct|profit_factor|max_drawdown_r|average_loss_r|rule_break_rate_pct"
)


class DevelopmentGoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    metric: str = Field(pattern=f"^({GOAL_METRICS})$")
    direction: str = Field(pattern="^(increase|decrease)$")
    target_value: float
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class DevelopmentGoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    target_value: float | None = None
    due_date: date | None = None
    status: str | None = Field(default=None, pattern="^(active|achieved|paused|dropped)$")
    notes: str | None = Field(default=None, max_length=5000)


class DevelopmentExperimentCreate(BaseModel):
    goal_id: UUID | None = None
    title: str = Field(min_length=1, max_length=160)
    hypothesis: str = Field(min_length=1, max_length=5000)
    rule: str = Field(min_length=1, max_length=5000)
    start_date: date
    end_date: date | None = None
    min_trades: int = Field(default=20, ge=1, le=1000)


class DevelopmentExperimentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    hypothesis: str | None = Field(default=None, min_length=1, max_length=5000)
    rule: str | None = Field(default=None, min_length=1, max_length=5000)
    end_date: date | None = None
    status: str | None = Field(default=None, pattern="^(planned|running|concluded|abandoned)$")
    conclusion: str | None = Field(default=None, max_length=5000)


class TradingViewWebhook(BaseModel):
    model_config = ConfigDict(extra="allow")

    webhook_token: str = Field(min_length=32, max_length=128, exclude=True)
    alert_id: str | None = Field(default=None, min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=32)
    action: str | None = Field(default=None, max_length=32)
    price: str | float | None = None
    lots: str | float | None = None
    timeframe: str | None = Field(default=None, max_length=16)
    timestamp: str | None = Field(default=None, max_length=64)
    payload: dict[str, object] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_alert_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Symbol cannot be blank")
        return value


class AlertRead(BaseModel):
    id: UUID
    external_alert_id: str
    symbol: str
    timeframe: str | None
    payload: dict[str, object]
    processing_status: str
    received_at: datetime
    dismissed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AlertMatch(BaseModel):
    trade_id: UUID


class TradeJournalSectionUpdate(BaseModel):
    content: dict[str, object] | list[object]


class TradeJournalSectionRead(BaseModel):
    section_key: str
    content: dict[str, object] | list[object]
    updated_at: datetime


class MT5OrderInput(BaseModel):
    external_order_id: str = Field(min_length=1, max_length=128)
    order_type: str = Field(min_length=1, max_length=32)
    volume: float = Field(ge=0)
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    state: str = Field(min_length=1, max_length=32)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_aware_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone offset")
        return value.astimezone(UTC)


class MT5DealInput(BaseModel):
    external_deal_id: str = Field(min_length=1, max_length=128)
    position_identifier: str | None = Field(default=None, max_length=128)
    external_order_id: str | None = Field(default=None, max_length=128)
    entry_type: str = Field(default="in", pattern="^(in|out|inout|out_by)$")
    symbol: str = Field(min_length=1, max_length=32)
    direction: PlanDirection
    volume: float = Field(ge=0)
    price: float = Field(ge=0)
    pnl: float | None = None
    commission: float | None = None
    swap: float | None = None
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_aware_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone offset")
        return value.astimezone(UTC)


class MT5PositionInput(BaseModel):
    external_position_id: str = Field(min_length=1, max_length=128)
    position_identifier: str | None = Field(default=None, max_length=128)
    symbol: str = Field(min_length=1, max_length=32)
    direction: PlanDirection
    volume: float = Field(ge=0)
    entry_price: float | None = None
    current_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    floating_pnl: float | None = None
    state: str = Field(min_length=1, max_length=24)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_aware_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone offset")
        return value.astimezone(UTC)


class MT5SnapshotInput(BaseModel):
    balance: float
    equity: float
    margin: float | None = None
    free_margin: float | None = None
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def require_aware_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone offset")
        return value.astimezone(UTC)


class MT5SyncPayload(BaseModel):
    sync_run_id: UUID
    external_account_id: str = Field(min_length=1, max_length=64)
    orders: list[MT5OrderInput] = Field(default_factory=list, max_length=10000)
    deals: list[MT5DealInput] = Field(default_factory=list, max_length=10000)
    positions: list[MT5PositionInput] = Field(default_factory=list, max_length=1000)
    snapshot: MT5SnapshotInput


class MT5SyncFailure(BaseModel):
    sync_run_id: UUID
    error: str = Field(min_length=1, max_length=2000)


class DashboardSummary(BaseModel):
    closed_trade_count: int
    wins: int
    losses: int
    net_pnl: float
    win_rate: float
    profit_factor: float | None
    average_r: float | None
    open_trade_count: int
    pending_review_count: int


class AnalyticsGroup(BaseModel):
    key: str
    trade_count: int
    net_pnl: float
    win_rate: float


class EquityPoint(BaseModel):
    observed_at: datetime
    balance: float
    equity: float
    source: str
