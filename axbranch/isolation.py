"""OS-enforced isolation for generated programs: Windows AppContainer + the existing Job Object.

Why AppContainer: built into Windows 8+ (documented Win32 app isolation), needs no administrator rights, no OS
feature, account or firewall change. A process in an AppContainer is denied every securable object (files,
registry, named objects) unless that object's ACL grants its package SID or one of its capability SIDs, and it has
no network access unless a network capability is granted (none is). Loopback is blocked for AppContainers too.

Per run (Manifest):
- a fresh package SID derived from a unique name (never registered, nothing persistent is created), so a grant made
  for one run is useless to any other run (no stale authority);
- read/write grants ONLY on directories AX Branch created for this run (a copy of the artifact), never on the
  Owner's folders, the Python installation or system locations;
- a private Python runtime (stdlib copy) granted once to a custom capability SID that every run carries;
- child processes forbidden by the OS (PROC_THREAD_ATTRIBUTE_CHILD_PROCESS_POLICY) unless the manifest allows them;
- clean environment (no credentials), Job Object limits and kill-on-close (sandbox.py).

Not covered: GPU/driver interfaces, side channels, kernel exploits, objects that grant ALL APPLICATION PACKAGES
(e.g. most of C:\\Windows, Program Files: readable, not writable). Third-party packages outside the stdlib are not in
the runtime: such programs are refused (they need a separately approved setup)."""
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

RUNTIME_CAPABILITY = 'axbranchSandboxRuntime'
RUNTIME_VERSION = 2
SKIP = {'test', 'idlelib', 'ensurepip', '__pycache__', 'lib2to3', 'pip'}    # site-packages kept: same imports as before


@dataclass
class Manifest:
    """What one isolated run may touch. Recorded with the run as its evidence identity."""
    purpose: str
    artifact_sha256: str = ''
    reads: list = field(default_factory=list)      # directories AX Branch created for this run
    writes: list = field(default_factory=list)
    network: str = 'none'                           # the only supported value
    child_processes: bool = False
    max_processes: int = 8
    allow_custom_acl: bool = False                 # native bootloader creates a private extraction DACL
    lifetime_seconds: int = 120
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    backend: str = 'appcontainer'
    package_sid: str = ''

    def record(self):
        return asdict(self)


class IsolationUnavailable(RuntimeError):
    """The required isolation cannot be provided: the protected execution must not run."""


if os.name == 'nt':
    from ctypes import wintypes
    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _adv = ctypes.WinDLL('advapi32', use_last_error=True)
    _env = ctypes.WinDLL('userenv', use_last_error=True)
    _kb = ctypes.WinDLL('kernelbase', use_last_error=True)

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [('Sid', ctypes.c_void_p), ('Attributes', wintypes.DWORD)]

    class SECURITY_CAPABILITIES(ctypes.Structure):
        _fields_ = [('AppContainerSid', ctypes.c_void_p), ('Capabilities', ctypes.POINTER(SID_AND_ATTRIBUTES)),
                    ('CapabilityCount', wintypes.DWORD), ('Reserved', wintypes.DWORD)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR), ('lpDesktop', wintypes.LPWSTR),
                    ('lpTitle', wintypes.LPWSTR), ('dwX', wintypes.DWORD), ('dwY', wintypes.DWORD),
                    ('dwXSize', wintypes.DWORD), ('dwYSize', wintypes.DWORD), ('dwXCountChars', wintypes.DWORD),
                    ('dwYCountChars', wintypes.DWORD), ('dwFillAttribute', wintypes.DWORD),
                    ('dwFlags', wintypes.DWORD), ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD),
                    ('lpReserved2', ctypes.c_void_p), ('hStdInput', wintypes.HANDLE),
                    ('hStdOutput', wintypes.HANDLE), ('hStdError', wintypes.HANDLE)]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [('StartupInfo', STARTUPINFOW), ('lpAttributeList', ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE),
                    ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)]

    _env.DeriveAppContainerSidFromAppContainerName.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p))
    _env.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
    _env.CreateAppContainerProfile.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
                                               wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))
    _env.CreateAppContainerProfile.restype = ctypes.c_long
    _env.DeleteAppContainerProfile.argtypes = (wintypes.LPCWSTR,)
    _env.DeleteAppContainerProfile.restype = ctypes.c_long
    _kb.DeriveCapabilitySidsFromName.argtypes = (
        wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD))
    _kb.DeriveCapabilitySidsFromName.restype = wintypes.BOOL
    _adv.ConvertSidToStringSidW.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))
    _adv.FreeSid.argtypes = (ctypes.c_void_p,)
    _k32.LocalFree.argtypes = (ctypes.c_void_p,)
    _k32.InitializeProcThreadAttributeList.argtypes = (ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                                       ctypes.POINTER(ctypes.c_size_t))
    _k32.UpdateProcThreadAttribute.argtypes = (ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p,
                                               ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p)
    _k32.DeleteProcThreadAttributeList.argtypes = (ctypes.c_void_p,)
    _k32.CreateProcessW.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                    wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
                                    ctypes.c_void_p, ctypes.POINTER(PROCESS_INFORMATION))
    _k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    _k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    _k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _k32.SetHandleInformation.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)

    ATTR_HANDLE_LIST, ATTR_SECURITY_CAPABILITIES, ATTR_CHILD_PROCESS_POLICY = 0x20002, 0x20009, 0x2000E
    CHILD_PROCESS_RESTRICTED = 0x1
    SE_GROUP_ENABLED = 0x4
    CREATE_SUSPENDED, DETACHED_PROCESS = 0x4, 0x8
    EXTENDED_STARTUPINFO_PRESENT, CREATE_UNICODE_ENVIRONMENT = 0x80000, 0x400
    STARTF_USESTDHANDLES, HANDLE_FLAG_INHERIT = 0x100, 0x1


