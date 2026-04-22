from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ManagerMode(str, Enum):
    OBSERVE = "observe"
    PAPER = "paper"
    GATED_LIVE = "gated_live"


class RiskPosture(str, Enum):
    DEFENSIVE = "defensive"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class ActionState(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class InterventionType(str, Enum):
    PAUSE = "pause"
    RESUME = "resume"
    FORCE_DRY_RUN = "force_dry_run"
    REQUIRE_APPROVAL = "require_approval"


class GuidanceAction(BaseModel):
    id: str
    title: str
    rationale: str
    state: ActionState = ActionState.PENDING


class PolicySet(BaseModel):
    max_position_size_usd: float = 250.0
    max_daily_loss_usd: float = 150.0
    confidence_threshold: float = 0.67
    allow_market_orders: bool = False
    require_human_approval: bool = True


class AuditEvent(BaseModel):
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str
    event: str
    detail: str


class AgentTelemetry(BaseModel):
    agent_id: str = "poly-agent-01"
    strategy_name: str = "legacy_hybrid"
    state: str = "monitoring"
    pnl_usd: float = 42.15
    exposure_usd: float = 118.40
    open_positions: int = 3


class ManagerState(BaseModel):
    id: str = "vault-mgmt-01"
    name: str = "Vault MGMT"
    agent_id: str = "poly-agent-01"
    mission: str = "Lead the Poly Agent with disciplined guidance, approvals, and policy-first execution."
    mode: ManagerMode = ManagerMode.OBSERVE
    posture: RiskPosture = RiskPosture.BALANCED
    guidance_notes: str = "Prioritize signal quality over activity. Protect downside first."
    recommended_actions: List[GuidanceAction] = Field(default_factory=list)
    policies: PolicySet = Field(default_factory=PolicySet)
    approval_required_actions: List[str] = Field(default_factory=lambda: [
        "switch_to_gated_live",
        "raise_position_limits",
        "override_confidence_threshold",
    ])
    last_override: Optional[str] = None
    last_reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    telemetry: AgentTelemetry = Field(default_factory=AgentTelemetry)
    audit_log: List[AuditEvent] = Field(default_factory=list)
