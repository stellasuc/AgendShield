"""Build payload-safe visualizer data from durable AgentShield runtime evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

from agentshield.detectors.composite import CompositePrivacyDetector
from agentshield.effects.models import EffectTransaction
from agentshield.effects.store import SQLiteRuntimeStore
from agentshield.shield import AgentShield


TIMELINE_STATUSES = {
    "INFO",
    "ALLOW",
    "WARNING",
    "BLOCK",
    "REPAIR",
    "APPROVAL",
    "SUCCESS",
}


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    sequence: int
    event_type: str
    status: str
    summary: str
    transaction_id: str | None = None
    effect_id: str | None = None
    capability_id: str | None = None
    decision: str | None = None
    data_object_id: str | None = None
    rule_ids: tuple[str, ...] = ()
    primary_rule_id: str | None = None
    regulation: str | None = None
    source_article: str | None = None
    source_url: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in TIMELINE_STATUSES:
            raise ValueError(f"Unsupported timeline status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DataObjectView:
    object_id: str
    classification: str
    contains_personal_data: bool | None
    contains_sensitive_data: bool | None
    categories: tuple[str, ...] = ()
    sensitive_categories: tuple[str, ...] = ()
    source: str | None = None
    purpose: str | None = None
    recipients: tuple[str, ...] = ()
    transformations: tuple[str, ...] = ()
    content_fingerprint: str | None = None
    safe_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LineageView:
    source: str
    target: str
    transformation: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PolicyDecisionView:
    decision: str
    regulation: str | None = None
    control: str | None = None
    rule_id: str | None = None
    source_article: str | None = None
    source_url: str | None = None
    reason: str | None = None
    intervention: str | None = None
    reverification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SecuritySnapshot:
    run_id: str
    regulations: tuple[str, ...]
    events: tuple[TimelineEvent, ...]
    data_objects: tuple[DataObjectView, ...]
    lineage: tuple[LineageView, ...]
    policy_decision: PolicyDecisionView | None
    transactions: tuple[Mapping[str, Any], ...]
    effects: tuple[Mapping[str, Any], ...]
    approvals: tuple[Mapping[str, Any], ...]
    broker_mediated: bool
    raw_backend_exposed_to_agent: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "regulations": list(self.regulations),
            "events": [event.to_dict() for event in self.events],
            "data_objects": [item.to_dict() for item in self.data_objects],
            "lineage": [edge.to_dict() for edge in self.lineage],
            "policy_decision": (
                self.policy_decision.to_dict() if self.policy_decision else None
            ),
            "transactions": [dict(item) for item in self.transactions],
            "effects": [dict(item) for item in self.effects],
            "approvals": [dict(item) for item in self.approvals],
            "broker_mediated": self.broker_mediated,
            "raw_backend_exposed_to_agent": self.raw_backend_exposed_to_agent,
        }


class SecurityTimeline:
    """Read-only projection shared by the CLI, dashboard, and tests."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        self.store = SQLiteRuntimeStore(self.database)
        self.detector = CompositePrivacyDetector()

    def events(self, run_id: str) -> tuple[TimelineEvent, ...]:
        return self.snapshot(run_id).events

    def snapshot(self, run_id: str) -> SecuritySnapshot:
        transactions = tuple(
            item
            for item in self.store.list_transactions()
            if item.trajectory_id == run_id
        )
        audit = self.store.read_audit(run_id)
        regulations = _regulations(transactions)
        rule_catalog = _rule_catalog(regulations)
        events = _timeline_events(audit, transactions, rule_catalog)
        data_objects, lineage = self._state_and_lineage(transactions, audit)
        transaction_ids = {item.transaction_id for item in transactions}
        effects = tuple(
            _safe_effect(item)
            for item in self.store.list_effects()
            if item["transaction_id"] in transaction_ids
        )
        approvals = tuple(
            _safe_approval(item)
            for item in self.store.list_approvals()
            if item["transaction_id"] in transaction_ids
        )
        return SecuritySnapshot(
            run_id=run_id,
            regulations=regulations,
            events=events,
            data_objects=data_objects,
            lineage=lineage,
            policy_decision=_primary_decision(events, rule_catalog),
            transactions=tuple(_safe_transaction(item) for item in transactions),
            effects=effects,
            approvals=approvals,
            broker_mediated=bool(transactions),
            raw_backend_exposed_to_agent=False,
        )

    def to_json(self, run_id: str) -> str:
        return json.dumps(
            self.snapshot(run_id).to_dict(),
            indent=2,
            sort_keys=True,
            default=str,
        )

    def _state_and_lineage(
        self,
        transactions: tuple[EffectTransaction, ...],
        audit: tuple[dict[str, Any], ...],
    ) -> tuple[tuple[DataObjectView, ...], tuple[LineageView, ...]]:
        observed: dict[str, dict[str, Any]] = {}
        edges: list[LineageView] = []

        for record in audit:
            payload = record["payload"]
            if record["event_type"] == "DATA_OBJECT_OBSERVED":
                object_id = payload.get("data_object_id")
                if object_id:
                    observed[str(object_id)] = {
                        **observed.get(str(object_id), {}),
                        **dict(payload),
                    }
            if record["event_type"] == "DERIVED_OBJECT":
                target = payload.get("data_object_id")
                sources = payload.get("source_data_object_ids") or ()
                transformation = str(payload.get("transformation") or "DERIVE")
                if target:
                    observed.setdefault(
                        str(target),
                        {
                            "data_object_id": str(target),
                            "transformations": [transformation],
                        },
                    )
                    for source in sources:
                        edges.append(
                            LineageView(str(source), str(target), transformation)
                        )

        for transaction in transactions:
            result_object = transaction.result_metadata.get("data_object_id")
            if result_object:
                observed.setdefault(
                    str(result_object),
                    {
                        "data_object_id": str(result_object),
                        "source": transaction.capability_id,
                    },
                )

            payload = _transaction_payload(transaction)
            for object_id in transaction.referenced_data_objects:
                detection = self.detector.detect(payload) if payload is not None else None
                prior = observed.get(object_id, {"data_object_id": object_id})
                recipients = set(prior.get("recipients") or ())
                recipient = transaction.original_arguments.get("recipient")
                if recipient:
                    recipients.add(str(recipient))
                transformations = set(prior.get("transformations") or ())
                if transaction.repair_parent:
                    transformations.add("AGGREGATE")
                candidate = {
                    **prior,
                    "classification": (
                        "SENSITIVE"
                        if detection and detection.contains_sensitive_personal_data
                        else "PERSONAL"
                        if detection and detection.contains_personal_data
                        else "NON_PERSONAL"
                        if detection
                        else prior.get("classification", "UNKNOWN")
                    ),
                    "contains_personal_data": (
                        detection.contains_personal_data
                        if detection
                        else prior.get("contains_personal_data")
                    ),
                    "contains_sensitive_data": (
                        detection.contains_sensitive_personal_data
                        if detection
                        else prior.get("contains_sensitive_data")
                    ),
                    "categories": (
                        list(detection.categories)
                        if detection
                        else list(prior.get("categories") or ())
                    ),
                    "sensitive_categories": (
                        list(detection.sensitive_categories)
                        if detection
                        else list(prior.get("sensitive_categories") or ())
                    ),
                    "purpose": (
                        transaction.original_arguments.get("purpose")
                        or prior.get("purpose")
                    ),
                    "recipients": sorted(recipients),
                    "transformations": sorted(transformations),
                    "content_fingerprint": (
                        detection.content_sha256
                        if detection
                        else prior.get("content_fingerprint")
                    ),
                    "safe_summary": _safe_summary(payload, detection),
                }
                observed[object_id] = _prefer_stronger(prior, candidate)

            if transaction.repair_parent:
                parent = next(
                    (
                        item
                        for item in transactions
                        if item.transaction_id == transaction.repair_parent
                    ),
                    None,
                )
                if parent:
                    for source in parent.referenced_data_objects:
                        for target in transaction.referenced_data_objects:
                            edge = LineageView(source, target, "AGGREGATE")
                            if edge not in edges:
                                edges.append(edge)

            if (
                transaction.capability_id == "email.send"
                and transaction.status.value == "SUCCEEDED"
            ):
                recipient = str(
                    transaction.result_metadata.get("recipient")
                    or transaction.original_arguments.get("recipient")
                    or "external-recipient"
                )
                for source in transaction.referenced_data_objects:
                    edge = LineageView(source, recipient, "EXTERNAL_TRANSFER")
                    if edge not in edges:
                        edges.append(edge)

        views = tuple(
            _data_object_view(item)
            for _, item in sorted(observed.items())
        )
        return views, tuple(edges)


