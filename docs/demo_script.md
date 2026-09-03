# 2–3 minute demo script

[简体中文](demo_script.zh-CN.md)

## 0:00–0:25 — Problem

“LLM agents no longer only generate text. They retrieve records, send email, write memory, and expose responses. The security decision depends on the data's origin, purpose, transformations, destination, and approval state—not just the current tool name.”

Show the README hero and say: “AgentShield mediates these capabilities before the real effect.”

## 0:25–0:50 — Architecture

“The LangGraph agent receives only a narrow BrokerClient. A separate process owns the registered mock backends. The broker persists a transaction, resolves compliance state and lineage, evaluates selected policy controls, and only an authorized transaction reaches the Effect Gateway.”

Point at the architecture diagram. Add: “This is capability reduction, not an OS sandbox.”

## 0:50–1:40 — GDPR repair

Run:

```bash
./scripts/record_gdpr_demo.sh
```

“The user asks for a customer count, but the agent proposes sending retrieved rows. The runtime detects personal data and the selected GDPR minimization rule returns `REPAIR: AGGREGATE`. AgentShield creates a derived object, re-verifies the child transaction, and sends only `EU customer count: 2`.”

Highlight the real outcomes: “Raw PII messages: zero. Aggregate messages: one. The agent and broker have different PIDs, and the normal agent surface has no raw backend handle.”

## 1:40–2:10 — PIPL approval

Switch the dashboard to PIPL and run the scenario. “Sensitive information proposed for external transfer becomes `WAITING_APPROVAL`; the effect count is still zero. Clicking Approve calls the real broker API, records exact-scope evidence, reconstructs state after restart, and re-verifies before execution.”

Show `Re-verification: PASS` and one executed effect. Mention that Deny leaves the effect unexecuted and that the demo does not claim legal consent outside its synthetic fixture.

## 2:10–2:30 — Restart and idempotency

Run:

```bash
./scripts/record_idempotency_demo.sh
```

“The second request uses the same `effect_id` after Broker restart. It returns `IDEMPOTENT_REPLAY`; the backend execution count remains one. This is effect integrity for committed local effects, not distributed exactly-once delivery.”

## 2:30–2:50 — Evidence and close

“The project currently passes 107 automated tests, including 20 focused Broker security tests. A 100-run local Mock benchmark measured a 14.5311 ms mean Broker path; that is transparent local evidence, not a production latency claim.”

End on the timeline: “The differentiator is the combination of lifecycle enforcement, object-scoped state, lineage, capability mediation, and durable effect safety.”

## Recording helpers

The three scripts use a new temporary database and clean it on exit:

```bash
./scripts/record_gdpr_demo.sh
./scripts/record_pipl_demo.sh
./scripts/record_idempotency_demo.sh
```

If `asciinema` is already installed, record without adding a project dependency:

```bash
asciinema rec -c './scripts/record_gdpr_demo.sh' gdpr-demo.cast
```
