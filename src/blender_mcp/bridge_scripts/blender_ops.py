"""
src/blender_mcp/bridge_scripts/blender_ops.py — Production-Grade Blender 3D Operations Core

Executes natively inside Blender 4.1+ (or headless daemon) on the main thread.
All operations have structured try/except blocks and raise or return standardized
domain exceptions defined in `error_boundary.py`.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import math
import os
import sys
import tempfile
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import bpy
    import mathutils
except ImportError:
    bpy = None  # type: ignore
    mathutils = None  # type: ignore

try:
    from blender_mcp.error_boundary import (
        ArmatureRiggingError,
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
        format_error_payload,
    )
except ImportError:
    # Fallback when running inside Blender where src might not be on sys.path yet
    class BlenderMCPError(Exception):
        def __init__(self, message: str = "", code: int = -32603, details: Optional[Dict[str, Any]] = None):
            super().__init__(message)
            self.message = message
            self.code = code
            self.details = (details or {}).copy()

    class InternalError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32603, details=details)

    class BlenderDaemonError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32000, details=details)

    class ParseError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32700, details=details)

    class InvalidRequestError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32600, details=details)

    class InvalidParamsError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32602, details=details)

    class ObjectNotFoundError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32001, details=details)

    class MaterialShaderError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32002, details=details)

    class ArmatureRiggingError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32003, details=details)

    class HierarchyCycleError(ArmatureRiggingError):
        pass

    class LightingCameraError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32004, details=details)

    class RenderEngineError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32005, details=details)

    class ViewportCaptureError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32006, details=details)

    class ScriptSyntaxError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32007, details=details)

    class MethodNotFoundError(BlenderMCPError):
        def __init__(self, message: str = "", details: Optional[Dict[str, Any]] = None):
            super().__init__(message, code=-32601, details=details)

    def format_error_payload(exc: Exception, code: Optional[int] = None, details: Optional[Dict[str, Any]] = None, tb: Optional[str] = None) -> Dict[str, Any]:
        c = getattr(exc, "code", code or -32603)
        det = getattr(exc, "details", details or {}).copy()
        res = {
            "status": "error",
            "error_code": c,
            "error_type": exc.__class__.__name__,
            "message": str(exc),
            "details": det,
            "isError": True,
        }
        if tb:
            res["traceback"] = tb
        return res


def _ensure_object_mode() -> None:
    """Safely restore Blender context to OBJECT mode to avoid operator context errors."""
    if bpy is not None and hasattr(bpy.context, "mode") and bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass


def _get_available_objects() -> List[str]:
    """Retrieve all object names in scene for error diagnostics."""
    if bpy is None:
        return []
    return [obj.name for obj in bpy.data.objects]


# ==============================================================================
# Category A: Scene & Object Manipulation
# ==============================================================================

def manage_object(
    action: str,
    primitive_type: str = "cube",
    name: Optional[str] = None,
    new_name: Optional[str] = None,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    Create primitives, duplicate, delete, rename, select, or deselect objects.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    _ensure_object_mode()
    action = action.lower().strip()

    if action == "create":
        prim = (primitive_type or "cube").lower().strip()
        loc = tuple(location) if location else (0.0, 0.0, 0.0)
        rot = tuple(rotation) if rotation else (0.0, 0.0, 0.0)
        scl = tuple(scale) if scale else (1.0, 1.0, 1.0)

        if prim == "cube":
            bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot, scale=scl)
        elif prim == "uv_sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(location=loc, rotation=rot, scale=scl)
        elif prim == "ico_sphere":
            bpy.ops.mesh.primitive_ico_sphere_add(location=loc, rotation=rot, scale=scl)
        elif prim == "cylinder":
            bpy.ops.mesh.primitive_cylinder_add(location=loc, rotation=rot, scale=scl)
        elif prim == "cone":
            bpy.ops.mesh.primitive_cone_add(location=loc, rotation=rot, scale=scl)
        elif prim == "plane":
            bpy.ops.mesh.primitive_plane_add(location=loc, rotation=rot, scale=scl)
        elif prim == "torus":
            bpy.ops.mesh.primitive_torus_add(location=loc, rotation=rot)
            # Torus does not support scale in operator call
            bpy.context.active_object.scale = scl
        elif prim == "monkey":
            bpy.ops.mesh.primitive_monkey_add(location=loc, rotation=rot, scale=scl)
        elif prim == "empty":
            bpy.ops.object.empty_add(type="PLAIN_AXES", location=loc, rotation=rot, scale=scl)
        else:
            raise InvalidParamsError(
                f"Unknown primitive_type '{primitive_type}'. Supported: "
                "cube, uv_sphere, ico_sphere, cylinder, cone, plane, torus, monkey, empty."
            )

        obj = bpy.context.active_object
        if not obj:
            raise InternalError("Failed to create 3D primitive.")

        if name:
            obj.name = name

        return {
            "status": "success",
            "action": "create",
            "object_name": obj.name,
            "actual_name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
            "rotation": list(obj.rotation_euler),
            "scale": list(obj.scale),
            "isError": False,
        }

    elif action == "delete":
        if name:
            obj = bpy.data.objects.get(name)
            if not obj:
                raise ObjectNotFoundError(
                    f"Object '{name}' not found for deletion.",
                    details={"target": name, "available_objects": _get_available_objects()},
                )
            bpy.data.objects.remove(obj, do_unlink=True)
            return {"status": "success", "action": "delete", "object_name": name, "isError": False}
        else:
            # Delete selected objects
            deleted = [o.name for o in bpy.context.selected_objects]
            bpy.ops.object.delete(use_global=False)
            return {"status": "success", "action": "delete", "deleted_objects": deleted, "isError": False}

    elif action == "duplicate":
        if not name:
            raise InvalidParamsError("Object 'name' is required for duplicate action.")
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ObjectNotFoundError(
                f"Object '{name}' not found for duplication.",
                details={"target": name, "available_objects": _get_available_objects()},
            )

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.duplicate()
        new_obj = bpy.context.active_object
        if new_name:
            new_obj.name = new_name
        if location:
            new_obj.location = location

        return {
            "status": "success",
            "action": "duplicate",
            "original_name": name,
            "object_name": new_obj.name,
            "actual_name": new_obj.name,
            "location": list(new_obj.location),
            "isError": False,
        }

    elif action == "rename":
        if not name or not new_name:
            raise InvalidParamsError("Both 'name' and 'new_name' are required for rename action.")
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ObjectNotFoundError(
                f"Object '{name}' not found for rename.",
                details={"target": name, "available_objects": _get_available_objects()},
            )
        obj.name = new_name
        return {
            "status": "success",
            "action": "rename",
            "old_name": name,
            "object_name": obj.name,
            "actual_name": obj.name,
            "isError": False,
        }

    elif action == "select":
        if not name:
            raise InvalidParamsError("Object 'name' is required for select action.")
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ObjectNotFoundError(
                f"Object '{name}' not found for selection.",
                details={"target": name, "available_objects": _get_available_objects()},
            )
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        return {"status": "success", "action": "select", "object_name": obj.name, "isError": False}

    elif action == "deselect_all":
        bpy.ops.object.select_all(action="DESELECT")
        return {"status": "success", "action": "deselect_all", "isError": False}

    else:
        raise InvalidParamsError(
            f"Invalid action '{action}'. Valid actions: create, delete, duplicate, rename, select, deselect_all."
        )


def transform_object(
    name: str,
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
    delta: bool = False,
    apply_transform: bool = False,
) -> Dict[str, Any]:
    """
    Adjust position, rotation, and scale of an existing object.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    _ensure_object_mode()
    obj = bpy.data.objects.get(name)
    if not obj:
        raise ObjectNotFoundError(
            f"Object '{name}' does not exist in scene.",
            details={"target": name, "available_objects": _get_available_objects()},
        )

    if delta:
        if location:
            obj.location = [a + b for a, b in zip(obj.location, location)]
        if rotation:
            obj.rotation_euler = [a + b for a, b in zip(obj.rotation_euler, rotation)]
        if scale:
            obj.scale = [a * b for a, b in zip(obj.scale, scale)]
    else:
        if location is not None:
            obj.location = location
        if rotation is not None:
            obj.rotation_euler = rotation
        if scale is not None:
            obj.scale = scale

    if apply_transform:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(
            location=location is not None,
            rotation=rotation is not None,
            scale=scale is not None,
        )

    return {
        "status": "success",
        "object_name": obj.name,
        "transforms": {
            "location": list(obj.location),
            "rotation": list(obj.rotation_euler),
            "scale": list(obj.scale),
        },
        "applied": apply_transform,
        "isError": False,
    }


