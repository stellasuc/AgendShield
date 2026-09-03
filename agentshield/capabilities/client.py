"""Agent-side HTTP proxy; contains no protected backend handle or credential."""

from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agentshield.capabilities.models import CapabilityRequest, CapabilityResponse


class BrokerClient:
    __slots__ = ("endpoint", "timeout")

    def __init__(self, endpoint: str, *, timeout: float = 10.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def request(self, request: CapabilityRequest) -> CapabilityResponse:
        payload = self._request("POST", "/capabilities", request.to_dict())
        return CapabilityResponse.from_dict(payload)

    def approve(
        self, transaction_id: str, scope: Mapping[str, Any] | None = None
    ) -> CapabilityResponse:
        payload = self._request("POST", f"/approve/{transaction_id}", {"scope": scope})
        return CapabilityResponse.from_dict(payload)

    def deny(
        self, transaction_id: str, scope: Mapping[str, Any] | None = None
    ) -> CapabilityResponse:
        payload = self._request("POST", f"/deny/{transaction_id}", {"scope": scope})
        return CapabilityResponse.from_dict(payload)

    def statistics(self) -> dict[str, Any]:
        return self._request("GET", "/stats")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def metrics(self) -> dict[str, float]:
        return self._request("GET", "/metrics")

    def transactions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/transactions")

    def approvals(self) -> list[dict[str, Any]]:
        return self._request("GET", "/approvals")

    def audit(self, run_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/audit/{run_id}")

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        data = None if payload is None else json.dumps(payload, default=str).encode()
        request = Request(
            self.endpoint + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except HTTPError as exc:
            body = json.loads(exc.read().decode())
            raise RuntimeError(body.get("error", f"Broker HTTP {exc.code}")) from exc
