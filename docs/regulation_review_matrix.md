# Regulation review matrix

[简体中文](regulation_review_matrix.zh-CN.md)

Reviewed: 2026-08-18. This matrix selects a narrow set of requirements that can be assisted by observable agent-runtime controls. It is not a restatement of either law and is not legal advice.

Primary sources:

- GDPR: [EUR-Lex, Regulation (EU) 2016/679, CELEX 32016R0679](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679)
- PIPL: [National People's Congress legal database](https://flk.npc.gov.cn/detail?fileId=&id=ff8081817b6472a3017b656cc2040044&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E4%B8%AA%E4%BA%BA%E4%BF%A1%E6%81%AF%E4%BF%9D%E6%8A%A4%E6%B3%95&type=) and [official text republished by the Cyberspace Administration of China](https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm)

## Selected controls

| Regulation | Article | Legal requirement summary | Agent risk | Observable runtime state | Enforceable? | Engineering intervention |
| --- | --- | --- | --- | --- | --- | --- |
| GDPR | 6(1) | Processing needs at least one applicable lawful basis. Consent is one basis, not the only basis. | Agent processes personal data without a validated basis. | Personal-data classification; `has_lawful_basis`; purpose. | Partially: Runtime can require a validated basis flag, but cannot decide whether a claimed basis is legally valid. | `REQUIRE_APPROVAL` when basis is absent or unvalidated. |
| GDPR | 5(1)(b) | Personal data must be collected for specified, explicit and legitimate purposes and incompatible further processing is restricted, subject to the Regulation's qualifications. | Data retrieved for support is reused for unrelated marketing or disclosure. | Declared purpose; source purpose; `purpose_compatible`; lineage. | Partially: observable declarations can be compared; legal compatibility requires human/legal context. | `REPLAN` or `BLOCK` when compatibility is explicitly false; approval when unknown at a high-risk boundary. |
| GDPR | 5(1)(c), 25(1)-(2) | Personal data should be adequate, relevant, and limited to what is necessary; by-default measures should limit amount, extent, storage, and accessibility to each purpose. | Agent transfers an entire customer export for a count. | Object fields/categories; declared purpose; transformations; `is_minimized`; recipient type. | Yes for selected technical patterns such as raw rows versus aggregate statistics. | `AGGREGATE`, `REDACT`, then `BLOCK` if repair cannot be verified. |
| GDPR | 9(1)-(2) | Listed special categories are generally prohibited from processing unless an Article 9(2) condition applies. | Agent processes health or biometric data as ordinary personal data. | Generic sensitive categories; GDPR special-category candidate mapping; `special_category_condition_confirmed`. | Partially: detector only produces a candidate; Runtime cannot determine the legal exception. | `REQUIRE_APPROVAL` unless an applicable condition is externally confirmed. |
| GDPR | 5(1)(e) | Identifiable personal data should not be kept longer than necessary for the processing purpose, subject to stated exceptions and safeguards. | Agent writes personal data to indefinite persistent memory. | Memory/log event; retention metadata; purpose; personal-data classification. | Yes for rejecting missing/unbounded retention metadata; not for calculating a legally correct period. | `PREVENT_MEMORY_WRITE` for indefinite/unknown retention at persistent boundaries. |
| GDPR | 13(1)(e), 14(1)(e) | Required information includes recipients or categories of recipients, where applicable. Article 13 applies to data collected from the data subject; Article 14 to data obtained elsewhere, with qualifications. | Agent discloses data to an unrecorded recipient. | Recipient identity/type; `recipient_disclosed`; data origin. | Partially: Runtime can require recipient metadata; it cannot decide every notice exception. | `REQUIRE_APPROVAL` when recipient transparency metadata is absent. |
| PIPL | 13 | A personal information handler may process personal information only under one of the listed circumstances; consent is one circumstance and is not always required where another listed circumstance applies. | Agent processes PI without a recorded processing basis. | PI classification; `has_lawful_basis`; purpose. | Partially: Runtime can require basis metadata, not make the legal determination. | `REQUIRE_APPROVAL`. |
| PIPL | 6 | Processing must have a clear and reasonable purpose, be directly related to it, minimize impact, and collection must stay within the minimum scope necessary for the purpose. | Over-collection or raw disclosure where a count is sufficient. | Purpose; fields/categories; transformations; `purpose_compatible`; `is_minimized`. | Yes for selected purpose/minimization patterns. | `REPLAN`, `AGGREGATE`, `REDACT`, or `BLOCK`. |
| PIPL | 19 | Unless laws or administrative regulations provide otherwise, retention should be the shortest period necessary to achieve the processing purpose. | Agent stores PI indefinitely in persistent memory. | Retention metadata; purpose; memory/log event; PI classification. | Yes for requiring bounded retention metadata; not for calculating the legally correct period. | `PREVENT_MEMORY_WRITE`. |
| PIPL | 23 | Providing PI to another handler requires specified notice to the individual and separate consent; the recipient is constrained by the notified scope. | Agent sends customer data to an external handler without scoped separate consent. | Recipient; purpose; categories; notice flag; object-scoped separate consent; operation. | Yes where the integration identifies the recipient as another handler. | `REQUIRE_CONSENT`; mismatched consent remains invalid. |
| PIPL | 28 | Sensitive PI includes enumerated/high-risk information and may be processed only for a specific purpose, with sufficient necessity and strict protective measures. | Agent treats medical, financial-account, biometric, identity, precise-location, minor, or credential data as ordinary PI. | Generic sensitive categories; PIPL candidate mapping; `specific_purpose`; `strictly_necessary`; `protective_measures_confirmed`. | Partially: classification is a candidate and legal necessity/protection must be confirmed externally. | `REQUIRE_APPROVAL` or `BLOCK`. |
| PIPL | 29 | Processing sensitive PI requires separate consent, subject to provisions requiring written consent. | Agent discloses health information under only general consent. | Sensitive candidate; object/purpose/recipient/operation-scoped separate consent. | Yes for consent evidence matching; Runtime does not decide when written form is additionally required. | `REQUIRE_CONSENT`. |
| PIPL | 38-39 | Cross-border provision requires one of the Article 38 routes/conditions, protective measures, the Article 39 notice, and separate consent. | Agent transfers PI abroad without a confirmed mechanism or scoped consent. | `cross_border`; recipient; notice; mechanism confirmation; separate consent. | Partially: Runtime checks evidence flags but cannot validate an adequacy route, certification, assessment, or contract. | `REQUIRE_APPROVAL` for mechanism; `REQUIRE_CONSENT` for missing scoped separate consent. |

## Considered but not selected for V1

- GDPR Chapter V is not implemented as a standalone cross-border decision engine. The applicable route and safeguards are jurisdiction- and context-dependent; V1 only records transfer metadata through the general recipient control.
- Accuracy, data-subject request workflows, breach notification, DPIAs, automated decision-making, and processor-contract governance are important but exceed the current event/state surface.
- PIPL public disclosure, automated decision-making, government-handler rules, localization thresholds, impact assessments, and individual-right request workflows are deferred.

## Interpretation boundary

Every selected control follows this chain:

```text
official article
  -> curated legal requirement summary
  -> explicit engineering interpretation
  -> observable declarative predicates
  -> bounded technical intervention
```

Detector output is technical evidence only. A `health` or `biometric` category becomes a regulation-specific *candidate*, not an automatic legal conclusion. Claims such as lawful basis, necessity, notice, safeguards, and transfer mechanism must come from trusted policy context or human review.
