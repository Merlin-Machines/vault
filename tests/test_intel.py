from __future__ import annotations

import unittest

from vault_mgmt.intel import build_technical_snapshot


def _sample_candles() -> list[dict[str, float]]:
    candles = []
    price = 100.0
    for index in range(40):
        price += 0.45
        candles.append(
            {
                "open": price - 0.2,
                "high": price + 0.5,
                "low": price - 0.6,
                "close": price,
                "volume": 1000 + index * 35,
            }
        )
    return candles


class IntelTests(unittest.TestCase):
    def test_build_technical_snapshot_from_trending_candles(self) -> None:
        snapshot = build_technical_snapshot("BTC", _sample_candles())
        self.assertEqual(snapshot["symbol"], "BTC")
        self.assertEqual(snapshot["interval"], "5m")
        self.assertGreater(snapshot["ema_fast"], snapshot["ema_slow"])
        self.assertEqual(snapshot["trend"], "up")
        self.assertIn(snapshot["macd_bias"], {"bullish", "neutral"})
        self.assertGreaterEqual(snapshot["alignment_score"], 1)

    def test_short_candle_stack_returns_waiting_state(self) -> None:
        snapshot = build_technical_snapshot("ETH", _sample_candles()[:10])
        self.assertEqual(snapshot["symbol"], "ETH")
        self.assertEqual(snapshot["summary"], "Waiting for enough 5-minute candles.")


if __name__ == "__main__":
    unittest.main()
