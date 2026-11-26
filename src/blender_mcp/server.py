"""
src/blender_mcp/server.py — Production-Grade Blender MCP Server

Features:
1. FastMCP Server hosting the complete 3D MCP tools suite.
2. Automatic daemon discovery & headless daemon spawning via DaemonManager.
3. Resilient socket auto-recovery (< 3s) via BlenderSocketClient.
4. Clean stdio JSON-RPC transport for AI client connectivity (Antigravity, Cursor, Claude Desktop).
"""

from __future__ import annotations

import argparse
import atexit
import logging
import os
import sys
import threading
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from blender_mcp.daemon_manager import DaemonManager
from blender_mcp.socket_client import BlenderSocketClient
from blender_mcp.tools import register_all_tools, set_client

logger = logging.getLogger("blender_mcp.server")

# Environment and default configurations
DEFAULT_HOST: str = os.environ.get("BLENDER_HOST", "127.0.0.1")
DEFAULT_PORT: int = int(os.environ.get("BLENDER_PORT", "9876"))

# Initialize FastMCP Server
mcp = FastMCP(
    name="Blender MCP Server",
    instructions="Comprehensive 3D MCP Server for Blender 4.1+ enabling automated modeling, PBR materials, rigging, lighting, and rendering.",
)

# Shared lifecycle singletons
_daemon_manager: Optional[DaemonManager] = None
_socket_client: Optional[BlenderSocketClient] = None
_server_lock = threading.Lock()


def get_active_daemon_manager(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> DaemonManager:
    """Get or create singleton DaemonManager."""
    global _daemon_manager
    with _server_lock:
        if _daemon_manager is None:
            _daemon_manager = DaemonManager(host=host, port=port)
        return _daemon_manager


def get_active_client(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> BlenderSocketClient:
    """
    Get or create singleton BlenderSocketClient.
    Ensures Blender daemon is running (auto-attaches or spawns headless).
    """
    global _socket_client
    with _server_lock:
        if _socket_client is None:
            dm = get_active_daemon_manager(host=host, port=port)
            # Ensure daemon is active before socket connection
            dm.ensure_daemon_running()

            client = BlenderSocketClient(
                host=host,
                port=port,
                daemon_manager=dm,
            )
            client.connect()
            _socket_client = client
            set_client(client)
            logger.info("BlenderSocketClient initialized and connected to %s:%s", host, port)
        else:
            if not _socket_client.is_connected:
                _socket_client.connect()

        return _socket_client


def shutdown_server() -> None:
    """Graceful cleanup hook on server termination."""
    global _socket_client, _daemon_manager
    with _server_lock:
        if _socket_client is not None:
            try:
                _socket_client.disconnect()
            except Exception:
                pass
            _socket_client = None

        if _daemon_manager is not None:
            try:
                _daemon_manager.shutdown()
            except Exception:
                pass
            _daemon_manager = None


atexit.register(shutdown_server)

# Register all 20 3D MCP tools + fallback code execution tool
register_all_tools(mcp)


def main() -> None:
    """CLI entry point for running the Blender MCP Server."""
    parser = argparse.ArgumentParser(description="Blender Model Context Protocol (MCP) Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Blender daemon host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Blender daemon port (default: 9876)")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse"], help="MCP transport (default: stdio)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    logger.info("Starting Blender MCP Server on transport '%s' (targeting Blender on %s:%d)...", args.transport, args.host, args.port)

    # Pre-flight daemon check in background or on first tool call
    if os.environ.get("BLENDER_SKIP_PREFLIGHT", "").strip().lower() not in ("1", "true", "yes"):
        try:
            dm = get_active_daemon_manager(host=args.host, port=args.port)
            dm.ensure_daemon_running()
            get_active_client(host=args.host, port=args.port)
            logger.info("Blender daemon ready and verified.")
        except Exception as e:
            logger.warning("Blender daemon pre-flight check deferred: %s", e)

    # Run MCP server
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.run(transport="sse")


if __name__ == "__main__":
    main()
