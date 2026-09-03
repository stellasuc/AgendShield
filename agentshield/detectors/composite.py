"""Merge detector evidence without mutating source content."""

from __future__ import annotations

from typing import Any, Iterable

from agentshield.detectors.base import DetectionEvidence, DetectionResult, Detector, content_hash


class CompositePrivacyDetector:
    name = "composite-privacy-v1"

    def __init__(self, detectors: Iterable[Detector] | None = None) -> None:
        if detectors is None:
            from agentshield.detectors.regex import RegexPatternDetector
            from agentshield.detectors.structured import StructuredFieldDetector

            detectors = (StructuredFieldDetector(), RegexPatternDetector())
        self.detectors = tuple(detectors)
        if not self.detectors:
            raise ValueError("Composite detector needs at least one detector")

    def detect(self, content: Any, context: dict[str, Any] | None = None) -> DetectionResult:
        results = tuple(detector.detect(content, context) for detector in self.detectors)
        categories = {category for result in results for category in result.categories}
        sensitive = {category for result in results for category in result.sensitive_categories}
        evidence: dict[tuple[str, str, str], DetectionEvidence] = {}
        for result in results:
            for item in result.evidence:
                evidence[(item.category, item.path, item.detector)] = item
        contains_sensitive = any(result.contains_sensitive_personal_data for result in results)
        contains_personal = contains_sensitive or any(result.contains_personal_data for result in results)
        return DetectionResult(
            contains_personal_data=contains_personal,
            contains_sensitive_personal_data=contains_sensitive,
            categories=tuple(sorted(categories)),
            sensitive_categories=tuple(sorted(sensitive)),
            confidence=max((item.confidence for item in evidence.values()), default=1.0),
            evidence=tuple(evidence.values()),
            detector=self.name,
            detectors=tuple(result.detector for result in results),
            content_sha256=content_hash(content),
        )

