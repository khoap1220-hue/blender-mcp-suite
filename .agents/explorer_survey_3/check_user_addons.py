import os

appdata = os.environ.get("APPDATA", "")
blender_user_dir = os.path.join(appdata, "Blender Foundation", "Blender", "4.1")
print("User AppData Blender 4.1 dir:", blender_user_dir)
print("Exists:", os.path.exists(blender_user_dir))
if os.path.exists(blender_user_dir):
    for root, dirs, files in os.walk(blender_user_dir):
        rel = os.path.relpath(root, blender_user_dir)
        print(f"[{rel}] dirs: {dirs}, files: {files}")