def _timeline_events(
    audit: tuple[dict[str, Any], ...],
    transactions: tuple[EffectTransaction, ...],
    rule_catalog: Mapping[str, Mapping[str, Any]],
) -> tuple[TimelineEvent, ...]:
    by_transaction = {item.transaction_id: item for item in transactions}
    events: list[TimelineEvent] = []
    for sequence, record in enumerate(audit, 1):
        payload = record["payload"]
        transaction = by_transaction.get(record.get("transaction_id"))
        capability = (
            payload.get("capability_id")
            or (transaction.capability_id if transaction else None)
        )
        decision = payload.get("decision")
        rule_ids = tuple(payload.get("activated_rules") or ())
        primary_rule = _select_rule(rule_ids, decision, rule_catalog)
        primary_rule_id = _select_rule_id(rule_ids, decision, rule_catalog)
        status = _event_status(record["event_type"], decision, payload)
        events.append(
            TimelineEvent(
                sequence=sequence,
                event_type=_event_type(record["event_type"], transaction),
                status=status,
                summary=_event_summary(
                    record["event_type"], capability, decision, payload
                ),
                transaction_id=record.get("transaction_id"),
                effect_id=payload.get("effect_id"),
                capability_id=capability,
                decision=decision,
                data_object_id=payload.get("data_object_id"),
                rule_ids=rule_ids,
                primary_rule_id=primary_rule_id,
                regulation=(
                    primary_rule.get("regulation") if primary_rule else None
                ),
                source_article=(
                    primary_rule.get("article") if primary_rule else None
                ),
                source_url=(
                    primary_rule.get("url") if primary_rule else None
                ),
                details=_safe_details(payload),
            )
        )
    return tuple(events)


