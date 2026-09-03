from __future__ import annotations

import json

import pytest

from agentshield.adapters.base import ToolRegistry, ToolRiskMetadata
from agentshield.adapters.langgraph import LangGraphAdapter, ToolCallBlocked
from agentshield.policy.rules import Decision
from agentshield.shield import AgentShield
from examples.langgraph_customer_service.agent import build_customer_service_agent


def _input(text="test"):
    return {"messages": [{"role": "user", "content": text}]}


def _session(tmp_path, *, shield=None):
    agent = build_customer_service_agent()
    session = LangGraphAdapter(
        shield or AgentShield(["GDPR"]), agent.tool_registry,
        trajectory_id="failure-run", audit_directory=tmp_path,
    )
    session.on_user_request(_input())
    return agent, session


def _events(session):
    return [
        json.loads(line)["event"]["event_type"]
        for line in session.audit_path.read_text().splitlines()
    ]


def test_tool_exception_is_audited_and_not_reported_safe(tmp_path):
    agent, session = _session(tmp_path)
    records = session.call_tool("search_customers", region="EU")
    agent.email.fail_next = True
    with pytest.raises(RuntimeError, match="injected mock email failure"):
        session.call_tool(
            "send_email", recipient="partner@example.test", body=records.value,
            data_object_id=records.data_object_id, purpose="customer_service",
        )
    assert agent.email.outbox == []
    assert "AGENT_ERROR" in _events(session)


def test_unknown_detector_escalates_external_transfer(tmp_path):
    class UnknownDetector:
        name = "unknown"

        def detect(self, content, context=None):
            raise ValueError("classification unavailable")

    shield = AgentShield(["GDPR"])
    shield.detector = UnknownDetector()
    agent, session = _session(tmp_path, shield=shield)
    records = session.call_tool("search_customers", region="EU")
    with pytest.raises(ToolCallBlocked) as caught:
        session.call_tool(
            "send_email", recipient="partner@example.test", body=records.value,
            data_object_id=records.data_object_id, purpose="customer_service",
        )
    assert caught.value.outcome == Decision.REQUIRE_APPROVAL
    assert agent.email.calls == 0


def test_unknown_high_risk_tool_metadata_escalates(tmp_path):
    calls = []
    registry = ToolRegistry()

    def external_submit(payload):
        calls.append(payload)

    registry.register(
        external_submit,
        risk=ToolRiskMetadata(side_effect=None, data_sink=True, trust_boundary="external"),
    )
    session = LangGraphAdapter(
        AgentShield(["GDPR"]), registry,
        trajectory_id="unknown-tool", audit_directory=tmp_path,
    )
    session.on_user_request(_input())
    with pytest.raises(ToolCallBlocked) as caught:
        session.call_tool("external_submit", payload={"value": 1})
    assert caught.value.outcome == Decision.REQUIRE_APPROVAL
    assert calls == []


def test_audit_logger_failure_defaults_fail_closed_before_tool(tmp_path):
    agent, session = _session(tmp_path)

    def fail(_entry):
        raise OSError("audit disk unavailable")

    session.harness.audit.append = fail
    with pytest.raises(OSError, match="audit disk unavailable"):
        session.call_tool("search_customers", region="EU")
    assert agent.crm.search_calls == 0
    assert session.harness.metrics["audit_failures"] == 1


def test_audit_logger_can_be_configured_fail_open(tmp_path):
    agent, session = _session(tmp_path)
    session.harness.audit_failure_mode = "fail_open"

    def fail(_entry):
        raise OSError("audit disk unavailable")

    session.harness.audit.append = fail
    observation = session.call_tool("search_customers", region="EU")
    assert observation.data_object_id == "customer-records-001"
    assert agent.crm.search_calls == 1
    assert session.harness.metrics["audit_failures"] == 2
