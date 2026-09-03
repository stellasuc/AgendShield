# PIPL support

[简体中文](pipl_support.zh-CN.md)

## Scope

The package uses the [National People's Congress legal database](https://flk.npc.gov.cn/detail?fileId=&id=ff8081817b6472a3017b656cc2040044&title=%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E4%B8%AA%E4%BA%BA%E4%BF%A1%E6%81%AF%E4%BF%9D%E6%8A%A4%E6%B3%95&type=) and [official text republished by the Cyberspace Administration of China](https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm). Seven selected requirements compile into nine executable controls.

| Requirement | Source | Runtime interpretation | Detection/state | Intervention |
| --- | --- | --- | --- | --- |
| Processing-basis evidence | Article 13 | PI effects require trusted confirmation of a reviewed Article 13 circumstance. Consent is not treated as the only possible circumstance. | PI flag, purpose, `has_lawful_basis`. | `REQUIRE_APPROVAL`. |
| Purpose/minimum necessary | Article 6 | Compare declared/source purpose and replace excessive raw data with a verified derivative. | Purpose compatibility, categories, transformations, `is_minimized`. | `REPLAN`, `AGGREGATE`, redaction, or block. |
| Retention | Article 19 | Persistent PI writes require bounded retention metadata; Runtime cannot calculate the legally shortest period or an exception. | PI flag, memory/log event, `retention_bounded`. | `PREVENT_MEMORY_WRITE`. |
| Provision to another handler | Article 23 | An event explicitly identified as provision to another handler requires notice metadata and separate consent scoped to object, purpose, recipient, and operation. | Recipient type/notice plus scoped consent. | `REQUIRE_CONSENT`. |
| Sensitive PI candidate | Article 28 | Generic supported sensitive categories produce a PIPL candidate; specific purpose, sufficient necessity, and protection claims must be confirmed externally. | Sensitive categories and three confirmation flags. | `REQUIRE_APPROVAL`. |
| Sensitive separate consent | Article 29 | Candidate-sensitive processing requires matching separate consent. Runtime does not decide written-consent requirements. | Object/purpose/recipient/operation consent scope. | `REQUIRE_CONSENT`. |
| Cross-border evidence | Articles 38-39 | Cross-border events require a trusted transfer-mechanism confirmation, notice metadata, and scoped separate consent. Runtime cannot validate the legal route. | `cross_border`, mechanism, recipient notice, scoped consent. | Approval for mechanism; consent for missing separate consent. |

## Regulation-specific mapping

The detector emits generic categories: `identity_document`, `financial`, `health`, `biometric`, `precise_location`, `minor_related`, and `account_credentials`. These become a `pipl_sensitive_candidate` technical flag. The flag does not by itself establish the legal classification or applicability of Article 28.

## What is not supported

- complete interpretation of Article 13 circumstances or consent validity;
- written-consent determinations and all notice exceptions;
- security assessment, certification, standard-contract, threshold, localization, or implementing-rule validation;
- personal information protection impact assessments;
- automated decision-making, public disclosure, government-handler rules, or individual-right request workflows;
- calculation of the legally shortest retention period.

AgentShield implements selected technical controls derived from regulations. It does not provide legal advice or guarantee legal compliance.
