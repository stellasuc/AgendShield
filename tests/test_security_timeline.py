from __future__ import annotations

import json
import importlib
import sys

import pytest

from agentshield.cli import main
from agentshield.dashboard_launcher import launch_dashboard
from agentshield.observability import SecurityTimeline
from dashboard.demo_loader import resolve_pipl_approval, run_demo
from examples.portfolio.demo import run_gdpr_broker, run_idempotency


def test_dashboard_entrypoint_is_safe_during_process_spawn():
    sys.modules.pop("dashboard.ui", None)
    import dashboard.app

    importlib.reload(dashboard.app)
    assert "dashboard.ui" not in sys.modules


def test_dashboard_launcher_explains_missing_optional_dependency(monkeypatch):
    monkeypatch.setattr("agentshield.dashboard_launcher.importlib.util.find_spec", lambda _: None)
    with pytest.raises(SystemExit, match=r"pip install -e '\.\[dashboard\]'"):
        launch_dashboard()


def test_dashboard_launcher_stops_cleanly_on_keyboard_interrupt(monkeypatch):
    monkeypatch.setattr(
        "agentshield.dashboard_launcher.subprocess.call",
        lambda _: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    assert launch_dashboard() == 130


def test_gdpr_timeline_uses_runtime_evidence_and_redacts_payload(tmp_path):
    database = tmp_path / "runtime.db"
    result = run_gdpr_broker(database)
    snapshot = SecurityTimeline(database).snapshot("gdpr-broker-demo")

    assert result["raw_pii_messages"] == 0
    assert result["aggregate_messages"] == 1
    assert any(event.status == "REPAIR" for event in snapshot.events)
    assert any(event.event_type == "RE_VERIFICATION" for event in snapshot.events)
    assert any(edge.transformation == "AGGREGATE" for edge in snapshot.lineage)
    assert snapshot.policy_decision is not None
    assert snapshot.policy_decision.regulation == "GDPR"
    assert snapshot.policy_decision.source_url.startswith("https://")
    assert snapshot.policy_decision.reverification == "PASS"

    raw = next(item for item in snapshot.data_objects if item.contains_personal_data)
    aggregate = next(
        item for item in snapshot.data_objects if "AGGREGATE" in item.transformations
    )
    assert raw.classification in {"PERSONAL", "SENSITIVE"}
    assert aggregate.contains_personal_data is False
    assert aggregate.safe_summary == "EU customer count: 2"
    exported = SecurityTimeline(database).to_json("gdpr-broker-demo")
    assert "alice@example.test" not in exported
    assert "+86" not in exported


def test_pipl_dashboard_approval_calls_real_broker_api():
    session = run_demo("pipl")
    try:
        assert session.result["initial_status"] == "WAITING_APPROVAL"
        assert session.result["email_messages_before_approval"] == 0
        assert any(item["status"] == "WAITING_APPROVAL" for item in session.snapshot.transactions)

        snapshot = resolve_pipl_approval(session, "approve")
        assert session.result["email_messages_after_decision"] == 1
        assert snapshot.policy_decision is not None
        assert snapshot.policy_decision.regulation == "PIPL"
        assert snapshot.policy_decision.rule_id == "PIPL_SENSITIVE_PROCESSING_001"
        assert snapshot.policy_decision.reverification == "PASS"
        assert len(snapshot.approvals) == 1
    finally:
        session.close()


def test_idempotency_timeline_reports_one_execution(tmp_path):
    database = tmp_path / "runtime.db"
    result = run_idempotency(database)
    snapshot = SecurityTimeline(database).snapshot("idempotency-demo")

    assert result["retry"] == "IDEMPOTENT_REPLAY"
    assert result["email_messages_after_restart_and_retry"] == 1
    assert sum(event.event_type == "EFFECT_EXECUTION" for event in snapshot.events) == 1
    assert any(event.event_type == "EFFECT_REPLAY" for event in snapshot.events)


def test_cli_timeline_exports_same_structured_projection(tmp_path, capsys):
    database = tmp_path / "runtime.db"
    run_idempotency(database)

    assert main(["timeline", "idempotency-demo", "--db", str(database)]) == 0
    output = json.loads(capsys.readouterr().out)
    expected = SecurityTimeline(database).snapshot("idempotency-demo")
    assert output["run_id"] == expected.run_id
    expected_json = json.loads(SecurityTimeline(database).to_json("idempotency-demo"))
    assert output["events"] == expected_json["events"]


def test_dashboard_demos_use_fresh_isolated_databases():
    first = run_demo("idempotency")
    second = run_demo("idempotency")
    try:
        assert first.database != second.database
        assert first.result["email_messages_after_restart_and_retry"] == 1
        assert second.result["email_messages_after_restart_and_retry"] == 1
    finally:
        first.close()
        second.close()
