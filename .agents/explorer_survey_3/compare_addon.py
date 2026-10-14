import hashlib
import os

f1 = r"y:\MCP Blender Agent\addon\blender_mcp.py"
f2 = os.path.expandvars(r"%APPDATA%\Blender Foundation\Blender\4.1\scripts\addons\blender_mcp.py")

h1 = hashlib.sha256(open(f1, "rb").read()).hexdigest()
h2 = hashlib.sha256(open(f2, "rb").read()).hexdigest()
print("f1 hash:", h1)
print("f2 hash:", h2)
print("Identical:", h1 == h2)
