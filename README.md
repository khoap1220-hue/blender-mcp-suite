# Blender MCP (Model Context Protocol) Suite for Windows

[![Blender 4.1+](https://img.shields.io/badge/Blender-4.1%2B-orange.svg)](https://www.blender.org/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Model Context Protocol](https://img.shields.io/badge/Protocol-MCP%20JSON--RPC-green.svg)](https://modelcontextprotocol.io/)
[![Test Suite](https://img.shields.io/badge/Tests-76%2F76%20Passing%20(100%25)-brightgreen.svg)]()
[![Platform](https://img.shields.io/badge/Platform-Windows%20x64-lightgrey.svg)]()

Production-grade, resilient **Model Context Protocol (MCP)** server suite providing deep two-way integration into **Blender 4.1+** on Windows. Designed for autonomous AI agents and developer workflows across **Antigravity**, **Cursor**, **Claude Desktop**, and custom MCP clients.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [R1: Daemon Lifecycle & Resilient Socket Auto-Recovery](#2-r1-daemon-lifecycle--resilient-socket-auto-recovery)
3. [R2: Full-Spectrum 3D MCP Tools Suite (21 Tools)](#3-r2-full-spectrum-3d-mcp-tools-suite-21-tools)
4. [R3: Structured Error Handling & Zero-Crash Boundary](#4-r3-structured-error-handling--zero-crash-boundary)
5. [R4: Automated Testing & Verification Suite](#5-r4-automated-testing--verification-suite)
6. [1-Click Quickstart](#6-1-click-quickstart)
7. [Multi-Client Configuration Guide](#7-multi-client-configuration-guide)
8. [Troubleshooting Guide](#8-troubleshooting-guide)
9. [Project Repository Layout](#9-project-repository-layout)

---

## 1. Architecture Overview

### System Topology

```
+-----------------------------------------------------------------------+
|              AI Client (Antigravity / Cursor / Claude Desktop)        |
+-----------------------------------------------------------------------+
                                  │
                                  │ Stdio JSON-RPC Protocol
                                  ▼
+-----------------------------------------------------------------------+
|                    Blender MCP Server Engine (Python)                 |
|  [src/blender_mcp/server.py]                                          |
|                                                                       |
|  ├── Daemon Lifecycle Manager (src/blender_mcp/daemon_manager.py)     |
|  │     ├── 4-Stage Blender 4.1+ Binary Auto-Detection                 |
|  │     ├── Headless Spawner (CREATE_NO_WINDOW, CREATE_NEW_GROUP)      |
|  │     └── Windows Job Object Anti-Zombie Containment (kernel32)      |
|  │                                                                    |
|  ├── Resilient Socket Client (src/blender_mcp/socket_client.py)       |
|  │     ├── Framing: Newline (\n) Delimited JSON Streaming             |
|  │     ├── Exponential Backoff Auto-Reconnect (< 3.0s recovery)       |
|  │     └── Process Respawn Hook & Thread-Safe RLock                   |
|  │                                                                    |
|  ├── 21 MCP 3D Tools Suite (src/blender_mcp/tools/)                   |
|  │     ├── Scene & Object Manipulation (5 tools)                      |
|  │     ├── PBR Shading & Materials (5 tools)                          |
|  │     ├── Auto-Rigging & Armature Hierarchies (3 tools)              |
|  │     ├── Cinematic Lighting & Cameras (4 tools)                     |
|  │     └── Render Engine & Viewport Vision (4 tools)                  |
|  │                                                                    |
|  └── Zero-Crash Error Boundary (src/blender_mcp/error_boundary.py)    |
|        ├── 13 Standardized JSON-RPC & Domain Error Codes              |
|        └── @error_boundary Decorator with Diagnostic Recovery Hints   |
+-----------------------------------------------------------------------+
                                  │
                                  │ TCP Port 9876 (127.0.0.1, SO_EXCLUSIVEADDRUSE)
                                  ▼
+-----------------------------------------------------------------------+
|                   Blender 4.1.1 Environment (Daemon / GUI)            |
|  [daemon/blender_mcp_daemon.py]                                       |
|                                                                       |
|  ├── Main-Thread Event Pump (select.select polling loop)              |
|  ├── In-Process Bridge Dispatcher (src/blender_mcp/bridge_scripts/)   |
|  └── Native 3D Engine Core (bpy, mathutils, Cycles, Eevee Next)       |
+-----------------------------------------------------------------------+
```

### Communication & Protocol Design

- **Transport**: Standard Input / Output (`stdio`) connects the AI Client to the FastMCP server.
- **Inter-Process Bridge**: Local loopback TCP socket (`127.0.0.1:9876`).
- **Framing**: UTF-8 JSON payloads delimited by newline (`\n`), fully compatible with null-byte (`\0`) delimiters and self-delimited JSON streams (`JSONDecoder.raw_decode`).
- **Thread Safety**: Blender's Python API (`bpy`) requires execution on Blender's main thread. The daemon implements a dedicated `select.select()` event pump running on the main thread, eliminating thread-race crashes while delivering sub-millisecond response times.

---

## 2. R1: Daemon Lifecycle & Resilient Socket Auto-Recovery

### 4-Stage Blender 4.1+ Binary Auto-Detection

The `DaemonManager` automatically discovers and validates Blender 4.1+ without requiring manual path configuration:

1. **Environment Variables**: Inspects `BLENDER_PATH`, `BLENDER_EXECUTABLE`, and `BLENDER_BIN`.
2. **Standard Windows Installation Locations**: Scans `C:\Program Files\Blender Foundation\Blender 4.1\blender.exe`, `Blender 4.2\`, `Blender 4.3\`, and user profile directories.
3. **Windows Registry**: Queries `HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\blender.exe` and `Uninstall` registry keys.
4. **System PATH**: Uses `where.exe blender` as a final fallback.
5. **Version Verification**: Runs `blender.exe --version` to enforce the $\ge 4.1.0$ requirement.

### Headless Daemon Execution

When no active Blender session is detected on port 9876, `DaemonManager` automatically launches Blender in background mode:
```cmd
blender.exe --background --python "daemon\blender_mcp_daemon.py" -- --host 127.0.0.1 --port 9876
```
Launched with Windows flags `CREATE_NO_WINDOW` and `CREATE_NEW_PROCESS_GROUP`, completely invisible in the background with zero pop-up windows.

### Windows Job Object Zero-Zombie Containment

To prevent orphan background Blender processes from consuming CPU and RAM when the IDE or MCP server terminates:
- A Windows Job Object is created via Win32 API (`ctypes.windll.kernel32.CreateJobObjectW`).
- Configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x00002000)`.
- All spawned Blender processes are assigned to this Job Object.
- **Guarantee**: If the parent Python process terminates, crashes, or is killed via Task Manager, the Windows kernel instantly terminates all child Blender processes.

### Exponential Backoff Socket Auto-Recovery (< 3s)

- Connection losses (such as TCP RST or sudden socket closures) are automatically intercepted by `BlenderSocketClient`.
- Implements an exponential backoff schedule `[0.1s, 0.2s, 0.4s, 0.8s]`.
- Reconnection completes in **~210 ms** (verified in live benchmark), well within the 3.0s acceptance limit.
- If the daemon process died, the client signals `DaemonManager` to respawn the daemon and re-establishes the session transparently without failing AI tool calls.

### Exclusive Port Binding

The daemon binds to `127.0.0.1:9876` using `SO_EXCLUSIVEADDRUSE` on Windows:
- Prevents port hijacking and unauthorized socket reuse.
- Eliminates Windows Firewall network authorization popups.
- Cleans up and releases the socket cleanly upon shutdown.

---

## 3. R2: Full-Spectrum 3D MCP Tools Suite (21 Tools)

The suite registers **21 production-grade MCP tools** covering the complete 3D workflow:

| # | Tool Name | Category | Description | Primary Parameters | Return Format |
|---|---|---|---|---|---|
| 1 | `blender_manage_object` | Scene | Create primitives, duplicate, delete, rename, or select objects | `action`, `primitive_type`, `name`, `new_name`, `location`, `rotation`, `scale` | Object metadata dictionary |
| 2 | `blender_transform_object` | Scene | Set or delta location, rotation, and scale; bake transforms | `name`, `location`, `rotation`, `scale`, `delta`, `apply_transform` | Updated transform state |
| 3 | `blender_manage_hierarchy` | Scene | Parent/unparent with keep-transform, collections, cycle prevention | `action`, `child_name`, `parent_name`, `keep_transform`, `collection_name`, `target_objects` | Hierarchy status confirmation |
| 4 | `blender_get_scene_info` | Scene | Query scene statistics, objects, active camera, render settings | `detailed`, `collection_filter` | Scene graph JSON |
| 5 | `blender_get_object_info` | Scene | Deep inspect object transforms, bounding box, modifiers, materials | `name` | Complete object inspect JSON |
| 6 | `blender_create_material` | Material | Initialize new material with Principled BSDF node setup | `material_name`, `use_nodes` | Material slot confirmation |
| 7 | `blender_assign_material` | Material | Assign material to target mesh object and slot | `object_name`, `material_name`, `slot_index` | Assignment confirmation |
| 8 | `blender_configure_pbr` | Material | Configure Principled BSDF sockets (color, metallic, roughness, IOR, alpha) | `material_name`, `base_color`, `metallic`, `roughness`, `ior`, `transmission_weight`, `alpha` | Updated shader socket values |
| 9 | `blender_set_pbr_textures` | Material | Connect texture maps with proper color spaces (sRGB vs Non-Color) | `material_name`, `base_color_texture`, `roughness_texture`, `metallic_texture`, `normal_map_texture`, `emission_texture` | Connected texture map summary |
| 10 | `blender_set_emission` | Material | Configure radiant emission color tint and radiance multiplier | `material_name`, `emission_color`, `emission_strength` | Emission parameters |
| 11 | `blender_create_armature` | Rigging | Generate armature with hierarchical edit bones | `bones` (list of head/tail/parent dicts), `armature_name`, `display_type` | Armature hierarchy data |
| 12 | `blender_bind_skin_weights` | Rigging | Parent mesh to armature with automatic bone heat weighting | `mesh_name`, `armature_name`, `bind_type` | Skin binding report |
| 13 | `blender_setup_ik_constraint`| Rigging | Configure Inverse Kinematics on pose bones with pole targets | `armature_name`, `bone_name`, `target_object`, `target_subtarget`, `chain_length`, `pole_target`, `pole_angle` | Constraint configuration |
| 14 | `blender_setup_light` | Lighting | Create/configure Point, Sun, Spot, and Area lights | `light_type`, `energy`, `light_name`, `color`, `location`, `size`, `spot_size`, `spot_blend` | Light source status |
| 15 | `blender_setup_world_hdri` | Lighting | Configure world ambient light or HDRI environment map | `color`, `strength`, `hdri_path`, `rotation_z` | World background state |
| 16 | `blender_setup_camera` | Camera | Create camera with focal length, sensor width, depth of field | `camera_name`, `location`, `rotation`, `focal_length`, `sensor_width`, `dof_target`, `dof_fstop`, `set_active` | Camera optics parameters |
| 17 | `blender_camera_track_to` | Camera | Add Track-To constraint locking camera onto target object | `target_object`, `camera_name`, `track_axis`, `up_axis` | Constraint status |
| 18 | `blender_configure_render_engine` | Render | Configure Cycles / Eevee Next, resolution, samples, device | `engine`, `device`, `resolution_x`, `resolution_y`, `samples`, `film_transparent` | Engine settings |
| 19 | `blender_render_frame` | Render | Execute render and save still frame to disk | `output_path`, `frame`, `file_format` | Render status & file path |
| 20 | `blender_get_viewport_screenshot` | Viewport | Capture 3D viewport/offscreen snapshot as base64 PNG | `max_dimension`, `shading_type`, `camera_view` | Multimodal text + ImageContent |
| 21 | `blender_execute_code` | Fallback | Fallback arbitrary Python execution inside Blender main thread | `code`, `strict_json` | Output, result, stdout/stderr |

---

## 4. R3: Structured Error Handling & Zero-Crash Boundary

All tool invocations are guarded by the `@error_boundary` decorator. Instead of crashing the server, raising unhandled socket exceptions, or dropping connections, errors are intercepted, classified, and returned as structured MCP envelopes with `isError: True` and actionable diagnostic hints.

### Standardized Error Taxonomy (13 Codes)

| Error Code | Error Symbol | Description & Diagnostic Recovery Hint |
|---|---|---|
| `-32700` | `PARSE_ERROR` | Malformed JSON byte framing. The parser drops corrupt chunks and restores stream alignment. |
| `-32600` | `INVALID_REQUEST` | Missing required protocol fields (`type`, `params`). Check request syntax. |
| `-32601` | `METHOD_NOT_FOUND` | Command or tool name not registered in bridge operations. |
| `-32602` | `INVALID_PARAMS` | Parameter failed schema validation or range requirements. |
| `-32603` | `INTERNAL_ERROR` | Unhandled server exception. Complete traceback captured in diagnostic details. |
| `-32000` | `BLENDER_DAEMON_ERROR` | Blender daemon offline, socket severed, or startup timeout. |
| `-32001` | `OBJECT_NOT_FOUND` | Target object not found in scene. Provides fuzzy-matched alternative suggestion. |
| `-32002` | `MATERIAL_SHADER_ERROR`| Material does not exist or node graph corrupt. Suggests creating material first. |
| `-32003` | `ARMATURE_RIGGING_ERROR`| Cyclic parenting, missing bone, or unweighted geometry failure. |
| `-32004` | `LIGHTING_CAMERA_ERROR` | Missing Track-To target or camera focal length out of physical sensor bounds. |
| `-32005` | `RENDER_ENGINE_ERROR` | Unsupported render engine or compute device failure (e.g. GPU CUDA/OptiX fallback). |
| `-32006` | `VIEWPORT_CAPTURE_ERROR`| Offscreen buffer allocation failed or camera missing for snapshot. |
| `-32007` | `SCRIPT_SYNTAX_ERROR` | Syntax error or unhandled runtime exception in `blender_execute_code`. |

### Diagnostic Envelope Format

```json
{
  "status": "error",
  "error_code": -32001,
  "error_type": "ObjectNotFoundError",
  "message": "Object 'Character' not found in scene",
  "details": {
    "target": "Character",
    "available_objects": ["Cube", "Light", "Camera"],
    "hint": "Target 'Character' not found. Verify existing objects using 'blender_get_scene_info'."
  },
  "isError": true
}
```

---

## 5. R4: Automated Testing & Verification Suite

The repository features a **4-tier test architecture** containing **76 automated tests** across unit, integration, stress, and adversarial verification.

### Test Architecture

- **Tier 1: Feature Coverage (13 tests)** — Validates daemon discovery, lifecycle, heartbeat ping/pong, and all primary tool categories (Scene, PBR, Lights, Cameras, Render, Viewport).
- **Tier 2: Boundary & Negative Invariants (8 tests)** — Validates error envelopes for missing objects, invalid parameters, cyclic hierarchies, syntax errors, and malformed JSON framing without socket drops.
- **Tier 3: Cross-Feature Integration Pipelines (3 tests)** — Validates end-to-end asset creation (Primitive $\to$ PBR Gold $\to$ 3-Point Light $\to$ Camera $\to$ Render), character rigging with IK, and hierarchical scene grouping.
- **Tier 4: Real-World Stress & Auto-Recovery (4 tests)** — Studio product scene creation, hard `SO_LINGER` TCP RST severance auto-recovery (< 3s), high-frequency burst throughput (50 ops), and Windows Job Object kernel containment.
- **Adversarial Hardening Suites (48 tests)** — Rapid port recycling, concurrent multi-threading, stream truncation, and parent taskkill containment.

### Benchmark Results

| Metric | Benchmark Result | Target Requirement | Status |
|---|---|---|---|
| **Hard TCP RST Auto-Recovery** | **~210 ms** | $< 3.0\text{ s}$ | **PASSED (14x faster)** |
| **Local Ping Latency** | **0.42 ms** | $< 100\text{ ms}$ | **PASSED** |
| **Burst Throughput (50 ops)** | **1.15 s (~23 ms/op)** | $< 35\text{ ms/op}$ | **PASSED** |
| **Viewport Screenshot & Encode** | **< 450 ms** | $< 2.0\text{ s}$ | **PASSED** |
| **Zombie Child Containment** | **0 orphan processes** | 0 zombie leak | **PASSED (Kernel Job Object)** |
| **Full Repository Test Suite** | **76 / 76 Passed (100%)** | 100% Pass Rate | **PASSED (67.14s)** |

---

## 6. 1-Click Quickstart

### Launch the MCP Server (1-Click)

Double-click `run_server.bat` or run from terminal:
```cmd
y:\MCP Blender Agent\run_server.bat
```

What `run_server.bat` does:
1. Detects your Python 3.10+ environment (virtual environment `.venv`/`venv`/`env` or system PATH).
2. Sets `PYTHONPATH` to include the project root and `src/`.
3. Launches `python -m src.blender_mcp.server` with stdio transport.
4. Auto-detects Blender 4.1+ and starts the headless background daemon if not already running.
5. In case of unexpected exit, displays diagnostic guidance and pauses.

### Run the Automated Tests (1-Click)

Double-click `run_tests.bat` or run from terminal:
```cmd
y:\MCP Blender Agent\run_tests.bat
```

To run the complete repository test suite:
```cmd
run_tests.bat tests/ -v
```

---

## 7. Multi-Client Configuration Guide

Ready-to-use configuration templates are located in the `configs/` directory.

### A. Antigravity Configuration

Save to your Antigravity MCP configuration (or reference `configs/antigravity_mcp_config.json`):

```json
{
  "mcpServers": {
    "blender": {
      "command": "python",
      "args": [
        "-m",
        "src.blender_mcp.server"
      ],
      "cwd": "y:\\MCP Blender Agent",
      "env": {
        "PYTHONPATH": "y:\\MCP Blender Agent\\src;y:\\MCP Blender Agent",
        "BLENDER_HOST": "127.0.0.1",
        "BLENDER_PORT": "9876"
      }
    }
  }
}
```

### B. Cursor Configuration

Copy `configs/cursor_mcp_config.json` into your project's `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "blender": {
      "command": "python",
      "args": [
        "-m",
        "src.blender_mcp.server"
      ],
      "cwd": "y:\\MCP Blender Agent",
      "env": {
        "PYTHONPATH": "y:\\MCP Blender Agent\\src;y:\\MCP Blender Agent",
        "BLENDER_HOST": "127.0.0.1",
        "BLENDER_PORT": "9876"
      }
    }
  }
}
```

### C. Claude Desktop Configuration

Add the contents of `configs/claude_desktop_config.json` to:  
`%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "blender": {
      "command": "python",
      "args": [
        "-m",
        "src.blender_mcp.server"
      ],
      "cwd": "y:\\MCP Blender Agent",
      "env": {
        "PYTHONPATH": "y:\\MCP Blender Agent\\src;y:\\MCP Blender Agent",
        "BLENDER_HOST": "127.0.0.1",
        "BLENDER_PORT": "9876"
      }
    }
  }
}
```

---

## 8. Troubleshooting Guide

### 1. Port 9876 Conflict (`WSAEADDRINUSE` / Error 10048)
- **Symptom**: Server reports `Port 127.0.0.1:9876 is already in use`.
- **Cause**: An existing headless daemon or Blender GUI session is already holding the exclusive port.
- **Resolution**:
  ```cmd
  netstat -ano | findstr 9876
  taskkill /PID <PID> /F
  ```

### 2. Custom Blender Installation Path
- **Symptom**: `BlenderNotFoundError: Blender 4.1+ executable could not be located`.
- **Resolution**: Set the `BLENDER_PATH` environment variable in your terminal or client configuration:
  ```cmd
  set BLENDER_PATH=D:\CustomPath\Blender 4.1\blender.exe
  ```

### 3. Headless vs. GUI Workflow
- **Headless Mode (Default)**: Automatically managed in the background. Does not require touching Blender. Ideal for automated pipeline runs, rendering, and agent-driven generation.
- **GUI Mode**: If you open Blender 4.1 interactively and enable the MCP server addon on port 9876, the MCP server will attach directly to your visible 3D viewport. All object creations and transformations will appear live on your screen.

### 4. Windows Firewall Warnings
- The daemon binds exclusively to local loopback interface `127.0.0.1` using `SO_EXCLUSIVEADDRUSE`. It does NOT listen on `0.0.0.0` (all interfaces), so Windows Firewall prompts will not appear.

---

## 9. Project Repository Layout

```
y:\MCP Blender Agent\
├── daemon\
│   └── blender_mcp_daemon.py          # Headless background Blender runner with main-thread socket loop
├── src\
│   └── blender_mcp\
│       ├── __init__.py                # Package exports
│       ├── server.py                  # Main FastMCP Server entry point
│       ├── daemon_manager.py          # Binary discovery, process spawner, Windows Job Objects
│       ├── socket_client.py           # Resilient socket client with auto-reconnect (< 3s)
│       ├── error_boundary.py          # Standardized error taxonomy & @error_boundary decorator
│       ├── tools\
│       │   ├── __init__.py            # Tool auto-registration
│       │   ├── scene.py               # Object CRUD, transforms, hierarchy, inspection
│       │   ├── material.py            # PBR materials, Principled BSDF, textures, emission
│       │   ├── rigging.py             # Armatures, bone hierarchy, auto-weights, IK
│       │   ├── lighting_camera.py     # Lights (Sun/Point/Spot/Area), HDRI, cameras, track-to
│       │   └── render_viewport.py     # Render engines, still render, viewport vision snapshot
│       └── bridge_scripts\
│           └── blender_ops.py         # In-process bpy execution handlers
├── configs\
│   ├── antigravity_mcp_config.json    # Antigravity client configuration
│   ├── cursor_mcp_config.json         # Cursor .cursor/mcp.json configuration
│   └── claude_desktop_config.json     # Claude Desktop configuration
├── tests\
│   ├── conftest.py                    # Test fixtures
│   ├── test_blender_mcp_e2e.py        # Authoritative 4-tier E2E test suite (28 tests)
│   ├── test_3d_tools.py               # 3D tools unit test suite
│   ├── test_daemon_lifecycle.py       # Daemon manager unit tests
│   ├── test_socket_client.py          # Socket client resilience tests
│   ├── test_adversarial_m1_lifecycle.py # Process crash & rebind adversarial tests
│   └── test_adversarial_socket_resilience.py # Socket severance & latency tests
├── run_server.bat                     # 1-Click launcher for Blender MCP Server
├── run_tests.bat                      # 1-Click test launcher
├── TEST_INFRA.md                      # Test infrastructure architecture specification
├── TEST_READY.md                      # Test verification & readiness signal
├── PROJECT.md                         # Master architecture & milestone index
├── ORIGINAL_REQUEST.md                # Original user requirements
└── README.md                          # Comprehensive documentation (this document)
```
