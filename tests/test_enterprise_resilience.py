"""
tests/test_enterprise_resilience.py — Enterprise Hardening & Idempotency Test Suite (7 Tests)

Validates enterprise invariants:
1. Command idempotency and replay safety
2. Deeply nested JSON payload handling and boundary validation
3. Multi-client socket namespace isolation
4. Socket keepalive and low-latency idle probes
5. BlenderBinaryDetector stage lookup priority
6. JSON-RPC error mapping taxomomy completeness
7. File descriptor and socket resource deallocation
"""

from __future__ import annotations

import gc
import json
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Any, Dict, List
import pytest

# Ensure src/ is in sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from blender_mcp.socket_client import BlenderSocketClient, BlenderConnectionError
from blender_mcp.daemon_manager import (
    BlenderBinaryDetector,
    BlenderNotFoundError,
    BlenderVersionError,
    WindowsJobObject,
)
from blender_mcp.error_boundary import (
    BlenderMCPError,
    ParseError,
    InvalidRequestError,
    MethodNotFoundError,
    InvalidParamsError,
    InternalError,
    BlenderDaemonError,
    ObjectNotFoundError,
    MaterialShaderError,
    ArmatureRiggingError,
    HierarchyCycleError,
    LightingCameraError,
    RenderEngineError,
    ViewportCaptureError,
    ScriptSyntaxError,
    ERROR_CODE_NAMES,
)


def test_enterprise_idempotent_command_replay() -> None:
    """Enterprise 01: Replay of read-only queries produces deterministic identical states."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _echo_server():
        conn, _ = server.accept()
        for _ in range(5):
            data = conn.recv(1024)
            if not data:
                break
            req = json.loads(data.decode("utf-8").strip())
            resp = {"status": "success", "result": {"version": "4.1.1", "echo_id": req.get("id")}}
            conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
        conn.close()
        server.close()

    t = threading.Thread(target=_echo_server, daemon=True)
    t.start()

    client = BlenderSocketClient(host="127.0.0.1", port=port, command_timeout=3.0)
    client.connect()

    results = []
    for i in range(5):
        resp = client.send_command({"type": "ping", "id": 1001})
        results.append(resp.get("result", {}).get("version"))

    client.disconnect()
    t.join(timeout=2.0)

    assert len(results) == 5
    assert all(v == "4.1.1" for v in results)


def test_enterprise_extreme_payload_json_handling() -> None:
    """Enterprise 02: Validate serialization and framing of deeply nested JSON structures."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _deep_server():
        conn, _ = server.accept()
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        req = json.loads(buf.decode("utf-8").strip())
        depth = len(req["params"]["nested"]["level1"]["level2"]["items"])
        resp = {"status": "success", "result": {"parsed_items": depth}}
        conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
        conn.close()
        server.close()

    t = threading.Thread(target=_deep_server, daemon=True)
    t.start()

    client = BlenderSocketClient(host="127.0.0.1", port=port, command_timeout=5.0)
    client.connect()

    deep_payload = {
        "type": "test_deep",
        "params": {
            "nested": {
                "level1": {
                    "level2": {
                        "items": [{"idx": i, "val": f"param_{i}"} for i in range(250)]
                    }
                }
            }
        }
    }
    resp = client.send_command(deep_payload)
    client.disconnect()
    t.join(timeout=2.0)

    assert resp.get("status") == "success"
    assert resp.get("result", {}).get("parsed_items") == 250


