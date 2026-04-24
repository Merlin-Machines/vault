from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyMode(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    CRYPTO_ONLY = "crypto_only"
    WEATHER_ONLY = "weather_only"
    LEGACY_AGGRESSIVE = "legacy_aggressive"


class AggressionIntensity(str, Enum):
    MODERATE = "moderate"
    ASSERTIVE = "assertive"
    MAX = "max"


class InterventionType(str, Enum):
    PAUSE = "pause"
    RESUME = "resume"
    COMMIT_BASELINE = "commit_baseline"


class AuditEvent(BaseModel):
    at: datetime = Field(default_factory=utc_now)
    actor: str
    event: str
    detail: str


class DirectiveProfile(BaseModel):
    name: str
    proposal_text: str
    summary: str
    source: str = "seeded"
    updated_at: datetime = Field(default_factory=utc_now)


class SafeControls(BaseModel):
    trading_enabled: bool = True
    strategy_mode: StrategyMode = StrategyMode.BALANCED
    continuous_trading: bool = True
    base_size_usdc: float = 1.25
    max_size_usdc: float = 3.0
    max_entries_per_cycle: int = 4
    max_hold_minutes: int = 45
    stop_loss_pct: float = 0.05
    profit_take_pct: float = 0.03
    alignment_required: int = 3
    dca_enabled: bool = True
    use_news_context: bool = True
    use_weather_context: bool = True
    use_tradingview_reference: bool = True
    crypto_enabled: bool = True
    weather_enabled: bool = True


class AggressionState(BaseModel):
    enabled: bool = False
    status: str = "idle"
    intensity: AggressionIntensity = AggressionIntensity.MODERATE
    duration_minutes: int = 0
    min_edge_pct: float = 5.0
    profit_target_pct: float = 3.0
    started_at: datetime | None = None
    until: datetime | None = None
    ended_at: datetime | None = None
    note: str = "No timed aggression window is active."
    source: str = "operator"


class ValidationReplay(BaseModel):
    sample_size: int = 32
    qualified_trades: int = 18
    estimated_pnl_usdc: float = 61.4
    estimated_win_rate_pct: float = 63.8


class ValidationState(BaseModel):
    ok: bool = True
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    replay: ValidationReplay = Field(default_factory=ValidationReplay)


class ReviewState(BaseModel):
    headline: str
    scorecard: List[str] = Field(default_factory=list)
    reinforcements: List[str] = Field(default_factory=list)
    coaching: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    goal_progress_pct: float = 0.0


class TelemetryState(BaseModel):
    agent_id: str = "poly-agent-01"
    runtime_state: str = "dry-run"
    strategy_name: str = "live-directive-hybrid"
    pnl_usd: float = 42.15
    open_positions: int = 3
    total_trades: int = 18
    today_trades: int = 6
    account_name: str = "ACCOUNT"
    wallet: str = ""
    source: str = "seeded"
    synced_at: datetime = Field(default_factory=utc_now)


class IntegrationState(BaseModel):
    enabled: bool = True
    configured: bool = False
    docs_url: str
    endpoint: str | None = None
    coverage: str = ""
    host: str | None = None
    notes: List[str] = Field(default_factory=list)


class WeatherIntegrations(BaseModel):
    noaa: IntegrationState
    weather_company: IntegrationState
    weatherapi_rapidapi: IntegrationState
    notes: List[str] = Field(default_factory=list)


class TradingViewIntegration(BaseModel):
    enabled: bool = True
    configured: bool = True
    default_symbol: str = "BINANCE:BTCUSDT"
    docs_url: str = "https://www.tradingview.com/widget-docs/widgets/charts"
    integration_mode: str = "widget"
    charting_library_access: bool = False
    host: str | None = None
    notes: List[str] = Field(default_factory=list)


class NewsIntegrations(BaseModel):
    google_news_rss: IntegrationState


class WorkflowIntegration(BaseModel):
    configured: bool = True
    repo_url: str
    note: str


class IntegrationsState(BaseModel):
    weather: WeatherIntegrations
    tradingview: TradingViewIntegration
    news: NewsIntegrations
    github: WorkflowIntegration


class RuntimeSyncState(BaseModel):
    connected: bool = False
    status: str = "disconnected"
    base_url: str = "http://127.0.0.1:7731"
    linked_runtime: str = "POLY_AGENT_Merlin"
    source: str = "seeded"
    last_error: str | None = None
    available_endpoints: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    synced_at: datetime = Field(default_factory=utc_now)


class MarketTicker(BaseModel):
    symbol: str
    price: float
    change_pct_24h: float = 0.0
    quote_volume_usd: float = 0.0
    funding_rate_pct: float | None = None
    open_interest_usd: float | None = None
    spread_pct: float | None = None
    regime: str = "mixed"
    note: str = ""


class TechnicalSnapshot(BaseModel):
    symbol: str
    interval: str = "5m"
    last_price: float
    ra_score: float = 0.0
    ra_label: str = "neutral"
    rsi: float = 50.0
    momentum_pct: float = 0.0
    trend: str = "neutral"
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    macd_bias: str = "neutral"
    bollinger_upper: float = 0.0
    bollinger_middle: float = 0.0
    bollinger_lower: float = 0.0
    bollinger_bandwidth_pct: float = 0.0
    bollinger_signal: str = "neutral"
    atr_pct: float = 0.0
    volume_ratio: float = 1.0
    alignment_score: int = 0
    stance: str = "neutral"
    summary: str = ""


class MarketOverview(BaseModel):
    status: str = "seeded"
    as_of: datetime = Field(default_factory=utc_now)
    summary: str = "Waiting for market data."
    risk_note: str = "Market intelligence is not hydrated yet."
    tickers: List[MarketTicker] = Field(default_factory=list)
    technicals: List[TechnicalSnapshot] = Field(default_factory=list)


class IntelFeedItem(BaseModel):
    source: str
    category: str
    title: str
    url: str
    sentiment: str = "neutral"
    summary: str = ""
    published_at: datetime | None = None


class ResearchSource(BaseModel):
    source: str
    category: str
    title: str
    url: str
    note: str = ""


class StrategyLayer(BaseModel):
    name: str
    posture: str
    thesis: str
    triggers: List[str] = Field(default_factory=list)
    risk_note: str = ""


class ManagerState(BaseModel):
    id: str = "vault-mgmt-01"
    name: str = "Vault MGMT"
    mission: str = (
        "Direct the Poly Agent through live manager directives, safe runtime knobs, "
        "and clear operator visibility."
    )
    live: DirectiveProfile
    baseline: DirectiveProfile
    controls: SafeControls
    validation: ValidationState
    review: ReviewState
    telemetry: TelemetryState
    runtime: RuntimeSyncState = Field(default_factory=RuntimeSyncState)
    market: MarketOverview = Field(default_factory=MarketOverview)
    integrations: IntegrationsState
    intel_feed: List[IntelFeedItem] = Field(default_factory=list)
    research_library: List[ResearchSource] = Field(default_factory=list)
    strategy_layers: List[StrategyLayer] = Field(default_factory=list)
    profiles: List[str] = Field(default_factory=list)
    diff: List[dict] = Field(default_factory=list)
    audit_log: List[AuditEvent] = Field(default_factory=list)
