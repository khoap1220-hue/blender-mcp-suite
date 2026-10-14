"""
Test client to verify daemon prototype
"""
import socket
import json
import sys
import time

HOST = "127.0.0.1"
PORT = 9989

def run_test():
    print(f"Connecting to {HOST}:{PORT}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    s.connect((HOST, PORT))
    print("Connected!")

    # 1. Ping
    print("\n--- Testing Ping ---")
    s.sendall(json.dumps({"type": "ping"}).encode("utf-8") + b"\n")
    data = s.recv(4096).decode("utf-8")
    print("Ping response:", data.strip())
    assert "pong" in data
    assert "4.1.1" in data

    # 2. Execute Code
    print("\n--- Testing execute_code ---")
    code_req = {
        "type": "execute_code",
        "params": {
            "code": "print('Hello from Blender stdout'); result = {'objects': [o.name for o in bpy.data.objects], 'version': bpy.app.version_string}",
            "strict_json": True
        }
    }
    s.sendall(json.dumps(code_req).encode("utf-8") + b"\n")
    data = s.recv(4096).decode("utf-8")
    print("Execute response:", data.strip())
    assert "Hello from Blender stdout" in data
    assert "Cube" in data or "objects" in data

    # 3. Shutdown
    print("\n--- Testing shutdown ---")
    s.sendall(json.dumps({"type": "shutdown"}).encode("utf-8") + b"\n")
    data = s.recv(4096).decode("utf-8")
    print("Shutdown response:", data.strip())
    assert "success" in data

    s.close()
    print("\n[+] All tests passed successfully!")

if __name__ == "__main__":
    run_test()
