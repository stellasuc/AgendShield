"""Level 1 deterministic pattern detector with conservative patterns."""

from __future__ import annotations

import re
from typing import Any, Iterator

from agentshield.detectors.base import DetectionEvidence, DetectionResult, content_hash


EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-])\d{3,4}[\s.-]\d{3,4}(?!\w)")
US_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
CN_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


class RegexPatternDetector:
    name = "regex-pattern-v1"

    def detect(self, content: Any, context: dict[str, Any] | None = None) -> DetectionResult:
        del context
        evidence: list[DetectionEvidence] = []
        for path, text in _walk_strings(content):
            if EMAIL.search(text):
                evidence.append(DetectionEvidence("email", path, self.name, 0.99, "email pattern"))
            if PHONE.search(text):
                evidence.append(DetectionEvidence("phone", path, self.name, 0.88, "phone pattern"))
            if US_SSN.search(text) or CN_ID.search(text):
                evidence.append(
                    DetectionEvidence("government_identifier", path, self.name, 0.97, "identifier pattern")
                )
                evidence.append(
                    DetectionEvidence("identity_document", path, self.name, 0.97, "identity identifier pattern")
                )
            for match in CARD_CANDIDATE.finditer(text):
                digits = re.sub(r"\D", "", match.group())
                if _luhn_valid(digits):
                    evidence.append(
                        DetectionEvidence("financial", path, self.name, 0.96, "Luhn-valid payment-card pattern")
                    )
                    break

        sensitive_categories = {"identity_document", "financial"}
        sensitive = {item.category for item in evidence if item.category in sensitive_categories}
        personal = {item.category for item in evidence if item.category not in sensitive_categories}
        if sensitive:
            personal.add("sensitive_personal_data")
        return DetectionResult(
            contains_personal_data=bool(personal),
            contains_sensitive_personal_data=bool(sensitive),
            categories=tuple(sorted(personal)),
            sensitive_categories=tuple(sorted(sensitive)),
            confidence=max((item.confidence for item in evidence), default=1.0),
            evidence=tuple(evidence),
            detector=self.name,
            detectors=(self.name,),
            content_sha256=content_hash(content),
        )


def _walk_strings(value: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{path}[{index}]")


def _luhn_valid(number: str) -> bool:
    if not 13 <= len(number) <= 19 or len(set(number)) == 1:
        return False
    digits = [int(char) for char in number]
    parity = len(digits) % 2
    total = 0
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0

