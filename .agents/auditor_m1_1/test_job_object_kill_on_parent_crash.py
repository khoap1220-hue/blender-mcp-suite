"""
Test that Windows Job Object terminates Blender daemon even if parent crashes (os._exit).
"""
import subprocess
import sys
import time
import os

parent_code = """
import sys, os, time
sys.path.insert(0, "src")
from blender_mcp.daemon_manager import DaemonManager

mgr = DaemonManager(host="127.0.0.1", port=9895)
status = mgr.ensure_daemon_running(timeout=15.0)
pid = status["pid"]
print(f"BLENDER_SPAWNED_PID:{pid}", flush=True)
time.sleep(1.0)
# Hard exit without calling shutdown or cleanup
os._exit(0)
"""

p = subprocess.Popen(
    [sys.executable, "-c", parent_code],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd=r"y:\MCP Blender Agent",
)

stdout, stderr = p.communicate(timeout=20.0)
print("PARENT_STDOUT:\n", stdout)
print("PARENT_STDERR:\n", stderr)

blender_pid = None
for line in stdout.splitlines():
    if "BLENDER_SPAWNED_PID:" in line:
        blender_pid = int(line.strip().split(":")[1])
        break
print(f"Parent process exited with code {p.returncode}. Checking Blender PID {blender_pid}...")

# Check if blender_pid is alive or terminated
time.sleep(2.0)

# Check via tasklist
res = subprocess.run(["tasklist", "/fi", f"PID eq {blender_pid}"], capture_output=True, text=True)
print("TASKLIST RESULT:\n", res.stdout)
if str(blender_pid) in res.stdout:
    print(f"[FAIL] Blender process {blender_pid} is still alive! Windows Job Object did not kill it on parent crash.")
    subprocess.run(["taskkill", "/F", "/PID", str(blender_pid)])
    sys.exit(1)
else:
    print(f"[PASS] Blender process {blender_pid} was killed by Windows Job Object on parent crash!")
    sys.exit(0)