def _event_type(event_type: str, transaction: EffectTransaction | None) -> str:
    if event_type == "TRANSACTION_CREATED":
        return "CAPABILITY_REQUEST"
    if event_type == "AUTHORIZED":
        if transaction and (
            transaction.repair_parent
            or transaction.result_metadata.get("approval_id")
        ):
            return "RE_VERIFICATION"
        return "POLICY_CHECK"
    if event_type == "EFFECT_SUCCEEDED":
        return "EFFECT_EXECUTION"
    if event_type == "EFFECT_FAILED":
        return "EFFECT_EXECUTION"
    if event_type == "IDEMPOTENT_REPLAY":
        return "EFFECT_REPLAY"
    return event_type


def _event_status(
    event_type: str,
    decision: str | None,
    payload: Mapping[str, Any],
) -> str:
    if event_type in {"EFFECT_SUCCEEDED", "IDEMPOTENT_REPLAY"}:
        return "SUCCESS"
    if event_type in {"EFFECT_FAILED", "APPROVAL_DENIED"}:
        return "BLOCK"
    if event_type == "APPROVAL_RECORDED":
        return "APPROVAL"
    if event_type == "DERIVED_OBJECT" or decision == "REPAIR":
        return "REPAIR"
    if decision in {"REQUIRE_APPROVAL", "REQUIRE_CONSENT"}:
        return "APPROVAL"
    if decision in {"BLOCK", "DENIED"}:
        return "BLOCK"
    if event_type == "DATA_OBJECT_OBSERVED" and payload.get(
        "contains_personal_data"
    ):
        return "WARNING"
    if decision == "ALLOW":
        return "ALLOW"
    return "INFO"


