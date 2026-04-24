# MGMT Handoff

## Current Goal

Turn `vault` into the shared MGMT repo for Chat dev and Codex, centered on a
live-directive manager UI instead of an approval-only console.

## Operator Intent

The current manager directive emphasizes:

- continuous short-duration trading behavior
- 5-minute candle context
- MACD, RA or RSI, Bollinger Bands, momentum, and trend
- news and weather context when helpful
- TradingView reference when available
- active YES or NO position management
- DCA support
- stop losses
- fast exits instead of drifting toward expiry

## Repo State

- `vault_mgmt/` already has a FastAPI shell and seeded UI
- initial scaffold still reflects approvals and intervention gates
- local Poly Agent work has already moved to:
  - live directives
  - safe runtime knobs
  - integration status for NOAA, Weather Company, WeatherAPI, TradingView
  - a separate MGMT control-room UI

## Next Implementation Steps

1. Replace seeded approval-oriented manager state with live-directive state
2. Port the cleaner operator UI into this repo
3. Add a runtime adapter contract for Poly Agent telemetry and manager updates
4. Track what is real versus seeded directly in the UI

## Notes

- Do not promise profit or certainty in UI copy
- Keep this repo dry-run safe until runtime wiring is explicit
- Use GitHub as the handoff layer between Chat dev and Codex
