# Vault MGMT

Vault MGMT is the manager layer for the Poly Agent ecosystem.

This repository starts with a dry-run-safe manager shell focused on:
- leadership and guidance
- live manager directives
- safe runtime knobs
- operator-facing interface
- audit visibility

## Phase 1

Phase 1 creates the first `Vault MGMT` implementation:
- manager domain models
- live-directive manager service
- lightweight FastAPI app
- seeded operator interface UI
- JSON API endpoints for live state, directives, controls, and baseline commits

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

- connect to the Poly Agent runtime in `polymarket-pipeline`
- replace seeded data with live telemetry adapters
- mirror the stronger MGMT control-room interface from local development
- add persistent storage and event history
- wire runtime-safe controls into execution adapters

## Collaboration

- Shared workflow notes live in `docs/MGMT_COLLAB_WORKFLOW.md`
- Current operator intent and handoff notes live in `docs/MGMT_HANDOFF.md`
