"""
src/blender_mcp/error_boundary.py — Structured Error Handling & Zero-Crash Boundary

Implements:
1. 13 Standardized JSON-RPC 2.0 & Blender MCP Domain Error Codes (-32700 to -32603, -32000 to -32007).
2. Domain Exception Hierarchy with Diagnostic Envelopes and Intelligent Hints.
3. Zero-Crash `@error_boundary` Decorator returning standardized MCP `CallToolResult` with `isError: True`.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import traceback
from typing import Any, Callable, Dict, List, Optional, Type, Union

try:
    from mcp.types import CallToolResult, ImageContent, TextContent
except ImportError:
    CallToolResult = Any  # type: ignore
    ImageContent = Any  # type: ignore
    TextContent = Any  # type: ignore

logger = logging.getLogger("blender_mcp.error_boundary")

# ==============================================================================
# 1. 13 Standardized JSON-RPC 2.0 & Blender MCP Error Codes
# ==============================================================================

# JSON-RPC 2.0 Standard Error Codes
PARSE_ERROR: int = -32700
INVALID_REQUEST: int = -32600
METHOD_NOT_FOUND: int = -32601
INVALID_PARAMS: int = -32602
INTERNAL_ERROR: int = -32603

# Blender MCP Domain-Specific Error Codes
BLENDER_DAEMON_ERROR: int = -32000
OBJECT_NOT_FOUND: int = -32001
MATERIAL_SHADER_ERROR: int = -32002
ARMATURE_RIGGING_ERROR: int = -32003
LIGHTING_CAMERA_ERROR: int = -32004
RENDER_ENGINE_ERROR: int = -32005
VIEWPORT_CAPTURE_ERROR: int = -32006
SCRIPT_SYNTAX_ERROR: int = -32007

ALL_ERROR_CODES: List[int] = [
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR,
    BLENDER_DAEMON_ERROR,
    OBJECT_NOT_FOUND,
    MATERIAL_SHADER_ERROR,
    ARMATURE_RIGGING_ERROR,
    LIGHTING_CAMERA_ERROR,
    RENDER_ENGINE_ERROR,
    VIEWPORT_CAPTURE_ERROR,
    SCRIPT_SYNTAX_ERROR,
]

ERROR_CODE_NAMES: Dict[int, str] = {
    PARSE_ERROR: "PARSE_ERROR",
    INVALID_REQUEST: "INVALID_REQUEST",
    METHOD_NOT_FOUND: "METHOD_NOT_FOUND",
    INVALID_PARAMS: "INVALID_PARAMS",
    INTERNAL_ERROR: "INTERNAL_ERROR",
    BLENDER_DAEMON_ERROR: "BLENDER_DAEMON_ERROR",
    OBJECT_NOT_FOUND: "OBJECT_NOT_FOUND",
    MATERIAL_SHADER_ERROR: "MATERIAL_SHADER_ERROR",
    ARMATURE_RIGGING_ERROR: "ARMATURE_RIGGING_ERROR",
    LIGHTING_CAMERA_ERROR: "LIGHTING_CAMERA_ERROR",
    RENDER_ENGINE_ERROR: "RENDER_ENGINE_ERROR",
    VIEWPORT_CAPTURE_ERROR: "VIEWPORT_CAPTURE_ERROR",
    SCRIPT_SYNTAX_ERROR: "SCRIPT_SYNTAX_ERROR",
}

ERROR_DEFAULT_MESSAGES: Dict[int, str] = {
    PARSE_ERROR: "Invalid JSON was received by the server while parsing payload.",
    INVALID_REQUEST: "The request sent is not a valid JSON-RPC request object.",
    METHOD_NOT_FOUND: "The requested tool or command method does not exist.",
    INVALID_PARAMS: "Invalid parameters provided for tool execution.",
    INTERNAL_ERROR: "Internal server error occurred during request execution.",
    BLENDER_DAEMON_ERROR: "Blender daemon is offline, unresponsive, or connection severed.",
    OBJECT_NOT_FOUND: "Target 3D object was not found in the current Blender scene.",
    MATERIAL_SHADER_ERROR: "Material shader node tree or socket configuration error.",
    ARMATURE_RIGGING_ERROR: "Armature bone hierarchy, skinning, or IK constraint failure.",
    LIGHTING_CAMERA_ERROR: "Lighting or camera configuration error.",
    RENDER_ENGINE_ERROR: "Render engine or compute device failure.",
    VIEWPORT_CAPTURE_ERROR: "Failed to capture 3D viewport or offscreen buffer.",
    SCRIPT_SYNTAX_ERROR: "Python syntax error or unhandled runtime exception in executed code.",
}


# ==============================================================================
# 2. Standardized Exception Hierarchy
# ==============================================================================

class BlenderMCPError(Exception):
    """Base exception for all Blender MCP operations."""
    code: int = INTERNAL_ERROR
    error_type: str = "InternalError"

    def __init__(
        self,
        message: Optional[str] = None,
        code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        hint: Optional[str] = None,
    ) -> None:
        if code is not None:
            self.code = code
        self.message = message or ERROR_DEFAULT_MESSAGES.get(self.code, "Blender MCP execution error.")
        super().__init__(self.message)

        self.details: Dict[str, Any] = details.copy() if details else {}
        if hint and "hint" not in self.details:
            self.details["hint"] = hint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "error",
            "error_code": self.code,
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "isError": True,
        }


class ParseError(BlenderMCPError):
    """Socket received malformed JSON string (-32700)."""
    code = PARSE_ERROR
    error_type = "ParseError"


class InvalidRequestError(BlenderMCPError):
    """JSON payload missing required routing fields (-32600)."""
    code = INVALID_REQUEST
    error_type = "InvalidRequestError"


class MethodNotFoundError(BlenderMCPError):
    """Requested tool name or bridge op unregistered (-32601)."""
    code = METHOD_NOT_FOUND
    error_type = "MethodNotFoundError"


class InvalidParamsError(BlenderMCPError):
    """Parameter fails schema validation or range requirements (-32602)."""
    code = INVALID_PARAMS
    error_type = "InvalidParamsError"


class InternalError(BlenderMCPError):
    """Unhandled internal server error (-32603)."""
    code = INTERNAL_ERROR
    error_type = "InternalError"


class BlenderDaemonError(BlenderMCPError):
    """Blender daemon offline, socket severed, or connection timed out (-32000)."""
    code = BLENDER_DAEMON_ERROR
    error_type = "BlenderDaemonError"


class ObjectNotFoundError(BlenderMCPError):
    """Target object missing in scene (-32001)."""
    code = OBJECT_NOT_FOUND
    error_type = "ObjectNotFoundError"


class MaterialShaderError(BlenderMCPError):
    """Material missing, shader node tree corrupt, or texture missing (-32002)."""
    code = MATERIAL_SHADER_ERROR
    error_type = "MaterialShaderError"


class ArmatureRiggingError(BlenderMCPError):
    """Bone missing, cyclic hierarchy, or bone heat weighting failure (-32003)."""
    code = ARMATURE_RIGGING_ERROR
    error_type = "ArmatureRiggingError"


class HierarchyCycleError(ArmatureRiggingError):
    """Cyclic hierarchy detected in parenting or constraint target (-32003)."""
    code = ARMATURE_RIGGING_ERROR
    error_type = "HierarchyCycleError"


class LightingCameraError(BlenderMCPError):
    """Track-to target missing, camera focal length out of bounds (-32004)."""
    code = LIGHTING_CAMERA_ERROR
    error_type = "LightingCameraError"


class RenderEngineError(BlenderMCPError):
    """Unsupported render engine, GPU device failure, or render error (-32005)."""
    code = RENDER_ENGINE_ERROR
    error_type = "RenderEngineError"


class ViewportCaptureError(BlenderMCPError):
    """Offscreen buffer allocation failed or OpenGL context missing (-32006)."""
    code = VIEWPORT_CAPTURE_ERROR
    error_type = "ViewportCaptureError"


class ScriptSyntaxError(BlenderMCPError):
    """Python syntax error or runtime script execution exception (-32007)."""
    code = SCRIPT_SYNTAX_ERROR
    error_type = "ScriptSyntaxError"


EXCEPTION_CODE_MAP: Dict[Type[Exception], int] = {
    ParseError: PARSE_ERROR,
    InvalidRequestError: INVALID_REQUEST,
    MethodNotFoundError: METHOD_NOT_FOUND,
    InvalidParamsError: INVALID_PARAMS,
    InternalError: INTERNAL_ERROR,
    BlenderDaemonError: BLENDER_DAEMON_ERROR,
    ObjectNotFoundError: OBJECT_NOT_FOUND,
    MaterialShaderError: MATERIAL_SHADER_ERROR,
    ArmatureRiggingError: ARMATURE_RIGGING_ERROR,
    HierarchyCycleError: ARMATURE_RIGGING_ERROR,
    LightingCameraError: LIGHTING_CAMERA_ERROR,
    RenderEngineError: RENDER_ENGINE_ERROR,
    ViewportCaptureError: VIEWPORT_CAPTURE_ERROR,
    ScriptSyntaxError: SCRIPT_SYNTAX_ERROR,
}


# ==============================================================================
# 3. Diagnostic Formatting & Hints
# ==============================================================================

def generate_diagnostic_hint(code: int, exc: Exception, details: Dict[str, Any]) -> Optional[str]:
    """Generates an intelligent recovery hint based on error code and context."""
    if "hint" in details and details["hint"]:
        return str(details["hint"])

    if code == OBJECT_NOT_FOUND:
        target = details.get("target") or details.get("name") or details.get("object_name")
        avail = details.get("available_objects")
        if avail and target:
            # Simple match search
            close_matches = [o for o in avail if target.lower() in o.lower() or o.lower() in target.lower()]
            if close_matches:
                return f"Target '{target}' not found. Did you mean '{close_matches[0]}'?"
        return "Verify existing objects in the scene using 'blender_get_scene_info'."

    elif code == MATERIAL_SHADER_ERROR:
        mat_name = details.get("material_name")
        if mat_name:
            return f"Verify material '{mat_name}' exists or create it using 'blender_create_material'."
        return "Verify material and texture file paths exist before connecting."

    elif code == ARMATURE_RIGGING_ERROR:
        return "Ensure armature and mesh are in Object Mode and mesh has manifold geometry with valid scale."

    elif code == LIGHTING_CAMERA_ERROR:
        return "Verify target object exists and camera parameters are within physical sensor ranges."

    elif code == RENDER_ENGINE_ERROR:
        return "Verify render engine name ('CYCLES', 'BLENDER_EEVEE_NEXT') or switch device to 'CPU'."

    elif code == VIEWPORT_CAPTURE_ERROR:
        return "Ensure scene contains an active camera and resolution is positive."

    elif code == SCRIPT_SYNTAX_ERROR:
        return "Check Python script syntax and variable declarations."

    elif code == INVALID_PARAMS:
        return "Check parameter types, non-empty values, and enum options against the tool specification."

    elif code == BLENDER_DAEMON_ERROR:
        return "Verify Blender daemon is active and listening on TCP port 9876."

    return None


def format_error_payload(
    exc: Exception,
    code: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    tb: Optional[str] = None,
    hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Constructs a standard structured diagnostic error payload."""
    det = (details or {}).copy()

    if isinstance(exc, BlenderMCPError):
        effective_code = code if code is not None else exc.code
        error_type = exc.__class__.__name__
        msg = exc.message
        det.update(exc.details)
    else:
        effective_code = code or INTERNAL_ERROR
        error_type = exc.__class__.__name__
        msg = str(exc) or ERROR_DEFAULT_MESSAGES.get(effective_code, "Unknown execution error.")

    diag_hint = hint or generate_diagnostic_hint(effective_code, exc, det)
    if diag_hint and "hint" not in det:
        det["hint"] = diag_hint

    payload: Dict[str, Any] = {
        "status": "error",
        "error_code": effective_code,
        "error_type": error_type,
        "message": msg,
        "details": det,
        "isError": True,
    }

    if tb:
        payload["traceback"] = tb

    return payload


