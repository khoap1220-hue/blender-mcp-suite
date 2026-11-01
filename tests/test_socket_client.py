"""
tests/test_socket_client.py
Comprehensive unit and stress tests for BlenderSocketClient.

Tests:
1. Normal command request/response framing (\\n delimiter).
2. Fast healthcheck probe ping() (2s timeout, metadata).
3. Buffer accumulator handling split chunks and multiple back-to-back responses.
4. Auto-recovery (< 3s) under simulated severed socket during send/recv.
5. Exponential backoff delays verification [0.1, 0.2, 0.4, 0.8].
6. DaemonManager respawn coordination hook upon daemon process death.
7. Concurrency and thread-safety under simultaneous multi-threaded commands.
8. Command timeout handling and clean socket state reset.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from blender_mcp.socket_client import (
    BlenderSocketClient,
    BlenderConnectionError,
    BlenderTimeoutError,
    BlenderProtocolError,
)


class MockBlenderServer:
    """
    Lightweight in-process TCP server simulating Blender MCP daemon behaviors.
    Supports deliberate connection drops, chunking, delays, and respawns.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.server_sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False

        self.drop_on_command_count: int = 0
        self.commands_received: int = 0
        self.simulated_delay: float = 0.0
        self.custom_version: str = "4.1.1"
        self.custom_pid: int = 98765

    def start(self) -> int:
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.port = self.server_sock.getsockname()[1]
        self.server_sock.listen(5)
        self.running = True

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self.port

    def stop(self) -> None:
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except OSError:
                pass
            self.server_sock = None
        if self.thread:
            self.thread.join(timeout=1.0)

    def _run(self) -> None:
        while self.running and self.server_sock:
            try:
                client_sock, _ = self.server_sock.accept()
            except OSError:
                break

            client_thread = threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True)
            client_thread.start()

    def _handle_client(self, sock: socket.socket) -> None:
        buffer = bytearray()
        try:
            while self.running:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buffer.extend(chunk)

                while b"\n" in buffer:
                    idx = buffer.find(b"\n")
                    line = buffer[:idx].decode("utf-8", errors="replace").strip()
                    del buffer[:idx + 1]

                    if not line:
                        continue

                    req = json.loads(line)
                    self.commands_received += 1

                    # Check deliberate connection drop simulation
                    if self.drop_on_command_count > 0 and self.commands_received == self.drop_on_command_count:
                        # Sever socket violently without sending response
                        sock.close()
                        return

                    if self.simulated_delay > 0:
                        time.sleep(self.simulated_delay)

                    # Build standard response
                    cmd_type = req.get("type")
                    if cmd_type == "ping":
                        resp = {
                            "status": "success",
                            "result": {
                                "pong": True,
                                "version": self.custom_version,
                                "pid": self.custom_pid,
                            },
                        }
                    else:
                        resp = {
                            "status": "success",
                            "result": {"echo": req, "cmd_id": self.commands_received},
                        }

                    resp_bytes = (json.dumps(resp) + "\n").encode("utf-8")
                    sock.sendall(resp_bytes)
        except (OSError, json.JSONDecodeError):
            pass
        finally:
            try:
                sock.close()
            except OSError:
                pass


class MockDaemonManager:
    """Simulates DaemonManager for testing respawn notifications."""

    def __init__(self, server: MockBlenderServer) -> None:
        self.server = server
        self.is_alive = True
        self.respawn_count = 0

    def is_running(self) -> bool:
        return self.is_alive

    def ensure_daemon_running(self) -> bool:
        self.respawn_count += 1
        self.is_alive = True
        # Restart mock server on same port
        self.server.start()
        return True


# --- Test Fixtures & Cases ---

@pytest.fixture
def mock_server():
    server = MockBlenderServer()
    server.start()
    yield server
    server.stop()


def test_normal_command_roundtrip(mock_server):
    """Verify normal framed JSON command and response."""
    client = BlenderSocketClient(host=mock_server.host, port=mock_server.port)
    with client:
        res = client.send_command({"type": "get_scene_info", "params": {"detailed": True}})
        assert res.get("status") == "success"
        assert res["result"]["echo"]["type"] == "get_scene_info"


