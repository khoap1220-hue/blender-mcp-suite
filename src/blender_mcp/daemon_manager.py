"""
src/blender_mcp/daemon_manager.py — Blender Daemon Lifecycle & Process Manager

Responsibilities:
1. 4-Stage Blender 4.1+ Binary Auto-Detection (Env, Known Paths, Registry, PATH).
2. Version validation via `blender.exe --version` regex check (requires 4.1+).
3. GUI Session Detection & Non-Destructive Attach (TCP port 9876 probe).
4. Headless Daemon Spawner with CREATE_NO_WINDOW & CREATE_NEW_PROCESS_GROUP.
5. Asynchronous stdout/stderr pipe draining and [BLENDER_MCP_DAEMON_READY:9876] sentinel capture.
6. Windows Job Object Anti-Zombie Containment (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE).
7. Graceful 3-phase shutdown (socket command -> process terminate -> process kill).
"""

from __future__ import annotations

import atexit
import collections
import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("blender_mcp.daemon_manager")

# ==============================================================================
# 1. Custom Exceptions
# ==============================================================================

class BlenderManagerError(Exception):
    """Base exception for all daemon manager errors."""
    pass

class BlenderNotFoundError(BlenderManagerError):
    """Raised when Blender 4.1+ executable cannot be located."""
    pass

class BlenderVersionError(BlenderManagerError):
    """Raised when Blender binary is located but fails version requirement (< 4.1)."""
    pass

class BlenderStartupError(BlenderManagerError):
    """Raised when headless Blender daemon fails to start or times out."""
    pass

class BlenderJobObjectError(BlenderManagerError):
    """Raised when Windows Job Object initialization or assignment fails."""
    pass


# ==============================================================================
# 2. Windows Job Object (ctypes) Anti-Zombie Containment
# ==============================================================================

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryLimit", ctypes.c_size_t),
        ("PeakJobMemoryLimit", ctypes.c_size_t),
    ]


class WindowsJobObject:
    """
    Encapsulates a Windows Job Object configured with
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE. Guarantees that any assigned child process
    is terminated unconditionally by the Windows kernel if the parent process exits,
    crashes, or is killed.
    """

    def __init__(self) -> None:
        self._handle: Optional[wintypes.HANDLE] = None
        self._is_windows = sys.platform == "win32"

    def create(self) -> bool:
        """Create and configure Job Object with KILL_ON_JOB_CLOSE."""
        if not self._is_windows:
            logger.debug("WindowsJobObject is a no-op on non-Windows platforms.")
            return False

        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE

            h_job = kernel32.CreateJobObjectW(None, None)
            if not h_job:
                err = ctypes.get_last_error()
                raise BlenderJobObjectError(f"CreateJobObjectW failed with error code: {err}")

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            kernel32.SetInformationJobObject.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            kernel32.SetInformationJobObject.restype = wintypes.BOOL

            res = kernel32.SetInformationJobObject(
                h_job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not res:
                err = ctypes.get_last_error()
                kernel32.CloseHandle(h_job)
                raise BlenderJobObjectError(f"SetInformationJobObject failed with error code: {err}")

            self._handle = h_job
            logger.info("Windows Job Object created with KILL_ON_JOB_CLOSE successfully (handle: %s).", h_job)
            return True

        except Exception as e:
            logger.warning("Failed to initialize Windows Job Object: %s", e)
            return False

    def assign_process(self, proc_or_pid: Union[subprocess.Popen, int]) -> bool:
        """Assign a child process handle to this Job Object."""
        if not self._is_windows or not self._handle:
            return False

        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

            if isinstance(proc_or_pid, subprocess.Popen):
                if hasattr(proc_or_pid, "_handle"):
                    h_proc = int(proc_or_pid._handle)
                else:
                    PROCESS_SET_QUOTA = 0x0100
                    PROCESS_TERMINATE = 0x0001
                    h_proc = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, proc_or_pid.pid)
            else:
                PROCESS_SET_QUOTA = 0x0100
                PROCESS_TERMINATE = 0x0001
                h_proc = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, proc_or_pid)

            res = kernel32.AssignProcessToJobObject(self._handle, h_proc)
            if not res:
                err = ctypes.get_last_error()
                logger.warning("AssignProcessToJobObject returned error %s (nested jobs or permission)", err)
                return False

            logger.info("Process successfully assigned to Windows Job Object.")
            return True

        except Exception as e:
            logger.warning("Exception during AssignProcessToJobObject: %s", e)
            return False

    def close(self) -> None:
        """Close Job Object handle. Child processes will be terminated by Windows."""
        if self._handle and self._is_windows:
            try:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel32.CloseHandle(self._handle)
                logger.info("Windows Job Object handle %s closed cleanly.", self._handle)
            except Exception as e:
                logger.warning("Error closing Windows Job Object handle: %s", e)
            finally:
                self._handle = None


