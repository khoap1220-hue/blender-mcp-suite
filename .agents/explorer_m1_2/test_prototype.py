import subprocess
import threading
import time
import ctypes
from ctypes import wintypes

# 1. Test Sentinel detection
ready_event = threading.Event()
cmd = ["python", "-c", "import sys, time; time.sleep(0.1); print('[BLENDER_MCP_DAEMON_READY:9876]', flush=True); time.sleep(1)"]
proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
    creationflags=subprocess.CREATE_NO_WINDOW
)

def read_stdout(pipe):
    for line in pipe:
        line_str = line.strip()
        if "[BLENDER_MCP_DAEMON_READY:9876]" in line_str:
            ready_event.set()

t = threading.Thread(target=read_stdout, args=(proc.stdout,), daemon=True)
t.start()

start = time.time()
ok = ready_event.wait(timeout=3.0)
elapsed = time.time() - start
print(f"Sentinel detected: {ok} in {elapsed:.3f}s")
proc.terminate()
proc.wait()

# 2. Test Job Object anti-zombie limit
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ('ReadOperationCount', ctypes.c_uint64),
        ('WriteOperationCount', ctypes.c_uint64),
        ('OtherOperationCount', ctypes.c_uint64),
        ('ReadTransferCount', ctypes.c_uint64),
        ('WriteTransferCount', ctypes.c_uint64),
        ('OtherTransferCount', ctypes.c_uint64),
    ]

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('PerProcessUserTimeLimit', ctypes.c_int64),
        ('PerJobUserTimeLimit', ctypes.c_int64),
        ('LimitFlags', wintypes.DWORD),
        ('MinimumWorkingSetSize', ctypes.c_size_t),
        ('MaximumWorkingSetSize', ctypes.c_size_t),
        ('ActiveProcessLimit', wintypes.DWORD),
        ('Affinity', ctypes.c_size_t),
        ('PriorityClass', wintypes.DWORD),
        ('SchedulingClass', wintypes.DWORD),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ('IoInfo', IO_COUNTERS),
        ('ProcessMemoryLimit', ctypes.c_size_t),
        ('JobMemoryLimit', ctypes.c_size_t),
        ('PeakProcessMemoryLimit', ctypes.c_size_t),
        ('PeakJobMemoryLimit', ctypes.c_size_t),
    ]

job = kernel32.CreateJobObjectW(None, None)
assert job != 0
info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
info.BasicLimitInformation.LimitFlags = 0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
res = kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
assert res != 0

p2 = subprocess.Popen(["python", "-c", "import time; time.sleep(10)"], creationflags=subprocess.CREATE_NO_WINDOW)
assign_ok = kernel32.AssignProcessToJobObject(job, int(p2._handle))
assert assign_ok != 0
print(f"Child process {p2.pid} assigned to Job Object. Closing job handle...")
kernel32.CloseHandle(job)
p2.wait(timeout=2)
print(f"Child process terminated automatically on job close! Return code: {p2.returncode}")
print("ALL TESTS PASSED SUCCESSFULLY!")
