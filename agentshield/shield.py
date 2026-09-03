"""Public facade for regulation selection and protected runtime creation."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Iterable

from agentshield.audit.logger import AuditLogger
from agentshield.detectors.composite import CompositePrivacyDetector
from agentshield.policy.engine import DeterministicPolicyEngine
from agentshield.regulations.compiler import RegulationCompiler
from agentshield.regulations.loader import RegulationLoader
from agentshield.regulations.models import RegulationPackage
from agentshield.runtime.harness import ComplianceHarness
from agentshield.state.models import ComplianceState


class AgentShield:
    """Load regulation packages and wrap a supported agent runtime."""

    def __init__(
        self,
        regulations: Iterable[str],
        *,
        package_root: str | Path | None = None,
        enforcement_mode: str = "enforce",
        verification_strategy: str = "event_driven",
    ) -> None:
        selected = tuple(str(item).upper() for item in regulations)
        if not selected:
            raise ValueError("AgentShield requires at least one regulation")
        if len(set(selected)) != len(selected):
            raise ValueError("Duplicate regulation selections are not allowed")
        root = Path(package_root) if package_root else default_package_root()
        self.loader = RegulationLoader(root)
        self.packages: tuple[RegulationPackage, ...] = tuple(
            self.loader.load(regulation_id) for regulation_id in selected
        )
        self.policy_set = RegulationCompiler().compile(list(self.packages))
        self.detector = CompositePrivacyDetector()
        if enforcement_mode not in {"audit", "enforce"}:
            raise ValueError("enforcement_mode must be 'audit' or 'enforce'")
        self.enforcement_mode = enforcement_mode
        if verification_strategy not in {"event_driven", "every_event"}:
            raise ValueError("verification_strategy must be event_driven or every_event")
        self.verification_strategy = verification_strategy

    @property
    def regulations(self) -> tuple[str, ...]:
        return self.policy_set.regulations

    def create_harness(
        self,
        trajectory_id: str,
        audit_directory: str | Path,
        *,
        max_repair_attempts: int = 2,
        audit_failure_mode: str = "fail_closed",
    ) -> ComplianceHarness:
        state = ComplianceState(trajectory_id=trajectory_id)
        return ComplianceHarness(
            DeterministicPolicyEngine(
                self.policy_set,
                verify_every_event=self.verification_strategy == "every_event",
            ),
            state,
            AuditLogger(audit_directory),
            max_repair_attempts=max_repair_attempts,
            detector=self.detector,
            audit_failure_mode=audit_failure_mode,
        )

    def package(self, regulation_id: str) -> RegulationPackage:
        normalized = regulation_id.upper()
        for package in self.packages:
            if package.metadata.regulation_id == normalized:
                return package
        raise KeyError(f"Regulation {normalized!r} was not selected")

    def wrap(
        self,
        agent: object,
        *,
        adapter: str = "langgraph",
        audit_directory: str | Path = ".agentshield/audit",
    ) -> object:
        if adapter.lower() != "langgraph":
            raise ValueError(f"Unsupported agent adapter: {adapter}")
        from agentshield.adapters.langgraph import SecuredLangGraphAgent

        return SecuredLangGraphAgent(
            self,
            agent,  # type: ignore[arg-type]
            audit_directory=audit_directory,
            enforcement_mode=self.enforcement_mode,
        )


def default_package_root() -> Path:
    candidates = (
        Path(__file__).resolve().parents[1] / "regulations",  # editable/source tree
        Path(sys.prefix) / "regulations",  # wheel data-files installation
    )
    for candidate in candidates:
        if (candidate / "gdpr" / "metadata.yaml").is_file():
            return candidate
    raise FileNotFoundError("Bundled regulation packages could not be located")
