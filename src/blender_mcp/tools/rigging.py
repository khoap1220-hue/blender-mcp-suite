"""
src/blender_mcp/tools/rigging.py — Auto-Rigging & Armature Tools

Covers:
- blender_create_armature: Generate armature with edit bone hierarchies.
- blender_bind_skin_weights: Parent mesh to armature with automatic bone heat weights.
- blender_setup_ik_constraint: Add and configure Inverse Kinematics constraint on pose bones.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp.types import CallToolResult

from blender_mcp.error_boundary import error_boundary


@error_boundary
def blender_create_armature(
    bones: List[Dict[str, Any]],
    armature_name: str = "Armature",
    display_type: str = "OCTAHEDRAL",
) -> CallToolResult:
    """
    Generate an Armature object with designated bone hierarchy and 3D head/tail coordinates.

    Parameters:
        bones: List of bone dicts, each with keys:
               - name: (str) identifier
               - head: [x, y, z] starting position
               - tail: [x, y, z] end position
               - parent: (optional str) parent bone name
               - use_connect: (optional bool) connect head to parent tail
        armature_name: Name of the Armature object to create (default: "Armature").
        display_type: Viewport display mode ("OCTAHEDRAL", "STICK", "BBONE", "WIRE").
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "bones": bones,
        "armature_name": armature_name,
        "display_type": display_type,
    }
    return execute_bridge_op("create_armature", params)


@error_boundary
def blender_bind_skin_weights(
    mesh_name: str,
    armature_name: str,
    bind_type: str = "AUTOMATIC",
) -> CallToolResult:
    """
    Parent a mesh to an armature and compute automatic skin weights (bone heat weighting).

    Parameters:
        mesh_name: Exact name of the mesh object to bind and deform.
        armature_name: Exact name of the governing armature object.
        bind_type: Weighting algorithm ("AUTOMATIC", "ENVELOPE", "EMPTY_GROUPS").
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "mesh_name": mesh_name,
        "armature_name": armature_name,
        "bind_type": bind_type,
    }
    return execute_bridge_op("bind_skin_weights", params)


@error_boundary
def blender_setup_ik_constraint(
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

    Parameters:
        armature_name: Exact name of the armature hosting the bone.
        bone_name: Pose bone name receiving the IK constraint (e.g. "LowerLeg", "Forearm").
        target_object: Object or armature hosting the IK target.
        target_subtarget: Bone within target object acting as IK effector.
        chain_length: Number of bones up the hierarchy influenced by IK (default: 2).
        pole_target: Pole target object for knee/elbow joint direction.
        pole_subtarget: Specific bone inside pole target object.
        pole_angle: Pole angle adjustment in radians (default: 0.0).
    """
    from blender_mcp.tools import execute_bridge_op

    params: Dict[str, Any] = {
        "armature_name": armature_name,
        "bone_name": bone_name,
        "target_object": target_object,
        "target_subtarget": target_subtarget,
        "chain_length": chain_length,
        "pole_target": pole_target,
        "pole_subtarget": pole_subtarget,
        "pole_angle": pole_angle,
    }
    return execute_bridge_op("setup_ik_constraint", params)
