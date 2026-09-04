"""Fail-closed adapter for the paper authors' open-source AutoPolicy pipeline.

AutoPolicy is intentionally kept outside the trusted runtime.  Its LLM outputs are
loaded as provenance-preserving candidates and require human review before they may
be translated into executable AgentShield controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

import yaml

from agentshield.integrations.upstreams import upstream_status


class AutoPolicyArtifactError(ValueError):
    """Raised when an AutoPolicy artifact cannot pass structural validation."""


class AutoPolicyExecutionError(RuntimeError):
    """Raised when the pinned AutoPolicy subprocess does not complete successfully."""


@dataclass(frozen=True, slots=True)
class AutoPolicyExtractionRequest:
    document: str
    organization: str
    input_type: str
    organization_description: str = ""
    target_subject: str = "Web task agent"
    user_request: str = "提取约束 Web Agent 行为的明确政策"
    initial_page_range: str = "1-10000"
    deep_policy: bool = False
    exploration_budget: int = 20
    async_sections: int = 1

    def __post_init__(self) -> None:
        if self.input_type not in {"pdf", "html", "txt"}:
            raise ValueError("input_type must be pdf, html, or txt")
        if not self.document.strip() or not self.organization.strip():
            raise ValueError("document and organization are required")
        if self.input_type == "html" and not self.document.startswith(("https://", "http://")):
            raise ValueError("HTML policy input must be an HTTP(S) URL")
        if not 1 <= self.async_sections <= 3:
            raise ValueError("async_sections must be between 1 and 3")
        if self.exploration_budget < 1:
            raise ValueError("exploration_budget must be positive")


@dataclass(frozen=True, slots=True)
class ExtractedPolicyCandidate:
    policy_id: str
    definitions: tuple[str, ...]
    scope: str
    description: str
    references: tuple[str, ...]
    source_file: str


@dataclass(frozen=True, slots=True)
class ExtractedRuleCandidate:
    rule_id: str
    description: str
    source_policy_ids: tuple[str, ...]
    scope: str = ""
    term_definitions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LTLRuleCandidate:
    predicates: tuple[str, ...]
    description: str
    formula: str
    rule_type: str


@dataclass(frozen=True, slots=True)
class AutoPolicyBundle:
    extraction_directory: Path
    organization: str
    policies: tuple[ExtractedPolicyCandidate, ...]
    rules: tuple[ExtractedRuleCandidate, ...]
    ltl_rules: tuple[LTLRuleCandidate, ...]
    risk_categories: tuple[Mapping[str, Any], ...]
    policy_rule_mapping: Mapping[str, tuple[str, ...]]
    extraction_report: Mapping[str, Any]
    upstream_revision: str
    artifact_digest: str
    review_status: str = "REVIEW_REQUIRED"

    def audit_view(self) -> dict[str, object]:
        return {
            "producer": "AutoPolicy",
            "upstream_revision": self.upstream_revision,
            "organization": self.organization,
            "policies": len(self.policies),
            "natural_language_rules": len(self.rules),
            "ltl_candidate_rules": len(self.ltl_rules),
            "risk_categories": len(self.risk_categories),
            "artifact_digest": self.artifact_digest,
            "review_status": self.review_status,
            "executable": False,
        }


class AutoPolicyRunner:
    """Invoke the unmodified pinned upstream CLI without putting keys in argv."""

    def __init__(
        self,
        *,
        upstream_root: str | Path | None = None,
        python_executable: str = "python",
    ) -> None:
        status = upstream_status("autopolicy", upstream_root)
        if not status.ready:
            raise AutoPolicyExecutionError(f"AutoPolicy 上游不可用：{status.detail}")
        self.checkout = status.root
        self.revision = status.actual_revision or status.project.revision
        self.python_executable = python_executable

    def build_command(
        self,
        request: AutoPolicyExtractionRequest,
        output_root: str | Path,
    ) -> tuple[str, ...]:
        document = (
            request.document
            if request.input_type == "html"
            else str(Path(request.document).expanduser().resolve())
        )
        command = [
            self.python_executable,
            "policy_extractor_async.py",
            "--document-path",
            document,
            "--organization",
            request.organization,
            "--organization-description",
            request.organization_description,
            "--target-subject",
            request.target_subject,
            "--input-type",
            request.input_type,
            "--initial-page-range",
            request.initial_page_range,
            "--output-dir",
            str(Path(output_root).expanduser().resolve()),
            "--user-request",
            request.user_request,
            "--async-num",
            str(request.async_sections),
            "--exploration-budget",
            str(request.exploration_budget),
            "--extract-rules",
        ]
        if request.deep_policy:
            command.append("--deep-policy")
        return tuple(command)

    def run(
        self,
        request: AutoPolicyExtractionRequest,
        output_root: str | Path,
        *,
        environment: Mapping[str, str] | None = None,
        extract_ltl: bool = False,
        timeout_seconds: int = 1800,
    ) -> AutoPolicyBundle:
        output = Path(output_root).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        before = {item.resolve() for item in output.glob("extraction_*") if item.is_dir()}
        process_environment = os.environ.copy()
        process_environment.update(dict(environment or {}))
        # The pinned upstream currently hard-codes Claude in policy_server.py,
        # despite exposing a --model flag. Refuse a confusing keyless launch.
        if not process_environment.get("ANTHROPIC_API_KEY", "").strip():
            raise AutoPolicyExecutionError(
                "固定版本 AutoPolicy 的抽取工具需要通过环境变量 ANTHROPIC_API_KEY 提供密钥"
            )
        try:
            completed = subprocess.run(
                self.build_command(request, output),
                cwd=self.checkout,
                env=process_environment,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AutoPolicyExecutionError(f"AutoPolicy 启动失败：{type(exc).__name__}") from exc
        if completed.returncode != 0:
            tail = "\n".join(completed.stderr.splitlines()[-8:])
            raise AutoPolicyExecutionError(
                f"AutoPolicy 退出码 {completed.returncode}；错误末尾：{tail or '无错误输出'}"
            )
        candidates = [
            item for item in output.glob("extraction_*")
            if item.is_dir() and item.resolve() not in before
        ]
        if not candidates:
            candidates = [item for item in output.glob("extraction_*") if item.is_dir()]
        if not candidates:
            raise AutoPolicyExecutionError("AutoPolicy 未生成 extraction_* 目录")
        latest = max(candidates, key=lambda item: item.stat().st_mtime_ns)
        bundle = load_autopolicy_bundle(latest, upstream_revision=self.revision)
        if extract_ltl:
            bundle = self.extract_ltl(
                bundle,
                environment=process_environment,
                timeout_seconds=timeout_seconds,
            )
        return bundle

    def build_ltl_command(self, bundle: AutoPolicyBundle) -> tuple[str, ...]:
        policy_path = bundle.extraction_directory / f"{bundle.organization}_all_extracted_policies.json"
        output_path = bundle.extraction_directory / f"{bundle.organization}_ltl_rules.json"
        return (
            self.python_executable,
            "agent/policy_construction/rule_extractor.py",
            str(policy_path),
            "--output-file",
            str(output_path),
        )

    def extract_ltl(
        self,
        bundle: AutoPolicyBundle,
        *,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: int = 1800,
    ) -> AutoPolicyBundle:
        process_environment = os.environ.copy()
        process_environment.update(dict(environment or {}))
        if not process_environment.get("OPENAI_API_KEY", "").strip():
            raise AutoPolicyExecutionError(
                "固定版本 AutoPolicy 的 LTLRuleExtractor 需要环境变量 OPENAI_API_KEY"
            )
        completed = subprocess.run(
            self.build_ltl_command(bundle),
            cwd=self.checkout,
            env=process_environment,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            tail = "\n".join(completed.stderr.splitlines()[-8:])
            raise AutoPolicyExecutionError(
                f"AutoPolicy LTL 抽取失败（{completed.returncode}）：{tail or '无错误输出'}"
            )
        return load_autopolicy_bundle(
            bundle.extraction_directory,
            upstream_revision=self.revision,
        )


def load_autopolicy_bundle(
    extraction_directory: str | Path,
    *,
    upstream_revision: str | None = None,
) -> AutoPolicyBundle:
    directory = Path(extraction_directory).expanduser().resolve()
    if not directory.is_dir():
        raise AutoPolicyArtifactError(f"AutoPolicy extraction directory not found: {directory}")
    policy_path = _single(directory, "*_all_extracted_policies.json", required=True)
    prefix = policy_path.name.removesuffix("_all_extracted_policies.json")
    rule_path = directory / f"{prefix}_all_extracted_rules.json"
    category_path = directory / f"{prefix}_risk_categories.json"
    mapping_path = directory / f"{prefix}_policy_rule_mapping.json"
    report_path = directory / f"{prefix}_extraction_report.json"
    for path in (rule_path, category_path, mapping_path, report_path):
        if not path.is_file():
            raise AutoPolicyArtifactError(f"缺少 AutoPolicy 输出文件：{path.name}")

    raw_policies = _json_list(policy_path)
    policies = tuple(_policy(item, index) for index, item in enumerate(raw_policies))
    policy_ids = {item.policy_id for item in policies}
    if len(policy_ids) != len(policies):
        raise AutoPolicyArtifactError("AutoPolicy policies contain duplicate policy_id values")

    raw_rules = _json_list(rule_path)
    rules = tuple(_rule(item, index, policy_ids) for index, item in enumerate(raw_rules))
    rule_ids = {item.rule_id for item in rules}
    if len(rule_ids) != len(rules):
        raise AutoPolicyArtifactError("AutoPolicy rules contain duplicate rule_id values")

    raw_categories = _read_json(category_path)
    if isinstance(raw_categories, dict):
        raw_categories = raw_categories.get("risk_categories", [])
    if not isinstance(raw_categories, list) or not all(isinstance(item, dict) for item in raw_categories):
        raise AutoPolicyArtifactError("AutoPolicy risk categories must be a list of objects")

    raw_mapping = _read_json(mapping_path)
    if not isinstance(raw_mapping, dict):
        raise AutoPolicyArtifactError("AutoPolicy policy-rule mapping must be an object")
    mapping: dict[str, tuple[str, ...]] = {}
    for policy_id, values in raw_mapping.items():
        normalized_policy_id = str(policy_id)
        if normalized_policy_id not in policy_ids:
            raise AutoPolicyArtifactError(
                f"Mapping references unknown policy {normalized_policy_id}"
            )
        if not isinstance(values, list):
            raise AutoPolicyArtifactError("Each policy-rule mapping value must be a list")
        normalized = tuple(str(item) for item in values)
        if any(item not in rule_ids for item in normalized):
            raise AutoPolicyArtifactError(f"Mapping for policy {policy_id} references an unknown rule")
        mapping[normalized_policy_id] = normalized
    declared_links = {
        (policy_id, rule.rule_id)
        for rule in rules
        for policy_id in rule.source_policy_ids
    }
    mapped_links = {
        (policy_id, rule_id)
        for policy_id, mapped_rule_ids in mapping.items()
        for rule_id in mapped_rule_ids
    }
    if mapped_links != declared_links:
        missing = sorted(declared_links - mapped_links)
        unexpected = sorted(mapped_links - declared_links)
        raise AutoPolicyArtifactError(
            "Policy-rule mapping disagrees with rule source_policy_idx: "
            f"missing={missing}, unexpected={unexpected}"
        )

    report = _read_json(report_path)
    if not isinstance(report, dict):
        raise AutoPolicyArtifactError("AutoPolicy extraction report must be an object")

    ltl_path = directory / f"{prefix}_ltl_rules.json"
    ltl_rules = tuple(
        _ltl_rule(item, index) for index, item in enumerate(_json_list(ltl_path))
    ) if ltl_path.is_file() else ()

    digest = sha256()
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    revision = upstream_revision or upstream_status("autopolicy").actual_revision
    if revision is None:
        raise AutoPolicyArtifactError("Cannot establish the AutoPolicy upstream revision")
    return AutoPolicyBundle(
        extraction_directory=directory,
        organization=prefix,
        policies=policies,
        rules=rules,
        ltl_rules=ltl_rules,
        risk_categories=tuple(raw_categories),
        policy_rule_mapping=mapping,
        extraction_report=report,
        upstream_revision=revision,
        artifact_digest=digest.hexdigest(),
    )


def render_review_template(bundle: AutoPolicyBundle) -> str:
    """Render a non-executable reviewer handoff without inventing rule bindings."""
    policy_by_id = {item.policy_id: item for item in bundle.policies}
    payload = {
        "review": {
            "status": "REVIEW_REQUIRED",
            "producer": "AutoPolicy",
            "upstream_revision": bundle.upstream_revision,
            "artifact_digest": bundle.artifact_digest,
            "organization": bundle.organization,
            "instructions": (
                "逐条核对来源与语义，并由审核人填写可观察谓词、生命周期、干预和官方 URL；"
                "此文件不能直接作为 AgentShield 运行时规则包。"
            ),
        },
        "natural_language_rule_candidates": [
            {
                "candidate_rule_id": rule.rule_id,
                "description": rule.description,
                "source_policies": [
                    {
                        "policy_id": policy_id,
                        "scope": policy_by_id[policy_id].scope,
                        "policy_description": policy_by_id[policy_id].description,
                        "references": list(policy_by_id[policy_id].references),
                    }
                    for policy_id in rule.source_policy_ids
                ],
                "reviewer_decision": "PENDING",
                "reviewer": "",
                "reviewed_at": "",
                "runtime_binding": {
                    "normalized_concept": "",
                    "lifecycle_stages": [],
                    "applicability": [],
                    "requirements": [],
                    "intervention": "",
                    "official_url": "",
                    "notes": "",
                },
            }
            for rule in bundle.rules
        ],
        "unlinked_ltl_candidates": [
            {
                "predicates": list(rule.predicates),
                "description": rule.description,
                "ltl_formula": rule.formula,
                "rule_type": rule.rule_type,
                "source_link_review": "PENDING",
            }
            for rule in bundle.ltl_rules
        ],
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _policy(payload: object, index: int) -> ExtractedPolicyCandidate:
    if not isinstance(payload, dict):
        raise AutoPolicyArtifactError(f"Policy {index} must be an object")
    policy_id = str(payload.get("policy_id", "")).strip()
    definitions = payload.get("definitions")
    references = payload.get("reference")
    scope = payload.get("scope")
    description = payload.get("policy_description")
    if not policy_id or not isinstance(definitions, list) or not all(isinstance(x, str) for x in definitions):
        raise AutoPolicyArtifactError(f"Policy {index} has invalid id or definitions")
    if not isinstance(references, list) or not references or not all(isinstance(x, str) for x in references):
        raise AutoPolicyArtifactError(f"Policy {policy_id} has no traceable reference")
    if not isinstance(scope, str) or not scope.strip() or not isinstance(description, str) or not description.strip():
        raise AutoPolicyArtifactError(f"Policy {policy_id} has invalid scope or description")
    return ExtractedPolicyCandidate(
        policy_id, tuple(definitions), scope.strip(), description.strip(), tuple(references),
        str(payload.get("source_file", "")),
    )


def _rule(payload: object, index: int, policy_ids: set[str]) -> ExtractedRuleCandidate:
    if not isinstance(payload, dict):
        raise AutoPolicyArtifactError(f"Rule {index} must be an object")
    rule_id = str(payload.get("rule_id", "")).strip()
    description = payload.get("rule_description")
    sources = payload.get("source_policy_idx", payload.get("source_policy_ids", []))
    if isinstance(sources, (int, str)):
        sources = [sources]
    normalized_sources = tuple(str(item) for item in sources) if isinstance(sources, list) else ()
    if not rule_id or not isinstance(description, str) or not description.strip():
        raise AutoPolicyArtifactError(f"Rule {index} has invalid id or description")
    if not normalized_sources or any(item not in policy_ids for item in normalized_sources):
        raise AutoPolicyArtifactError(f"Rule {rule_id} has unknown or missing source policies")
    definitions = payload.get("term_definitions", [])
    if isinstance(definitions, str):
        definitions = [definitions]
    if not isinstance(definitions, list) or not all(isinstance(item, str) for item in definitions):
        raise AutoPolicyArtifactError(f"Rule {rule_id} has invalid term definitions")
    return ExtractedRuleCandidate(
        rule_id,
        description.strip(),
        normalized_sources,
        str(payload.get("scope", "")),
        tuple(definitions),
    )


def _ltl_rule(payload: object, index: int) -> LTLRuleCandidate:
    if not isinstance(payload, dict):
        raise AutoPolicyArtifactError(f"LTL rule {index} must be an object")
    predicates = payload.get("predicates")
    description = payload.get("description")
    formula = payload.get("ltl_formula")
    rule_type = str(payload.get("rule_type", "")).lower()
    if not isinstance(predicates, list) or not predicates or not all(isinstance(item, str) for item in predicates):
        raise AutoPolicyArtifactError(f"LTL rule {index} has invalid predicates")
    if not isinstance(description, str) or not description.strip() or not isinstance(formula, str) or not formula.strip():
        raise AutoPolicyArtifactError(f"LTL rule {index} has invalid description or formula")
    if rule_type not in {"action", "physical"}:
        raise AutoPolicyArtifactError(f"LTL rule {index} has invalid rule_type")
    return LTLRuleCandidate(tuple(predicates), description.strip(), formula.strip(), rule_type)


def _single(directory: Path, pattern: str, *, required: bool) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) == 1:
        return matches[0]
    if not matches and not required:
        return Path()
    raise AutoPolicyArtifactError(f"Expected exactly one {pattern}, found {len(matches)}")


def _json_list(path: Path) -> list[object]:
    value = _read_json(path)
    if not isinstance(value, list):
        raise AutoPolicyArtifactError(f"{path.name} must contain a JSON list")
    return value


def _read_json(path: Path) -> object:
    if path.stat().st_size > 32 * 1024 * 1024:
        raise AutoPolicyArtifactError(f"AutoPolicy artifact is too large: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutoPolicyArtifactError(f"Invalid AutoPolicy JSON: {path.name}") from exc
