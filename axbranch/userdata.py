"""Owner data of a running result, kept apart from the verified program.

Data contract (explicit, deliberately narrow):
- only files under the program's ./data/ folder are Owner data;
- formats: .json (must parse), .csv/.txt (must be UTF-8 text), .sqlite/.sqlite3/.db (SQLite: copied with the SQLite
  backup API, never as raw bytes of a live file, then integrity_check);
- never data: executables, code, scripts, libraries, shortcuts, links/junctions, and anything that looks like a
  credential or key; limits of 200 files and 50 MB per snapshot.

Snapshots live per project in projects/<id>/userdata/snapshots/<seq>/ with a manifest (code version, data version,
file hashes). A snapshot is built in a staging folder, verified, then renamed into place, and the current.json pointer
is replaced atomically, so a failed or interrupted save never replaces the last good data. Restore copies only
contract files into the new run's ./data/ after checking their hashes; the verified artifact is never written.

Guarantee: after an abnormal end the Owner keeps the last successful snapshot: at most the changes since the previous
save (periodic saves run every SAVE_INTERVAL seconds while the result is open). A plain file caught mid-write fails
validation and the previous snapshot stays current. Other databases or app formats are NOT supported."""
import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path

DATA_DIR = 'data'
FORMATS = {'.json': 'json', '.csv': 'text', '.txt': 'text', '.sqlite': 'sqlite', '.sqlite3': 'sqlite', '.db': 'sqlite'}
SECRET_HINTS = ('secret', 'token', 'credential', 'password', 'passwd', 'apikey', 'api_key', 'private', '.env', 'id_rsa')
MAX_FILES, MAX_BYTES = 200, 50 * 1024 * 1024
KEEP = 5
SAVE_INTERVAL = 60
if os.environ.get('AXB_DEV') == '1' and os.environ.get('AXB_SAVE_INTERVAL', '').isdigit():
    SAVE_INTERVAL = max(1, int(os.environ['AXB_SAVE_INTERVAL']))     # test harnesses only (AXB_DEV)


class SaveFailed(Exception):
    """The snapshot was not written; the previous good snapshot is still current."""


def root(project_dir):
    return Path(project_dir) / 'userdata'


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect(run_dir, formats=None):
    """(files [(relative path, kind)], skipped [reasons]) of the data contract in a run folder. formats: the
    project's declared subset of FORMATS (the runner never widens it)."""
    allowed = {f: k for f, k in FORMATS.items() if formats is None or f in formats}
    base = Path(run_dir) / DATA_DIR
    files, skipped = [], []
    if not base.is_dir() or base.is_symlink():
        return files, skipped
    for folder, dirs, names in os.walk(base, followlinks=False):
        for d in list(dirs):
            p = Path(folder) / d
            if p.is_symlink() or getattr(p.lstat(), 'st_file_attributes', 0) & 0x400:
                dirs.remove(d)
                skipped.append(f'{p.relative_to(run_dir).as_posix()}: link or junction')
        for name in names:
            p = Path(folder) / name
            rel = p.relative_to(run_dir).as_posix()
            kind = allowed.get(p.suffix.lower())
            if p.is_symlink() or getattr(p.lstat(), 'st_file_attributes', 0) & 0x400:
                skipped.append(f'{rel}: link')
            elif name.lower().endswith(('-wal', '-shm', '-journal')):
                continue                        # SQLite side files: the backup API reads them consistently
            elif any(h in name.lower() for h in SECRET_HINTS):
                skipped.append(f'{rel}: looks like a credential; never saved')
            elif kind is None:
                skipped.append(f'{rel}: format not in the data contract')
            else:
                files.append((rel, kind))
    return sorted(files), skipped


