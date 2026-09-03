"""Incremental state changes used for affected-rule lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class StateDiff:
    changed_variables: frozenset[str] = frozenset()
    changed_objects: dict[str, frozenset[str]] = field(default_factory=dict)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)

    @property
    def compliance_relevant(self) -> bool:
        return bool(self.changed_variables)

    def audit_view(self) -> dict[str, Any]:
        return {
            "changed_variables": sorted(self.changed_variables),
            "changed_objects": {key: sorted(value) for key, value in self.changed_objects.items()},
        }

