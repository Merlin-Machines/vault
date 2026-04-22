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
    integrations: IntegrationsState
    profiles: List[str] = Field(default_factory=list)
    diff: List[dict] = Field(default_factory=list)
    audit_log: List[AuditEvent] = Field(default_factory=list)
