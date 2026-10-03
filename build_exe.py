"""Build AX Branch as a Windows program (PyInstaller one-folder, cheongwol's approach).

    python -X utf8 build_exe.py        ->  dist/AXBranch/AXBranch.exe

PyInstaller is a build-only tool; the program itself uses only the standard library.
cheongwol's provider helpers are bundled from ../cheongwol/ceo.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHEONGWOL = HERE.parent / 'cheongwol' / 'ceo'

if __name__ == '__main__':
    sys.exit(subprocess.call([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
        '--name', 'AXBranch', '--paths', str(CHEONGWOL), '--hidden-import', 'cheongwol.connectors',
        '--distpath', str(HERE / 'dist'), '--workpath', str(HERE / 'build'), '--specpath', str(HERE / 'build'),
        str(HERE / 'axbranch_app.py')]))
