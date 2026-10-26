"""Build AX Branch as a Windows program (PyInstaller one-folder, cheongwol's approach).

    python -X utf8 build_exe.py        ->  dist/AXBranch/AXBranch.exe

PyInstaller is a build-only tool; the program itself uses only the standard library.
cheongwol's provider helpers are bundled from ../cheongwol/ceo.
"""
import subprocess
import sys
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHEONGWOL = HERE.parent / 'cheongwol' / 'ceo'

def command(output=None, work=None):
    args = [
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
        '--name', 'AXBranch', '--paths', str(CHEONGWOL), '--hidden-import', 'cheongwol.connectors',
        '--distpath', str(output or HERE / 'dist'), '--workpath', str(work or HERE / 'build'),
        '--specpath', str(work or HERE / 'build')]
    for source, dest in (('axbranch/webui', 'axbranch/webui'), ('departments', 'departments'),
                         ('docs/devroom', 'docs/devroom')):
        args += ['--add-data', f'{HERE / source}{__import__("os").pathsep}{dest}']
    return args + [str(HERE / 'axbranch_app.py')]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--work-dir', type=Path)
    opts = parser.parse_args()
    sys.exit(subprocess.call(command(opts.output_dir, opts.work_dir)))
