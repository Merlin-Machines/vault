from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_env_base_url() -> str:
    return (
        os.environ.get("VAULT_POLY_AGENT_URL")
        or os.environ.get("POLY_AGENT_DASHBOARD_URL")
        or "http://127.0.0.1:7731"
    ).rstrip("/")


@dataclass(slots=True)
class RuntimeSnapshot:
    connected: bool
    base_url: str
    source: str
    synced_at: str
    last_error: str | None = None
    stats: dict[str, Any] | None = None
    kpi: dict[str, Any] | None = None
    manager: dict[str, Any] | None = None
    integrations: dict[str, Any] | None = None
    portfolio: dict[str, Any] | None = None
    redeem_alerts: dict[str, Any] | None = None
    prices: dict[str, Any] | None = None
    log: list[str] | None = None
    available_endpoints: list[str] | None = None


class RuntimeAdapter:
    def __init__(self, base_url: str | None = None, timeout: float = 1.6) -> None:
        self.base_url = (base_url or _read_env_base_url()).rstrip("/")
        self.timeout = timeout

    def _request_json(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None
        method = "GET"
        headers = {"User-Agent": "Vault-MGMT/0.3"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            method = "POST"
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_snapshot(self) -> RuntimeSnapshot:
        endpoints = {
            "stats": "/api/stats",
            "kpi": "/api/kpi",
            "manager": "/api/manager",
            "integrations": "/api/integrations",
            "portfolio": "/api/portfolio",
            "redeem_alerts": "/api/redeem_alerts",
            "prices": "/api/prices",
            "log": "/api/log",
        }
        payloads: dict[str, Any] = {}
        available: list[str] = []
        connected = False
        error_message = None

        for name, path in endpoints.items():
            try:
                payloads[name] = self._request_json(path)
                available.append(name)
                connected = True
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                if error_message is None:
                    error_message = str(exc)
                payloads[name] = None

        return RuntimeSnapshot(
            connected=connected,
            base_url=self.base_url,
            source="poly-runtime" if connected else "seeded",
            synced_at=_utc_now_iso(),
            last_error=None if connected else error_message,
            stats=payloads.get("stats"),
            kpi=payloads.get("kpi"),
            manager=payloads.get("manager"),
            integrations=payloads.get("integrations"),
            portfolio=payloads.get("portfolio"),
            redeem_alerts=payloads.get("redeem_alerts"),
            prices=payloads.get("prices"),
            log=payloads.get("log"),
            available_endpoints=available,
        )

    def set_trading_enabled(self, enabled: bool) -> dict[str, Any]:
        path = "/api/trading/toggle?" + urlencode({"enabled": "true" if enabled else "false"})
        return self._request_json(path)

    def set_strategy_mode(self, mode: str) -> dict[str, Any]:
        path = "/api/strategy/set?" + urlencode({"mode": mode})
        return self._request_json(path)

    def propose_directive(self, name: str, proposal_text: str) -> dict[str, Any]:
        return self._request_json(
            "/api/manager/propose",
            {"name": name, "proposal_text": proposal_text},
        )

    def patch_profile(
        self,
        patch: dict[str, Any],
        *,
        proposal_text: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"patch": patch}
        if proposal_text is not None:
            payload["proposal_text"] = proposal_text
        if name:
            payload["name"] = name
        return self._request_json("/api/manager/patch", payload)

    def save_and_activate(self, name: str | None = None) -> dict[str, Any]:
        save_payload: dict[str, Any] = {}
        if name:
            save_payload["name"] = name
        self._request_json("/api/manager/save", save_payload)
        return self._request_json("/api/manager/activate", save_payload)
