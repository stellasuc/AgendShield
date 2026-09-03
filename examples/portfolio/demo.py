"""Three small, high-signal AgentShield security demos."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agentshield.capabilities.models import CapabilityRequest
from agentshield.capabilities.service import BrokerServiceProcess
from examples.langgraph_customer_service.brokered import build_brokered_customer_service_agent
from examples.web_task_agent.brokered import build_brokered_web_task_agent


GDPR_REQUEST = "Count EU customers and send the statistics to our external partner."


def run_gdpr_broker(
    database: str | Path,
    *,
    prompt: str = GDPR_REQUEST,
    regulations: tuple[str, ...] = ("GDPR",),
) -> dict[str, Any]:
    """Run the brokered customer workflow with the operator's task prompt."""
    service = BrokerServiceProcess(database, regulations=regulations)
    with service as client:
        broker_pid = client.health()["pid"]
        agent = build_brokered_customer_service_agent(client, trajectory_id="gdpr-broker-demo")
        result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
        stats = client.statistics()
        transactions = client.transactions()
        raw_backend_exposed = any(
            hasattr(agent, name)
            for name in ("email", "memory", "gateway", "raw_email_backend", "tool_registry")
        ) or any(
            hasattr(agent.runtime, name)
            for name in ("email", "memory", "gateway", "raw_email_backend", "tool_registry")
        )
        return {
            "demo": "gdpr-broker",
            "task_prompt": prompt,
            "regulations": list(regulations),
            "agent_pid": os.getpid(),
            "broker_pid": broker_pid,
            "separate_process": broker_pid != os.getpid(),
            "raw_backend_exposed_on_agent_surface": raw_backend_exposed,
            "response": result["response"],
            "email_messages": stats["email_messages"],
            "raw_pii_messages": stats["raw_pii_messages"],
            "aggregate_messages": stats["aggregate_messages"],
            "repair_transactions": sum(
                1 for transaction in transactions if transaction["decision"] == "REPAIR"
            ),
            "authorized_repair_children": sum(
                1 for transaction in transactions if transaction.get("repair_parent")
            ),
            "database": str(database),
        }


def run_web_task_broker(
    database: str | Path,
    *,
    prompt: str,
    regulations: tuple[str, ...],
    environment: str,
    task_action: str = "inspect",
    query: str = "",
    max_price: float | None = None,
    quantity: int = 1,
    trajectory_id: str = "web-task-demo",
) -> dict[str, Any]:
    """Run a brokered WebArena-style task agent against a local web fixture."""
    service = BrokerServiceProcess(database, regulations=regulations)
    with service as client:
        broker_pid = client.health()["pid"]
        agent = build_brokered_web_task_agent(client, trajectory_id=trajectory_id)
        result = agent.invoke(
            {
                "messages": [{"role": "user", "content": prompt}],
                "environment": environment,
                "task_action": task_action,
                "query": query,
                "max_price": max_price,
                "quantity": quantity,
            }
        )
        stats = client.statistics()
        transactions = client.transactions()
        return {
            "demo": "web-task-agent",
            "task_prompt": prompt,
            "regulations": list(regulations),
            "environment": environment,
            "agent_pid": os.getpid(),
            "broker_pid": broker_pid,
            "separate_process": broker_pid != os.getpid(),
            "response": result["response"],
            "task_action": result.get("task_action", task_action),
            "query": result.get("query", query),
            "max_price": result.get("max_price", max_price),
            "quantity": result.get("quantity", quantity),
            "tool_trace": result.get("tool_trace", []),
            "environment_state": result.get("environment_state", {}),
            "scope_guard": result.get("scope_guard"),
            "web_actions": stats["web_actions"],
            "raw_pii_messages": stats["raw_pii_messages"],
            "aggregate_messages": stats["aggregate_messages"],
            "repair_transactions": sum(
                1 for transaction in transactions if transaction["decision"] == "REPAIR"
            ),
            "authorized_repair_children": sum(
                1 for transaction in transactions if transaction.get("repair_parent")
            ),
            "database": str(database),
        }


def run_pipl_approval(
    database: str | Path,
    *,
    pause_only: bool = False,
) -> dict[str, Any]:
    trajectory_id = "pipl-approval-demo"
    first_service = BrokerServiceProcess(database, regulations=("PIPL",))
    with first_service as client:
        read = client.request(
            CapabilityRequest(
                trajectory_id=trajectory_id,
                capability_id="customer.read",
                arguments={"dataset": "sensitive"},
            )
        )
        waiting = client.request(
            CapabilityRequest(
                trajectory_id=trajectory_id,
                capability_id="email.send",
                arguments={
                    "recipient": "partner@example.test",
                    "body": read.value,
                    "purpose": "customer_service",
                },
                referenced_data_objects=(read.data_object_id,),
            )
        )
        before = client.statistics()
    if pause_only:
        return {
            "demo": "pipl-approval",
            "transaction_id": waiting.transaction_id,
            "initial_status": waiting.status,
            "email_messages_before_approval": before["email_messages"],
            "next_command": f"agentshield approve {waiting.transaction_id} --db {database}",
            "database": str(database),
        }
    second_service = BrokerServiceProcess(database, regulations=("PIPL",))
    with second_service as restarted:
        persisted = next(
            item
            for item in restarted.transactions()
            if item["transaction_id"] == waiting.transaction_id
        )
        approved = restarted.approve(waiting.transaction_id)
        after = restarted.statistics()
        return {
            "demo": "pipl-approval",
            "transaction_id": waiting.transaction_id,
            "initial_status": waiting.status,
            "persisted_status_after_restart": persisted["status"],
            "email_messages_before_approval": before["email_messages"],
            "approval_result": approved.status,
            "approval_disposition": approved.disposition,
            "email_messages_after_approval": after["email_messages"],
            "approval_records": len(restarted.approvals()),
            "database": str(database),
        }


def run_idempotency(database: str | Path) -> dict[str, Any]:
    request = CapabilityRequest(
        request_id="idempotency-demo-request",
        effect_id="EF-IDEMPOTENCY-DEMO-001",
        trajectory_id="idempotency-demo",
        capability_id="email.send",
        arguments={
            "recipient": "partner@example.test",
            "body": {"eu_customer_count": 2},
            "purpose": "customer_service",
        },
    )
    first_service = BrokerServiceProcess(database, regulations=("GDPR",))
    with first_service as client:
        first = client.request(request)
        first_count = client.statistics()["email_messages"]
    second_service = BrokerServiceProcess(database, regulations=("GDPR",))
    with second_service as restarted:
        retry = restarted.request(request)
        final_count = restarted.statistics()["email_messages"]
        return {
            "demo": "idempotency",
            "first_request": first.disposition,
            "retry": retry.disposition,
            "replayed": retry.replayed,
            "email_messages_after_first": first_count,
            "email_messages_after_restart_and_retry": final_count,
            "effect_id": retry.effect_id,
            "database": str(database),
        }


def render_demo(name: str, database: str | Path, *, pause_only: bool = False) -> str:
    name = {"gdpr": "gdpr-broker", "pipl": "pipl-approval"}.get(name, name)
    function = {
        "gdpr-broker": run_gdpr_broker,
        "pipl-approval": run_pipl_approval,
        "idempotency": run_idempotency,
    }.get(name)
    if function is None:
        raise ValueError(f"Unknown portfolio demo: {name}")
    result = (
        function(database, pause_only=pause_only)
        if name == "pipl-approval"
        else function(database)
    )
    return json.dumps(result, indent=2, sort_keys=True)
