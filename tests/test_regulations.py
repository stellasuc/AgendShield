from __future__ import annotations

from dataclasses import replace

import pytest

from agentshield.policy.rules import Intervention
from agentshield.regulations.compiler import RegulationCompiler
from agentshield.regulations.loader import RegulationLoader, UnsupportedRegulationError
from agentshield.regulations.models import RegulationMetadata, RegulationPackage


def _write_package(root, package_id: str, rule_id: str = "R1") -> None:
    directory = root / package_id.lower()
    directory.mkdir()
    (directory / "metadata.yaml").write_text(
        "\n".join(
            [
                f"regulation_id: {package_id}",
                "official_name: Synthetic Regulation",
                "jurisdiction: Test",
                "version: v1",
                "effective_date: '2026-01-01'",
                "official_url: https://example.invalid/official",
                "description: Test-only package",
            ]
        ),
        encoding="utf-8",
    )
    (directory / "requirements.yaml").write_text(
        f"""requirements:
  - rule_id: {rule_id}
    normalized_concept: data_minimization
    description: Minimize transfers
    lifecycle_stages: [EXTERNAL_TRANSFER]
    dependencies: [event.is_minimized]
    applicability: []
    requirements:
      - variable: event.is_minimized
        operator: EQ
        value: true
    severity: HIGH
    intervention: AGGREGATE
    repair_strategy: AGGREGATE
    sources:
      - regulation: {package_id}
        article: TEST-1
        official_url: https://example.invalid/official#test-1
        legal_requirement: Synthetic text, not law.
        engineering_interpretation: Aggregate before transfer.
""",
        encoding="utf-8",
    )
    (directory / "mappings.yaml").write_text("concepts: {}\n", encoding="utf-8")


def test_package_loads_and_preserves_source(tmp_path) -> None:
    _write_package(tmp_path, "TEST")
    package = RegulationLoader(tmp_path).load("TEST")
    assert package.metadata.regulation_id == "TEST"
    assert package.rules[0].sources[0].article == "TEST-1"
    assert package.rules[0].sources[0].engineering_interpretation


def test_unsupported_regulation_has_clear_error(tmp_path) -> None:
    _write_package(tmp_path, "TEST")
    with pytest.raises(UnsupportedRegulationError, match="Available packages: TEST"):
        RegulationLoader(tmp_path).load("MISSING")


def test_exact_duplicate_concepts_merge_and_keep_sources(minimization_rule, source) -> None:
    source_two = replace(source, regulation="TEST2", article="T-2")
    duplicate = replace(
        minimization_rule,
        rule_id="TEST2_MINIMIZATION",
        sources=(source_two,),
        regulation_ids=frozenset({"TEST2"}),
    )
    metadata_one = RegulationMetadata("TEST", "Test", "X", "v1", "2026", "https://example.invalid/1")
    metadata_two = RegulationMetadata("TEST2", "Test 2", "Y", "v1", "2026", "https://example.invalid/2")
    compiled = RegulationCompiler().compile(
        [RegulationPackage(metadata_one, (minimization_rule,)), RegulationPackage(metadata_two, (duplicate,))]
    )
    assert len(compiled.rules) == 1
    assert {item.regulation for item in compiled.rules[0].sources} == {"TEST", "TEST2"}
    assert compiled.rules[0].regulation_ids == {"TEST", "TEST2"}


def test_non_identical_controls_are_preserved_and_conflict_reported(minimization_rule) -> None:
    stricter = replace(minimization_rule, rule_id="BLOCK_MIN", intervention=Intervention.BLOCK)
    metadata = RegulationMetadata("TEST", "Test", "X", "v1", "2026", "https://example.invalid/1")
    compiled = RegulationCompiler().compile([RegulationPackage(metadata, (minimization_rule, stricter))])
    assert len(compiled.rules) == 2
    assert compiled.conflicts[0].selected_control == Intervention.BLOCK
    assert "human review" in compiled.conflicts[0].explanation.lower()

