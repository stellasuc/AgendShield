"""Privacy detector contracts and payload-free evidence models."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class DetectionEvidence:
    category: str
    path: str
    detector: str
    confidence: float
    reason: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Evidence confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class DetectionResult:
    contains_personal_data: bool
    contains_sensitive_personal_data: bool
    categories: tuple[str, ...]
    sensitive_categories: tuple[str, ...]
    confidence: float
    evidence: tuple[DetectionEvidence, ...]
    detector: str
    detectors: tuple[str, ...] = ()
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if self.contains_sensitive_personal_data and not self.contains_personal_data:
            raise ValueError("Sensitive personal data must also be personal data")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Detection confidence must be between 0 and 1")


class Detector(Protocol):
    name: str

    def detect(self, content: Any, context: dict[str, Any] | None = None) -> DetectionResult: ...


def content_hash(content: Any) -> str:
    encoded = json.dumps(content, sort_keys=True, default=str, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def empty_result(detector: str, content: Any) -> DetectionResult:
    return DetectionResult(
        contains_personal_data=False,
        contains_sensitive_personal_data=False,
        categories=(),
        sensitive_categories=(),
        confidence=1.0,
        evidence=(),
        detector=detector,
        detectors=(detector,),
        content_sha256=content_hash(content),
    )

