"""Runtime entry point that composes pinned AWM with the AgentShield BrowserGym gate."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any

from agentshield.integrations.browsergym import BrowserGymActionGuard, ShieldedBrowserAgent

try:
    from browsergym.experiments import AbstractAgentArgs as _AbstractAgentArgs
except ImportError:  # Optional dependency: CLI help and core tests remain available.
    class _AbstractAgentArgs:  # type: ignore[no-redef]
        pass


@dataclass(kw_only=True)
class ShieldedAWMArgs(_AbstractAgentArgs):
    """Top-level serializable BrowserGym arguments for the composed agent."""

    delegate_args: Any
    regulations: tuple[str, ...]
    trajectory_id: str
    audit_directory: str
    max_replans: int

    def make_agent(self):
        delegate = self.delegate_args.make_agent()
        guard = BrowserGymActionGuard(
            self.regulations,
            trajectory_id=self.trajectory_id,
            audit_directory=self.audit_directory,
        )
        return ShieldedBrowserAgent(delegate, guard, max_replans=self.max_replans)


def _install_openai_tokenizer_fallback(llm_utils: Any, model_name: str) -> bool:
    """Let AWM estimate tokens for OpenAI-compatible models unknown to tiktoken."""
    if not model_name.startswith("openai/"):
        return False
    try:
        llm_utils.get_tokenizer(model_name)
        return False
    except KeyError:
        pass

    original_get_tokenizer = llm_utils.get_tokenizer
    fallback = llm_utils.tiktoken.get_encoding("cl100k_base")

    def compatible_get_tokenizer(requested_model: str = "openai/gpt-4"):
        try:
            return original_get_tokenizer(requested_model)
        except KeyError:
            if requested_model.startswith("openai/"):
                return fallback
            raise

    llm_utils.get_tokenizer = compatible_get_tokenizer
    return True


def _raise_on_browsergym_failure(experiment_directory: str | Path) -> None:
    """BrowserGym 0.3 records loop failures without returning a non-zero status."""
    summary_path = Path(experiment_directory) / "summary_info.json"
    if not summary_path.is_file():
        raise RuntimeError("BrowserGym 未生成执行摘要")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("BrowserGym 执行摘要无法读取") from exc
    error = str(summary.get("err_msg") or "").strip()
    if error:
        raise RuntimeError(f"BrowserGym 执行失败：{error}")


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run pinned AWM behind ShieldAgent on WebArena")
    parser.add_argument("--awm-root", required=True)
    parser.add_argument("--webarena-root", required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--model-name", default="openai/gpt-4o")
    parser.add_argument("--workflow", default="shopping")
    parser.add_argument("--regulations", nargs="+", required=True)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--max-replans", type=int, default=2)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--headless", type=_bool, default=True)
    parser.add_argument("--start-url", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    awm_web = Path(args.awm_root).resolve() / "webarena"
    canonical_webarena = Path(args.webarena_root).resolve()
    if not (awm_web / "agents" / "legacy" / "agent.py").is_file():
        raise SystemExit("Pinned AWM entry point not found")
    if not (canonical_webarena / "browser_env").is_dir():
        raise SystemExit("Pinned WebArena environment source not found")
    sys.path.insert(0, str(awm_web))

    try:
        from browsergym.experiments import EnvArgs, ExpArgs
        from agents.legacy.agent import GenericAgentArgs
        from agents.legacy.dynamic_prompting import Flags
        from agents.legacy.utils.chat_api import ChatModelArgs
        from agents.legacy.utils import llm_utils
    except ImportError as exc:
        raise SystemExit(
            "AWM/BrowserGym dependencies are missing; install third_party/agent-workflow-memory/webarena/requirements.txt"
        ) from exc

    _install_openai_tokenizer_fallback(llm_utils, args.model_name)

    output = Path(args.output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    audit = output / "audit"
    workflow = awm_web / "workflow" / f"{args.workflow}.txt"

    task_id = args.task_name.removeprefix("webarena.")
    trajectory_id = f"awm-webarena-{task_id}"
    delegate_args = GenericAgentArgs(
        chat_model_args=ChatModelArgs(
            model_name=args.model_name,
            max_total_tokens=128_000,
            max_input_tokens=126_000,
            max_new_tokens=2_000,
        ),
        flags=Flags(
            use_html=False,
            use_ax_tree=True,
            use_thinking=True,
            use_error_logs=True,
            use_memory=False,
            use_history=True,
            use_diff=False,
            use_past_error_logs=True,
            use_action_history=True,
            multi_actions=True,
            use_abstract_example=True,
            use_concrete_example=True,
            use_screenshot=True,
            enable_chat=True,
            demo_mode="off" if args.headless else "default",
            workflow_path=str(workflow),
        ),
    )
    env_args = EnvArgs(
        task_name=args.task_name,
        task_seed=None,
        max_steps=args.max_steps,
        headless=args.headless,
        viewport={"width": 1500, "height": 1280},
        slow_mo=0 if args.headless else 30,
    )
    if args.task_name == "openended":
        prompt = os.environ.get("AGENTSHIELD_TASK_PROMPT", "").strip()
        if not prompt:
            raise SystemExit("AGENTSHIELD_TASK_PROMPT is required for BrowserGym openended execution")
        if not args.start_url.startswith(("http://", "https://")):
            raise SystemExit("--start-url is required for BrowserGym openended execution")
        env_args.wait_for_user_message = False
        env_args.task_kwargs = {"start_url": args.start_url, "goal": prompt}

    experiment = ExpArgs(
        env_args=env_args,
        agent_args=ShieldedAWMArgs(
            delegate_args=delegate_args,
            regulations=tuple(item.upper() for item in args.regulations),
            trajectory_id=trajectory_id,
            audit_directory=str(audit),
            max_replans=args.max_replans,
        ),
    )
    experiment.prepare(output)
    experiment.run()
    _raise_on_browsergym_failure(experiment.exp_dir)
    print(json.dumps({
        "type": "agentshield_run_result",
        "task_name": args.task_name,
        "task_agent": "AWM",
        "environment": "WebArena",
        "experiment_directory": str(experiment.exp_dir),
        "audit_path": str(audit / f"{trajectory_id}.jsonl"),
        "shield_trace_path": str(audit / f"{trajectory_id}.shield.jsonl"),
        "regulations": [item.upper() for item in args.regulations],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
