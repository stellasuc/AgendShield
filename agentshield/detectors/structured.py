"""Level 0 detection using structured field names.

The detector records field paths and category names, never matching values.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from agentshield.detectors.base import DetectionEvidence, DetectionResult, content_hash


PERSONAL_FIELDS: dict[str, tuple[str, ...]] = {
    "name": (
        "name", "full_name", "first_name", "last_name", "customer_name",
        "patient_name", "contact_name",
    ),
    "email": ("email", "email_address", "customer_email", "contact_email"),
    "phone": ("phone", "phone_number", "mobile", "mobile_number", "telephone"),
    "address": ("address", "postal_address", "street_address", "home_address"),
    "government_identifier": (
        "national_id", "government_id", "id_card", "identity_number",
        "passport_number", "social_security_number", "ssn",
    ),
    "date_of_birth": ("date_of_birth", "birth_date", "dob"),
    "location": ("location", "geolocation", "gps", "latitude", "longitude", "coordinates"),
    "account_identifier": ("account_id", "customer_id", "user_id", "member_id", "account_number"),
}

SENSITIVE_FIELDS: dict[str, tuple[str, ...]] = {
    "identity_document": (
        "national_id", "government_id", "id_card", "identity_number",
        "passport_number", "social_security_number", "ssn",
    ),
    "financial": (
        "bank_account", "bank_account_number", "credit_card", "card_number",
        "iban", "financial_account",
    ),
    "health": (
        "health_data", "diagnosis", "medical_record", "medical_history",
        "health_condition", "prescription",
    ),
    "biometric": ("biometric", "fingerprint", "face_template", "iris_scan", "voiceprint"),
    "precise_location": ("gps", "latitude", "longitude", "coordinates", "precise_location"),
    "minor_related": ("minor", "minor_age", "child_age", "under_14", "guardian_id"),
    "account_credentials": (
        "password", "passcode", "pin", "api_key", "access_token", "refresh_token",
        "secret_key", "credential",
    ),
}

REDACTED_VALUES = {"", "[redacted]", "***", "<redacted>", "null", "none"}


class StructuredFieldDetector:
    name = "structured-field-v1"

    def detect(self, content: Any, context: dict[str, Any] | None = None) -> DetectionResult:
        del context
        evidence: list[DetectionEvidence] = []
        for path, key, value in _walk_fields(content):
            if _is_absent_or_redacted(value):
                continue
            normalized = _normalize(key)
            for category, fields in PERSONAL_FIELDS.items():
                if normalized in fields:
                    evidence.append(
                        DetectionEvidence(category, path, self.name, 0.92, f"structured field '{normalized}'")
                    )
            for category, fields in SENSITIVE_FIELDS.items():
                if normalized in fields:
                    evidence.append(
                        DetectionEvidence(category, path, self.name, 0.96, f"sensitive field '{normalized}'")
                    )

        personal = {item.category for item in evidence if item.category in PERSONAL_FIELDS}
        sensitive = {item.category for item in evidence if item.category in SENSITIVE_FIELDS}
        if sensitive:
            personal.add("sensitive_personal_data")
        return DetectionResult(
            contains_personal_data=bool(personal),
            contains_sensitive_personal_data=bool(sensitive),
            categories=tuple(sorted(personal)),
            sensitive_categories=tuple(sorted(sensitive)),
            confidence=max((item.confidence for item in evidence), default=1.0),
            evidence=tuple(_dedupe_evidence(evidence)),
            detector=self.name,
            detectors=(self.name,),
            content_sha256=content_hash(content),
        )


def _normalize(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower())).strip("_")


def _walk_fields(value: Any, path: str = "$") -> Iterator[tuple[str, str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            yield child, str(key), item
            yield from _walk_fields(item, child)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _walk_fields(item, f"{path}[{index}]")


def _is_absent_or_redacted(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in REDACTED_VALUES
    if isinstance(value, (list, tuple, dict)):
        return not value
    return False


def _dedupe_evidence(items: list[DetectionEvidence]) -> list[DetectionEvidence]:
    result: dict[tuple[str, str, str], DetectionEvidence] = {}
    for item in items:
        result[(item.category, item.path, item.detector)] = item
    return list(result.values())

