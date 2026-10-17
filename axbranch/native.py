"""Native Windows distribution: a one-file .exe built from the verified Python source by the engine.

The tool is acquired into the PROJECT (projects/<id>/tools/pyinstaller-<version>, an isolated venv with a pinned
PyInstaller from PyPI): no system change, no global install, no admin rights. The build runs on a copy of the version
and writes projects/<id>/dist/v<N>/<name>.exe; the version folder itself stays immutable. The harness then runs that
.exe, never `python <entry>`, as the Owner will."""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from . import artifacts, sandbox

PYINSTALLER = '6.22.3'           # pinned: the version proven on this PC; a change is a reviewed decision
TOOL_TIMEOUT, BUILD_TIMEOUT = 900, 900


class ToolUnavailable(Exception):
    """The build tool could not be acquired (e.g. offline): an environment gap, never a product failure."""


def _run(args, cwd, timeout):
    """Contained like generated code (clean environment: no session credentials; a Job Object kills the whole tree
    on finish or timeout), without the process/memory caps PyInstaller's analysis subprocesses exceed.
    Returns (exit code or None on timeout, output tail)."""
    proc = sandbox.start([str(a) for a in args], cwd, caps=False)
    try:
        code = proc.wait(timeout)
        return code, proc.output()[-3000:]
    finally:
        proc.stop()
        proc.cleanup()


def ensure_tool(project_dir, python=None):
    """The project's isolated PyInstaller (created once). Returns a record of what was acquired."""
    venv = Path(project_dir) / 'tools' / f'pyinstaller-{PYINSTALLER}'
    exe = venv / ('Scripts/pyinstaller.exe' if os.name == 'nt' else 'bin/pyinstaller')
    done = venv / 'AXB_INSTALLED'          # written last: an interrupted install is never mistaken for a tool
    if exe.is_file() and done.is_file():
        return {'tool': 'pyinstaller', 'version': PYINSTALLER, 'path': str(exe), 'acquired': False}
    shutil.rmtree(venv, ignore_errors=True)
    python = python or sys.executable
    started = time.monotonic()
    try:
        code, out = _run([python, '-m', 'venv', str(venv)], str(project_dir), TOOL_TIMEOUT)
        if code != 0:
            raise ToolUnavailable(f'venv creation failed (exit {code}): {out[-400:]}')
        vpy = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        # --isolated: no user/env pip configuration; one explicit index; no shared cache outside the project.
        code, out = _run([vpy, '-m', 'pip', 'install', '--isolated', '--disable-pip-version-check', '--no-input',
                          '--no-cache-dir', '--index-url', 'https://pypi.org/simple', f'pyinstaller=={PYINSTALLER}'],
                         str(project_dir), TOOL_TIMEOUT)
        if code != 0 or not exe.is_file():
            raise ToolUnavailable(f'pip install pyinstaller=={PYINSTALLER} failed (exit {code}): {out[-600:]}')
        done.write_text(PYINSTALLER, encoding='utf-8')
    except BaseException as e:
        shutil.rmtree(venv, ignore_errors=True)      # never leave a half tool that looks installed
        if isinstance(e, ToolUnavailable):
            raise
        raise ToolUnavailable(f'tool acquisition failed: {type(e).__name__}: {e}') from None
    return {'tool': 'pyinstaller', 'version': PYINSTALLER, 'path': str(exe), 'acquired': True,
            'seconds': round(time.monotonic() - started), 'source': 'PyPI (pip)'}


def build(tool_exe, artifact, entry, name, windowed, out_dir):
    """Build <out_dir>/<name>.exe from a copy of the artifact. Returns {ok, exe, sha256, output, seconds}."""
    started = time.monotonic()
    out_dir = Path(out_dir)
    with tempfile.TemporaryDirectory(prefix='axb-build-', ignore_cleanup_errors=True) as tmp:
        src = Path(tmp) / 'src'
        src.mkdir()
        artifacts.materialize(artifact, src)
        command = [str(x) for x in tool_exe] if isinstance(tool_exe, (list, tuple)) else [str(tool_exe)]
        args = [*command, '--onefile', '--noconfirm', '--clean', '--name', name,
                '--distpath', str(Path(tmp) / 'dist'), '--workpath', str(Path(tmp) / 'work'),
                '--specpath', str(Path(tmp) / 'spec'), *(['--windowed'] if windowed else []), str(src / entry)]
        code, out = _run(args, str(src), BUILD_TIMEOUT)
        if code is None:
            return {'ok': False, 'output': f'build timed out ({BUILD_TIMEOUT}s); process tree killed', 'seconds': BUILD_TIMEOUT}
        built = Path(tmp) / 'dist' / (name + ('.exe' if os.name == 'nt' else ''))
        if code != 0 or not built.is_file():
            return {'ok': False, 'output': out, 'seconds': round(time.monotonic() - started)}
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / built.name
        shutil.copyfile(built, target)
    data = target.read_bytes()
    return {'ok': True, 'exe': str(target), 'sha256': artifacts.sha(data), 'size': len(data), 'output': out[-800:],
            'seconds': round(time.monotonic() - started)}
