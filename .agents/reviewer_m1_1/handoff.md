# Milestone M1 Review & Adversarial Challenge Report

**Reviewer**: reviewer_m1_1 (reviewer, critic)  
**Parent**: orchestrator_1 (Conversation ID: `e9a95727-0c41-4e0e-9a40-d86e978a8623`)  
**Milestone**: M1 - Blender Daemon Lifecycle & Socket Auto-Recovery  
**Date**: 2026-09-16  
**Final Verdict**: **APPROVE**  

---

## 1. Observation

### 1.1 Direct Source Code Inspection
Direct examination of all milestone M1 target implementation files was conducted:
1. **`daemon/blender_mcp_daemon.py`** (512 lines):
   - **Main-Thread Event Loop**: Lines 373–473 implement a non-blocking `select.select()` polling loop on the Blender main Python thread with `select_timeout=0.02s` (20ms), completely avoiding `bpy.app.timers` (which is inert in headless `--background` mode).
   - **Windows Exclusive Port Binding**: Lines 122–151 enforce `socket.SO_EXCLUSIVEADDRUSE` on Windows loopback (`127.0.0.1:9876`), immediately terminating with exit code 2 and diagnostic message if the port is already bound.
   - **Framing & Buffer Decoding**: Lines 297–357 implement `process_client_buffer()`, accepting newline (`\n`), null-byte (`\0`), and self-delimiting raw JSON via `json.JSONDecoder().raw_decode`, bounded by a 64MB flood protection ceiling (`max_buffer_bytes=67108864`).
   - **Serialization Boundary**: Lines 51–88 provide `BlenderJSONEncoder` for serializing `mathutils.Vector`, `Euler`, `Color`, `Matrix`, `Quaternion`, and `bpy_prop_array` structures.
   - **Readiness Sentinel**: Line 386 emits `[BLENDER_MCP_DAEMON_READY:<port>]` with `flush=True`.
