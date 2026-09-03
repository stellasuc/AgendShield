from __future__ import annotations

import pytest

from agentshield import AgentShield
from agentshield.regulations.compiler import RegulationCompiler
from agentshield.regulations.loader import RegulationLoader, RegulationPackageError


def test_gdpr_package_loads_with_six_curated_requirements() -> None:
    package = RegulationLoader("regulations").load("GDPR")
    assert len(package.requirements) == 6
    assert len(package.rules) == 6
    assert all(item.source.official_source for item in package.requirements)


def test_pipl_package_loads_with_seven_curated_requirements() -> None:
    package = RegulationLoader("regulations").load("PIPL")
    assert len(package.requirements) == 7
    assert len(package.rules) == 9
    assert package.metadata.effective_date == "2021-11-01"


def test_rule_sources_preserve_requirement_article_and_official_source() -> None:
    package = RegulationLoader("regulations").load("GDPR")
    for rule in package.rules:
        assert all(source.requirement_id for source in rule.sources)
        assert all(source.article for source in rule.sources)
        assert all(source.official_source for source in rule.sources)
        assert all(source.official_url.startswith("https://") for source in rule.sources)


def test_malformed_regulation_package_fails(tmp_path) -> None:
    package = tmp_path / "bad"
    package.mkdir()
    (package / "metadata.yaml").write_text(
        "id: BAD\nname: Bad\njurisdiction: Test\nversion: v1\neffective_date: '2026'\nofficial_sources: []\n",
        encoding="utf-8",
    )
    (package / "requirements.yaml").write_text("requirements: []\n", encoding="utf-8")
    (package / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
    with pytest.raises(RegulationPackageError, match="official_sources"):
        RegulationLoader(tmp_path).load("BAD")


def test_multi_regulation_compile_merges_duplicate_execution_and_keeps_sources() -> None:
    loader = RegulationLoader("regulations")
    effective = RegulationCompiler().compile([loader.load("GDPR"), loader.load("PIPL")])
    assert effective.regulations == ("GDPR", "PIPL")
    assert len(effective.rules) == 11
    minimization = [rule for rule in effective.rules if rule.normalized_concept == "DATA_MINIMIZATION"]
    assert len(minimization) == 1
    assert minimization[0].regulation_ids == {"GDPR", "PIPL"}
    assert {source.regulation for source in minimization[0].sources} == {"GDPR", "PIPL"}


def test_agent_shield_selects_only_requested_regulations() -> None:
    assert AgentShield(["GDPR"]).regulations == ("GDPR",)
    assert AgentShield(["GDPR", "PIPL"]).regulations == ("GDPR", "PIPL")
    with pytest.raises(ValueError, match="Duplicate"):
        AgentShield(["GDPR", "GDPR"])
