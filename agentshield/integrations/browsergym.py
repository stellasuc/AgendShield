"""Online ShieldAgent gate for an existing BrowserGym-compatible task agent."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Protocol
from uuid import uuid4

from agentshield.policy.rules import Decision
from agentshield.runtime.lifecycle import EventType, LifecycleEvent
from agentshield.shield import AgentShield


AWM_BID_ACTIONS = frozenset({
    "click", "dblclick", "hover", "fill", "select_option", "press", "focus", "clear",
    "drag_and_drop", "upload_file", "scroll", "send_msg_to_user", "noop",
    "report_infeasible", "new_tab", "tab_close", "tab_focus", "goto", "go_back",
    "go_forward",
})


class BrowserAgent(Protocol):
    action_set: object

    def obs_preprocessor(self, observation: dict[str, Any]) -> dict[str, Any]: ...

    def get_action(self, observation: dict[str, Any]) -> tuple[str, dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class ActionVerification:
    allowed: bool
    action: str | None
    decision: str
    explanation: str
    action_names: tuple[str, ...]
    action_sha256: str
    shielding_plan: Mapping[str, object]
    repair_attempts: int
    user_handoff: Mapping[str, object] | None = None

    def audit_view(self) -> dict[str, object]:
        return {
            "record_type": "PLAN_STEP_DECISION",
            "allowed": self.allowed,
            "decision": self.decision,
            "explanation": self.explanation,
            "action_names": list(self.action_names),
            "action_sha256": self.action_sha256,
            "shielding_plan": dict(self.shielding_plan),
            "repair_attempts": self.repair_attempts,
            "user_handoff": dict(self.user_handoff) if self.user_handoff else None,
        }


class BrowserGymActionGuard:
    """Normalize a BrowserGym action and verify it before ``env.step``."""

    def __init__(
        self,
        regulations: tuple[str, ...],
        *,
        trajectory_id: str | None = None,
        audit_directory: str | Path = ".agentshield/audit",
        package_root: str | Path | None = None,
    ) -> None:
        self.trajectory_id = trajectory_id or f"webarena-{uuid4()}"
        self.shield = AgentShield(regulations, package_root=package_root)
        self.harness = self.shield.create_harness(self.trajectory_id, audit_directory)
        self._sequence = -1
        self._attempt = 0

    @property
    def audit_path(self) -> Path:
        return self.harness.audit.directory / f"{self.trajectory_id}.jsonl"

    @property
    def shield_trace_path(self) -> Path:
        return self.harness.audit.directory / f"{self.trajectory_id}.shield.jsonl"

    def verify(
        self,
        action: str,
        observation: Mapping[str, Any],
        agent_info: Mapping[str, Any] | None = None,
    ) -> ActionVerification:
        if not isinstance(action, str) or not action.strip():
            return self._record(self._invalid(action if isinstance(action, str) else "", "任务 Agent 未生成动作"))
        try:
            names = action_names(action)
        except ValueError as exc:
            return self._record(self._invalid(action, str(exc)))
        if not names:
            return self._record(self._invalid(action, "动作中没有可识别的 BrowserGym 调用"))
        unexpected = tuple(name for name in names if name not in AWM_BID_ACTIONS)
        if unexpected:
            return self._record(self._invalid(
                action,
                "动作包含 AWM bid action space 之外的调用：" + ", ".join(unexpected),
            ))

        self._attempt += 1
        event_type, side_effectful = classify_action(names, action, observation)
        object_id = f"browser-action-{self._attempt:04d}"
        goal = str(observation.get("goal") or "")
        purpose = "webarena_task"
        recipient = str(observation.get("url") or observation.get("current_url") or "webarena")
        metadata = {
            "runtime_phase": "BROWSER_ACTION_PROPOSED",
            "side_effectful": side_effectful,
            "trust_boundary": event_type in {EventType.EXTERNAL_TRANSFER, EventType.RESPONSE_GENERATED},
            "recipient_type": "external" if event_type == EventType.EXTERNAL_TRANSFER else "user",
            "data_object": {
                "object_id": object_id,
                "source": "awm.agent.get_action",
                "purpose": purpose,
                "attributes": {
                    "action_names": list(names),
                    "source_agent": "AWM",
                },
            },
            "adapter": "browsergym",
            "goal_sha256": sha256(goal.encode("utf-8")).hexdigest() if goal else None,
        }
        event = LifecycleEvent(
            trajectory_id=self.trajectory_id,
            sequence=self._next_sequence(),
            event_type=event_type,
            actor="AWM",
            tool="browsergym.high_level_action",
            input=None if event_type == EventType.RESPONSE_GENERATED else action,
            output=action if event_type == EventType.RESPONSE_GENERATED else None,
            data_object_ids=(object_id,),
            recipient=recipient,
            purpose=purpose,
            metadata=metadata,
        )
        result = self.harness.enforce(event)
        self._sequence = max(
            self._sequence,
            int(self.harness.state.audit_metadata.get("last_sequence", self._sequence)),
        )
        final = result.final_event
        final_payload = None if final is None else (
            final.output if event_type == EventType.RESPONSE_GENERATED else final.input
        )
        candidate = final_payload if isinstance(final_payload, str) else action
        repaired_to_browser_action = result.repair_attempts == 0 or (
            isinstance(final_payload, str) and final_payload != action
        )
        allowed = (
            result.outcome in {Decision.ALLOW, Decision.AUDIT_ONLY}
            and repaired_to_browser_action
        )
        decision = result.outcome.value if allowed else (
            "REPLAN" if result.repair_attempts and not repaired_to_browser_action else result.outcome.value
        )
        explanation = (
            result.decisions[-1].explanation if result.decisions else "ShieldAgent runtime gate"
        )
        plan = result.shielding_plans[-1].audit_view() if result.shielding_plans else {}
        action_sha256 = sha256(action.encode("utf-8")).hexdigest()
        user_handoff = _user_handoff(
            result.outcome,
            names,
            action_sha256,
            recipient,
            plan,
        )
        return self._record(ActionVerification(
            allowed=allowed,
            action=candidate if allowed else None,
            decision=decision,
            explanation=explanation,
            action_names=names,
            action_sha256=action_sha256,
            shielding_plan=plan,
            repair_attempts=result.repair_attempts,
            user_handoff=user_handoff,
        ))

    def verify_plan_step(
        self,
        action: str,
        observation: Mapping[str, Any],
        agent_info: Mapping[str, Any] | None = None,
    ) -> ActionVerification:
        """Verify an AWM candidate plan step before it becomes an executable action."""
        return self.verify(action, observation, agent_info)

    def _record(self, verdict: ActionVerification) -> ActionVerification:
        self._record_payload(verdict.audit_view())
        return verdict

    def _record_payload(self, payload: Mapping[str, object]) -> None:
        self.shield_trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.shield_trace_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(payload), ensure_ascii=False, default=str) + "\n")

    def _invalid(self, action: str, explanation: str) -> ActionVerification:
        return ActionVerification(
            allowed=False,
            action=None,
            decision="REPLAN",
            explanation=explanation,
            action_names=(),
            action_sha256=sha256(action.encode("utf-8")).hexdigest(),
            shielding_plan={},
            repair_attempts=0,
        )

    def _next_sequence(self) -> int:
        current = int(self.harness.state.audit_metadata.get("last_sequence", -1))
        self._sequence = max(self._sequence, current) + 1
        return self._sequence


class ShieldedBrowserAgent:
    """Compose an unmodified task agent with online feedback and pre-step blocking."""

    def __init__(
        self,
        delegate: BrowserAgent,
        guard: BrowserGymActionGuard,
        *,
        max_replans: int = 2,
        enable_user_handoff: bool = False,
    ) -> None:
        if max_replans < 0:
            raise ValueError("max_replans cannot be negative")
        self.delegate = delegate
        self.guard = guard
        self.max_replans = max_replans
        self.enable_user_handoff = enable_user_handoff
        self.action_set = delegate.action_set

    def obs_preprocessor(self, observation: dict[str, Any]) -> dict[str, Any]:
        return self.delegate.obs_preprocessor(observation)

    def get_action(self, observation: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # Deliberately pass the upstream observation through unchanged. AWM is
        # the protected agent: ShieldAgent must not alter its goal, chat, or
        # workflow prompt. Its returned action is treated as a candidate plan
        # step and checked before BrowserGym can execute it.
        current = dict(observation)
        attempts: list[dict[str, object]] = []
        last_info: dict[str, Any] = {}
        for replan in range(self.max_replans + 1):
            action, info = self.delegate.get_action(current)
            last_info = dict(info or {})
            verdict = self.guard.verify_plan_step(action, current, last_info)
            attempts.append(verdict.audit_view())
            if verdict.allowed and verdict.action is not None:
                last_info["agentshield"] = {
                    "status": "ALLOWED",
                    "attempts": attempts,
                    "audit_path": str(self.guard.audit_path),
                }
                return verdict.action, last_info
            if self.enable_user_handoff and verdict.user_handoff:
                last_info["agentshield"] = {
                    "status": "WAITING_USER",
                    "attempts": attempts,
                    "audit_path": str(self.guard.audit_path),
                    "user_handoff": dict(verdict.user_handoff),
                }
                return (
                    'send_msg_to_user("ShieldAgent paused this task for a scoped user action. Complete the requested step in the AgentShield console to continue.")',
                    last_info,
                )
            if replan < self.max_replans:
                current = dict(current)
                current["last_action_error"] = _feedback(verdict)

        last_info["agentshield"] = {
            "status": "BLOCKED",
            "attempts": attempts,
            "audit_path": str(self.guard.audit_path),
        }
        return (
            "send_msg_to_user(\"ShieldAgent blocked this action because it could not satisfy the selected policy.\")",
            last_info,
        )
def action_names(action: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(action)
    except SyntaxError as exc:
        raise ValueError("任务 Agent 动作不是可解析的 BrowserGym action") from exc
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name):
            names.append(function.id)
        elif isinstance(function, ast.Attribute):
            names.append(function.attr)
    return tuple(names)


def classify_action(
    names: tuple[str, ...],
    action: str,
    observation: Mapping[str, Any],
) -> tuple[EventType, bool]:
    normalized = {item.lower() for item in names}
    if "send_msg_to_user" in normalized:
        return EventType.RESPONSE_GENERATED, True
    transfer = {"fill", "type", "upload_file", "set_input_files"}
    if normalized & transfer:
        return EventType.EXTERNAL_TRANSFER, True
    direct_effect = {"delete", "submit", "post", "purchase", "checkout"}
    if normalized & direct_effect:
        return EventType.TOOL_CALL, True
    if normalized & {"click", "press", "select_option", "drag_and_drop"}:
        evidence = " ".join(
            str(observation.get(key, "")) for key in ("axtree_txt", "dom_txt", "pruned_html")
        )
        effect_words = r"submit|send|post|publish|delete|remove|checkout|place order|buy now|confirm|save"
        side_effectful = bool(re.search(effect_words, action + " " + evidence, re.IGNORECASE))
        return EventType.TOOL_CALL, side_effectful
    return EventType.TOOL_CALL, False


def _feedback(verdict: ActionVerification) -> str:
    rules = verdict.shielding_plan.get("circuits", []) if verdict.shielding_plan else []
    rule_ids = [str(item.get("rule_id")) for item in rules if isinstance(item, dict)]
    suffix = f" Relevant rules: {', '.join(rule_ids)}." if rule_ids else ""
    return (
        f"ShieldAgent rejected the proposed action ({verdict.decision}). "
        "Replan without bypassing the policy gate or exposing protected data."
        f"{suffix}"
    )


def _user_handoff(
    outcome: Decision,
    action_names_: tuple[str, ...],
    action_sha256: str,
    recipient: str,
    shielding_plan: Mapping[str, object],
) -> dict[str, object] | None:
    if outcome not in {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_CONSENT}:
        return None
    action_kind = "MANUAL_SENSITIVE_INPUT" if set(action_names_) & {"fill", "upload_file"} else "MANUAL_REVIEW"
    instruction = (
        "请在目标网站中亲自完成涉及个人或敏感信息的输入，完成后返回 AgentShield 确认；不要把信息填写到 Agent Prompt 或完成说明中。"
        if action_kind == "MANUAL_SENSITIVE_INPUT"
        else "请人工检查该动作的接收方、目的和数据范围，确认已完成必要授权后返回 AgentShield。"
    )
    now = datetime.now(timezone.utc)
    circuits = shielding_plan.get("circuits", []) if shielding_plan else []
    return {
        "handoff_id": f"UH-{uuid4().hex[:12]}",
        "status": "PENDING_USER",
        "action_kind": action_kind,
        "instruction": instruction,
        "action_sha256": action_sha256,
        "recipient_sha256": sha256(recipient.encode("utf-8")).hexdigest(),
        "rule_ids": [str(item.get("rule_id")) for item in circuits if isinstance(item, dict)],
        "evidence_type": "USER_ATTESTATION",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
    }