def _sid_string(psid):
    out = wintypes.LPWSTR()
    if not _adv.ConvertSidToStringSidW(psid, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), 'ConvertSidToStringSid failed')
    try:
        return out.value
    finally:
        _k32.LocalFree(out)


def _package_sid(name):
    psid = ctypes.c_void_p()
    hr = _env.DeriveAppContainerSidFromAppContainerName(name, ctypes.byref(psid))
    if hr != 0:
        raise IsolationUnavailable(f'DeriveAppContainerSidFromAppContainerName failed (0x{hr & 0xffffffff:08x})')
    return psid


def _create_profile(name):
    """Register a per-run AppContainer profile (CreateProcess needs it); deleted when the run ends."""
    psid = ctypes.c_void_p()
    hr = _env.CreateAppContainerProfile(name, name, 'AX Branch isolated run', None, 0, ctypes.byref(psid))
    if hr & 0xffffffff == 0x800700B7:                     # already exists (e.g. a crashed earlier attempt)
        return _package_sid(name)
    if hr != 0:
        raise IsolationUnavailable(f'CreateAppContainerProfile failed (0x{hr & 0xffffffff:08x})')
    return psid


def delete_profile(name):
    _env.DeleteAppContainerProfile(name)


def _capability_sid(name):
    """(raw SID pointer, string) of a custom capability; the derived arrays are leaked deliberately (tiny, once)."""
    groups, gcount = ctypes.c_void_p(), wintypes.DWORD()
    sids, scount = ctypes.c_void_p(), wintypes.DWORD()
    if not _kb.DeriveCapabilitySidsFromName(name, ctypes.byref(groups), ctypes.byref(gcount),
                                             ctypes.byref(sids), ctypes.byref(scount)) or not scount.value:
        raise IsolationUnavailable(f'DeriveCapabilitySidsFromName failed ({ctypes.get_last_error()})')
    first = ctypes.cast(sids, ctypes.POINTER(ctypes.c_void_p))[0]
    return first, _sid_string(first)


def grant(path, sid_string, write, custom_acl=False):
    """Grant one SID access to a directory AX Branch created (inherited by everything inside)."""
    rights = '(OI)(CI)(M)' if write else '(OI)(CI)(RX)'
    extra = ['/grant', f'*{sid_string}:(OI)(CI)(WDAC)'] if write and custom_acl else []
    r = subprocess.run(['icacls', str(path), '/grant', f'*{sid_string}:{rights}', *extra, '/T', '/C', '/Q'],
                       capture_output=True, text=True, errors='replace', creationflags=0x08000000)
    if r.returncode != 0:
        raise IsolationUnavailable(f'could not grant run access to {path}: {r.stdout.strip()} {r.stderr.strip()}'[:300])


def python_source():
    """The real Python installation generated programs ran with before (a packaged AX Branch has none of its own)."""
    if not getattr(sys, 'frozen', False):
        return Path(sys.base_prefix)
    found = shutil.which('python') or shutil.which('py')
    if not found:
        raise IsolationUnavailable('no Python installation found to build the isolated runtime')
    return Path(found).resolve().parent