# ==============================================================================
# 3. 4-Stage Blender 4.1+ Binary Auto-Detection
# ==============================================================================

class BlenderBinaryDetector:
    """
    4-Stage Blender 4.1+ Binary Locator:
    Stage 1: BLENDER_PATH environment variable
    Stage 2: Known Windows installation paths
    Stage 3: Windows Registry (HKLM/HKCU Uninstall keys & BlenderFoundation)
    Stage 4: System PATH
    Stage 5 (Validation): `blender.exe --version` regex check for 4.1+.
    """

    VERSION_REGEX = re.compile(r"Blender\s+(\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)

    def __init__(self, min_major: int = 4, min_minor: int = 1) -> None:
        self.min_major = min_major
        self.min_minor = min_minor

    def find_blender(self, explicit_path: Optional[str] = None) -> Tuple[str, str]:
        """
        Locates a valid Blender binary >= 4.1.
        Returns: (executable_path, version_string)
        Raises: BlenderNotFoundError, BlenderVersionError
        """
        candidates: List[Tuple[str, str]] = []

        # Stage 0: Explicit path if provided
        if explicit_path:
            candidates.extend(self._resolve_file_or_dir(explicit_path, "Explicit Argument"))

        # Stage 1: Environment Variables
        candidates.extend(self._from_environment())

        # Stage 2: Known Windows Installation Paths
        candidates.extend(self._from_known_paths())

        # Stage 3: Windows Registry
        candidates.extend(self._from_registry())

        # Stage 4: System PATH
        candidates.extend(self._from_system_path())

        # Deduplicate while preserving search order
        seen = set()
        deduped_candidates: List[Tuple[str, str]] = []
        for path, source in candidates:
            norm_path = os.path.normcase(os.path.abspath(path))
            if norm_path not in seen:
                seen.add(norm_path)
                deduped_candidates.append((path, source))

        if not deduped_candidates:
            raise BlenderNotFoundError(
                "Could not locate Blender executable in environment variables, known paths, "
                "Windows registry, or system PATH. Please set BLENDER_PATH."
            )

        # Stage 5: Version Validation
        rejected_versions: List[str] = []
        for path, source in deduped_candidates:
            is_valid, ver_tuple, ver_str = self.validate_version(path)
            if is_valid:
                logger.info("Selected Blender binary: %s (version: %s, source: %s)", path, ver_str, source)
                return path, ver_str
            else:
                if ver_str:
                    rejected_versions.append(f"{path} ({ver_str} from {source})")
                logger.debug("Rejected candidate %s (version: %s, source: %s)", path, ver_str, source)

        if rejected_versions:
            raise BlenderVersionError(
                f"Blender binary was found, but version requirement (>={self.min_major}.{self.min_minor}) "
                f"was not met: {', '.join(rejected_versions)}"
            )
        raise BlenderNotFoundError("No executable Blender binary satisfied version requirements.")

    def validate_version(self, executable_path: str) -> Tuple[bool, Optional[Tuple[int, int, int]], str]:
        """
        Runs `blender --version` and checks if version >= min_major.min_minor.
        Returns: (is_supported, (major, minor, patch), raw_version_string)
        """
        if not os.path.isfile(executable_path) or not os.access(executable_path, os.X_OK):
            return False, None, ""

        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            res = subprocess.run(
                [executable_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5.0,
                creationflags=flags,
            )
            output = res.stdout
            match = self.VERSION_REGEX.search(output)
            if match:
                major = int(match.group(1))
                minor = int(match.group(2))
                patch = int(match.group(3)) if match.group(3) else 0
                ver_str = f"{major}.{minor}.{patch}"
                is_supported = (major > self.min_major) or (major == self.min_major and minor >= self.min_minor)
                return is_supported, (major, minor, patch), ver_str
            return False, None, output.strip().split("\n")[0] if output else ""
        except Exception as e:
            logger.debug("Error probing version for %s: %s", executable_path, e)
            return False, None, ""

    def _resolve_file_or_dir(self, path_str: str, source_label: str) -> List[Tuple[str, str]]:
        if not path_str:
            return []
        p = Path(os.path.expandvars(os.path.expanduser(path_str)))
        if p.is_file():
            return [(str(p), source_label)]
        if p.is_dir():
            target = p / ("blender.exe" if sys.platform == "win32" else "blender")
            if target.is_file():
                return [(str(target), source_label)]
        return []

    def _from_environment(self) -> List[Tuple[str, str]]:
        res = []
        for var in ["BLENDER_PATH", "BLENDER_EXECUTABLE", "BLENDER_BIN"]:
            val = os.environ.get(var)
            if val:
                res.extend(self._resolve_file_or_dir(val, f"Env Var ${var}"))
        return res

    def _from_known_paths(self) -> List[Tuple[str, str]]:
        res = []
        if sys.platform != "win32":
            # Unix / macOS common locations
            unix_paths = [
                "/Applications/Blender.app/Contents/MacOS/Blender",
                "/usr/bin/blender",
                "/usr/local/bin/blender",
                "/snap/bin/blender",
            ]
            for p in unix_paths:
                if os.path.isfile(p):
                    res.append((p, "Known Unix Path"))
            return res

        # Windows known installation paths
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_appdata = os.environ.get("LOCALAPPDATA", "")

        versions = ["4.1", "4.2", "4.3", "4.4", "4.0", "5.0"]
        drives = ["C", "D", "E"]

        for v in versions:
            # Standard Program Files
            p = Path(prog_files) / "Blender Foundation" / f"Blender {v}" / "blender.exe"
            if p.is_file():
                res.append((str(p), f"Known Path ({v})"))

            # Alternate drive letters
            for d in drives:
                alt = Path(f"{d}:\\Program Files\\Blender Foundation\\Blender {v}\\blender.exe")
                if alt.is_file():
                    res.append((str(alt), f"Known Path ({d}:\\ {v})"))

        # Steam install locations
        steam_locations = [
            Path(prog_files) / "Steam" / "steamapps" / "common" / "Blender" / "blender.exe",
            Path(prog_files_x86) / "Steam" / "steamapps" / "common" / "Blender" / "blender.exe",
            Path(r"D:\SteamLibrary\steamapps\common\Blender\blender.exe"),
            Path(r"E:\SteamLibrary\steamapps\common\Blender\blender.exe"),
        ]
        for s in steam_locations:
            if s.is_file():
                res.append((str(s), "Steam common path"))

        # Scoop / Chocolatey
        if local_appdata:
            scoop = Path(os.environ.get("USERPROFILE", "")) / "scoop" / "apps" / "blender" / "current" / "blender.exe"
            if scoop.is_file():
                res.append((str(scoop), "Scoop apps path"))

        choco = Path(r"C:\ProgramData\chocolatey\bin\blender.exe")
        if choco.is_file():
            res.append((str(choco), "Chocolatey path"))

        return res

    def _from_registry(self) -> List[Tuple[str, str]]:
        if sys.platform != "win32":
            return []

        res = []
        try:
            import winreg
        except ImportError:
            return []

        hives = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]

        # 1. Uninstall registry keys
        uninstall_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]

        for hive in hives:
            for uninst in uninstall_paths:
                try:
                    with winreg.OpenKey(hive, uninst) as root_key:
                        idx = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(root_key, idx)
                                idx += 1
                                with winreg.OpenKey(root_key, subkey_name) as subkey:
                                    try:
                                        disp, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                        if "blender" in str(disp).lower():
                                            # Check InstallLocation
                                            try:
                                                loc, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                                                if loc:
                                                    cand = Path(str(loc)) / "blender.exe"
                                                    if cand.is_file():
                                                        res.append((str(cand), "Windows Registry Uninstall Location"))
                                            except OSError:
                                                pass

                                            # Check DisplayIcon
                                            try:
                                                icon, _ = winreg.QueryValueEx(subkey, "DisplayIcon")
                                                if icon:
                                                    icon_path = str(icon).split(",")[0].strip('"')
                                                    if icon_path.lower().endswith("blender.exe") and os.path.isfile(icon_path):
                                                        res.append((icon_path, "Windows Registry DisplayIcon"))
                                            except OSError:
                                                pass
                                    except OSError:
                                        pass
                            except OSError:
                                break
                except OSError:
                    pass

        # 2. BlenderFoundation direct install keys
        bf_keys = [
            r"SOFTWARE\BlenderFoundation",
            r"SOFTWARE\Blender Foundation",
            r"SOFTWARE\WOW6432Node\BlenderFoundation",
        ]
        for hive in hives:
            for bf_key in bf_keys:
                try:
                    with winreg.OpenKey(hive, bf_key) as k:
                        for val_name in ["Install_Dir", "InstallDir", "Path", ""]:
                            try:
                                val, _ = winreg.QueryValueEx(k, val_name)
                                res.extend(self._resolve_file_or_dir(str(val), f"Windows Registry {bf_key}\\{val_name}"))
                            except OSError:
                                pass
                except OSError:
                    pass

        # 3. App Paths
        for hive in hives:
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\blender.exe") as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    if val and os.path.isfile(str(val)):
                        res.append((str(val), "Windows Registry App Paths"))
            except OSError:
                pass

        return res

    def _from_system_path(self) -> List[Tuple[str, str]]:
        res = []
        target = "blender.exe" if sys.platform == "win32" else "blender"
        w = shutil.which(target)
        if w and os.path.isfile(w):
            res.append((w, "System PATH (shutil.which)"))

        path_env = os.environ.get("PATH", "")
        for entry in path_env.split(os.pathsep):
            entry_clean = entry.strip('"').strip()
            if entry_clean:
                cand = Path(entry_clean) / target
                if cand.is_file():
                    res.append((str(cand), "System PATH Scan"))
        return res


