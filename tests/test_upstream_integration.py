from __future__ import annotations

from agentshield.cli import main
from agentshield.integrations.awm_webarena import (
    AWMWebArenaConfig,
    AWMWebArenaRunner,
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

    command = runner.build_command(config, tmp_path)

    assert command[0] == "awm-python"
    assert config.task_prompt not in command
    assert not any("secret" in item.lower() or "api_key" in item.lower() for item in command)