def manage_hierarchy(
    action: str,
    child_name: Optional[str] = None,
    parent_name: Optional[str] = None,
    keep_transform: bool = True,
    collection_name: Optional[str] = None,
    target_objects: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Parent/unparent objects and manage scene collections with cycle detection.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    _ensure_object_mode()
    action = action.lower().strip()

    if action == "set_parent":
        if not child_name or not parent_name:
            raise InvalidParamsError("Both 'child_name' and 'parent_name' are required for set_parent.")

        child = bpy.data.objects.get(child_name)
        parent = bpy.data.objects.get(parent_name)
        if not child:
            raise ObjectNotFoundError(f"Child object '{child_name}' not found.", details={"target": child_name})
        if not parent:
            raise ObjectNotFoundError(f"Parent object '{parent_name}' not found.", details={"target": parent_name})

        # Cyclic dependency detection
        curr = parent
        while curr:
            if curr == child:
                raise HierarchyCycleError(
                    f"Cannot parent '{child_name}' to '{parent_name}': creates cyclic dependency.",
                    details={"child": child_name, "parent": parent_name},
                )
            curr = curr.parent

        if keep_transform:
            child.matrix_parent_inverse = parent.matrix_world.inverted()
        child.parent = parent

        return {
            "status": "success",
            "action": "set_parent",
            "child": child.name,
            "parent": parent.name,
            "keep_transform": keep_transform,
            "isError": False,
        }

    elif action == "clear_parent":
        if not child_name:
            raise InvalidParamsError("Object 'child_name' is required for clear_parent.")
        child = bpy.data.objects.get(child_name)
        if not child:
            raise ObjectNotFoundError(f"Child object '{child_name}' not found.", details={"target": child_name})

        if keep_transform:
            world_mat = child.matrix_world.copy()
            child.parent = None
            child.matrix_world = world_mat
        else:
            child.parent = None

        return {"status": "success", "action": "clear_parent", "child": child.name, "isError": False}

    elif action == "create_collection":
        if not collection_name:
            raise InvalidParamsError("Parameter 'collection_name' is required for create_collection.")

        coll = bpy.data.collections.get(collection_name)
        if not coll:
            coll = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(coll)

        if target_objects:
            for obj_name in target_objects:
                obj = bpy.data.objects.get(obj_name)
                if obj and obj.name not in coll.objects:
                    coll.objects.link(obj)

        return {
            "status": "success",
            "action": "create_collection",
            "collection_name": coll.name,
            "objects": [o.name for o in coll.objects],
            "isError": False,
        }

    elif action == "move_to_collection":
        if not collection_name or not target_objects:
            raise InvalidParamsError("Both 'collection_name' and 'target_objects' required for move_to_collection.")

        coll = bpy.data.collections.get(collection_name)
        if not coll:
            raise ObjectNotFoundError(f"Collection '{collection_name}' not found.", details={"target": collection_name})

        moved = []
        for obj_name in target_objects:
            obj = bpy.data.objects.get(obj_name)
            if not obj:
                raise ObjectNotFoundError(f"Target object '{obj_name}' not found.", details={"target": obj_name})
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            coll.objects.link(obj)
            moved.append(obj.name)

        return {
            "status": "success",
            "action": "move_to_collection",
            "collection_name": coll.name,
            "moved_objects": moved,
            "isError": False,
        }

    else:
        raise InvalidParamsError(
            f"Invalid hierarchy action '{action}'. Valid: set_parent, clear_parent, create_collection, move_to_collection."
        )


def get_scene_info(
    detailed: bool = False,
    collection_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query scene metadata, objects list, active camera, and render engine.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    scene = bpy.context.scene
    objects = bpy.data.objects

    if collection_filter:
        coll = bpy.data.collections.get(collection_filter)
        if not coll:
            raise ObjectNotFoundError(
                f"Collection '{collection_filter}' not found.",
                details={"target": collection_filter},
            )
        objects = coll.objects

    obj_list = []
    total_verts = 0
    total_faces = 0

    for obj in objects:
        info: Dict[str, Any] = {
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
            "rotation": list(obj.rotation_euler),
            "scale": list(obj.scale),
            "parent": obj.parent.name if obj.parent else None,
            "children": [c.name for c in obj.children],
        }
        if detailed and obj.type == "MESH" and obj.data:
            verts = len(obj.data.vertices)
            faces = len(obj.data.polygons)
            total_verts += verts
            total_faces += faces
            info["vertices"] = verts
            info["polygons"] = faces
            info["modifiers"] = [m.name for m in obj.modifiers]
            info["materials"] = [slot.material.name for slot in obj.material_slots if slot.material]
        obj_list.append(info)

    return {
        "status": "success",
        "scene_name": scene.name,
        "active_camera": scene.camera.name if scene.camera else None,
        "render_engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "frame_current": scene.frame_current,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "object_count": len(obj_list),
        "objects": obj_list,
        "total_vertices": total_verts if detailed else None,
        "total_faces": total_faces if detailed else None,
        "isError": False,
    }


def get_object_info(name: str) -> Dict[str, Any]:
    """
    Retrieve deep inspect data for a specific 3D object.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    obj = bpy.data.objects.get(name)
    if not obj:
        raise ObjectNotFoundError(
            f"Object '{name}' not found in scene.",
            details={"target": name, "available_objects": _get_available_objects()},
        )

    bbox = [list(pt) for pt in obj.bound_box]
    res: Dict[str, Any] = {
        "status": "success",
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "dimensions": list(obj.dimensions),
        "bbox": bbox,
        "parent": obj.parent.name if obj.parent else None,
        "children": [c.name for c in obj.children],
        "modifiers": [{"name": m.name, "type": m.type} for m in obj.modifiers],
        "materials": [slot.material.name for slot in obj.material_slots if slot.material],
        "isError": False,
    }

    if obj.type == "MESH" and obj.data:
        res["vertex_count"] = len(obj.data.vertices)
        res["polygon_count"] = len(obj.data.polygons)
        res["edge_count"] = len(obj.data.edges)

    return res


# ==============================================================================
# Category B: PBR Shading & Materials
# ==============================================================================

def create_material(
    material_name: str,
    use_nodes: bool = True,
) -> Dict[str, Any]:
    """
    Initialize a new material with a modern Principled BSDF node setup.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    if not material_name:
        raise InvalidParamsError("Parameter 'material_name' is required.")

    mat = bpy.data.materials.get(material_name)
    if not mat:
        mat = bpy.data.materials.new(name=material_name)

    mat.use_nodes = use_nodes
    if use_nodes:
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        bsdf = nodes.get("Principled BSDF")
        if not bsdf:
            bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
            bsdf.name = "Principled BSDF"

        output = nodes.get("Material Output")
        if not output:
            output = nodes.new(type="ShaderNodeOutputMaterial")
            output.name = "Material Output"

        # Ensure BSDF is connected to Surface output
        surface_input = output.inputs.get("Surface")
        if surface_input and not surface_input.is_linked:
            links.new(bsdf.outputs["BSDF"], surface_input)

    return {
        "status": "success",
        "material_name": mat.name,
        "use_nodes": mat.use_nodes,
        "isError": False,
    }


def assign_material(
    object_name: str,
    material_name: str,
    slot_index: int = 0,
) -> Dict[str, Any]:
    """
    Assign a material to an object or specific material slot.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    obj = bpy.data.objects.get(object_name)
    if not obj:
        raise ObjectNotFoundError(
            f"Object '{object_name}' not found for material assignment.",
            details={"target": object_name, "available_objects": _get_available_objects()},
        )

    mat = bpy.data.materials.get(material_name)
    if not mat:
        raise MaterialShaderError(
            f"Material '{material_name}' does not exist.",
            details={"material_name": material_name},
        )

    if hasattr(obj, "data") and hasattr(obj.data, "materials"):
        while len(obj.data.materials) <= slot_index:
            obj.data.materials.append(None)
        obj.data.materials[slot_index] = mat

    return {
        "status": "success",
        "object_name": obj.name,
        "material_name": mat.name,
        "slot_index": slot_index,
        "isError": False,
    }


def configure_pbr(
    material_name: str,
    base_color: Optional[List[float]] = None,
    metallic: Optional[float] = None,
    roughness: Optional[float] = None,
    ior: Optional[float] = None,
    transmission_weight: Optional[float] = None,
    alpha: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Configure Principled BSDF socket values with version-aware socket normalization.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    mat = bpy.data.materials.get(material_name)
    if not mat:
        raise MaterialShaderError(
            f"Material '{material_name}' not found.",
            details={"material_name": material_name},
        )

    if not mat.use_nodes or not mat.node_tree:
        raise MaterialShaderError(f"Material '{material_name}' does not use nodes.")

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        raise MaterialShaderError(f"Principled BSDF node not found in material '{material_name}'.")

    updated: Dict[str, Any] = {}

    def _set_socket(socket_aliases: List[str], val: Any) -> Optional[str]:
        for alias in socket_aliases:
            sock = bsdf.inputs.get(alias)
            if sock:
                sock.default_value = val
                return alias
        return None

    if base_color is not None:
        col4 = list(base_color) + [1.0] * (4 - len(base_color))
        _set_socket(["Base Color"], col4)
        updated["base_color"] = col4

    if metallic is not None:
        _set_socket(["Metallic"], float(metallic))
        updated["metallic"] = float(metallic)

    if roughness is not None:
        _set_socket(["Roughness"], float(roughness))
        updated["roughness"] = float(roughness)

    if ior is not None:
        _set_socket(["IOR"], float(ior))
        updated["ior"] = float(ior)

    if transmission_weight is not None:
        _set_socket(["Transmission Weight", "Transmission"], float(transmission_weight))
        updated["transmission_weight"] = float(transmission_weight)

    if alpha is not None:
        _set_socket(["Alpha"], float(alpha))
        updated["alpha"] = float(alpha)

    return {
        "status": "success",
        "material_name": mat.name,
        "updated": updated,
        "isError": False,
    }


def set_pbr_textures(
    material_name: str,
    base_color_texture: Optional[str] = None,
    roughness_texture: Optional[str] = None,
    metallic_texture: Optional[str] = None,
    normal_map_texture: Optional[str] = None,
    emission_texture: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Connect texture image files to Principled BSDF shader sockets with appropriate color spaces.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    mat = bpy.data.materials.get(material_name)
    if not mat:
        raise MaterialShaderError(f"Material '{material_name}' not found.")

    if not mat.use_nodes:
        mat.use_nodes = True

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        raise MaterialShaderError(f"Principled BSDF node not found in material '{material_name}'.")

    # Validate file paths before modifying nodes
    textures: Dict[str, Optional[str]] = {
        "base_color": base_color_texture,
        "roughness": roughness_texture,
        "metallic": metallic_texture,
        "normal_map": normal_map_texture,
        "emission": emission_texture,
    }

    for tex_key, path in textures.items():
        if path and not os.path.isfile(path):
            raise MaterialShaderError(
                f"Texture file for '{tex_key}' not found at: '{path}'",
                details={"texture_type": tex_key, "path": path},
            )

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    connected: List[str] = []

    def _add_image_node(img_path: str, color_space: str) -> Any:
        img = bpy.data.images.load(img_path, check_existing=True)
        img.colorspace_settings.name = color_space
        tex_node = nodes.new(type="ShaderNodeTexImage")
        tex_node.image = img
        return tex_node

    if base_color_texture:
        node = _add_image_node(base_color_texture, "sRGB")
        target_sock = bsdf.inputs.get("Base Color")
        if target_sock:
            links.new(node.outputs["Color"], target_sock)
            connected.append("base_color")

    if emission_texture:
        node = _add_image_node(emission_texture, "sRGB")
        target_sock = bsdf.inputs.get("Emission Color")
        if target_sock:
            links.new(node.outputs["Color"], target_sock)
            connected.append("emission")

    if roughness_texture:
        node = _add_image_node(roughness_texture, "Non-Color")
        target_sock = bsdf.inputs.get("Roughness")
        if target_sock:
            links.new(node.outputs["Color"], target_sock)
            connected.append("roughness")

    if metallic_texture:
        node = _add_image_node(metallic_texture, "Non-Color")
        target_sock = bsdf.inputs.get("Metallic")
        if target_sock:
            links.new(node.outputs["Color"], target_sock)
            connected.append("metallic")

    if normal_map_texture:
        img_node = _add_image_node(normal_map_texture, "Non-Color")
        norm_node = nodes.new(type="ShaderNodeNormalMap")
        links.new(img_node.outputs["Color"], norm_node.inputs["Color"])
        target_sock = bsdf.inputs.get("Normal")
        if target_sock:
            links.new(norm_node.outputs["Normal"], target_sock)
            connected.append("normal_map")

    return {
        "status": "success",
        "material_name": mat.name,
        "connected_textures": connected,
        "isError": False,
    }


def set_emission(
    material_name: str,
    emission_color: Optional[List[float]] = None,
    emission_strength: float = 1.0,
) -> Dict[str, Any]:
    """
    Adjust emission color and radiant strength on Principled BSDF.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    mat = bpy.data.materials.get(material_name)
    if not mat:
        raise MaterialShaderError(f"Material '{material_name}' not found.")

    if not mat.use_nodes or not mat.node_tree:
        raise MaterialShaderError(f"Material '{material_name}' does not use nodes.")

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        raise MaterialShaderError("Principled BSDF node not found.")

    if emission_color is not None:
        col4 = list(emission_color) + [1.0] * (4 - len(emission_color))
        sock_col = bsdf.inputs.get("Emission Color")
        if sock_col:
            sock_col.default_value = col4

    sock_str = bsdf.inputs.get("Emission Strength")
    if sock_str:
        sock_str.default_value = float(emission_strength)

    return {
        "status": "success",
        "material_name": mat.name,
        "emission_color": list(bsdf.inputs["Emission Color"].default_value) if bsdf.inputs.get("Emission Color") else None,
        "emission_strength": float(emission_strength),
        "isError": False,
    }


# ==============================================================================
# Category C: Auto-Rigging & Armatures
# ==============================================================================

def create_armature(
    armature_name: str = "Armature",
    bones: Optional[List[Dict[str, Any]]] = None,
    display_type: str = "OCTAHEDRAL",
) -> Dict[str, Any]:
    """
    Generate an Armature object with designated bone hierarchy and 3D head/tail vectors.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    if not bones:
        raise ArmatureRiggingError("At least one bone definition is required in 'bones' list.")

    _ensure_object_mode()

    arm_data = bpy.data.armatures.new(name=armature_name)
    arm_obj = bpy.data.objects.new(name=armature_name, object_data=arm_data)
    bpy.context.scene.collection.objects.link(arm_obj)

    bpy.ops.object.select_all(action="DESELECT")
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj

    # Enter EDIT mode to build bones
    bpy.ops.object.mode_set(mode="EDIT")

    created_bones: Dict[str, Any] = {}
    for b_info in bones:
        b_name = b_info["name"]
        head = b_info["head"]
        tail = b_info["tail"]
        eb = arm_data.edit_bones.new(b_name)
        eb.head = tuple(head)
        eb.tail = tuple(tail)
        created_bones[b_name] = eb

    # Setup bone parenting hierarchy
    for b_info in bones:
        b_name = b_info["name"]
        parent_name = b_info.get("parent")
        if parent_name and parent_name in created_bones:
            created_bones[b_name].parent = created_bones[parent_name]
            if b_info.get("use_connect", False):
                created_bones[b_name].use_connect = True

    bpy.ops.object.mode_set(mode="OBJECT")
    arm_data.display_type = display_type

    return {
        "status": "success",
        "armature_name": arm_obj.name,
        "bone_count": len(arm_data.bones),
        "bones": [b.name for b in arm_data.bones],
        "isError": False,
    }


def bind_skin_weights(
    mesh_name: str,
    armature_name: str,
    bind_type: str = "AUTOMATIC",
) -> Dict[str, Any]:
    """
    Parent a mesh to an armature and compute automatic skin weights (bone heat weighting).
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    mesh_obj = bpy.data.objects.get(mesh_name)
    arm_obj = bpy.data.objects.get(armature_name)

    if not mesh_obj:
        raise ObjectNotFoundError(f"Mesh object '{mesh_name}' not found.", details={"target": mesh_name})
    if not arm_obj:
        raise ObjectNotFoundError(f"Armature object '{armature_name}' not found.", details={"target": armature_name})
    if arm_obj.type != "ARMATURE":
        raise ArmatureRiggingError(f"Target '{armature_name}' is not an ARMATURE (type: {arm_obj.type}).")

    _ensure_object_mode()

    bpy.ops.object.select_all(action="DESELECT")
    mesh_obj.select_set(True)
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj

    parent_type_map = {
        "AUTOMATIC": "ARMATURE_AUTO",
        "ENVELOPE": "ARMATURE_ENVELOPE",
        "EMPTY_GROUPS": "ARMATURE_NAME",
    }
    ptype = parent_type_map.get(bind_type.upper(), "ARMATURE_AUTO")

    try:
        bpy.ops.object.parent_set(type=ptype)
    except Exception as e:
        raise ArmatureRiggingError(
            f"Bone heat skin weighting failed: {e}",
            details={"mesh": mesh_name, "armature": armature_name, "bind_type": bind_type},
        )

    vg_count = len(mesh_obj.vertex_groups)
    return {
        "status": "success",
        "mesh_name": mesh_obj.name,
        "armature_name": arm_obj.name,
        "bind_type": bind_type,
        "vertex_groups": vg_count,
        "isError": False,
    }


def setup_ik_constraint(
    armature_name: str,
    bone_name: str,
    target_object: str,
    target_subtarget: Optional[str] = None,
    chain_length: int = 2,
    pole_target: Optional[str] = None,
    pole_subtarget: Optional[str] = None,
    pole_angle: float = 0.0,
) -> Dict[str, Any]:
    """
    Configure Inverse Kinematics (IK) constraint on an armature pose bone.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    arm_obj = bpy.data.objects.get(armature_name)
    if not arm_obj or arm_obj.type != "ARMATURE":
        raise ArmatureRiggingError(f"Armature object '{armature_name}' not found.")

    target = bpy.data.objects.get(target_object)
    if not target:
        raise ObjectNotFoundError(f"IK target object '{target_object}' not found.")

    pbone = arm_obj.pose.bones.get(bone_name)
    if not pbone:
        raise ArmatureRiggingError(
            f"Pose bone '{bone_name}' not found in armature '{armature_name}'.",
            details={"armature": armature_name, "bone": bone_name},
        )

    # Find or create IK constraint
    ik_con = None
    for con in pbone.constraints:
        if con.type == "IK":
            ik_con = con
            break

    if not ik_con:
        ik_con = pbone.constraints.new(type="IK")

    ik_con.target = target
    if target_subtarget:
        ik_con.subtarget = target_subtarget
    ik_con.chain_length = max(0, int(chain_length))

    if pole_target:
        p_obj = bpy.data.objects.get(pole_target)
        if p_obj:
            ik_con.pole_target = p_obj
            if pole_subtarget:
                ik_con.pole_subtarget = pole_subtarget
            ik_con.pole_angle = float(pole_angle)

    return {
        "status": "success",
        "armature_name": arm_obj.name,
        "bone_name": bone_name,
        "constraint": "IK",
        "chain_length": ik_con.chain_length,
        "target": target.name,
        "subtarget": target_subtarget,
        "isError": False,
    }


# ==============================================================================
# Category D: Cinematic Lighting & Camera Control
# ==============================================================================

def setup_light(
    light_name: Optional[str] = None,
    light_type: str = "POINT",
    energy: float = 100.0,
    color: Optional[List[float]] = None,
    location: Optional[List[float]] = None,
    size: Optional[float] = None,
    spot_size: Optional[float] = None,
    spot_blend: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Create or configure a light source (Sun, Point, Spot, Area).
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    valid_types = ["POINT", "SUN", "SPOT", "AREA"]
    ltype = light_type.upper().strip()
    if ltype not in valid_types:
        raise InvalidParamsError(f"Invalid light_type '{light_type}'. Valid: {valid_types}")

    lname = light_name or f"{ltype.capitalize()}_Light"
    light_data = bpy.data.lights.get(lname)
    if not light_data:
        light_data = bpy.data.lights.new(name=lname, type=ltype)
    else:
        light_data.type = ltype

    light_data.energy = float(energy)
    if color:
        light_data.color = tuple(color[:3])

    if size is not None and hasattr(light_data, "size"):
        light_data.size = float(size)

    if spot_size is not None and hasattr(light_data, "spot_size"):
        light_data.spot_size = float(spot_size)

    if spot_blend is not None and hasattr(light_data, "spot_blend"):
        light_data.spot_blend = float(spot_blend)

    light_obj = bpy.data.objects.get(lname)
    if not light_obj:
        light_obj = bpy.data.objects.new(name=lname, object_data=light_data)
        bpy.context.scene.collection.objects.link(light_obj)

    if location is not None:
        light_obj.location = tuple(location)

    return {
        "status": "success",
        "light_name": light_obj.name,
        "light_type": light_data.type,
        "energy": light_data.energy,
        "color": list(light_data.color),
        "location": list(light_obj.location),
        "isError": False,
    }


def setup_world_hdri(
    color: Optional[List[float]] = None,
    strength: float = 1.0,
    hdri_path: Optional[str] = None,
    rotation_z: float = 0.0,
) -> Dict[str, Any]:
    """
    Configure world environment lighting and HDRI background texture.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    scene = bpy.context.scene
    world = scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        scene.world = world

    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    bg = nodes.get("Background")
    if not bg:
        bg = nodes.new(type="ShaderNodeBackground")

    bg.inputs["Strength"].default_value = float(strength)

    if hdri_path:
        if not os.path.isfile(hdri_path):
            raise LightingCameraError(f"HDRI file not found at: '{hdri_path}'", details={"hdri_path": hdri_path})

        img = bpy.data.images.load(hdri_path, check_existing=True)
        env_node = nodes.get("Environment Texture") or nodes.new(type="ShaderNodeTexEnvironment")
        env_node.image = img

        tex_coord = nodes.get("Texture Coordinate") or nodes.new(type="ShaderNodeTexCoord")
        mapping = nodes.get("Mapping") or nodes.new(type="ShaderNodeMapping")
        mapping.inputs["Rotation"].default_value[2] = float(rotation_z)

        links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], env_node.inputs["Vector"])
        links.new(env_node.outputs["Color"], bg.inputs["Color"])

    elif color is not None:
        bg.inputs["Color"].default_value = list(color[:3]) + [1.0]

    output = nodes.get("World Output") or nodes.new(type="ShaderNodeOutputWorld")
    if not output.inputs["Surface"].is_linked:
        links.new(bg.outputs["Background"], output.inputs["Surface"])

    return {
        "status": "success",
        "world_nodes": True,
        "strength": float(strength),
        "hdri_applied": bool(hdri_path),
        "isError": False,
    }


