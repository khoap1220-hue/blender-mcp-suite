"""
.agents/auditor_m1_1/forensic_test.py
Independent Forensic Integrity Verification Script for Milestone M1.
"""

import os
import sys
import time
import socket
import subprocess

REPO_ROOT = r"y:\MCP Blender Agent"
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from blender_mcp.daemon_manager import BlenderBinaryDetector, DaemonManager, WindowsJobObject
from blender_mcp.socket_client import BlenderSocketClient


def test_genuine_windows_job_object():
    print("[1/3] Testing genuine Windows Job Object kernel containment...")
    job = WindowsJobObject()
    created = job.create()
    assert created is True, "Failed to create Windows Job Object"
    assert job._handle is not None, "Job Object handle is None"
    print(f"      Kernel Job Object created successfully, handle: {job._handle}")

    # Launch a dummy worker process
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        assert proc.poll() is None, "Child process failed to start"
        assigned = job.assign_process(proc)
        assert assigned is True, "Failed to assign process to Job Object"
        print(f"      Child process PID {proc.pid} assigned to Job Object")

        # Terminate Job Object by closing handle
        job.close()
        print("      Job Object handle closed. Awaiting kernel process termination...")

        try:
            proc.wait(timeout=3.0)
            print(f"      [PASS] Child process PID {proc.pid} was terminated by Windows kernel!")
        except subprocess.TimeoutExpired:
            proc.kill()
            raise AssertionError("[FAIL] Child process was NOT terminated when Job Object handle closed!")
    finally:
        if proc.poll() is None:
            proc.kill()


def test_live_blender_dynamic_execution():
    print("\n[2/3] Testing live Blender 4.1 execution with dynamic, non-hardcoded payloads...")
    detector = BlenderBinaryDetector()
    blender_path, version = detector.find_blender()
    print(f"      Detected Blender: {blender_path} ({version})")

    port = 9892
    mgr = DaemonManager(host="127.0.0.1", port=port, custom_blender_path=blender_path)
    try:
        status = mgr.ensure_daemon_running(timeout=15.0)
        assert status["running"] is True
        print(f"      Blender daemon running on port {port}, PID: {status['pid']}")

        client = BlenderSocketClient(host="127.0.0.1", port=port)
        with client:
            # 1. Ping
            ping_res = client.ping()
            assert ping_res["alive"] is True
            assert ping_res["pong"] is True
            print(f"      Ping OK: version={ping_res['version']}, pid={ping_res['pid']}, latency={ping_res['latency_ms']}ms")

            # 2. Dynamic arithmetic (cannot be hardcoded)
            expr = "result = 98765 * 4321 + 1111"
            expected = 98765 * 4321 + 1111
            res = client.send_command({"type": "execute_code", "params": {"code": expr}})
            assert res["status"] == "success"
            assert res["result"] == expected
            print(f"      Dynamic computation check: {expected} == {res['result']} -> PASS")

            # 3. Dynamic Blender mesh manipulation
            bpy_code = (
                "import bpy\n"
                "bpy.ops.mesh.primitive_cylinder_add(radius=2.5, depth=4.0)\n"
                "obj = bpy.context.active_object\n"
                "result = {'name': obj.name, 'type': obj.type, 'dim_z': round(obj.dimensions.z, 2)}"
            )
            res = client.send_command({"type": "execute_code", "params": {"code": bpy_code}})
            assert res["status"] == "success"
            assert res["result"]["name"].startswith("Cylinder")
            assert res["result"]["type"] == "MESH"
            assert res["result"]["dim_z"] == 4.0
            print(f"      Dynamic Blender bpy execution: created {res['result']['name']} -> PASS")

            # 4. Mathutils vector serialization
            vec_code = "import mathutils; result = mathutils.Vector((12.0, 56.0, 90.0))"
            res = client.send_command({"type": "execute_code", "params": {"code": vec_code}})
            assert res["status"] == "success"
            assert res["result"] == [12.0, 56.0, 90.0]
            print(f"      BlenderJSONEncoder mathutils Vector check: {res['result']} -> PASS")

            # 5. Stdout / stderr capture
            token = "FORENSIC_TOKEN_998877"
            print_code = f"print('{token}'); result = True"
            res = client.send_command({"type": "execute_code", "params": {"code": print_code}})
            assert res["status"] == "success"
            assert token in res["stdout"]
            print(f"      Stdout capture check: found '{token}' -> PASS")

            # 6. Structured error handling in execute_code
            err_code = "raise KeyError('AUDIT_TEST_KEY_ERROR')"
            res = client.send_command({"type": "execute_code", "params": {"code": err_code}})
            assert res["status"] == "error"
            assert res["error_code"] == -32000
            assert "AUDIT_TEST_KEY_ERROR" in res["message"]
            print(f"      Exception boundary check: error_code {res['error_code']} ({res['message']}) -> PASS")

        # 7. Shutdown
        print("      Shutting down Blender daemon...")
        shut = mgr.shutdown(timeout=5.0)
        assert shut is True
        print("      Daemon shutdown reported True.")

        # 8. Check port release
        time.sleep(1.0)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
            raise AssertionError(f"Port {port} is still open after shutdown!")
        except (ConnectionRefusedError, socket.timeout, OSError):
            print("      [PASS] Port 9892 successfully released!")
        finally:
            s.close()

    finally:
        if mgr.process is not None:
            mgr.shutdown(timeout=2.0)


def test_socket_auto_recovery_timing():
    print("\n[3/3] Testing socket auto-recovery timing under severed connection...")
    # Import MockBlenderServer from tests/test_socket_client.py
    sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
    from test_socket_client import MockBlenderServer

    server = MockBlenderServer()
    server.start()
    try:
        server.drop_on_command_count = 1
        client = BlenderSocketClient(host=server.host, port=server.port)
        with client:
            r1 = client.send_command({"type": "init"})
            assert r1["status"] == "success"

            # Connection dropped by server on command 1. Command 2 triggers auto-recovery:
            t0 = time.perf_counter()
            r2 = client.send_command({"type": "retry"})
            recovery_time = time.perf_counter() - t0

            assert r2["status"] == "success"
            assert recovery_time < 3.0
            print(f"      [PASS] Auto-recovery completed in {recovery_time:.3f}s (< 3.0s requirement)!")
    finally:
        server.stop()


if __name__ == "__main__":
    test_genuine_windows_job_object()
    test_live_blender_dynamic_execution()
    test_socket_auto_recovery_timing()
    print("\n========================================================")
    print("ALL FORENSIC VERIFICATION CHECKS PASSED EMPIRICALLY!")
    print("========================================================")
