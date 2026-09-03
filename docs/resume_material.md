# Resume material

[简体中文](resume_material.zh-CN.md)

## Version A — one line

**AgentShield — Runtime Security & Compliance Harness for LLM Agents:** built a real LangGraph integration with lifecycle enforcement, a separate-process capability broker, object-level state/lineage, and selected GDPR/PIPL technical controls.

## Version B — two bullets

- Built a lifecycle-level security runtime for LangGraph agents that mediates data access, email, memory, and response release through a separate-process capability broker with deterministic policy decisions, repair, approval, and re-verification.
- Designed SQLite-backed compliance state, lineage, scoped approvals, transaction recovery, and `effect_id` replay protection; validated with 117 automated tests, including 20 focused broker-security tests.

## Version C — three technical bullets

- Engineered a typed Python/LangGraph runtime that normalizes agent lifecycle events, detects personal/sensitive data, resolves object-scoped state and lineage, and evaluates curated GDPR/PIPL technical controls with source-linked explanations.
- Built a loopback capability broker and reference-monitor gateway with durable transactions, blocked-parent/reverified-child repair, approval pause/resume across restart, and application-level at-most-once replay for completed effects.
- Delivered three repeatable security demos plus a real-data Streamlit visualizer; measured a 14.5311 ms mean brokered mock path across 100 runs and passed 121 tests (20 broker-security), explicitly scoped as local—not production—evidence.

## Interview-safe wording

Say “selected runtime-enforceable technical controls,” not “GDPR/PIPL compliant.” Say “application-level at-most-once replay for committed effects,” not “exactly once.” Say “separate-process capability reduction,” not “sandbox” or “absolute isolation.”
