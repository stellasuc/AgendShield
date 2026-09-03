# Security evaluation

[简体中文](security_evaluation.zh-CN.md)

## Reproducible results

Measured locally with Python 3.12.13, deterministic mock backends, loopback HTTP, and SQLite:

| Check | Actual result |
| --- | ---: |
| Full automated suite | 107 passed |
| Focused broker security suite | 20 passed |
| Performance repetitions | 100 (+ 5 warmups) |
| Brokered safe path mean / median / p95 | 14.531114 / 14.449521 / 15.350542 ms |
| Added latency mean / median / p95 | 14.528934 / 14.447604 / 15.347958 ms |

Commands:

```bash
python -m pytest -q
python -m pytest -q tests/test_broker_security.py
python -m evaluation.broker_runtime
```

Machine-readable evidence is stored in [`../evaluation/results/portfolio_validation.json`](../evaluation/results/portfolio_validation.json) and [`../evaluation/results/broker_runtime.json`](../evaluation/results/broker_runtime.json). Timing includes process/loopback dispatch, policy checks, SQLite work, audit, gateway persistence, and a mock email effect. It excludes LLM inference and remote services and is not a production latency claim.

## Security properties exercised

- unknown capabilities are rejected before transaction creation;
- the gateway rejects unauthorized or capability-mismatched dispatch;
- GDPR raw personal rows are repaired to an aggregate and the raw-email count remains zero;
- repaired child transactions and approval-resumed transactions are re-verified;
- PIPL transfer is paused durably and exact-scope approval survives broker restart;
- unsafe memory persistence and response leakage are intercepted before release;
- a completed `effect_id` is replayed after restart without a duplicate mock effect;
- ambiguous in-flight effects enter human review instead of automatic retry;
- audit, CLI timeline, and dashboard projections omit raw payloads;
- the normal brokered Agent surface exposes no raw mock backend handle.

## Interpretation

These tests establish deterministic properties of the reference implementation, not universal security or legal compliance. The detector fixtures are synthetic, backends are local mocks, broker traffic is unauthenticated loopback HTTP, and concurrency/distributed failure semantics are intentionally out of scope. The strongest evidence is the combination of pre-effect enforcement assertions, durable-state inspection, restart tests, and outcome counts—not the number of tests alone.
