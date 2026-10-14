"""
src/blender_mcp/tools/__init__.py — Full-Spectrum 3D MCP Tools Suite

Exports:
- Bridge operation executor and client accessor.
- 20 Core 3D MCP Tools across 5 Categories + Fallback Script Runner.
- `register_all_tools(server: FastMCP)` auto-registration helper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from blender_mcp.error_boundary import (
    ArmatureRiggingError,
    BlenderDaemonError,
    BlenderMCPError,
    HierarchyCycleError,
    InternalError,
    InvalidParamsError,
    LightingCameraError,
    MaterialShaderError,
    MethodNotFoundError,
    ObjectNotFoundError,
    RenderEngineError,
    ScriptSyntaxError,
    ViewportCaptureError,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = Path(__file__).resolve().parents[2]
BRIDGE_DIR = Path(__file__).resolve().parents[1] / "bridge_scripts"

_active_client: Optional[Any] = None


def set_client(client: Optional[Any]) -> None:
    """Set the active BlenderSocketClient instance for tool operations."""
    global _active_client
    _active_client = client


def get_client() -> Any:
    """Get or auto-initialize the active BlenderSocketClient instance."""
    global _active_client
    if _active_client is not None:
        return _active_client
    from blender_mcp.server import get_active_client
    return get_active_client()


def execute_bridge_op(op_name: str, params: Dict[str, Any], client: Optional[Any] = None) -> Any:
    """
    Executes a named 3D operation inside the Blender process via BlenderSocketClient.
    Translates daemon JSON responses and maps structured errors to domain exceptions.
    """
    c = client or get_client()
    if c is None:
        raise BlenderDaemonError("No active Blender socket client available.")

    bridge_dir = str(BRIDGE_DIR)
    code = f"""
import sys
bridge_dir = {repr(bridge_dir)}
if bridge_dir not in sys.path:
    sys.path.insert(0, bridge_dir)
import blender_ops
result = blender_ops.dispatch_op({repr(op_name)}, {repr(params)})
"""
    try:
        resp = c.send_command({"type": "execute_code", "params": {"code": code}})
    except Exception as e:
        raise BlenderDaemonError(f"Socket communication failed during '{op_name}': {e}") from e

    if not isinstance(resp, dict):
        raise InternalError(f"Invalid non-dict response received from Blender daemon: {resp}")

    if resp.get("status") == "error":
        err_code = resp.get("error_code", -32000)
        err_msg = resp.get("message", f"Execution of '{op_name}' failed.")
        err_details = resp.get("details", {})
        _raise_mapped_exception(err_code, err_msg, err_details)

    result = resp.get("result")
    if isinstance(result, dict) and result.get("status") == "error":
        err_code = result.get("error_code", -32603)
        err_msg = result.get("message", f"Operation '{op_name}' returned error.")
        err_details = result.get("details", {})
        _raise_mapped_exception(err_code, err_msg, err_details)

    return result


def _raise_mapped_exception(code: int, msg: str, details: Dict[str, Any]) -> None:
    code_map = {
        -32000: BlenderDaemonError,
        -32001: ObjectNotFoundError,
        -32002: MaterialShaderError,
        -32003: ArmatureRiggingError,
        -32004: LightingCameraError,
        -32005: RenderEngineError,
        -32006: ViewportCaptureError,
        -32007: ScriptSyntaxError,
        -32602: InvalidParamsError,
    }
    exc_cls = code_map.get(code, BlenderMCPError)
    raise exc_cls(msg, code=code, details=details)


# Deferred imports of tool functions from submodules
from blender_mcp.tools.scene import (
    blender_get_object_info,
    blender_get_scene_info,
    blender_manage_hierarchy,
    blender_manage_object,
    blender_transform_object,
)
from blender_mcp.tools.material import (
    blender_assign_material,
    blender_configure_pbr,
    blender_create_material,
    blender_set_emission,
    blender_set_pbr_textures,
)
from blender_mcp.tools.rigging import (
    blender_bind_skin_weights,
    blender_create_armature,
    blender_setup_ik_constraint,
)
from blender_mcp.tools.lighting_camera import (
    blender_camera_track_to,
    blender_setup_camera,
    blender_setup_light,
    blender_setup_world_hdri,
)
from blender_mcp.tools.render_viewport import (
    blender_configure_render_engine,
    blender_execute_code,
    blender_get_viewport_screenshot,
    blender_render_frame,
)

__all__ = [
    "set_client",
    "get_client",
    "execute_bridge_op",
    # Scene
    "blender_manage_object",
    "blender_transform_object",
    "blender_manage_hierarchy",
    "blender_get_scene_info",
    "blender_get_object_info",
    # Material
    "blender_create_material",
    "blender_assign_material",
    "blender_configure_pbr",
    "blender_set_pbr_textures",
    "blender_set_emission",
    # Rigging
    "blender_create_armature",
    "blender_bind_skin_weights",
    "blender_setup_ik_constraint",
    # Lighting & Camera
    "blender_setup_light",
    "blender_setup_world_hdri",
    "blender_setup_camera",
    "blender_camera_track_to",
    # Render & Viewport
    "blender_configure_render_engine",
    "blender_render_frame",
    "blender_get_viewport_screenshot",
    "blender_execute_code",
    # Registration
    "register_all_tools",
]


def register_all_tools(server: FastMCP) -> None:
    """Register all 20 3D tools + fallback code executor with FastMCP."""
    tools = [
        blender_manage_object,
        blender_transform_object,
        blender_manage_hierarchy,
        blender_get_scene_info,
        blender_get_object_info,
        blender_create_material,
        blender_assign_material,
        blender_configure_pbr,
        blender_set_pbr_textures,
        blender_set_emission,
        blender_create_armature,
        blender_bind_skin_weights,
        blender_setup_ik_constraint,
        blender_setup_light,
        blender_setup_world_hdri,
        blender_setup_camera,
        blender_camera_track_to,
        blender_configure_render_engine,
        blender_render_frame,
        blender_get_viewport_screenshot,
        blender_execute_code,
    ]
    for tool_fn in tools:
        server.add_tool(tool_fn)
