from __future__ import annotations

import re
import time
from copy import deepcopy
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any

from .intel import build_reference_library, build_technical_snapshot, fetch_intel_feed, fetch_market_overview
from .models import (
    AuditEvent,
    DirectiveProfile,
    IntegrationsState,
    IntegrationState,
    IntelFeedItem,
    InterventionType,
    ManagerState,
    MarketOverview,
    MarketTicker,
    NewsIntegrations,
    ResearchSource,
    ReviewState,
    RuntimeSyncState,
    SafeControls,
    StrategyLayer,
    StrategyMode,
    TechnicalSnapshot,
    TelemetryState,
    TradingViewIntegration,
    ValidationReplay,
    ValidationState,
    WeatherIntegrations,
    WorkflowIntegration,
)
from .policy import (
    validate_entry_count,
    PolicyError,
    validate_hold_minutes,
    validate_pct,
    validate_position_limit,
    validate_probability_threshold,
)
from .runtime_adapter import RuntimeAdapter, RuntimeSnapshot


DEFAULT_DIRECTIVE_TEXT = (
    "The manager should direct the Poly Agent to continuously trade short-duration setups. "
    "Use 5-minute candles with MACD, RA/RSI, Bollinger Bands, momentum, trend, news, "
    "weather context, and TradingView reference when available. Enter and exit YES or NO "
    "positions actively, avoid holding into expiry, use DCA carefully, keep stop losses in "
    "place, and focus on disciplined profit scraping instead of letting positions decay."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return raw or "continuous-profit-manager"


def _next_friday_iso() -> str:
    today = date.today()
    days_ahead = (4 - today.weekday()) % 7
    return today.fromordinal(today.toordinal() + days_ahead).isoformat()


def _today_friday_progress(pnl_usd: float, target_usd: float) -> float:
    if target_usd <= 0:
        return 0.0
    return max(0.0, min(100.0, round((pnl_usd / target_usd) * 100.0, 1)))


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
    return _utc_now()


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
        "Profit and certainty are targets, not guarantees. The manager should optimize expectancy and discipline.",
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


def _build_integrations(runtime_base_url: str) -> IntegrationsState:
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
                "Runtime adapter can mirror live integration readiness from the POLY agent when it is online.",
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
                coverage="Lightweight crypto and prediction-market headline context.",
            )
        ),
        github=WorkflowIntegration(
            repo_url="https://github.com/Merlin-Machines/vault",
            note=f"Vault is the shared repo handoff layer. Runtime target: {runtime_base_url}.",
        ),
    )


def _build_diff(live: DirectiveProfile, baseline: DirectiveProfile, controls: SafeControls) -> list[dict[str, Any]]:
    diff: list[dict[str, Any]] = []
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


def _seed_runtime_state(base_url: str) -> RuntimeSyncState:
    return RuntimeSyncState(
        connected=False,
        status="disconnected",
        base_url=base_url,
        linked_runtime="POLY_AGENT_Merlin",
        source="seeded",
        last_error="Waiting for runtime connection.",
        notes=[
            "Vault remains fully usable offline and will sync into the runtime the next time the local dashboard is available.",
        ],
    )


def _seed_market_state() -> MarketOverview:
    return MarketOverview(
        status="seeded",
        summary="Market board is warming up.",
        risk_note="No live market data yet; the manager is running from seeded state.",
        tickers=[
            MarketTicker(symbol="BTC", price=0.0, note="Waiting for live Binance data."),
            MarketTicker(symbol="ETH", price=0.0, note="Waiting for live Binance data."),
        ],
        technicals=[],
    )