# ==============================================================================
# 4. DaemonManager: Spawner, GUI Attach, Sentinel & Lifecycle
# ==============================================================================

class DaemonManager:
    """
    Manages the Blender daemon process lifecycle:
    - Pre-checks existing GUI session on TCP port 9876.
    - Spawns headless background Blender daemon if no session active.
    - Captures stdout sentinel [BLENDER_MCP_DAEMON_READY:9876] with timeout.
    - Prevents zombie child processes via Windows Job Objects.
    - Drains stdout/stderr pipes asynchronously to prevent OS buffer deadlocks.
    - Provides 3-phase graceful shutdown and restart capabilities.
    """

    SENTINEL_PATTERN = re.compile(r"\[BLENDER_MCP_DAEMON_READY:(\d+)\]")

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9876,
        daemon_script_path: Optional[str] = None,
        custom_blender_path: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.custom_blender_path = custom_blender_path

        # Resolve daemon runner script path
        if daemon_script_path:
            self.daemon_script_path = Path(daemon_script_path).resolve()
        else:
            # Default to y:\MCP Blender Agent\daemon\blender_mcp_daemon.py
            repo_root = Path(__file__).resolve().parents[2]
            self.daemon_script_path = repo_root / "daemon" / "blender_mcp_daemon.py"

        self.detector = BlenderBinaryDetector()
        self.job_object = WindowsJobObject()

        # Runtime state
        self.blender_binary: Optional[str] = None
        self.blender_version: Optional[str] = None
        self.process: Optional[subprocess.Popen] = None
        self.is_gui_session: bool = False

        # Synchronization & Logging
        self._lock = threading.Lock()
        self._ready_event = threading.Event()
        self._stdout_logs: collections.deque[str] = collections.deque(maxlen=200)
        self._stderr_logs: collections.deque[str] = collections.deque(maxlen=200)
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

        # Clean exit hook
        atexit.register(self.shutdown)

    # --------------------------------------------------------------------------
    # Socket Probe (GUI Session Pre-Check)
    # --------------------------------------------------------------------------

    def probe_existing_session(self, timeout: float = 0.8) -> Optional[Dict[str, Any]]:
        """
        Fast TCP ping probe to host:port.
        Returns result dict if ping succeeds, None otherwise.
        Non-destructive: does not modify process state.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((self.host, self.port))
            payload = json.dumps({"type": "ping"}) + "\n"
            s.sendall(payload.encode("utf-8"))

            buffer = b""
            while b"\n" not in buffer:
                chunk = s.recv(1024)
                if not chunk:
                    break
                buffer += chunk

            if not buffer:
                return None

            resp = json.loads(buffer.decode("utf-8").strip())
            if resp.get("status") == "success" and resp.get("result", {}).get("pong"):
                return resp.get("result")
            return None
        except (ConnectionRefusedError, socket.timeout, OSError):
            return None
        finally:
            try:
                s.close()
            except Exception:
                pass

    # --------------------------------------------------------------------------
    # Lifecycle: Ensure Running
    # --------------------------------------------------------------------------

    def ensure_daemon_running(self, timeout: float = 15.0) -> Dict[str, Any]:
        """
        Main entry point for socket client / server engine:
        1. Probe if port is already active (GUI or existing daemon).
        2. If active, attach directly.
        3. If inactive, spawn headless daemon and wait for sentinel / readiness.
        """
        with self._lock:
            # 1. Pre-check existing session
            ping_res = self.probe_existing_session(timeout=1.0)
            if ping_res:
                if self.process is None:
                    self.is_gui_session = True
                    logger.info("Attached to pre-existing Blender GUI/Daemon session on %s:%s (PID: %s)",
                                self.host, self.port, ping_res.get("pid"))
                return {
                    "running": True,
                    "attached": True,
                    "is_gui": self.is_gui_session,
                    "port": self.port,
                    "pid": ping_res.get("pid"),
                    "version": ping_res.get("version"),
                }

            # If our process was already launched and is still alive, wait for it
            if self.process is not None and self.process.poll() is None:
                logger.info("Process already running, waiting for readiness...")
                if self._wait_for_readiness(timeout=timeout):
                    return self.get_status()

            # 2. Inactive -> Spawn headless daemon
            return self._spawn_headless(timeout=timeout)

    # --------------------------------------------------------------------------
    # Internal Spawner
    # --------------------------------------------------------------------------

    def _spawn_headless(self, timeout: float = 15.0) -> Dict[str, Any]:
        """Spawns headless background Blender with Job Object containment."""
        if not self.daemon_script_path.is_file():
            raise BlenderStartupError(f"Blender daemon script not found at: {self.daemon_script_path}")

        # Detect binary if not cached
        if not self.blender_binary:
            self.blender_binary, self.blender_version = self.detector.find_blender(self.custom_blender_path)

        # Build CLI arguments
        cmd = [
            self.blender_binary,
            "--background",
            "--python", str(self.daemon_script_path),
            "--",
            "--host", self.host,
            "--port", str(self.port),
        ]

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

        # Prepare state
        self._ready_event.clear()
        self._stdout_logs.clear()
        self._stderr_logs.clear()

        logger.info("Spawning headless Blender daemon: %s", " ".join(cmd))
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=creationflags,
                cwd=str(self.daemon_script_path.parent.parent),
            )
        except Exception as e:
            raise BlenderStartupError(f"Failed to spawn Blender process: {e}") from e

        # Anti-zombie containment: assign process to Windows Job Object
        self.job_object.create()
        self.job_object.assign_process(self.process)
        self.is_gui_session = False

        # Start asynchronous pipe readers to prevent deadlocks
        self._stdout_thread = threading.Thread(
            target=self._drain_pipe,
            args=(self.process.stdout, self._stdout_logs, True),
            daemon=True,
            name="blender-stdout-reader",
        )
        self._stderr_thread = threading.Thread(
            target=self._drain_pipe,
            args=(self.process.stderr, self._stderr_logs, False),
            daemon=True,
            name="blender-stderr-reader",
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

        # Wait for sentinel emission or socket ping readiness
        if not self._wait_for_readiness(timeout=timeout):
            exit_code = self.process.poll()
            recent_err = "\n".join(list(self._stderr_logs)[-15:])
            recent_out = "\n".join(list(self._stdout_logs)[-15:])
            self.shutdown(timeout=1.0)
            raise BlenderStartupError(
                f"Blender daemon failed to start on port {self.port} within {timeout}s "
                f"(exit code: {exit_code}).\nStdout:\n{recent_out}\nStderr:\n{recent_err}"
            )

        logger.info("Blender headless daemon successfully running on %s:%s (PID: %s)",
                    self.host, self.port, self.process.pid)
        return self.get_status()

    def _drain_pipe(self, pipe: Any, log_queue: collections.deque[str], check_sentinel: bool) -> None:
        """Continuously drains stdout/stderr pipe to prevent buffer deadlocks."""
        try:
            for line in iter(pipe.readline, ""):
                clean = line.strip()
                if clean:
                    log_queue.append(clean)
                    if check_sentinel:
                        match = self.SENTINEL_PATTERN.search(clean)
                        if match and int(match.group(1)) == self.port:
                            logger.info("Captured daemon ready sentinel: %s", clean)
                            self._ready_event.set()
        except (ValueError, OSError):
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _wait_for_readiness(self, timeout: float) -> bool:
        """Polls ready_event and verifies TCP ping probe within timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if process terminated prematurely
            if self.process and self.process.poll() is not None:
                return False

            # Check sentinel
            if self._ready_event.is_set():
                # Perform secondary socket verification
                if self.probe_existing_session(timeout=0.5):
                    return True

            # Direct socket probe fallback even if sentinel missed
            if self.probe_existing_session(timeout=0.2):
                return True

            time.sleep(0.1)

        return False

    # --------------------------------------------------------------------------
    # Graceful Shutdown
    # --------------------------------------------------------------------------

    def shutdown(self, timeout: float = 3.0) -> bool:
        """
        Gracefully terminates the daemon:
        1. If attached to GUI session, detach non-destructively (never kill GUI).
        2. If headless daemon:
           - Send {"type": "shutdown"} over socket.
           - Wait up to timeout seconds.
           - Fall back to process.terminate() and process.kill() if hung.
           - Close Windows Job Object.
        """
        with self._lock:
            # Detach from user's GUI session cleanly
            if self.is_gui_session:
                logger.info("Detaching from user's Blender GUI session; leaving Blender GUI intact.")
                self.is_gui_session = False
                return True

            if self.process is None:
                return True

            logger.info("Initiating graceful shutdown of Blender daemon (PID: %s)...", self.process.pid)

            # Phase 1: Socket shutdown command
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                s.connect((self.host, self.port))
                s.sendall(json.dumps({"type": "shutdown"}).encode("utf-8") + b"\n")
                s.close()
            except Exception as e:
                logger.debug("Could not send socket shutdown command: %s", e)

            # Phase 2: Wait for clean exit
            start = time.time()
            clean_exit = False
            while time.time() - start < timeout:
                if self.process.poll() is not None:
                    clean_exit = True
                    break
                time.sleep(0.1)

            # Phase 3: Fallback terminate & kill
            if not clean_exit and self.process.poll() is None:
                logger.warning("Blender daemon did not exit within %ss, terminating...", timeout)
                try:
                    self.process.terminate()
                    self.process.wait(timeout=1.0)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass

            # Phase 4: Close Job Object
            self.job_object.close()

            # Phase 5: Cleanup state
            self.process = None
            self._ready_event.clear()
            logger.info("Blender daemon shutdown complete.")
            return True

    def respawn_daemon(self, timeout: float = 15.0) -> Dict[str, Any]:
        """Forces a clean shutdown and respawns a fresh headless daemon."""
        logger.info("Respawning Blender daemon on %s:%s...", self.host, self.port)
        self.shutdown(timeout=2.0)
        return self.ensure_daemon_running(timeout=timeout)

    # --------------------------------------------------------------------------
    # Query & Status
    # --------------------------------------------------------------------------

    def is_running(self) -> bool:
        """Returns True if the daemon or GUI session is responding."""
        return self.probe_existing_session(timeout=0.5) is not None

    def get_status(self) -> Dict[str, Any]:
        """Returns snapshot of daemon lifecycle status."""
        active = self.is_running()
        mode = "stopped"
        if active:
            mode = "gui" if self.is_gui_session else "headless"

        pid = self.process.pid if self.process else None
        return {
            "running": active,
            "mode": mode,
            "host": self.host,
            "port": self.port,
            "pid": pid,
            "blender_path": self.blender_binary,
            "blender_version": self.blender_version,
            "is_gui": self.is_gui_session,
        }
```
