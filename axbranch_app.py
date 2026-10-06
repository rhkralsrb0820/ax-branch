"""Desktop entry point (PyInstaller). Opens the Owner window.

    AXBranch.exe                    open the window
    AXBranch.exe --goal "..."       open it with the goal filled in and submitted
    AXBranch.exe --resume <id>      open it and continue/resume that project
"""
import sys

from axbranch.gui import main

if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == 'run':                 # background project worker started by the window
        from axbranch.__main__ import main as cli
        sys.exit(cli(args))

    def opt(name):
        return args[args.index(name) + 1] if name in args[:-1] else None
    main(goal=opt('--goal'), resume=opt('--resume'))
