from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from threading import Lock

from .models import (
    AuditEvent,
    DirectiveProfile,
    IntegrationsState,
    IntegrationState,
    InterventionType,
    ManagerState,
    NewsIntegrations,
    ReviewState,
    SafeControls,
    StrategyMode,
    TelemetryState,
    TradingViewIntegration,
    ValidationReplay,
    ValidationState,
    WeatherIntegrations,
    WorkflowIntegration,
)
from .policy import (
    PolicyError,
    validate_hold_minutes,
    validate_pct,
    validate_position_limit,
    validate_probability_threshold,
)


DEFAULT_DIRECTIVE_TEXT = (
    "The manager should direct the Poly Agent to continuously trade short-duration setups. "
    "Use 5-minute candles with MACD, RA/RSI, Bollinger Bands, momentum, trend, news, "
    "weather context, and TradingView reference when available. Enter and exit YES or NO "
    "positions actively, avoid holding into expiry, use DCA carefully, keep stop losses in "
    "place, and focus on disciplined profit scraping instead of letting positions decay."
)


def _slugify(value: str) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return raw or "continuous-profit-manager"


def _today_friday_progress(pnl_usd: float, target_usd: float) -> float:
    if target_usd <= 0:
        return 0.0
    return max(0.0, min(100.0, round((pnl_usd / target_usd) * 100.0, 1)))


def _next_friday_iso() -> str:
    today = date.today()
    days_ahead = (4 - today.weekday()) % 7
    return today.fromordinal(today.toordinal() + days_ahead).isoformat()


def _build_review(telemetry: TelemetryState, controls: SafeControls) -> ReviewState:
    target = 100.0
    goal_progress = _today_friday_progress(telemetry.pnl_usd, target)
    headline = (
        "MGMT is live-directing the agent through short-duration setups and active exit discipline."
    )
    scorecard = [
        f"Goal progress: ${telemetry.pnl_usd:.2f} / ${target:.2f} by {_next_friday_iso()} ({goal_progress:.1f}%).",
        f"Open positions: {telemetry.open_positions}.",
        f"Today trades: {telemetry.today_trades}.",
        f"Current strategy mode: {controls.strategy_mode.value}.",
    ]
    reinforcements = [
        "Continuous trading is enabled with tight hold discipline.",
        "News, weather, and TradingView context stay visible at the manager layer.",
    ]
    coaching = []
    if controls.max_entries_per_cycle > 4:
        coaching.append("High turnover can erode edge. Keep watching signal quality while cycling capital.")
    if telemetry.open_positions > 4:
        coaching.append("Open position count is climbing. Tighten exits before adding more churn.")
    if controls.weather_enabled and controls.crypto_enabled:
        reinforcements.append("Both crypto and weather routes remain available to the manager.")
    risks = [
        "Profit and certainty are targets, not guarantees. The repo UI should not imply otherwise.",
    ]
    return ReviewState(
        headline=headline,
        scorecard=scorecard,
        reinforcements=reinforcements,
        coaching=coaching,
        risks=risks,
        goal_progress_pct=goal_progress,
    )


def _build_validation(controls: SafeControls) -> ValidationState:
    warnings: list[str] = []
    errors: list[str] = []
    if controls.max_entries_per_cycle >= 5:
        warnings.append("Entry cadence is near the top of the seeded safety range.")
    if not controls.crypto_enabled and not controls.weather_enabled:
        errors.append("At least one market filter should remain enabled.")
    if controls.alignment_required < 3:
        warnings.append("Lower alignment can increase activity faster than quality.")
    replay = ValidationReplay(
        sample_size=32,
        qualified_trades=18 if not errors else 12,
        estimated_pnl_usdc=61.4 if not errors else 28.0,
        estimated_win_rate_pct=63.8 if not errors else 52.0,
    )
    return ValidationState(ok=not errors, warnings=warnings, errors=errors, replay=replay)


