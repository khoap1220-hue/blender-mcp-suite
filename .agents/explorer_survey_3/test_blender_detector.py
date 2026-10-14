import os
import sys
import glob
import shutil
import winreg
from pathlib import Path

def find_blender_windows() -> str | None:
    # 1. Environment variable
    env_path = os.environ.get("BLENDER_PATH") or os.environ.get("BLENDER_EXECUTABLE")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2. Well-known standard paths
    standard_paths = [
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation\Blender 4.1\blender.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation\Blender\blender.exe"),
    ]
    for p in standard_paths:
        if os.path.isfile(p):
            return p

    # 2b. Glob standard Program Files
    prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    matches = glob.glob(os.path.join(prog_files, "Blender Foundation", "Blender*", "blender.exe"))
    if matches:
        # Sort reverse so higher versions come first
        matches.sort(reverse=True)
        return matches[0]

    # 3. PATH
    which_path = shutil.which("blender") or shutil.which("blender.exe")
    if which_path:
        return which_path

    # 4. Registry: App Paths
    for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
        for sub in [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\blender.exe",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\blender.exe",
        ]:
            try:
                with winreg.OpenKey(hive, sub) as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val and os.path.isfile(val):
                        return val
            except OSError:
                pass

    # 5. Registry: Uninstall keys
    for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
        for sub in [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]:
            try:
                with winreg.OpenKey(hive, sub) as key:
                    num_subkeys = winreg.QueryInfoKey(key)[0]
                    for i in range(num_subkeys):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subk:
                                try:
                                    disp, _ = winreg.QueryValueEx(subk, "DisplayName")
                                    if "blender" in disp.lower():
                                        loc, _ = winreg.QueryValueEx(subk, "InstallLocation")
                                        candidate = os.path.join(loc, "blender.exe")
                                        if os.path.isfile(candidate):
                                            return candidate
                                except OSError:
                                    pass
                        except OSError:
                            pass
            except OSError:
                pass

    # 6. Registry: blendfile association
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"blendfile\shell\open\command") as key:
            val, _ = winreg.QueryValueEx(key, "")
            # usually format: "C:\path\to\blender.exe" "%1"
            if val:
                import shlex
                parts = shlex.split(val)
                if parts and os.path.isfile(parts[0]):
                    return parts[0]
    except OSError:
        pass

    return None

if __name__ == "__main__":
    result = find_blender_windows()
    print("Detected Blender executable:", result)
