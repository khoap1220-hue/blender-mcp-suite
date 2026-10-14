"""
Comprehensive PoC for Blender MCP Daemon and Client Handshake
"""
import sys
import socket
import json
import os
import select
import time
import io
import contextlib
import traceback
import argparse

# When run directly inside Blender as daemon:
def run_daemon(host="127.0.0.1", port=9989):
    import bpy
    
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_sock.bind((host, port))
    server_sock.listen(10)
    server_sock.setblocking(False)

    print(f"[BLENDER_MCP_DAEMON_READY:{port}]", flush=True)

    client_states = {}  # sock: {"buffer": bytearray(), "addr": addr}
    running = True

    # Shared execution globals for bpy operations
    import mathutils
    exec_globals = {
        "bpy": bpy,
        "mathutils": mathutils,
        "sys": sys,
        "os": os,
        "json": json,
    }

    def handle_request(req):
        cmd_type = req.get("type", "")
        params = req.get("params", {})
        
        if cmd_type == "ping":
            return {
                "status": "success",
                "result": {
                    "pong": True,
                    "version": bpy.app.version_string,
                    "pid": os.getpid()
                }
            }
        
        elif cmd_type in ("execute_code", "execute"):
            code = params.get("code") or req.get("code") or ""
            strict_json = params.get("strict_json", req.get("strict_json", False))
            
            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            
            exec_namespace = exec_globals.copy()
            exec_namespace["result"] = None
            
            try:
                with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                    exec(code, exec_namespace)
                
                result_val = exec_namespace.get("result")
                out_str = stdout_buf.getvalue()
                err_str = stderr_buf.getvalue()
                
                # Test serializability
                try:
                    json.dumps(result_val)
                except (TypeError, OverflowError):
                    if strict_json:
                        return {
                            "status": "error",
                            "error_code": -32602,
                            "error_type": "SERIALIZATION_ERROR",
                            "message": f"Result of type {type(result_val).__name__} is not JSON-serializable under strict_json=True",
                            "stdout": out_str,
                            "stderr": err_str
                        }
                    result_val = str(result_val)
                
                return {
                    "status": "success",
                    "result": result_val,
                    "stdout": out_str,
                    "stderr": err_str
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error_code": -32000,
                    "error_type": "EXECUTION_ERROR",
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                    "stdout": stdout_buf.getvalue(),
                    "stderr": stderr_buf.getvalue()
                }
                
        elif cmd_type == "shutdown":
            return {
                "status": "success",
                "result": {"message": "Shutting down Blender daemon cleanly"}
            }
        else:
            return {
                "status": "error",
                "error_code": -32601,
                "error_type": "METHOD_NOT_FOUND",
                "message": f"Unknown command type: {cmd_type}"
            }

    try:
        while running:
            read_sockets = [server_sock] + list(client_states.keys())
            readable, _, exceptional = select.select(read_sockets, [], read_sockets, 0.05)

            for sock in exceptional:
                if sock in client_states:
                    del client_states[sock]
                sock.close()

            for sock in readable:
                if sock is server_sock:
                    try:
                        conn, addr = server_sock.accept()
                        conn.setblocking(False)
                        client_states[conn] = {"buffer": bytearray(), "addr": addr}
                    except Exception:
                        pass
                else:
                    state = client_states[sock]
                    try:
                        chunk = sock.recv(65536)
                        if not chunk:
                            # Client disconnected
                            del client_states[sock]
                            sock.close()
                            continue
                        state["buffer"].extend(chunk)
                    except (ConnectionResetError, ConnectionAbortedError):
                        del client_states[sock]
                        sock.close()
                        continue

                    # Process buffer
                    buf = state["buffer"]
                    while buf:
                        # Check delimiter: \n or \0
                        msg_bytes = None
                        delim_idx = -1
                        for idx, b in enumerate(buf):
                            if b == 10 or b == 0:  # \n or \0
                                delim_idx = idx
                                break
                        
                        if delim_idx != -1:
                            msg_bytes = buf[:delim_idx]
                            del buf[:delim_idx + 1]
                            raw_str = msg_bytes.decode("utf-8", errors="replace").strip()
                            if not raw_str:
                                continue
                            try:
                                req = json.loads(raw_str)
                            except json.JSONDecodeError as e:
                                err_resp = {
                                    "status": "error",
                                    "error_code": -32700,
                                    "message": f"Parse error: {e}"
                                }
                                sock.sendall((json.dumps(err_resp) + "\n").encode("utf-8"))
                                continue
                        else:
                            # No delimiter found yet, try raw JSON parse if complete
                            raw_str = buf.decode("utf-8", errors="replace").strip()
                            try:
                                dec = json.JSONDecoder()
                                req, end_idx = dec.raw_decode(raw_str)
                                del buf[:end_idx]
                            except json.JSONDecodeError:
                                # Incomplete payload, await more chunks
                                break

                        # Execute request
                        resp = handle_request(req)
                        resp_bytes = (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")
                        try:
                            sock.sendall(resp_bytes)
                        except Exception:
                            pass

                        if req.get("type") == "shutdown":
                            running = False
                            break
    finally:
        for s in list(client_states.keys()):
            try:
                s.close()
            except Exception:
                pass
        server_sock.close()
        print("[BLENDER_MCP_DAEMON_SHUTDOWN]", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9989)
    
    # In Blender headless, args after '--' are custom
    argv = sys.argv
    if "--" in argv:
        args_to_parse = argv[argv.index("--") + 1:]
    else:
        args_to_parse = []
        
    args = parser.parse_args(args_to_parse)
    run_daemon(host=args.host, port=args.port)