def setup_camera(
    camera_name: str = "Camera",
    location: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    focal_length: float = 50.0,
    sensor_width: float = 36.0,
    dof_target: Optional[str] = None,
    dof_fstop: float = 2.8,
    set_active: bool = True,
) -> Dict[str, Any]:
    """
    Create or configure camera parameters (focal length, sensor, depth of field).
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    cam_data = bpy.data.cameras.get(camera_name)
    if not cam_data:
        cam_data = bpy.data.cameras.new(name=camera_name)

    cam_data.lens = float(focal_length)
    cam_data.sensor_width = float(sensor_width)

    if dof_target:
        target = bpy.data.objects.get(dof_target)
        if not target:
            raise ObjectNotFoundError(f"DOF target object '{dof_target}' not found.")
        cam_data.dof.use_dof = True
        cam_data.dof.focus_object = target
        cam_data.dof.aperture_fstop = float(dof_fstop)

    cam_obj = bpy.data.objects.get(camera_name)
    if not cam_obj:
        cam_obj = bpy.data.objects.new(name=camera_name, object_data=cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)

    if location is not None:
        cam_obj.location = tuple(location)
    if rotation is not None:
        cam_obj.rotation_euler = tuple(rotation)

    if set_active:
        bpy.context.scene.camera = cam_obj

    return {
        "status": "success",
        "camera_name": cam_obj.name,
        "focal_length": cam_data.lens,
        "sensor_width": cam_data.sensor_width,
        "location": list(cam_obj.location),
        "rotation": list(cam_obj.rotation_euler),
        "is_active": bpy.context.scene.camera == cam_obj,
        "isError": False,
    }


def camera_track_to(
    target_object: str,
    camera_name: Optional[str] = None,
    track_axis: str = "TRACK_NEG_Z",
    up_axis: str = "UP_Y",
) -> Dict[str, Any]:
    """
    Add a Track-To constraint to lock camera focus on a target object.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    if camera_name:
        cam_obj = bpy.data.objects.get(camera_name)
    else:
        cam_obj = bpy.context.scene.camera

    if not cam_obj:
        raise LightingCameraError(f"Camera '{camera_name or 'active'}' not found in scene.")

    target = bpy.data.objects.get(target_object)
    if not target:
        raise ObjectNotFoundError(f"Track-to target '{target_object}' not found.")

    if target.parent == cam_obj:
        raise HierarchyCycleError(f"Cannot track camera '{cam_obj.name}' to its child '{target_object}'.")

    con = None
    for c in cam_obj.constraints:
        if c.type == "TRACK_TO":
            con = c
            break

    if not con:
        con = cam_obj.constraints.new(type="TRACK_TO")

    axis_map = {
        "TRACK_NEG_Z": "TRACK_NEGATIVE_Z",
        "TRACK_NEG_X": "TRACK_NEGATIVE_X",
        "TRACK_NEG_Y": "TRACK_NEGATIVE_Y",
        "TRACK_NEGATIVE_Z": "TRACK_NEGATIVE_Z",
        "TRACK_NEGATIVE_X": "TRACK_NEGATIVE_X",
        "TRACK_NEGATIVE_Y": "TRACK_NEGATIVE_Y",
        "-Z": "TRACK_NEGATIVE_Z",
        "-X": "TRACK_NEGATIVE_X",
        "-Y": "TRACK_NEGATIVE_Y",
        "TRACK_Z": "TRACK_Z",
        "TRACK_X": "TRACK_X",
        "TRACK_Y": "TRACK_Y",
        "Z": "TRACK_Z",
        "X": "TRACK_X",
        "Y": "TRACK_Y",
    }
    con.track_axis = axis_map.get(track_axis.upper(), track_axis.upper())

    up_map = {
        "UP_X": "UP_X",
        "UP_Y": "UP_Y",
        "UP_Z": "UP_Z",
        "X": "UP_X",
        "Y": "UP_Y",
        "Z": "UP_Z",
    }
    con.up_axis = up_map.get(up_axis.upper(), up_axis.upper())

    return {
        "status": "success",
        "camera_name": cam_obj.name,
        "target": target.name,
        "track_axis": track_axis,
        "up_axis": up_axis,
        "isError": False,
    }


