## 2026-09-16T08:46:09Z

Your working directory is: y:\MCP Blender Agent\.agents\spec_miner_survey_2
Your parent is orchestrator_1 (conversation ID: e9a95727-0c41-4e0e-9a40-d86e978a8623).

MANDATORY: Read y:\MCP Blender Agent\ORIGINAL_REQUEST.md first.

Task:
Extract and document the complete, rigorous specification for the Blender MCP suite:
1. Break down every requirement in ORIGINAL_REQUEST.md (R1, R2, R3, R4) into atomic features with clear inputs, outputs, schemas, and behavior.
2. For R1 (Daemon Lifecycle & Socket Auto-Recovery): specify auto-detection behavior, launch CLI arguments (--background, --python), healthcheck/ping ping-pong, exponential backoff reconnect formula, port binding and cleanup logic.
3. For R2 (Full-Spectrum 3D MCP Tools Suite): define precise MCP tool definitions (tool name, description, JSON schema for arguments, return format with content and isError):
   - Scene & Object Manipulation
   - PBR Shading & Materials (Principled BSDF, textures, roughness, metallic, normal, emission)
   - Auto-Rigging & Armatures (bones, automatic weights, IK constraints)
   - Cinematic Lighting & Camera Control (Sun, Point, Spot, Area, HDRI/World, Track-To Target, focal length)
   - Render Engine & Viewport Capture (Cycles & Eevee Next, resolution, samples, viewport snapshot)
4. For R3 (Structured Error Handling): specify error taxonomy, JSON-RPC error codes (-32602 invalid params, -32603 internal error, domain-specific codes), diagnostic message format.
5. For R4 (E2E Testing Suite): specify test requirements for tests/test_blender_mcp_e2e.py across Tiers 1-4.
6. Write your comprehensive specification in y:\MCP Blender Agent\.agents\spec_miner_survey_2\handoff.md.

Update your progress.md regularly. When finished, write handoff.md and notify parent via send_message.
