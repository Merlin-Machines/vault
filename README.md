# Vault MGMT

Vault MGMT is the manager layer for the Poly Agent ecosystem.

This repository starts with a dry-run-safe manager shell focused on:
- leadership and guidance
- policy enforcement
- approvals and intervention gates
- operator-facing interface
- audit visibility

## Phase 1

Phase 1 creates the first `Vault MGMT` implementation:
- manager domain models
- policy and intervention service
- lightweight FastAPI app
- seeded operator interface UI
- JSON API endpoints for state, guidance, and interventions

## Safety

This scaffold is intentionally dry-run oriented.
No live trading actions are enabled in this repository.

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
- add authentication and role-based approvals
- add persistent storage and event history
- wire policies into execution guards
