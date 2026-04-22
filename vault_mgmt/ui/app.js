const toast = document.getElementById("toast");

const state = {
  manager: null,
  renderedSymbol: null,
  directiveDirty: false,
  nameDirty: false,
  controlsDirty: false,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMoney(value) {
  const numeric = Number(value || 0);
  return `$${numeric.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
}

function formatPct(value, digits = 2) {
  return `${Number(value || 0).toFixed(digits)}%`;
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.remove("hidden");
  toast.style.background = isError ? "#7d2f1b" : "#1f1a15";
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 2600);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Request failed");
  }
  return response.json();
}

function metric(label, value, meta = "") {
  return `
    <div class="metric">
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${escapeHtml(value)}</span>
      <span class="meta">${escapeHtml(meta)}</span>
    </div>
  `;
}

function syncForm(manager) {
  if (!state.nameDirty) {
    document.getElementById("profile-name").value = manager.live.name;
  }
  if (!state.directiveDirty) {
    document.getElementById("directive-text").value = manager.live.proposal_text;
  }
  if (state.controlsDirty) {
    return;
  }
  const controls = manager.controls;
  document.getElementById("strategy-mode").value = controls.strategy_mode;
  document.getElementById("base-size").value = controls.base_size_usdc;
  document.getElementById("max-size").value = controls.max_size_usdc;
  document.getElementById("max-entries").value = controls.max_entries_per_cycle;
  document.getElementById("max-hold").value = controls.max_hold_minutes;
  document.getElementById("stop-loss").value = controls.stop_loss_pct;
  document.getElementById("profit-take").value = controls.profit_take_pct;
  document.getElementById("alignment-required").value = controls.alignment_required;
  document.getElementById("continuous-trading").checked = controls.continuous_trading;
  document.getElementById("dca-enabled").checked = controls.dca_enabled;
  document.getElementById("crypto-enabled").checked = controls.crypto_enabled;
  document.getElementById("weather-enabled").checked = controls.weather_enabled;
  document.getElementById("use-news").checked = controls.use_news_context;
  document.getElementById("use-weather").checked = controls.use_weather_context;
  document.getElementById("use-tradingview").checked = controls.use_tradingview_reference;
}

function renderTop(manager) {
  const { live, baseline, controls, review, telemetry, runtime, market, integrations } = manager;
  document.getElementById("runtime-pill").textContent = runtime.connected ? "Runtime linked" : "Runtime queued";
  document.getElementById("live-pill").textContent = `Live: ${live.name}`;
  document.getElementById("baseline-pill").textContent = `Baseline: ${baseline.name}`;
  document.getElementById("mode-pill").textContent = `Mode: ${controls.strategy_mode}`;
  document.getElementById("hero-review").textContent = review.headline;
  document.getElementById("toggle-trading").textContent = controls.trading_enabled ? "Pause Trading" : "Resume Trading";

  const runtimeMeta = runtime.connected ? runtime.base_url : "standalone mode";
  const marketSummary = market.summary || "Market summary pending.";
  document.getElementById("metrics").innerHTML = [
    metric("P&L USD", formatMoney(telemetry.pnl_usd), review.scorecard[0] || ""),
    metric("Today Trades", String(telemetry.today_trades), `${telemetry.total_trades} total tracked`),
    metric("Open Positions", String(telemetry.open_positions), `Runtime: ${telemetry.runtime_state}`),
    metric("Market", market.status.toUpperCase(), marketSummary),
  ].join("");

  document.getElementById("runtime-note").textContent = runtime.notes.join(" ");
  document.getElementById("runtime-endpoints").innerHTML = (runtime.available_endpoints || []).length
    ? runtime.available_endpoints.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")
    : `<span class="tag muted">offline</span>`;

  const runtimeLink = document.getElementById("open-runtime-link");
  runtimeLink.href = `${runtime.base_url}/mgmt`;
  runtimeLink.textContent = runtime.connected ? "Open Runtime" : "Open Runtime Target";
  runtimeLink.title = runtimeMeta;

  document.getElementById("tv-symbol").value = integrations.tradingview.default_symbol || "BINANCE:BTCUSDT";
  renderTradingView(document.getElementById("tv-symbol").value, integrations.tradingview);
}

function renderReview(manager) {
  const blocks = [];
  const review = manager.review || {};
  (review.scorecard || []).forEach((line) => blocks.push(`<div class="item"><strong>Scorecard</strong><p>${escapeHtml(line)}</p></div>`));
  (review.reinforcements || []).forEach((line) => blocks.push(`<div class="item"><strong>Reinforce</strong><p>${escapeHtml(line)}</p></div>`));
  (review.coaching || []).forEach((line) => blocks.push(`<div class="item"><strong>Coach</strong><p>${escapeHtml(line)}</p></div>`));
  (review.risks || []).forEach((line) => blocks.push(`<div class="item"><strong>Risk</strong><p>${escapeHtml(line)}</p></div>`));
  document.getElementById("review-list").innerHTML = blocks.join("");
}

function renderValidation(manager) {
  const validation = manager.validation || {};
  const blocks = [];
  (validation.errors || []).forEach((line) => blocks.push(`<div class="item warn"><strong>Error</strong><p>${escapeHtml(line)}</p></div>`));
  (validation.warnings || []).forEach((line) => blocks.push(`<div class="item caution"><strong>Warning</strong><p>${escapeHtml(line)}</p></div>`));
  if (validation.replay) {
    blocks.push(
      `<div class="item">` +
      `<strong>Replay</strong>` +
      `<p>Sample ${escapeHtml(validation.replay.sample_size)} | Qualified ${escapeHtml(validation.replay.qualified_trades)} | ` +
      `Est P&amp;L ${escapeHtml(formatMoney(validation.replay.estimated_pnl_usdc))} | ` +
      `Est win rate ${escapeHtml(formatPct(validation.replay.estimated_win_rate_pct, 1))}</p>` +
      `</div>`
    );
  }
  document.getElementById("validation-list").innerHTML = blocks.join("");
}

function renderMarket(manager) {
  const market = manager.market || {};
  document.getElementById("market-summary").textContent = `${market.summary || "Waiting for market snapshot."} ${market.risk_note || ""}`.trim();

  document.getElementById("ticker-grid").innerHTML = (market.tickers || []).map((ticker) => `
    <div class="ticker-card">
      <div class="ticker-head">
        <strong>${escapeHtml(ticker.symbol)}</strong>
        <span class="tag ${escapeHtml(ticker.regime || "mixed")}">${escapeHtml(ticker.regime || "mixed")}</span>
      </div>
      <div class="ticker-price">${escapeHtml(formatMoney(ticker.price))}</div>
      <div class="ticker-meta">${escapeHtml(formatPct(ticker.change_pct_24h))} 24h | ${escapeHtml(formatMoney(ticker.quote_volume_usd || 0))} volume</div>
      <div class="ticker-meta">
        Funding ${ticker.funding_rate_pct == null ? "n/a" : escapeHtml(formatPct(ticker.funding_rate_pct, 4))} |
        OI ${ticker.open_interest_usd == null ? "n/a" : escapeHtml(formatMoney(ticker.open_interest_usd))}
      </div>
      <p>${escapeHtml(ticker.note || "")}</p>
    </div>
  `).join("");

  document.getElementById("technical-grid").innerHTML = (market.technicals || []).map((item) => `
    <div class="tech-card">
      <div class="tech-top">
        <strong>${escapeHtml(item.symbol)}</strong>
        <span class="tag ${escapeHtml(item.stance || "mixed")}">${escapeHtml(item.stance || "mixed")}</span>
      </div>
      <div class="tech-row">
        <span>RA</span>
        <span>${escapeHtml(item.ra_label)} (${escapeHtml(item.ra_score)})</span>
      </div>
      <div class="tech-row">
        <span>RSI</span>
        <span>${escapeHtml(item.rsi)}</span>
      </div>
      <div class="tech-row">
        <span>MACD</span>
        <span>${escapeHtml(item.macd_bias)} (${escapeHtml(item.macd_hist)})</span>
      </div>
      <div class="tech-row">
        <span>Bollinger</span>
        <span>${escapeHtml(item.bollinger_signal)} / ${escapeHtml(formatPct(item.bollinger_bandwidth_pct))}</span>
      </div>
      <div class="tech-row">
        <span>Momentum</span>
        <span>${escapeHtml(formatPct(item.momentum_pct))}</span>
      </div>
      <div class="tech-row">
        <span>ATR</span>
        <span>${escapeHtml(formatPct(item.atr_pct))}</span>
      </div>
      <div class="tech-row">
        <span>Volume</span>
        <span>${escapeHtml(`${Number(item.volume_ratio || 0).toFixed(2)}x`)}</span>
      </div>
      <div class="tech-row">
        <span>Alignment</span>
        <span>${escapeHtml(`${item.alignment_score}/5`)}</span>
      </div>
      <p>${escapeHtml(item.summary || "")}</p>
    </div>
  `).join("");
}

function renderLayers(manager) {
  document.getElementById("layers-list").innerHTML = (manager.strategy_layers || []).map((layer) => `
    <div class="item layer-card">
      <div class="item-head">
        <strong>${escapeHtml(layer.name)}</strong>
        <span class="tag ${escapeHtml(layer.posture || "watch")}">${escapeHtml(layer.posture || "watch")}</span>
      </div>
      <p>${escapeHtml(layer.thesis || "")}</p>
      <div class="trigger-list">${(layer.triggers || []).map((trigger) => `<span class="tag">${escapeHtml(trigger)}</span>`).join("")}</div>
      <div class="meta">${escapeHtml(layer.risk_note || "")}</div>
    </div>
  `).join("");
}

function renderIntel(manager) {
  document.getElementById("intel-list").innerHTML = (manager.intel_feed || []).map((item) => `
    <div class="item intel-card">
      <div class="item-head">
        <strong>${escapeHtml(item.title)}</strong>
        <span class="tag ${escapeHtml(item.sentiment || "neutral")}">${escapeHtml(item.sentiment || "neutral")}</span>
      </div>
      <p>${escapeHtml(item.summary || "")}</p>
      <div class="meta">
        ${escapeHtml(item.source)} | ${escapeHtml(item.category)}${item.published_at ? ` | ${escapeHtml(new Date(item.published_at).toLocaleString())}` : ""}
      </div>
      <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">Open source</a>
    </div>
  `).join("");
}

function renderResearch(manager) {
  document.getElementById("research-list").innerHTML = (manager.research_library || []).map((item) => `
    <div class="item">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.note || "")}</p>
      <div class="meta">${escapeHtml(item.source)} | ${escapeHtml(item.category)}</div>
      <a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.url)}</a>
    </div>
  `).join("");
}

function renderIntegrations(manager) {
  const integrations = manager.integrations || {};
  const weather = integrations.weather || {};
  const items = [];
  items.push(
    `<div class="item"><strong>GitHub workflow</strong>` +
    `<p><a href="${escapeHtml(integrations.github.repo_url)}" target="_blank" rel="noreferrer">${escapeHtml(integrations.github.repo_url)}</a></p>` +
    `<div class="meta">${escapeHtml(integrations.github.note || "")}</div></div>`
  );
  items.push(
    `<div class="item"><strong>NOAA</strong><p>${escapeHtml(weather.noaa.coverage || "")}</p>` +
    `<div class="meta">${escapeHtml(weather.noaa.endpoint || "")}</div></div>`
  );
  items.push(
    `<div class="item"><strong>Weather Company</strong><p>${escapeHtml(weather.weather_company.coverage || "")}</p>` +
    `<div class="meta">${escapeHtml(weather.weather_company.docs_url || "")}</div></div>`
  );
  items.push(
    `<div class="item"><strong>WeatherAPI via RapidAPI</strong><p>${escapeHtml(weather.weatherapi_rapidapi.coverage || "")}</p>` +
    `<div class="meta">${escapeHtml(weather.weatherapi_rapidapi.host || "")}</div></div>`
  );
  items.push(
    `<div class="item"><strong>TradingView</strong><p>${escapeHtml((integrations.tradingview.notes || []).join(" "))}</p>` +
    `<div class="meta">${escapeHtml(integrations.tradingview.docs_url || "")}</div></div>`
  );
  document.getElementById("integrations-list").innerHTML = items.join("");
  document.getElementById("chart-meta").textContent = `TradingView ${integrations.tradingview.integration_mode} | ${integrations.tradingview.default_symbol}`;
}

function renderDiffAudit(manager) {
  const diff = manager.diff || [];
  const audit = manager.audit_log || [];
  document.getElementById("diff-list").innerHTML = diff.length
    ? diff.map((item) => `
      <div class="diff-item">
        <strong>${escapeHtml(item.field)}</strong>
        <div class="meta">from ${escapeHtml(JSON.stringify(item.from))}</div>
        <div class="meta">to ${escapeHtml(JSON.stringify(item.to))}</div>
      </div>
    `).join("")
    : `<div class="item"><strong>No diff</strong><p>Live directive matches the current baseline.</p></div>`;

  document.getElementById("audit-list").innerHTML = audit.length
    ? audit.map((entry) => `
      <div class="audit-item">
        <strong>${escapeHtml(entry.event)}</strong>
        <p>${escapeHtml(entry.detail)}</p>
        <div class="meta">${escapeHtml(new Date(entry.at).toLocaleString())} | ${escapeHtml(entry.actor)}</div>
      </div>
    `).join("")
    : "";
}

function renderTradingView(symbol, config) {
  const cleaned = (symbol || config.default_symbol || "BINANCE:BTCUSDT").trim().toUpperCase();
  if (!cleaned || state.renderedSymbol === cleaned) {
    return;
  }
  state.renderedSymbol = cleaned;
  const stage = document.getElementById("tv-stage");
  stage.innerHTML = `<div class="tradingview-widget-container__widget"></div>`;
  const script = document.createElement("script");
  script.type = "text/javascript";
  script.async = true;
  script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
  script.text = JSON.stringify({
    autosize: true,
    symbol: cleaned,
    interval: "5",
    timezone: "America/New_York",
    theme: "light",
    style: "1",
    locale: "en",
    allow_symbol_change: true,
    calendar: false,
    support_host: "https://www.tradingview.com"
  });
  stage.appendChild(script);
}

async function refresh() {
  const manager = await request("/api/manager");
  state.manager = manager;
  syncForm(manager);
  renderTop(manager);
  renderReview(manager);
  renderValidation(manager);
  renderMarket(manager);
  renderLayers(manager);
  renderIntel(manager);
  renderResearch(manager);
  renderIntegrations(manager);
  renderDiffAudit(manager);
}

async function updateDirective() {
  try {
    await request("/api/manager/directive", {
      method: "POST",
      body: JSON.stringify({
        name: document.getElementById("profile-name").value,
        proposal_text: document.getElementById("directive-text").value,
      }),
    });
    state.directiveDirty = false;
    state.nameDirty = false;
    await refresh();
    showToast("Live directive updated.");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function applyControls() {
  try {
    await request("/api/manager/controls", {
      method: "POST",
      body: JSON.stringify({
        strategy_mode: document.getElementById("strategy-mode").value,
        base_size_usdc: Number(document.getElementById("base-size").value),
        max_size_usdc: Number(document.getElementById("max-size").value),
        max_entries_per_cycle: Number(document.getElementById("max-entries").value),
        max_hold_minutes: Number(document.getElementById("max-hold").value),
        stop_loss_pct: Number(document.getElementById("stop-loss").value),
        profit_take_pct: Number(document.getElementById("profit-take").value),
        alignment_required: Number(document.getElementById("alignment-required").value),
        continuous_trading: document.getElementById("continuous-trading").checked,
        dca_enabled: document.getElementById("dca-enabled").checked,
        crypto_enabled: document.getElementById("crypto-enabled").checked,
        weather_enabled: document.getElementById("weather-enabled").checked,
        use_news_context: document.getElementById("use-news").checked,
        use_weather_context: document.getElementById("use-weather").checked,
        use_tradingview_reference: document.getElementById("use-tradingview").checked,
      }),
    });
    state.controlsDirty = false;
    await refresh();
    showToast("Safe controls updated.");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function commitBaseline() {
  try {
    await request("/api/manager/baseline", {
      method: "POST",
      body: JSON.stringify({ name: document.getElementById("profile-name").value }),
    });
    await refresh();
    showToast("Baseline committed.");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function toggleTrading() {
  try {
    await request("/api/manager/trading", {
      method: "POST",
      body: JSON.stringify({ enabled: !state.manager.controls.trading_enabled }),
    });
    await refresh();
    showToast("Trading state updated.");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function intervene(action) {
  try {
    await request("/api/manager/intervention", {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    await refresh();
    showToast(`Intervention applied: ${action}`);
  } catch (error) {
    showToast(error.message, true);
  }
}

document.getElementById("refresh-now").addEventListener("click", () => refresh().catch((error) => showToast(error.message, true)));
document.getElementById("toggle-trading").addEventListener("click", toggleTrading);
document.getElementById("apply-controls").addEventListener("click", applyControls);
document.getElementById("update-directive").addEventListener("click", updateDirective);
document.getElementById("commit-baseline").addEventListener("click", commitBaseline);
document.getElementById("reload-chart").addEventListener("click", () => {
  state.renderedSymbol = null;
  renderTradingView(document.getElementById("tv-symbol").value, state.manager.integrations.tradingview);
});

document.querySelectorAll("[data-intervention]").forEach((button) => {
  button.addEventListener("click", () => intervene(button.dataset.intervention));
});

document.getElementById("directive-text").addEventListener("input", () => { state.directiveDirty = true; });
document.getElementById("profile-name").addEventListener("input", () => { state.nameDirty = true; });
[
  "strategy-mode",
  "base-size",
  "max-size",
  "max-entries",
  "max-hold",
  "stop-loss",
  "profit-take",
  "alignment-required",
  "continuous-trading",
  "dca-enabled",
  "crypto-enabled",
  "weather-enabled",
  "use-news",
  "use-weather",
  "use-tradingview",
].forEach((id) => {
  const el = document.getElementById(id);
  el.addEventListener("input", () => { state.controlsDirty = true; });
  el.addEventListener("change", () => { state.controlsDirty = true; });
});

refresh().catch((error) => showToast(error.message, true));
setInterval(() => refresh().catch(() => {}), 25000);
