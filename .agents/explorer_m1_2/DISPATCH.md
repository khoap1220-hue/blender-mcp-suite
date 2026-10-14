## 2026-09-16T08:53:23Z
Your working directory is: y:\MCP Blender Agent\.agents\explorer_m1_2
Your parent is orchestrator_1 (conversation ID: e9a95727-0c41-4e0e-9a40-d86e978a8623).

MANDATORY: Read y:\MCP Blender Agent\ORIGINAL_REQUEST.md first.
Also read y:\MCP Blender Agent\PROJECT.md.

Milestone: M1 - Blender Daemon Lifecycle & Socket Auto-Recovery (R1).
Task:
Develop the precise technical implementation blueprint for src/blender_mcp/daemon_manager.py:
1. 4-Stage Blender 4.1 Binary Auto-Detection:
   - Environment variable BLENDER_PATH
   - Known Windows installation paths (C:\Program Files\Blender Foundation\Blender 4.1\blender.exe, etc.)
   - Windows Registry (HKLM/HKCU \SOFTWARE\BlenderFoundation\Install_Dir and Uninstall keys)
   - System PATH
   - Validate version via blender.exe --version regex check for 4.1+.
2. Process Spawner & GUI Session Detection:
   - Pre-check if port 9876 is already responding to ping (GUI session already open with MCP addon). If yes, attach directly without spawning.
   - If no active session, spawn headless daemon via subprocess.Popen with creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP.
   - Wait for [BLENDER_MCP_DAEMON_READY:9876] sentinel or socket readiness with timeout.
3. Windows Job Object Anti-Zombie Containment:
   - Use Windows Job Objects via ctypes (CreateJobObjectW, SetInformationJobObject with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000, AssignProcessToJobObject).
   - Guarantee zero orphan/zombie Blender processes if MCP server exits, terminates, or crashes.
4. Graceful Shutdown:
   - Send shutdown command over socket, wait up to 3 seconds for clean exit, fall back to process termination if needed.
5. Write full technical architecture, code design, and verification plan in y:\MCP Blender Agent\.agents\explorer_m1_2\handoff.md.

Update your progress.md regularly. When finished, write handoff.md and notify parent via send_message.
