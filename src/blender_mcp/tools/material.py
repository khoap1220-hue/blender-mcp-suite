"""
src/blender_mcp/tools/material.py — PBR Shading & Material Tools

Covers:
- blender_create_material: Initialize new material with Principled BSDF node setup.
- blender_assign_material: Assign material to object and target slot.
- blender_configure_pbr: Configure standard Principled BSDF socket values.
- blender_set_pbr_textures: Connect texture image files with proper color spaces.
- blender_set_emission: Configure emission radiant color and intensity.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp.types import CallToolResult

from blender_mcp.error_boundary import error_boundary


@error_boundary
def blender_create_material(
    material_name: str,
    use_nodes: bool = True,
) -> CallToolResult:
    """
    Initialize a new material with a modern Principled BSDF node setup.

    Parameters:
        material_name: Name of the material to create.
        use_nodes: Enable shader node graph for PBR shading.
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "material_name": material_name,
        "use_nodes": use_nodes,
    }
    return execute_bridge_op("create_material", params)


@error_boundary
def blender_assign_material(
    object_name: str,
    material_name: str,
    slot_index: int = 0,
) -> CallToolResult:
    """
    Assign a material to a target 3D object or specific material slot.

    Parameters:
        object_name: Name of the target mesh or surface object.
        material_name: Name of the material to assign.
        slot_index: Material slot index (default: 0 for primary material).
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "object_name": object_name,
        "material_name": material_name,
        "slot_index": slot_index,
    }
    return execute_bridge_op("assign_material", params)


@error_boundary
def blender_configure_pbr(
    material_name: str,
    base_color: Optional[List[float]] = None,
    metallic: Optional[float] = None,
    roughness: Optional[float] = None,
    ior: Optional[float] = None,
    transmission_weight: Optional[float] = None,
    alpha: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Configure Principled BSDF socket values (Base Color, Metallic, Roughness, IOR, Alpha).

    Parameters:
        material_name: Name of the target material.
        base_color: RGB or RGBA color components [r, g, b, (a)] between 0.0 and 1.0.
        metallic: Metallic reflectivity factor (0.0 to 1.0).
        roughness: Surface microfacet roughness (0.0 to 1.0).
        ior: Index of Refraction (e.g. 1.45 for glass, 1.33 for water).
        transmission_weight: Glass / transmission transparency factor (0.0 to 1.0).
        alpha: Surface opacity factor (0.0 to 1.0).
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "material_name": material_name,
        "base_color": base_color,
        "metallic": metallic,
        "roughness": roughness,
        "ior": ior,
        "transmission_weight": transmission_weight,
        "alpha": alpha,
    }
    return execute_bridge_op("configure_pbr", params)


@error_boundary
def blender_set_pbr_textures(
    material_name: str,
    base_color_texture: Optional[str] = None,
    roughness_texture: Optional[str] = None,
    metallic_texture: Optional[str] = None,
    normal_map_texture: Optional[str] = None,
    emission_texture: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Connect texture image files to Principled BSDF shader sockets with appropriate color spaces.

    Parameters:
        material_name: Target material name.
        base_color_texture: Absolute path to Base Color image (sRGB).
        roughness_texture: Absolute path to Roughness image (Non-Color).
        metallic_texture: Absolute path to Metallic image (Non-Color).
        normal_map_texture: Absolute path to Normal map image (Non-Color, via Normal Map node).
        emission_texture: Absolute path to Emission map image (sRGB).
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "material_name": material_name,
        "base_color_texture": base_color_texture,
        "roughness_texture": roughness_texture,
        "metallic_texture": metallic_texture,
        "normal_map_texture": normal_map_texture,
        "emission_texture": emission_texture,
    }
    return execute_bridge_op("set_pbr_textures", params)


@error_boundary
def blender_set_emission(
    material_name: str,
    emission_color: Optional[List[float]] = None,
    emission_strength: float = 1.0,
) -> Dict[str, Any]:
    """
    Adjust emission color and radiant intensity multiplier on Principled BSDF.

    Parameters:
        material_name: Target material name.
        emission_color: Emission light tint [r, g, b, (a)].
        emission_strength: Emission radiant intensity factor (default: 1.0).
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "material_name": material_name,
        "emission_color": emission_color,
        "emission_strength": emission_strength,
    }
    return execute_bridge_op("set_emission", params)
