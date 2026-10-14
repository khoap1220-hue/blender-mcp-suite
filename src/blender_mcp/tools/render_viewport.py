"""
src/blender_mcp/tools/render_viewport.py — Render Engine & Viewport Tools

Covers:
- blender_configure_render_engine: Switch engine (Cycles / Eevee), resolution, samples, device.
- blender_render_frame: Execute render and save output frame to disk.
- blender_get_viewport_screenshot: Capture 3D viewport/offscreen snapshot as base64 PNG.
- blender_execute_code: Fallback execution of arbitrary Python script in Blender.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from mcp.types import CallToolResult, ImageContent, TextContent

from blender_mcp.error_boundary import error_boundary, format_mcp_success


@error_boundary
def blender_configure_render_engine(
    engine: str,
    device: str = "GPU",
    resolution_x: int = 1920,
    resolution_y: int = 1080,
    samples: int = 64,
    film_transparent: bool = False,
) -> CallToolResult:
    """
    Configure render engine (Cycles vs Eevee), resolution, sample counts, and background alpha.

    Parameters:
        engine: Rendering engine ("CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH").
        device: Compute device ("GPU" or "CPU").
        resolution_x: Horizontal frame width in pixels (default: 1920).
        resolution_y: Vertical frame height in pixels (default: 1080).
        samples: Render sample iterations (default: 64).
        film_transparent: Render alpha transparency for empty background areas.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "engine": engine,
        "device": device,
        "resolution_x": resolution_x,
        "resolution_y": resolution_y,
        "samples": samples,
        "film_transparent": film_transparent,
    }
    return execute_bridge_op("configure_render_engine", params)


@error_boundary
def blender_render_frame(
    output_path: str,
    frame: Optional[int] = None,
    file_format: str = "PNG",
) -> CallToolResult:
    """
    Execute scene render and save still frame to disk.

    Parameters:
        output_path: Destination file path for rendered output (e.g. C:\\render.png).
        frame: Optional frame number to render (defaults to active scene frame).
        file_format: Output image format ("PNG", "JPEG", "OPEN_EXR").
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "output_path": output_path,
        "frame": frame,
        "file_format": file_format,
    }
    return execute_bridge_op("render_frame", params)


@error_boundary
def blender_get_viewport_screenshot(
    max_dimension: int = 1024,
    shading_type: str = "MATERIAL",
    camera_view: bool = True,
) -> CallToolResult:
    """
    Capture instant 3D viewport snapshot formatted for AI multimodal vision input.

    Parameters:
        max_dimension: Maximum pixel size for longest dimension (default: 1024).
        shading_type: Shading display style ("WIREFRAME", "SOLID", "MATERIAL", "RENDERED").
        camera_view: Frame capture from active scene camera viewpoint.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "max_dimension": max_dimension,
        "shading_type": shading_type,
        "camera_view": camera_view,
    }
    res = execute_bridge_op("get_viewport_screenshot", params)

    b64_data = res.get("image_base64", "")
    mime_type = res.get("mime_type", "image/png")
    res_x, res_y = res.get("resolution", [1024, 576])
    cam = res.get("camera", "Camera")
    shading = res.get("shading", shading_type)

    caption = f"Viewport snapshot: resolution {res_x}x{res_y}, shading: {shading}, camera: {cam}"
    return format_mcp_success(
        result=res,
        text_summary=caption,
        image_data=b64_data,
        mime_type=mime_type,
    )


@error_boundary
def blender_execute_code(
    code: str,
    strict_json: bool = False,
) -> Dict[str, Any]:
    """
    Fallback execution of arbitrary Python script inside Blender's main-thread namespace.

    Parameters:
        code: Python script to execute. Assign to variable `result` for return value.
        strict_json: Enforce strict JSON standard serialization without mathutils conversions.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "code": code,
        "strict_json": strict_json,
    }
    return execute_bridge_op("execute_code", params)
