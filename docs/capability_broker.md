# Capability broker design

[简体中文](capability_broker.zh-CN.md)

## Purpose

`CapabilityBroker` turns an agent action from a direct Python function call into a policy-aware transaction proposal. It owns the capability registry, existing AgentShield verifier, approval manager, SQLite store, and effect gateway. `BrokerClient` contains no backend object or credential.

The implementation is intentionally small enough to inspect in an interview:

- `agentshield/capabilities/models.py` — request/response contracts;
- `agentshield/capabilities/registry.py` — four allowed capabilities;
- `agentshield/capabilities/broker.py` — policy and transaction orchestration;
- `agentshield/capabilities/service.py` — loopback process boundary;
- `agentshield/effects/transactions.py` — transaction creation/transitions;
- `agentshield/effects/gateway.py` — final authorization check and mock effects;
- `agentshield/effects/store.py` — durable SQLite state;
- `agentshield/approval/manager.py` — exact-scope approval.

## Contracts

A request carries:

```python
CapabilityRequest(
    request_id="...",
    trajectory_id="...",
    capability_id="email.send",
    arguments={"recipient": "...", "body": {...}, "purpose": "..."},
    referenced_data_objects=("customer-records-001",),
    effect_id="optional stable caller id",
)
```

A response returns durable identifiers, status/decision, safe result value where applicable, data-object ID, replay flag, disposition, activated rules, and error.

Capabilities are not free-form tool names. The registry currently accepts only `customer.read`, `email.send`, `memory.write`, and `response.release`, with explicit source/sink/persistence/trust-boundary properties.

## End-to-end authorization

```text
client proposal
  -> registry allowlist
  -> completed effect_id lookup
  -> persist CREATED transaction
  -> policy CHECKING
  -> block / pause / repair child / authorize
  -> persist EXECUTING
  -> gateway reloads and validates transaction
  -> mock backend effect
  -> persist effect + SUCCEEDED transaction
  -> payload-minimized audit/response
```

The gateway is deliberately stateful: receiving plausible arguments is insufficient. It requires a durable authorization state tied to the same capability.

## Data-object continuity after restart

Policy checks depend on object classification and lineage. For a paused transaction, SQLite retains referenced object IDs and the original payload. When a new broker process approves it, the broker reconstructs those objects in a fresh per-trajectory adapter session before re-verification.

This is suitable for the deterministic reference fixtures. A production system should persist the full compliance-state/lineage model separately, with schema versioning and retention controls, instead of reconstructing it from transaction arguments.

## Approval is evidence, not override

The expected scope is computed from the persisted proposal:

```json
{
  "data_objects": ["customer-records-001"],
  "purpose": "customer_service",
  "recipient": "partner@example.test",
  "operation": "email.send"
}
```

A mismatch is rejected. A match records approval and provides the corresponding trusted lifecycle evidence; the policy engine still decides. This design prevents a generic `approved=true` flag from bypassing an unrelated rule or later mutation.

## Idempotency

The stable effect ID is either caller supplied or the SHA-256 digest of canonical trajectory/capability/arguments/object references. The `effects.effect_id` primary key is the deduplication point. Successful replay uses stored non-sensitive effect metadata; email/memory payload bodies are never stored in the effects table.

Limits:

- changing semantic inputs changes a derived effect ID;
- caller-supplied IDs require correct caller discipline;
- deduplication is local to one database;
- real providers should also receive a provider-native idempotency key;
- an `EXECUTING` crash is ambiguous, so automated replay is unsafe.

## Operating the reference service

The portfolio demo starts an ephemeral loopback broker automatically:

```bash
agentshield demo gdpr
```

For durable operator interaction, choose a database path:

```bash
agentshield demo pipl --pause-only --db .agentshield/runtime.db
agentshield transactions list --db .agentshield/runtime.db
agentshield approve <transaction_id> --db .agentshield/runtime.db
```

The service endpoints (`/capabilities`, `/approve`, `/deny`, `/transactions`, `/approvals`, `/audit`, `/metrics`, `/stats`, `/health`) are reference APIs without authentication. Do not expose this server beyond a controlled local demo.

## Production hardening path

A production successor would add authenticated Unix-domain sockets or mTLS, per-principal capability grants, request signing/nonces, database encryption and migrations, provider idempotency, leases/fencing, graceful shutdown, durable lineage, tamper-evident remote audit, rate limits, observability, and explicit operator recovery playbooks.

Those are documented extensions, not claims made by the current implementation.
