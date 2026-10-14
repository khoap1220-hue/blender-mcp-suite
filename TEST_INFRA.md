# TEST_INFRA.md — Production-Grade Blender MCP Test Infrastructure & 4-Tier Methodology

## 1. Executive Summary & Purpose

This document establishes the official test architecture, verification methodology, and quality standards for the **Production-Grade Blender MCP (Model Context Protocol) Suite**. 

The suite bridges AI assistants (such as Antigravity, Cursor, and Claude Desktop) to Blender 4.1+ via a dual-layer transport architecture:
1. **Stdio JSON-RPC**: AI Client $\leftrightarrow$ Blender MCP Server Engine.
2. **TCP Socket (Port 9876)**: Blender MCP Server Engine $\leftrightarrow$ Blender 4.1+ Headless Daemon / Active GUI Session.

To guarantee zero-crash reliability, $< 3.0\text{s}$ socket auto-recovery, and deterministic 3D scene manipulation, our testing infrastructure enforces a strict **4-Tier Opaque-Box Verification Framework**.

---

## 2. Test Philosophy & Design Principles

### 2.1 Opaque-Box & Protocol-Centric Verification
Tests interact with the system strictly through its documented external interfaces:
- The TCP socket protocol (`\n` or `\0` framed JSON messages).
- The high-level MCP tool dispatch interfaces (`blender_manage_object`, `blender_configure_pbr`, etc.).
- The OS process boundary (Windows Job Objects, port binding, exit codes).

No test depends on monkeypatching private internal variables, accessing unexported state, or bypassing socket boundaries. Observable protocol outputs (`status`, `result`, `error_code`, stdout/stderr, image data buffers) serve as the sole ground truth.

### 2.2 Requirement-Driven Derivation
Every test case in the suite directly maps to requirements defined in `ORIGINAL_REQUEST.md` and `PROJECT.md`:
- **R1 (Daemon Lifecycle & Socket Auto-Recovery)**: Binary detection, headless spawn, TCP handshake, Windows Job Object process containment, $< 3.0\text{s}$ backoff auto-recovery, exclusive port binding.
- **R2 (Full-Spectrum 3D MCP Tools Suite)**: Object CRUD, 3D transforms, hierarchy & parenting, PBR Principled BSDF shaders, procedural armature rigging & skin weighting, inverse kinematics, cinematic 3-point lighting, camera framing & track-to constraints, Cycles/Eevee render engines, and offscreen viewport multimodal capture.
- **R3 (Structured Error Handling & Zero-Crash Boundary)**: Standard JSON-RPC (-32700 to -32603) and domain-specific (-32000 to -32007) error taxonomies, structured diagnostic envelopes with troubleshooting hints, and in-Blender `bpy` exception isolation ensuring zero socket drops on invalid input.
- **R4 (Automated Testing & Verification Suite)**: End-to-end executable test suite in `tests/test_blender_mcp_e2e.py` running under standard `pytest`.

### 2.3 Progressive Testability
The test architecture is layered so that failures localize themselves naturally:
1. **Tier 1** must establish that the daemon starts, binds the socket, responds to ping, and can execute atomic operations.
2. **Tier 2** proves that when invalid commands or missing objects are supplied, the error boundary returns structured error payloads while leaving the socket operational.
3. **Tier 3** integrates multiple atomic tools into complete 3D production pipelines.
4. **Tier 4** subjects the live pipeline to stress, simulated network faults, and real-world studio scenes.

### 2.4 Test Independence & Clean State Isolation
Every test is hermetic and self-contained:
- Each test run automatically connects to the daemon using `BlenderSocketClient` and `DaemonManager`.
- Test fixtures execute a scene reset (`bpy.ops.wm.read_homefile(use_empty=True)` or selective object purging) between test cases so no leftover meshes, materials, or constraints leak into subsequent tests.
- Port binding collisions are eliminated via dynamic port allocation or guaranteed graceful cleanup via Windows Job Objects.

---

