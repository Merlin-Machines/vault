from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from statistics import mean
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


BINANCE_SPOT = "https://api.binance.com"
BINANCE_FUTURES = "https://fapi.binance.com"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _request_text(url: str, params: dict[str, Any] | None = None, timeout: float = 4.0) -> str:
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "Vault-MGMT/0.3"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _request_json(url: str, params: dict[str, Any] | None = None, timeout: float = 4.0) -> Any:
    return json.loads(_request_text(url, params=params, timeout=timeout))


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    series = [values[0]]
    for value in values[1:]:
        series.append((value - series[-1]) * multiplier + series[-1])
    return series


def _safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _parse_candles(rows: list[list[Any]]) -> list[dict[str, float]]:
    candles = []
    for row in rows:
        candles.append(
            {
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[7]),
            }
        )
    return candles


def build_technical_snapshot(symbol: str, candles: list[dict[str, float]]) -> dict[str, Any]:
    if len(candles) < 30:
        price = candles[-1]["close"] if candles else 0.0
        return {
            "symbol": symbol,
            "interval": "5m",
            "last_price": price,
            "ra_score": 0.0,
            "ra_label": "neutral",
            "rsi": 50.0,
            "momentum_pct": 0.0,
            "trend": "neutral",
            "ema_fast": price,
            "ema_slow": price,
            "macd": 0.0,
            "macd_signal": 0.0,
            "macd_hist": 0.0,
            "macd_bias": "neutral",
            "bollinger_upper": price,
            "bollinger_middle": price,
            "bollinger_lower": price,
            "bollinger_bandwidth_pct": 0.0,
            "bollinger_signal": "neutral",
            "atr_pct": 0.0,
            "volume_ratio": 1.0,
            "alignment_score": 0,
            "stance": "neutral",
            "summary": "Waiting for enough 5-minute candles.",
        }

    closes = [candle["close"] for candle in candles]
    highs = [candle["high"] for candle in candles]
    lows = [candle["low"] for candle in candles]
    volumes = [candle["volume"] for candle in candles]
    last_price = closes[-1]

    deltas = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains = [delta if delta > 0 else 0.0 for delta in deltas]
    losses = [-delta if delta < 0 else 0.0 for delta in deltas]
    avg_gain = _safe_mean(gains[-14:])
    avg_loss = _safe_mean(losses[-14:])
    rs = avg_gain / avg_loss if avg_loss else 0.0
    rsi = 100 - (100 / (1 + rs)) if rs else 50.0

    ema_fast_series = _ema(closes, 9)
    ema_slow_series = _ema(closes, 21)
    ema_fast = ema_fast_series[-1]
    ema_slow = ema_slow_series[-1]
    trend = "up" if ema_fast > ema_slow else "down" if ema_fast < ema_slow else "neutral"

    macd_series = [fast - slow for fast, slow in zip(_ema(closes, 12), _ema(closes, 26))]
    signal_series = _ema(macd_series, 9)
    macd = macd_series[-1]
    macd_signal = signal_series[-1]
    macd_hist = macd - macd_signal
    macd_bias = "bullish" if macd_hist > 0 else "bearish" if macd_hist < 0 else "neutral"

    lookback = closes[-20:]
    middle = _safe_mean(lookback)
    variance = _safe_mean([(value - middle) ** 2 for value in lookback])
    std_dev = math.sqrt(variance)
    upper = middle + 2 * std_dev
    lower = middle - 2 * std_dev
    bandwidth_pct = ((upper - lower) / middle * 100) if middle else 0.0
    if last_price >= upper:
        bollinger_signal = "overbought"
    elif last_price <= lower:
        bollinger_signal = "oversold"
    else:
        bollinger_signal = "neutral"

    true_ranges = []
    for index in range(1, len(candles)):
        high = highs[index]
        low = lows[index]
        prev_close = closes[index - 1]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = _safe_mean(true_ranges[-14:])
    atr_pct = (atr / last_price * 100) if last_price else 0.0

    momentum_pct = ((last_price - closes[-5]) / closes[-5] * 100) if closes[-5] else 0.0
    recent_range = atr if atr else max(last_price * 0.0025, 0.0001)
    ra_score = (last_price - closes[-5]) / recent_range
    if ra_score > 0.9:
        ra_label = "expanding-up"
    elif ra_score < -0.9:
        ra_label = "expanding-down"
    else:
        ra_label = "balanced"

    recent_volume = volumes[-1]
    average_volume = _safe_mean(volumes[-20:])
    volume_ratio = (recent_volume / average_volume) if average_volume else 1.0

    bullish_signals = 0
    bearish_signals = 0
    if rsi >= 52:
        bullish_signals += 1
    elif rsi <= 48:
        bearish_signals += 1
    if macd_hist > 0:
        bullish_signals += 1
    elif macd_hist < 0:
        bearish_signals += 1
    if trend == "up":
        bullish_signals += 1
    elif trend == "down":
        bearish_signals += 1
    if momentum_pct > 0.2:
        bullish_signals += 1
    elif momentum_pct < -0.2:
        bearish_signals += 1
    if volume_ratio >= 1.15 and bullish_signals >= bearish_signals:
        bullish_signals += 1
    elif volume_ratio >= 1.15 and bearish_signals > bullish_signals:
        bearish_signals += 1
    if bollinger_signal == "oversold":
        bullish_signals += 1
    elif bollinger_signal == "overbought":
        bearish_signals += 1

    alignment_score = max(bullish_signals, bearish_signals)
    if bullish_signals > bearish_signals and alignment_score >= 3:
        stance = "bullish"
    elif bearish_signals > bullish_signals and alignment_score >= 3:
        stance = "bearish"
    else:
        stance = "mixed"

    summary = (
        f"{symbol} is {stance} on the 5-minute stack with RSI {rsi:.1f}, "
        f"MACD {macd_bias}, RA {ra_label}, and volume {volume_ratio:.2f}x average."
    )

    return {
        "symbol": symbol,
        "interval": "5m",
        "last_price": round(last_price, 4),
        "ra_score": round(ra_score, 2),
        "ra_label": ra_label,
        "rsi": round(rsi, 1),
        "momentum_pct": round(momentum_pct, 2),
        "trend": trend,
        "ema_fast": round(ema_fast, 4),
        "ema_slow": round(ema_slow, 4),
        "macd": round(macd, 4),
        "macd_signal": round(macd_signal, 4),
        "macd_hist": round(macd_hist, 4),
        "macd_bias": macd_bias,
        "bollinger_upper": round(upper, 4),
        "bollinger_middle": round(middle, 4),
        "bollinger_lower": round(lower, 4),
        "bollinger_bandwidth_pct": round(bandwidth_pct, 2),
        "bollinger_signal": bollinger_signal,
        "atr_pct": round(atr_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "alignment_score": alignment_score,
        "stance": stance,
        "summary": summary,
    }


def _ticker_note(change_pct: float, spread_pct: float | None) -> str:
    direction = "firm" if change_pct > 1 else "soft" if change_pct < -1 else "balanced"
    spread_note = f"{spread_pct:.3f}% spread" if spread_pct is not None else "spread unavailable"
    return f"24h tape is {direction}; {spread_note}."


def _regime_summary(technicals: list[dict[str, Any]]) -> tuple[str, str]:
    bullish = sum(1 for item in technicals if item["stance"] == "bullish")
    bearish = sum(1 for item in technicals if item["stance"] == "bearish")
    high_vol = any(item["atr_pct"] >= 0.7 for item in technicals)
    if bullish and not bearish:
        summary = "Risk-on tape with multi-indicator bullish alignment."
    elif bearish and not bullish:
        summary = "Risk-off tape with persistent downside pressure."
    else:
        summary = "Mixed tape with split leadership across the tracked pairs."
    risk_note = (
        "Short-duration setups are moving fast; keep exits tight and avoid adding size into volatility."
        if high_vol
        else "Volatility is contained enough to keep the manager focused on signal quality over speed."
    )
    return summary, risk_note


def fetch_market_overview(symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")) -> dict[str, Any]:
    tickers: list[dict[str, Any]] = []
    technicals: list[dict[str, Any]] = []

    for symbol in symbols:
        ticker = _request_json(f"{BINANCE_SPOT}/api/v3/ticker/24hr", {"symbol": symbol})
        book = _request_json(f"{BINANCE_SPOT}/api/v3/ticker/bookTicker", {"symbol": symbol})
        candles = _parse_candles(
            _request_json(
                f"{BINANCE_SPOT}/api/v3/klines",
                {"symbol": symbol, "interval": "5m", "limit": 120},
            )
        )

        funding_rate_pct = None
        open_interest_usd = None
        futures_symbol = symbol
        try:
            premium = _request_json(f"{BINANCE_FUTURES}/fapi/v1/premiumIndex", {"symbol": futures_symbol})
            funding_rate_pct = float(premium.get("lastFundingRate", 0.0)) * 100
        except Exception:
            funding_rate_pct = None
        try:
            open_interest = _request_json(f"{BINANCE_FUTURES}/fapi/v1/openInterest", {"symbol": futures_symbol})
            open_interest_usd = float(open_interest.get("openInterest", 0.0)) * float(ticker["lastPrice"])
        except Exception:
            open_interest_usd = None

        bid = float(book["bidPrice"])
        ask = float(book["askPrice"])
        mid = (bid + ask) / 2 if bid and ask else 0.0
        spread_pct = ((ask - bid) / mid * 100) if mid else None

        tech = build_technical_snapshot(symbol.replace("USDT", ""), candles)
        technicals.append(tech)
        tickers.append(
            {
                "symbol": symbol.replace("USDT", ""),
                "price": round(float(ticker["lastPrice"]), 4),
                "change_pct_24h": round(float(ticker["priceChangePercent"]), 2),
                "quote_volume_usd": round(float(ticker["quoteVolume"]), 2),
                "funding_rate_pct": round(funding_rate_pct, 4) if funding_rate_pct is not None else None,
                "open_interest_usd": round(open_interest_usd, 2) if open_interest_usd is not None else None,
                "spread_pct": round(spread_pct, 4) if spread_pct is not None else None,
                "regime": tech["stance"],
                "note": _ticker_note(float(ticker["priceChangePercent"]), spread_pct),
            }
        )

    summary, risk_note = _regime_summary(technicals)
    return {
        "status": "live",
        "as_of": utc_now(),
        "summary": summary,
        "risk_note": risk_note,
        "tickers": tickers,
        "technicals": technicals,
    }


def _sentiment_from_text(text: str) -> str:
    lowered = text.lower()
    positive_words = ("surge", "rally", "gain", "bull", "breakout", "approval", "record", "strong")
    negative_words = ("drop", "falls", "bear", "hack", "lawsuit", "risk", "liquidation", "weak")
    score = sum(1 for word in positive_words if word in lowered) - sum(1 for word in negative_words if word in lowered)
    if score > 0:
        return "bullish"
    if score < 0:
        return "bearish"
    return "neutral"


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _entry_text(node: ET.Element, *tags: str) -> str:
    for child in node:
        if _strip_ns(child.tag) in tags:
            return (child.text or "").strip()
    return ""


def _entry_link(node: ET.Element) -> str:
    for child in node:
        tag = _strip_ns(child.tag)
        if tag == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
    return ""


def _parse_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _parse_feed_items(
    xml_text: str,
    *,
    source: str,
    category: str,
    limit: int,
    summary_prefix: str,
) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []

    for node in root.iter():
        tag = _strip_ns(node.tag)
        if tag not in {"item", "entry"}:
            continue
        title = _entry_text(node, "title")
        if not title:
            continue
        link = _entry_link(node)
        published = _parse_datetime(_entry_text(node, "pubDate", "published", "updated"))
        description = _entry_text(node, "description", "summary")
        items.append(
            {
                "source": source,
                "category": category,
                "title": title,
                "url": link,
                "sentiment": _sentiment_from_text(title),
                "summary": f"{summary_prefix} {description[:180].strip()}".strip(),
                "published_at": published,
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_intel_feed() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    news_queries = (
        ("google-news/bitcoin", "news", "Bitcoin price crypto market"),
        ("google-news/ethereum", "news", "Ethereum price crypto market"),
        ("google-news/polymarket", "news", "Polymarket prediction market"),
    )
    for source, category, query in news_queries:
        xml_text = _request_text(
            "https://news.google.com/rss/search",
            {
                "q": query,
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            },
        )
        items.extend(
            _parse_feed_items(
                xml_text,
                source=source,
                category=category,
                limit=2,
                summary_prefix="Headline context.",
            )
        )

    reddit_feeds = (
        ("reddit/r/CryptoCurrency", "community", "https://www.reddit.com/r/CryptoCurrency/.rss"),
        ("reddit/r/BitcoinMarkets", "community", "https://www.reddit.com/r/BitcoinMarkets/.rss"),
    )
    for source, category, url in reddit_feeds:
        xml_text = _request_text(url)
        items.extend(
            _parse_feed_items(
                xml_text,
                source=source,
                category=category,
                limit=2,
                summary_prefix="Community scan.",
            )
        )

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (item["source"], item["title"])
        deduped[key] = item
    sorted_items = sorted(
        deduped.values(),
        key=lambda item: item["published_at"] or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )
    return sorted_items[:10]


def build_reference_library() -> list[dict[str, str]]:
    return [
        {
            "source": "github",
            "category": "workflow",
            "title": "Vault collaboration repo",
            "url": "https://github.com/Merlin-Machines/vault",
            "note": "Primary manager/interface coordination repo for Chat dev and Codex.",
        },
        {
            "source": "github",
            "category": "runtime",
            "title": "POLY Agent Merlin runtime repo",
            "url": "https://github.com/Merlin-Machines/POLY_AGENT_Merlin",
            "note": "Live runtime, dashboard, and execution-side manager hooks.",
        },
        {
            "source": "tradingview",
            "category": "analysis",
            "title": "TradingView BTC/USDT 5-minute chart",
            "url": "https://www.tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT",
            "note": "Use for visual cross-checking, not as the only signal source.",
        },
        {
            "source": "reddit",
            "category": "community",
            "title": "Reddit crypto community watchlist",
            "url": "https://www.reddit.com/r/CryptoCurrency/",
            "note": "Use for narrative context only; community conviction is not edge by itself.",
        },
        {
            "source": "youtube",
            "category": "video",
            "title": "YouTube search: Bitcoin 5-minute MACD Bollinger",
            "url": "https://www.youtube.com/results?search_query=bitcoin+5+minute+macd+bollinger",
            "note": "Quick route to strategy breakdowns and post-market reviews without hard-coding a single creator.",
        },
        {
            "source": "youtube",
            "category": "video",
            "title": "YouTube search: Polymarket trading strategy",
            "url": "https://www.youtube.com/results?search_query=polymarket+trading+strategy",
            "note": "Good for collecting user walkthroughs and replay ideas to vet offline.",
        },
        {
            "source": "weather",
            "category": "data",
            "title": "NOAA weather API docs",
            "url": "https://www.weather.gov/documentation/services-web-api",
            "note": "Best public U.S. weather feed for forecast and alert context.",
        },
    ]
