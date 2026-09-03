"""Data lineage operations and origin tracing."""

from __future__ import annotations

from copy import deepcopy

from agentshield.lineage.models import LineageEdge, TransformationType
from agentshield.state.models import ComplianceState, DataClassification, DataObject


class DataLineageTracker:
    def __init__(self, state: ComplianceState) -> None:
        self.state = state

    def transform(
        self,
        source_object_id: str,
        target_object_id: str,
        transformation: TransformationType,
        event_id: str,
        *,
        preserves_personal_data: bool | None = None,
        confidence: float = 1.0,
        purpose: str | None = None,
    ) -> DataObject:
        if source_object_id not in self.state.data_objects:
            raise KeyError(f"Unknown lineage source object: {source_object_id}")
        if target_object_id in self.state.data_objects:
            raise ValueError(f"Lineage target already exists: {target_object_id}")
        source = self.state.data_objects[source_object_id]
        if preserves_personal_data is None:
            preserves_personal_data = transformation not in {
                TransformationType.AGGREGATE,
                TransformationType.REDACT,
            }

        target = deepcopy(source)
        target.object_id = target_object_id
        target.source = source_object_id
        target.purpose = purpose or source.purpose
        target.transformations = [*source.transformations, transformation.value]
        target.provenance = [*source.provenance, source_object_id, event_id]
        target.recipients = []
        if preserves_personal_data is False:
            target.classification = DataClassification.NON_PERSONAL
            target.contains_personal_data = False
            target.contains_sensitive_data = False
            target.categories = []
            target.sensitive_categories = []
            target.detection_confidence = None
            target.detectors = []
        edge = LineageEdge(
            source_object_id=source_object_id,
            target_object_id=target_object_id,
            transformation=transformation,
            event_id=event_id,
            preserves_personal_data=preserves_personal_data,
            confidence=confidence,
        )
        self.state.data_objects[target_object_id] = target
        self.state.lineage_edges.append(edge)
        return target

    def trace_origins(self, object_id: str) -> tuple[str, ...]:
        if object_id not in self.state.data_objects:
            raise KeyError(f"Unknown data object: {object_id}")
        parents: dict[str, list[str]] = {}
        for edge in self.state.lineage_edges:
            parents.setdefault(edge.target_object_id, []).append(edge.source_object_id)
        origins: set[str] = set()
        pending = [object_id]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            if current not in parents:
                origins.add(current)
            else:
                pending.extend(parents[current])
        return tuple(sorted(origins))
