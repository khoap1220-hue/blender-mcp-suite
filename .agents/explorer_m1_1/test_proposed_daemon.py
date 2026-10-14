"""
test_proposed_daemon.py — Validates proposed_blender_mcp_daemon.py functionality
"""
import socket
import json
import sys

HOST = "127.0.0.1"
PORT = 9990

s = socket.socket()
s.connect((HOST, PORT))

# 1. Ping
s.sendall(json.dumps({"type": "ping"}).encode("utf-8") + b"\n")
resp1 = json.loads(s.recv(4096).decode("utf-8"))
print("PING RESP:", resp1)
assert resp1["status"] == "success"
assert resp1["result"]["pong"] is True
assert "4.1.1" in resp1["result"]["version"]

# 2. Execute code with Vector and bpy types
exec_payload = {
    "type": "execute_code",
    "params": {
        "code": "import mathutils\nresult = {'vec': mathutils.Vector((1, 2, 3)), 'cube': bpy.data.objects.get('Cube')}",
        "strict_json": False
    }
}
s.sendall(json.dumps(exec_payload).encode("utf-8") + b"\n")
resp2 = json.loads(s.recv(4096).decode("utf-8"))
print("EXEC CODE RESP:", resp2)
assert resp2["status"] == "success"
assert resp2["result"]["vec"] == [1.0, 2.0, 3.0]
assert resp2["result"]["cube"]["name"] == "Cube"

# 3. Shutdown
s.sendall(json.dumps({"type": "shutdown"}).encode("utf-8") + b"\n")
resp3 = json.loads(s.recv(4096).decode("utf-8"))
print("SHUTDOWN RESP:", resp3)
assert resp3["status"] == "success"
s.close()
print("\n[+] ALL CHECKS PASSED FOR PROPOSED DAEMON!")
