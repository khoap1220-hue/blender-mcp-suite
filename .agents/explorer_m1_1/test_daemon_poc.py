"""
Proof of Concept: Test headless Blender socket loop with SO_EXCLUSIVEADDRUSE
"""
import sys
import socket
import json
import os
import select
import time

print(f"[TEST_POC] Starting in Blender PID: {os.getpid()}")
print(f"[TEST_POC] Python version: {sys.version}")

HOST = "127.0.0.1"
PORT = 9988  # Use 9988 for test so we don't interfere with anything on 9876

server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
else:
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server_sock.bind((HOST, PORT))
server_sock.listen(5)
server_sock.setblocking(False)

print(f"[BLENDER_MCP_DAEMON_READY:{PORT}]", flush=True)

# Run loop for 2 seconds to prove it doesn't exit immediately and receives select
start = time.time()
print("[TEST_POC] Entering event loop for 2 seconds...")
while time.time() - start < 2.0:
    rlist, _, _ = select.select([server_sock], [], [], 0.1)
    if rlist:
        print("[TEST_POC] Activity detected on socket!")

server_sock.close()
print("[TEST_POC] Loop exited cleanly, shutting down.")