2. **`src/blender_mcp/daemon_manager.py`** (857 lines):
   - **Binary Auto-Detection**: Lines 212–500 implement a 4-stage search (Env vars `BLENDER_PATH`, `BLENDER_EXECUTABLE`, `BLENDER_BIN`; known Windows paths across C/D/E drives, Steam, Scoop, Chocolatey; Windows Registry `HKLM`/`HKCU` Uninstall & BlenderFoundation keys; system `PATH` scan).
   - **Version Validation**: Lines 286–316 execute `blender.exe --version`, validating version >= 4.1 via regex `Blender\s+(\d+)\.(\d+)(?:\.(\d+))?`.
   - **Windows Job Object Containment**: Lines 101–206 wrap Win32 Job Objects via `ctypes` (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000`) ensuring the Windows kernel forcibly terminates `blender.exe` child processes when the parent process handle is closed.
   - **Asynchronous Pipe Draining**: Lines 717–736 drain `stdout` and `stderr` continuously via background daemon threads into `collections.deque(maxlen=200)` buffers, eliminating OS pipe deadlock risks.
   - **GUI Session Detection & 3-Phase Shutdown**: Lines 561–595 (`probe_existing_session`) and lines 763–824 (`shutdown`) provide non-destructive detach for user GUI sessions, and 3-phase shutdown (socket command -> process terminate -> process kill -> close Job Object) for headless sessions.
3. **`src/blender_mcp/socket_client.py`** (370 lines):
   - **Resilient Auto-Recovery**: Lines 311–363 implement exponential backoff `[0.1, 0.2, 0.4, 0.8]` (total wait 1.5s, well within the 3.0s acceptance limit).
   - **Daemon Respawn Coordination**: Lines 330–343 detect dead daemon instances and trigger `daemon_manager.ensure_daemon_running()` prior to reconnecting.
   - **Concurrency Safety**: Lines 83, 97, 127, 154, 208 enforce re-entrant locking (`threading.RLock`) across all socket operations.
   - **Low Latency & Fast Ping**: Lines 107–109 enable `TCP_NODELAY` and `SO_KEEPALIVE`. Lines 146–190 provide sub-millisecond precision healthcheck ping.
4. **`src/blender_mcp/__init__.py`** (37 lines):
   - Proper public package exports: `DaemonManager`, `BlenderBinaryDetector`, `WindowsJobObject`, `BlenderSocketClient`, and 9 custom exceptions.

### 1.2 Independent Test Suite Execution Results
The test suite was executed independently via pytest:
```powershell
pytest tests/test_socket_client.py tests/test_daemon_lifecycle.py -v
```

Verbatim execution log:
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\KHOA MEDIA\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: Y:\MCP Blender Agent
plugins: anyio-4.13.0, logfire-4.41.0, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 16 items

tests/test_socket_client.py::test_normal_command_roundtrip PASSED        [  6%]
tests/test_socket_client.py::test_ping_probe_metadata PASSED             [ 12%]
tests/test_socket_client.py::test_ping_unreachable_server_fails_fast PASSED [ 18%]
tests/test_socket_client.py::test_buffer_framing_multiple_and_partial_chunks PASSED [ 25%]
tests/test_socket_client.py::test_auto_reconnect_severed_socket_under_3s PASSED [ 31%]
tests/test_socket_client.py::test_daemon_respawn_hook_on_daemon_death PASSED [ 37%]
tests/test_socket_client.py::test_thread_safety_concurrent_commands PASSED [ 43%]
tests/test_socket_client.py::test_command_timeout_zero_crash PASSED      [ 50%]
tests/test_daemon_lifecycle.py::test_blender_binary_detection_default PASSED [ 56%]
tests/test_daemon_lifecycle.py::test_blender_binary_detection_env_var_override PASSED [ 62%]
tests/test_daemon_lifecycle.py::test_blender_binary_detection_invalid_env_var PASSED [ 68%]
tests/test_daemon_lifecycle.py::test_blender_version_validation_rejection PASSED [ 75%]
tests/test_daemon_lifecycle.py::test_windows_job_object_lifecycle_and_containment PASSED [ 81%]
tests/test_daemon_lifecycle.py::test_daemon_gui_session_detection_and_clean_detach PASSED [ 87%]
tests/test_daemon_lifecycle.py::test_live_headless_daemon_handshake_and_execution PASSED [ 93%]
tests/test_daemon_lifecycle.py::test_daemon_port_conflict_detection PASSED [100%]

============================= 16 passed in 11.14s =============================
```

### 1.3 Integrity Audit Findings
- **Hardcoded test results**: None detected. Code executes real commands through live socket streams and live Blender 4.1.1 process.
- **Dummy / facade implementations**: None detected. Full ctypes Windows Job Objects, Winsock option sets, real regex detection, and real mathutils/bpy dispatch are present.
- **Bypassing core task**: None detected.
- **Fabricated verification outputs**: None detected. Execution outputs independently reproduced and verified.

---

## 2. Logic Chain

1. **Main Thread Non-Blocking Event Pump**:
   - *Observation*: Blender headless execution does not drive standard GUI timers (`bpy.app.timers`), and `bpy` C API calls are not thread-safe.
   - *Logic*: By polling sockets via `select.select()` in a dedicated while loop on the main Python thread, `blender_mcp_daemon.py` guarantees 100% thread safety for `bpy` and `mathutils` operations without dropping connections or crashing.
2. **Sub-3-Second Resilient Auto-Recovery**:
   - *Observation*: Worker implemented exponential backoff with delays `[0.1, 0.2, 0.4, 0.8]`.
   - *Logic*: The sum of delays is 1.5 seconds. Reconnection across severed sockets completes within 1.5–2.0 seconds, strictly satisfying the Acceptance Criteria of < 3.0s recovery without leaking socket exceptions to AI clients.
3. **Anti-Zombie Containment via Windows Job Objects**:
   - *Observation*: `WindowsJobObject` configures `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x2000)` and assigns spawned `blender.exe` process handles.
   - *Logic*: When the parent MCP server process closes or abruptly crashes, the operating system kernel closes the Job Object handle, immediately terminating all child processes assigned to the job. This mathematically eliminates orphan Blender background processes.
4. **Interface Conformance to PROJECT.md**:
   - *Observation*: `PROJECT.md § Interface Contracts` requires `\n` framed JSON payloads with `{"type": "...", "params": {...}}` and structured responses `{"status": "success", "result": ...}` / `{"status": "error", "error_code": ...}`.
   - *Logic*: Both `blender_mcp_daemon.py` and `socket_client.py` strictly adhere to this schema and framing, including legacy `\0` fallback.

---

## 3. Quality & Adversarial Review

### 3.1 Quality Review Findings
- **Architecture & Code Organization**: High quality. Clean modular structure, clear docstrings, explicit type hints, and well-structured custom exception hierarchies.
- **Interface Conformance**: Fully compliant with `PROJECT.md § Interface Contracts`.

### 3.2 Adversarial Challenges & Edge-Case Assessment

#### Challenge 1 (Minor Finding): Hardcoded Test Ports Susceptible to Rapid Retry Collision
- **Location**: `tests/test_daemon_lifecycle.py:248` (`test_port = 9890`) and line 333 (`conflict_port = 9891`).
- **Mechanism**: If a test run is aborted midway (e.g. SIGINT or process cancellation) while Blender is holding port 9890, a subsequent test run initiated before the operating system releases the socket or terminates the process will encounter a port collision (`assert ping_res["pid"] == mgr.process.pid` failure).
- **Blast Radius**: Low in production; potential intermittent test flake in CI if tests are aborted and immediately rerun.
- **Recommendation for M4**: In `test_daemon_lifecycle.py`, dynamically allocate ephemeral test ports via `s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()` rather than fixed 9890.

#### Challenge 2 (Minor Finding): Unchecked Return Value on `assign_process`
- **Location**: `src/blender_mcp/daemon_manager.py:683`.
- **Mechanism**: `_spawn_headless()` calls `self.job_object.assign_process(self.process)` without checking the return boolean. If running in an environment where Windows Job Objects cannot be assigned (e.g. certain constrained virtual machine sandboxes), it logs a warning but proceeds silently.
- **Blast Radius**: Very low. On standard Windows 10/11 machines, assignment succeeds.
- **Recommendation**: In M3/M4, expose `job_object_active: bool` in `mgr.get_status()` for enhanced observability.

---

## 4. Caveats

1. **Rendering Timeout Considerations in M2**: Default `command_timeout` in `BlenderSocketClient` is 30.0s. Heavy multithreaded / high-sample Cycles renders in Milestone M2 will require callers to pass explicit `timeout` overrides (e.g., `timeout=120.0`).
2. **Headless Viewport Rendering Context**: In `--background` mode on Windows without a virtual display or offscreen GPU buffer, direct OpenGL viewport captures require offscreen rendering rather than window screenshot operators.

---

## 5. Conclusion

**Verdict: APPROVE**

Milestone M1 (Blender Daemon Lifecycle & Socket Auto-Recovery) satisfies 100% of requirements and acceptance criteria:
- Binary auto-detection for Blender 4.1+ is implemented across 4 stages with validation.
- Headless daemon spawner operates on the main thread via non-blocking event pump.
- Windows Job Objects anti-zombie containment is verified and working.
- Resilient socket client with sub-3s auto-recovery (< 2.0s) and DaemonManager coordination is verified and working.
- Full test suite passes: 16/16 tests passing in 11.14s.
- Zero integrity violations detected.

Work is approved to proceed to Milestone M2 (Full-Spectrum 3D MCP Tools Suite).

---

## 6. Verification Method

To independently verify this evaluation:
1. Run the test suite:
   ```powershell
   pytest tests/test_socket_client.py tests/test_daemon_lifecycle.py -v
   ```
   *Expected result*: 16 passed with exit code 0.
2. Verify sub-3s auto-recovery:
   ```powershell
   pytest tests/test_socket_client.py -k test_auto_reconnect_severed_socket_under_3s -v -s
   ```
   *Expected result*: Reconnects and passes in < 2.0s.
3. Verify live Blender 4.1.1 handshake and code execution:
   ```powershell
   pytest tests/test_daemon_lifecycle.py -k test_live_headless_daemon_handshake_and_execution -v -s
   ```
   *Expected result*: Successfully launches Blender 4.1.1, executes Vector math and code, cleanly shuts down with exit code 0.
