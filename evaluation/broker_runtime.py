"""100-run local mock direct-vs-brokered capability microbenchmark."""

from __future__ import annotations

from statistics import mean, median
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from pathlib import Path
from typing import Any

from agentshield.capabilities.models import CapabilityRequest
from agentshield.capabilities.service import BrokerServiceProcess


class DirectMockEmail:
    def __init__(self) -> None:
        self.messages = []

    def send(self, recipient: str, body: Any) -> dict[str, Any]:
        self.messages.append({"recipient": recipient, "body": body})
        return {"status": "sent", "message_id": f"direct-{len(self.messages):03d}"}


def run_evaluation(repetitions: int = 100) -> dict[str, Any]:
    if repetitions != 100:
        raise ValueError("The portfolio microbenchmark is fixed at 100 measured runs")
    direct = DirectMockEmail()
    direct_samples: list[float] = []
    broker_samples: list[float] = []
    components: dict[str, list[float]] = {
        "policy_verification_ms": [],
        "sqlite_persistence_ms": [],
        "idempotency_lookup_ms": [],
        "audit_persistence_ms": [],
    }
    with TemporaryDirectory(prefix="agentshield-broker-benchmark-") as directory:
        service = BrokerServiceProcess(Path(directory) / "runtime.db", regulations=("GDPR",))
        with service as client:
            for index in range(5):
                client.request(_safe_request(f"warmup-{index}", f"EF-WARMUP-{index}"))
            for index in range(repetitions):
                def direct_call():
                    return direct.send("partner@example.test", {"eu_customer_count": 2})

                def broker_call():
                    return client.request(_safe_request(f"bench-{index}", f"EF-BENCH-{index}"))

                if index % 2 == 0:
                    direct_samples.append(_time(direct_call))
                    broker_samples.append(_time(broker_call))
                else:
                    broker_samples.append(_time(broker_call))
                    direct_samples.append(_time(direct_call))
                request_metrics = client.metrics()
                for key in components:
                    components[key].append(float(request_metrics.get(key, 0.0)))
            executed = client.statistics()["email_messages"]

    overhead = [broker - direct for direct, broker in zip(direct_samples, broker_samples)]
    return {
        "mode": "local_loopback_http_sqlite_mock",
        "measured_runs": repetitions,
        "warmup_runs": 5,
        "direct_mock_latency_ms": _summary(direct_samples),
        "brokered_safe_latency_ms": _summary(broker_samples),
        "total_added_latency_ms": _summary(overhead),
        "components_ms": {key: _summary(values) for key, values in components.items()},
        "broker_email_effects_including_warmup": executed,
        "note": "Local mock microbenchmark, not production performance.",
    }


def _safe_request(trajectory_id: str, effect_id: str) -> CapabilityRequest:
    return CapabilityRequest(
        trajectory_id=trajectory_id,
        capability_id="email.send",
        effect_id=effect_id,
        arguments={
            "recipient": "partner@example.test",
            "body": {"eu_customer_count": 2},
            "purpose": "customer_service",
        },
    )


def _time(function) -> float:
    started = perf_counter_ns()
    function()
    return (perf_counter_ns() - started) / 1_000_000


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
    return {
        "mean": round(mean(values), 6),
        "median": round(median(values), 6),
        "p95": round(ordered[p95_index], 6),
    }


def main() -> int:
    import json

    print(json.dumps(run_evaluation(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