def format_mcp_error(
    exc: Exception,
    code: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    tb: Optional[str] = None,
    hint: Optional[str] = None,
) -> CallToolResult:
    """Wraps error payload into standard MCP CallToolResult with isError: True."""
    payload = format_error_payload(exc=exc, code=code, details=details, tb=tb, hint=hint)
    text_json = json.dumps(payload, indent=2, ensure_ascii=False)
    return CallToolResult(
        content=[TextContent(type="text", text=text_json)],
        isError=True,
    )


def format_mcp_success(
    result: Any,
    text_summary: Optional[str] = None,
    image_data: Optional[str] = None,
    mime_type: str = "image/png",
) -> CallToolResult:
    """Wraps result payload into standard MCP CallToolResult with isError: False."""
    content: List[Union[TextContent, ImageContent]] = []

    if image_data:
        # Put text first then image as per convention
        caption = text_summary or "Viewport screenshot captured successfully."
        content.append(TextContent(type="text", text=caption))
        content.append(ImageContent(type="image", data=image_data, mimeType=mime_type))
    else:
        if isinstance(result, str):
            content.append(TextContent(type="text", text=result))
        else:
            text_json = json.dumps(result, indent=2, ensure_ascii=False)
            content.append(TextContent(type="text", text=text_json))

    return CallToolResult(
        content=content,
        isError=False,
    )


