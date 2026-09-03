"""SQLite persistence for transactions, effects, approvals, and broker audit."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from time import perf_counter
from typing import Any, Mapping

from agentshield.effects.models import EffectStatus, EffectTransaction


class SQLiteRuntimeStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.recover_uncertain_executions()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    effect_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    trajectory_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    original_arguments TEXT NOT NULL,
                    effective_arguments TEXT NOT NULL,
                    referenced_data_objects TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    activated_rules TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    repair_parent TEXT,
                    approval_required INTEGER NOT NULL,
                    execution_attempts INTEGER NOT NULL,
                    result_metadata TEXT NOT NULL,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_transactions_effect ON transactions(effect_id);
                CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
                CREATE TABLE IF NOT EXISTS effects (
                    effect_id TEXT PRIMARY KEY,
                    transaction_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    transaction_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    transaction_id TEXT,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id, id);
                """
            )

    def save_transaction(self, transaction: EffectTransaction) -> float:
        started = perf_counter()
        payload = asdict(transaction)
        payload["status"] = transaction.status.value
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO transactions VALUES (
                    :transaction_id, :effect_id, :request_id, :trajectory_id,
                    :capability_id, :original_arguments, :effective_arguments,
                    :referenced_data_objects, :decision, :activated_rules, :status,
                    :created_at, :updated_at, :repair_parent, :approval_required,
                    :execution_attempts, :result_metadata, :error
                )
                ON CONFLICT(transaction_id) DO UPDATE SET
                    effective_arguments=excluded.effective_arguments,
                    referenced_data_objects=excluded.referenced_data_objects,
                    decision=excluded.decision,
                    activated_rules=excluded.activated_rules,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    repair_parent=excluded.repair_parent,
                    approval_required=excluded.approval_required,
                    execution_attempts=excluded.execution_attempts,
                    result_metadata=excluded.result_metadata,
                    error=excluded.error
                """,
                {
                    **payload,
                    "original_arguments": _json(transaction.original_arguments),
                    "effective_arguments": _json(transaction.effective_arguments),
                    "referenced_data_objects": _json(transaction.referenced_data_objects),
                    "activated_rules": _json(transaction.activated_rules),
                    "approval_required": int(transaction.approval_required),
                    "result_metadata": _json(transaction.result_metadata),
                },
            )
        return (perf_counter() - started) * 1000

    def get_transaction(self, transaction_id: str) -> EffectTransaction:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM transactions WHERE transaction_id=?", (transaction_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown transaction: {transaction_id}")
        return _transaction(row)

    def list_transactions(self, *, status: str | None = None) -> tuple[EffectTransaction, ...]:
        query = "SELECT * FROM transactions"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY created_at, transaction_id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(_transaction(row) for row in rows)

    def get_succeeded_effect(self, effect_id: str) -> Mapping[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM effects WHERE effect_id=? AND status='SUCCEEDED'", (effect_id,)
            ).fetchone()
        return dict(row) | {"result_metadata": json.loads(row["result_metadata"])} if row else None

    def save_effect(
        self,
        *,
        effect_id: str,
        transaction_id: str,
        capability_id: str,
        status: str,
        result_metadata: Mapping[str, Any],
        created_at: str,
        updated_at: str,
    ) -> float:
        started = perf_counter()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO effects VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(effect_id) DO UPDATE SET
                    transaction_id=excluded.transaction_id,
                    status=excluded.status,
                    result_metadata=excluded.result_metadata,
                    updated_at=excluded.updated_at
                """,
                (
                    effect_id,
                    transaction_id,
                    capability_id,
                    status,
                    _json(result_metadata),
                    created_at,
                    updated_at,
                ),
            )
        return (perf_counter() - started) * 1000

    def list_effects(self, capability_id: str | None = None) -> tuple[dict[str, Any], ...]:
        query = "SELECT * FROM effects"
        params: tuple[Any, ...] = ()
        if capability_id:
            query += " WHERE capability_id=?"
            params = (capability_id,)
        query += " ORDER BY created_at"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple(dict(row) | {"result_metadata": json.loads(row["result_metadata"])} for row in rows)

    def save_approval(
        self,
        approval_id: str,
        transaction_id: str,
        decision: str,
        scope: Mapping[str, Any],
        created_at: str,
    ) -> float:
        started = perf_counter()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?, ?)",
                (approval_id, transaction_id, decision, _json(scope), created_at),
            )
        return (perf_counter() - started) * 1000

    def list_approvals(self) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM approvals ORDER BY created_at").fetchall()
        return tuple(dict(row) | {"scope": json.loads(row["scope"])} for row in rows)

    def append_audit(
        self,
        run_id: str,
        transaction_id: str | None,
        event_type: str,
        payload: Mapping[str, Any],
        created_at: str,
    ) -> float:
        started = perf_counter()
        safe_payload = _audit_safe(payload)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_events(run_id, transaction_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, transaction_id, event_type, _json(safe_payload), created_at),
            )
        return (perf_counter() - started) * 1000

    def read_audit(self, run_id: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events WHERE run_id=? ORDER BY id", (run_id,)
            ).fetchall()
        return tuple(dict(row) | {"payload": json.loads(row["payload"])} for row in rows)

    def recover_uncertain_executions(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE transactions
                SET status='REQUIRE_HUMAN_REVIEW',
                    error='Broker restarted while effect was EXECUTING; backend outcome is unknown.'
                WHERE status='EXECUTING'
                """
            )
        return cursor.rowcount


def _transaction(row: sqlite3.Row) -> EffectTransaction:
    return EffectTransaction(
        transaction_id=row["transaction_id"],
        effect_id=row["effect_id"],
        request_id=row["request_id"],
        trajectory_id=row["trajectory_id"],
        capability_id=row["capability_id"],
        original_arguments=json.loads(row["original_arguments"]),
        effective_arguments=json.loads(row["effective_arguments"]),
        referenced_data_objects=tuple(json.loads(row["referenced_data_objects"])),
        decision=row["decision"],
        activated_rules=tuple(json.loads(row["activated_rules"])),
        status=EffectStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        repair_parent=row["repair_parent"],
        approval_required=bool(row["approval_required"]),
        execution_attempts=int(row["execution_attempts"]),
        result_metadata=json.loads(row["result_metadata"]),
        error=row["error"],
    )


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _audit_safe(payload: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"arguments", "original_arguments", "effective_arguments", "value", "body", "data"}:
            encoded = _json(value).encode()
            result[f"{key}_fingerprint"] = {
                "sha256": sha256(encoded).hexdigest(),
                "bytes": len(encoded),
            }
        else:
            result[key] = value
    return result