def _copy_checked(src, dest, kind):
    """Copy one contract file into staging, consistently for its format; raise SaveFailed when it is not valid."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if kind == 'sqlite':
        try:
            source = sqlite3.connect(f'{Path(src).resolve().as_uri()}?mode=ro', uri=True, timeout=5)
            target = sqlite3.connect(dest)
            with target:
                source.backup(target)
            ok = target.execute('PRAGMA integrity_check').fetchone()[0]
            source.close()
            target.close()
        except sqlite3.Error as e:
            raise SaveFailed(f'{src.name}: SQLite backup failed ({e})') from e
        if ok != 'ok':
            raise SaveFailed(f'{src.name}: SQLite integrity check failed ({ok})')
        return
    data = src.read_bytes()
    try:
        text = data.decode('utf-8-sig')
        if kind == 'json':
            json.loads(text)
    except (UnicodeDecodeError, ValueError) as e:
        raise SaveFailed(f'{src.name}: not valid {kind} (maybe caught mid-write): {e}'[:300]) from e
    dest.write_bytes(data)


def current(project_dir):
    """Manifest of the last good snapshot, or None. A pointer to a damaged snapshot falls back to the newest intact
    one (its hashes are checked)."""
    base = root(project_dir)
    candidates = []
    try:
        pointer = json.loads((base / 'current.json').read_text(encoding='utf-8'))
        candidates.append(pointer.get('snapshot'))
    except (OSError, ValueError):
        pass
    snaps = sorted((base / 'snapshots').glob('*')) if (base / 'snapshots').is_dir() else []
    candidates += [s.name for s in reversed(snaps)]
    for name in [c for c in dict.fromkeys(candidates) if c]:
        manifest = _intact(base / 'snapshots' / name)
        if manifest:
            return manifest
    return None


def _intact(folder):
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    for f in manifest.get('files', []):
        path = folder / 'files' / f['path']
        if not path.is_file() or _sha(path) != f['sha256']:
            return None
    manifest['folder'] = str(folder)
    return manifest


def snapshot(project_dir, run_dir, code_version, reason, only_if_changed=False, contract=None):
    """Save the run's contract data as a new snapshot. Returns its manifest, or None when there is nothing to save
    (no ./data folder, or unchanged with only_if_changed). Raises SaveFailed (previous snapshot untouched)."""
    files, skipped = collect(run_dir, (contract or {}).get('formats'))
    if not (Path(run_dir) / DATA_DIR).is_dir():
        return None
    if len(files) > MAX_FILES:
        raise SaveFailed(f'{len(files)} data files exceed the limit of {MAX_FILES}')
    total = sum((Path(run_dir) / rel).stat().st_size for rel, _ in files)
    if total > MAX_BYTES:
        raise SaveFailed(f'data is {total:,} bytes, over the {MAX_BYTES:,} byte limit')
    base = root(project_dir)
    (base / 'snapshots').mkdir(parents=True, exist_ok=True)
    staging = base / f'.staging-{uuid.uuid4().hex[:10]}'
    try:
        for rel, kind in files:
            _copy_checked(Path(run_dir) / rel, staging / 'files' / rel, kind)
        entries = [{'path': rel, 'kind': kind, 'sha256': _sha(staging / 'files' / rel),
                    'bytes': (staging / 'files' / rel).stat().st_size} for rel, kind in files]
        last = current(project_dir)
        if only_if_changed and last and [(e['path'], e['sha256']) for e in last['files']] == \
                [(e['path'], e['sha256']) for e in entries] and last.get('code_version') == code_version:
            shutil.rmtree(staging, ignore_errors=True)
            return None
        seq = 1 + max([int(p.name) for p in (base / 'snapshots').glob('*') if p.name.isdigit()] or [0])
        manifest = {'snapshot': f'{seq:06d}', 'data_version': seq, 'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'saved_epoch': time.time(), 'reason': reason, 'code_version': code_version, 'files': entries,
                    'skipped': skipped, 'previous': last and last['snapshot'],
                    'contract': {'dir': DATA_DIR, 'formats': sorted((contract or {}).get('formats') or FORMATS)},
                    'data_schema': (contract or {}).get('schema_version')}
        (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
        final = base / 'snapshots' / manifest['snapshot']
        os.replace(staging, final)
        tmp = base / f'.current-{uuid.uuid4().hex[:8]}.json'
        tmp.write_text(json.dumps({'snapshot': manifest['snapshot'], 'saved_at': manifest['saved_at']}), encoding='utf-8')
        os.replace(tmp, base / 'current.json')
    except SaveFailed:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except OSError as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise SaveFailed(f'could not write the snapshot: {e}') from e
    _prune(base)
    manifest['folder'] = str(final)
    return manifest


def _prune(base):
    """Keep the newest KEEP snapshots AND the newest snapshot of every code version, so data saved with an older
    version (e.g. before an incompatible revision) is never pruned away by saves of a newer one."""
    snaps = sorted(p for p in (base / 'snapshots').glob('*') if p.name.isdigit())
    newest_per_code = {}
    for s in snaps:
        try:
            code = json.loads((s / 'manifest.json').read_text(encoding='utf-8')).get('code_version', {}).get('sha256')
        except (OSError, ValueError):
            continue
        newest_per_code[code] = s
    keep = set(snaps[-KEEP:]) | set(newest_per_code.values())
    for old in snaps:
        if old not in keep:
            shutil.rmtree(old, ignore_errors=True)


def restore(manifest, run_dir):
    """Copy a snapshot's contract files into the run's ./data/ (hashes checked again). Returns the restored paths."""
    folder = Path(manifest['folder'])
    out = []
    for f in manifest['files']:
        parts = Path(f['path']).parts
        if Path(f['path']).is_absolute() or not parts or parts[0] != DATA_DIR or '..' in parts:
            raise SaveFailed(f"snapshot entry outside the data contract: {f['path']}")
        src = folder / 'files' / f['path']
        if not src.is_file() or _sha(src) != f['sha256']:
            raise SaveFailed(f"snapshot {manifest['snapshot']} file {f['path']} no longer matches its hash")
        dest = Path(run_dir) / f['path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        out.append(f['path'])
    return out
