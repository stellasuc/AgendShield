# SHIELDAGENT technical analysis and AgentShield boundary

[简体中文](shieldagent_analysis.zh-CN.md)

## Scope and source

This document is based on a complete review of the 25-page local paper `ShieldAgent.pdf`, titled *SHIELDAGENT: Shielding Agents via Verifiable Safety Policy Reasoning* (ICLR 2025 Workshop on Foundation Models in the Wild). AgentShield is an independent engineering extension. It does not use, modify, or claim to reproduce official SHIELDAGENT source code.

## Threat model

SHIELDAGENT protects an autonomous agent whose internal configuration or external environment may be adversarially manipulated. The paper distinguishes agent-based attacks (for example poisoned instructions, memory, knowledge bases, or tools) and environment-based attacks (for example malicious web content). The protected surface is an action trajectory: unsafe behavior may emerge across sequential agent/environment interactions and may cause access-control failures, privacy breaches, financial loss, content-policy violations, hallucination, operational errors, or longer-term harm (Sections 1, 2.1, 4, and Appendix E).

The guardrail receives the current observation and proposed action together with prior interaction history. It is trusted to retrieve and interpret a safety policy model, collect evidence, verify rules, and label the proposed action safe or unsafe. The paper does not claim that the guardrail prevents host compromise, makes policy extraction legally authoritative, or eliminates model and detector error.

## Action-based Safety Policy Model (ASPM)

ASPM is a logical knowledge graph `G_ASPM = (P, R, pi_theta)` (Sections 3.1-3.2):

- `P = {P_a, P_s}` partitions predicates into action and state predicates.
- `R = {R_a, R_p}` partitions constraints into action rules and physical rules.
- `pi_theta` is a probabilistic logic model organized into action-related rule circuits.

The offline construction pipeline extracts structured policies from regulations, organizational policies, or user constraints; translates them into LTL/LTLf-style rules; iteratively improves verifiability; prunes redundancy; clusters rules by action and dependency; and learns soft rule weights from labeled or simulated data. The paper keeps references to source policy material in each extracted policy block.

## Action and state predicates

An **action predicate** represents an action to be executed, such as deleting, publishing, sending, or inviting. A rule that directly constrains an action must include at least one action predicate. A **state predicate** describes an observable environmental or system condition, such as whether data is confidential or whether a user authorized an operation. Each predicate is intended to receive a Boolean value at a time step.

Physical rules encode relationships among state variables without directly constraining an action. They serve as domain knowledge that can make reasoning robust to an incorrectly assigned predicate. Appendix A.2 illustrates an action rule (`confidential AND not authorized -> do not delete`) and a physical classification rule.

## Policy representation

The policy-extraction stage produces self-contained blocks with term definitions, application scope, policy description, and references. The rule-extraction stage represents a rule as `r = [P_r, T_r, phi_r, t_r]`, containing predicates, a natural-language constraint, an LTL representation, and a rule type. The prompts in Appendix H emphasize atomic, observable predicates and source traceability.

Verifiability Refinement corrects inaccurate logical representations, decomposes vague or compound rules, and attempts to make predicates observable. Redundancy Pruning clusters semantically related predicates and merges redundant rules while trying to preserve meaning. The paper permits human expert review after automated refinement.

## Rule circuits and probabilistic inference

Rules with strongly related or semantically similar state predicates are clustered. For each action predicate, SHIELDAGENT unions relevant clusters into an action-specific circuit. At inference time, only the circuit associated with the invoked action is retrieved, reducing work relative to traversing the full policy.

Within a circuit, a Markov Logic Network assigns weighted probability to predicate worlds. SHIELDAGENT compares the probability of the world with the action invoked against the counterfactual world in which it is not invoked. A configurable threshold produces the final binary safety label. Soft rule weights are learned with a guardrail hinge loss so unreliable or differently important rules need not act as identical hard constraints (Sections 3.2.4 and Appendix C.5).

## Shielding plan and operations

After retrieving the current action's rule circuit, SHIELDAGENT retrieves similar successful verification workflows from long-term memory. It uses these examples to generate a step-by-step shielding plan whose operations collect truth values for unassigned state predicates. The plan continues until all relevant predicates are assigned or an early-termination condition is reached. It then generates executable model-checking code, verifies each rule, performs probabilistic circuit inference, and returns a safety label, violated rules, and an explanation (Algorithm 1 and Section 3.3).

The four operation families are:

- **Search** retrieves and enumerates relevant information from interaction history.
- **Binary-Check** assigns a binary label to a query.
- **Detect** invokes moderation tools for risk categories and modalities.
- **Formal Verify** runs model-checking algorithms over the rule representation.