# ==============================================================================
# Category E: Render Engine & Viewport Capture
# ==============================================================================

def configure_render_engine(
    engine: str,
    device: str = "GPU",
    resolution_x: int = 1920,
    resolution_y: int = 1080,
    samples: int = 64,
    film_transparent: bool = False,
) -> Dict[str, Any]:
    """
    Switch render engines (Cycles vs Eevee), configure resolution, samples, and transparency.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    scene = bpy.context.scene
    engine_raw = engine.upper().strip()

    # Map Eevee Next to available Eevee engine in current Blender build
    if engine_raw in ("BLENDER_EEVEE_NEXT", "EEVEE", "BLENDER_EEVEE"):
        engine_mapped = "BLENDER_EEVEE"
    elif engine_raw in ("WORKBENCH", "BLENDER_WORKBENCH"):
        engine_mapped = "BLENDER_WORKBENCH"
    elif engine_raw in ("CYCLES",):
        engine_mapped = "CYCLES"
    else:
        raise RenderEngineError(f"Unsupported render engine: '{engine}'. Valid: CYCLES, BLENDER_EEVEE_NEXT, BLENDER_WORKBENCH.")

    scene.render.engine = engine_mapped
    scene.render.resolution_x = int(resolution_x)
    scene.render.resolution_y = int(resolution_y)
    scene.render.film_transparent = bool(film_transparent)

    if engine_mapped == "CYCLES":
        if hasattr(scene.cycles, "device"):
            scene.cycles.device = device.upper()
        scene.cycles.samples = int(samples)
    elif hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = int(samples)

    return {
        "status": "success",
        "engine": scene.render.engine,
        "device": device,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "samples": samples,
        "film_transparent": film_transparent,
        "isError": False,
    }


def render_frame(
    output_path: str,
    frame: Optional[int] = None,
    file_format: str = "PNG",
) -> Dict[str, Any]:
    """
    Render still frame to file.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    scene = bpy.context.scene
    if frame is not None:
        scene.frame_set(int(frame))

    abs_output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)

    scene.render.filepath = abs_output
    scene.render.image_settings.file_format = file_format.upper()

    t0 = time.perf_counter()
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as e:
        raise RenderEngineError(f"Render execution failed: {e}", details={"output_path": abs_output, "frame": scene.frame_current})

    render_time = round(time.perf_counter() - t0, 3)

    return {
        "status": "success",
        "output_path": abs_output,
        "frame": scene.frame_current,
        "render_time_seconds": render_time,
        "isError": False,
    }


