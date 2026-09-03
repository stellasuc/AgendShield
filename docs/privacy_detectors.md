# Privacy detector design

[简体中文](privacy_detectors.zh-CN.md)

## Architecture

```text
raw event content (read-only)
  -> Level 0 structured-field detector
  -> Level 1 conservative regex detector
  -> composite evidence merge
  -> generic personal/sensitive categories
  -> regulation-specific candidate flags
  -> object-scoped ComplianceState
```

The API is `Detector.detect(content, context=None) -> DetectionResult`. Results contain personal and sensitive booleans, generic categories, confidence, payload-free evidence, detector provenance, and a content SHA-256 fingerprint. No paid API or external model is used.

## Supported general categories

- `name`, `email`, `phone`, `address`;
- `government_identifier`, `date_of_birth`, `location`, `account_identifier`;
- `identity_document`, `financial`, `health`, `biometric`;
- `precise_location`, `minor_related`, `account_credentials`.

Structured detection uses explicit field-name mappings. Regex detection covers email, conservative formatted phone patterns, selected government-identifier patterns, and Luhn-valid payment-card candidates. It intentionally does not claim general named-entity recognition.

## Evidence and privacy

Evidence contains category, JSON-like path, detector name, confidence, and pattern/field reason. It does not store the matched value. Raw content is not mutated. Audit events fingerprint raw input/output and redact sensitive metadata rather than persisting payloads.

## Regulation mapping

- GDPR: `health` and qualifying `biometric` signals become `gdpr_special_category_candidate`.
- PIPL: all supported generic sensitive categories become `pipl_sensitive_candidate`.

These are candidates for policy activation, not legal classifications. For example, not every financial field is an Article 9 special category, while PIPL Article 28 has its own sensitive-information definition and risk threshold.

## State and lineage behavior

Every detected payload belongs to one `DataObject`. A COPY preserves source classification when no new content is available. REDACT and AGGREGATE create new object IDs. When derived content is available, the detector runs again and replaces inherited classification; therefore an aggregate is not presumed safe solely because its transformation label is `AGGREGATE`.

## Limitations and failure risks

- Field names can be misleading, localized, abbreviated, or attacker-controlled.
- Regex can miss unconventional formatting and can classify coincidental patterns.
- Name and address detection depends mainly on structured schemas.
- Contextual identifiability, singling out, indirect identifiers, free-form medical language, ethnicity, beliefs, sexuality, and political/trade-union information are not comprehensively detected.
- Redaction safety depends on the repaired content actually removing identifiers; detector pass is not proof of irreversible anonymization.
- Confidence is a deterministic heuristic score, not a calibrated probability.
- Adversarial obfuscation and multimodal content are outside the current detector scope.

The optional model-classifier level remains an extension point for a later phase; it must preserve provenance and should be evaluated before enforcement use.
