"""Artifact files on disk: one file (markdown/python) or a bundle of files.

Every artifact is hash-addressed. A single file's sha256 is of its bytes; a bundle's is of
its manifest (sorted relative path + per-file sha256), and each file is checked too. Model
supplied paths are untrusted: only plain relative paths inside the artifact folder are
written; anything else is refused and recorded so verification fails on it.
"""
import hashlib
import json
import shutil
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


def text_of(artifact, cap=120_000):
    files = files_of(artifact)
    if not artifact.get('manifest'):
        return files[0][1].read_bytes().decode('utf-8')
    parts = [f'=== {rel} ===\n{path.read_bytes().decode("utf-8", errors="replace")}' for rel, path, _ in files]
    return '\n\n'.join(parts)[:cap]


def materialize(artifact, folder):
    """Copy the artifact's files into folder (for running checks away from the original)."""
    for rel, path, _ in files_of(artifact):
        target = Path(folder) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
