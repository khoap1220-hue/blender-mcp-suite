# Project: Production-Grade Blender MCP Suite

## Overview
A comprehensive, resilient Model Context Protocol (MCP) server suite integrated deeply into Blender 4.1+ on Windows. Features automatic daemon lifecycle management, zero-zombie child containment via Windows Job Objects, resilient socket auto-recovery (< 3s), 18 full-spectrum 3D MCP tools, zero-crash structured error boundaries, and an end-to-end automated testing suite.

## Architecture

### System Topology
```
[ AI Client: Antigravity / Cursor / Claude Desktop ]
                       │
                       │ (Stdio JSON-RPC)
                       ▼
          [ Blender MCP Server Engine ]
          ├── Daemon Lifecycle Manager (Detection, Auto-Spawn, Job Object)
          ├── Resilient Socket Client (Auto-Reconnect, Backoff, Healthcheck)
          ├── MCP Tools Registry (18 3D Tools + Fallback Runner)
          └── Structured Error & Response Boundary
                       │
                       │ (TCP Socket on 127.0.0.1:9876, SO_EXCLUSIVEADDRUSE)
                       ▼
          [ Blender 4.1.1 Daemon / GUI ]
          ├── Daemon Event Pump (Main-Thread Execution Loop)
          ├── bpy Dispatcher & Exception Boundary
          └── 3D Operations Core (Mesh, PBR, Rigging, Lighting, Render, Viewport)
```

### Key Architectural Decisions
1. **Daemon Runtime**: Separate headless daemon runner `daemon/blender_mcp_daemon.py` executing Blender in `--background` with a dedicated main-thread event pump loop, bypassing `bpy.app.timers` UI loop limitations.
2. **Winsock Ownership**: Port 9876 is bound strictly to `127.0.0.1` with `SO_EXCLUSIVEADDRUSE` to prevent port hijacking and Windows firewall prompts.
3. **Anti-Zombie Containment**: Windows Job Objects (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) assigned to Blender child processes so that any server exit immediately terminates child Blender instances.
4. **Resilient Auto-Recovery**: Client socket communication is wrapped in an exponential backoff reconnect loop `[0.1, 0.2, 0.4, 0.8]` restoring dropped sessions in < 2.0s without crashing tool invocations.
5. **Zero-Crash Protocol Boundary**: All `bpy` script operations are enveloped in structured error handlers returning `isError: true` with standard JSON-RPC (-32700 to -32603) and domain error codes (-32000 to -32007).

