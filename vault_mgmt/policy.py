from __future__ import annotations


class PolicyError(ValueError):
    """Raised when a requested manager change violates the local safety rules."""


def validate_position_limit(value: float) -> None:
    if value <= 0:
        raise PolicyError("Position limit must be greater than zero.")
    if value > 20:
        raise PolicyError("Position limit above 20 USDC is blocked in the seeded repo state.")


def validate_probability_threshold(value: int) -> None:
    if not 1 <= value <= 5:
        raise PolicyError("Indicator alignment must remain between 1 and 5.")


def validate_pct(value: float, label: str) -> None:
    if not 0.0 <= value <= 0.5:
        raise PolicyError(f"{label} must remain between 0.00 and 0.50.")


def validate_hold_minutes(value: int) -> None:
    if not 5 <= value <= 720:
        raise PolicyError("Hold cap must remain between 5 and 720 minutes.")