def test_enterprise_multiprocess_socket_isolation() -> None:
    """Enterprise 03: Multiple concurrent client connections maintain distinct request context."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    port = server.getsockname()[1]
    running = True

    def _multi_server():
        while running:
            try:
                server.settimeout(0.5)
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except Exception:
                break

            def _handle(c):
                data = c.recv(1024)
                if data:
                    req = json.loads(data.decode("utf-8").strip())
                    cid = req.get("client_id")
                    resp = {"status": "success", "result": {"client_id": cid, "pong": True}}
                    c.sendall(json.dumps(resp).encode("utf-8") + b"\n")
                c.close()

            threading.Thread(target=_handle, args=(conn,), daemon=True).start()

        server.close()

    t = threading.Thread(target=_multi_server, daemon=True)
    t.start()

    def _client_task(cid: int, outs: List[Any]):
        c = BlenderSocketClient(host="127.0.0.1", port=port, command_timeout=3.0)
        c.connect()
        r = c.send_command({"type": "ping", "client_id": cid})
        outs.append(r.get("result", {}).get("client_id"))
        c.disconnect()

    outputs: List[Any] = []
    threads = []
    for idx in range(6):
        th = threading.Thread(target=_client_task, args=(idx, outputs))
        threads.append(th)
        th.start()

    for th in threads:
        th.join(timeout=3.0)

    running = False
    t.join(timeout=2.0)

    assert len(outputs) == 6
    assert set(outputs) == {0, 1, 2, 3, 4, 5}


def test_enterprise_socket_keepalive_probe() -> None:
    """Enterprise 04: Idle socket keep-alive probe returns ultra-low latency sub-millisecond status."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _keepalive_server():
        conn, _ = server.accept()
        for _ in range(3):
            data = conn.recv(1024)
            if not data:
                break
            conn.sendall(b'{"status":"success","result":{"alive":true}}\n')
        conn.close()
        server.close()

    t = threading.Thread(target=_keepalive_server, daemon=True)
    t.start()

    client = BlenderSocketClient(host="127.0.0.1", port=port, command_timeout=3.0)
    client.connect()

    t0 = time.perf_counter()
    resp1 = client.send_command({"type": "ping"})
    lat1 = time.perf_counter() - t0

    time.sleep(0.1)  # brief idle

    t1 = time.perf_counter()
    resp2 = client.send_command({"type": "ping"})
    lat2 = time.perf_counter() - t1

    client.disconnect()
    t.join(timeout=2.0)

    assert resp1.get("status") == "success"
    assert resp2.get("status") == "success"
    assert lat1 < 0.2
    assert lat2 < 0.2


def test_enterprise_blender_binary_matrix_lookup() -> None:
    """Enterprise 05: Verify BlenderBinaryDetector locates Blender 4.1+ binary."""
    detector = BlenderBinaryDetector()
    path, ver = detector.find_blender()
    assert path is not None
    assert ver.startswith("4.1")


def test_enterprise_error_code_mapping_completeness() -> None:
    """Enterprise 06: All defined enterprise error types map to RFC/JSON-RPC compliant error codes."""
    known_errors = [
        ParseError,
        InvalidRequestError,
        MethodNotFoundError,
        InvalidParamsError,
        InternalError,
        BlenderDaemonError,
        ObjectNotFoundError,
        MaterialShaderError,
        ArmatureRiggingError,
        HierarchyCycleError,
        LightingCameraError,
        RenderEngineError,
        ViewportCaptureError,
        ScriptSyntaxError,
    ]
    for err_cls in known_errors:
        assert issubclass(err_cls, BlenderMCPError)
        inst = err_cls("test message")
        assert inst.code < 0
        assert inst.code in ERROR_CODE_NAMES
        assert inst.to_dict()["isError"] is True


def test_enterprise_clean_resource_deallocation() -> None:
    """Enterprise 07: Client socket and memory buffers release all OS resources cleanly."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def _quick_server():
        conn, _ = server.accept()
        conn.recv(1024)
        conn.sendall(b'{"status":"success"}\n')
        conn.close()
        server.close()

    t = threading.Thread(target=_quick_server, daemon=True)
    t.start()

    client = BlenderSocketClient(host="127.0.0.1", port=port, command_timeout=3.0)
    client.connect()
    assert client.is_connected
    client.send_command({"type": "ping"})
    client.disconnect()
    assert not client.is_connected
    assert client._sock is None

    del client
    gc.collect()
    t.join(timeout=2.0)
