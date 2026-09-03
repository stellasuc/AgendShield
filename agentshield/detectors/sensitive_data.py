"""Generic sensitive classification and regulation-specific candidate mapping."""

from __future__ import annotations

from typing import Any

from agentshield.detectors.base import DetectionResult
from agentshield.detectors.composite import CompositePrivacyDetector


GDPR_SPECIAL_CATEGORY_CANDIDATES = {"health", "biometric"}
PIPL_SENSITIVE_CANDIDATES = {
    "identity_document",
    "financial",
    "health",
    "biometric",
    "precise_location",
    "minor_related",
    "account_credentials",
}


class SensitiveDataDetector:
    name = "sensitive-data-v1"

    def __init__(self) -> None:
        self._detector = CompositePrivacyDetector()

    def detect(self, content: Any, context: dict[str, Any] | None = None) -> DetectionResult:
        return self._detector.detect(content, context)


def regulation_candidate_mappings(result: DetectionResult) -> dict[str, bool]:
    categories = set(result.sensitive_categories)
    return {
        "gdpr_special_category_candidate": bool(categories & GDPR_SPECIAL_CATEGORY_CANDIDATES),
        "pipl_sensitive_candidate": bool(categories & PIPL_SENSITIVE_CANDIDATES),
    }

