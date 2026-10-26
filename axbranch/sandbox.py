"""Run generated code for its self-test with containment.

- Clean environment: only what Python needs to start. Credentials and session tokens in the
  parent's environment (API keys, CLI session tokens) never reach generated code.
- Windows Job Object: the whole process tree is capped (process count, memory) and killed when
  the check ends or times out — no orphaned grandchildren. Elsewhere: a new session + killpg.

- isolate=Manifest (Windows): additionally an AppContainer (isolation.py): the OS denies the program every file,
  registry key and network endpoint outside what the manifest grants, and child processes unless allowed. If the
  boundary cannot be set up the run does NOT start (isolation.IsolationUnavailable); there is no silent fallback.
Without isolate: not a security boundary against reading the user's files (same OS account).
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
                 'TEMP': tmp, 'TMP': tmp, 'TMPDIR': tmp, 'HOME': tmp, 'USERPROFILE': tmp, 'PYTHONUTF8': '1',
                 # Python's webbrowser honors BROWSER: under verification "open the browser" is a no-op,
                 # never a window on the Owner's desktop.
                 'BROWSER': 'cmd /c exit' if os.name == 'nt' else 'true'})
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

    def _job(caps=True, process_limit=MAX_PROCESSES):
        job = _k32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), 'CreateJobObject failed')
        info = _Extended()
        info.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE | ((ACTIVE_PROCESS | JOB_MEMORY) if caps else 0)
        info.BasicLimitInformation.ActiveProcessLimit = process_limit
        info.JobMemoryLimit = MAX_MEMORY
        if not _k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            _k32.CloseHandle(job)
            raise OSError(ctypes.get_last_error(), 'SetInformationJobObject failed')
        return job


def run(args, cwd, timeout, stdin_text='', extra_env=None, isolate=None):
    """Returns (returncode or None on timeout, combined output)."""
    proc = start(args, cwd, stdin_text, extra_env=extra_env, isolate=isolate)
    try:
        code = proc.wait(timeout)
        proc.stop()
        return code, proc.output()
    finally:
        proc.stop()
        proc.cleanup()


def start(args, cwd, stdin_text='', env=None, caps=True, extra_env=None, split=False, isolate=None):
    """A contained process that keeps running (e.g. a server under test). Always call stop().
    env=None -> the clean environment for generated code (plus extra_env); provider CLIs pass their own
    (logged-in) environment and caps=False, keeping only kill-the-whole-tree.
    split: stderr goes to its own file (streams()); output() still returns stdout then stderr."""
    return Contained(args, cwd, stdin_text, env, caps, extra_env, split, isolate)


class Contained:
    # Output goes to a file, not a pipe: a grandchild inheriting a pipe would keep us waiting until
    # it finished its work. We wait for the main process only, then kill whatever is left.
    def __init__(self, args, cwd, stdin_text, env=None, caps=True, extra_env=None, split=False, isolate=None):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-tmp-'))   # outside cwd: the program's folder stays as built
        self.log = self.tmp / 'output.txt'
        self.err_log = self.tmp / 'stderr.txt' if split else None
        self.proc = self.job = self._out = self._in = self._err = None
        self.manifest = isolate
        try:
            stdin_path = self.tmp / 'stdin.txt'
            stdin_path.write_bytes((stdin_text or '').encode('utf-8'))
            self._out = self.log.open('wb')
            self._in = stdin_path.open('rb')
            self._err = self.err_log.open('wb') if split else None
            if env is None:
                env = {**clean_env(str(self.tmp)), **(extra_env or {})}
            common = dict(cwd=cwd, env=env, stdin=self._in,
                          stdout=self._out, stderr=self._err or subprocess.STDOUT)
            if isolate is not None:
                from . import isolation
                isolation.check_grants(isolate)
                self.job = _job(True, process_limit=isolate.max_processes)
                isolate.writes = list(dict.fromkeys([*isolate.writes, str(self.tmp), str(cwd)]))
                isolate.reads = list(dict.fromkeys([*isolate.reads, *isolate.writes]))
                isolation.check_grants(isolate)
                self.proc = isolation.launch(isolation.isolated_args(args), cwd, env, self._in, self._out,
                                             self._err or self._out, isolate)
                if not _k32.AssignProcessToJobObject(self.job, int(self.proc._handle)):
                    self.proc.kill()
                    raise OSError(ctypes.get_last_error(), 'AssignProcessToJobObject failed')
                self.proc.resume()
                return
            if os.name != 'nt':
                self.proc = subprocess.Popen(args, start_new_session=True, **common)
                return
            self.job = _job(caps)
            # Suspended until it is inside the job, so nothing it starts can escape the limits.
            self.proc = subprocess.Popen(args, creationflags=CREATE_SUSPENDED | CREATE_NO_WINDOW, **common)
            if not _k32.AssignProcessToJobObject(self.job, int(self.proc._handle)):
                self.proc.kill()
                self.stop()
                raise OSError(ctypes.get_last_error(), 'AssignProcessToJobObject failed')
            status = _ntdll.NtResumeProcess(int(self.proc._handle))
            if status != 0:
                raise OSError(f'NtResumeProcess failed: {status}')
        except BaseException:
            # Construction can fail before the caller receives a process to stop.
            try:
                if self.proc is not None:
                    self.stop()
            finally:
                if self.job is not None:
                    _k32.CloseHandle(self.job)
                    self.job = None
                for handle in (self._out, self._in, self._err):
                    if handle is not None and not handle.closed:
                        handle.close()
                self.cleanup()
            raise

    def alive(self):
        return self.proc.poll() is None

    def wait(self, timeout):
        """Exit code, or None if still running after timeout."""
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def output(self):
        out, err = self.streams()
        return out + err

    def streams(self):
        """(stdout, stderr); stderr is '' unless started with split=True (then it is inside stdout)."""
        texts = []
        for f, path in ((self._out, self.log), (self._err, self.err_log)):
            if path is None:
                texts.append('')
                continue
            if not f.closed:
                f.flush()
            texts.append(path.read_bytes().decode('utf-8', errors='replace'))
        return texts[0], texts[1]

    def stop(self):
        """Kill the whole tree now (idempotent); returns the exit code if it had exited by itself."""
        code = self.proc.poll()
        if self.job is not None:
            _k32.TerminateJobObject(self.job, 1)
            self.proc.wait()
            _k32.CloseHandle(self.job)
            self.job = None
        elif os.name != 'nt':
            import signal
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except OSError:
                pass
            self.proc.wait()
        for f in (self._out, self._in, self._err):
            if f is not None and not f.closed:
                f.close()
        if hasattr(self.proc, 'close'):          # isolated: release handles, delete the per-run AppContainer profile
            self.proc.close()
        return code

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