def get_viewport_screenshot(
    max_dimension: int = 1024,
    shading_type: str = "MATERIAL",
    camera_view: bool = True,
) -> Dict[str, Any]:
    """
    Capture 3D viewport / offscreen render formatted as base64 PNG data.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    scene = bpy.context.scene

    # Save current render parameters
    orig_rx = scene.render.resolution_x
    orig_ry = scene.render.resolution_y
    orig_fp = scene.render.filepath

    # Scale resolution to max_dimension for token economy
    scale = 1.0
    longest = max(orig_rx, orig_ry)
    if longest > max_dimension:
        scale = max_dimension / longest

    scaled_x = max(16, int(orig_rx * scale))
    scaled_y = max(16, int(orig_ry * scale))
    scene.render.resolution_x = scaled_x
    scene.render.resolution_y = scaled_y

    temp_path = os.path.join(tempfile.gettempdir(), f"mcp_viewport_{uuid.uuid4().hex[:8]}.png")
    scene.render.filepath = temp_path

    try:
        bpy.ops.render.render(write_still=True)
        with open(temp_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        raise ViewportCaptureError(f"Viewport capture failed: {e}", details={"resolution": [scaled_x, scaled_y]})
    finally:
        scene.render.resolution_x = orig_rx
        scene.render.resolution_y = orig_ry
        scene.render.filepath = orig_fp
        if os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    active_cam = scene.camera.name if scene.camera else "Default View"
    return {
        "status": "success",
        "image_base64": b64_data,
        "mime_type": "image/png",
        "resolution": [scaled_x, scaled_y],
        "camera": active_cam,
        "shading": shading_type,
        "isError": False,
    }


def execute_code(code: str, strict_json: bool = False) -> Dict[str, Any]:
    """
    Fallback execution of arbitrary Python script within Blender main-thread namespace.
    """
    if bpy is None:
        raise InternalError("Blender runtime (bpy) is not loaded.")

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    local_ns: Dict[str, Any] = {
        "bpy": bpy,
        "mathutils": mathutils,
        "result": None,
    }

    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            exec(code, local_ns)
        return {
            "status": "success",
            "result": local_ns.get("result"),
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "isError": False,
        }
    except Exception as exc:
        raise ScriptSyntaxError(
            str(exc),
            details={
                "code": code,
                "stdout": stdout_buf.getvalue(),
                "stderr": stderr_buf.getvalue(),
                "traceback": traceback.format_exc(),
            },
        )


# ==============================================================================
# Master Operations Dispatcher
# ==============================================================================

OPERATIONS_MAP: Dict[str, Any] = {
    "manage_object": manage_object,
    "transform_object": transform_object,
    "manage_hierarchy": manage_hierarchy,
    "get_scene_info": get_scene_info,
    "get_object_info": get_object_info,
    "create_material": create_material,
    "assign_material": assign_material,
    "configure_pbr": configure_pbr,
    "set_pbr_textures": set_pbr_textures,
    "set_emission": set_emission,
    "create_armature": create_armature,
    "bind_skin_weights": bind_skin_weights,
    "setup_ik_constraint": setup_ik_constraint,
    "setup_light": setup_light,
    "setup_world_hdri": setup_world_hdri,
    "setup_camera": setup_camera,
    "camera_track_to": camera_track_to,
    "configure_render_engine": configure_render_engine,
    "render_frame": render_frame,
    "get_viewport_screenshot": get_viewport_screenshot,
    "execute_code": execute_code,
}


def dispatch_op(op_name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Main dispatch entry point called by the bridge/daemon.
    Ensures structured exception handling and zero unhandled crashes.
    """
    fn = OPERATIONS_MAP.get(op_name)
    if not fn:
        return format_error_payload(
            MethodNotFoundError(f"Operation '{op_name}' not recognized."),
            details={"op_name": op_name, "available_ops": list(OPERATIONS_MAP.keys())},
        )

    try:
        res = fn(**(params or {}))
        if isinstance(res, dict):
            res.setdefault("status", "success")
            res.setdefault("isError", False)
        return res
    except BlenderMCPError as bme:
        return format_error_payload(bme)
    except Exception as exc:
        tb = traceback.format_exc()
        return format_error_payload(InternalError(str(exc)), tb=tb)
