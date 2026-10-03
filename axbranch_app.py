"""Desktop entry point (PyInstaller). Opens the Owner window.

    AXBranch.exe                    open the window
    AXBranch.exe --goal "..."       open it with the goal filled in and submitted
    AXBranch.exe --resume <id>      open it and continue/resume that project
"""
import sys

from axbranch.gui import main

if __name__ == '__main__':
    args = sys.argv[1:]

    def opt(name):
        return args[args.index(name) + 1] if name in args[:-1] else None
    main(goal=opt('--goal'), resume=opt('--resume'))
