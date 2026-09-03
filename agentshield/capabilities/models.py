"""Minimal capability and request models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Capability:
    id: str
    side_effect: bool
    risk_level: str
    trust_boundary: str
    data_sink: bool = False
    persistent: bool = False
    data_source: bool = False


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    trajectory_id: str
    capability_id: str
    arguments: Mapping[str, Any]
    referenced_data_objects: tuple[str, ...] = ()
    request_id: str = field(default_factory=lambda: str(uuid4()))
    effect_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "arguments": dict(self.arguments),
            "referenced_data_objects": list(self.referenced_data_objects),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilityRequest":
        return cls(
            request_id=str(payload.get("request_id") or uuid4()),
            trajectory_id=str(payload["trajectory_id"]),
            capability_id=str(payload["capability_id"]),
            arguments=dict(payload.get("arguments") or {}),
            referenced_data_objects=tuple(payload.get("referenced_data_objects") or ()),
            effect_id=(str(payload["effect_id"]) if payload.get("effect_id") else None),
        )


@dataclass(frozen=True, slots=True)
class CapabilityResponse:
    transaction_id: str
    effect_id: str
    status: str
    decision: str
    value: Any = None
    data_object_id: str | None = None
    replayed: bool = False
    disposition: str = "PROCESSED"
    activated_rules: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "activated_rules": list(self.activated_rules)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilityResponse":
        return cls(
            transaction_id=str(payload["transaction_id"]),
            effect_id=str(payload["effect_id"]),
            status=str(payload["status"]),
            decision=str(payload["decision"]),
            value=payload.get("value"),
            data_object_id=payload.get("data_object_id"),
            replayed=bool(payload.get("replayed", False)),
            disposition=str(payload.get("disposition", "PROCESSED")),
            activated_rules=tuple(payload.get("activated_rules") or ()),
            error=payload.get("error"),
        )
