# Adapter and capability-broker security

[简体中文](adapter_security.zh-CN.md)

## Brokered security boundary

The LangGraph adapter remains a security-critical lifecycle mapper inside the trusted broker, but it is not the only boundary. The brokered agent receives a `BrokerClient` with only `endpoint` and `timeout`; raw email/memory implementations and the `EffectGateway` are constructed in a separate process.

This removes the most important normal-API bypass from the portfolio demo: retaining a raw backend beside the wrapped agent and calling it directly. It does not make arbitrary local Python code safe.

## Protected brokered paths

- registered `customer.read` requests before data-source execution;
- `email.send` before external mock delivery;
- `memory.write` before persistence;
- `response.release` before returning a value;
- repaired calls through a new, reverified child transaction;
- approved calls through scoped evidence and re-verification;
- successful retries through durable `effect_id` replay;
- ambiguous crash recovery without automatic repeat.

The gateway independently reloads durable state and rejects calls unless the transaction is `EXECUTING` and the capability matches. Thus policy authorization is not represented only by an in-memory Boolean passed from agent code.

## Remaining bypass paths

The complete-mediation claim applies only when all relevant effects are brokered. Remaining out-of-scope bypasses include:

1. Agent code receives another network, shell, filesystem, database, plugin, callback, or memory capability.
2. A trusted broker backend hides a nested side effect not represented by its registered capability.
3. Malicious code obtains the loopback endpoint and submits requests; the reference service has no caller authentication.
4. A principal modifies broker code, regulation packages, risk/governance metadata, or the SQLite database.
5. A principal imports/constructs backend objects within the broker process or compromises that process.
6. A real provider performs an effect but the broker crashes before recording it, leaving an ambiguous `REQUIRE_HUMAN_REVIEW` transaction.
7. Multiple brokers share state without leases, fencing, or provider idempotency coordination.
8. An unwrapped in-process agent is used instead of the brokered reference agent.

Python name privacy (`__email_backend`) is an encapsulation aid, not an adversarial boundary. The actual reduction comes from process separation and the agent not receiving a backend reference or credential.

## Adapter invariants retained

Inside the broker, `LangGraphAdapter` still provides:

- lifecycle normalization and explicit tool-risk metadata;
- allowed-call correlation before tool-result ingestion;
- object-scoped detection and lineage;
- repaired-argument injection and re-verification;
- pre-memory and pre-response checks;
- error and causal audit records;
- per-trajectory compliance sessions.

The broker integration adds two trusted operations: hydrating a referenced object after restart and recording scoped approval/consent evidence. These are not exposed on `BrokerClient` as arbitrary policy-fact injection.

## Retry, repair, and approval

A normal retry is a new request proposal, but its stable `effect_id` is checked before a new side effect. Blocked transactions have no successful effect row and are evaluated again; a completed effect is replayed.

A repair does not mutate the unsafe record into an allowed one. The blocked parent preserves the original decision, while a new child stores minimized effective arguments and executes only after verification.

Approval scope is derived from the paused transaction and requires exact equality. An accepted decision produces lifecycle evidence and returns through `CHECKING`; it never calls the gateway directly.

## Audit and sensitive state

SQLite audit events replace payload-shaped fields with SHA-256 fingerprints plus byte length. `transactions show` applies the same presentation rule to arguments and nested result payloads.

The transaction table itself retains original and effective arguments for durable recovery. Anyone with database read access may therefore access sensitive data. The runtime assumes restrictive filesystem permissions; encryption, database authorization, retention deletion, and key management remain production work.

## Adapter-only mode

`AgentShield.wrap()` supports in-process integration and retains its limitations: direct calls around its registered gateway remain possible. It is useful for compatibility and instrumentation, but the brokered path is the stronger reference architecture for effect mediation.
