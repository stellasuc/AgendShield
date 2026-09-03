"""Local one-to-one LangGraph runtime overhead evaluation."""

from __future__ import annotations

import json
from statistics import mean, median
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from typing import Any

from agentshield.shield import AgentShield
from examples.langgraph_customer_service.agent import build_customer_service_agent
from examples.langgraph_customer_service.demo import REQUEST_EMAIL


SAFE_REQUEST = {"messages": [{"role": "user", "content": "Only count EU customers safely."}]}
UNSAFE_REQUEST = {"messages": [{"role": "user", "content": REQUEST_EMAIL}]}


def run_evaluation(repetitions: int = 100) -> dict[str, Any]:
    if repetitions < 2:
        raise ValueError("repetitions must be at least 2")
    with TemporaryDirectory(prefix="agentshield-lifecycle-") as audit_dir:
        _warmup(audit_dir)
        baseline_safe, shielded_safe, safe_metrics = _measure_pair(
            SAFE_REQUEST, repetitions, audit_dir, "event_driven", "safe"
        )
        baseline_unsafe, shielded_unsafe, unsafe_metrics = _measure_pair(
            UNSAFE_REQUEST, repetitions, audit_dir, "event_driven", "unsafe"
        )
        event_driven, every_event, event_metrics, every_metrics = _measure_strategy_pair(
            SAFE_REQUEST, repetitions, audit_dir
        )

    return {
        "repetitions": repetitions,
        "mode": "deterministic_local_langgraph",
        "llm_calls": 0,
        "safe_task": _comparison(baseline_safe, shielded_safe, safe_metrics),
        "unsafe_task": {
            **_comparison(baseline_unsafe, shielded_unsafe, unsafe_metrics),
            "repair_attempts_total": int(unsafe_metrics["repair_attempts"]),
            "repair_path_overhead_ms_mean": round(
                mean(shielded_unsafe) - mean(baseline_unsafe), 6
            ),
        },
        "event_driven_comparison": {
            "event_driven": {
                "latency_ms": _summary(event_driven),
                "rule_evaluation_latency_ms_total": round(
                    event_metrics.get("rule_evaluation_latency_ms", 0.0), 6
                ),
                **_counter_summary(event_metrics, repetitions),
            },
            "every_event": {
                "latency_ms": _summary(every_event),
                "rule_evaluation_latency_ms_total": round(
                    every_metrics.get("rule_evaluation_latency_ms", 0.0), 6
                ),
                **_counter_summary(every_metrics, repetitions),
            },
            "verification_trigger_reduction": int(
                every_metrics["verification_triggers"] - safe_metrics["verification_triggers"]
            ),
            "rules_evaluated_reduction": int(
                every_metrics["rules_evaluated"] - safe_metrics["rules_evaluated"]
            ),
        },
    }


def _measure_pair(
    request: dict[str, Any],
    repetitions: int,
    audit_dir: str,
    strategy: str,
    label: str,
) -> tuple[list[float], list[float], dict[str, float]]:
    baseline_samples = []
    shielded_samples = []
    totals: dict[str, float] = {}
    for index in range(repetitions):
        baseline_agent = build_customer_service_agent()
        shielded_agent = build_customer_service_agent()
        shield = AgentShield(["GDPR"], verification_strategy=strategy)
        secured = shield.wrap(shielded_agent, audit_directory=audit_dir)

        def baseline_call():
            return baseline_agent.invoke(request)

        def shielded_call():
            return secured.invoke(
                request,
                config={"configurable": {"thread_id": f"{label}-{strategy}-{index}"}},
            )

        if index % 2 == 0:
            baseline_samples.append(_time_call(baseline_call))
            shielded_samples.append(_time_call(shielded_call))
        else:
            shielded_samples.append(_time_call(shielded_call))
            baseline_samples.append(_time_call(baseline_call))
        _add_metrics(totals, secured.last_session.harness.metrics)
    return baseline_samples, shielded_samples, totals


def _measure_strategy_pair(
    request: dict[str, Any], repetitions: int, audit_dir: str
) -> tuple[list[float], list[float], dict[str, float], dict[str, float]]:
    event_samples: list[float] = []
    every_samples: list[float] = []
    event_totals: dict[str, float] = {}
    every_totals: dict[str, float] = {}
    for index in range(repetitions):
        event_agent = build_customer_service_agent()
        every_agent = build_customer_service_agent()
        event_secured = AgentShield(["GDPR"]).wrap(event_agent, audit_directory=audit_dir)
        every_secured = AgentShield(["GDPR"], verification_strategy="every_event").wrap(
            every_agent, audit_directory=audit_dir
        )

        def event_call():
            return event_secured.invoke(
                request, config={"configurable": {"thread_id": f"compare-event-{index}"}}
            )

        def every_call():
            return every_secured.invoke(
                request, config={"configurable": {"thread_id": f"compare-every-{index}"}}
            )

        if index % 2 == 0:
            event_samples.append(_time_call(event_call))
            every_samples.append(_time_call(every_call))
        else:
            every_samples.append(_time_call(every_call))
            event_samples.append(_time_call(event_call))
        _add_metrics(event_totals, event_secured.last_session.harness.metrics)
        _add_metrics(every_totals, every_secured.last_session.harness.metrics)
    return event_samples, every_samples, event_totals, every_totals


def _warmup(audit_dir: str) -> None:
    for index in range(5):
        agent = build_customer_service_agent()
        agent.invoke(SAFE_REQUEST)
        secured = AgentShield(["GDPR"]).wrap(
            build_customer_service_agent(), audit_directory=audit_dir
        )
        secured.invoke(
            SAFE_REQUEST,
            config={"configurable": {"thread_id": f"warmup-{index}"}},
        )


def _time_call(function) -> float:
    started = perf_counter_ns()
    function()
    return (perf_counter_ns() - started) / 1_000_000


def _add_metrics(target: dict[str, float], source: dict[str, float]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0.0) + float(value)


def _comparison(
    baseline: list[float],
    shielded: list[float],
    metrics: dict[str, float],
) -> dict[str, Any]:
    return {
        "baseline_total_latency_ms": _summary(baseline),
        "shielded_total_latency_ms": _summary(shielded),
        "agentshield_overhead_ms": _summary(
            [shielded_value - baseline_value for baseline_value, shielded_value in zip(baseline, shielded)]
        ),
        "components_total_ms": {
            key: round(metrics.get(key, 0.0), 6)
            for key in (
                "detector_latency_ms",
                "state_update_latency_ms",
                "rule_evaluation_latency_ms",
                "audit_latency_ms",
            )
        },
        **_counter_summary(metrics, len(shielded)),
    }


def _counter_summary(metrics: dict[str, float], repetitions: int) -> dict[str, Any]:
    keys = (
        "events",
        "verification_triggers",
        "events_skipped",
        "rules_evaluated",
        "detector_calls",
        "repair_attempts",
    )
    return {
        key: int(metrics.get(key, 0.0)) for key in keys
    } | {
        f"{key}_mean_per_run": round(metrics.get(key, 0.0) / repetitions, 4)
        for key in keys
    }


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(0.95 * len(ordered) + 0.999999) - 1))
    return {
        "mean": round(mean(values), 6),
        "median": round(median(values), 6),
        "p95": round(ordered[index], 6),
    }


def main() -> int:
    results = run_evaluation()
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
