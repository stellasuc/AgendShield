"""Pinned, read-only discovery of the open-source components used by the paper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True, slots=True)
class UpstreamProject:
    project_id: str
    display_name: str
    repository: str
    revision: str
    license: str
    relative_path: str
    required_paths: tuple[str, ...]
    role: str


@dataclass(frozen=True, slots=True)
class UpstreamStatus:
    project: UpstreamProject
    root: Path
    installed: bool
    actual_revision: str | None
    revision_matches: bool
    required_files_present: bool
    detail: str

    @property
    def ready(self) -> bool:
        return self.installed and self.revision_matches and self.required_files_present

    def audit_view(self) -> dict[str, object]:
        return {
            "project_id": self.project.project_id,
            "display_name": self.project.display_name,
            "repository": self.project.repository,
            "expected_revision": self.project.revision,
            "actual_revision": self.actual_revision,
            "license": self.project.license,
            "role": self.project.role,
            "ready": self.ready,
            "detail": self.detail,
        }


UPSTREAM_PROJECTS: tuple[UpstreamProject, ...] = (
    UpstreamProject(
        project_id="autopolicy",
        display_name="AutoPolicy",
        repository="https://github.com/BillChan226/AutoPolicy.git",
        revision="7f02c713aa7f2541e2bdd40a47d5ecaf19ec880f",
        license="MIT",
        relative_path="AutoPolicy",
        required_paths=(
            "policy_extractor_async.py",
            "utility/policy_server.py",
            "agent/policy_construction/rule_extractor.py",
        ),
        role="法规文档解析、结构化政策抽取、自然语言规则与 LTL 候选规则抽取",
    ),
    UpstreamProject(
        project_id="awm",
        display_name="Agent Workflow Memory (AWM)",
        repository="https://github.com/zorazrw/agent-workflow-memory.git",
        revision="8c0ff8cd11d648c8fceb99e4e42f37e3b75381b1",
        license="Apache-2.0",
        relative_path="agent-workflow-memory",
        required_paths=(
            "webarena/run.py",
            "webarena/agents/legacy/agent.py",
            "webarena/workflow/shopping.txt",
        ),
        role="论文实验中的被保护 Web 任务 Agent",
    ),
    UpstreamProject(
        project_id="webarena",
        display_name="WebArena",
        repository="https://github.com/web-arena-x/webarena.git",
        revision="dce04686a56253aefba7b18a4fa0937cf1dc987b",
        license="Apache-2.0",
        relative_path="webarena",
        required_paths=("browser_env", "environment_docker", "config_files"),
        role="论文 Web 任务的开源网站与浏览器环境",
    ),
)


def default_upstream_root() -> Path:
    return Path(__file__).resolve().parents[2] / "third_party"


def inspect_upstreams(root: str | Path | None = None) -> tuple[UpstreamStatus, ...]:
    base = Path(root) if root is not None else default_upstream_root()
    return tuple(_inspect(project, base / project.relative_path) for project in UPSTREAM_PROJECTS)


def upstream_status(project_id: str, root: str | Path | None = None) -> UpstreamStatus:
    normalized = project_id.strip().lower()
    for status in inspect_upstreams(root):
        if status.project.project_id == normalized:
            return status
    raise KeyError(f"Unknown upstream project: {project_id}")


def _inspect(project: UpstreamProject, checkout: Path) -> UpstreamStatus:
    installed = checkout.is_dir()
    required = installed and all((checkout / item).exists() for item in project.required_paths)
    revision = _git_revision(checkout) if installed else None
    matches = revision == project.revision
    if not installed:
        detail = "未初始化；请运行 git submodule update --init --recursive"
    elif not required:
        detail = "目录存在，但缺少上游入口文件"
    elif revision is None:
        detail = "无法读取 Git revision"
    elif not matches:
        detail = f"版本不匹配：当前 {revision[:12]}，期望 {project.revision[:12]}"
    else:
        detail = f"已固定到 {revision[:12]}"
    return UpstreamStatus(project, checkout, installed, revision, matches, required, detail)


def _git_revision(checkout: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip().lower()
    return revision if len(revision) == 40 else None
