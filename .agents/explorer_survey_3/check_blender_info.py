import subprocess
import sys

blender_exe = r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe"
expr = "import sys, bpy; print('BLENDER_PYTHON_VERSION:', sys.version); print('BLENDER_APP_VERSION:', bpy.app.version_string); print('BLENDER_EXECUTABLE:', bpy.app.binary_path)"

res = subprocess.run(
    [blender_exe, "--background", "--factory-startup", "--python-expr", expr],
    capture_output=True,
    text=True
)
print("Return code:", res.returncode)
print("STDOUT:\n", res.stdout)
print("STDERR:\n", res.stderr)