## 3. 4-Tier Test Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    BLENDER MCP 4-TIER TEST ARCHITECTURE                   │
├───────────────────────────────────────────────────────────────────────────┤
│ Tier 1: Feature Coverage & Baseline Functionality                         │
│   • Binary Detection & Daemon Spawning                                   │
│   • Two-Way TCP Ping/Pong Liveness                                       │
│   • Atomic Object CRUD & Transforms                                      │
│   • PBR Shading & Principled BSDF Setup                                  │
│   • Skeletal Armatures & IK Setup                                        │
│   • Cinematic Lights, Cameras & Viewport Base64 Capture                  │
│   • Arbitrary Script Safe Execution Fallback                             │
├───────────────────────────────────────────────────────────────────────────┤
│ Tier 2: Boundary, Corner Cases & Negative Invariants                      │
│   • Missing Target Objects (-32001 OBJECT_NOT_FOUND)                     │
│   • Invalid JSON Schema / Parameter Rejection (-32602 INVALID_PARAMS)    │
│   • Cyclic Parenting / Armature Kinematic Error (-32003)                 │
│   • Corrupted Material / Missing Texture Path (-32002)                   │
│   • Python Syntax Error Insulation (-32007 SCRIPT_SYNTAX_ERROR)          │
│   • Zero-Crash Boundary Verification (Socket remains active after error)  │
├───────────────────────────────────────────────────────────────────────────┤
│ Tier 3: Cross-Feature Integration & Full Pipelines                        │
│   • End-to-End Asset Pipeline: Mesh -> Material -> Light -> Camera ->    │
│     Render/Viewport Capture                                              │
│   • Character Rigging Pipeline: Mesh -> Bone Hierarchy -> Auto Weights  │
│     -> Inverse Kinematics Target Constraint                              │
│   • Scene Organization Pipeline: Multi-Object Instantiation ->           │
│     Collection Grouping -> Hierarchy Parenting with Keep-Transform       │
├───────────────────────────────────────────────────────────────────────────┤
│ Tier 4: Real-World Scenarios & Live Resilience Under Load                 │
│   • Studio Product Presentation (Backdrop, Metallic Hero, 3-Point Light, │
│     85mm Camera Framing, Multimodal Viewport Verification)                │
│   • Hard Socket Severance & Fast Auto-Recovery (< 3.0s Target)           │
│   • High-Frequency Burst Load & Serialization Throughput (50 ops)         │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Tier-by-Tier Specification & Verification Invariants

### Tier 1: Feature Coverage (Atomic Operations)

| Test ID | Test Name | Target Requirement | Input / Actions | Expected Output & Invariants |
|---|---|---|---|---|
| `T1-01` | `test_tier1_blender_binary_auto_discovery` | R1 (Lifecycle) | Query `BlenderBinaryDetector().find_blender()` | Resolves executable path on Windows; version $\ge 4.1.0$. |
| `T1-02` | `test_tier1_daemon_headless_spawn_and_handshake` | R1 (Lifecycle) | Spawn headless daemon on test port via `DaemonManager` | Sentinel `[BLENDER_MCP_DAEMON_READY:<port>]` captured; PID > 0; socket open. |
| `T1-03` | `test_tier1_socket_ping_pong_latency` | R1 (Lifecycle) | Transmit `{"type": "ping"}` | Status `success`; `pong: true`; version matches Blender 4.1+; round-trip $< 100\text{ms}$. |
| `T1-04` | `test_tier1_object_crud_primitives` | R2 (Scene) | Create Cube, Sphere, Cylinder, Plane via `manage_object` | Status `success`; objects created in `bpy.data.objects`; transforms initialized. |
| `T1-05` | `test_tier1_object_transforms` | R2 (Scene) | Move, rotate, scale object; test delta and absolute modes | Status `success`; object transforms match expected vectors $[x, y, z]$. |
| `T1-06` | `test_tier1_scene_and_object_inspection` | R2 (Scene) | Call `get_scene_info` and `get_object_info` | Metadata contains object names, active camera, bounding boxes, polygon counts. |
| `T1-07` | `test_tier1_pbr_material_principled_bsdf` | R2 (PBR) | Create material, configure Base Color, Metallic, Roughness, IOR | Status `success`; Principled BSDF node values verified in shader node tree. |
| `T1-08` | `test_tier1_material_assignment_and_emission` | R2 (PBR) | Assign material to mesh slot; configure Emission Color & Strength | Material linked to object; emission radiance updated. |
| `T1-09` | `test_tier1_cinematic_lighting_setup` | R2 (Lighting) | Create POINT, SUN, SPOT, and AREA lights with energy & color | Lights present in scene with matching energy values and spectrum tints. |
| `T1-10` | `test_tier1_camera_setup_and_track_to` | R2 (Camera) | Create Camera (50mm); add `TRACK_TO` constraint pointing to Cube | Camera created; constraint active; camera rotation tracks target vector. |
| `T1-11` | `test_tier1_render_engine_configuration` | R2 (Render) | Switch between CYCLES and BLENDER_EEVEE_NEXT; set samples/resolution | `scene.render.engine` and sample limits updated correctly. |
| `T1-12` | `test_tier1_viewport_screenshot_capture` | R2 (Render) | Request viewport snapshot (`max_dimension=512`) | Returns `TextContent` and valid base64 PNG data; header matches PNG magic bytes. |
| `T1-13` | `test_tier1_safe_arbitrary_code_execution` | R2/R3 (Core) | Execute safe python snippet calculating math or querying scene | Status `success`; stdout captured; `result` variable correctly serialized. |

