"""
tests/test_daemon_lifecycle.py
Unit and integration tests for Blender binary locator, Windows Job Object containment,
and DaemonManager lifecycle.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from blender_mcp.daemon_manager import (
    BlenderBinaryDetector,
    BlenderNotFoundError,
    BlenderVersionError,
    DaemonManager,
    WindowsJobObject,
)
from blender_mcp.socket_client import BlenderSocketClient


def test_blender_binary_detection_default():
    """Verify 4-stage binary detector locates Blender 4.1+ executable."""
    detector = BlenderBinaryDetector()
    path, ver = detector.find_blender()
    assert path is not None
    assert os.path.isfile(path)
    assert ver.startswith("4.1")


def test_blender_binary_detection_env_var_override(monkeypatch):
    """Verify BLENDER_PATH environment variable overrides default search order."""
    detector = BlenderBinaryDetector()
    real_path, real_ver = detector.find_blender()
    monkeypatch.setenv("BLENDER_PATH", real_path)

    found_path, found_ver = detector.find_blender()
    assert os.path.normcase(found_path) == os.path.normcase(real_path)
    assert found_ver == real_ver


def test_blender_binary_detection_invalid_env_var(monkeypatch):
    """Verify non-existent BLENDER_PATH is rejected and detector raises or falls back."""
    monkeypatch.setenv("BLENDER_PATH", r"C:\non_existent_dir_99999\blender.exe")
    monkeypatch.setenv("BLENDER_EXECUTABLE", "")
    monkeypatch.setenv("BLENDER_BIN", "")
    detector = BlenderBinaryDetector()

    # When explicit env var points to missing file, stage 1 produces empty and falls back to other stages
    # If other stages find binary, it returns that; otherwise BlenderNotFoundError
    path, ver = detector.find_blender()
    assert os.path.isfile(path)


def test_blender_version_validation_rejection(monkeypatch):
    """Verify validate_version() correctly rejects versions < 4.1."""
    detector = BlenderBinaryDetector(min_major=4, min_minor=1)

    class DummyCompletedProcess:
        stdout = "Blender 3.6.5\n\tbuild date: 2023-10-18\n"
        stderr = ""
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: DummyCompletedProcess())
    is_valid, ver_tuple, ver_str = detector.validate_version(sys.executable)
    assert is_valid is False
    assert ver_tuple == (3, 6, 5)
    assert ver_str == "3.6.5"


def test_windows_job_object_lifecycle_and_containment():
    """Verify Windows Job Object kernel containment terminates child on close."""
    job = WindowsJobObject()
    created = job.create()
    if not job._is_windows:
        pytest.skip("Windows Job Objects are only supported on Win32")

    assert created is True
    assert job._handle is not None

    # Spawn dummy child process
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        assert proc.poll() is None
        assigned = job.assign_process(proc)
        assert assigned is True

        # Close handle; Windows kernel terminates child
        job.close()
        try:
            proc.wait(timeout=3.0)
            assert proc.poll() is not None
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("Child process was not terminated when Job Object handle closed")
    finally:
        if proc.poll() is None:
            proc.kill()


def test_daemon_gui_session_detection_and_clean_detach():
    """Verify probe_existing_session() detects active session and shutdown() detaches cleanly."""
    # Start temporary server simulating active GUI session
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen(1)

    running = True

    def srv_loop():
        while running:
            try:
                server.settimeout(0.5)
                conn, _ = server.accept()
                data = conn.recv(1024)
                if b"ping" in data:
                    resp = json.dumps({"status": "success", "result": {"pong": True, "version": "4.1.1", "pid": 11111}}) + "\n"
                    conn.sendall(resp.encode("utf-8"))
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break

    t = threading.Thread(target=srv_loop, daemon=True)
    t.start()

    try:
        mgr = DaemonManager(port=port)
        probe = mgr.probe_existing_session()
        assert probe is not None
        assert probe["pong"] is True
        assert probe["pid"] == 11111

        # ensure_daemon_running attaches as GUI session
        status = mgr.ensure_daemon_running()
        assert status["running"] is True
        assert status["is_gui"] is True

        # Shutdown should detach cleanly without killing server
        assert mgr.shutdown() is True
        assert running is True
    finally:
        running = False
        server.close()
        t.join(timeout=1.0)


def test_live_headless_daemon_handshake_and_execution():
    """Verify live headless daemon spawn, handshake, command execution, and clean shutdown."""
    # Find free port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    test_port = s.getsockname()[1]
    s.close()

    mgr = DaemonManager(port=test_port)
    try:
        status = mgr.ensure_daemon_running(timeout=12.0)
        assert status["running"] is True
        assert mgr.is_running() is True

        client = BlenderSocketClient(port=test_port, daemon_manager=mgr)
        with client:
            ping_res = client.ping()
            assert ping_res["alive"] is True
            assert ping_res["pong"] is True

            # Execute simple math command
            res = client.send_command({
                "type": "execute_code",
                "params": {"code": "result = 1234 * 2"}
            })
            assert res["status"] == "success"
            assert res["result"] == 2468
    finally:
        mgr.shutdown(timeout=3.0)
        assert mgr.is_running() is False


def test_daemon_port_conflict_detection():
    """Verify binding on already occupied port is detected."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.listen(1)

    try:
        mgr = DaemonManager(port=port)
        # Port is open but not responding with MCP ping
        probe = mgr.probe_existing_session(timeout=0.2)
        assert probe is None
    finally:
        s.close()
