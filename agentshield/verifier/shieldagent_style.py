"""SHIELDAGENT-inspired structured verifier interface.

The reference runtime binds the interface to deterministic checks. Other implementations may
provide Search, Binary-Check, Detect, or Formal Verify operations without changing
the policy engine contract.
"""

from __future__ import annotations

from typing import Protocol

from agentshield.policy.rules import ComplianceRule, RuleEvaluation
from agentshield.runtime.lifecycle import LifecycleEvent
from agentshield.state.models import ComplianceState


class ShieldingOperation(Protocol):
    def execute(self, query: str, event: LifecycleEvent, state: ComplianceState) -> object: ...


class ShieldAgentStyleVerifier(Protocol):
    def verify(self, rule: ComplianceRule, event: LifecycleEvent, state: ComplianceState) -> RuleEvaluation: ...