def runtime_dir(root=None):
    """A private Python runtime (stdlib + the installation's site-packages, without pip) readable by isolated runs,
    built once and reused. Copied from the installation; the installation itself is never modified."""
    base = python_source()
    root = Path(root or Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AXBranch' / 'sandbox-runtime')
    target = root / f'py{sys.version_info.major}{sys.version_info.minor}-v{RUNTIME_VERSION}'
    marker = target / 'READY.json'
    if marker.is_file():
        return target
    staging = root / f'.staging-{uuid.uuid4().hex[:8]}'
    staging.mkdir(parents=True)
    try:
        for name in os.listdir(base):
            p = base / name
            if p.is_file() and (name.lower().endswith(('.exe', '.dll')) and name.lower() != 'pythonw.exe'):
                shutil.copy2(p, staging / name)
        for sub in ('DLLs', 'tcl'):
            if (base / sub).is_dir():
                shutil.copytree(base / sub, staging / sub)
        shutil.copytree(base / 'Lib', staging / 'Lib',
                        ignore=lambda d, names: [n for n in names if n in SKIP or n.endswith('.pyc')])
        (staging / 'pyvenv.cfg').unlink(missing_ok=True)
        grant(staging, _capability_sid(RUNTIME_CAPABILITY)[1], write=False)
        (staging / 'READY.json').write_text(json.dumps({'source': str(base), 'version': sys.version,
                                                        'runtime_version': RUNTIME_VERSION}), encoding='utf-8')
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def available():
    """(True, '') when this machine can enforce the boundary now; otherwise (False, actionable reason)."""
    if os.name != 'nt':
        return False, 'OS isolation backend is implemented for Windows only (AppContainer)'
    try:
        psid = _package_sid('AXBranch.Probe')
        _adv.FreeSid(psid)
        _capability_sid(RUNTIME_CAPABILITY)
        return True, ''
    except (IsolationUnavailable, OSError, AttributeError) as e:
        return False, f'AppContainer isolation unavailable: {e}'


class Process:
    """Minimal Popen-like handle for an AppContainer process (what sandbox.Contained needs)."""
    def __init__(self, info):
        self._handle, self._thread, self.pid = info.hProcess, info.hThread, info.dwProcessId
        self.returncode = None

    def poll(self):
        if self.returncode is None and _k32.WaitForSingleObject(self._handle, 0) == 0:
            code = wintypes.DWORD()
            _k32.GetExitCodeProcess(self._handle, ctypes.byref(code))
            self.returncode = code.value if code.value < 0x80000000 else code.value - 0x100000000
        return self.returncode

    def wait(self, timeout=None):
        ms = 0xFFFFFFFF if timeout is None else int(timeout * 1000)
        if _k32.WaitForSingleObject(self._handle, ms) != 0:
            raise subprocess.TimeoutExpired('isolated process', timeout)
        return self.poll()

    def kill(self):
        if self.poll() is None:
            _k32.TerminateProcess(self._handle, 1)

    def resume(self):
        if ctypes.WinDLL('kernel32').ResumeThread(wintypes.HANDLE(self._thread)) == 0xFFFFFFFF:
            raise OSError(ctypes.get_last_error(), 'ResumeThread failed')

    def close(self):
        for h in (self._thread, self._handle):
            if h:
                _k32.CloseHandle(h)
        self._thread = self._handle = None
        if getattr(self, 'profile', None):
            delete_profile(self.profile)
            self.profile = None


def launch(args, cwd, env, stdin, stdout, stderr, manifest):
    """Start args SUSPENDED inside a fresh AppContainer (caller assigns the Job Object, then resume()).
    stdin/stdout/stderr: open file objects (inherited handles only). Grants for manifest.reads/writes are applied
    to the package SID first; anything else is denied by the OS."""
    if os.name != 'nt':
        raise IsolationUnavailable('OS isolation backend is implemented for Windows only')
    if manifest.network != 'none':
        raise IsolationUnavailable(f'network scope {manifest.network!r} is not supported by the isolated backend')
    profile = f'AXBranch.Run.{manifest.run_id}'
    psid = _create_profile(profile)
    attrs = None
    ok = False
    try:
        manifest.package_sid = _sid_string(psid)
        for d in manifest.reads:
            grant(d, manifest.package_sid, write=False)
        for d in manifest.writes:
            grant(d, manifest.package_sid, write=True, custom_acl=manifest.allow_custom_acl)
        cap_sid, _ = _capability_sid(RUNTIME_CAPABILITY)
        caps = (SID_AND_ATTRIBUTES * 1)(SID_AND_ATTRIBUTES(cap_sid, SE_GROUP_ENABLED))
        sc = SECURITY_CAPABILITIES(psid, caps, 1, 0)
        handles = []
        for f in (stdin, stdout, stderr):
            h = wintypes.HANDLE(__import__('msvcrt').get_osfhandle(f.fileno()))
            _k32.SetHandleInformation(h, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
            handles.append(h)
        unique = list(dict.fromkeys(h.value for h in handles))
        hlist = (wintypes.HANDLE * len(unique))(*unique)
        size = ctypes.c_size_t()
        _k32.InitializeProcThreadAttributeList(None, 3, 0, ctypes.byref(size))
        attrs = ctypes.create_string_buffer(size.value)
        if not _k32.InitializeProcThreadAttributeList(attrs, 3, 0, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), 'InitializeProcThreadAttributeList failed')
        policy = wintypes.DWORD(0 if manifest.child_processes else CHILD_PROCESS_RESTRICTED)
        for attr, ptr, n in ((ATTR_SECURITY_CAPABILITIES, ctypes.byref(sc), ctypes.sizeof(sc)),
                             (ATTR_HANDLE_LIST, hlist, ctypes.sizeof(hlist)),
                             (ATTR_CHILD_PROCESS_POLICY, ctypes.byref(policy), ctypes.sizeof(policy))):
            if not _k32.UpdateProcThreadAttribute(attrs, 0, attr, ptr, n, None, None):
                raise OSError(ctypes.get_last_error(), f'UpdateProcThreadAttribute 0x{attr:x} failed')
        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        si.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        si.StartupInfo.hStdInput, si.StartupInfo.hStdOutput, si.StartupInfo.hStdError = handles
        si.lpAttributeList = ctypes.addressof(attrs)
        private = env.get('TEMP') or str(cwd)        # AppContainer creation needs LOCALAPPDATA; keep it run-private
        # GetTempPathW redirects AppContainer temp into this package-relative tree even
        # when TEMP is set. Native onefile bootloaders use that API before Python runs.
        # Create the parents inside the already-granted run temp, never in the Owner profile.
        (Path(private) / 'Packages' / profile.lower() / 'AC' / 'Temp').mkdir(parents=True, exist_ok=True)
        env = {**env, 'LOCALAPPDATA': private, 'APPDATA': private}
        block = ''.join(f'{k}={v}\0' for k, v in sorted(env.items())) + '\0'
        envbuf = ctypes.create_unicode_buffer(block, len(block))
        cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(a) for a in args]))
        info = PROCESS_INFORMATION()
        # DETACHED: no console, so no conhost child (the child-process policy would block it; std handles are files)
        flags = CREATE_SUSPENDED | DETACHED_PROCESS | EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT
        if not _k32.CreateProcessW(None, cmd, None, None, True, flags, envbuf, str(cwd), ctypes.byref(si),
                                   ctypes.byref(info)):
            raise IsolationUnavailable(f'CreateProcess in AppContainer failed ({ctypes.get_last_error()})')
        proc = Process(info)
        proc.profile = profile
        ok = True
        return proc
    finally:
        if not ok:
            delete_profile(profile)
        if attrs is not None:
            _k32.DeleteProcThreadAttributeList(attrs)
        _adv.FreeSid(psid)