---

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Binary Auto-Detection | 4-stage search (env vars, Windows paths, registry, PATH) targeting Blender 4.1+ | M1 | Survey |
| 2 | Headless Daemon Spawning | Launches Blender in background (`--background --python daemon.py`) with persistent socket | M1 | Survey |
| 3 | GUI Session Detection & Attach | Detects running Blender GUI instance on port 9876 and attaches seamlessly | M1 | Survey |
| 4 | Two-Way Heartbeat Ping/Pong | Liveness probe verifying socket health and version handshake | M1 | Survey |
| 5 | Exponential Backoff Socket Auto-Recovery | Restores dropped socket session within < 3s without AI client crash | M1 | Survey |
| 6 | Windows Job Object Anti-Zombie Containment | Eliminates zombie Blender processes on server termination | M1 | Survey |
| 7 | Exclusive Port Binding & Release | Uses `SO_EXCLUSIVEADDRUSE` on `127.0.0.1:9876` and clean shutdown release | M1 | Survey |
| 8 | `blender_manage_object` | Create primitives, duplicate, delete, rename, and select objects | M2 | Survey |
| 9 | `blender_transform_object` | Set or delta transform location, rotation, and scale; apply transforms | M2 | Survey |
| 10 | `blender_manage_hierarchy` | Parent/unparent with keep-transform, organize scene collections | M2 | Survey |
| 11 | `blender_get_scene_info` | Query scene metadata, objects, active camera, render engine | M2 | Survey |
| 12 | `blender_get_object_info` | Query detailed object transforms, bounding box, materials, modifiers | M2 | Survey |
| 13 | `blender_create_material` | Create new material with node tree and Principled BSDF | M2 | Survey |
| 14 | `blender_assign_material` | Assign material to target object and slot | M2 | Survey |
| 15 | `blender_configure_pbr` | Configure Principled BSDF socket values (Color, Roughness, Metallic, IOR, Alpha) | M2 | Survey |
| 16 | `blender_set_pbr_textures` | Connect image textures to Principled BSDF with correct color spaces | M2 | Survey |
| 17 | `blender_set_emission` | Configure Principled BSDF emission color and strength | M2 | Survey |
| 18 | `blender_create_armature` | Create armature object with hierarchical edit bones | M2 | Survey |
| 19 | `blender_bind_skin_weights` | Parent mesh to armature with automatic bone heat weights | M2 | Survey |
| 20 | `blender_setup_ik_constraint` | Setup Inverse Kinematics constraints on pose bones | M2 | Survey |
| 21 | `blender_setup_light` | Create and configure Point, Sun, Spot, Area lights | M2 | Survey |
| 22 | `blender_setup_world_hdri` | Set world background color and HDRI environment texture | M2 | Survey |
| 23 | `blender_setup_camera` | Create camera, configure focal length, sensor, depth of field | M2 | Survey |
| 24 | `blender_camera_track_to` | Attach Track-To constraint to camera targeting object | M2 | Survey |
| 25 | `blender_configure_render_engine` | Configure render engine (Cycles / Eevee Next), resolution, samples, device | M2 | Survey |
| 26 | `blender_render_frame` | Execute render and save output frame to disk | M2 | Survey |
| 27 | `blender_get_viewport_screenshot` | Capture 3D viewport / offscreen render as base64 PNG | M2 | Survey |
| 28 | `blender_execute_code` | Fallback arbitrary Python execution inside Blender main thread | M2 | Survey |
| 29 | Structured Error Taxonomy | 13 standard JSON-RPC and domain error codes (-32700 to -32007) | M3 | Survey |
| 30 | Diagnostic Error Envelopes | Format errors with `isError: true`, error code, message, and hints | M3 | Survey |
| 31 | In-Process `bpy` Exception Isolation | Zero-crash boundary preventing Blender script errors from dropping socket | M3 | Survey |
| 32 | E2E Test Harness & Runner | Test suite infrastructure in `tests/test_blender_mcp_e2e.py` | M_TEST | Survey |
| 33 | Tier 1 Feature Coverage Tests | Happy-path coverage for daemon lifecycle, ping, and core tool calls | M_TEST | Survey |
| 34 | Tier 2 Boundary & Negative Tests | Invalid parameters, missing targets, cyclic hierarchies | M_TEST | Survey |
| 35 | Tier 3 Cross-Feature Integration Tests | End-to-end multi-tool workflows (Mesh -> Material -> Light -> Cam -> Render) | M_TEST | Survey |
| 36 | Tier 4 Stress & Fast Reconnect Tests | Drop socket simulation, verify recovery < 3.0s | M_TEST | Survey |
| 37 | Tier 5 Adversarial Coverage Hardening | White-box stress testing and edge-case hardening | M4 | Survey |
| 38 | 1-Click Launchers & Documentation | `run_server.bat`, `run_tests.bat`, comprehensive user manual | M5 | Survey |
| 39 | Multi-Client Configurations | Ready-to-use configs for Antigravity, Cursor, and Claude Desktop | M5 | Survey |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M_TEST | E2E Testing Track | Design test infrastructure, runner, and test cases (Tiers 1-4) in `tests/test_blender_mcp_e2e.py`, write `TEST_INFRA.md`, publish `TEST_READY.md` | None | DONE |
| M1 | Daemon Lifecycle & Socket Auto-Recovery | Blender binary detection, headless daemon spawner, Windows Job Object anti-zombie containment, resilient socket client with auto-reconnect (< 3s), heartbeat ping/pong, and graceful shutdown | None | DONE |
| M2 | Full-Spectrum 3D MCP Tools Suite | Implement 18 core 3D MCP tools across 5 categories + execution fallback | M1 interface contracts | DONE |
| M3 | Structured Error Handling & Zero-Crash Boundary | Standardized JSON-RPC + domain error taxonomy, diagnostic envelopes with hints, `bpy` exception isolation | M2 | DONE |
| M4 | Final Milestone: E2E Verification & Adversarial Hardening | Phase 1: Pass 100% of E2E tests (Tiers 1-4). Phase 2: Adversarial coverage hardening (Tier 5) | M1, M2, M3, M_TEST | DONE |
| M5 | Packaging, 1-Click Launchers & Documentation | Create `run_server.bat`, `run_tests.bat`, multi-client configs (Antigravity/Cursor/Claude Desktop), update README | M4 | DONE |

