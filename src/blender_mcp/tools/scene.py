"""
src/blender_mcp/tools/scene.py — Scene & Object Manipulation Tools

Covers:
- blender_manage_object: Create 3D primitives, duplicate, delete, rename, select.
- blender_transform_object: Set or delta location/rotation/scale, apply transforms.
- blender_manage_hierarchy: Parenting (with keep transform & cycle detection) and collections.
- blender_get_scene_info: Query scene statistics, objects, active camera, render settings.
- blender_get_object_info: Detailed object transforms, bounding box, modifiers, materials.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp.types import CallToolResult

from blender_mcp.error_boundary import error_boundary


@error_boundary
def blender_manage_object(
    action: str,
    primitive_type: str = "cube",
    name: Optional[str] = None,
    new_name: Optional[str] = None,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> CallToolResult:
    """
    Create 3D primitives, duplicate, delete, rename, or select objects in the scene.

    Parameters:
        action: Manipulation action ("create", "delete", "duplicate", "rename", "select", "deselect_all").
        primitive_type: Mesh primitive to create ("cube", "uv_sphere", "ico_sphere", "cylinder", "cone", "plane", "torus", "monkey", "empty").
        name: Name of target object or base name for creation.
        new_name: New object name if action is "rename".
        location: World position [x, y, z] for newly created object.
        rotation: Euler angles [rx, ry, rz] in radians.
        scale: Scale multipliers [sx, sy, sz].
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "action": action,
        "primitive_type": primitive_type,
        "name": name,
        "new_name": new_name,
        "location": location,
        "rotation": rotation,
        "scale": scale,
    }
    return execute_bridge_op("manage_object", params)


@error_boundary
def blender_transform_object(
    name: str,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
    delta: bool = False,
    apply_transform: bool = False,
) -> CallToolResult:
    """
    Adjust position, rotation, and scale of an existing object with optional delta mode and transform application.

    Parameters:
        name: Exact name of the object to transform.
        location: Target position [x, y, z].
        rotation: Target Euler rotation angles [rx, ry, rz] in radians.
        scale: Target scale factors [sx, sy, sz].
        delta: If True, adds transform values relative to current object coordinates.
        apply_transform: If True, bakes current transforms into mesh data.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "name": name,
        "location": location,
        "rotation": rotation,
        "scale": scale,
        "delta": delta,
        "apply_transform": apply_transform,
    }
    return execute_bridge_op("transform_object", params)


@error_boundary
def blender_manage_hierarchy(
    action: str,
    child_name: Optional[str] = None,
    parent_name: Optional[str] = None,
    keep_transform: bool = True,
    collection_name: Optional[str] = None,
    target_objects: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Manage parenting relationships and collection grouping with cyclic dependency protection.

    Parameters:
        action: Hierarchy action ("set_parent", "clear_parent", "create_collection", "move_to_collection").
        child_name: Name of child object for parenting actions.
        parent_name: Name of parent object for set_parent action.
        keep_transform: Maintain current world matrix coordinates during parenting.
        collection_name: Target collection name for organization.
        target_objects: List of object names to move into collection.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "action": action,
        "child_name": child_name,
        "parent_name": parent_name,
        "keep_transform": keep_transform,
        "collection_name": collection_name,
        "target_objects": target_objects,
    }
    return execute_bridge_op("manage_hierarchy", params)


@error_boundary
def blender_get_scene_info(
    detailed: bool = False,
    collection_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query scene statistics, active camera, render settings, and hierarchy tree.

    Parameters:
        detailed: If True, includes vertex/face counts, modifiers, and material slots.
        collection_filter: Optional collection name to restrict query scope.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "detailed": detailed,
        "collection_filter": collection_filter,
    }
    return execute_bridge_op("get_scene_info", params)


@error_boundary
def blender_get_object_info(name: str) -> Dict[str, Any]:
    """
    Retrieve deep inspect data for a specific object (transforms, bounding box, dimensions, modifiers).

    Parameters:
        name: Exact name of the object to inspect.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {"name": name}
    return execute_bridge_op("get_object_info", params)
