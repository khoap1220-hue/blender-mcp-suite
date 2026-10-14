"""
src/blender_mcp/tools/lighting_camera.py — Cinematic Lighting & Camera Tools

Covers:
- blender_setup_light: Create/configure lights (Point, Sun, Spot, Area).
- blender_setup_world_hdri: Configure world ambient lighting or HDRI environment map.
- blender_setup_camera: Create camera with focal length, sensor width, and depth of field.
- blender_camera_track_to: Attach Track-To constraint pointing camera at target object.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp.types import CallToolResult

from blender_mcp.error_boundary import error_boundary


@error_boundary
def blender_setup_light(
    light_type: str,
    energy: float,
    light_name: Optional[str] = None,
    color: Optional[List[float]] = None,
    location: Optional[List[float]] = None,
    size: Optional[float] = None,
    spot_size: Optional[float] = None,
    spot_blend: Optional[float] = None,
) -> CallToolResult:
    """
    Create or configure a light source (Sun, Point, Spot, Area).

    Parameters:
        light_type: Light type ("POINT", "SUN", "SPOT", "AREA").
        energy: Light power in Watts (Point/Spot/Area) or Strength (Sun).
        light_name: Name of the light object to create or update.
        color: RGB light tint [r, g, b] (each 0.0 to 1.0).
        location: World position coordinates [x, y, z].
        size: Radius for Point/Spot or size for Area light.
        spot_size: Spot light beam angle in radians.
        spot_blend: Spot light edge softness (0.0 to 1.0).
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "light_type": light_type,
        "energy": energy,
        "light_name": light_name,
        "color": color,
        "location": location,
        "size": size,
        "spot_size": spot_size,
        "spot_blend": spot_blend,
    }
    return execute_bridge_op("setup_light", params)


@error_boundary
def blender_setup_world_hdri(
    color: Optional[List[float]] = None,
    strength: float = 1.0,
    hdri_path: Optional[str] = None,
    rotation_z: float = 0.0,
) -> CallToolResult:
    """
    Configure world environment lighting and HDRI background texture.

    Parameters:
        color: Background solid RGB tint [r, g, b].
        strength: World environment light radiant multiplier (default: 1.0).
        hdri_path: Absolute file path to .hdr or .exr environment map.
        rotation_z: Z-axis rotation angle in radians for HDRI alignment.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "color": color,
        "strength": strength,
        "hdri_path": hdri_path,
        "rotation_z": rotation_z,
    }
    return execute_bridge_op("setup_world_hdri", params)


@error_boundary
def blender_setup_camera(
    camera_name: str = "Camera",
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    focal_length: float = 50.0,
    sensor_width: float = 36.0,
    dof_target: Optional[str] = None,
    dof_fstop: float = 2.8,
    set_active: bool = True,
) -> CallToolResult:
    """
    Create or configure camera parameters (focal length, sensor, depth of field).

    Parameters:
        camera_name: Identifier for the camera object (default: "Camera").
        location: World position coordinates [x, y, z].
        rotation: Euler orientation angles [rx, ry, rz] in radians.
        focal_length: Lens focal length in millimeters (e.g. 24, 35, 50, 85).
        sensor_width: Physical sensor width in millimeters (36.0 = Full Frame).
        dof_target: Object name to autofocus on.
        dof_fstop: Lens aperture f-stop for depth of field blur (default: 2.8).
        set_active: Set camera as the active rendering camera for the scene.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "camera_name": camera_name,
        "location": location,
        "rotation": rotation,
        "focal_length": focal_length,
        "sensor_width": sensor_width,
        "dof_target": dof_target,
        "dof_fstop": dof_fstop,
        "set_active": set_active,
    }
    return execute_bridge_op("setup_camera", params)


@error_boundary
def blender_camera_track_to(
    target_object: str,
    camera_name: Optional[str] = None,
    track_axis: str = "TRACK_NEG_Z",
    up_axis: str = "UP_Y",
) -> CallToolResult:
    """
    Add a Track-To constraint to lock camera orientation toward a target object.

    Parameters:
        target_object: Name of target object to track.
        camera_name: Name of camera (default: active scene camera).
        track_axis: Camera forward aiming axis ("TRACK_NEG_Z", "TRACK_Z", "TRACK_Y", "TRACK_X").
        up_axis: Camera upward orienting axis ("UP_Y", "UP_Z", "UP_X").
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "target_object": target_object,
        "camera_name": camera_name,
        "track_axis": track_axis,
        "up_axis": up_axis,
    }
    return execute_bridge_op("camera_track_to", params)
