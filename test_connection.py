"""
test_connection.py — Quick test script to verify Blender MCP socket connection.
"""

import socket
import json
import time

HOST = "127.0.0.1"
PORT = 9876

def test_blender_socket():
    print(f"[*] Testing connection to Blender MCP socket on {HOST}:{PORT}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    try:
        s.connect((HOST, PORT))
        print("[+] SUCCESS: Connected to Blender MCP socket on port 9876!")
        
        # 1. Test ping
        ping_payload = json.dumps({"type": "ping"})
        s.sendall(ping_payload.encode("utf-8"))
        
        data = s.recv(4096)
        if data:
            resp = json.loads(data.decode("utf-8"))
            print("[+] Ping response:", json.dumps(resp))
        else:
            print("[-] No data received for ping.")
            
        # 2. Test execute_code
        exec_payload = json.dumps({
            "type": "execute_code",
            "params": {"code": "result = {'version': bpy.app.version_string, 'objects': [o.name for o in bpy.data.objects]}"}
        })
        s.sendall(exec_payload.encode("utf-8"))
        data = s.recv(4096)
        if data:
            resp = json.loads(data.decode("utf-8"))
            print("[+] Scene info from Blender:", json.dumps(resp, indent=2))
        else:
            print("[-] No data received for execute_code.")
            
    except ConnectionRefusedError:
        print(f"[-] FAILED: Could not connect to {HOST}:{PORT}.")
        print("    Ensure Blender is open with GUI and the MCP Server is started.")
    except socket.timeout:
        print("[-] FAILED: Connection timed out.")
    except Exception as e:
        print(f"[-] Error: {e}")
    finally:
        s.close()

if __name__ == "__main__":
    test_blender_socket()
