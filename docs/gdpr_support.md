# GDPR support

[简体中文](gdpr_support.zh-CN.md)

## Scope

The GDPR package is grounded in the [EUR-Lex official text of Regulation (EU) 2016/679](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679). It implements six selected runtime-assistive controls. “Supported” means the runtime can observe and intervene on a narrow technical pattern; it does not mean complete GDPR compliance.

| Requirement | Source | Runtime interpretation | Detection/state | Intervention |
| --- | --- | --- | --- | --- |
| Lawful-basis evidence | Article 6(1) | Personal-data effects require a trusted `has_lawful_basis` confirmation. Runtime does not select or validate the basis, and does not assume consent is always required. | Object personal-data flag, purpose, event confirmation. | `REQUIRE_APPROVAL` if missing/false/unknown. |
| Purpose limitation | Article 5(1)(b) | A trusted integration declares whether the effect is compatible with the source purpose. | Object/source purpose, lineage, `purpose_compatible`. | `REPLAN` when false; fail closed at selected boundaries when unknown. |
| Data minimization/by default | Articles 5(1)(c), 25(1)-(2) | Raw identified records should be replaced by an aggregate or redacted derivative when a statistics purpose does not need the fields. | Categories, declared purpose, recipient type, transformations, `is_minimized`. | `AGGREGATE`, then reclassify/re-verify; fallback controls include redaction/block. |
| Special-category candidate | Article 9(1)-(2) | `health` or qualifying `biometric` detector output is a candidate, not a legal conclusion; an Article 9 condition must be externally confirmed. | Generic sensitive categories, GDPR candidate flag, condition confirmation. | `REQUIRE_APPROVAL`. |
| Storage limitation | Article 5(1)(e) | Persistent memory/log writes require bounded retention metadata. Runtime does not calculate the legally correct period or exception. | Personal-data flag, persistent-write stage, `retention_bounded`. | `PREVENT_MEMORY_WRITE`. |
| Recipient transparency metadata | Articles 13(1)(e), 14(1)(e) | External disclosure requires recipient metadata and trusted confirmation that applicable recipient transparency has been addressed. | Data origin, recipient, `recipient_disclosed`. | `REQUIRE_APPROVAL`. |

## What is detected

The detector can identify selected names, email addresses, phone numbers, addresses, identifier-like fields, dates of birth, location, account identifiers, health fields, biometrics, and other generic sensitive categories. It cannot decide whether a person is identifiable in every context or whether a category legally falls within an Article 9 definition.

## What is not supported

- complete lawful-basis analysis, legitimate-interest balancing, or consent validity;
- all Article 9 conditions, Member State conditions, criminal-data rules, or child-consent analysis;
- full Articles 13/14 notice generation or exception analysis;
- data-subject rights, DPIA, breach notification, records of processing, processor contracts, or security-program compliance;
- an automated Chapter V international-transfer decision engine;
- calculation of legally correct retention periods.

AgentShield implements selected technical controls derived from regulations. It does not provide legal advice or guarantee legal compliance.
