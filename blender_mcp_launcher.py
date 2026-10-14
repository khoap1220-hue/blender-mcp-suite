"""
blender_mcp_launcher.py — Clean stdio launcher for Blender MCP server.
Filters Python warnings to ensure pristine JSON-RPC communication on stdio.
"""

import warnings
warnings.filterwarnings("ignore")

import sys
import os

# Ensure default host & port
os.environ.setdefault("BLENDER_HOST", "127.0.0.1")
os.environ.setdefault("BLENDER_PORT", "9876")

from blender_mcp.server import main

if __name__ == "__main__":
    main()
