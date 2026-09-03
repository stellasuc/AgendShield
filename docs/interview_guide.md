# AgentShield interview guide

[简体中文](interview_guide.zh-CN.md)

## Q1. What problem does AgentShield solve?

Tool-using agents can retrieve sensitive data and then create real effects such as email, memory writes, or released responses. AgentShield turns those capability proposals into policy-checked, stateful, auditable transactions before a protected backend is reachable. Its focus is runtime enforcement across an execution lifecycle, not only content moderation or prompt filtering.

## Q2. Why is action-level verification alone insufficient?

The same `email.send` action can be safe for an aggregate and unsafe for raw customer rows. The decision therefore needs facts accumulated from prior tool results, purpose, provenance, transformations, destination, and authorization. AgentShield materializes those facts as compliance state and lineage instead of expecting each isolated call to carry all trustworthy context.

## Q3. How does this relate to SHIELDAGENT?

AgentShield is an independent engineering project inspired by SHIELDAGENT's policy-based action verification. SHIELDAGENT reasons about current actions with relevant state and interaction history; AgentShield adds an explicit typed state model, object lineage, lifecycle hooks, broker mediation, durable effects, approval, and replay controls. It is not the official implementation and does not claim SHIELDAGENT's learned models, probabilistic circuits, or benchmark results.

## Q4. Why keep persistent compliance state?

Security-relevant facts often appear before the action that needs them. Persistent state lets a later external transfer reuse classification, purpose, recipient, and approval evidence produced earlier in the trajectory. It also makes decisions explainable and supports pause/resume instead of reconstructing context from prose.

## Q5. Why is state scoped to data objects?

A trajectory can contain both raw personal records and a safe aggregate derived from them. One global “contains PII” flag would either over-block the aggregate or under-protect the raw source. Object scope preserves separate classification and obligations while lineage records their relationship.

## Q6. What does data lineage contribute?

Lineage answers where data came from, what transformation occurred, and which object reached a sink. In the GDPR demo it records raw records → aggregate count → external recipient. This supports minimization checks and audit explanations without pretending that transforming one object changes the classification of its source.

## Q7. Why use a Capability Broker?

An in-process guard is bypassable when agent code still owns a raw backend or can call an unwrapped helper. The broker changes possession: the agent normally gets only a typed client, while email, memory, and response backends live in a separate process. This reduces the normal capability surface, although it is not an OS sandbox.

## Q8. Why is an adapter not enough?

The LangGraph adapter is useful for lifecycle normalization and ordinary framework integration, but it cannot establish complete mediation by itself. Its guarantee depends on calls flowing through wrapped tools, while raw Python references may still exist in the same process. The broker reuses the adapter internally and adds a durable authorization boundary in front of broker-owned effects.

## Q9. Can an agent still bypass the Broker?

Yes, if deployment gives it another network, filesystem, subprocess, plugin, callback, or raw backend channel. AgentShield's claim is limited to capabilities routed through the reference broker and to the normal brokered agent surface. Production deployment must combine least privilege, authenticated IPC, OS/container controls, and removal of alternative authorities.

## Q10. Why must a repair be re-verified?

A repair creates a different action and often a different data object. Treating a transformation as automatically safe would make the repair code an implicit policy bypass. AgentShield blocks the unsafe parent, creates a linked child with effective arguments, and verifies the child before execution.

## Q11. Why does approval not execute immediately?

Approval is evidence for an exact object, purpose, recipient, and operation—not a universal allow token. State or arguments may have changed while a transaction was paused, and policy may have other unmet requirements. AgentShield records the decision, returns to `CHECKING`, rebuilds state after restart, and executes only after policy passes.

## Q12. What does `effect_id` solve?

Agent frameworks retry after timeouts, worker failures, or broker restarts, which can duplicate real effects. A stable `effect_id` lets AgentShield recognize a previously committed supported effect and return stored safe metadata. The idempotency record survives because it is stored in SQLite rather than process memory.

## Q13. Is this exactly-once delivery?

No. It is application-level at-most-once replay for completed effects committed to one SQLite store. If the broker crashes after a provider performed an effect but before the local commit, the outcome is ambiguous, so surviving `EXECUTING` transactions move to `REQUIRE_HUMAN_REVIEW` rather than being retried automatically.

## Q14. How are GDPR and PIPL turned into rules?

The project uses manually curated YAML packages with metadata, normalized requirements, deterministic predicates, interventions, tests, and official source links. The runtime loads selected packages and compiles them into an effective policy set indexed by affected facts and lifecycle events. This is reviewable engineering interpretation, not automated legal parsing or complete statutory encoding.

## Q15. Does AgentShield guarantee GDPR or PIPL compliance?

No. It implements selected runtime-enforceable technical controls that can assist a broader compliance program. Legal applicability, valid consent, organizational process, data-subject rights, contracts, and many jurisdiction-specific obligations require human and organizational governance.

## Q16. How do you handle detector false positives or negatives?

Detectors are evidence producers, not legal authorities. High-risk unknowns fail closed or request approval in the reference rules, while source-linked audit makes the input and decision inspectable. Production work would add calibrated detectors, confidence handling, domain evaluation, overrides with governance, and monitoring for drift.

## Q17. Where does the measured overhead come from?

The refreshed 100-run local benchmark measured a 14.5311 ms mean brokered path and 14.5289 ms mean added latency. Instrumented mean components were 0.3933 ms policy verification, 1.6052 ms SQLite transaction persistence, 0.1558 ms idempotency lookup, and 0.7490 ms audit persistence. The remainder includes loopback HTTP/process scheduling and gateway/effect persistence; this deterministic mock result is not a production latency claim.

## Q18. What would you add for production?

I would first add authenticated and authorized IPC, per-principal capability grants, encrypted/migrated storage, secret management, and structured operational recovery. Then I would integrate provider idempotency keys, leases or fencing for concurrency, tamper-evident remote audit, and deployment-level sandboxing. Load, chaos, detector-quality, and policy-change evaluation would follow before expanding regulation coverage.

## Q19. Why not let an LLM decide compliance directly?

An LLM can help interpret context, but a stochastic model should not be the sole authorization boundary for irreversible effects. AgentShield keeps final decisions in explicit predicates, sourced rules, durable state transitions, and gateway invariants that can be regression-tested. Learned classifiers can plug in as evidence providers without silently owning execution authority.

## Q20. What is the largest security assumption?

Complete mediation depends on deployment ensuring that the agent has no alternative authority outside the broker. The broker host, policy packages, capability registry, SQLite integrity, and approval identity are also trusted. If arbitrary agent code has host privileges or can reach raw services directly, process separation alone cannot protect the effect.

## Suggested live walkthrough

Run `agentshield demo gdpr`, open the dashboard, and connect the repair decision to its raw and derived objects. Then show PIPL pause/approve/re-verification and the restart idempotency result. Finish with the gateway invariant, the threat-model boundary, and the fresh test/performance evidence rather than adding more feature claims.
