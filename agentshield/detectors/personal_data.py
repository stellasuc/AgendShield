"""Convenience detector for general personal-data signals."""

from __future__ import annotations

from typing import Any

from agentshield.detectors.base import DetectionResult
from agentshield.detectors.composite import CompositePrivacyDetector
from agentshield.detectors.regex import RegexPatternDetector
from agentshield.detectors.structured import StructuredFieldDetector


class PersonalDataDetector:
    name = "personal-data-v1"

    def __init__(self) -> None:
        self._composite = CompositePrivacyDetector((StructuredFieldDetector(), RegexPatternDetector()))

    def detect(self, content: Any, context: dict[str, Any] | None = None) -> DetectionResult:
        return self._composite.detect(content, context)

