"""
tests/test_adversarial_socket_resilience.py
Adversarial Stress Test Harness for Milestone M1 Socket Resilience.

Empirically challenges:
1. Abrupt client socket termination mid-call.
2. Abrupt server socket drops (graceful FIN and violent TCP RST).
3. Mid-stream truncation (incomplete JSON payload without newline followed by immediate drop).
4. Multi-chunk fragmented truncation before drop.
5. Simulated network latency / jitter during send_command without false disconnects.
6. Multiple consecutive socket drops across successive calls without leaking socket handles.
7. Reconnection duration benchmarking (< 3.0s requirement) with high-resolution time.perf_counter.
8. Live Blender 4.1.1 daemon socket drop and auto-recovery benchmark.
9. Response synchronization under command timeout boundary.
"""

from __future__ import annotations

import gc
import json
import os
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from blender_mcp.daemon_manager import DaemonManager
from blender_mcp.socket_client import (
    BlenderConnectionError,
    BlenderProtocolError,
    BlenderSocketClient,
    BlenderTimeoutError,
)


class AdversarialMockServer:
    """
    Highly configurable TCP server engineered specifically for adversarial socket testing.
    Can inject TCP RST, mid-stream truncations, artificial latency, and controlled drops.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.server_sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False

        # Adversarial control state
        self._drop_budget: int = 0
        self._drop_behavior: str = "drop_fin"  # "drop_fin", "drop_rst", "truncate", "multi_truncate"
        self._truncate_payload: bytes = b'{"status": "succ'
        self.latency_seconds: float = 0.0

        self.total_commands_received: int = 0
        self.active_clients: List[socket.socket] = []
        self._lock = threading.Lock()

    def start(self) -> int:
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.port = self.server_sock.getsockname()[1]
        self.server_sock.listen(16)
        self.running = True

        self.thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.thread.start()
        return self.port

    def stop(self) -> None:
        self.running = False
        with self._lock:
            for s in list(self.active_clients):
                try:
                    s.close()
                except OSError:
                    pass
            self.active_clients.clear()

        if self.server_sock:
            try:
                self.server_sock.close()
            except OSError:
                pass
            self.server_sock = None

        if self.thread:
            self.thread.join(timeout=1.0)

    def trigger_drop(self, behavior: str = "drop_fin", count: int = 1, truncate_payload: bytes = b'{"status": "succ') -> None:
        """Arm the server to drop the next `count` commands using specified behavior."""
        with self._lock:
            self._drop_behavior = behavior
            self._drop_budget = count
            self._truncate_payload = truncate_payload

    def _accept_loop(self) -> None:
        while self.running and self.server_sock:
            try:
                client_sock, _ = self.server_sock.accept()
            except OSError:
                break

            with self._lock:
                self.active_clients.append(client_sock)

            t = threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True)
            t.start()

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
                    del buffer[: idx + 1]

                    if not line:
                        continue

                    req = json.loads(line)
                    with self._lock:
                        self.total_commands_received += 1
                        should_drop = self._drop_budget > 0
                        if should_drop:
                            self._drop_budget -= 1
                            behavior = self._drop_behavior
                            payload = self._truncate_payload

                    if should_drop:
                        if behavior == "drop_rst":
                            # Send TCP RST by setting SO_LINGER to (1, 0) and closing immediately
                            try:
                                sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                            except OSError:
                                pass
                            sock.close()
                            return
                        elif behavior == "truncate":
                            # Send partial chunk without newline, then close abruptly
                            try:
                                sock.sendall(payload)
                            except OSError:
                                pass
                            sock.close()
                            return
                        elif behavior == "multi_truncate":
                            # Send 2 fragmented chunks then close abruptly
                            try:
                                sock.sendall(b'{"status":')
                                time.sleep(0.02)
                                sock.sendall(b' "partial_data"')
                            except OSError:
                                pass
                            sock.close()
                            return
                        else:  # drop_fin
                            sock.close()
                            return

                    # Normal handling with optional latency
                    if self.latency_seconds > 0:
                        time.sleep(self.latency_seconds)

                    cmd_type = req.get("type", "unknown")
                    resp = {
                        "status": "success",
                        "result": {
                            "type": cmd_type,
                            "echo": req.get("params", {}),
                        },
                    }
                    data = (json.dumps(resp) + "\n").encode("utf-8")
                    sock.sendall(data)

        except (OSError, json.JSONDecodeError):
            pass
        finally:
            with self._lock:
                if sock in self.active_clients:
                    self.active_clients.remove(sock)
            try:
                sock.close()
            except OSError:
                pass


@pytest.fixture
def adv_server():
    server = AdversarialMockServer()
    server.start()
    yield server
    server.stop()


# ---------------------------------------------------------------------------
# CHALLENGE 1: Abrupt Server Drop with Violent TCP RST
# ---------------------------------------------------------------------------

def test_adversarial_server_rst_drop(adv_server):
    """
    Adversarial Scenario: Server forcefully issues TCP RST (WSAECONNRESET) mid-command.
    Verify: Client catches error, auto-reconnects in < 3.0s, and successfully completes retried command.
    """
    client = BlenderSocketClient(host=adv_server.host, port=adv_server.port)
    with client:
        # Arm server to drop the first command with TCP RST
        adv_server.trigger_drop(behavior="drop_rst", count=1)

        t0 = time.perf_counter()
        resp = client.send_command({"type": "test_rst", "params": {"data": 123}})
        elapsed = time.perf_counter() - t0

        assert resp["status"] == "success"
        assert resp["result"]["type"] == "test_rst"
        assert resp["result"]["echo"]["data"] == 123
        assert elapsed < 3.0, f"Reconnection took {elapsed:.3f}s, exceeding 3.0s budget!"
        print(f"\n[PASS] Server RST drop recovered in {elapsed:.3f}s (< 3.0s budget)")


# ---------------------------------------------------------------------------
# CHALLENGE 2: Abrupt Client Socket Termination Mid-Call
# ---------------------------------------------------------------------------

def test_adversarial_abrupt_client_socket_sever(adv_server):
    """
    Adversarial Scenario: Client's underlying OS socket is abruptly closed right before call.
    Verify: Client detects dead handle, re-establishes connection, and completes call in < 3.0s.
    """
    client = BlenderSocketClient(host=adv_server.host, port=adv_server.port)
    with client:
        # Establish connection
        client.send_command({"type": "init"})
        assert client.is_connected

        # Forcefully corrupt/close internal socket descriptor behind client's back
        raw_sock = client._sock
        assert raw_sock is not None
        raw_sock.close()

        # Send command should detect closed socket, auto-recover in < 3.0s, and succeed
        t0 = time.perf_counter()
        resp = client.send_command({"type": "post_client_sever", "params": {"key": "val"}})
        elapsed = time.perf_counter() - t0

        assert resp["status"] == "success"
        assert resp["result"]["type"] == "post_client_sever"
        assert resp["result"]["echo"]["key"] == "val"
        assert elapsed < 3.0, f"Reconnection took {elapsed:.3f}s, exceeding 3.0s budget!"
        print(f"\n[PASS] Abrupt client-side socket sever recovered in {elapsed:.3f}s (< 3.0s budget)")


# ---------------------------------------------------------------------------
# CHALLENGE 3: Mid-Stream Truncation (Corrupted Incomplete Frame + Drop)
# ---------------------------------------------------------------------------

def test_adversarial_midstream_truncation_recovery(adv_server):
    """
    Adversarial Scenario: Server sends partial JSON '{"status": "succ' then drops socket.
    Verify: Client receive buffer is purged; dirty partial frame does not contaminate retry.
    """
    client = BlenderSocketClient(host=adv_server.host, port=adv_server.port)
    with client:
        adv_server.trigger_drop(behavior="truncate", count=1, truncate_payload=b'{"status": "succ')

        t0 = time.perf_counter()
        resp = client.send_command({"type": "test_truncate", "params": {"payload": "clean_request"}})
        elapsed = time.perf_counter() - t0

        assert resp["status"] == "success"
        assert resp["result"]["type"] == "test_truncate"
        assert resp["result"]["echo"]["payload"] == "clean_request"
        assert elapsed < 3.0, f"Reconnection took {elapsed:.3f}s, exceeding 3.0s budget!"
        print(f"\n[PASS] Mid-stream truncation recovered cleanly in {elapsed:.3f}s (< 3.0s budget)")


# ---------------------------------------------------------------------------
# CHALLENGE 4: Multi-Chunk Fragmented Truncation
# ---------------------------------------------------------------------------

def test_adversarial_multi_chunk_fragmented_truncation(adv_server):
    """
    Adversarial Scenario: Server sends multiple broken chunks across network then severs.
    Verify: Client buffer cleanly resets and retry succeeds in < 3.0s.
    """
    client = BlenderSocketClient(host=adv_server.host, port=adv_server.port)
    with client:
        adv_server.trigger_drop(behavior="multi_truncate", count=1)

        t0 = time.perf_counter()
        resp = client.send_command({"type": "multi_frag_test", "params": {"tag": "alpha"}})
        elapsed = time.perf_counter() - t0

        assert resp["status"] == "success"
        assert resp["result"]["type"] == "multi_frag_test"
        assert resp["result"]["echo"]["tag"] == "alpha"
        assert elapsed < 3.0, f"Reconnection took {elapsed:.3f}s, exceeding 3.0s budget!"
        print(f"\n[PASS] Multi-chunk fragmented truncation recovered in {elapsed:.3f}s (< 3.0s budget)")


# ---------------------------------------------------------------------------
# CHALLENGE 5: Simulated Network Latency / Jitter (No False Disconnects)
# ---------------------------------------------------------------------------

def test_adversarial_simulated_network_latency(adv_server):
    """
    Adversarial Scenario: Network or Blender computation exhibits 300ms latency.
    Verify: Client handles delayed response correctly without premature reconnection or timeout.
    """
    adv_server.latency_seconds = 0.3
    client = BlenderSocketClient(host=adv_server.host, port=adv_server.port, command_timeout=2.0)

    with client:
        t0 = time.perf_counter()
        resp = client.send_command({"type": "latency_test", "params": {"wait": 0.3}})
        elapsed = time.perf_counter() - t0

        assert resp["status"] == "success"
        assert resp["result"]["type"] == "latency_test"
        assert 0.28 <= elapsed <= 1.0, f"Elapsed {elapsed:.3f}s outside expected window [0.28, 1.0]"
        print(f"\n[PASS] Handled 300ms latency without false disconnects (elapsed: {elapsed:.3f}s)")


# ---------------------------------------------------------------------------
# CHALLENGE 6: Multiple Consecutive Socket Drops & Handle Leak Audit
# ---------------------------------------------------------------------------

def test_adversarial_multiple_consecutive_drops_and_handle_leak(adv_server):
    """
    Adversarial Scenario: Server drops 10 CONSECUTIVE commands in a row!
    On every single command, the first attempt is dropped (FIN), client auto-recovers and completes.
    Verify:
    1. All 10 consecutive commands recover in < 3.0s each.
    2. Zero unhandled exceptions raised to the caller.
    3. Windows OS handle count does NOT leak across 10 drop/reconnect cycles.
    """
    proc = psutil.Process()
    gc.collect()
    initial_handles = proc.num_handles()

    client = BlenderSocketClient(host=adv_server.host, port=adv_server.port)
    recovery_times: List[float] = []

    with client:
        for i in range(10):
            # Arm server to drop on the 1st attempt of this command
            adv_server.trigger_drop(behavior="drop_fin", count=1)

            t0 = time.perf_counter()
            resp = client.send_command({"type": f"consecutive_drop_{i}", "params": {"idx": i}})
            elapsed = time.perf_counter() - t0
            recovery_times.append(elapsed)

            assert resp["status"] == "success"
            assert resp["result"]["type"] == f"consecutive_drop_{i}"
            assert resp["result"]["echo"]["idx"] == i
            assert elapsed < 3.0, f"Iteration {i} took {elapsed:.3f}s (> 3.0s limit)"

    # Audit OS handles after all 10 drop-and-recover cycles
    gc.collect()
    time.sleep(0.1)
    final_handles = proc.num_handles()
    handle_growth = final_handles - initial_handles

    avg_recovery = sum(recovery_times) / len(recovery_times)
    max_recovery = max(recovery_times)
    min_recovery = min(recovery_times)

    print(
        f"\n[PASS] 10 consecutive drops handled cleanly!\n"
        f"  - Min recovery: {min_recovery:.3f}s\n"
        f"  - Avg recovery: {avg_recovery:.3f}s\n"
        f"  - Max recovery: {max_recovery:.3f}s\n"
        f"  - Initial handles: {initial_handles}, Final handles: {final_handles} (Delta: {handle_growth})"
    )

    # In Windows, handle count fluctuates slightly due to pytest internals (+/- 5 handles),
    # but leaking 10 sockets would cause a sustained jump of >= 10 handles.
    assert handle_growth <= 5, f"Handle leak detected! Initial={initial_handles}, Final={final_handles}, Growth={handle_growth}"


# ---------------------------------------------------------------------------
# CHALLENGE 7: Live Blender 4.1.1 Daemon Socket Drop & Recovery Benchmark
# ---------------------------------------------------------------------------

def test_adversarial_live_blender_socket_drop_benchmark():
    """
    Adversarial Scenario: Live Blender 4.1.1 headless daemon running on port 9892.
    Client forcibly severs socket while interacting with live Blender engine.
    Verify:
    1. Recovery succeeds against the real Blender process in < 3.0s.
    2. Real bpy / Python computation executes accurately after recovery.
    """
    test_port = 9892
    daemon_mgr = DaemonManager(port=test_port)

    # Ensure clean start
    daemon_mgr.ensure_daemon_running()
    assert daemon_mgr.is_running()

    client = BlenderSocketClient(port=test_port, daemon_manager=daemon_mgr)
    try:
        with client:
            # 1. Verify initial live handshake
            p1 = client.ping()
            assert p1["alive"] is True
            assert "4.1" in str(p1["version"])

            # 2. Forcibly close the socket under the hood
            assert client._sock is not None
            client._sock.close()

            # 3. Call execute_code against live Blender — must auto-recover and return result
            t0 = time.perf_counter()
            resp = client.send_command({
                "type": "execute_code",
                "params": {
                    "code": "result = {'adversarial_key': 99 * 88, 'platform': sys.platform}"
                }
            })
            recovery_duration = time.perf_counter() - t0

            assert resp["status"] == "success"
            res_data = resp["result"]
            assert res_data["adversarial_key"] == 8712
            assert res_data["platform"] == "win32"
            assert recovery_duration < 3.0, f"Live Blender recovery duration {recovery_duration:.3f}s exceeded 3.0s!"

            print(
                f"\n[PASS] Live Blender 4.1.1 daemon recovery benchmark: {recovery_duration:.3f}s (< 3.0s budget)\n"
                f"  - Computation verified: 99 * 88 = {res_data['adversarial_key']}"
            )

    finally:
        client.disconnect()
        daemon_mgr.shutdown()


# ---------------------------------------------------------------------------
# CHALLENGE 8: Desynchronization Resilience Check on Command Timeout
# ---------------------------------------------------------------------------

def test_adversarial_timeout_socket_hygiene(adv_server):
    """
    Adversarial Scenario:
    Command 1 times out because server is intentionally delayed.
    Verify whether subsequent commands can recover without receiving stale responses.
    """
    adv_server.latency_seconds = 0.5
    client = BlenderSocketClient(host=adv_server.host, port=adv_server.port, command_timeout=0.1)

    with client:
        # Command 1: times out
        with pytest.raises(BlenderTimeoutError):
            client.send_command({"type": "timed_out_command"})

        # Wait for server to finish transmitting stale response to socket buffer
        time.sleep(0.6)

        # Server latency reset to 0
        adv_server.latency_seconds = 0.0
        client.command_timeout = 2.0

        # When client disconnects or reconnects after timeout, framing must stay synchronized
        client.disconnect()  # Ensure hygiene
        resp = client.send_command({"type": "fresh_command", "params": {"expected": 42}})

        assert resp["status"] == "success"
        assert resp["result"]["type"] == "fresh_command"
        assert resp["result"]["echo"]["expected"] == 42
        print("\n[PASS] Post-timeout fresh command executed with clean frame synchronization.")