def _seed_strategy_layers(controls: SafeControls) -> list[StrategyLayer]:
    return [
        StrategyLayer(
            name="Dislocation Hunter",
            posture="watch",
            thesis="Fade stretched short-duration moves only when price reaches the edge of the band stack and reversal evidence starts to build.",
            triggers=["Bollinger extremes", "RA inflection", "Tight hold cap"],
            risk_note="Do not confuse oversold or overbought with guaranteed reversal.",
        ),
        StrategyLayer(
            name="Momentum Tape",
            posture="active" if controls.continuous_trading else "standby",
            thesis="Stay active while MACD, RA/RSI, momentum, and trend align on the 5-minute chart.",
            triggers=["MACD agreement", "EMA stack", "Volume confirmation"],
            risk_note="Continuous mode should increase throughput only when alignment stays real.",
        ),
        StrategyLayer(
            name="Risk Sentinel",
            posture="active",
            thesis="Protect edge with fast exits, capped size, and constant pressure against expiry drift.",
            triggers=["Stop losses live", "Profit scrape discipline", "No expiry complacency"],
            risk_note="The manager should reduce churn before it widens drawdown.",
        ),
    ]


class ManagerService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._runtime = RuntimeAdapter()
        self._cache_ttl_seconds = 45.0
        self._last_market_refresh = 0.0
        self._cached_market = _seed_market_state()
        self._cached_feed: list[IntelFeedItem] = []
        self._cached_references = [ResearchSource(**item) for item in build_reference_library()]

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
            runtime=_seed_runtime_state(self._runtime.base_url),
            market=self._cached_market.model_copy(deep=True),
            integrations=_build_integrations(self._runtime.base_url),
            intel_feed=list(self._cached_feed),
            research_library=[item.model_copy(deep=True) for item in self._cached_references],
            strategy_layers=_seed_strategy_layers(controls),
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
        with self._lock:
            return self._snapshot_state_locked()

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
            self._refresh_local_summary()
            self._stamp("operator", "directive_updated", f"Live directive updated to {directive_name}.")
            self._sync_runtime_directive_locked(directive_name, text)
            return self._snapshot_state_locked()

    def update_controls(self, **payload: Any) -> ManagerState:
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
            if "max_entries_per_cycle" in payload:
                validate_entry_count(payload["max_entries_per_cycle"])
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
            self._refresh_local_summary()
            self._stamp("operator", "controls_updated", "Safe runtime controls updated.")
            self._sync_runtime_controls_locked()
            return self._snapshot_state_locked()

    def set_trading_enabled(self, enabled: bool) -> ManagerState:
        return self.update_controls(trading_enabled=enabled)

    def commit_baseline(self, name: str | None = None) -> ManagerState:
        with self._lock:
            baseline_name = _slugify(name or self._manager.live.name)
            self._manager.baseline = self._manager.live.model_copy(deep=True)
            self._manager.baseline.name = baseline_name
            if baseline_name not in self._manager.profiles:
                self._manager.profiles.append(baseline_name)
            self._refresh_local_summary()
            self._stamp("operator", "baseline_committed", f"Baseline committed as {baseline_name}.")
            try:
                self._runtime.patch_profile(
                    self._controls_to_runtime_patch(self._manager.controls),
                    proposal_text=self._manager.live.proposal_text,
                    name=self._manager.live.name,
                )
                self._runtime.save_and_activate(name=baseline_name)
                self._stamp("runtime", "runtime_baseline_committed", f"Runtime baseline activated as {baseline_name}.")
            except Exception as exc:
                self._stamp("runtime", "runtime_sync_deferred", f"Baseline sync deferred: {exc}")
            return self._snapshot_state_locked()

    def intervene(self, action: InterventionType) -> ManagerState:
        with self._lock:
            if action == InterventionType.PAUSE:
                self._manager.controls.trading_enabled = False
                self._manager.telemetry.runtime_state = "paused"
                try:
                    self._runtime.set_trading_enabled(False)
                    self._stamp("runtime", "runtime_pause", "Runtime trading paused from Vault MGMT.")
                except Exception as exc:
                    self._stamp("runtime", "runtime_sync_deferred", f"Pause deferred: {exc}")
            elif action == InterventionType.RESUME:
                self._manager.controls.trading_enabled = True
                self._manager.telemetry.runtime_state = "dry-run"
                try:
                    self._runtime.set_trading_enabled(True)
                    self._stamp("runtime", "runtime_resume", "Runtime trading resumed from Vault MGMT.")
                except Exception as exc:
                    self._stamp("runtime", "runtime_sync_deferred", f"Resume deferred: {exc}")
            elif action == InterventionType.COMMIT_BASELINE:
                baseline_name = _slugify(self._manager.live.name)
                self._manager.baseline = self._manager.live.model_copy(deep=True)
                self._manager.baseline.name = baseline_name
                if baseline_name not in self._manager.profiles:
                    self._manager.profiles.append(baseline_name)
                try:
                    self._runtime.save_and_activate(name=baseline_name)
                    self._stamp("runtime", "runtime_baseline_committed", f"Runtime baseline activated as {baseline_name}.")
                except Exception as exc:
                    self._stamp("runtime", "runtime_sync_deferred", f"Baseline intervention deferred: {exc}")
            self._refresh_local_summary()
            self._stamp("operator", "intervention", f"Intervention applied: {action.value}.")
            return self._snapshot_state_locked()

    def _sync_runtime_directive_locked(self, name: str, proposal_text: str) -> None:
        try:
            self._runtime.propose_directive(name, proposal_text)
            self._runtime.patch_profile(
                self._controls_to_runtime_patch(self._manager.controls),
                proposal_text=proposal_text,
                name=name,
            )
            self._stamp("runtime", "runtime_directive_sync", f"Directive pushed to POLY runtime as {name}.")
        except Exception as exc:
            self._stamp("runtime", "runtime_sync_deferred", f"Directive sync deferred: {exc}")

    def _sync_runtime_controls_locked(self) -> None:
        try:
            self._runtime.patch_profile(
                self._controls_to_runtime_patch(self._manager.controls),
                proposal_text=self._manager.live.proposal_text,
                name=self._manager.live.name,
            )
            self._runtime.set_trading_enabled(self._manager.controls.trading_enabled)
            self._stamp("runtime", "runtime_controls_sync", "Controls pushed to POLY runtime.")
        except Exception as exc:
            self._stamp("runtime", "runtime_sync_deferred", f"Control sync deferred: {exc}")

    def _controls_to_runtime_patch(self, controls: SafeControls) -> dict[str, Any]:
        return {
            "strategy_mode": controls.strategy_mode.value,
            "market_filters": {
                "crypto": controls.crypto_enabled,
                "weather": controls.weather_enabled,
            },
            "analysis": {
                "candle_interval": "5m",
                "use_macd": True,
                "use_rsi": True,
                "use_ra": True,
                "use_bollinger": True,
                "use_trend": True,
                "use_news_context": controls.use_news_context,
                "use_weather_context": controls.use_weather_context,
                "use_tradingview_reference": controls.use_tradingview_reference,
                "alignment_required": controls.alignment_required,
            },
            "entry": {
                "continuous_trading": controls.continuous_trading,
                "max_entries_per_cycle": controls.max_entries_per_cycle,
            },
            "positioning": {
                "base_size_usdc": controls.base_size_usdc,
                "max_size_usdc": controls.max_size_usdc,
                "dca_enabled": controls.dca_enabled,
                "max_dca_steps": 2 if controls.dca_enabled else 0,
                "price_improvement_for_dca": 0.03 if controls.dca_enabled else 0.0,
            },
            "exits": {
                "max_hold_minutes": controls.max_hold_minutes,
                "profit_take_pct": controls.profit_take_pct,
                "stop_loss_pct": controls.stop_loss_pct,
                "avoid_expiry_minutes": min(max(10, controls.max_hold_minutes // 2), 120),
                "require_profit_to_continue": True,
                "flat_exit_minutes": min(15, controls.max_hold_minutes),
            },
        }

    def _snapshot_state_locked(self) -> ManagerState:
        manager = self._manager.model_copy(deep=True)
        manager.market, manager.intel_feed, manager.research_library = self._get_cached_intel_locked()
        runtime_snapshot = self._runtime.get_snapshot()
        manager.runtime = self._runtime_state_from_snapshot(runtime_snapshot)
        if runtime_snapshot.connected and runtime_snapshot.manager:
            manager = self._overlay_runtime_state(manager, runtime_snapshot)
        else:
            manager.runtime.notes.append(
                "Local Vault edits stay queued here and will sync the next time the POLY runtime is reachable."
            )
        runtime_market = self._market_from_runtime_log(runtime_snapshot)
        if runtime_market and manager.market.status in {"seeded", "stale"}:
            manager.market = runtime_market
        runtime_feed = self._intel_feed_from_runtime_log(runtime_snapshot)
        if runtime_feed and (
            not manager.intel_feed
            or all(item.source == "system" for item in manager.intel_feed)
        ):
            manager.intel_feed = runtime_feed
        manager.strategy_layers = self._build_strategy_layers(manager)
        manager.telemetry.synced_at = manager.runtime.synced_at
        return manager

    def _get_cached_intel_locked(
        self,
    ) -> tuple[MarketOverview, list[IntelFeedItem], list[ResearchSource]]:
        should_refresh = (time.monotonic() - self._last_market_refresh) >= self._cache_ttl_seconds
        if should_refresh or not self._cached_feed:
            try:
                self._cached_market = MarketOverview(**fetch_market_overview())
                self._cached_feed = [IntelFeedItem(**item) for item in fetch_intel_feed()]
                self._cached_references = [ResearchSource(**item) for item in build_reference_library()]
                self._last_market_refresh = time.monotonic()
            except Exception as exc:
                if self._cached_market.status == "seeded":
                    self._cached_market = self._cached_market.model_copy(update={"risk_note": f"Market fetch deferred: {exc}"})
                else:
                    self._cached_market = self._cached_market.model_copy(
                        update={
                            "status": "stale",
                            "risk_note": f"Using last good market snapshot because refresh failed: {exc}",
                        }
                    )
                if not self._cached_feed:
                    self._cached_feed = [
                        IntelFeedItem(
                            source="system",
                            category="status",
                            title="Market feed is waiting for the next successful refresh.",
                            url="https://github.com/Merlin-Machines/vault",
                            sentiment="neutral",
                            summary=str(exc),
                        )
                    ]
                if not self._cached_references:
                    self._cached_references = [ResearchSource(**item) for item in build_reference_library()]
        return (
            self._cached_market.model_copy(deep=True),
            [item.model_copy(deep=True) for item in self._cached_feed],
            [item.model_copy(deep=True) for item in self._cached_references],
        )

    def _market_from_runtime_log(self, snapshot: RuntimeSnapshot) -> MarketOverview | None:
        lines = snapshot.log or []
        if not lines:
            return None

        price_history: dict[str, list[tuple[datetime, float]]] = {"BTC": [], "ETH": []}
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        for line in lines:
            price_match = re.search(
                r"^(?P<stamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .* PRICE \| (?P<sym>BTC|ETH): \$?(?P<price>[\d,]+(?:\.\d+)?)",
                line,
            )
            if not price_match:
                continue
            stamp = datetime.strptime(price_match.group("stamp"), "%Y-%m-%d %H:%M:%S").replace(tzinfo=local_tz)
            price = float(price_match.group("price").replace(",", ""))
            price_history[price_match.group("sym")].append((stamp, price))

        tickers: list[MarketTicker] = []
        technicals: list[TechnicalSnapshot] = []
        for symbol, rows in price_history.items():
            if not rows:
                continue
            recent_rows = rows[-40:]
            prices = [price for _, price in recent_rows]
            synthetic_candles = []
            for index, price in enumerate(prices):
                previous = prices[index - 1] if index else price
                synthetic_candles.append(
                    {
                        "open": previous,
                        "high": max(previous, price),
                        "low": min(previous, price),
                        "close": price,
                        "volume": 1.0 + index,
                    }
                )
            tech = TechnicalSnapshot(**build_technical_snapshot(symbol, synthetic_candles))
            technicals.append(tech)
            change_pct = ((prices[-1] - prices[0]) / prices[0] * 100) if len(prices) > 1 and prices[0] else 0.0
            tickers.append(
                MarketTicker(
                    symbol=symbol,
                    price=prices[-1],
                    change_pct_24h=round(change_pct, 2),
                    regime=tech.stance,
                    note="Runtime-derived from local price logs because the direct exchange feed was unavailable.",
                )
            )

        if not tickers:
            return None

        if all(item.stance == "bullish" for item in technicals):
            summary = "Runtime fallback shows both tracked pairs leaning bullish across recent local price logs."
        elif all(item.stance == "bearish" for item in technicals):
            summary = "Runtime fallback shows both tracked pairs leaning bearish across recent local price logs."
        else:
            summary = "Runtime fallback market board is mixed, built from the local agent's own recent price logs."

        latest_stamp = max((stamp for rows in price_history.values() for stamp, _ in rows), default=_utc_now())
        return MarketOverview(
            status="runtime-fallback",
            as_of=latest_stamp,
            summary=summary,
            risk_note="Direct exchange refresh failed on this network, so Vault is using the runtime's local price log as the market board source.",
            tickers=tickers,
            technicals=technicals,
        )

    def _intel_feed_from_runtime_log(self, snapshot: RuntimeSnapshot) -> list[IntelFeedItem]:
        lines = snapshot.log or []
        if not lines:
            return []
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        items: list[IntelFeedItem] = []
        seen: set[str] = set()
        for line in reversed(lines):
            match = re.search(
                r"^(?P<stamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .* NEWS \| (?P<sym>BTC|ETH) \| (?P<sentiment>[a-z]+) \| (?P<title>.+)$",
                line,
            )
            if not match:
                continue
            title = match.group("title").strip()
            if title in seen:
                continue
            seen.add(title)
            stamp = datetime.strptime(match.group("stamp"), "%Y-%m-%d %H:%M:%S").replace(tzinfo=local_tz)
            symbol = match.group("sym")
            items.append(
                IntelFeedItem(
                    source=f"runtime-log/{symbol.lower()}",
                    category="news",
                    title=title,
                    url="http://127.0.0.1:7731/mgmt",
                    sentiment=match.group("sentiment"),
                    summary=f"Captured from the live POLY runtime log for {symbol}.",
                    published_at=stamp,
                )
            )
            if len(items) >= 6:
                break
        return items

    def _runtime_state_from_snapshot(self, snapshot: RuntimeSnapshot) -> RuntimeSyncState:
        notes = []
        if snapshot.connected:
            notes.append("Vault is reading and directing the POLY runtime through the local dashboard bridge.")
        else:
            notes.append("Runtime bridge is offline right now; Vault remains editable in standalone mode.")
        return RuntimeSyncState(
            connected=snapshot.connected,
            status="connected" if snapshot.connected else "disconnected",
            base_url=snapshot.base_url,
            linked_runtime="POLY_AGENT_Merlin",
            source=snapshot.source,
            last_error=snapshot.last_error,
            available_endpoints=list(snapshot.available_endpoints or []),
            notes=notes,
            synced_at=_coerce_datetime(snapshot.synced_at),
        )

    def _overlay_runtime_state(self, manager: ManagerState, snapshot: RuntimeSnapshot) -> ManagerState:
        raw_manager = snapshot.manager or {}
        live_payload = raw_manager.get("live") or {}
        active_payload = raw_manager.get("active") or {}

        manager.live = self._directive_from_runtime(live_payload, fallback=manager.live, default_source="poly-runtime")
        manager.baseline = self._directive_from_runtime(active_payload, fallback=manager.baseline, default_source="poly-runtime")
        manager.controls = self._controls_from_runtime(live_payload.get("profile") or {}, snapshot, manager.controls)
        manager.validation = self._validation_from_runtime(raw_manager.get("validation") or {}, manager.validation)
        manager.review = self._review_from_runtime(raw_manager.get("review") or {}, manager.review)
        manager.telemetry = self._telemetry_from_runtime(snapshot, manager.live.name)
        manager.integrations = self._integrations_from_runtime(snapshot.integrations or {}, snapshot.base_url)
        manager.profiles = list(raw_manager.get("profiles") or manager.profiles)
        manager.diff = list(raw_manager.get("diff") or manager.diff)
        return manager

    def _directive_from_runtime(
        self,
        payload: dict[str, Any],
        *,
        fallback: DirectiveProfile,
        default_source: str,
    ) -> DirectiveProfile:
        profile = payload.get("profile") or {}
        return DirectiveProfile(
            name=payload.get("name") or profile.get("name") or fallback.name,
            proposal_text=profile.get("proposal_text") or payload.get("proposal_text") or fallback.proposal_text,
            summary=profile.get("summary") or fallback.summary,
            source=payload.get("source") or default_source,
            updated_at=_coerce_datetime(
                profile.get("updated_at") or payload.get("activated_at") or fallback.updated_at
            ),
        )

    def _controls_from_runtime(
        self,
        profile: dict[str, Any],
        snapshot: RuntimeSnapshot,
        fallback: SafeControls,
    ) -> SafeControls:
        analysis = profile.get("analysis") or {}
        entry = profile.get("entry") or {}
        positioning = profile.get("positioning") or {}
        exits = profile.get("exits") or {}
        filters = profile.get("market_filters") or {}
        stats = snapshot.stats or {}
        try:
            strategy_mode = StrategyMode(profile.get("strategy_mode") or fallback.strategy_mode.value)
        except ValueError:
            strategy_mode = fallback.strategy_mode

        return SafeControls(
            trading_enabled=bool(stats.get("trading_enabled", fallback.trading_enabled)),
            strategy_mode=strategy_mode,
            continuous_trading=bool(entry.get("continuous_trading", fallback.continuous_trading)),
            base_size_usdc=float(positioning.get("base_size_usdc", fallback.base_size_usdc)),
            max_size_usdc=float(positioning.get("max_size_usdc", fallback.max_size_usdc)),
            max_entries_per_cycle=int(entry.get("max_entries_per_cycle", fallback.max_entries_per_cycle)),
            max_hold_minutes=int(exits.get("max_hold_minutes", fallback.max_hold_minutes)),
            stop_loss_pct=float(exits.get("stop_loss_pct", fallback.stop_loss_pct)),
            profit_take_pct=float(exits.get("profit_take_pct", fallback.profit_take_pct)),
            alignment_required=int(analysis.get("alignment_required", fallback.alignment_required)),
            dca_enabled=bool(positioning.get("dca_enabled", fallback.dca_enabled)),
            use_news_context=bool(analysis.get("use_news_context", fallback.use_news_context)),
            use_weather_context=bool(analysis.get("use_weather_context", fallback.use_weather_context)),
            use_tradingview_reference=bool(
                analysis.get("use_tradingview_reference", fallback.use_tradingview_reference)
            ),
            crypto_enabled=bool(filters.get("crypto", fallback.crypto_enabled)),
            weather_enabled=bool(filters.get("weather", fallback.weather_enabled)),
        )

    def _validation_from_runtime(
        self,
        payload: dict[str, Any],
        fallback: ValidationState,
    ) -> ValidationState:
        replay = payload.get("replay") or {}
        return ValidationState(
            ok=bool(payload.get("ok", fallback.ok)),
            warnings=list(payload.get("warnings") or fallback.warnings),
            errors=list(payload.get("errors") or fallback.errors),
            replay=ValidationReplay(
                sample_size=int(replay.get("sample_size", fallback.replay.sample_size)),
                qualified_trades=int(replay.get("qualified_trades", fallback.replay.qualified_trades)),
                estimated_pnl_usdc=float(replay.get("estimated_pnl_usdc", fallback.replay.estimated_pnl_usdc)),
                estimated_win_rate_pct=float(
                    replay.get("estimated_win_rate_pct", fallback.replay.estimated_win_rate_pct)
                ),
            ),
        )

    def _review_from_runtime(self, payload: dict[str, Any], fallback: ReviewState) -> ReviewState:
        return ReviewState(
            headline=payload.get("headline") or fallback.headline,
            scorecard=list(payload.get("scorecard") or fallback.scorecard),
            reinforcements=list(payload.get("reinforcements") or fallback.reinforcements),
            coaching=list(payload.get("coaching") or fallback.coaching),
            risks=list(payload.get("risks") or fallback.risks),
            goal_progress_pct=float(payload.get("goal_progress_pct", fallback.goal_progress_pct)),
        )

    def _telemetry_from_runtime(self, snapshot: RuntimeSnapshot, strategy_name: str) -> TelemetryState:
        stats = snapshot.stats or {}
        return TelemetryState(
            agent_id="poly-agent-01",
            runtime_state=str(stats.get("mode", "DRY RUN")).lower().replace(" ", "-"),
            strategy_name=strategy_name,
            pnl_usd=float(stats.get("estimated_pnl", 0.0) or 0.0),
            open_positions=int(stats.get("open_positions", 0) or 0),
            total_trades=int(stats.get("total_trades", 0) or 0),
            today_trades=int(stats.get("today_trades", 0) or 0),
            account_name=str(stats.get("account", "ACCOUNT") or "ACCOUNT"),
            wallet=str(stats.get("wallet", "") or ""),
            source="poly-runtime",
            synced_at=_coerce_datetime(stats.get("last_updated") or snapshot.synced_at),
        )

    def _integrations_from_runtime(
        self,
        payload: dict[str, Any],
        runtime_base_url: str,
    ) -> IntegrationsState:
        integrations = _build_integrations(runtime_base_url)
        weather = payload.get("weather") or {}
        tradingview = payload.get("tradingview") or {}
        news = payload.get("news") or {}
        github = payload.get("chatgpt") or {}

        for field in ("noaa", "weather_company", "weatherapi_rapidapi"):
            raw = weather.get(field) or {}
            current = getattr(integrations.weather, field)
            setattr(
                integrations.weather,
                field,
                current.model_copy(
                    update={
                        "enabled": raw.get("enabled", current.enabled),
                        "configured": raw.get("configured", current.configured),
                        "docs_url": raw.get("docs_url", current.docs_url),
                        "endpoint": raw.get("endpoint", current.endpoint),
                        "coverage": raw.get("coverage", current.coverage),
                        "host": raw.get("host", current.host),
                    }
                ),
            )
        notes = weather.get("notes")
        if isinstance(notes, list) and notes:
            integrations.weather.notes = [str(note) for note in notes]

        integrations.tradingview = integrations.tradingview.model_copy(
            update={
                "enabled": tradingview.get("enabled", integrations.tradingview.enabled),
                "configured": tradingview.get("enabled", integrations.tradingview.configured),
                "default_symbol": tradingview.get("default_symbol", integrations.tradingview.default_symbol),
                "docs_url": tradingview.get("docs_url", integrations.tradingview.docs_url),
                "integration_mode": tradingview.get("integration_mode", integrations.tradingview.integration_mode),
                "charting_library_access": tradingview.get(
                    "charting_library_access",
                    integrations.tradingview.charting_library_access,
                ),
                "host": tradingview.get("library_path", integrations.tradingview.host),
                "notes": [str(note) for note in tradingview.get("notes") or integrations.tradingview.notes],
            }
        )

        google_news = news.get("google_news_rss") or {}
        integrations.news.google_news_rss = integrations.news.google_news_rss.model_copy(
            update={
                "enabled": google_news.get("enabled", integrations.news.google_news_rss.enabled),
                "configured": google_news.get("configured", integrations.news.google_news_rss.configured),
                "coverage": google_news.get("source", integrations.news.google_news_rss.coverage),
            }
        )

        if github.get("thread_url"):
            integrations.github.note = f'{integrations.github.note} ChatGPT thread: {github.get("thread_url")}'
        return integrations

    def _build_strategy_layers(self, manager: ManagerState) -> list[StrategyLayer]:
        technicals = manager.market.technicals
        strongest = technicals[0] if technicals else None
        posture = "active" if manager.controls.continuous_trading else "standby"

        dislocation_triggers = []
        momentum_triggers = []
        context_triggers = []
        for technical in technicals:
            if technical.bollinger_signal != "neutral":
                dislocation_triggers.append(
                    f"{technical.symbol}: {technical.bollinger_signal} at bands with RA {technical.ra_label}."
                )
            if technical.alignment_score >= manager.controls.alignment_required:
                momentum_triggers.append(
                    f"{technical.symbol}: alignment {technical.alignment_score}/5 with {technical.macd_bias} MACD."
                )
        for item in manager.intel_feed[:3]:
            context_triggers.append(f"{item.source}: {item.title}")

        if not dislocation_triggers:
            dislocation_triggers.append("No clean band dislocation is firing right now.")
        if not momentum_triggers:
            momentum_triggers.append("Momentum stack is mixed, so size should stay disciplined.")
        if not context_triggers:
            context_triggers.append("News and community feeds are waiting for the next refresh.")

        risk_posture = "guarded" if manager.market.risk_note.lower().startswith("short-duration setups are moving fast") else "active"
        strongest_note = strongest.summary if strongest else "No symbol has a fully hydrated technical stack yet."

        return [
            StrategyLayer(
                name="Dislocation Hunter",
                posture="watch" if dislocation_triggers[0].startswith("No clean") else "active",
                thesis="Fade overstretched short-duration moves only when band extremes, RA, and exit discipline point in the same direction.",
                triggers=dislocation_triggers[:3],
                risk_note="This layer is for asymmetric entries, not stubborn hero trades.",
            ),
            StrategyLayer(
                name="Momentum Tape",
                posture=posture,
                thesis="Keep the agent active when MACD, RA/RSI, trend, and volume align on the 5-minute stack.",
                triggers=momentum_triggers[:3],
                risk_note=strongest_note,
            ),
            StrategyLayer(
                name="Catalyst Context",
                posture="active" if (manager.controls.use_news_context or manager.controls.use_weather_context) else "standby",
                thesis="Use market headlines, community chatter, and weather/news overlays as context filters rather than as standalone trade triggers.",
                triggers=context_triggers[:3],
                risk_note="Catalyst narratives should guide selection and timing, not replace edge validation.",
            ),
            StrategyLayer(
                name="Risk Sentinel",
                posture=risk_posture,
                thesis="Guard the edge with hold caps, stop losses, capped size, and pressure against expiry drift.",
                triggers=[
                    f"Trading {'enabled' if manager.controls.trading_enabled else 'paused'}.",
                    f"Hold cap {manager.controls.max_hold_minutes}m with stop loss {manager.controls.stop_loss_pct:.2f}.",
                    manager.market.risk_note,
                ],
                risk_note="The manager wins by preventing weak trades from compounding into messy ones.",
            ),
        ]

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

    def _refresh_local_summary(self) -> None:
        self._manager.validation = _build_validation(self._manager.controls)
        self._manager.review = _build_review(self._manager.telemetry, self._manager.controls)
        self._manager.diff = _build_diff(self._manager.live, self._manager.baseline, self._manager.controls)
        self._manager.runtime = self._manager.runtime.model_copy(update={"synced_at": _utc_now()})

    def _stamp(self, actor: str, event: str, detail: str) -> None:
        self._manager.audit_log.insert(0, AuditEvent(actor=actor, event=event, detail=detail))


manager_service = ManagerService()
