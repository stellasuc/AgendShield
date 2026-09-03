"""Load and validate human-curated regulation packages from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agentshield.policy.rules import ComplianceRule
from agentshield.regulations.models import (
    OfficialSource,
    RegulationMetadata,
    RegulationPackage,
    RegulationRequirement,
)


class UnsupportedRegulationError(ValueError):
    """Raised when a selected regulation package is not present."""


class RegulationPackageError(ValueError):
    """Raised when a package is malformed."""


class RegulationLoader:
    def __init__(self, package_root: str | Path) -> None:
        self.package_root = Path(package_root)

    def load(self, regulation_id: str) -> RegulationPackage:
        package_dir = self.package_root / regulation_id.lower()
        if not package_dir.is_dir():
            available = sorted(p.name.upper() for p in self.package_root.glob("*") if p.is_dir())
            suffix = f" Available packages: {', '.join(available)}." if available else ""
            raise UnsupportedRegulationError(
                f"Unsupported regulation {regulation_id!r}.{suffix}"
            )

        metadata_raw = self._read_mapping(package_dir / "metadata.yaml")
        requirements_raw = self._read_yaml(package_dir / "requirements.yaml")
        mappings_path = package_dir / "mappings.yaml"
        mappings = self._read_mapping(mappings_path) if mappings_path.is_file() else {}
        try:
            metadata = self._metadata(metadata_raw)
            rules_path = package_dir / "rules.yaml"
            if rules_path.is_file():
                requirement_rows = self._list_payload(requirements_raw, "requirements", "requirements.yaml")
                requirements = tuple(RegulationRequirement.from_mapping(row) for row in requirement_rows)
                by_id = {item.requirement_id: item for item in requirements}
                if len(by_id) != len(requirements):
                    raise RegulationPackageError("Duplicate requirement_id in requirements.yaml")
                rule_rows = self._list_payload(self._read_yaml(rules_path), "rules", "rules.yaml")
                rules = tuple(self._runtime_rule(row, metadata.regulation_id, by_id) for row in rule_rows)
                if len({rule.rule_id for rule in rules}) != len(rules):
                    raise RegulationPackageError("Duplicate rule_id in rules.yaml")
            else:
                # Backward-compatible fixture format: executable rules
                # were stored directly under requirements.yaml.
                rows = self._list_payload(requirements_raw, "requirements", "requirements.yaml")
                rules = tuple(ComplianceRule.from_mapping(row, metadata.regulation_id) for row in rows)
                requirements = ()
        except (TypeError, KeyError, ValueError) as exc:
            if isinstance(exc, RegulationPackageError):
                raise
            raise RegulationPackageError(f"Invalid package {regulation_id!r}: {exc}") from exc
        return RegulationPackage(
            metadata=metadata,
            rules=rules,
            requirements=requirements,
            mappings=mappings,
        )

    @staticmethod
    def _metadata(payload: dict[str, Any]) -> RegulationMetadata:
        if "id" not in payload:
            return RegulationMetadata(**payload)
        source_rows = payload.get("official_sources")
        if not isinstance(source_rows, list) or not source_rows:
            raise RegulationPackageError("metadata.yaml requires non-empty official_sources")
        sources = tuple(OfficialSource(name=str(row["name"]), url=str(row["url"])) for row in source_rows)
        return RegulationMetadata(
            regulation_id=str(payload["id"]),
            official_name=str(payload["name"]),
            jurisdiction=str(payload["jurisdiction"]),
            version=str(payload["version"]),
            effective_date=str(payload["effective_date"]),
            official_url=sources[0].url,
            description=str(payload.get("description", "")),
            official_sources=sources,
        )

    @staticmethod
    def _runtime_rule(
        payload: dict[str, Any],
        regulation_id: str,
        requirements: dict[str, RegulationRequirement],
    ) -> ComplianceRule:
        references = payload.get("regulation_sources")
        if not isinstance(references, list) or not references:
            raise RegulationPackageError("Every runtime rule needs regulation_sources")
        sources = []
        concepts = set()
        for reference in references:
            requirement_id = str(reference["requirement_id"])
            if requirement_id not in requirements:
                raise RegulationPackageError(
                    f"Rule {payload.get('rule_id')!r} references unknown requirement {requirement_id!r}"
                )
            requirement = requirements[requirement_id]
            concepts.add(requirement.normalized_concept)
            sources.append(
                {
                    "regulation": requirement.source.regulation,
                    "article": requirement.source.article,
                    "official_url": requirement.source.official_url,
                    "legal_requirement": requirement.legal_requirement_summary,
                    "engineering_interpretation": requirement.engineering_interpretation,
                    "official_source": requirement.source.official_source,
                    "requirement_id": requirement.requirement_id,
                }
            )
        predicate = payload.get("predicate")
        if not isinstance(predicate, dict) or predicate.get("type") != "deterministic" or not predicate.get("handler"):
            raise RegulationPackageError("Runtime rules require a deterministic predicate handler")
        normalized = dict(payload)
        normalized["sources"] = sources
        normalized["normalized_concept"] = str(
            payload.get("normalized_concept") or next(iter(concepts))
        ).upper()
        interventions = payload.get("interventions")
        if not isinstance(interventions, list) or not interventions:
            raise RegulationPackageError("Runtime rules require a non-empty interventions list")
        normalized["intervention"] = interventions[0]
        return ComplianceRule.from_mapping(normalized, regulation_id)

    @staticmethod
    def _list_payload(payload: Any, key: str, filename: str) -> list[dict[str, Any]]:
        rows = payload.get(key) if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
            raise RegulationPackageError(f"{filename} must contain a non-empty {key} list")
        return rows

    @staticmethod
    def _read_mapping(path: Path) -> dict[str, Any]:
        payload = RegulationLoader._read_yaml(path)
        if not isinstance(payload, dict):
            raise RegulationPackageError(f"{path.name} must contain a YAML mapping")
        return payload

    @staticmethod
    def _read_yaml(path: Path) -> Any:
        if not path.is_file():
            raise RegulationPackageError(f"Missing required package file: {path.name}")
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return payload