# ==============================================================================
# 4. Zero-Crash @error_boundary Decorator
# ==============================================================================

def error_boundary(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator enforcing the Zero-Crash Boundary for all MCP tool handlers.
    Catches all exceptions, maps them to the appropriate error code,
    and returns a structured CallToolResult with isError: True and rich diagnostics.
    """
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> CallToolResult:
            try:
                res = await func(*args, **kwargs)
                if isinstance(res, CallToolResult):
                    return res
                if isinstance(res, dict) and res.get("status") == "error":
                    # Error returned from Blender daemon or internal op
                    err_code = res.get("error_code", INTERNAL_ERROR)
                    err_msg = res.get("message", "Operation failed")
                    err_details = res.get("details", {})
                    tb = res.get("traceback")
                    return CallToolResult(
                        content=[TextContent(type="text", text=json.dumps(res, indent=2, ensure_ascii=False))],
                        isError=True,
                    )
                return format_mcp_success(res)
            except BlenderMCPError as be:
                logger.warning("BlenderMCPError in tool '%s': %s (code %d)", func.__name__, be, be.code)
                return format_mcp_error(be, code=be.code, details=be.details)
            except (ValueError, TypeError, KeyError) as pe:
                logger.warning("Invalid parameters in tool '%s': %s", func.__name__, pe)
                return format_mcp_error(pe, code=INVALID_PARAMS, details={"function": func.__name__})
            except (ConnectionError, OSError) as ce:
                logger.error("Connection/OS error in tool '%s': %s", func.__name__, ce)
                return format_mcp_error(ce, code=BLENDER_DAEMON_ERROR, details={"function": func.__name__})
            except Exception as e:
                tb = traceback.format_exc()
                logger.error("Unhandled exception in tool '%s': %s\n%s", func.__name__, e, tb)
                return format_mcp_error(e, code=INTERNAL_ERROR, details={"function": func.__name__}, tb=tb)

        return async_wrapper

    else:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> CallToolResult:
            try:
                res = func(*args, **kwargs)
                if isinstance(res, CallToolResult):
                    return res
                if isinstance(res, dict) and res.get("status") == "error":
                    # Error returned from Blender daemon or internal op
                    return CallToolResult(
                        content=[TextContent(type="text", text=json.dumps(res, indent=2, ensure_ascii=False))],
                        isError=True,
                    )
                return format_mcp_success(res)
            except BlenderMCPError as be:
                logger.warning("BlenderMCPError in tool '%s': %s (code %d)", func.__name__, be, be.code)
                return format_mcp_error(be, code=be.code, details=be.details)
            except (ValueError, TypeError, KeyError) as pe:
                logger.warning("Invalid parameters in tool '%s': %s", func.__name__, pe)
                return format_mcp_error(pe, code=INVALID_PARAMS, details={"function": func.__name__})
            except (ConnectionError, OSError) as ce:
                logger.error("Connection/OS error in tool '%s': %s", func.__name__, ce)
                return format_mcp_error(ce, code=BLENDER_DAEMON_ERROR, details={"function": func.__name__})
            except Exception as e:
                tb = traceback.format_exc()
                logger.error("Unhandled exception in tool '%s': %s\n%s", func.__name__, e, tb)
                return format_mcp_error(e, code=INTERNAL_ERROR, details={"function": func.__name__}, tb=tb)

        return sync_wrapper