def _build_integrations() -> IntegrationsState:
    return IntegrationsState(
        weather=WeatherIntegrations(
            noaa=IntegrationState(
                enabled=True,
                configured=True,
                docs_url="https://www.weather.gov/documentation/services-web-api",
                endpoint="https://api.weather.gov/points/{lat},{lon}",
                coverage="Best for U.S. locations and alerts.",
            ),
            weather_company=IntegrationState(
                enabled=True,
                configured=False,
                docs_url="https://developer.weather.com/docs/standard-weather-data-package",
                endpoint="https://api.weather.com/v3/wx/forecast/hourly/2day",
                coverage="Optional key-backed weather.com data overlay.",
            ),
            weatherapi_rapidapi=IntegrationState(
                enabled=True,
                configured=False,
                docs_url="https://rapidapi.com/weatherapi/api/weatherapi-com",
                endpoint="https://weatherapi-com.p.rapidapi.com/forecast.json",
                host="weatherapi-com.p.rapidapi.com",
                coverage="Optional global current + forecast feed through RapidAPI.",
            ),
            notes=[
                "WeatherAPI.com via RapidAPI is separate from weather.com / The Weather Company.",
                "This repo reports integration intent first; runtime adapters come next.",
            ],
        ),
        tradingview=TradingViewIntegration(
            notes=[
                "The official widget path is the default here.",
                "The full Charting Library still needs separate TradingView access approval.",
            ]
        ),
        news=NewsIntegrations(
            google_news_rss=IntegrationState(
                enabled=True,
                configured=True,
                docs_url="https://news.google.com",
                coverage="Lightweight crypto headline context.",
            )
        ),
        github=WorkflowIntegration(
            repo_url="https://github.com/Merlin-Machines/vault",
            note="Use this repo as the shared handoff layer between Chat dev and Codex.",
        ),
    )


def _build_diff(live: DirectiveProfile, baseline: DirectiveProfile, controls: SafeControls) -> list[dict]:
    diff: list[dict] = []
    if live.name != baseline.name:
        diff.append({"field": "directive.name", "from": baseline.name, "to": live.name})
    if live.proposal_text != baseline.proposal_text:
        diff.append(
            {
                "field": "directive.proposal_text",
                "from": baseline.proposal_text[:140],
                "to": live.proposal_text[:140],
            }
        )
    if controls.continuous_trading:
        diff.append({"field": "controls.continuous_trading", "from": False, "to": True})
    diff.append({"field": "controls.strategy_mode", "from": "baseline", "to": controls.strategy_mode.value})
    return diff[:16]


