# Security engineering report

[简体中文](security_report.zh-CN.md)

## Outcome

The current system addresses the strongest bypass in the adapter-only reference application—raw backends coexisting with the agent—through a separate-process capability broker, durable effect transactions, scoped approval, and restart-safe idempotency.

The implementation reuses the existing LangGraph adapter, lineage model, policy engine, GDPR/PIPL packages, repair loop, and response guard. It does not add laws or broaden statutory claims.

## Delivered scope

| Deliverable | Evidence |
| --- | --- |
| Capability broker | fixed four-capability registry and narrow client |
| Brokered email/memory/response | raw mock backends constructed only by broker gateway |
| Durable effect transaction | explicit state machine with repair parent and attempts |
| SQLite persistence | `transactions`, `effects`, `approvals`, `audit_events` |
| Idempotent effects | unique stable `effect_id`; restart replay demo |
| Approval pause/resume | exact object/purpose/recipient/operation scope and re-verification |
| GDPR broker demo | separate PID, no agent backend handle, aggregate 1, raw PII 0 |
| PIPL approval demo | waiting state survives restart; email 0 before and 1 after |
| Idempotency demo | second request after restart replays; count remains 1 |
| Security tests | 20 focused broker tests; 115 full-suite tests passing |
| Performance | 5 warmups + 100 measured runs with component timings |
| Portfolio docs | broker design, architecture, threat model, report, interview guide |

## Demonstrated results

### GDPR capability reduction and repair

Observed demo fields:

```text
separate_process: true
raw_backend_exposed_on_agent_surface: false
email_messages: 1
raw_pii_messages: 0
aggregate_messages: 1
repair_transactions: 1
authorized_repair_children: 1
```

### PIPL durable approval

```text
initial_status: WAITING_APPROVAL
persisted_status_after_restart: WAITING_APPROVAL
email_messages_before_approval: 0
approval_result: SUCCEEDED
approval_disposition: EXECUTED
email_messages_after_approval: 1
approval_records: 1
```

### Restart idempotency

```text
first_request: EXECUTED
retry: IDEMPOTENT_REPLAY
replayed: true
email_messages_after_first: 1
email_messages_after_restart_and_retry: 1
```

## Verification

```bash
.venv/bin/pytest -q tests/test_broker_security.py
# 20 passed

.venv/bin/pytest -q
# 115 passed
```

The security suite covers reject-before-transaction, raw-transfer repair, repair-child re-verification, memory pre-block and retry, response redaction, unauthorized gateway calls, same-process and restart idempotency, durable waiting approval, scope mismatch, re-verification, denial, audit minimization, crash recovery, authorized resume, provenance hydration, API surface, process separation, and CLI minimization.

## Performance

Source: `evaluation/results/broker_runtime.json`.

| Metric | Mean | Median | p95 |
| --- | ---: | ---: | ---: |
| Direct mock | 0.002180 ms | 0.002083 ms | 0.003250 ms |
| Brokered safe effect | 14.531114 ms | 14.449521 ms | 15.350542 ms |
| Added latency | 14.528934 ms | 14.447604 ms | 15.347958 ms |
| Policy verification | 0.393274 ms | 0.381521 ms | 0.477708 ms |
| SQLite transaction persistence | 1.605186 ms | 1.573478 ms | 1.838167 ms |
| Idempotency lookup | 0.155808 ms | 0.150375 ms | 0.193417 ms |
| Audit persistence | 0.748956 ms | 0.729104 ms | 0.897957 ms |

This is local loopback HTTP, SQLite, and mocks. It is useful as an implementation baseline, not a production capacity number. Component timers do not cover the entire request, particularly HTTP/process scheduling and gateway/effect persistence.

## Security interpretation

The brokered architecture materially improves capability containment and recovery semantics for the reference path. The correct claim is:

> The normal brokered agent cannot access the raw mock effect objects through its API, and every registered effect is checked against a durable transaction before gateway dispatch.

The incorrect claim would be:

> The agent is sandboxed or cannot perform any unapproved effect.

That stronger statement would require restricting all OS/network/plugin/file capabilities, authenticating the broker endpoint, protecting the database and process, and proving provider-level semantics.

## Known limitations

- unauthenticated local HTTP reference service;
- no OS sandbox or credential isolation beyond process ownership;
- original arguments persist unencrypted in trusted SQLite state;
- single-host/process-local locking;
- mock backends and no external provider atomicity;
- ambiguous crash outcomes require human review;
- reconstructed rather than fully durable lineage on approval restart;
- partial regulation packages and fallible detectors;
- approval evidence is not legal proof.

These limits are explicit so the project demonstrates security judgment as well as implementation ability.