---

## Interface Contracts

### 1. Blender MCP Client ↔ Blender Daemon Protocol (TCP Port 9876)
- **Framing**: UTF-8 encoded JSON payload followed by newline `\n` (and compatible with raw JSON parse buffer).
- **Request Format**:
  ```json
  {
    "type": "command_name",
    "params": {
      "key": "value"
    }
  }
  ```
- **Response Format (Success)**:
  ```json
  {
    "status": "success",
    "result": { ... }
  }
  ```
- **Response Format (Error)**:
  ```json
  {
    "status": "error",
    "error_code": -32001,
    "error_type": "ERR_OBJECT_NOT_FOUND",
    "message": "Object 'Character' not found in scene",
    "details": {
      "target": "Character",
      "available_objects": ["Cube", "Light", "Camera"],
      "hint": "Verify object name with blender_get_scene_info"
    }
  }
  ```

### 2. MCP Client (AI Assistant) ↔ MCP Server (Stdio JSON-RPC)
- **Tool Call Return**:
  - On Success:
    ```json
    {
      "content": [
        {"type": "text", "text": "{\"status\": \"success\", ...}"}
      ],
      "isError": false
    }
    ```
  - On Error:
    ```json
    {
      "content": [
        {"type": "text", "text": "Error [-32001]: Object 'Character' not found..."}
      ],
      "isError": true
    }
    ```
  - On Viewport Screenshot:
    ```json
    {
      "content": [
        {"type": "text", "text": "Viewport capture rendered successfully."},
        {"type": "image", "data": "<base64_encoded_png>", "mimeType": "image/png"}
      ],
      "isError": false
    }
    ```

---

## Code Layout

```
y:\MCP Blender Agent\
├── daemon\
│   └── blender_mcp_daemon.py       # Headless background Blender runner with main-thread socket loop
├── src\
│   └── blender_mcp\
│       ├── __init__.py
│       ├── server.py               # Main MCP Server entry point (FastMCP / MCP SDK)
│       ├── daemon_manager.py       # Blender binary detection, process spawner, Windows Job Objects
│       ├── socket_client.py        # Resilient socket client with auto-reconnect (< 3s) and backoff
│       ├── error_boundary.py       # JSON-RPC error taxonomy and exception decorators
│       ├── tools\
│       │   ├── __init__.py
│       │   ├── scene.py            # Object CRUD, transforms, hierarchies, scene queries
│       │   ├── material.py         # PBR shaders, Principled BSDF, textures, emission
│       │   ├── rigging.py          # Armatures, bone hierarchy, auto-weights, IK constraints
│       │   ├── lighting_camera.py  # Lights (Point/Sun/Spot/Area), HDRI, cameras, track-to
│       │   └── render_viewport.py  # Render engine configs, frame render, viewport snapshot
│       └── bridge_scripts\
│           └── blender_ops.py      # Internal bpy execution handlers inside Blender
├── tests\
│   ├── __init__.py
│   ├── conftest.py
│   └── test_blender_mcp_e2e.py     # Comprehensive E2E test suite (Tiers 1-4)
├── configs\
│   ├── antigravity_mcp_config.json
│   ├── cursor_mcp_config.json
│   └── claude_desktop_config.json
├── run_server.bat                  # 1-Click launcher for MCP server
├── run_tests.bat                   # 1-Click test runner
├── TEST_INFRA.md                   # E2E Test track documentation
├── TEST_READY.md                   # E2E Test suite ready signal
├── PROJECT.md                      # Master architecture & milestone index
└── README.md                       # Comprehensive user guide & documentation
```
