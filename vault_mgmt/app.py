from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .models import InterventionType, StrategyMode
from .policy import PolicyError
from .service import manager_service


app = FastAPI(title="Vault MGMT", version="0.2.0")
app.mount("/static", StaticFiles(directory="vault_mgmt/ui"), name="static")


class DirectiveRequest(BaseModel):
    name: Optional[str] = None
    proposal_text: str


class ControlsRequest(BaseModel):
    trading_enabled: Optional[bool] = None
    strategy_mode: Optional[StrategyMode] = None
    continuous_trading: Optional[bool] = None
    base_size_usdc: Optional[float] = None
    max_size_usdc: Optional[float] = None
    max_entries_per_cycle: Optional[int] = None
    max_hold_minutes: Optional[int] = None
    stop_loss_pct: Optional[float] = None
    profit_take_pct: Optional[float] = None
    alignment_required: Optional[int] = None
    dca_enabled: Optional[bool] = None
    use_news_context: Optional[bool] = None
    use_weather_context: Optional[bool] = None
    use_tradingview_reference: Optional[bool] = None
    crypto_enabled: Optional[bool] = None
    weather_enabled: Optional[bool] = None


class TradingRequest(BaseModel):
    enabled: bool


class BaselineRequest(BaseModel):
    name: Optional[str] = None


class InterventionRequest(BaseModel):
    action: InterventionType


@app.get("/")
def index() -> FileResponse:
    return FileResponse("vault_mgmt/ui/index.html")


@app.get("/api/manager")
def get_manager_state():
    return manager_service.get_state()


@app.post("/api/manager/directive")
def update_directive(payload: DirectiveRequest):
    try:
        return manager_service.update_directive(payload.name or "", payload.proposal_text)
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/manager/controls")
def update_controls(payload: ControlsRequest):
    body = payload.model_dump(exclude_none=True)
    try:
        return manager_service.update_controls(**body)
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/manager/trading")
def update_trading(payload: TradingRequest):
    return manager_service.set_trading_enabled(payload.enabled)


@app.post("/api/manager/baseline")
def commit_baseline(payload: BaselineRequest):
    return manager_service.commit_baseline(payload.name)


@app.post("/api/manager/intervention")
def intervene(payload: InterventionRequest):
    return manager_service.intervene(payload.action)
