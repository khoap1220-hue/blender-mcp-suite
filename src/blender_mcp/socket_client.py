"""
src/blender_mcp/socket_client.py
Resilient TCP Socket Client for Blender MCP communication.

Features:
- Newline (\\n) framed JSON-RPC transport with 16KB chunk buffer accumulator.
- Fast non-blocking healthcheck probe ping() with 2s timeout and metadata.
- Auto-recovery with exponential backoff [0.1, 0.2, 0.4, 0.8] (< 3.0s target).
- Integrated DaemonManager respawn notification hook for dead process recovery.
- Seamless command retry without exposing raw socket exceptions to AI clients.
- Thread-safe serialization with re-entrant lock (threading.RLock).
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("blender_mcp.socket_client")

# Defaults and Constants
DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 9876
DEFAULT_COMMAND_TIMEOUT: float = 30.0
DEFAULT_PING_TIMEOUT: float = 2.0
DEFAULT_CONNECT_TIMEOUT: float = 2.0
DEFAULT_BACKOFF_DELAYS: Tuple[float, ...] = (0.1, 0.2, 0.4, 0.8)
MAX_BUFFER_SIZE_BYTES: int = 64 * 1024 * 1024  # 64 MB guard
RECV_CHUNK_SIZE: int = 16384  # 16 KB chunks


class BlenderSocketError(Exception):
    """Base exception for all Blender MCP socket communication failures."""
    pass


class BlenderConnectionError(BlenderSocketError):
    """Raised when connection cannot be established or re-established after retries."""
    pass


class BlenderTimeoutError(BlenderSocketError):
    """Raised when an operation exceeds its configured timeout deadline."""
    pass


class BlenderProtocolError(BlenderSocketError):
    """Raised when framing or JSON payload decoding encounters fatal corruption."""
    pass


class BlenderSocketClient:
    """
    Resilient, thread-safe TCP socket client for communicating with the Blender daemon.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        command_timeout: float = DEFAULT_COMMAND_TIMEOUT,
        ping_timeout: float = DEFAULT_PING_TIMEOUT,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        backoff_delays: Tuple[float, ...] = DEFAULT_BACKOFF_DELAYS,
        daemon_manager: Optional[Any] = None,
        custom_logger: Optional[logging.Logger] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.command_timeout = command_timeout
        self.ping_timeout = ping_timeout
        self.connect_timeout = connect_timeout
        self.backoff_delays = list(backoff_delays)
        self.daemon_manager = daemon_manager
        self.logger = custom_logger or logger

        self._sock: Optional[socket.socket] = None
        self._recv_buffer: bytearray = bytearray()
        self._lock: threading.RLock = threading.RLock()
        self._is_connected: bool = False

    @property
    def is_connected(self) -> bool:
        """Return cached connection status."""
        with self._lock:
            return self._is_connected and self._sock is not None

    def connect(self, timeout: Optional[float] = None) -> bool:
        """
        Explicitly open TCP connection to the Blender daemon.
        Thread-safe. Returns True on success, raises BlenderConnectionError on failure.
        """
        with self._lock:
            return self._connect_locked(timeout=timeout or self.connect_timeout)

    def _connect_locked(self, timeout: float) -> bool:
        """Internal connect helper. Must be called while holding self._lock."""
        self._disconnect_locked()

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Low-latency configuration: disable Nagle's algorithm
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            # Enable TCP keepalive for persistent session health
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            s.settimeout(timeout)

            self.logger.debug("Connecting to Blender daemon at %s:%d (timeout=%.1fs)...", self.host, self.port, timeout)
            s.connect((self.host, self.port))

            self._sock = s
            self._is_connected = True
            self._recv_buffer.clear()
            self.logger.info("Connected successfully to Blender daemon at %s:%d", self.host, self.port)
            return True

        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            self._disconnect_locked()
            raise BlenderConnectionError(f"Failed to connect to Blender daemon at {self.host}:{self.port}: {e}") from e

    def disconnect(self) -> None:
        """Close current socket connection and release resources. Thread-safe."""
        with self._lock:
            self._disconnect_locked()

    def _disconnect_locked(self) -> None:
        """Internal disconnect helper. Must be called while holding self._lock."""
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        self._is_connected = False
        self._recv_buffer.clear()

    def ping(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Fast healthcheck probe verifying liveness, version, and PID.
        Does not execute multi-stage backoff; returns rich diagnostics within timeout.
        """
        effective_timeout = timeout or self.ping_timeout
        start_time = time.perf_counter()

        with self._lock:
            try:
                # Ensure connection is established
                if not self.is_connected:
                    self._connect_locked(timeout=effective_timeout)

                # Send ping command without auto-reconnect to ensure strict fast timeout
                resp = self._send_and_receive_locked({"type": "ping"}, timeout=effective_timeout)
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                result = resp.get("result", {})
                version = result.get("version") or result.get("blender_version")
                pid = result.get("pid")
                pong = result.get("pong", True)

                return {
                    "alive": True,
                    "pong": pong,
                    "version": version,
                    "pid": pid,
                    "latency_ms": round(latency_ms, 2),
                    "error": None,
                }

            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                self.logger.warning("Ping probe failed against %s:%d (%.1f ms): %s", self.host, self.port, latency_ms, e)
                self._disconnect_locked()
                return {
                    "alive": False,
                    "pong": False,
                    "version": None,
                    "pid": None,
                    "latency_ms": round(latency_ms, 2),
                    "error": str(e),
                }

    def is_alive(self, timeout: Optional[float] = None) -> bool:
        """Convenience helper returning simple boolean liveness status."""
        return bool(self.ping(timeout=timeout).get("alive", False))

    def send_command(
        self,
        command: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Send a JSON command to the Blender daemon and receive structured response.
        
        Thread-safe. Automatically recovers broken connections with exponential
        backoff [0.1, 0.2, 0.4, 0.8] and seamlessly retries the command.
        """
        effective_timeout = timeout or self.command_timeout

        with self._lock:
            # 1. Establish connection if not currently open
            if not self.is_connected:
                self._recover_connection_locked(trigger_error=BlenderConnectionError("Not currently connected"))

            # 2. Attempt send and receive with seamless auto-recovery on disconnect
            try:
                return self._send_and_receive_locked(command, timeout=effective_timeout)
            except (ConnectionResetError, BrokenPipeError, ConnectionRefusedError, socket.timeout, EOFError, OSError) as e:
                self.logger.warning(
                    "Socket severed during command '%s' (%s). Triggering auto-recovery (< 3s)...",
                    command.get("type", "unknown"),
                    e,
                )
                # Initiate exponential backoff auto-recovery
                self._recover_connection_locked(trigger_error=e)
                self.logger.info("Auto-recovery successful. Retrying original command seamlessly...")
                # Seamless retry of the failed command
                return self._send_and_receive_locked(command, timeout=effective_timeout)

    def _send_and_receive_locked(self, command: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        """Send command and read framed response. Must be called while holding self._lock."""
        if self._sock is None:
            raise BlenderConnectionError("Cannot send command: socket is not connected.")

        # Serialize payload with newline delimiter
        try:
            payload_str = json.dumps(command, ensure_ascii=False) + "\n"
            payload_bytes = payload_str.encode("utf-8")
        except (TypeError, ValueError) as e:
            raise BlenderProtocolError(f"Command payload serialization failed: {e}") from e

        # Configure socket timeout
        self._sock.settimeout(timeout)

        # Transmit request
        try:
            self._sock.sendall(payload_bytes)
        except socket.timeout as e:
            raise BlenderTimeoutError(f"Socket send timed out after {timeout:.1f}s") from e
        except OSError as e:
            raise ConnectionResetError(f"Socket send failed: {e}") from e

        # Receive framed response
        return self._recv_framed_locked(timeout=timeout)

    def _recv_framed_locked(self, timeout: float) -> Dict[str, Any]:
        """Accumulate bytes and parse delimiter-separated JSON frame."""
        assert self._sock is not None
        self._sock.settimeout(timeout)

        while True:
            # Check if complete frame already exists in buffer
            # Check for \n (primary) or \0 (legacy bridge fallback)
            newline_idx = self._recv_buffer.find(b"\n")
            null_idx = self._recv_buffer.find(b"\0")

            split_pos = -1
            if newline_idx != -1 and null_idx != -1:
                split_pos = min(newline_idx, null_idx)
            elif newline_idx != -1:
                split_pos = newline_idx
            elif null_idx != -1:
                split_pos = null_idx

            if split_pos != -1:
                raw_frame = bytes(self._recv_buffer[:split_pos])
                # Consume frame and delimiter
                del self._recv_buffer[:split_pos + 1]

                raw_frame_str = raw_frame.strip().decode("utf-8", errors="replace")
                if not raw_frame_str:
                    # Blank line between frames, continue parsing
                    continue

                try:
                    parsed = json.loads(raw_frame_str)
                    if isinstance(parsed, dict):
                        return parsed
                    return {"status": "success", "result": parsed}
                except json.JSONDecodeError as e:
                    self.logger.error("JSON decode error on frame: %r", raw_frame_str[:200])
                    raise BlenderProtocolError(f"Malformed JSON frame received: {e}") from e

            # Read next chunk from network
            try:
                chunk = self._sock.recv(RECV_CHUNK_SIZE)
            except socket.timeout as e:
                raise BlenderTimeoutError(f"Socket receive timed out after {timeout:.1f}s") from e
            except OSError as e:
                raise ConnectionResetError(f"Socket receive failed: {e}") from e

            if not chunk:
                # 0 bytes received indicates remote endpoint closed TCP connection (EOF)
                raise EOFError("Remote Blender daemon closed the TCP connection (0 bytes received).")

            self._recv_buffer.extend(chunk)

            # Prevent runaway buffer consumption
            if len(self._recv_buffer) > MAX_BUFFER_SIZE_BYTES:
                self._recv_buffer.clear()
                raise BlenderProtocolError(f"Receive buffer exceeded maximum safe limit of {MAX_BUFFER_SIZE_BYTES} bytes.")

    def _recover_connection_locked(self, trigger_error: Exception) -> None:
        """
        Execute exponential backoff reconnection loop [0.1, 0.2, 0.4, 0.8].
        Total sleep is ~1.5s, well within the 3.0s acceptance limit.
        Invokes DaemonManager respawn hook if daemon process terminated.
        """
        self._disconnect_locked()
        total_backoff = sum(self.backoff_delays)
        self.logger.info(
            "Commencing auto-recovery loop across %d attempts (delays: %s, total backoff: %.1fs)...",
            len(self.backoff_delays),
            self.backoff_delays,
            total_backoff,
        )

        last_err: Optional[Exception] = trigger_error

        for attempt, delay in enumerate(self.backoff_delays, start=1):
            # Check daemon status and notify DaemonManager to respawn if dead
            if self.daemon_manager is not None:
                is_running_fn = getattr(self.daemon_manager, "is_running", None)
                if callable(is_running_fn) and not is_running_fn():
                    self.logger.warning("Blender daemon process died. Notifying DaemonManager to respawn...")
                    ensure_running_fn = (
                        getattr(self.daemon_manager, "ensure_daemon_running", None)
                        or getattr(self.daemon_manager, "start_daemon", None)
                    )
                    if callable(ensure_running_fn):
                        try:
                            ensure_running_fn()
                        except Exception as de:
                            self.logger.error("DaemonManager failed to respawn daemon: %s", de)

            # Wait exponential backoff delay
            time.sleep(delay)

            # Attempt connection
            try:
                self.logger.debug("Recovery attempt %d/%d (connecting with timeout=%.1fs)...", attempt, len(self.backoff_delays), self.connect_timeout)
                self._connect_locked(timeout=self.connect_timeout)
                self.logger.info("Auto-recovery successful on attempt %d/%d!", attempt, len(self.backoff_delays))
                return
            except (BlenderConnectionError, OSError) as err:
                last_err = err
                self.logger.debug("Recovery attempt %d failed: %s", attempt, err)

        # If all attempts exhausted, raise structured domain exception
        raise BlenderConnectionError(
            f"Failed to recover connection to Blender daemon at {self.host}:{self.port} "
            f"after {len(self.backoff_delays)} attempts (total wait: {total_backoff:.1f}s). "
            f"Final error: {last_err}"
        ) from last_err

    def __enter__(self) -> BlenderSocketClient:
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()
