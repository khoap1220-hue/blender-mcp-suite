import ctypes
from ctypes import wintypes
import subprocess
import time
import os

# Test Windows Job Object setup via ctypes (zero external dependencies!)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
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

def create_kill_on_close_job():
    h_job = kernel32.CreateJobObjectW(None, None)
    if not h_job:
        raise ctypes.WinError(ctypes.get_last_error())
    
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    
    success = kernel32.SetInformationJobObject(
        h_job,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info)
    )
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())
    return h_job

def assign_process_to_job(h_job, proc_handle):
    success = kernel32.AssignProcessToJobObject(h_job, proc_handle)
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())

# Test it
job = create_kill_on_close_job()
print("[+] Created Windows Job Object with KILL_ON_JOB_CLOSE successfully!")

# Let's test launching a process and assigning it
blender_exe = r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe"
p = subprocess.Popen([blender_exe, "--background", "--factory-startup", "--python-expr", "import time; time.sleep(10)"])
print(f"[+] Launched background Blender PID={p.pid}")

# Get process handle
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
h_proc = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, p.pid)
assign_process_to_job(job, h_proc)
kernel32.CloseHandle(h_proc)
print("[+] Assigned Blender process to Windows Job Object.")

# Now test closing the job handle -> Windows OS should instantly terminate Blender!
t0 = time.perf_counter()
kernel32.CloseHandle(job)
p.wait(timeout=3)
elapsed = time.perf_counter() - t0
print(f"[+] Job handle closed -> Blender terminated cleanly by Windows OS in {elapsed*1000:.1f}ms! Returncode={p.returncode}")
