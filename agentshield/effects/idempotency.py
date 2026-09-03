"""Application-level idempotency keys for supported brokered effects."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping


def effect_id_for(
    trajectory_id: str,
    capability_id: str,
    arguments: Mapping[str, Any],
    referenced_data_objects: tuple[str, ...],
) -> str:
    logical = {
        "trajectory_id": trajectory_id,
        "capability_id": capability_id,
        "arguments": arguments,
        "referenced_data_objects": sorted(referenced_data_objects),
    }
    encoded = json.dumps(logical, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"EF-{sha256(encoded).hexdigest()[:20]}"