The paper describes supporting multimodal moderation APIs, specialized fine-tuned models for Search and Binary-Check, and formal verification tooling such as Stormpy. AgentShield does not reproduce those trained components or the probabilistic circuit.

## Action-level verification workflow

Algorithm 1 can be summarized as:

```text
current action
  -> extract action predicates
  -> retrieve the action-related rule circuit
  -> retrieve successful shielding workflows
  -> plan Search / Binary-Check / Detect / Formal Verify operations
  -> assign state predicates from observation and history
  -> formally verify relevant rules
  -> probabilistic circuit inference
  -> safe/unsafe label + violated rules + explanation
```

The online experiment integrates this decision as step-by-step post-verification feedback to a web agent so it can adjust subsequent behavior. AgentShield instead targets pre-effect checks for side-effectful boundaries and an explicit intervention/repair loop.

## History and memory usage

SHIELDAGENT **does use history**. Equation (1) gives the guardrail the prior interaction history `H_<i`, current observation, and current action. Search explicitly queries `H_<=i`. Its hybrid memory contains:

1. short-term interaction history, stored incrementally as a KV cache and discarded after the current action sequence is verified; and
2. long-term memory of successful shielding workflows, retrieved as reusable examples and continually updated.

Therefore, “SHIELDAGENT does not use history” is inaccurate. The meaningful AgentShield distinction is not history versus no history; it is an explicit persistent, typed compliance state and data-lineage model that is updated across heterogeneous lifecycle events.

## What AgentShield reuses as design inspiration

AgentShield borrows the following ideas at the architectural level:

- policy-grounded rather than model-memory-only decisions;
- atomic predicates and structured rule evaluation;
- retrieval of only action/event-relevant rules;
- collection of facts required by those rules;
- deterministic or formal verification behind a stable verifier interface;
- explicit violated-rule and source-grounded explanations;
- extensible Search, Binary-Check, Detect, and Formal Verify operation slots.

The local implementation is original code. At runtime it emits a rule-circuit projection for each actual brokered action, assigns TRUE/FALSE/UNKNOWN to atomic predicates, performs deterministic LTL-style verification, and persists an auditable shielding plan. `ShieldAgentStyleVerifier` remains an extensible interface; the project does not claim equivalence with the paper's learned models, ASPM training, Markov Logic Network, or benchmark results.

The current demonstration uses a local WebArena-style Web task agent with Shopping, CMS, Reddit, GitLab, Maps, and SuiteCRM environments. Its page reads and action submissions travel through the independent Capability Broker; SuiteCRM customer records demonstrate GDPR minimization repair. This is an auditable engineering scenario aligned to the paper's environment categories, not a reproduction of WebArena, AWM, or the paper's experiments.

## Capabilities belonging to SHIELDAGENT

The following are paper capabilities and are not claimed by AgentShield:

- automated LLM policy and LTL rule extraction from long documents;
- iterative vagueness-guided rule refinement and semantic redundancy pruning;
- action-based probabilistic circuits and trained soft rule weights;
- Markov Logic Network inference and relative safety probability thresholding;
- fine-tuned Search and Binary-Check guardrail models;
- multimodal moderation and Stormpy-based formal model checking;
- the long-term learned workflow memory described in the paper;
- SHIELDAGENT-BENCH, its data, or its reported performance.

## AgentShield lifecycle-level extension

The intended operational contrast is:

```text
SHIELDAGENT
current action
  -> retrieve action-related rules
  -> reason over relevant state/history
  -> verify current action
  -> allow/block

AgentShield
runtime lifecycle event
  -> update persistent compliance state
  -> track data lineage and obligations
  -> identify affected regulations/rules
  -> perform event-driven verification
  -> allow / block / repair / require approval
  -> continue execution
```

AgentShield extends enforcement to user requests, plans, tool calls and results, external transfers, memory writes, logs, consent updates, approvals, and trust-boundary responses. Data is represented by object identity, classification, purpose, transformations, recipients, and provenance so an aggregate can be non-personal without erasing the classification of its raw source. A variable-to-rule index skips verification when a state diff cannot affect a rule, while side-effectful and trust-boundary events are always checked. Repairs create a new event and data object, record provenance, update state, and pass through verification again before release.

This is an engineering extension of the policy-verification pattern: it records a shielding plan for each actual brokered action, but does not introduce the paper's learned probabilistic inference or training components. It is not a claim of novelty over every history-aware guardrail and not a modification of official SHIELDAGENT code.