def isolated_args(args):
    """The same command for the isolated run: the AX Branch Python is swapped for its private runtime copy; a program
    inside the run folder (a built .exe) runs as is; any other interpreter is refused (it is not inside the boundary)."""
    first = Path(str(args[0]))
    try:
        source = python_source()
    except IsolationUnavailable:
        source = None
    if source is not None and first.name.lower() in ('python.exe', 'python', 'py.exe') and (
            first.resolve().parent == source.resolve() or first.resolve() == Path(sys.executable).resolve()):
        return [str(python_for()), *map(str, args[1:])]
    if first.is_absolute() and _under_temp(first):
        return list(map(str, args))
    raise IsolationUnavailable(f'{first} is not available inside the isolated runtime (only the AX Branch Python '
                               'and programs inside the run folder are)')


def _under_temp(path):
    import tempfile
    temp = Path(tempfile.gettempdir()).resolve()
    return Path(path).resolve() == temp or temp in Path(path).resolve().parents


def check_grants(manifest):
    """Grants go only to folders AX Branch created for this run under the temp directory: never the Owner's
    workspace, profile, the Python installation or system locations."""
    if type(manifest.max_processes) is not int or not 1 <= manifest.max_processes <= 8:
        raise IsolationUnavailable('isolated process limit must be an integer between 1 and 8')
    bad = [d for d in manifest.reads + manifest.writes if not _under_temp(d) or Path(d).resolve() == Path(
        __import__('tempfile').gettempdir()).resolve()]
    if bad:
        raise IsolationUnavailable(f'refusing to grant isolated access outside run folders: {bad}')


def python_for(manifest_root=None):
    """The interpreter isolated Python runs use."""
    return runtime_dir(manifest_root) / 'python.exe'


def sha256_dir(path):
    h = hashlib.sha256()
    for f in sorted(Path(path).rglob('*')):
        if f.is_file():
            h.update(f.relative_to(path).as_posix().encode() + b'\0' + f.read_bytes())
    return h.hexdigest()
