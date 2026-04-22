from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from .models import (
    ActionState,
    AuditEvent,
    GuidanceAction,
    InterventionType,
    ManagerMode,
    ManagerState,
    RiskPosture,
)
from .policy import (
    PolicyError,
    enforce_phase_one_guardrails,
    validate_confidence_threshold,
    validate_mode_transition,
    validate_position_limit,
)


class ManagerService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._manager = ManagerState(
            recommended_actions=[
                GuidanceAction(
                    id="guide-1",
                    title="Reduce market participation during thin liquidity windows",
                    rationale="Current posture favors preserving edge and lowering reactive fills.",
                ),
                GuidanceAction(
                    id="guide-2",
                    title="Require approval before any position size increase",
                    rationale="Signal quality has not yet justified looser risk limits.",
                ),
            ],
            audit_log=[
                AuditEvent(
                    actor="system",
                    event="manager_initialized",
                    detail="Vault MGMT phase 1 state initialized in observe mode.",
                )
            ],
        )

    def get_state(self) -> ManagerState:
        return self._manager

    def update_mode(self, requested_mode: ManagerMode) -> ManagerState:
        with self._lock:
            validate_mode_transition(self._manager.mode, requested_mode)
            self._manager.mode = requested_mode
            enforce_phase_one_guardrails(self._manager)
            self._stamp("operator", "mode_updated", f"Manager mode set to {requested_mode.value}.")
            return self._manager

    def update_posture(self, posture: RiskPosture) -> ManagerState:
        with self._lock:
            self._manager.posture = posture
            self._stamp("operator", "posture_updated", f"Risk posture set to {posture.value}.")
            return self._manager

    def update_guidance(self, notes: str) -> ManagerState:
        with self._lock:
            self._manager.guidance_notes = notes.strip()
            self._stamp("operator", "guidance_updated", "Guidance notes updated.")
            return self._manager

    def update_policies(
        self,
        max_position_size_usd: float,
        max_daily_loss_usd: float,
        confidence_threshold: float,
        allow_market_orders: bool,
        require_human_approval: bool,
    ) -> ManagerState:
        with self._lock:
            validate_position_limit(max_position_size_usd)
            validate_confidence_threshold(confidence_threshold)
            self._manager.policies.max_position_size_usd = max_position_size_usd
            self._manager.policies.max_daily_loss_usd = max_daily_loss_usd
            self._manager.policies.confidence_threshold = confidence_threshold
            self._manager.policies.allow_market_orders = allow_market_orders
            self._manager.policies.require_human_approval = require_human_approval
            self._stamp("operator", "policies_updated", "Manager policies updated.")
            return self._manager

    def apply_guidance_action(self, action_id: str, state: ActionState) -> ManagerState:
        with self._lock:
            for action in self._manager.recommended_actions:
                if action.id == action_id:
                    action.state = state
                    self._stamp("operator", "guidance_action_updated", f"{action_id} marked as {state.value}.")
                    return self._manager
            raise PolicyError(f"Unknown guidance action: {action_id}")

    def intervene(self, action: InterventionType) -> ManagerState:
        with self._lock:
            if action == InterventionType.PAUSE:
                self._manager.telemetry.state = "paused"
            elif action == InterventionType.RESUME:
                self._manager.telemetry.state = "monitoring"
            elif action == InterventionType.FORCE_DRY_RUN:
                self._manager.mode = ManagerMode.OBSERVE
                self._manager.last_override = "force_dry_run"
            elif action == InterventionType.REQUIRE_APPROVAL:
                self._manager.policies.require_human_approval = True
                self._manager.last_override = "require_approval"
            self._stamp("operator", "intervention", f"Intervention applied: {action.value}.")
            return self._manager

    def _stamp(self, actor: str, event: str, detail: str) -> None:
        self._manager.last_reviewed_at = datetime.now(timezone.utc)
        self._manager.audit_log.insert(
            0,
            AuditEvent(actor=actor, event=event, detail=detail),
        )


manager_service = ManagerService()