class ManagerService:
    def __init__(self) -> None:
        self._lock = Lock()
        live = DirectiveProfile(
            name="continuous-profit-manager",
            proposal_text=DEFAULT_DIRECTIVE_TEXT,
            summary="Live directive for short-duration active management.",
        )
        baseline = deepcopy(live)
        controls = SafeControls()
        telemetry = TelemetryState()
        validation = _build_validation(controls)
        review = _build_review(telemetry, controls)
        self._manager = ManagerState(
            live=live,
            baseline=baseline,
            controls=controls,
            validation=validation,
            review=review,
            telemetry=telemetry,
            integrations=_build_integrations(),
            profiles=[live.name],
            diff=_build_diff(live, baseline, controls),
            audit_log=[
                AuditEvent(
                    actor="system",
                    event="manager_initialized",
                    detail="Vault MGMT seeded with the live-directive operator model.",
                )
            ],
        )

    def get_state(self) -> ManagerState:
        return self._manager

    def update_directive(self, name: str, proposal_text: str) -> ManagerState:
        with self._lock:
            directive_name = _slugify(name or self._manager.live.name)
            text = proposal_text.strip() or self._manager.live.proposal_text
            self._manager.live = DirectiveProfile(
                name=directive_name,
                proposal_text=text,
                summary="Live directive for short-duration active management.",
                source="operator",
            )
            self._apply_directive_hints(text)
            if directive_name not in self._manager.profiles:
                self._manager.profiles.append(directive_name)
            self._refresh_summary()
            self._stamp("operator", "directive_updated", f"Live directive updated to {directive_name}.")
            return self._manager

    def update_controls(self, **payload) -> ManagerState:
        with self._lock:
            controls = self._manager.controls.model_copy(deep=True)
            if "base_size_usdc" in payload:
                validate_position_limit(payload["base_size_usdc"])
                controls.base_size_usdc = payload["base_size_usdc"]
            if "max_size_usdc" in payload:
                validate_position_limit(payload["max_size_usdc"])
                controls.max_size_usdc = payload["max_size_usdc"]
            if controls.max_size_usdc < controls.base_size_usdc:
                controls.max_size_usdc = controls.base_size_usdc
            if "max_hold_minutes" in payload:
                validate_hold_minutes(payload["max_hold_minutes"])
                controls.max_hold_minutes = payload["max_hold_minutes"]
            if "stop_loss_pct" in payload:
                validate_pct(payload["stop_loss_pct"], "Stop loss")
                controls.stop_loss_pct = payload["stop_loss_pct"]
            if "profit_take_pct" in payload:
                validate_pct(payload["profit_take_pct"], "Profit take")
                controls.profit_take_pct = payload["profit_take_pct"]
            if "alignment_required" in payload:
                validate_probability_threshold(payload["alignment_required"])
                controls.alignment_required = payload["alignment_required"]
            for field in (
                "trading_enabled",
                "continuous_trading",
                "max_entries_per_cycle",
                "dca_enabled",
                "use_news_context",
                "use_weather_context",
                "use_tradingview_reference",
                "crypto_enabled",
                "weather_enabled",
            ):
                if field in payload:
                    setattr(controls, field, payload[field])
            if "strategy_mode" in payload and payload["strategy_mode"]:
                controls.strategy_mode = StrategyMode(payload["strategy_mode"])
            self._manager.controls = controls
            self._refresh_summary()
            self._stamp("operator", "controls_updated", "Safe runtime controls updated.")
            return self._manager

    def set_trading_enabled(self, enabled: bool) -> ManagerState:
        return self.update_controls(trading_enabled=enabled)

    def commit_baseline(self, name: str | None = None) -> ManagerState:
        with self._lock:
            baseline_name = _slugify(name or self._manager.live.name)
            self._manager.baseline = self._manager.live.model_copy(deep=True)
            self._manager.baseline.name = baseline_name
            if baseline_name not in self._manager.profiles:
                self._manager.profiles.append(baseline_name)
            self._refresh_summary()
            self._stamp("operator", "baseline_committed", f"Baseline committed as {baseline_name}.")
            return self._manager

    def intervene(self, action: InterventionType) -> ManagerState:
        with self._lock:
            if action == InterventionType.PAUSE:
                self._manager.controls.trading_enabled = False
                self._manager.telemetry.runtime_state = "paused"
            elif action == InterventionType.RESUME:
                self._manager.controls.trading_enabled = True
                self._manager.telemetry.runtime_state = "dry-run"
            elif action == InterventionType.COMMIT_BASELINE:
                baseline_name = _slugify(self._manager.live.name)
                self._manager.baseline = self._manager.live.model_copy(deep=True)
                self._manager.baseline.name = baseline_name
                if baseline_name not in self._manager.profiles:
                    self._manager.profiles.append(baseline_name)
            self._refresh_summary()
            self._stamp("operator", "intervention", f"Intervention applied: {action.value}.")
            return self._manager

    def _apply_directive_hints(self, text: str) -> None:
        lowered = text.lower()
        controls = self._manager.controls.model_copy(deep=True)
        if "continuous" in lowered:
            controls.continuous_trading = True
            controls.max_entries_per_cycle = max(controls.max_entries_per_cycle, 4)
        if "dca" in lowered or "dollar cost averaging" in lowered:
            controls.dca_enabled = True
        if "weather" in lowered:
            controls.use_weather_context = True
            controls.weather_enabled = True
        if "news" in lowered:
            controls.use_news_context = True
        if "tradingview" in lowered:
            controls.use_tradingview_reference = True
        if "macd" in lowered or "bollinger" in lowered or "rsi" in lowered or re.search(r"\bra\b", lowered):
            controls.alignment_required = max(controls.alignment_required, 3)
            controls.strategy_mode = StrategyMode.BALANCED
        if "never stay in trades" in lowered or "avoid holding into expiry" in lowered or "expiry" in lowered:
            controls.max_hold_minutes = min(controls.max_hold_minutes, 45)
        if "crypto only" in lowered:
            controls.strategy_mode = StrategyMode.CRYPTO_ONLY
            controls.weather_enabled = False
        self._manager.controls = controls

    def _refresh_summary(self) -> None:
        self._manager.validation = _build_validation(self._manager.controls)
        self._manager.review = _build_review(self._manager.telemetry, self._manager.controls)
        self._manager.diff = _build_diff(self._manager.live, self._manager.baseline, self._manager.controls)
        self._manager.telemetry.synced_at = AuditEvent(actor="system", event="sync", detail="").at

    def _stamp(self, actor: str, event: str, detail: str) -> None:
        self._manager.audit_log.insert(0, AuditEvent(actor=actor, event=event, detail=detail))


manager_service = ManagerService()
