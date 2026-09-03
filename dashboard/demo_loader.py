"""Run isolated portfolio demos and load their real runtime evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from agentshield.capabilities.service import BrokerServiceProcess
from agentshield.observability import SecuritySnapshot, SecurityTimeline
from examples.portfolio.demo import (
    run_gdpr_broker,
    run_idempotency,
    run_pipl_approval,
)


@dataclass(frozen=True, slots=True)
class DemoDefinition:
    key: str
    title: str
    regulation: str
    run_id: str
    user_request: str
    description: str


DEMO_DEFINITIONS = {
    "gdpr": DemoDefinition(
        key="gdpr",
        title="GDPR — Personal Data Exfiltration Prevention",
        regulation="GDPR",
        run_id="gdpr-broker-demo",
        user_request=(
            "Count EU customers and send the statistics to our external partner."
        ),
        description=(
            "Raw customer records are detected, repaired to an aggregate, "
            "re-verified, and sent through the broker."
        ),
    ),
    "pipl": DemoDefinition(
        key="pipl",
        title="PIPL — Sensitive Information Approval",
        regulation="PIPL",
        run_id="pipl-approval-demo",
        user_request=(
            "Send sensitive customer information to the external partner "
            "for customer service."
        ),
        description=(
            "The effect pauses durably and can be approved or denied through "
            "the real broker API."
        ),
    ),
    "idempotency": DemoDefinition(
        key="idempotency",
        title="Agent Retry / Broker Restart Protection",
        regulation="GDPR",
        run_id="idempotency-demo",
        user_request="Send the approved aggregate statistics once.",
        description=(
            "The same logical effect is retried after broker restart and "
            "returns a durable replay instead of executing twice."
        ),
    ),
}


@dataclass(slots=True)
class DemoSession:
    definition: DemoDefinition
    database: Path
    result: dict[str, Any]
    snapshot: SecuritySnapshot
    _temporary_directory: TemporaryDirectory[str] = field(repr=False)

    def refresh(self) -> SecuritySnapshot:
        self.snapshot = SecurityTimeline(self.database).snapshot(
            self.definition.run_id
        )
        return self.snapshot

    def close(self) -> None:
        self._temporary_directory.cleanup()


def run_demo(key: str) -> DemoSession:
    if key not in DEMO_DEFINITIONS:
        raise ValueError(f"Unknown dashboard demo: {key}")
    definition = DEMO_DEFINITIONS[key]
    temporary = TemporaryDirectory(prefix=f"agentshield-{key}-dashboard-")
    database = Path(temporary.name) / "runtime.db"
    try:
        if key == "gdpr":
            result = run_gdpr_broker(database)
        elif key == "pipl":
            result = run_pipl_approval(database, pause_only=True)
        else:
            result = run_idempotency(database)
        snapshot = SecurityTimeline(database).snapshot(definition.run_id)
        return DemoSession(
            definition=definition,
            database=database,
            result=result,
            snapshot=snapshot,
            _temporary_directory=temporary,
        )
    except BaseException:
        temporary.cleanup()
        raise


def resolve_pipl_approval(
    session: DemoSession,
    decision: str,
) -> SecuritySnapshot:
    if session.definition.key != "pipl":
        raise ValueError("Approval controls are available only for the PIPL demo")
    transaction_id = str(session.result["transaction_id"])
    service = BrokerServiceProcess(session.database, regulations=("PIPL",))
    with service as client:
        if decision == "approve":
            response = client.approve(transaction_id)
        elif decision == "deny":
            response = client.deny(transaction_id)
        else:
            raise ValueError("Decision must be approve or deny")
        stats = client.statistics()
    session.result.update(
        {
            "operator_decision": decision.upper(),
            "approval_result": response.status,
            "approval_disposition": response.disposition,
            "email_messages_after_decision": stats["email_messages"],
        }
    )
    return session.refresh()
