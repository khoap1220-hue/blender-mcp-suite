import subprocess
import os

blender_exe = r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe"

test_script = r"""
import bpy
import time

print("SCRIPT STARTING in background mode:", bpy.app.background)

called = False
def my_timer():
    global called
    called = True
    print("TIMER FIRED!")
    return None

bpy.app.timers.register(my_timer, first_interval=0.1)

# In background mode, Blender executes the script from top to bottom.
# If the script finishes without keeping Blender alive, does Blender exit?
print("Script finished top-level execution. Waiting 0.5s...")
time.sleep(0.5)
print("Timer called after sleep?:", called)
"""

script_path = r"y:\MCP Blender Agent\.agents\explorer_survey_3\timer_bg_test.py"
with open(script_path, "w") as f:
    f.write(test_script)

res = subprocess.run(
    [blender_exe, "--background", "--factory-startup", "--python", script_path],
    capture_output=True,
    text=True,
    timeout=10
)
print("Return code:", res.returncode)
print("STDOUT:\n", res.stdout)
print("STDERR:\n", res.stderr)
