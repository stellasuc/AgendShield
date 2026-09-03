# Portfolio audit

[简体中文](portfolio_audit.zh-CN.md)

## Executive verdict

**Ready for a public GitHub portfolio and resume inclusion from a technical-content perspective.** The repository now presents one coherent engineering story: an LLM agent proposes typed capabilities; a separate broker owns protected effects; AgentShield evaluates lifecycle state and lineage; durable authorization precedes execution. The claims are deliberately narrower than a sandbox or legal-compliance guarantee and are backed by runnable demos, tests, persisted evidence, and a local benchmark.

The current workspace copy has no `.git` directory, so `git status` cannot be inspected and publication history is not yet established. Before publishing, initialize or place the files in the intended repository and replace `<your-repository-url>` in the Quick Start. These are release operations, not missing product features.

## Repository evidence

| Area | Audited result |
| --- | --- |
| Automated tests | 115 passed |
| Broker security tests | 20 passed |
| Performance evidence | 100 measured runs + 5 warmups; 14.5311 ms mean brokered mock path |
| CLI | policy, demo, run, audit, timeline, transactions, approvals, approve, deny, dashboard |
| Flagship demos | `gdpr`, `pipl`, `idempotency`; fresh temporary DB by default |
| Agent integration | real LangGraph `StateGraph` using a narrow `BrokerClient` |
| Broker | separate spawned process; loopback HTTP; broker-owned mock backends |
| Persistence | caller-selected SQLite path; temporary by default for demos |
| Visualizer | Streamlit, shared `SecurityTimeline`, real approval API |
| Documentation | English/Chinese architecture, threat model, evaluation, interview, resume, and demo guides |
| License | Apache-2.0 |

The earlier stale performance and test counts were removed. Stage-oriented names and narrative were replaced with capability-oriented, project-wide names. Generated caches, test cache, package metadata, and local databases are ignored; generated copies present during the audit were removed.

## Recruiter review — 30 seconds

The hero explains the product in one sentence and shows Agent → Broker → Runtime → Policy/State/Lineage → Gateway. The first demo gives an immediately legible before/after outcome: zero raw-PII emails and one aggregate email. Concrete commands, screenshots/visualizer, six focused capabilities, and real validation numbers make it credible without asking the reader to study the internals first.

**Verdict:** the problem, value, and proof of implementation are understandable within 30 seconds.

## Agent Security Engineer review

The trust boundary is explicit: agent proposals are untrusted; broker, registry, policies, gateway, and SQLite integrity are trusted. Enforcement occurs before protected effects, and `EffectGateway` reloads durable state rather than trusting a caller-provided authorization flag. Object-scoped state and lineage are used by the runtime; repair creates a linked child and re-verifies; approval returns through `CHECKING`; completed effect IDs replay without duplicate mock execution.

The limitations are correctly exposed: unauthenticated loopback IPC, no host sandbox, plaintext trusted SQLite payloads, reconstructed lineage after restart, process-local serialization, and no distributed/provider-level exactly-once semantics. This makes the broker meaningful without overstating isolation.

**Verdict:** the design demonstrates reference-monitor thinking, lifecycle security, stateful authorization, recovery reasoning, and honest boundary definition.

## Hiring Manager review

The project demonstrates agent-system understanding through real LangGraph execution and tool lifecycle handling. It demonstrates security reasoning through complete-mediation limits, object identity, re-verification, scoped approval, fail-safe crash handling, and data-minimized observability. It demonstrates runtime engineering through process separation, typed protocol, SQLite transactions, restart behavior, CLI, reusable projection API, and interactive UI.

Testing covers both policy behavior and effect outcomes; performance evidence is reproducible and carefully scoped. The interview guide and resume wording make the work discussable without inflated claims.

**Verdict:** strong evidence for Agent Security Engineer, Agent Safety Engineer, LLM Security Engineer, or AI Security Engineer applications.

## Completion gate

- [x] Current suite and broker suite rerun successfully
- [x] Actual benchmark and generated validation JSON refreshed
- [x] GDPR, PIPL, and idempotency demos use real runtime paths
- [x] Dashboard launches with one command and uses actual runtime evidence
- [x] Timeline, state, lineage, decisions, effects, and approval are visualized
- [x] Dashboard approval uses the broker API rather than direct database mutation
- [x] README and key documentation are portfolio-oriented and bilingual
- [x] Architecture, threat model, recording scripts, video script, interview guide, and resume material are ready
- [x] Timeline/dashboard output is payload-safe by default
- [x] Repository artifacts and ignore rules are cleaned

## Remaining technical limitations

1. The reference broker endpoint has no authentication, per-principal authorization, TLS, or multi-tenant isolation.
2. SQLite is single-host sensitive storage, retains recovery arguments without encryption, and does not provide distributed/provider-atomic effect semantics.
3. Regulation coverage and detectors are intentionally partial and fallible; the project cannot determine or guarantee legal compliance.

## Publication checklist

- Initialize or move this workspace into the intended Git repository, review `git status`, and publish with an appropriate commit history.
- Replace the placeholder clone URL with the final public repository URL.
- Keep the current scope; do not add more security mechanisms merely for portfolio breadth.
