# MGMT Collaboration Workflow

This repository is the shared coordination hub for the MGMT layer that directs
the Poly Agent ecosystem.

## Source Of Truth

- GitHub repo: `Merlin-Machines/vault`
- Manager UI and API live in `vault_mgmt/`
- Local experimental work may happen in other repos, but anything that should be
  shared across Chat dev and Codex should land here as documented changes

## Working Model

- Chat dev can explore, scaffold, and push repo-native changes quickly
- Codex can port working local runtime patterns into this repo and clean up the
  implementation
- Operator intent should be preserved as plain-language manager directives, not
  buried in code comments or chat history

## Current Product Direction

- MGMT directly guides the Poly Agent rather than acting as an approval-only gate
- The live agent should read safe runtime config and keep execution focused
- Safe knobs stay operator-visible:
  - trading on or off
  - strategy mode
  - size caps
  - hold caps
  - stop loss and profit take
  - DCA on or off
  - market filters
  - news, weather, and TradingView context flags
- Strategy code changes still belong in a dev workflow, but manager directives
  can update the live runtime profile without requiring manual approval clicks

## Repo Ritual

1. Put the current manager goal in `docs/MGMT_HANDOFF.md`.
2. Keep UI and API changes paired in the same branch when possible.
3. Use small PRs with a single theme:
   - backend state model
   - operator UI
   - runtime adapter
   - integration status
4. When copying a working pattern from another repo, note the source path and
   the reason for the port in the PR description.

## Branch Suggestions

- `feature/live-directive-state`
- `feature/mgmt-control-room-ui`
- `feature/poly-runtime-adapter`
- `feature/weather-integration-status`

## Near-Term Priorities

1. Align this repo to the live-directive manager model
2. Mirror the stronger MGMT control-room interface here
3. Add an adapter layer to consume Poly Agent runtime telemetry
4. Keep all trading behavior dry-run safe in this repo until the runtime adapter
   is explicit and tested
