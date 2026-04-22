from __future__ import annotations

from .models import ManagerMode, ManagerState


class PolicyError(ValueError):
    """Raised when a requested manager change violates policy."""


def validate_mode_transition(current: ManagerMode, requested: ManagerMode) -> None:
    if current == ManagerMode.OBSERVE and requested == ManagerMode.GATED_LIVE:
        raise PolicyError(
            "Direct transition from observe to gated_live is blocked. Move through paper mode first."
        )


def validate_position_limit(value: float) -> None:
    if value <= 0:
        raise PolicyError("Position limit must be greater than zero.")
    if value > 5000:
        raise PolicyError("Position limit above 5000 USD is blocked in phase 1.")


def validate_confidence_threshold(value: float) -> None:
    if not 0.5 <= value <= 0.99:
        raise PolicyError("Confidence threshold must remain between 0.50 and 0.99.")


def enforce_phase_one_guardrails(manager: ManagerState) -> None:
    if manager.mode == ManagerMode.GATED_LIVE:
        raise PolicyError(
            "Phase 1 keeps the manager dry-run safe. gated_live may be represented in UI, but not activated."
        )