def _event_summary(
    event_type: str,
    capability: str | None,
    decision: str | None,
    payload: Mapping[str, Any],
) -> str:
    capability = capability or "runtime"
    if event_type == "TRANSACTION_CREATED":
        return f"Agent proposed {capability}"
    if event_type == "POLICY_DECISION":
        intervention = payload.get("intervention")
        suffix = f" → {intervention}" if intervention else ""
        return f"Policy decision for {capability}: {decision}{suffix}"
    if event_type == "DERIVED_OBJECT":
        return (
            f"Derived {payload.get('data_object_id', 'data object')} via "
            f"{payload.get('transformation', 'transformation')}"
        )
    if event_type == "DATA_OBJECT_OBSERVED":
        categories = payload.get("categories") or ()
        classification = payload.get("classification") or "UNKNOWN"
        return (
            f"{payload.get('data_object_id', 'Data object')} classified "
            f"{classification}; {len(categories)} categories detected"
        )
    if event_type == "AUTHORIZED":
        return f"Policy verification passed for {capability}"
    if event_type == "APPROVAL_RECORDED":
        return f"Scoped approval recorded for {capability}; re-verification required"
    if event_type == "APPROVAL_DENIED":
        return f"Approval denied for {capability}"
    if event_type == "EFFECT_SUCCEEDED":
        return f"{capability} executed successfully"
    if event_type == "EFFECT_FAILED":
        return f"{capability} execution failed"
    if event_type == "IDEMPOTENT_REPLAY":
        return f"{capability} returned a durable idempotent replay"
    return event_type.replace("_", " ").title()


def _regulations(
    transactions: tuple[EffectTransaction, ...],
) -> tuple[str, ...]:
    values: list[str] = []
    for transaction in transactions:
        for regulation in transaction.result_metadata.get("regulations") or ():
            normalized = str(regulation).upper()
            if normalized not in values:
                values.append(normalized)
    return tuple(values or ("GDPR",))


