"""
daemon/blender_mcp_daemon.py — Production-Grade Blender MCP Headless Daemon

Architected for Blender 4.1+ on Windows.
Runs inside Blender via:
    blender.exe --background --python daemon/blender_mcp_daemon.py -- --host 127.0.0.1 --port 9876

Key Architectural Highlights:
1. Main-Thread Event Pump:
   Bypasses `bpy.app.timers` (which does NOT fire in Blender headless background mode).
   Drives socket polling and message dispatch directly on the main thread via non-blocking
   `select.select()`, ensuring 100% thread safety for all `bpy` and `mathutils` operations.
2. Windows Exclusive Port Binding:
   Enforces `SO_EXCLUSIVEADDRUSE` on Windows (fallback to `SO_REUSEADDR` elsewhere) on `127.0.0.1`
   to prevent port hijacking, eliminate Windows Firewall prompts, and fail fast on conflicts.
3. Universal Protocol Framing:
   Transparently decodes `\n`-delimited JSON, `\0`-delimited JSON (Blender Lab bridge),
   and self-delimited raw JSON streams via `json.JSONDecoder.raw_decode`.
4. Command Handlers:
   - ping: Returns liveness status, Blender version, and PID.
   - execute_code: Executes script in isolated namespace, captures stdout/stderr,
     retrieves `result` variable, and serializes Blender mathutils/ID types.
   - shutdown: Flushes response, releases sockets, and triggers clean Blender exit.
5. Readiness Sentinel:
   Emits `[BLENDER_MCP_DAEMON_READY:<port>]` to stdout immediately upon socket bind.
"""

import argparse
import atexit
import contextlib
import errno
import io
import json
import os
import select
import signal
import socket
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

try:
    import bpy
    import mathutils
except ImportError:
    try:
        import mock_bpy as bpy
        import mock_bpy as mathutils
        sys.modules["bpy"] = bpy
        sys.modules["mathutils"] = mathutils
    except Exception:
        bpy = None  # type: ignore
        mathutils = None  # type: ignore


class BlenderJSONEncoder(json.JSONEncoder):
    """
    JSON encoder that seamlessly handles Blender mathutils, vectors, matrices,
    quaternions, colors, and basic ID object references when strict_json is False.
    """

    def default(self, obj: Any) -> Any:
        if mathutils is not None:
            if isinstance(obj, (mathutils.Vector, mathutils.Euler, mathutils.Color)):
                return list(obj)
            if isinstance(obj, mathutils.Matrix):
                return [list(row) for row in obj]
            if isinstance(obj, mathutils.Quaternion):
                return list(obj)

        if hasattr(obj, "to_dict") and callable(obj.to_dict):
            return obj.to_dict()

        if hasattr(obj, "to_list") and callable(obj.to_list):
            return obj.to_list()

        # Handle bpy_prop_array (e.g. obj.location, color arrays)
        if obj.__class__.__name__ == "bpy_prop_array":
            return list(obj)

        # Handle Blender ID objects (Object, Material, Mesh, etc.)
        if hasattr(obj, "name") and hasattr(obj, "rna_type"):
            return {
                "name": getattr(obj, "name", "unknown"),
                "type": getattr(obj, "type", obj.rna_type.name),
            }

        # Handle sets, deques, generators
        if isinstance(obj, (set, frozenset)):
            return list(obj)

        return super().default(obj)


