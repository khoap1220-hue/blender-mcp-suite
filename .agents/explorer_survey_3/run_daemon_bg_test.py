import socket
import subprocess
import time
import json

daemon_script = r"""
import bpy
import socket
import json
import threading
import queue
import time
import sys

print("[DAEMON] Starting background daemon script...")

PORT = 9988
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", PORT))
s.listen(5)
s.settimeout(0.2)

print(f"[DAEMON] Listening on port {PORT}")

cmd_queue = queue.Queue()
running = True

def network_thread():
    while running:
        try:
            client, addr = s.accept()
            print(f"[DAEMON-NET] Accepted client from {addr}")
            client.settimeout(5.0)
            data = client.recv(4096)
            if data:
                cmd = json.loads(data.decode('utf-8'))
                res_event = threading.Event()
                cmd_queue.put((cmd, client, res_event))
                res_event.wait(timeout=10.0)
            client.close()
        except socket.timeout:
            continue
        except Exception as e:
            if running:
                print(f"[DAEMON-NET] Error: {e}")

t = threading.Thread(target=network_thread, daemon=True)
t.start()

# Main thread loop: this IS the main thread with full bpy access!
start_time = time.time()
while time.time() - start_time < 5.0: # Run for 5 seconds
    try:
        cmd, client, res_event = cmd_queue.get(timeout=0.1)
        print(f"[DAEMON-MAIN] Executing bpy command: {cmd}")
        # Test bpy operation
        cube = bpy.ops.mesh.primitive_cube_add(size=2.0)
        obj_names = [o.name for o in bpy.data.objects]
        res = {"status": "ok", "objects": obj_names}
        client.sendall(json.dumps(res).encode('utf-8'))
        res_event.set()
    except queue.Empty:
        pass

running = False
s.close()
print("[DAEMON] Daemon finished cleanly.")
"""

script_path = r"y:\MCP Blender Agent\.agents\explorer_survey_3\bg_daemon_test.py"
with open(script_path, "w") as f:
    f.write(daemon_script)

blender_exe = r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe"

# Launch Blender in background
proc = subprocess.Popen(
    [blender_exe, "--background", "--factory-startup", "--python", script_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

time.sleep(1.5)

# Connect as a client
client_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_s.connect(("127.0.0.1", 9988))
client_s.sendall(json.dumps({"action": "create_cube"}).encode('utf-8'))
resp = client_s.recv(4096)
print("Client received response:", resp.decode('utf-8'))
client_s.close()

stdout, stderr = proc.communicate(timeout=10)
print("Blender returncode:", proc.returncode)
print("Blender STDOUT:\n", stdout)
