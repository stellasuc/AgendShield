"""Regulation-package models.

Packages are curated inputs.  Legal text and executable engineering controls remain
separate so a decision can be traced without presenting a control as legal advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentshield.policy.rules import ComplianceRule


@dataclass(frozen=True, slots=True)
class OfficialSource:
    name: str
    url: str

    def __post_init__(self) -> None:
        if not self.name or not self.url.startswith(("https://", "http://")):
            raise ValueError("Official sources require a name and HTTP(S) URL")


@dataclass(frozen=True, slots=True)
class RegulationMetadata:
    regulation_id: str
    official_name: str
    jurisdiction: str
    version: str
    effective_date: str
    official_url: str
    description: str = ""
    official_sources: tuple[OfficialSource, ...] = ()

    def __post_init__(self) -> None:
        if not self.regulation_id.strip():
            raise ValueError("regulation_id must not be empty")
        if not self.official_url.startswith(("https://", "http://")):
            raise ValueError("official_url must be an HTTP(S) URL")


@dataclass(frozen=True, slots=True)
class RequirementSource:
    regulation: str
    article: str
    official_source: str
    official_url: str

    def __post_init__(self) -> None:
        if not all((self.regulation, self.article, self.official_source)):
            raise ValueError("Requirement source fields must not be empty")
        if not self.official_url.startswith(("https://", "http://")):
            raise ValueError("Requirement official_url must be an HTTP(S) URL")


@dataclass(frozen=True, slots=True)
class RegulationRequirement:
    requirement_id: str
    normalized_concept: str
    source: RequirementSource
    legal_requirement_summary: str
    engineering_interpretation: str
    runtime_enforcement: str
    lifecycle_stages: tuple[str, ...]
    required_state: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "RegulationRequirement":
        return cls(
            requirement_id=str(payload["requirement_id"]),
            normalized_concept=str(payload["normalized_concept"]).upper(),
            source=RequirementSource(**payload["source"]),
            legal_requirement_summary=str(payload["legal_requirement_summary"]),
            engineering_interpretation=str(payload["engineering_interpretation"]),
            runtime_enforcement=str(payload["runtime_enforcement"]),
            lifecycle_stages=tuple(payload["lifecycle_stages"]),
            required_state=tuple(payload["required_state"]),
        )

    def __post_init__(self) -> None:
        if not all(
            (
                self.requirement_id,
                self.normalized_concept,
                self.legal_requirement_summary,
                self.engineering_interpretation,
                self.runtime_enforcement,
            )
        ):
            raise ValueError("Regulation requirement fields must not be empty")
        if not self.lifecycle_stages or not self.required_state:
            raise ValueError("Requirements need lifecycle stages and required state")


@dataclass(frozen=True, slots=True)
class RegulationPackage:
    metadata: RegulationMetadata
    rules: tuple[ComplianceRule, ...]
    requirements: tuple[RegulationRequirement, ...] = ()
    mappings: dict[str, Any] = field(default_factory=dict)
