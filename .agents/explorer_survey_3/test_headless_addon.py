import subprocess
import os
import sys
import socket
import json
import time

test_harness = r"""
import sys
import os
import bpy
import time
import queue

# Add addon directory to sys.path
sys.path.insert(0, r"y:\MCP Blender Agent\addon")
import blender_mcp

print("[TEST] Loaded blender_mcp module:", blender_mcp.__file__)

# Instantiate server
server = blender_mcp.BlenderMCPServer(host="127.0.0.1", port=9877)

# Override start to NOT return if bpy.app.background
server.running = True
server.socket = blender_mcp.socket.socket(blender_mcp.socket.AF_INET, blender_mcp.socket.SOCK_STREAM)
server.socket.setsockopt(blender_mcp.socket.SOL_SOCKET, blender_mcp.socket.SO_REUSEADDR, 1)
server.socket.bind((server.host, server.port))
server.socket.listen(5)

server.server_thread = blender_mcp.threading.Thread(target=server._server_loop)
server.server_thread.daemon = True
server.server_thread.start()

print(f"[TEST] Headless server listening on {server.host}:{server.port}")

# Main thread loop
start_time = time.time()
while time.time() - start_time < 5.0 and server.running:
    server._drain_command_queue()
    time.sleep(0.02)

server.stop()
print("[TEST] Headless server stopped cleanly.")
"""

harness_path = r"y:\MCP Blender Agent\.agents\explorer_survey_3\headless_mcp_harness.py"
with open(harness_path, "w") as f:
    f.write(test_harness)

blender_exe = r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe"

proc = subprocess.Popen(
    [blender_exe, "--background", "--factory-startup", "--python", harness_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

time.sleep(1.5)

# Connect client to port 9877
try:
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect(("127.0.0.1", 9877))
    # Send ping command as expected by blender_mcp
    c.sendall(json.dumps({"type": "ping"}).encode('utf-8'))
    resp_raw = c.recv(4096)
    print("Received ping response from blender_mcp:", resp_raw.decode('utf-8'))

    # Send execute_code command
    code_cmd = {
        "type": "execute_code",
        "params": {"code": "result = {'version': bpy.app.version_string, 'objects_count': len(bpy.data.objects)}"}
    }
    c.sendall(json.dumps(code_cmd).encode('utf-8'))
    resp_code = c.recv(4096)
    print("Received execute_code response from blender_mcp:", resp_code.decode('utf-8'))
    c.close()
except Exception as e:
    print("Client error:", e)

stdout, stderr = proc.communicate(timeout=10)
print("Blender output:\n", stdout)
