from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .models import ActionState, InterventionType, ManagerMode, RiskPosture
from .policy import PolicyError
from .service import manager_service


app = FastAPI(title="Vault MGMT", version="0.1.0")
app.mount("/static", StaticFiles(directory="vault_mgmt/ui"), name="static")


class ModeRequest(BaseModel):
    mode: ManagerMode


class PostureRequest(BaseModel):
    posture: RiskPosture


class GuidanceRequest(BaseModel):
    notes: str


class PolicyRequest(BaseModel):
    max_position_size_usd: float
    max_daily_loss_usd: float
    confidence_threshold: float
    allow_market_orders: bool
    require_human_approval: bool


class GuidanceActionRequest(BaseModel):
    action_id: str
    state: ActionState


class InterventionRequest(BaseModel):
    action: InterventionType


@app.get("/")
def index() -> FileResponse:
    return FileResponse("vault_mgmt/ui/index.html")


@app.get("/api/manager")
def get_manager_state():
    return manager_service.get_state()


@app.post("/api/manager/mode")
def update_mode(payload: ModeRequest):
    try:
        return manager_service.update_mode(payload.mode)
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/manager/posture")
def update_posture(payload: PostureRequest):
    return manager_service.update_posture(payload.posture)


@app.post("/api/manager/guidance")
def update_guidance(payload: GuidanceRequest):
    return manager_service.update_guidance(payload.notes)


@app.post("/api/manager/policies")
def update_policies(payload: PolicyRequest):
    try:
        return manager_service.update_policies(
            max_position_size_usd=payload.max_position_size_usd,
            max_daily_loss_usd=payload.max_daily_loss_usd,
            confidence_threshold=payload.confidence_threshold,
            allow_market_orders=payload.allow_market_orders,
            require_human_approval=payload.require_human_approval,
        )
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/manager/guidance/action")
def apply_guidance_action(payload: GuidanceActionRequest):
    try:
        return manager_service.apply_guidance_action(payload.action_id, payload.state)
    except PolicyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/manager/intervention")
def intervene(payload: InterventionRequest):
    return manager_service.intervene(payload.action)