def _rule_catalog(regulations: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for rule in AgentShield(regulations).policy_set.rules:
        source = rule.sources[0]
        catalog[rule.rule_id] = {
            "regulation": source.regulation,
            "control": rule.normalized_concept.replace("_", " ").title(),
            "article": source.article,
            "url": source.official_url,
            "reason": rule.description,
            "intervention": (
                rule.repair_strategy
                or rule.intervention.value
            ),
        }
    return catalog


def _select_rule(
    rule_ids: tuple[str, ...],
    decision: str | None,
    catalog: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    rule_id = _select_rule_id(rule_ids, decision, catalog)
    return catalog.get(rule_id) if rule_id else None


def _select_rule_id(
    rule_ids: tuple[str, ...],
    decision: str | None,
    catalog: Mapping[str, Mapping[str, Any]],
) -> str | None:
    candidates = [(rule_id, catalog.get(rule_id)) for rule_id in rule_ids]
    candidates = [(rule_id, rule) for rule_id, rule in candidates if rule]
    if not candidates:
        return None
    if decision == "REPAIR":
        for _, rule in candidates:
            if rule.get("intervention") in {"AGGREGATE", "REDACT"}:
                return next(
                    rule_id for rule_id, candidate in candidates if candidate == rule
                )
    if decision in {"REQUIRE_APPROVAL", "REQUIRE_CONSENT"}:
        for rule_id, _ in candidates:
            if rule_id in {
                "PIPL_SENSITIVE_PROCESSING_001",
                "PIPL_SENSITIVE_SEPARATE_CONSENT_001",
            }:
                return rule_id
        for _, rule in candidates:
            if rule.get("intervention") in {
                "REQUIRE_APPROVAL",
                "REQUIRE_CONSENT",
            }:
                return next(
                    rule_id for rule_id, candidate in candidates if candidate == rule
                )
    return candidates[0][0]


def _primary_decision(
    events: tuple[TimelineEvent, ...],
    catalog: Mapping[str, Mapping[str, Any]],
) -> PolicyDecisionView | None:
    meaningful = [
        event
        for event in events
        if event.decision
        in {
            "REPAIR",
            "REQUIRE_APPROVAL",
            "REQUIRE_CONSENT",
            "BLOCK",
            "DENIED",
        }
    ]
    event = meaningful[-1] if meaningful else next(
        (item for item in reversed(events) if item.decision == "ALLOW"),
        None,
    )
    if event is None:
        return None
    rule = _select_rule(event.rule_ids, event.decision, catalog) or {}
    rule_id = event.primary_rule_id or (
        event.rule_ids[0] if event.rule_ids else None
    )
    reverified = any(
        item.event_type == "RE_VERIFICATION"
        and item.sequence > event.sequence
        for item in events
    )
    return PolicyDecisionView(
        decision=event.decision or "ALLOW",
        regulation=rule.get("regulation") or event.regulation,
        control=rule.get("control"),
        rule_id=rule_id,
        source_article=rule.get("article") or event.source_article,
        source_url=rule.get("url") or event.source_url,
        reason=rule.get("reason") or event.summary,
        intervention=(
            event.details.get("intervention")
            or rule.get("intervention")
        ),
        reverification="PASS" if reverified else None,
    )


def _transaction_payload(transaction: EffectTransaction) -> Any:
    arguments = (
        transaction.effective_arguments
        if transaction.repair_parent
        else transaction.original_arguments
    )
    for field in ("body", "data", "response"):
        if field in arguments:
            return arguments[field]
    return None


def _prefer_stronger(
    prior: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    rank = {"UNKNOWN": 0, "NON_PERSONAL": 1, "PERSONAL": 2, "SENSITIVE": 3}
    prior_class = str(prior.get("classification") or "UNKNOWN")
    candidate_class = str(candidate.get("classification") or "UNKNOWN")
    if rank.get(prior_class, 0) > rank.get(candidate_class, 0):
        merged = dict(candidate)
        merged.update(
            {
                "classification": prior_class,
                "contains_personal_data": prior.get("contains_personal_data"),
                "contains_sensitive_data": prior.get("contains_sensitive_data"),
                "categories": prior.get("categories") or (),
                "sensitive_categories": prior.get("sensitive_categories") or (),
                "content_fingerprint": prior.get("content_fingerprint"),
            }
        )
        return merged
    return dict(candidate)


def _data_object_view(payload: Mapping[str, Any]) -> DataObjectView:
    return DataObjectView(
        object_id=str(payload.get("data_object_id")),
        classification=str(payload.get("classification") or "UNKNOWN"),
        contains_personal_data=payload.get("contains_personal_data"),
        contains_sensitive_data=payload.get("contains_sensitive_data"),
        categories=tuple(payload.get("categories") or ()),
        sensitive_categories=tuple(payload.get("sensitive_categories") or ()),
        source=payload.get("source"),
        purpose=payload.get("purpose"),
        recipients=tuple(payload.get("recipients") or ()),
        transformations=tuple(payload.get("transformations") or ()),
        content_fingerprint=payload.get("content_fingerprint"),
        safe_summary=payload.get("safe_summary"),
    )


def _safe_summary(payload: Any, detection: Any) -> str | None:
    if detection is None or detection.contains_personal_data:
        return None
    if isinstance(payload, Mapping) and set(payload) == {"eu_customer_count"}:
        return f"EU customer count: {int(payload['eu_customer_count'])}"
    return None


def _safe_transaction(transaction: EffectTransaction) -> dict[str, Any]:
    return {
        "transaction_id": transaction.transaction_id,
        "effect_id": transaction.effect_id,
        "capability_id": transaction.capability_id,
        "decision": transaction.decision,
        "status": transaction.status.value,
        "referenced_data_objects": list(transaction.referenced_data_objects),
        "activated_rules": list(transaction.activated_rules),
        "repair_parent": transaction.repair_parent,
        "approval_required": transaction.approval_required,
        "execution_attempts": transaction.execution_attempts,
        "created_at": transaction.created_at,
        "updated_at": transaction.updated_at,
    }


def _safe_effect(effect: Mapping[str, Any]) -> dict[str, Any]:
    metadata = effect["result_metadata"]
    allowed = {
        "status",
        "message_id",
        "index",
        "recipient",
        "raw_pii",
        "aggregate",
        "body_fingerprint",
        "data_fingerprint",
        "response_fingerprint",
    }
    return {
        "effect_id": effect["effect_id"],
        "transaction_id": effect["transaction_id"],
        "capability_id": effect["capability_id"],
        "status": effect["status"],
        "result_metadata": {
            key: value for key, value in metadata.items() if key in allowed
        },
    }


def _safe_approval(approval: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "approval_id": approval["approval_id"],
        "transaction_id": approval["transaction_id"],
        "decision": approval["decision"],
        "scope": dict(approval["scope"]),
        "created_at": approval["created_at"],
    }


def _safe_details(payload: Mapping[str, Any]) -> dict[str, Any]:
    hidden = {
        "arguments",
        "original_arguments",
        "effective_arguments",
        "value",
        "body",
        "data",
        "response",
    }
    return {
        str(key): value
        for key, value in payload.items()
        if key not in hidden
    }