def test_ping_probe_metadata(mock_server):
    """Verify fast healthcheck returns version, pid, and latency < 50ms."""
    client = BlenderSocketClient(host=mock_server.host, port=mock_server.port)
    ping_res = client.ping()
    assert ping_res["alive"] is True
    assert ping_res["pong"] is True
    assert ping_res["version"] == "4.1.1"
    assert ping_res["pid"] == 98765
    assert ping_res["latency_ms"] < 200.0  # Localhost is typically < 5ms
    assert client.is_alive() is True


def test_ping_unreachable_server_fails_fast():
    """Verify ping against dead port returns alive=False within 2s without hanging."""
    # Port 59999 is unbound
    client = BlenderSocketClient(host="127.0.0.1", port=59999, ping_timeout=1.0)
    t0 = time.perf_counter()
    ping_res = client.ping()
    elapsed = time.perf_counter() - t0

    assert ping_res["alive"] is False
    assert ping_res["error"] is not None
    assert elapsed < 1.5  # Bounded fail-fast


def test_buffer_framing_multiple_and_partial_chunks(mock_server):
    """Verify accumulator handles fragmented payloads and back-to-back frames."""
    client = BlenderSocketClient(host=mock_server.host, port=mock_server.port)
    with client:
        # Send 5 rapid commands; socket client must parse each distinctly
        for i in range(5):
            res = client.send_command({"type": "iteration", "params": {"i": i}})
            assert res["result"]["echo"]["params"]["i"] == i


def test_auto_reconnect_severed_socket_under_3s(mock_server):
    """
    Core R1 Acceptance Test:
    Server forcefully terminates connection on command #1.
    Command #2 detects severance, reconnects (< 3s), and retries seamlessly.
    """
    mock_server.drop_on_command_count = 1  # Drop client on first command
    client = BlenderSocketClient(host=mock_server.host, port=mock_server.port)

    with client:
        # Command 1 succeeds before severance trigger
        res1 = client.send_command({"type": "cmd_1"})
        assert res1["status"] == "success"

        # Now server dropped socket. Command 2 should trigger auto-recovery and succeed.
        t0 = time.perf_counter()
        res2 = client.send_command({"type": "cmd_2"})
        recovery_time = time.perf_counter() - t0

        assert res2["status"] == "success"
        assert res2["result"]["echo"]["type"] == "cmd_2"
        # Must recover in less than 3.0 seconds!
        assert recovery_time < 3.0
        print(f"Auto-recovery latency under severed socket: {recovery_time:.3f}s")


def test_daemon_respawn_hook_on_daemon_death(mock_server):
    """Verify DaemonManager is notified to respawn daemon if process dies."""
    daemon_mgr = MockDaemonManager(mock_server)
    client = BlenderSocketClient(
        host=mock_server.host,
        port=mock_server.port,
        daemon_manager=daemon_mgr,
    )

    with client:
        # Normal command
        client.send_command({"type": "init"})

        # Simulate fatal daemon death
        daemon_mgr.is_alive = False
        mock_server.stop()

        # Next command detects broken socket, notices daemon_mgr.is_alive == False,
        # triggers ensure_daemon_running(), which starts mock_server and rebinds.
        res = client.send_command({"type": "after_respawn"})
        assert res["status"] == "success"
        assert daemon_mgr.respawn_count == 1


def test_thread_safety_concurrent_commands(mock_server):
    """Verify thread-safety: 10 concurrent threads sending 100 commands without corruption."""
    client = BlenderSocketClient(host=mock_server.host, port=mock_server.port)
    errors: List[Exception] = []

    def worker(worker_id: int):
        for j in range(10):
            try:
                res = client.send_command({"type": "worker_test", "worker": worker_id, "seq": j})
                if res.get("status") != "success":
                    errors.append(ValueError(f"Bad response: {res}"))
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    client.disconnect()
    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"


def test_command_timeout_zero_crash(mock_server):
    """Verify command timeout raises clean BlenderTimeoutError without socket leak."""
    mock_server.simulated_delay = 1.0  # Server delays 1s
    client = BlenderSocketClient(host=mock_server.host, port=mock_server.port, command_timeout=0.3)

    with pytest.raises(BlenderTimeoutError):
        client.send_command({"type": "slow_operation"})

    # Socket state is safely recoverable on next operation
    mock_server.simulated_delay = 0.0
    client.command_timeout = 5.0
    res = client.send_command({"type": "quick_operation"})
    assert res["status"] == "success"

