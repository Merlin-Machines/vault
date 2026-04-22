# Vault MGMT

Vault MGMT is the manager layer for the Poly Agent ecosystem.

This repository starts with a dry-run-safe manager shell focused on:
- leadership and guidance
- live manager directives
- safe runtime knobs
- operator-facing interface
- audit visibility
- runtime bridge into `POLY_AGENT_Merlin` when the local dashboard is online
- live market board with 5-minute technicals
- news, community, and research context panels

## Phase 1

Phase 1 creates the first `Vault MGMT` implementation:
- manager domain models
- live-directive manager service
- lightweight FastAPI app
- operator interface UI with a separate management surface
- JSON API endpoints for live state, directives, controls, and baseline commits
- public market-intel fetchers for Binance, Google News RSS, and Reddit RSS
- runtime adapter for local POLY dashboard sync

## Safety

This scaffold is intentionally dry-run oriented.
No live trading actions are enabled in this repository.
The current product direction is that MGMT directs the agent through runtime
state rather than acting as an approval-only gate.

## Run locally

```bash
pip install -r requirements.txt
uvicorn vault_mgmt.app:app --reload
```

Then open:
- API: `http://127.0.0.1:8000/api/manager`
- UI: `http://127.0.0.1:8000/`

## Next steps

- deepen the runtime adapter with richer execution telemetry
- add persistent storage and event history
- add stronger replay and backtest adapters
- wire runtime-safe controls into execution adapters

## Collaboration

- Shared workflow notes live in `docs/MGMT_COLLAB_WORKFLOW.md`
- Current operator intent and handoff notes live in `docs/MGMT_HANDOFF.md`
