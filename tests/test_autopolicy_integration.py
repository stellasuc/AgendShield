from __future__ import annotations

import json

import pytest

from agentshield.integrations.autopolicy import (
    AutoPolicyArtifactError,
    AutoPolicyExtractionRequest,
    AutoPolicyRunner,
    load_autopolicy_bundle,
    render_review_template,
)


def _write_bundle(root, *, bad_source: bool = False, bad_mapping: bool = False):
    organization = "Demo"
    (root / f"{organization}_all_extracted_policies.json").write_text(
        json.dumps([
            {
                "policy_id": 0,
                "definitions": ["Personal data: identified information"],
                "scope": "Web task agent operations",
                "policy_description": "The agent must not disclose personal data.",
                "reference": ["Article 1"],
                "source_file": "policy.pdf",
            }
        ]),
        encoding="utf-8",
    )
    (root / f"{organization}_all_extracted_rules.json").write_text(
        json.dumps([
            {
                "rule_id": 1,
                "rule_description": "Do not disclose personal data.",
                "source_policy_idx": [99 if bad_source else 0],
                "scope": "Web task agent operations",
                "term_definitions": ["Personal data"],
            }
        ]),
        encoding="utf-8",
    )
    (root / f"{organization}_risk_categories.json").write_text(
        json.dumps([{"category_name": "Privacy", "risk_level": "high", "rules": []}]),
        encoding="utf-8",
    )
    (root / f"{organization}_policy_rule_mapping.json").write_text(
        json.dumps({"0": [] if bad_mapping else ["1"]}), encoding="utf-8"
    )
    (root / f"{organization}_extraction_report.json").write_text(
        json.dumps({"document_path": "policy.pdf", "policies_extracted": 1}),
        encoding="utf-8",
    )


def test_autopolicy_bundle_is_candidate_only_and_traceable(tmp_path):
    _write_bundle(tmp_path)
    bundle = load_autopolicy_bundle(tmp_path, upstream_revision="a" * 40)

    assert bundle.review_status == "REVIEW_REQUIRED"
    assert bundle.policies[0].references == ("Article 1",)
    assert bundle.rules[0].source_policy_ids == ("0",)
    assert bundle.policy_rule_mapping == {"0": ("1",)}
    assert bundle.audit_view()["executable"] is False
    assert len(bundle.artifact_digest) == 64
    review = render_review_template(bundle)
    assert "status: REVIEW_REQUIRED" in review
    assert "candidate_rule_id: '1'" in review
    assert "runtime_binding:" in review
    assert "official_url: ''" in review


def test_autopolicy_bundle_rejects_broken_rule_provenance(tmp_path):
    _write_bundle(tmp_path, bad_source=True)
    with pytest.raises(AutoPolicyArtifactError, match="source policies"):
        load_autopolicy_bundle(tmp_path, upstream_revision="a" * 40)


def test_autopolicy_bundle_rejects_disagreeing_policy_rule_mapping(tmp_path):
    _write_bundle(tmp_path, bad_mapping=True)
    with pytest.raises(AutoPolicyArtifactError, match="mapping disagrees"):
        load_autopolicy_bundle(tmp_path, upstream_revision="a" * 40)


def test_autopolicy_runner_builds_argument_vector_without_api_key():
    runner = AutoPolicyRunner(python_executable="policy-python")
    request = AutoPolicyExtractionRequest(
        document="policy_docs/eu_ai_act_art5.pdf",
        organization="EU AI Act",
        input_type="pdf",
        deep_policy=True,
    )

    command = runner.build_command(request, "/tmp/output")
    assert command[0] == "policy-python"
    assert command[1] == "policy_extractor_async.py"
    assert "--extract-rules" in command
    assert "--deep-policy" in command
    assert not any("key" in value.lower() for value in command)

    bundle_root = runner.checkout / "output" / "nonexistent-for-command-test"
    bundle = type("Bundle", (), {"extraction_directory": bundle_root, "organization": "Demo"})()
    ltl_command = runner.build_ltl_command(bundle)
    assert "--api-key" not in ltl_command
    assert not any("secret" in value.lower() for value in ltl_command)