class BlenderMCPDaemon:
    """
    Headless TCP daemon hosting the Blender MCP socket service on the main thread.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9876,
        select_timeout: float = 0.02,
        max_buffer_bytes: int = 67108864,  # 64 MB
    ):
        self.host = host
        self.port = port
        self.select_timeout = select_timeout
        self.max_buffer_bytes = max_buffer_bytes

        self.server_sock: Optional[socket.socket] = None
        self.client_states: Dict[socket.socket, Dict[str, Any]] = {}
        self.running: bool = False

        # Persistent execution namespace on main thread
        self.exec_globals: Dict[str, Any] = {
            "bpy": bpy,
            "mathutils": mathutils,
            "sys": sys,
            "os": os,
            "json": json,
            "time": time,
        }

    def setup_socket(self) -> None:
        """
        Creates and binds server socket with SO_EXCLUSIVEADDRUSE on Windows.
        """
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Windows-specific socket hardening
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError as e:
                print(f"[BLENDER_MCP_DAEMON_WARN] Could not set SO_EXCLUSIVEADDRUSE: {e}", file=sys.stderr)
                self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        else:
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.server_sock.bind((self.host, self.port))
        except OSError as e:
            if e.errno in (errno.EADDRINUSE, 10048):  # WSAEADDRINUSE
                print(
                    f"[BLENDER_MCP_DAEMON_ERROR] Port {self.host}:{self.port} is already in use. "
                    "Another Blender session or daemon is holding the exclusive port.",
                    file=sys.stderr,
                    flush=True,
                )
                sys.exit(2)
            raise

        self.server_sock.listen(16)
        self.server_sock.setblocking(False)

        # Register cleanup on abnormal exit
        atexit.register(self.cleanup)

    def cleanup(self) -> None:
        """
        Closes all active client connections and server listener.
        """
        for sock in list(self.client_states.keys()):
            try:
                sock.close()
            except Exception:
                pass
        self.client_states.clear()

        if self.server_sock is not None:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None

    def handle_signal(self, signum: int, frame: Any) -> None:
        """
        Signal handler for clean shutdown on SIGINT / SIGTERM.
        """
        print(f"\n[BLENDER_MCP_DAEMON] Caught signal {signum}, initiating graceful shutdown...", flush=True)
        self.running = False

    def handle_ping(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles ping request: returns status, Blender version, and PID.
        """
        if bpy is not None:
            version_str = bpy.app.version_string
            version_tuple = list(bpy.app.version)
        else:
            version_str = os.environ.get("BLENDER_VERSION", "4.1.1")
            version_tuple = [4, 1, 1]
        return {
            "status": "success",
            "result": {
                "pong": True,
                "version": version_str,
                "version_tuple": version_tuple,
                "pid": os.getpid(),
                "background": bpy.app.background if bpy is not None else True,
            },
        }

    def handle_execute_code(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes arbitrary Python code safely on the main thread inside Blender.
        Captures stdout and stderr, extracts `result` namespace variable,
        and serializes return structure.
        """
        params = req.get("params", {})
        code = params.get("code") or req.get("code") or ""
        strict_json = params.get("strict_json", req.get("strict_json", False))

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # Build fresh local execution namespace derived from global base
        exec_namespace = self.exec_globals.copy()
        exec_namespace["result"] = None

        try:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                exec(code, exec_namespace)

            result_val = exec_namespace.get("result")
            out_str = stdout_buf.getvalue()
            err_str = stderr_buf.getvalue()

            # Verify and serialize result
            if strict_json:
                try:
                    # Strict validation: must serialize with standard json encoder
                    json.dumps(result_val)
                except (TypeError, OverflowError) as ser_err:
                    return {
                        "status": "error",
                        "error_code": -32602,
                        "error_type": "SERIALIZATION_ERROR",
                        "message": (
                            f"Result of type '{type(result_val).__name__}' is not JSON-serializable "
                            f"under strict_json=True: {ser_err}"
                        ),
                        "stdout": out_str,
                        "stderr": err_str,
                    }
            else:
                # Permissive serialization using BlenderJSONEncoder
                try:
                    json.dumps(result_val, cls=BlenderJSONEncoder)
                except Exception:
                    result_val = str(result_val)

            return {
                "status": "success",
                "result": result_val,
                "stdout": out_str,
                "stderr": err_str,
            }

        except Exception as exc:
            return {
                "status": "error",
                "error_code": -32000,
                "error_type": "EXECUTION_ERROR",
                "message": str(exc),
                "traceback": traceback.format_exc(),
                "stdout": stdout_buf.getvalue(),
                "stderr": stderr_buf.getvalue(),
            }

    def handle_shutdown(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles daemon shutdown command.
        """
        self.running = False
        return {
            "status": "success",
            "result": {
                "message": "Shutting down Blender daemon cleanly",
                "pid": os.getpid(),
            },
        }

    def dispatch_command(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatches request dictionary to appropriate command handler.
        """
        cmd_type = req.get("type", "")
        if cmd_type == "ping":
            return self.handle_ping(req)
        elif cmd_type in ("execute_code", "execute"):
            return self.handle_execute_code(req)
        elif cmd_type == "shutdown":
            return self.handle_shutdown(req)
        else:
            return {
                "status": "error",
                "error_code": -32601,
                "error_type": "METHOD_NOT_FOUND",
                "message": f"Unknown command type: '{cmd_type}'",
            }

    def process_client_buffer(self, sock: socket.socket) -> List[Tuple[Dict[str, Any], str]]:
        """
        Extracts all complete messages from the client's receive buffer.
        Returns list of tuples: (request_dict, delimiter_style).
        """
        state = self.client_states[sock]
        buf = state["buffer"]
        messages = []

        while buf:
            # Check for explicit line (\n) or null-byte (\0) delimiter
            delim_idx = -1
            delim_char = "\n"
            for idx, byte_val in enumerate(buf):
                if byte_val == 10:  # \n
                    delim_idx = idx
                    delim_char = "\n"
                    break
                elif byte_val == 0:  # \0
                    delim_idx = idx
                    delim_char = "\0"
                    break

            if delim_idx != -1:
                raw_chunk = buf[:delim_idx]
                del buf[: delim_idx + 1]
                raw_str = raw_chunk.decode("utf-8", errors="replace").strip()
                if not raw_str:
                    continue
                try:
                    req = json.loads(raw_str)
                    if isinstance(req, dict):
                        messages.append((req, delim_char))
                except json.JSONDecodeError as err:
                    err_resp = {
                        "status": "error",
                        "error_code": -32700,
                        "error_type": "PARSE_ERROR",
                        "message": f"JSON parse error: {err}",
                    }
                    self.send_response(sock, err_resp, delim_char)
                continue

            # If no delimiter found yet, test raw JSON parsing
            raw_str = buf.decode("utf-8", errors="replace").strip()
            if not raw_str:
                break

            try:
                dec = json.JSONDecoder()
                req, end_idx = dec.raw_decode(raw_str)
                # Count consumed bytes from decoded character index
                consumed_bytes = len(raw_str[:end_idx].encode("utf-8"))
                del buf[:consumed_bytes]
                if isinstance(req, dict):
                    messages.append((req, "\n"))
            except json.JSONDecodeError:
                # Incomplete payload — await further socket chunks
                break

        return messages

    def send_response(self, sock: socket.socket, response: Dict[str, Any], delimiter: str = "\n") -> bool:
        """
        Serializes and transmits response payload over socket.
        Appends delimiter (\n or \0) matching incoming request.
        """
        try:
            payload_str = json.dumps(response, cls=BlenderJSONEncoder, ensure_ascii=False)
            wire_bytes = (payload_str + delimiter).encode("utf-8")
            sock.sendall(wire_bytes)
            return True
        except Exception as e:
            print(f"[BLENDER_MCP_DAEMON_WARN] Error sending response to client: {e}", file=sys.stderr)
            return False

    def run(self) -> None:
        """
        Main execution loop.
        Listens, polls, and processes all events directly on Blender's main thread.
        """
        self.setup_socket()
        self.running = True

        # Hook standard OS signals
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        # Emit readiness sentinel to stdout for parent process synchronisation
        print(f"[BLENDER_MCP_DAEMON_READY:{self.port}]", flush=True)

        try:
            while self.running:
                # Polling list: server listener + all active client sockets
                read_sockets = [self.server_sock] + list(self.client_states.keys())
                try:
                    readable, _, exceptional = select.select(
                        read_sockets, [], read_sockets, self.select_timeout
                    )
                except (select.error, OSError) as sel_err:
                    if not self.running:
                        break
                    print(f"[BLENDER_MCP_DAEMON_WARN] select error: {sel_err}", file=sys.stderr)
                    continue

                # Handle disconnected or faulted sockets
                for sock in exceptional:
                    if sock in self.client_states:
                        del self.client_states[sock]
                    try:
                        sock.close()
                    except Exception:
                        pass

                for sock in readable:
                    if sock is self.server_sock:
                        # Accept new incoming client connection
                        try:
                            conn, addr = self.server_sock.accept()
                            conn.setblocking(False)
                            self.client_states[conn] = {
                                "buffer": bytearray(),
                                "addr": addr,
                                "connected_at": time.time(),
                            }
                        except Exception:
                            pass
                    else:
                        # Read data from existing client connection
                        state = self.client_states.get(sock)
                        if state is None:
                            continue

                        try:
                            chunk = sock.recv(65536)
                            if not chunk:
                                # Client disconnected cleanly (EOF)
                                del self.client_states[sock]
                                sock.close()
                                continue

                            state["buffer"].extend(chunk)

                            # Buffer flood protection
                            if len(state["buffer"]) > self.max_buffer_bytes:
                                print(
                                    f"[BLENDER_MCP_DAEMON_WARN] Buffer overflow from {state['addr']}, dropping connection.",
                                    file=sys.stderr,
                                )
                                del self.client_states[sock]
                                sock.close()
                                continue

                        except (ConnectionResetError, ConnectionAbortedError, OSError):
                            if sock in self.client_states:
                                del self.client_states[sock]
                            try:
                                sock.close()
                            except Exception:
                                pass
                            continue

                        # Drain and execute all complete messages in buffer
                        requests = self.process_client_buffer(sock)
                        for req, delim in requests:
                            # Execute handler directly on main thread
                            resp = self.dispatch_command(req)
                            self.send_response(sock, resp, delim)

                            if req.get("type") == "shutdown":
                                self.running = False
                                break

                        if not self.running:
                            break

        finally:
            self.cleanup()
            print("[BLENDER_MCP_DAEMON_SHUTDOWN]", flush=True)

            # Ensure Blender exits completely in headless mode
            if bpy is not None:
                try:
                    bpy.ops.wm.quit_blender()
                except Exception:
                    pass
            sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Blender MCP Headless Daemon Runner")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9876, help="Port to bind (default: 9876)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.02,
        help="Select loop polling timeout in seconds (default: 0.02 = 20ms)",
    )

    # In Blender CLI, arguments following '--' are passed to Python script
    raw_argv = sys.argv
    if "--" in raw_argv:
        custom_args = raw_argv[raw_argv.index("--") + 1 :]
    else:
        custom_args = []

    args = parser.parse_args(custom_args)

    daemon = BlenderMCPDaemon(host=args.host, port=args.port, select_timeout=args.timeout)
    daemon.run()


if __name__ == "__main__":
    main()
