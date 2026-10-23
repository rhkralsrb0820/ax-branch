"""Artifact files on disk: one file (markdown/python) or a bundle of files.

Every artifact is hash-addressed. A single file's sha256 is of its bytes; a bundle's is of
its manifest (sorted relative path + per-file sha256), and each file is checked too. Model
supplied paths are untrusted: only plain relative paths inside the artifact folder are
written; anything else is refused and recorded so verification fails on it.
"""
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path, PurePosixPath

MAX_FILES, MAX_BYTES = 40, 400_000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_relpath(raw):
    """'pkg/mod.py' -> 'pkg/mod.py'; None for absolute, drive, '..', empty or odd names."""
    text = (raw or '').replace('\\', '/').strip()
    p = PurePosixPath(text)
    if not text or p.is_absolute() or ':' in text or any(part in ('', '.', '..') for part in p.parts):
        return None
    if any(not part.replace('.', '').replace('_', '').replace('-', '').isalnum() for part in p.parts):
        return None
    return str(p)


def manifest_digest(files):
    return sha('\n'.join(f"{f['path']}\0{f['sha256']}" for f in sorted(files, key=lambda f: f['path'])).encode('utf-8'))


def write_bundle(folder, files):
    """Write [{'path','content'}] under folder. Returns (manifest, digest)."""
    folder = Path(folder)
    accepted, rejected, total = [], [], 0
    for f in files:
        rel = safe_relpath(f.get('path'))
        data = (f.get('content') or '').encode('utf-8')
        total += len(data)
        if rel is None or rel in {a['path'] for a in accepted}:
            rejected.append(f"unsafe or duplicate path: {str(f.get('path'))[:80]}")
        elif len(accepted) >= MAX_FILES or total > MAX_BYTES:
            rejected.append(f'over limit ({MAX_FILES} files / {MAX_BYTES} bytes): {rel}')
        else:
            target = folder / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)                 # exact bytes; no newline translation
            accepted.append({'path': rel, 'sha256': sha(data), 'bytes': len(data)})
    manifest = {'files': accepted, 'rejected': rejected}
    return manifest, manifest_digest(accepted)


def files_of(artifact):
    """[(relative path, absolute Path, recorded sha256)] for any artifact row."""
    if artifact.get('manifest'):
        root = Path(artifact['path'])
        return [(f['path'], root / f['path'], f['sha256']) for f in json.loads(artifact['manifest'])['files']]
    path = Path(artifact['path'])
    return [(path.name, path, artifact['sha256'])]


def problems(artifact):
    """Disk vs record. [] means every byte is what was built."""
    out = []
    for rel, path, digest in files_of(artifact):
        if not path.is_file():
            out.append(f"v{artifact['iteration']} missing: {rel}")
        elif sha(path.read_bytes()) != digest:
            out.append(f"v{artifact['iteration']} bytes differ from recorded sha256: {rel}")
    if artifact.get('manifest'):
        files = json.loads(artifact['manifest'])['files']
        if manifest_digest(files) != artifact['sha256']:
            out.append(f"v{artifact['iteration']} manifest does not match recorded sha256")
        known = {f['path'] for f in files}
        extra = [p for p in Path(artifact['path']).rglob('*') if p.is_file()
                 and p.relative_to(artifact['path']).as_posix() not in known]
        out += [f"v{artifact['iteration']} unexpected file: {p.relative_to(artifact['path']).as_posix()}" for p in extra]
    return out


def is_empty(artifact):
    """True when the artifact holds no content at all (0.1.9: two empty builds were each sent to verification)."""
    if artifact.get('manifest'):
        return not any(f['bytes'] for f in json.loads(artifact['manifest'])['files'])
    return artifact['sha256'] == sha(b'')


def text_of(artifact, cap=400_000):
    files = files_of(artifact)
    if not artifact.get('manifest'):
        return files[0][1].read_bytes().decode('utf-8')
    parts = [f'=== {rel} ===\n{path.read_bytes().decode("utf-8", errors="replace")}' for rel, path, _ in files]
    return '\n\n'.join(parts)[:cap]


