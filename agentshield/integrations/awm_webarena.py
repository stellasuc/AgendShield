"""Configuration and subprocess launcher for pinned AWM on open-source WebArena."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping
import uuid

from agentshield.integrations.upstreams import inspect_upstreams


WEBARENA_URL_VARIABLES = (
    "SHOPPING",
    "SHOPPING_ADMIN",
    "REDDIT",
    "GITLAB",
    "MAP",
    "WIKIPEDIA",
    "HOMEPAGE",
)


def default_awm_python() -> str:
    """Prefer the isolated legacy-AWM environment when it has been installed."""
    project_root = Path(__file__).resolve().parents[2]
    isolated = project_root / ".venv-awm" / "bin" / "python"
    return str(isolated) if isolated.is_file() else sys.executable


def awm_runtime_ready(python_executable: str | None = None) -> bool:
    """Check the imports needed by the pinned AWM runner without loading them here."""
    executable = python_executable or default_awm_python()
    try:
        completed = subprocess.run(
            [
                executable,
                "-c",
                "import browsergym.experiments; import browsergym.webarena; import langchain_openai",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


@dataclass(frozen=True, slots=True)
class AWMWebArenaConfig:
    task_name: str
    model_name: str = "openai/gpt-4o"
    regulations: tuple[str, ...] = ("GDPR",)
    workflow: str = "shopping"
    max_steps: int = 10
    headless: bool = True
    max_replans: int = 2
    task_prompt: str = ""
    start_url: str = ""

    def __post_init__(self) -> None:
        if self.task_name == "openended":
            if not self.task_prompt.strip():
                raise ValueError("Open-ended WebArena-site execution requires task_prompt")
            if not self.start_url.startswith(("https://", "http://")):
                raise ValueError("Open-ended execution requires an HTTP(S) start_url")
        else:
            if not self.task_name.startswith("webarena."):
                raise ValueError("task_name must be openended or webarena.<task_id>")
            suffix = self.task_name.removeprefix("webarena.")
            if not suffix.isdigit() or not 0 <= int(suffix) <= 811:
                raise ValueError("WebArena task id must be between 0 and 811")
        if self.workflow not in {"shopping", "shopping_admin", "gitlab", "reddit", "map"}:
            raise ValueError("Unsupported AWM workflow")
        if not self.model_name.startswith("openai/"):
            raise ValueError("Pinned AWM currently expects an openai/<model> ChatOpenAI name")
        if not self.regulations:
            raise ValueError("At least one regulation is required")
        if not 1 <= self.max_steps <= 100:
            raise ValueError("max_steps must be between 1 and 100")


@dataclass(frozen=True, slots=True)
class AWMWebArenaReadiness:
    upstreams_ready: bool
    missing_url_variables: tuple[str, ...]
    api_key_present: bool

    @property
    def ready(self) -> bool:
        return self.upstreams_ready and not self.missing_url_variables and self.api_key_present

    def audit_view(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "upstreams_ready": self.upstreams_ready,
            "missing_url_variables": list(self.missing_url_variables),
            "api_key_present": self.api_key_present,
        }


def inspect_awm_webarena(
    environment: Mapping[str, str] | None = None,
    *,
    upstream_root: str | Path | None = None,
) -> AWMWebArenaReadiness:
    values = dict(os.environ if environment is None else environment)
    statuses = {item.project.project_id: item for item in inspect_upstreams(upstream_root)}
    needed = ("awm", "webarena")
    upstreams_ready = all(statuses[name].ready for name in needed)
    missing = tuple(name for name in WEBARENA_URL_VARIABLES if not values.get(name, "").strip())
    return AWMWebArenaReadiness(
        upstreams_ready=upstreams_ready,
        missing_url_variables=missing,
        api_key_present=bool(values.get("OPENAI_API_KEY", "").strip()),
    )


class AWMWebArenaRunner:
    """Launch the local ShieldAgent wrapper around the unmodified AWM agent."""

    def __init__(
        self,
        *,
        upstream_root: str | Path | None = None,
        python_executable: str | None = None,
    ) -> None:
        statuses = {item.project.project_id: item for item in inspect_upstreams(upstream_root)}
        for project_id in ("awm", "webarena"):
            if not statuses[project_id].ready:
                raise RuntimeError(f"{statuses[project_id].project.display_name} 不可用：{statuses[project_id].detail}")
        self.awm_root = statuses["awm"].root
        self.webarena_root = statuses["webarena"].root
        self.upstream_root = Path(upstream_root) if upstream_root is not None else None
        self.python_executable = python_executable or default_awm_python()

    def build_command(
        self,
        config: AWMWebArenaConfig,
        output_root: str | Path,
        *,
        trajectory_id: str = "",
    ) -> tuple[str, ...]:
        return (
            self.python_executable,
            "-m",
            "agentshield.integrations.awm_runner",
            "--awm-root",
            str(self.awm_root),
            "--webarena-root",
            str(self.webarena_root),
            "--task-name",
            config.task_name,
            "--model-name",
            config.model_name,
            "--workflow",
            config.workflow,
            "--regulations",
            *config.regulations,
            "--max-steps",
            str(config.max_steps),
            "--max-replans",
            str(config.max_replans),
            "--output-root",
            str(Path(output_root).expanduser().resolve()),
            "--trajectory-id",
            trajectory_id,
            "--headless",
            "true" if config.headless else "false",
            "--start-url",
            config.start_url,
        )

    def run(
        self,
        config: AWMWebArenaConfig,
        output_root: str | Path,
        *,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: int = 3600,
        progress_callback: Callable[[str, Mapping[str, object]], None] | None = None,
    ) -> Mapping[str, object]:
        process_environment = os.environ.copy()
        process_environment.update(dict(environment or {}))
        readiness = inspect_awm_webarena(
            process_environment,
            upstream_root=self.upstream_root,
        )
        if config.task_name == "openended":
            ready = bool(process_environment.get("OPENAI_API_KEY", "").strip())
        else:
            ready = readiness.ready
        if not ready:
            raise RuntimeError(f"AWM/WebArena 尚未就绪：{json.dumps(readiness.audit_view(), ensure_ascii=False)}")
        if config.task_prompt:
            process_environment["AGENTSHIELD_TASK_PROMPT"] = config.task_prompt
        output_path = Path(output_root).expanduser().resolve()
        task_id = config.task_name.removeprefix("webarena.")
        trajectory_id = f"awm-webarena-{task_id}-{uuid.uuid4().hex[:12]}"
        trace_path = output_path / "audit" / f"{trajectory_id}.shield.jsonl"
        trace_offset = 0
        started_at = time.monotonic()
        with (
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout_stream,
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr_stream,
        ):
            process = subprocess.Popen(
                self.build_command(config, output_root, trajectory_id=trajectory_id),
                cwd=Path(__file__).resolve().parents[2],
                env=process_environment,
                stdout=stdout_stream,
                stderr=stderr_stream,
                text=True,
            )
            try:
                while process.poll() is None:
                    trace_offset = _emit_trace_updates(trace_path, trace_offset, progress_callback)
                    if time.monotonic() - started_at > timeout_seconds:
                        process.kill()
                        process.wait()
                        raise RuntimeError(f"Shielded AWM run timed out after {timeout_seconds} seconds")
                    time.sleep(0.35)
                trace_offset = _emit_trace_updates(trace_path, trace_offset, progress_callback)
            except BaseException:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                raise
            stdout_stream.seek(0)
            stderr_stream.seek(0)
            stdout = stdout_stream.read()
            stderr = stderr_stream.read()
            returncode = process.returncode

        if returncode != 0:
            tail = "\n".join(stderr.splitlines()[-12:])
            raise RuntimeError(f"Shielded AWM run failed ({returncode}): {tail}")
        for line in reversed(stdout.splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("type") == "agentshield_run_result":
                return payload
        raise RuntimeError("Shielded AWM run completed without a machine-readable result")


def _emit_trace_updates(
    trace_path: Path,
    offset: int,
    callback: Callable[[str, Mapping[str, object]], None] | None,
) -> int:
    """Emit complete ShieldAgent JSONL records written since the last poll."""
    if not trace_path.is_file():
        return offset
    try:
        with trace_path.open("r", encoding="utf-8") as stream:
            stream.seek(offset)
            lines = stream.readlines()
            next_offset = stream.tell()
    except OSError:
        return offset
    if callback is not None:
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                callback("paper_action_verified", item)
    return next_offset