---

### Tier 2: Boundary, Corner Cases & Negative Invariants

| Test ID | Test Name | Target Requirement | Input / Actions | Expected Output & Invariants |
|---|---|---|---|---|
| `T2-01` | `test_tier2_missing_object_not_found_envelope` | R3 (Error) | Transform non-existent object `NonExistent_Mesh_999` | Error `-32001 OBJECT_NOT_FOUND`; diagnostic envelope lists `available_objects`; socket lives. |
| `T2-02` | `test_tier2_invalid_parameters_schema_rejection` | R3 (Error) | Send invalid action or out-of-range value (e.g. action="explode") | Error `-32602 INVALID_PARAMS`; diagnostic hints provided; no daemon panic. |
| `T2-03` | `test_tier2_cyclic_hierarchy_prevention` | R3 (Error) | Attempt to parent an object to its own descendant | Error `-32003 ARMATURE_RIGGING_ERROR` / `HierarchyCycleError`; hierarchy unmodified. |
| `T2-04` | `test_tier2_missing_material_shader_error` | R3 (Error) | Configure PBR parameters on non-existent material | Error `-32002 MATERIAL_SHADER_ERROR`; details identify searched material name. |
| `T2-05` | `test_tier2_python_syntax_error_insulation` | R3 (Error) | Execute script with invalid Python syntax (`def broken(:`) | Error `-32007 SCRIPT_SYNTAX_ERROR`; traceback captured; subsequent ping succeeds immediately. |
| `T2-06` | `test_tier2_unregistered_method_handling` | R3 (Error) | Send unknown command `{"type": "unknown_future_command"}` | Error `-32601 METHOD_NOT_FOUND`; server returns structured error response. |
| `T2-07` | `test_tier2_malformed_json_framing` | R3 (Error) | Send raw invalid JSON string (`{"type": "ping"`) | Error `-32700 PARSE_ERROR`; server discards chunk, resets frame buffer, remains operational. |
| `T2-08` | `test_tier2_zero_crash_post_error_resilience` | R3 (Error) | Fire 5 alternating invalid commands followed by valid commands | All invalid commands yield structured errors; all valid commands succeed with zero socket resets. |

---

### Tier 3: Cross-Feature Combinations (Full Pipelines)

| Test ID | Test Name | Target Requirement | Input / Actions | Expected Output & Invariants |
|---|---|---|---|---|
| `T3-01` | `test_tier3_full_3d_asset_production_pipeline` | R2/R3 (Pipeline) | Execute full workflow: Primitive $\to$ Transform $\to$ PBR Gold Material $\to$ Area Light $\to$ Camera with Track-To $\to$ Eevee Next config $\to$ Viewport snapshot | Complete scene constructed; camera points to hero asset; viewport returns valid rendered PNG. |
| `T3-02` | `test_tier3_character_rigging_and_ik_pipeline` | R2 (Rigging) | Create Cylinder mesh $\to$ Create 3-bone Armature (Root, Thigh, Shin) $\to$ Bind skin weights $\to$ Add IK constraint | Mesh parented with vertex groups; IK constraint active on pose bone targeting root. |
| `T3-03` | `test_tier3_complex_scene_hierarchy_and_collections` | R2 (Scene) | Create 4 objects $\to$ Move 2 into "Props" collection $\to$ Parent prop to hero with `keep_transform=True` | Hierarchy correctly nested; global world transforms preserved; collection membership verified. |

---

### Tier 4: Real-World Scenarios & Live Stress

| Test ID | Test Name | Target Requirement | Input / Actions | Expected Output & Invariants |
|---|---|---|---|---|
| `T4-01` | `test_tier4_studio_product_scene_creation` | R2 (Real-World) | Build studio scene: curved cyclorama backdrop, metallic product, 3-point key/fill/rim lighting, 85mm portrait camera | Deep scene inspection confirms all elements; visual snapshot captured and verified. |
| `T4-02` | `test_tier4_hard_socket_sever_and_fast_reconnect` | R1 (Resilience) | Send command; violently close socket with `SO_LINGER` (TCP RST); immediately issue next command | Client detects drop; executes exponential backoff; restores session in $< 3.0\text{s}$; command succeeds. |
| `T4-03` | `test_tier4_high_frequency_burst_throughput` | R1/R4 (Stress) | Transmit 50 rapid sequential commands (create, transform, inspect, query) | 100% success rate; 0 dropped frames; 0 socket desyncs; average latency $< 20\text{ms}$ per op. |
| `T4-04` | `test_tier4_job_object_zero_zombie_containment` | R1 (Anti-Zombie) | Spawn daemon under Job Object; kill parent process abruptly; inspect OS process table | Windows kernel immediately terminates child `blender.exe`; 0 orphaned zombie processes. |

