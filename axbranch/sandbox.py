"""Run generated code for its self-test with containment.

- Clean environment: only what Python needs to start. Credentials and session tokens in the
  parent's environment (API keys, CLI session tokens) never reach generated code.
- Windows Job Object: the whole process tree is capped (process count, memory) and killed when
  the check ends or times out — no orphaned grandchildren. Elsewhere: a new session + killpg.

Not a security boundary against reading the user's files: same OS account. A separate
low-privilege account is the upgrade path (see docs/DECISIONS.md D12).
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_PROCESSES = 8
MAX_MEMORY = 1024 * 1024 * 1024        # bytes, whole tree


def clean_env(tmp):
    keep = {k: os.environ[k] for k in ('SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC', 'PATHEXT', 'LANG')
            if k in os.environ}
    keep.update({'PATH': os.path.dirname(os.__file__) if os.name != 'nt' else os.environ.get('SYSTEMROOT', '') + r'\system32',
                 'TEMP': tmp, 'TMP': tmp, 'TMPDIR': tmp, 'HOME': tmp, 'USERPROFILE': tmp, 'PYTHONUTF8': '1'})
    return keep


if os.name == 'nt':
    import ctypes
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD)]

    class _Extended(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', _Basic), ('IoInfo', ctypes.c_uint64 * 6),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    _k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _ntdll = ctypes.WinDLL('ntdll')
    _ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
    CREATE_SUSPENDED, CREATE_NO_WINDOW = 0x4, 0x08000000
    KILL_ON_JOB_CLOSE, ACTIVE_PROCESS, JOB_MEMORY = 0x2000, 0x8, 0x200

    def _job():
        job = _k32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), 'CreateJobObject failed')
        info = _Extended()
        info.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE | ACTIVE_PROCESS | JOB_MEMORY
        info.BasicLimitInformation.ActiveProcessLimit = MAX_PROCESSES
        info.JobMemoryLimit = MAX_MEMORY
        if not _k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            _k32.CloseHandle(job)
            raise OSError(ctypes.get_last_error(), 'SetInformationJobObject failed')
        return job


def run(args, cwd, timeout):
    """Returns (returncode or None on timeout, combined output)."""
    tmp = tempfile.mkdtemp(prefix='axb-tmp-')          # outside cwd: the program's folder stays as built
    try:
        return _run(args, cwd, timeout, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(args, cwd, timeout, tmp):
    # Output goes to a file, not a pipe: a grandchild inheriting a pipe would keep us waiting until
    # it finished its work. We wait for the main process only, then kill whatever is left.
    log = Path(tmp) / 'output.txt'
    with log.open('wb') as out:
        common = dict(cwd=cwd, env=clean_env(tmp), stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
        code = _launch_and_wait(args, timeout, common)
    return code, log.read_bytes().decode('utf-8', errors='replace')


def _launch_and_wait(args, timeout, common):
    if os.name != 'nt':
        import signal
        proc = subprocess.Popen(args, start_new_session=True, **common)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)       # the main process and anything it left behind
            except OSError:
                pass
            proc.wait()
    job = _job()
    try:
        # Suspended until it is inside the job, so nothing it starts can escape the limits.
        proc = subprocess.Popen(args, creationflags=CREATE_SUSPENDED | CREATE_NO_WINDOW, **common)
        if not _k32.AssignProcessToJobObject(job, int(proc._handle)):
            proc.kill()
            proc.wait()
            raise OSError(ctypes.get_last_error(), 'AssignProcessToJobObject failed')
        _ntdll.NtResumeProcess(int(proc._handle))
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        finally:
            _k32.TerminateJobObject(job, 1)               # whole tree, now — not when it chooses to exit
            proc.wait()
    finally:
        _k32.CloseHandle(job)