def apply_edits(artifact, edits):
    """Apply exact search/replace edits to an artifact's files. Returns ({relpath: text}, None) or
    (None, reason). Each `find` must occur exactly once in its file at the time it is applied, so an
    edit can never land somewhere unintended; any problem rejects the whole build."""
    files = {rel: path.read_bytes().decode('utf-8') for rel, path, _ in files_of(artifact)}
    only = next(iter(files)) if len(files) == 1 else None
    for i, edit in enumerate(edits, 1):
        rel = only or safe_relpath(edit.get('path'))     # single file: the path is informational
        if rel is None:
            return None, f'edit {i}: unsafe or missing path {edit.get("path")!r}'
        if rel not in files:
            if edit.get('find'):
                return None, f'edit {i}: file {edit.get("path")!r} is not in the current version'
            files[rel] = edit.get('replace') or ''       # empty find on a new path = create the file
            continue
        find, text = edit.get('find') or '', files[rel]
        if not find:
            # Empty find on an existing file: empty replace deletes it (bundle), otherwise replace = the whole new
            # file. A complete rewrite never has to reproduce the old text byte-exactly (P-20261023-2a0e75 v5 put
            # whole-file replacements into find/replace and every one failed to match).
            if edit.get('replace'):
                files[rel] = edit['replace']
            elif len(files) > 1:
                del files[rel]
            else:
                return None, f'edit {i} ({rel}): an empty find and replace would delete the only file'
            continue
        hits = text.count(find) if find else 0
        if hits != 1:
            return None, (f'edit {i} ({rel}): the text to replace occurs {hits} times in the current version; '
                          'it must occur exactly once (copy a longer, exact snippet)')
        files[rel] = text.replace(find, edit.get('replace') or '', 1)
    return files, None


def materialize(artifact, folder):
    """Copy the artifact's files into folder (for running checks away from the original)."""
    for rel, path, _ in files_of(artifact):
        target = Path(folder) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


# ---- Owner input files: read-only copies in projects/<id>/inputs, given to checks as ./inputs/<name>
MAX_INPUTS, MAX_INPUT_BYTES = 10, 20 * 2**20


def validate_inputs(paths, existing=(), existing_bytes=0):
    """Raise ValueError naming the first problem; nothing is created. Names compare case-insensitively (Windows)."""
    paths = [Path(p) for p in paths]
    if len(paths) + len(existing) > MAX_INPUTS:
        raise ValueError(f'at most {MAX_INPUTS} input files')
    names = [p.name.lower() for p in paths] + [n.lower() for n in existing]
    if len(set(names)) != len(names):
        raise ValueError('input file names must be unique (case-insensitive)')
    total = existing_bytes
    for p in paths:
        if not p.is_file() or p.is_symlink() or safe_relpath(p.name) != p.name:
            raise ValueError(f'not a readable regular file: {p}')
        total += p.stat().st_size
    if total > MAX_INPUT_BYTES:
        raise ValueError(f'input files exceed {MAX_INPUT_BYTES // 2**20} MB in total')
    return paths


def attach_inputs(project_dir, paths, known=()):
    """Copy the Owner's files into project_dir/inputs (read-only; originals are only read). known = the records
    already attached (from SQLite, the only source of truth). The byte budget is enforced on the bytes actually read.
    Returns [{name, size, sha256, source}] or raises ValueError (then nothing new is left behind)."""
    folder = Path(project_dir) / 'inputs'
    present = [f.name for f in folder.iterdir()] if folder.is_dir() else []
    names = list({n.lower(): n for n in [r['name'] for r in known] + present}.values())
    paths = validate_inputs(paths, names, sum(r['size'] for r in known))
    budget = MAX_INPUT_BYTES - sum(r['size'] for r in known)
    loaded = []
    for p in paths:
        with open(p, 'rb') as f:
            data = f.read(budget + 1)
        budget -= len(data)
        if budget < 0:
            raise ValueError(f'input files exceed {MAX_INPUT_BYTES // 2**20} MB in total')
        loaded.append((p, data))
    folder.mkdir(parents=True, exist_ok=True)
    records, written = [], []
    try:
        for p, data in loaded:
            target = folder / p.name
            target.write_bytes(data)
            written.append(target)
            os.chmod(target, stat.S_IREAD)
            records.append({'name': p.name, 'size': len(data), 'sha256': sha(data), 'source': str(p)})
    except OSError:
        for f in written:
            os.chmod(f, stat.S_IWRITE | stat.S_IREAD)
            f.unlink(missing_ok=True)
        raise
    return records


def inputs_folder(path):
    """projects/<id>/inputs for a path inside projects/<id>/artifacts/..., else None."""
    path = Path(path)
    for parent in path.parents:
        if parent.name == 'artifacts':
            folder = parent.parent / 'inputs'
            return folder if folder.is_dir() else None
    return None


def copy_inputs(path, dest, records):
    """Writable copies of the project's RECORDED inputs (records from SQLite) into dest/inputs: the program reads
    ./inputs/<name>. A file whose bytes no longer match its record is refused; unrecorded files are never copied."""
    folder = inputs_folder(path)
    if not records:
        return
    if folder is None:
        raise ValueError('input files are recorded but the inputs folder is missing')
    (Path(dest) / 'inputs').mkdir(parents=True, exist_ok=True)
    for r in records:
        data = (folder / r['name']).read_bytes() if (folder / r['name']).is_file() else b''
        if sha(data) != r['sha256']:
            raise ValueError(f"input file {r['name']} changed after it was attached")
        (Path(dest) / 'inputs' / r['name']).write_bytes(data)
