from __future__ import annotations

import json

import pytest

from agentshield.cli import main
from agentshield.integrations.awm_runner import (
    _install_openai_tokenizer_fallback,
    _raise_on_browsergym_failure,
)
from agentshield.integrations.awm_webarena import (
    AWMWebArenaConfig,
    AWMWebArenaRunner,
    _emit_trace_updates,
    inspect_awm_webarena,
)
from agentshield.integrations.upstreams import inspect_upstreams


def test_all_paper_upstreams_are_present_and_pinned():
    statuses = inspect_upstreams()
    assert {item.project.project_id for item in statuses} == {"autopolicy", "awm", "webarena"}
    assert all(item.ready for item in statuses)
    assert {item.project.license for item in statuses} == {"MIT", "Apache-2.0"}


def test_awm_webarena_readiness_never_requires_api_key_in_arguments():
    environment = {
        "OPENAI_API_KEY": "secret",
        "SHOPPING": "http://shopping.local",
        "SHOPPING_ADMIN": "http://admin.local",
        "REDDIT": "http://reddit.local",
        "GITLAB": "http://gitlab.local",
        "MAP": "http://map.local",
        "WIKIPEDIA": "http://wiki.local",
        "HOMEPAGE": "http://home.local",
    }
    assert inspect_awm_webarena(environment).ready is True
    assert AWMWebArenaConfig(task_name="webarena.0").task_name == "webarena.0"
    openended = AWMWebArenaConfig(
        task_name="openended",
        task_prompt="在购物站寻找一款耳机，不要下单。",
        start_url="http://shopping.local",
    )
    assert openended.task_prompt.startswith("在购物站")


def test_upstream_status_cli(capsys):
    assert main(["upstream", "status"]) == 0
    output = capsys.readouterr().out
    assert "AutoPolicy" in output
    assert "Agent Workflow Memory" in output
    assert "WebArena" in output
    assert output.count("READY") == 3


def test_awm_command_uses_isolated_python_without_prompt_or_key(tmp_path):
    runner = AWMWebArenaRunner(python_executable="awm-python")
    config = AWMWebArenaConfig(
        task_name="openended",
        task_prompt="包含隐私的用户任务，不应进入 argv",
        start_url="http://shopping.local",
    )

    command = runner.build_command(config, tmp_path, trajectory_id="awm-test-run")

    assert command[0] == "awm-python"
    assert command[command.index("--trajectory-id") + 1] == "awm-test-run"
    assert config.task_prompt not in command
    assert not any("secret" in item.lower() or "api_key" in item.lower() for item in command)


def test_awm_trace_updates_are_emitted_once(tmp_path):
    trace = tmp_path / "audit" / "awm-webarena-openended.shield.jsonl"
    trace.parent.mkdir()
    trace.write_text(json.dumps({"decision": "ALLOW", "allowed": True}) + "\n", encoding="utf-8")
    updates = []

    offset = _emit_trace_updates(trace, 0, lambda event, payload: updates.append((event, payload)))
    unchanged = _emit_trace_updates(trace, offset, lambda event, payload: updates.append((event, payload)))

    assert unchanged == offset
    assert updates == [("paper_action_verified", {"decision": "ALLOW", "allowed": True})]


def test_unknown_openai_compatible_model_uses_tokenizer_fallback():
    fallback = object()

    class FakeTiktoken:
        @staticmethod
        def get_encoding(name):
            assert name == "cl100k_base"
            return fallback

    class FakeLLMUtils:
        tiktoken = FakeTiktoken()

        @staticmethod
        def get_tokenizer(model_name="openai/gpt-4"):
            if model_name == "openai/MiniMax-M2.7":
                raise KeyError(model_name)
            return "known-tokenizer"

    assert _install_openai_tokenizer_fallback(FakeLLMUtils, "openai/MiniMax-M2.7") is True
    assert FakeLLMUtils.get_tokenizer("openai/MiniMax-M2.7") is fallback
    assert FakeLLMUtils.get_tokenizer("openai/gpt-4") == "known-tokenizer"


def test_browsergym_recorded_failure_is_not_reported_as_success(tmp_path):
    (tmp_path / "summary_info.json").write_text(
        json.dumps({"n_steps": 0, "err_msg": "tokenizer mapping failed"}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="tokenizer mapping failed"):
        _raise_on_browsergym_failure(tmp_path)


def test_browsergym_clean_summary_is_accepted(tmp_path):
    (tmp_path / "summary_info.json").write_text(
        json.dumps({"n_steps": 2, "err_msg": None}),
        encoding="utf-8",
    )

    _raise_on_browsergym_failure(tmp_path)
