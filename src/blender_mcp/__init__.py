"""
src/blender_mcp/__init__.py
Blender MCP Package root.
"""
from blender_mcp.daemon_manager import (
    BlenderBinaryDetector,
    DaemonManager,
    WindowsJobObject,
    BlenderManagerError,
    BlenderNotFoundError,
    BlenderVersionError,
    BlenderStartupError,
    BlenderJobObjectError,
)
from blender_mcp.socket_client import (
    BlenderSocketClient,
    BlenderSocketError,
    BlenderConnectionError,
    BlenderTimeoutError,
    BlenderProtocolError,
)

__version__ = "1.0.0"

__all__ = [
    "BlenderBinaryDetector",
    "DaemonManager",
    "WindowsJobObject",
    "BlenderManagerError",
    "BlenderNotFoundError",
    "BlenderVersionError",
    "BlenderStartupError",
    "BlenderJobObjectError",
    "BlenderSocketClient",
    "BlenderSocketError",
    "BlenderConnectionError",
    "BlenderTimeoutError",
    "BlenderProtocolError",
]