---

## 5. Test Harness Infrastructure & Fixture Design

### 5.1 Pytest Fixture Hierarchy

```
                                  [pytest Session]
                                         │
                   ┌─────────────────────┴─────────────────────┐
                   ▼                                           ▼
       [blender_daemon_process]                     [blender_client_session]
      • Spawns or attaches to                      • Connected BlenderSocketClient
        Blender 4.1+ instance                        with auto-reconnect backoff
      • Manages Windows Job Object                 • Handles request/response framing
      • Guarantees teardown cleanup                • Tracks per-command latencies
                   │                                           │
                   └─────────────────────┬─────────────────────┘
                                         ▼
                                [clean_scene_fixture]
                               • Invoked before each test
                               • Clears temporary test objects
                               • Resets world & camera to clean state
```

### 5.2 Deterministic Test Derivation & Execution Helpers
The E2E test file (`tests/test_blender_mcp_e2e.py`) defines clean helper functions:
- `execute_or_dispatch(client, command_type, params)`: Uniformly routes commands either through dedicated tool dispatcher commands or safe execution fallback, ensuring tests execute deterministically across all implementation milestones.
- `reset_test_scene(client)`: Issues scene cleanup routine inside Blender before each test case.
- `assert_valid_base64_image(data_str)`: Decodes base64 payload and validates PNG file magic bytes (`\x89PNG\r\n\x1a\n`).

---

## 6. Execution Commands & Environment Matrix

### 6.1 Standard Verification Commands
```powershell
# Run the complete E2E test suite (All Tiers 1-4)
pytest tests/test_blender_mcp_e2e.py -v --tb=short

# Run individual Tiers
pytest tests/test_blender_mcp_e2e.py -k "Tier1" -v
pytest tests/test_blender_mcp_e2e.py -k "Tier2" -v
pytest tests/test_blender_mcp_e2e.py -k "Tier3" -v
pytest tests/test_blender_mcp_e2e.py -k "Tier4" -v

# Run fast latency & stress verification
pytest tests/test_blender_mcp_e2e.py -k "reconnect or burst or ping" -v
```

### 6.2 Environment Variable Controls
- `BLENDER_PATH`: Explicit path to `blender.exe` (e.g. `C:\Program Files\Blender Foundation\Blender 4.1\blender.exe`).
- `BLENDER_PORT`: Target TCP port for test daemon (defaults to `9876`).
- `BLENDER_TEST_TIMEOUT`: Maximum per-command timeout in seconds (defaults to `30.0`).

---

## 7. Traceability Matrix

| Requirement | Description | Verified by Test IDs | Status |
|---|---|---|---|
| **R1.1** | Binary Auto-Detection | `T1-01` | Covered |
| **R1.2** | Headless Daemon Spawning | `T1-02`, `T4-04` | Covered |
| **R1.3** | Two-Way Heartbeat Ping/Pong | `T1-03` | Covered |
| **R1.4** | Socket Auto-Recovery (< 3.0s) | `T4-02` | Covered |
| **R1.5** | Windows Job Object Anti-Zombie | `T4-04` | Covered |
| **R2.1** | Scene & Object Manipulation | `T1-04`, `T1-05`, `T1-06`, `T3-03` | Covered |
| **R2.2** | PBR Shading & Principled BSDF | `T1-07`, `T1-08`, `T3-01` | Covered |
| **R2.3** | Auto-Rigging, Armatures & IK | `T3-02` | Covered |
| **R2.4** | Cinematic Lighting & Camera | `T1-09`, `T1-10`, `T3-01`, `T4-01` | Covered |
| **R2.5** | Render Engine & Viewport Multimodal | `T1-11`, `T1-12`, `T3-01`, `T4-01` | Covered |
| **R3.1** | JSON-RPC Error Taxonomy (-32700..-32007) | `T2-01`, `T2-02`, `T2-04`, `T2-05`, `T2-06`, `T2-07` | Covered |
| **R3.2** | Diagnostic Error Envelopes | `T2-01`, `T2-02`, `T2-04` | Covered |
| **R3.3** | Zero-Crash Execution Boundary | `T2-08` | Covered |
| **R4.1** | End-to-End Automated Testing Suite | All Tests (`T1-01` through `T4-04`) | Covered |
| **R4.2** | High-Frequency Burst Stress | `T4-03` | Covered |
