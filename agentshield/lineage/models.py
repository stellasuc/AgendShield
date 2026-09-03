from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TransformationType(str, Enum):
    COPY = "COPY"
    FILTER = "FILTER"
    REDACT = "REDACT"
    AGGREGATE = "AGGREGATE"
    SUMMARIZE = "SUMMARIZE"
    SERIALIZE = "SERIALIZE"
    STORE = "STORE"
    TRANSFER = "TRANSFER"


@dataclass(frozen=True, slots=True)
class LineageEdge:
    source_object_id: str
    target_object_id: str
    transformation: TransformationType
    event_id: str
    preserves_personal_data: bool | None
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

