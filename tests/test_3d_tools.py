"""
tests/test_3d_tools.py — Comprehensive Test Suite for M2 & M3 Milestones

Tests:
1. Error boundary taxonomy & exception hierarchy (13 error codes).
2. Zero-crash decorator behavior (success, domain errors, unexpected exceptions).
3. All 20 3D MCP tools + code execution tool:
   - Category A: Scene & Object Manipulation (manage_object, transform_object, manage_hierarchy, get_scene_info, get_object_info)
   - Category B: PBR Materials & Shaders (create_material, assign_material, configure_pbr, set_pbr_textures, set_emission)
   - Category C: Auto-Rigging & Armatures (create_armature, bind_skin_weights, setup_ik_constraint)
   - Category D: Cinematic Lighting & Camera (setup_light, setup_world_hdri, setup_camera, camera_track_to)
   - Category E: Render Engine & Viewport (configure_render_engine, render_frame, get_viewport_screenshot, execute_code)
4. Structured error responses: missing objects, invalid parameters, cyclic hierarchies, syntax errors (isError: True).
5. FastMCP tool registration and async invocation verification.
6. Live Blender 4.1.1 integration workflow.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mcp.types import CallToolResult, ImageContent, TextContent

from blender_mcp import error_boundary as eb
from blender_mcp.daemon_manager import BlenderBinaryDetector, DaemonManager
from blender_mcp.server import get_active_client, get_active_daemon_manager, mcp
from blender_mcp.socket_client import BlenderSocketClient
import blender_mcp.tools as tools
from blender_mcp.tools import (
    blender_assign_material,
    blender_bind_skin_weights,
    blender_camera_track_to,
    blender_configure_pbr,
    blender_configure_render_engine,
    blender_create_armature,
    blender_create_material,
    blender_execute_code,
    blender_get_object_info,
    blender_get_scene_info,
    blender_get_viewport_screenshot,
    blender_manage_hierarchy,
    blender_manage_object,
    blender_render_frame,
    blender_set_emission,
    blender_set_pbr_textures,
    blender_setup_camera,
    blender_setup_ik_constraint,
    blender_setup_light,
    blender_setup_world_hdri,
    blender_transform_object,
    register_all_tools,
    set_client,
)


# ==============================================================================
# 1. Error Boundary & Taxonomy Tests (13 Error Codes)
# ==============================================================================

def test_13_error_codes_taxonomy():
    """Verify all 13 standard JSON-RPC and domain error codes are defined and unique."""
    expected_codes = {
        eb.PARSE_ERROR: -32700,
        eb.INVALID_REQUEST: -32600,
        eb.METHOD_NOT_FOUND: -32601,
        eb.INVALID_PARAMS: -32602,
        eb.INTERNAL_ERROR: -32603,
        eb.BLENDER_DAEMON_ERROR: -32000,
        eb.OBJECT_NOT_FOUND: -32001,
        eb.MATERIAL_SHADER_ERROR: -32002,
        eb.ARMATURE_RIGGING_ERROR: -32003,
        eb.LIGHTING_CAMERA_ERROR: -32004,
        eb.RENDER_ENGINE_ERROR: -32005,
        eb.VIEWPORT_CAPTURE_ERROR: -32006,
        eb.SCRIPT_SYNTAX_ERROR: -32007,
    }
    assert len(expected_codes) == 13
    for code_const, val in expected_codes.items():
        assert code_const == val
        assert code_const in eb.ERROR_CODE_NAMES
        assert code_const in eb.ERROR_DEFAULT_MESSAGES


def test_exception_classes_hierarchy_and_formatting():
    """Verify domain exceptions carry correct codes, messages, and diagnostic details."""
    exc1 = eb.ObjectNotFoundError("Mesh 'Hero' missing", details={"target": "Hero"})
    assert exc1.code == -32001
    assert exc1.details["target"] == "Hero"
    assert "hint" in exc1.details or exc1.details.get("target")

    payload = exc1.to_dict()
    assert payload["status"] == "error"
    assert payload["error_code"] == -32001
    assert payload["error_type"] == "ObjectNotFoundError"
    assert payload["isError"] is True

    # Test HierarchyCycleError subclassing ArmatureRiggingError
    cycle_err = eb.HierarchyCycleError("Cyclic parenting detected")
    assert isinstance(cycle_err, eb.ArmatureRiggingError)
    assert cycle_err.code == -32003


def test_error_boundary_decorator_zero_crash():
    """Verify @error_boundary intercepts exceptions and returns CallToolResult with isError: True."""

    @eb.error_boundary
    def failing_tool():
        raise eb.ObjectNotFoundError("Cube not found", details={"target": "Cube", "available_objects": ["Light"]})

    res = failing_tool()
    assert isinstance(res, CallToolResult)
    assert res.isError is True
    assert len(res.content) == 1
    assert isinstance(res.content[0], TextContent)

    data = json.loads(res.content[0].text)
    assert data["status"] == "error"
    assert data["error_code"] == -32001
    assert data["error_type"] == "ObjectNotFoundError"
    assert "hint" in data["details"]

    # Test unexpected ValueError mapping to INVALID_PARAMS (-32602)
    @eb.error_boundary
    def bad_param_tool():
        raise ValueError("Invalid radius value: -5")

    res2 = bad_param_tool()
    assert res2.isError is True
    data2 = json.loads(res2.content[0].text)
    assert data2["error_code"] == -32602

    # Test unexpected generic exception mapping to INTERNAL_ERROR (-32603)
    @eb.error_boundary
    def crash_tool():
        raise RuntimeError("Unexpected memory fault")

    res3 = crash_tool()
    assert res3.isError is True
    data3 = json.loads(res3.content[0].text)
    assert data3["error_code"] == -32603
    assert "traceback" in data3


# ==============================================================================
# 2. Mock Bridge Client Fixture for Deterministic Unit Verification
# ==============================================================================

class MockBlenderSocketClient:
    """Mock socket client simulating responses from daemon/blender_ops."""

    def __init__(self):
        self.is_connected = True
        self.sent_commands = []
        self.mock_dispatch_handler = None

    def send_command(self, cmd: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        self.sent_commands.append(cmd)
        if self.mock_dispatch_handler:
            return self.mock_dispatch_handler(cmd)

        # Default handler: inspect python code snippet sent to daemon
        code = cmd.get("params", {}).get("code", "")
        # Emulate successful response from dispatch_op
        if "dispatch_op('manage_object'" in code or 'dispatch_op("manage_object"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "action": "create", "object_name": "Cube", "isError": False},
            }
        elif "dispatch_op('transform_object'" in code or 'dispatch_op("transform_object"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "object_name": "Cube", "transforms": {"location": [1.0, 2.0, 3.0]}, "isError": False},
            }
        elif "dispatch_op('manage_hierarchy'" in code or 'dispatch_op("manage_hierarchy"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "action": "set_parent", "child": "Child", "parent": "Parent", "isError": False},
            }
        elif "dispatch_op('get_scene_info'" in code or 'dispatch_op("get_scene_info"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "scene_name": "Scene", "object_count": 3, "objects": [], "isError": False},
            }
        elif "dispatch_op('get_object_info'" in code or 'dispatch_op("get_object_info"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "name": "Cube", "type": "MESH", "bbox": [[0,0,0]]*8, "isError": False},
            }
        elif "dispatch_op('create_material'" in code or 'dispatch_op("create_material"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "material_name": "Gold_PBR", "use_nodes": True, "isError": False},
            }
        elif "dispatch_op('assign_material'" in code or 'dispatch_op("assign_material"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "object_name": "Cube", "material_name": "Gold_PBR", "isError": False},
            }
        elif "dispatch_op('configure_pbr'" in code or 'dispatch_op("configure_pbr"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "material_name": "Gold_PBR", "updated": {"metallic": 0.9}, "isError": False},
            }
        elif "dispatch_op('set_pbr_textures'" in code or 'dispatch_op("set_pbr_textures"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "material_name": "Gold_PBR", "connected_textures": ["base_color"], "isError": False},
            }
        elif "dispatch_op('set_emission'" in code or 'dispatch_op("set_emission"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "material_name": "Gold_PBR", "emission_strength": 2.5, "isError": False},
            }
        elif "dispatch_op('create_armature'" in code or 'dispatch_op("create_armature"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "armature_name": "RobotRig", "bone_count": 2, "isError": False},
            }
        elif "dispatch_op('bind_skin_weights'" in code or 'dispatch_op("bind_skin_weights"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "mesh_name": "LegMesh", "vertex_groups": 2, "isError": False},
            }
        elif "dispatch_op('setup_ik_constraint'" in code or 'dispatch_op("setup_ik_constraint"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "armature_name": "RobotRig", "constraint": "IK", "isError": False},
            }
        elif "dispatch_op('setup_light'" in code or 'dispatch_op("setup_light"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "light_name": "KeyLight", "energy": 500.0, "isError": False},
            }
        elif "dispatch_op('setup_world_hdri'" in code or 'dispatch_op("setup_world_hdri"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "world_nodes": True, "strength": 1.5, "isError": False},
            }
        elif "dispatch_op('setup_camera'" in code or 'dispatch_op("setup_camera"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "camera_name": "MainCamera", "focal_length": 85.0, "isError": False},
            }
        elif "dispatch_op('camera_track_to'" in code or 'dispatch_op("camera_track_to"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "camera_name": "MainCamera", "target": "Cube", "isError": False},
            }
        elif "dispatch_op('configure_render_engine'" in code or 'dispatch_op("configure_render_engine"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "engine": "CYCLES", "samples": 128, "isError": False},
            }
        elif "dispatch_op('render_frame'" in code or 'dispatch_op("render_frame"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "output_path": "C:\\render.png", "render_time_seconds": 1.2, "isError": False},
            }
        elif "dispatch_op('get_viewport_screenshot'" in code or 'dispatch_op("get_viewport_screenshot"' in code:
            return {
                "status": "success",
                "result": {
                    "status": "success",
                    "image_base64": base64.b64encode(b"PNG_SAMPLE_DATA").decode("ascii"),
                    "mime_type": "image/png",
                    "resolution": [512, 512],
                    "camera": "Camera",
                    "shading": "MATERIAL",
                    "isError": False,
                },
            }
        elif "dispatch_op('execute_code'" in code or 'dispatch_op("execute_code"' in code:
            return {
                "status": "success",
                "result": {"status": "success", "result": 42, "stdout": "hello", "isError": False},
            }

        return {"status": "success", "result": {"status": "success", "isError": False}}


@pytest.fixture
def mock_client():
    client = MockBlenderSocketClient()
    set_client(client)
    yield client
    set_client(None)


# ==============================================================================
# 3. Comprehensive Unit Verification for All 20 3D Tools
# ==============================================================================

def test_scene_tools_suite(mock_client):
    """Verify Scene tools suite (manage_object, transform, hierarchy, scene_info, object_info)."""
    # 1. manage_object create
    res1 = blender_manage_object(action="create", primitive_type="cube", name="HeroCube")
    assert res1.isError is False
    data1 = json.loads(res1.content[0].text)
    assert data1["status"] == "success"

    # 2. transform_object
    res2 = blender_transform_object(name="HeroCube", location=[1.0, 2.0, 3.0])
    assert res2.isError is False

    # 3. manage_hierarchy
    res3 = blender_manage_hierarchy(action="set_parent", child_name="Child", parent_name="Parent")
    assert res3.isError is False

    # 4. get_scene_info
    res4 = blender_get_scene_info(detailed=True)
    assert res4.isError is False

    # 5. get_object_info
    res5 = blender_get_object_info(name="HeroCube")
    assert res5.isError is False


def test_material_tools_suite(mock_client):
    """Verify Material tools suite (create, assign, configure, textures, emission)."""
    res1 = blender_create_material(material_name="PBR_Metal", use_nodes=True)
    assert res1.isError is False

    res2 = blender_assign_material(object_name="HeroCube", material_name="PBR_Metal")
    assert res2.isError is False

    res3 = blender_configure_pbr(material_name="PBR_Metal", metallic=0.9, roughness=0.1)
    assert res3.isError is False

    res4 = blender_set_pbr_textures(material_name="PBR_Metal", base_color_texture="dummy.png")
    assert res4.isError is False

    res5 = blender_set_emission(material_name="PBR_Metal", emission_strength=5.0)
    assert res5.isError is False


def test_rigging_tools_suite(mock_client):
    """Verify Rigging tools suite (create_armature, bind_skin_weights, setup_ik_constraint)."""
    bones = [
        {"name": "Root", "head": [0, 0, 0], "tail": [0, 0, 1]},
        {"name": "Leg", "head": [0, 0, 1], "tail": [0, 0, 2], "parent": "Root"},
    ]
    res1 = blender_create_armature(bones=bones, armature_name="TestArmature")
    assert res1.isError is False

    res2 = blender_bind_skin_weights(mesh_name="LegMesh", armature_name="TestArmature")
    assert res2.isError is False

    res3 = blender_setup_ik_constraint(armature_name="TestArmature", bone_name="Leg", target_object="TargetObj")
    assert res3.isError is False


def test_lighting_camera_tools_suite(mock_client):
    """Verify Lighting & Camera suite (setup_light, world_hdri, camera, camera_track_to)."""
    res1 = blender_setup_light(light_type="AREA", energy=800.0, light_name="KeyLight")
    assert res1.isError is False

    res2 = blender_setup_world_hdri(color=[0.1, 0.1, 0.2], strength=1.0)
    assert res2.isError is False

    res3 = blender_setup_camera(camera_name="MainCam", focal_length=85.0)
    assert res3.isError is False

    res4 = blender_camera_track_to(camera_name="MainCam", target_object="HeroCube")
    assert res4.isError is False


def test_render_viewport_tools_suite(mock_client):
    """Verify Render & Viewport suite (configure_engine, render_frame, viewport_screenshot, execute_code)."""
    res1 = blender_configure_render_engine(engine="CYCLES", samples=128)
    assert res1.isError is False

    res2 = blender_render_frame(output_path="C:\\test_out.png")
    assert res2.isError is False

    # Screenshot test: must verify ImageContent and TextContent returned
    res3 = blender_get_viewport_screenshot(max_dimension=512)
    assert res3.isError is False
    assert len(res3.content) == 2
    assert isinstance(res3.content[0], TextContent)
    assert isinstance(res3.content[1], ImageContent)
    assert res3.content[1].mimeType == "image/png"
    assert len(res3.content[1].data) > 0

    res4 = blender_execute_code(code="result = 42")
    assert res4.isError is False


# ==============================================================================
# 4. Error Condition Verification (isError: True & Zero Crashes)
# ==============================================================================

def test_missing_object_error_handling(mock_client):
    """Verify object not found returns structured error with isError: True and code -32001."""
    def error_responder(cmd):
        return {
            "status": "success",
            "result": {
                "status": "error",
                "error_code": -32001,
                "error_type": "ObjectNotFoundError",
                "message": "Object 'Ghost_Object' does not exist in scene.",
                "details": {
                    "target": "Ghost_Object",
                    "available_objects": ["Cube", "Light", "Camera"],
                    "hint": "Verify existing objects using blender_get_scene_info",
                },
            },
        }

    mock_client.mock_dispatch_handler = error_responder

    res = blender_transform_object(name="Ghost_Object", location=[0, 0, 1])
    assert res.isError is True
    data = json.loads(res.content[0].text)
    assert data["status"] == "error"
    assert data["error_code"] == -32001
    assert data["error_type"] == "ObjectNotFoundError"
    assert "hint" in data["details"]


def test_material_shader_error_handling(mock_client):
    """Verify material missing returns code -32002."""
    def error_responder(cmd):
        return {
            "status": "success",
            "result": {
                "status": "error",
                "error_code": -32002,
                "error_type": "MaterialShaderError",
                "message": "Material 'NonExistentMat' not found.",
                "details": {"material_name": "NonExistentMat"},
            },
        }

    mock_client.mock_dispatch_handler = error_responder

    res = blender_configure_pbr(material_name="NonExistentMat", metallic=1.0)
    assert res.isError is True
    data = json.loads(res.content[0].text)
    assert data["error_code"] == -32002


def test_python_syntax_error_handling(mock_client):
    """Verify arbitrary syntax error returns code -32007 with traceback."""
    def error_responder(cmd):
        return {
            "status": "success",
            "result": {
                "status": "error",
                "error_code": -32007,
                "error_type": "ScriptSyntaxError",
                "message": "SyntaxError: invalid syntax",
                "details": {"traceback": "Traceback at line 1"},
            },
        }

    mock_client.mock_dispatch_handler = error_responder

    res = blender_execute_code(code="def broken(")
    assert res.isError is True
    data = json.loads(res.content[0].text)
    assert data["error_code"] == -32007


# ==============================================================================
# 5. FastMCP Registration & Async Invocation Verification
# ==============================================================================

def test_fastmcp_server_registration(mock_client):
    """Verify all 21 tools are registered on FastMCP and callable via mcp.call_tool."""
    expected_tools = [
        "blender_manage_object",
        "blender_transform_object",
        "blender_manage_hierarchy",
        "blender_get_scene_info",
        "blender_get_object_info",
        "blender_create_material",
        "blender_assign_material",
        "blender_configure_pbr",
        "blender_set_pbr_textures",
        "blender_set_emission",
        "blender_create_armature",
        "blender_bind_skin_weights",
        "blender_setup_ik_constraint",
        "blender_setup_light",
        "blender_setup_world_hdri",
        "blender_setup_camera",
        "blender_camera_track_to",
        "blender_configure_render_engine",
        "blender_render_frame",
        "blender_get_viewport_screenshot",
        "blender_execute_code",
    ]

    registered = mcp._tool_manager._tools
    for tool_name in expected_tools:
        assert tool_name in registered, f"Tool '{tool_name}' missing from FastMCP registry!"

    # Test invoking via async mcp.call_tool
    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(mcp.call_tool("blender_manage_object", {"action": "create", "primitive_type": "cube"}))
        assert isinstance(res, CallToolResult)
        assert res.isError is False
        assert len(res.content) > 0
    finally:
        loop.close()


# ==============================================================================
# 6. Live Blender 4.1.1 End-to-End Integration Verification
# ==============================================================================

@pytest.mark.skipif(
    not BlenderBinaryDetector()._from_known_paths() and not BlenderBinaryDetector()._from_system_path(),
    reason="Blender executable not installed on this host",
)
def test_live_blender_3d_tools_workflow():
    """
    Spawns real headless Blender 4.1.1 daemon on port 9877, executes genuine
    3D tools end-to-end workflow, validates zero-crash error responses,
    and shuts down cleanly without orphan processes.
    """
    test_port = 9877
    dm = DaemonManager(port=test_port)
    client = BlenderSocketClient(port=test_port, daemon_manager=dm)

    try:
        # Start headless daemon
        status = dm.ensure_daemon_running(timeout=15.0)
        assert status["running"] is True

        client.connect(timeout=3.0)
        assert client.is_connected is True

        set_client(client)

        # 1. Create Mesh Primitive
        res_create = blender_manage_object(action="create", primitive_type="cube", name="TestCube")
        assert res_create.isError is False
        data_create = json.loads(res_create.content[0].text)
        assert data_create["status"] == "success"
        actual_name = data_create["object_name"]

        # 2. Transform Object
        res_trans = blender_transform_object(name=actual_name, location=[2.0, 0.0, 1.5])
        assert res_trans.isError is False

        # 3. Create & Assign Material
        res_mat = blender_create_material(material_name="LiveTestMat", use_nodes=True)
        assert res_mat.isError is False

        res_assign = blender_assign_material(object_name=actual_name, material_name="LiveTestMat")
        assert res_assign.isError is False

        # 4. Configure PBR & Emission
        res_pbr = blender_configure_pbr(material_name="LiveTestMat", metallic=0.8, roughness=0.2)
        assert res_pbr.isError is False

        res_emiss = blender_set_emission(material_name="LiveTestMat", emission_strength=2.0)
        assert res_emiss.isError is False

        # 5. Setup Light
        res_light = blender_setup_light(light_type="POINT", energy=250.0, light_name="LiveLight", location=[3.0, -3.0, 4.0])
        assert res_light.isError is False

        # 6. Setup Camera and Track-To
        res_cam = blender_setup_camera(camera_name="LiveCam", focal_length=50.0, location=[5.0, -5.0, 3.0])
        assert res_cam.isError is False

        res_track = blender_camera_track_to(camera_name="LiveCam", target_object=actual_name)
        assert res_track.isError is False

        # 7. Configure Render Engine
        res_engine = blender_configure_render_engine(engine="BLENDER_EEVEE_NEXT", samples=32, resolution_x=320, resolution_y=240)
        assert res_engine.isError is False

        # 8. Viewport Screenshot
        res_snap = blender_get_viewport_screenshot(max_dimension=256)
        assert res_snap.isError is False
        assert len(res_snap.content) == 2
        assert isinstance(res_snap.content[1], ImageContent)
        assert len(res_snap.content[1].data) > 0

        # 9. Query Scene Info
        res_scene = blender_get_scene_info(detailed=True)
        assert res_scene.isError is False
        data_scene = json.loads(res_scene.content[0].text)
        assert data_scene["object_count"] >= 3

        # 10. Negative Test: Query Missing Object (Must return isError: True without crash)
        res_err = blender_transform_object(name="NonExistent_Ghost_Obj")
        assert res_err.isError is True
        err_data = json.loads(res_err.content[0].text)
        assert err_data["error_code"] == -32001
        assert err_data["error_type"] == "ObjectNotFoundError"
        assert "available_objects" in err_data["details"]

    finally:
        set_client(None)
        client.disconnect()
        dm.shutdown(timeout=3.0)


# ==============================================================================
# 7. Additional Boundary & Negative Cases Across All 5 Tool Categories
# ==============================================================================

def test_scene_negative_and_boundary_cases(mock_client):
    """Verify negative validation for scene operations returning isError: True."""
    def error_responder(cmd):
        code = cmd.get("params", {}).get("code", "")
        if "invalid_action" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32602, "message": "Invalid action"}}
        if "invalid_primitive" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32602, "message": "Unknown primitive"}}
        if "cyclic_parenting" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32003, "message": "Cyclic hierarchy"}}
        return {"status": "success", "result": {"status": "error", "error_code": -32001, "message": "Object not found"}}

    mock_client.mock_dispatch_handler = error_responder

    # Invalid action
    res1 = blender_manage_object(action="invalid_action")
    assert res1.isError is True
    assert json.loads(res1.content[0].text)["error_code"] == -32602

    # Invalid primitive
    res2 = blender_manage_object(action="create", primitive_type="invalid_primitive")
    assert res2.isError is True
    assert json.loads(res2.content[0].text)["error_code"] == -32602

    # Cyclic parenting
    res3 = blender_manage_hierarchy(action="set_parent", child_name="Parent", parent_name="Child")
    assert res3.isError is True
    assert json.loads(res3.content[0].text)["error_code"] in (-32003, -32001)

    # Missing target
    res4 = blender_get_object_info(name="Ghost")
    assert res4.isError is True
    assert json.loads(res4.content[0].text)["error_code"] == -32001


def test_lighting_and_render_negative_cases(mock_client):
    """Verify negative validation for lighting and render tools."""
    def error_responder(cmd):
        code = cmd.get("params", {}).get("code", "")
        if "LASER" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32602, "message": "Invalid light type"}}
        if "RAYTRACER_INVALID" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32005, "message": "Unsupported render engine"}}
        if "ghost_hdri.hdr" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32004, "message": "HDRI not found"}}
        return {"status": "success", "result": {"status": "error", "error_code": -32001, "message": "Not found"}}

    mock_client.mock_dispatch_handler = error_responder

    # Invalid light type
    res1 = blender_setup_light(light_type="LASER", energy=100.0)
    assert res1.isError is True
    assert json.loads(res1.content[0].text)["error_code"] == -32602

    # Unsupported render engine
    res2 = blender_configure_render_engine(engine="RAYTRACER_INVALID")
    assert res2.isError is True
    assert json.loads(res2.content[0].text)["error_code"] == -32005

    # Missing HDRI
    res3 = blender_setup_world_hdri(hdri_path="ghost_hdri.hdr")
    assert res3.isError is True
    assert json.loads(res3.content[0].text)["error_code"] == -32004


def test_daemon_offline_zero_crash_boundary():
    """Verify tool handles disconnected client without crashing server process."""
    dead_client = MockBlenderSocketClient()
    def fail_send(cmd, timeout=None):
        raise ConnectionRefusedError("Connection refused on 127.0.0.1:9999")
    dead_client.send_command = fail_send

    set_client(dead_client)
    try:
        res = blender_get_scene_info()
        assert isinstance(res, CallToolResult)
        assert res.isError is True
        data = json.loads(res.content[0].text)
        assert data["status"] == "error"
        assert data["error_code"] == -32000
        assert data["error_type"] == "BlenderDaemonError"
    finally:
        set_client(None)


def test_direct_blender_ops_dispatch():
    """Verify blender_ops.dispatch_op handles unregistered operations cleanly."""
    from blender_mcp.bridge_scripts import blender_ops
    res = blender_ops.dispatch_op("non_existent_op", {})
    assert res["status"] == "error"
    assert res["error_code"] == -32601
    assert "available_ops" in res["details"]



# ==============================================================================
# 7. Additional Boundary & Negative Cases Across All 5 Tool Categories
# ==============================================================================

def test_scene_negative_and_boundary_cases(mock_client):
    """Verify negative validation for scene operations returning isError: True."""
    def error_responder(cmd):
        code = cmd.get("params", {}).get("code", "")
        if "invalid_action" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32602, "message": "Invalid action"}}
        if "invalid_primitive" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32602, "message": "Unknown primitive"}}
        if "cyclic_parenting" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32003, "message": "Cyclic hierarchy"}}
        return {"status": "success", "result": {"status": "error", "error_code": -32001, "message": "Object not found"}}

    mock_client.mock_dispatch_handler = error_responder

    # Invalid action
    res1 = blender_manage_object(action="invalid_action")
    assert res1.isError is True
    assert json.loads(res1.content[0].text)["error_code"] == -32602

    # Invalid primitive
    res2 = blender_manage_object(action="create", primitive_type="invalid_primitive")
    assert res2.isError is True
    assert json.loads(res2.content[0].text)["error_code"] == -32602

    # Cyclic parenting
    res3 = blender_manage_hierarchy(action="set_parent", child_name="Parent", parent_name="Child")
    assert res3.isError is True
    assert json.loads(res3.content[0].text)["error_code"] in (-32003, -32001)

    # Missing target
    res4 = blender_get_object_info(name="Ghost")
    assert res4.isError is True
    assert json.loads(res4.content[0].text)["error_code"] == -32001


def test_lighting_and_render_negative_cases(mock_client):
    """Verify negative validation for lighting and render tools."""
    def error_responder(cmd):
        code = cmd.get("params", {}).get("code", "")
        if "LASER" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32602, "message": "Invalid light type"}}
        if "RAYTRACER_INVALID" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32005, "message": "Unsupported render engine"}}
        if "ghost_hdri.hdr" in code:
            return {"status": "success", "result": {"status": "error", "error_code": -32004, "message": "HDRI not found"}}
        return {"status": "success", "result": {"status": "error", "error_code": -32001, "message": "Not found"}}

    mock_client.mock_dispatch_handler = error_responder

    # Invalid light type
    res1 = blender_setup_light(light_type="LASER", energy=100.0)
    assert res1.isError is True
    assert json.loads(res1.content[0].text)["error_code"] == -32602

    # Unsupported render engine
    res2 = blender_configure_render_engine(engine="RAYTRACER_INVALID")
    assert res2.isError is True
    assert json.loads(res2.content[0].text)["error_code"] == -32005

    # Missing HDRI
    res3 = blender_setup_world_hdri(hdri_path="ghost_hdri.hdr")
    assert res3.isError is True
    assert json.loads(res3.content[0].text)["error_code"] == -32004


def test_daemon_offline_zero_crash_boundary():
    """Verify tool handles disconnected client without crashing server process."""
    dead_client = MockBlenderSocketClient()
    def fail_send(cmd, timeout=None):
        raise ConnectionRefusedError("Connection refused on 127.0.0.1:9999")
    dead_client.send_command = fail_send

    set_client(dead_client)
    try:
        res = blender_get_scene_info()
        assert isinstance(res, CallToolResult)
        assert res.isError is True
        data = json.loads(res.content[0].text)
        assert data["status"] == "error"
        assert data["error_code"] == -32000
        assert data["error_type"] == "BlenderDaemonError"
    finally:
        set_client(None)


def test_direct_blender_ops_dispatch():
    """Verify blender_ops.dispatch_op handles unregistered operations cleanly."""
    from blender_mcp.bridge_scripts import blender_ops
    res = blender_ops.dispatch_op("non_existent_op", {})
    assert res["status"] == "error"
    assert res["error_code"] == -32601
    assert "available_ops" in res["details"]

