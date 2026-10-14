"""
official_blender_lab_bridge.py — MCP Bridge for the official Blender Lab Addon (projects.blender.org/lab/blender_mcp)

Translates between:
  MCP Client (Antigravity, Claude Code, Cursor, etc.)
       <── JSON-RPC 2.0 / stdio ──>
  THIS SCRIPT
       <── null-byte-delimited JSON / TCP ──>
  Blender Lab MCP addon (localhost:9876)

Protocol details:
  Official Blender Lab addon uses TCP on port 9876 with \\0 delimiter:
  Request:  {"type": "execute", "code": "...", "strict_json": true}\\0
  Response: {"status": "ok", "result": {...}}\\0
"""

import asyncio
import json
import os
import socket
import sys

try:
    import mcp.server.stdio
    from mcp.server import Server
    from mcp.types import TextContent, Tool
except ImportError:
    print("Error: 'mcp' package is required. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

BLENDER_HOST: str = os.environ.get("BLENDER_HOST", "127.0.0.1")
BLENDER_PORT: int = int(os.environ.get("BLENDER_PORT", "9876"))
SOCKET_TIMEOUT: float = float(os.environ.get("BLENDER_TIMEOUT", "30.0"))


def blender_exec(code: str, strict_json: bool = False) -> dict:
    """Send one execute request to Blender via TCP socket and return response dict."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(SOCKET_TIMEOUT)
    try:
        s.connect((BLENDER_HOST, BLENDER_PORT))
        payload = json.dumps({"type": "execute", "code": code, "strict_json": strict_json}) + "\0"
        s.sendall(payload.encode("utf-8"))
        buf = bytearray()
        while b"\0" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf.extend(chunk)
        null_idx = buf.index(b"\0") if b"\0" in buf else len(buf)
        if not buf:
            return {"status": "error", "message": "Empty response received from Blender socket."}
        return json.loads(buf[:null_idx])
    except ConnectionRefusedError:
        return {
            "status": "error",
            "message": (
                f"Could not connect to Blender at {BLENDER_HOST}:{BLENDER_PORT}. "
                "Ensure Blender is running and the MCP Server is started."
            ),
        }
    except Exception as e:
        return {"status": "error", "message": f"Socket communication error: {str(e)}"}
    finally:
        s.close()


def _format_response(resp: dict) -> str:
    lines = []
    if resp.get("status") == "error":
        lines.append(f"ERROR: {resp.get('message', 'Unknown error')}")
    else:
        result = resp.get("result")
        if result is not None:
            lines.append(json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result))
        else:
            lines.append("OK")
    for key in ("stdout", "stderr"):
        val = resp.get(key)
        if val:
            lines.append(f"\n--- {key} ---\n{val}")
    return "\n".join(lines)


server = Server("blender-lab-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="blender_execute",
            description=(
                "Execute arbitrary Python code inside Blender. "
                "Assign return values to the `result` variable. "
                "Example: result = {'version': bpy.app.version_string, 'objects': [o.name for o in bpy.data.objects]}"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute inside Blender."},
                    "strict_json": {
                        "type": "boolean",
                        "description": "If true, enforces JSON serialization on the result.",
                        "default": False,
                    },
                },
                "required": ["code"],
            },
        ),
        Tool(
            name="blender_get_scene",
            description="Query objects, active camera, render engine, and frame range of current scene.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="blender_ping",
            description="Test connectivity to the running Blender instance.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "blender_execute":
        code = arguments.get("code", "")
        strict_json = arguments.get("strict_json", False)
        resp = blender_exec(code, strict_json=strict_json)
        return [TextContent(type="text", text=_format_response(resp))]

    elif name == "blender_get_scene":
        inspect_code = """
import bpy
result = {
    "scene_name": bpy.context.scene.name,
    "render_engine": bpy.context.scene.render.engine,
    "active_camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
    "frame_current": bpy.context.scene.frame_current,
    "frame_range": [bpy.context.scene.frame_start, bpy.context.scene.frame_end],
    "objects": [
        {
            "name": obj.name,
            "type": obj.type,
            "location": list(round(c, 3) for c in obj.location),
            "visible": obj.visible_get()
        }
        for obj in bpy.context.scene.objects
    ]
}
"""
        resp = blender_exec(inspect_code, strict_json=True)
        return [TextContent(type="text", text=_format_response(resp))]

    elif name == "blender_ping":
        ping_code = "result = {'status': 'pong', 'blender_version': bpy.app.version_string}"
        resp = blender_exec(ping_code, strict_json=True)
        return [TextContent(type="text", text=_format_response(resp))]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
