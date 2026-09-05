from __future__ import annotations

import json

from agentshield.integrations.browsergym import (
    BrowserGymActionGuard,
    ShieldedBrowserAgent,
    _with_plan_constraints,
    action_names,
    classify_action,
)
from agentshield.runtime.lifecycle import EventType


def test_browsergym_action_parser_and_classification():
    assert action_names('click("12")\nfill("14", "query")') == ("click", "fill")
    assert classify_action(("fill",), 'fill("1", "query")', {}) == (
        EventType.EXTERNAL_TRANSFER,
        True,
    )


def test_browsergym_guard_allows_non_personal_navigation(tmp_path):
    guard = BrowserGymActionGuard(("GDPR",), audit_directory=tmp_path)
    verdict = guard.verify('click("12")', {"goal": "查看商品", "axtree_txt": "button 12 product"})

    assert verdict.allowed is True
    assert verdict.action == 'click("12")'
    assert verdict.action_names == ("click",)
    assert guard.audit_path.is_file()
    assert guard.shield_trace_path.is_file()


def test_plan_preflight_is_audited_and_constraints_are_injected_before_planning(tmp_path):
    guard = BrowserGymActionGuard(("GDPR",), audit_directory=tmp_path)
    preflight = guard.prepare_plan("把 alice@example.com 填入客户表单")

    constrained = _with_plan_constraints(
        {
            "goal": "把 alice@example.com 填入客户表单",
            "chat_messages": [{"role": "user", "message": "完成表单"}],
        },
        preflight,
    )
    records = [json.loads(line) for line in guard.shield_trace_path.read_text().splitlines()]

    assert preflight.allowed is True
    assert preflight.decision == "PLAN_CONSTRAINED"
    assert preflight.detected_categories
    assert records[0]["record_type"] == "PLAN_PREFLIGHT"
    assert "alice@example.com" not in json.dumps(records[0])
    assert "[AgentShield verified planning constraints]" in constrained["goal"]
    assert constrained["chat_messages"][-1]["role"] == "system"


def test_empty_goal_is_blocked_before_delegate_planning(tmp_path):
    delegate = _Agent(['click("9")'])
    shielded = ShieldedBrowserAgent(
        delegate,
        BrowserGymActionGuard(("GDPR",), audit_directory=tmp_path),
    )

    action, info = shielded.get_action({"goal": ""})

    assert action.startswith("send_msg_to_user")
    assert info["agentshield"]["status"] == "PLAN_BLOCKED"
    assert delegate.observations == []


def test_browsergym_guard_blocks_personal_data_fill_before_environment_step(tmp_path):
    guard = BrowserGymActionGuard(("GDPR",), audit_directory=tmp_path)
    verdict = guard.verify(
        'fill("12", "alice@example.com")',
        {"goal": "提交表单", "url": "http://shopping.local/form"},
    )

    assert verdict.allowed is False
    assert verdict.action is None
    assert verdict.decision in {"REQUIRE_APPROVAL", "REPLAN"}
    assert verdict.shielding_plan["circuits"]
    assert verdict.user_handoff
    assert verdict.user_handoff["status"] == "PENDING_USER"
    assert "alice@example.com" not in json.dumps(verdict.user_handoff)


def test_pipl_guard_blocks_sensitive_test_identifiers_before_environment_step(tmp_path):
    for index, value in enumerate(("110101199001011234", "4242424242424242")):
        guard = BrowserGymActionGuard(
            ("PIPL",),
            trajectory_id=f"pipl-sensitive-{index}",
            audit_directory=tmp_path,
        )
        verdict = guard.verify(
            f'fill("12", "{value}")',
            {"goal": "执行敏感信息防护测试", "url": "http://shopping.local"},
        )

        assert verdict.allowed is False
        assert verdict.action is None
        assert verdict.decision in {"REQUIRE_APPROVAL", "REQUIRE_CONSENT", "REPLAN"}
        assert verdict.shielding_plan["circuits"]


def test_browsergym_guard_blocks_personal_data_in_agent_response(tmp_path):
    guard = BrowserGymActionGuard(("GDPR",), audit_directory=tmp_path)
    verdict = guard.verify(
        'send_msg_to_user("Contact alice@example.com")',
        {"goal": "回答用户"},
    )

    assert verdict.allowed is False
    assert verdict.action is None


def test_browsergym_guard_rejects_calls_outside_awm_action_space(tmp_path):
    guard = BrowserGymActionGuard(("GDPR",), audit_directory=tmp_path)
    verdict = guard.verify('system("curl example.com")', {"goal": "浏览网页"})

    assert verdict.allowed is False
    assert verdict.decision == "REPLAN"


class _Agent:
    action_set = object()

    def __init__(self, actions):
        self.actions = iter(actions)
        self.observations = []

    def obs_preprocessor(self, observation):
        return {**observation, "processed": True}

    def get_action(self, observation):
        self.observations.append(dict(observation))
        return next(self.actions), {"delegate": "AWM"}


def test_shielded_agent_sends_feedback_to_existing_agent_and_replans(tmp_path):
    delegate = _Agent(['fill("12", "alice@example.com")', 'click("9")'])
    shielded = ShieldedBrowserAgent(
        delegate,
        BrowserGymActionGuard(("GDPR",), audit_directory=tmp_path),
        max_replans=1,
    )

    action, info = shielded.get_action({"goal": "完成任务", "last_action_error": ""})

    assert action == 'click("9")'
    assert "ShieldAgent rejected" in delegate.observations[1]["last_action_error"]
    assert info["agentshield"]["status"] == "ALLOWED"
    assert len(info["agentshield"]["attempts"]) == 2
    assert "[AgentShield verified planning constraints]" in delegate.observations[0]["goal"]
    records = [json.loads(line) for line in shielded.guard.shield_trace_path.read_text().splitlines()]
    assert records[0]["record_type"] == "PLAN_PREFLIGHT"
    assert records[1]["record_type"] == "PLAN_STEP_DECISION"


def test_shielded_agent_pauses_for_scoped_user_handoff_when_enabled(tmp_path):
    delegate = _Agent(['fill("12", "alice@example.com")'])
    shielded = ShieldedBrowserAgent(
        delegate,
        BrowserGymActionGuard(("GDPR",), audit_directory=tmp_path),
        max_replans=2,
        enable_user_handoff=True,
    )

    action, info = shielded.get_action({"goal": "提交测试客户资料", "url": "http://shopping.local"})

    assert action.startswith("send_msg_to_user")
    assert info["agentshield"]["status"] == "WAITING_USER"
    assert info["agentshield"]["user_handoff"]["handoff_id"].startswith("UH-")
    assert len(delegate.observations) == 1
