# Threat model

[简体中文](threat_model.zh-CN.md)

## Security objective

AgentShield aims to ensure that security-relevant effects exposed through the reference broker are registered, policy-checked, durably authorized, scoped when human approval is required, and auditable before a raw backend is invoked.

It is a reference monitor for brokered capabilities, not a general Python sandbox or a legal-compliance oracle.

## Protected assets

- personal and sensitive personal information in tool results and derived objects;
- external email, persistent memory, and response-release authority;
- approval scope and consent/governance evidence;
- transaction, effect, and policy-decision integrity;
- idempotency state used to prevent duplicate effects;
- payload-minimized audit evidence.

## Principals and boundaries

| Principal/component | Trust posture |
| --- | --- |
| Agent plan, arguments, retrieved/tool content | untrusted |
| `BrokerClient` caller | allowed to propose only; not trusted to authorize |
| Capability registry and risk metadata | trusted deployment input |
| Broker, policy engine, adapter, gateway | trusted computing base |
| Human approver | trusted only for the exact recorded scope |
| SQLite database | sensitive, trusted, access-controlled storage |
| Mock backends | broker-owned effects; results remain untrusted data |
| Regulation packages/detectors | curated inputs with incomplete/possible-error caveats |

## Threats in scope

- an agent requests an unknown or excessive capability;
- raw personal data is proposed for an external transfer where an aggregate suffices;
- sensitive content is proposed for persistent memory;
- personal data leaks through the final response;
- an effect is attempted without an authorized transaction or under the wrong capability;
- a repair is executed without a fresh verification pass;
- stale or unrelated approval is reused for another object, purpose, recipient, or operation;
- an approved proposal changes before execution;
- a retry or broker restart duplicates an already committed effect;
- a crash leaves an in-flight effect with unknown outcome;
- audit or CLI presentation leaks raw payloads;
- malicious instructions in tool output try to influence the policy layer.

## Controls and evidence

| Threat | Control | Regression evidence |
| --- | --- | --- |
| Unknown operation | fixed capability registry | rejected before transaction creation |
| Direct gateway call | persisted status/capability check | unauthorized gateway test |
| Excessive GDPR transfer | lineage-aware minimization repair | raw count 0; aggregate count 1 |
| Unsafe memory | pre-effect policy check | blocked store count remains 0 across retry |
| Response leak | pre-release redaction | released value is redacted |
| Repair bypass | blocked parent + reverified child | parent/child transaction assertions |
| Approval confusion | exact scope equality | wrong-scope approval rejected |
| Approval as bypass | `WAITING_APPROVAL -> CHECKING` | approval audit precedes authorization |
| Duplicate effect | unique durable `effect_id` | replay after restart; count remains 1 |
| Unknown crash outcome | startup recovery state | `EXECUTING -> REQUIRE_HUMAN_REVIEW` |
| Presentation leak | payload fingerprints | raw fixture absent from audit and CLI views |
| In-process raw handle | separate broker + narrow client | different PID and surface inspection |

## Trust assumptions

- the agent uses the broker client for the capabilities claimed protected;
- the broker host, code, registry, database permissions, and policy configuration are trusted;
- no other raw email, database, shell, network, callback, plugin, or memory authority is available to the agent;
- the loopback endpoint is reachable only by intended local principals in the demo environment;
- human approval and broker-supplied governance facts are authentic;
- SQLite is available and its filesystem semantics are correct;
- sequential broker handling is sufficient for this local reference deployment.

## Out of scope

- compromise of the OS, Python interpreter, broker process, policy packages, or database;
- an agent opening arbitrary network/socket/subprocess/file channels outside the broker;
- authentication, authorization tokens, TLS, mTLS, rate limiting, and multi-tenant isolation for the broker endpoint;
- encryption at rest, secret management, signed metadata, tamper-proof audit, and remote attestation;
- atomic exactly-once coordination with a real external provider;
- distributed brokers, replicas, cross-region effects, or parallel workflow commits;
- hidden nested side effects inside a trusted backend implementation;
- complete prompt-injection prevention;
- detector perfection, complete statutory coverage, or legal conclusions.

## Failure posture

Unknown capabilities fail before persistence. Unknown high-risk policy facts block or require approval. Gateway authorization is checked from durable state. Audit failure remains fail-closed by default in the core runtime. An in-flight record observed after restart is escalated for human review instead of retried.

The broker service is deliberately minimal and terminates its child process in the demo wrapper; SQLite commits make completed state durable. Production would require graceful shutdown, authenticated IPC, storage encryption, provider-specific idempotency keys, leases/fencing for concurrency, and operational recovery procedures.

## Compliance statement

AgentShield provides technical controls that can assist a compliance program. Approval records, detector labels, and selected policy rules are evidence used by software—not legal advice, proof of consent, or a guarantee of GDPR/PIPL compliance.
