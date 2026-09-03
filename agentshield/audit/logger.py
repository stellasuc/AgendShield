"""Append-only, payload-minimizing JSONL audit logger."""

from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path

from agentshield.audit.models import AuditEntry


class AuditLogger:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def append(self, entry: AuditEntry) -> AuditEntry:
        payload = asdict(replace(entry, record_hash=""))
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        finalized = replace(entry, record_hash=sha256(canonical.encode()).hexdigest())
        path = self.directory / f"{entry.run_id}.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(finalized), sort_keys=True, default=str) + "\n")
        return finalized

    def read(self, run_id: str) -> tuple[dict[str, object], ...]:
        path = self.directory / f"{run_id}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"No audit log for run {run_id!r}")
        return tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())

    @staticmethod
    def verify(record: dict[str, object]) -> bool:
        expected = record.get("record_hash")
        payload = {**record, "record_hash": ""}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return expected == sha256(canonical.encode()).hexdigest()

