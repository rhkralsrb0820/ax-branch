"""Desktop entry point (PyInstaller). Opens the Owner window.

    AXBranch.exe                    open the window
    AXBranch.exe --goal "..."       open it with the goal filled in and submitted
    AXBranch.exe --resume <id>      open it and continue/resume that project
    AXBranch.exe --open <id>        open it on that project's view (nothing is run or resumed)
    AXBranch.exe result <id>        [결과 실행] / [결과 보기] of that project's verified result
"""
import sys

from axbranch.gui import main

if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] in ('run', 'result', 'department', 'web', 'lifecycle', 'isolation', 'verification',
                           'status', 'check', 'training-env'):     # named CLI operations, not GUI auto-execution
        # A windowed exe shows a modal dialog on an uncaught exception; a hidden worker would wait on it
        # forever. Log the error and exit instead (the supervisor sees the stopped worker).
        try:
            from axbranch.__main__ import main as cli
            code = cli(args)
        except BaseException:
            import traceback
            from axbranch import WORKSPACE
            (WORKSPACE / 'logs').mkdir(parents=True, exist_ok=True)
            with (WORKSPACE / 'logs' / 'worker-errors.log').open('a', encoding='utf-8') as log:
                log.write(f"--- AXBranch.exe {' '.join(args)}\n{traceback.format_exc()}\n")
            code = 1
        sys.exit(code)

    def opt(name):
        return args[args.index(name) + 1] if name in args[:-1] else None
    main(goal=opt('--goal'), resume=opt('--resume'), open_id=opt('--open'))
