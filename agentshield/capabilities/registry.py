"""Small explicit capability catalog."""

from __future__ import annotations

from agentshield.capabilities.models import Capability


class CapabilityRegistry:
    def __init__(self, capabilities: tuple[Capability, ...] | None = None) -> None:
        capabilities = capabilities or default_capabilities()
        self._capabilities = {capability.id: capability for capability in capabilities}
        if len(self._capabilities) != len(capabilities):
            raise ValueError("Duplicate capability ID")

    def get(self, capability_id: str) -> Capability:
        try:
            return self._capabilities[capability_id]
        except KeyError as exc:
            raise KeyError(f"Unregistered capability: {capability_id}") from exc

    def list(self) -> tuple[Capability, ...]:
        return tuple(self._capabilities.values())


def default_capabilities() -> tuple[Capability, ...]:
    return (
        Capability("customer.read", False, "LOW", "internal", data_source=True),
        Capability("web.page.read", False, "MEDIUM", "external", data_source=True),
        Capability("web.action.submit", True, "HIGH", "external", data_sink=True),
        Capability("email.send", True, "HIGH", "external", data_sink=True),
        Capability(
            "memory.write", True, "HIGH", "internal", data_sink=True, persistent=True
        ),
        Capability("response.release", True, "HIGH", "user", data_sink=True),
    )
