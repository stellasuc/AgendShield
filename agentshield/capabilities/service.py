"""Loopback-only local HTTP service creating a real agent/broker process boundary."""

from __future__ import annotations

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
from pathlib import Path
from threading import Thread
from typing import Any

from agentshield.capabilities.broker import CapabilityBroker
from agentshield.capabilities.client import BrokerClient
from agentshield.capabilities.models import CapabilityRequest


class BrokerServiceProcess:
    """Test/demo process wrapper. The child alone constructs EffectGateway/backends."""

    def __init__(
        self,
        database: str | Path,
        *,
        regulations: tuple[str, ...] = ("GDPR",),
    ) -> None:
        self.database = str(database)
        self.regulations = regulations
        self.process: multiprocessing.Process | None = None
        self.endpoint: str | None = None

    def start(self) -> BrokerClient:
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        self.process = context.Process(
            target=_serve,
            args=(self.database, self.regulations, child),
            daemon=True,
        )
        self.process.start()
        if not parent.poll(15):
            self.process.terminate()
            raise TimeoutError("Capability Broker did not start")
        message = parent.recv()
        if "error" in message:
            raise RuntimeError(message["error"])
        self.endpoint = message["endpoint"]
        return BrokerClient(self.endpoint)

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=3)
        self.process = None

    def __enter__(self) -> BrokerClient:
        return self.start()

    def __exit__(self, *_args: Any) -> None:
        self.stop()


def _serve(database: str, regulations: tuple[str, ...], pipe) -> None:
    try:
        broker = CapabilityBroker(database, regulations=regulations)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    if self.path == "/health":
                        return self._send(200, {"status": "ok", "pid": multiprocessing.current_process().pid})
                    if self.path == "/stats":
                        return self._send(200, broker.statistics())
                    if self.path == "/metrics":
                        return self._send(200, broker.last_metrics)
                    if self.path == "/transactions":
                        return self._send(
                            200,
                            [_transaction_view(item) for item in broker.store.list_transactions()],
                        )
                    if self.path == "/approvals":
                        return self._send(200, list(broker.store.list_approvals()))
                    if self.path.startswith("/audit/"):
                        run_id = self.path.removeprefix("/audit/")
                        return self._send(200, list(broker.store.read_audit(run_id)))
                    return self._send(404, {"error": "not found"})
                except Exception as exc:
                    return self._send(400, {"error": f"{type(exc).__name__}: {exc}"})

            def do_POST(self):
                try:
                    payload = self._payload()
                    if self.path == "/capabilities":
                        result = broker.handle(CapabilityRequest.from_dict(payload))
                        return self._send(200, result.to_dict())
                    if self.path.startswith("/approve/"):
                        transaction_id = self.path.removeprefix("/approve/")
                        result = broker.approve(transaction_id, scope=payload.get("scope"))
                        return self._send(200, result.to_dict())
                    if self.path.startswith("/deny/"):
                        transaction_id = self.path.removeprefix("/deny/")
                        result = broker.deny(transaction_id, scope=payload.get("scope"))
                        return self._send(200, result.to_dict())
                    if self.path == "/shutdown":
                        self._send(200, {"status": "stopping"})
                        Thread(target=self.server.shutdown, daemon=True).start()
                        return
                    return self._send(404, {"error": "not found"})
                except Exception as exc:
                    return self._send(400, {"error": f"{type(exc).__name__}: {exc}"})

            def _payload(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                return json.loads(self.rfile.read(length) or b"{}")

            def _send(self, status: int, payload: Any):
                encoded = json.dumps(payload, default=str).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        endpoint = f"http://127.0.0.1:{server.server_port}"
        pipe.send({"endpoint": endpoint})
        pipe.close()
        server.serve_forever()
        server.server_close()
    except BaseException as exc:
        pipe.send({"error": f"{type(exc).__name__}: {exc}"})
        pipe.close()


def _transaction_view(transaction) -> dict[str, Any]:
    return {
        "transaction_id": transaction.transaction_id,
        "effect_id": transaction.effect_id,
        "request_id": transaction.request_id,
        "trajectory_id": transaction.trajectory_id,
        "capability_id": transaction.capability_id,
        "referenced_data_objects": list(transaction.referenced_data_objects),
        "decision": transaction.decision,
        "activated_rules": list(transaction.activated_rules),
        "status": transaction.status.value,
        "created_at": transaction.created_at,
        "updated_at": transaction.updated_at,
        "repair_parent": transaction.repair_parent,
        "approval_required": transaction.approval_required,
        "execution_attempts": transaction.execution_attempts,
        "result_metadata": dict(transaction.result_metadata),
        "error": transaction.error,
    }
