"""AX Branch command line.

  python -m axbranch gui                         Owner window
  python -m axbranch new "goal" [--run]          create a project (and run it)
  python -m axbranch run <id>                    continue a project from SQLite (any engine)
  python -m axbranch status [<id>]               projects / one project's handoff
  python -m axbranch check <id>                  SQLite <-> disk consistency (exit 1 if unsafe)
  python -m axbranch resume <id> [--rounds N]    resume a PAUSED project
  python -m axbranch finish <id> [--save|--pause|--discard --confirm] [--satisfaction N]
  python -m axbranch review <id> --works | --problem "..." | --change "..."   Owner verdict; problem/change rebuild
  python -m axbranch upgrade-proposal           draft only, and only if Owner satisfaction >= 90%
"""
import argparse
import json
import sys

from . import __version__
from .engine import open_engine
from .state import Busy


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(prog='axbranch', description=f'AX Branch {__version__}')
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('gui')
    n = sub.add_parser('new'); n.add_argument('goal'); n.add_argument('--run', action='store_true')
    r = sub.add_parser('run'); r.add_argument('id')
    r.add_argument('--stop-at', choices=('STAFFING', 'EXECUTING', 'VERIFYING'),
                   help='end the session when this state is reached (controlled checkpoint)')
    c = sub.add_parser('check'); c.add_argument('id')
    s = sub.add_parser('status'); s.add_argument('id', nargs='?')
    rs = sub.add_parser('resume'); rs.add_argument('id'); rs.add_argument('--rounds', type=int, default=0)
    f = sub.add_parser('finish'); f.add_argument('id')
    g = f.add_mutually_exclusive_group()
    for choice in ('save', 'pause', 'discard'):
        g.add_argument('--' + choice, dest='choice', action='store_const', const=choice)
    f.add_argument('--confirm', action='store_true'); f.add_argument('--satisfaction', type=int)
    sub.add_parser('upgrade-proposal')
    rv = sub.add_parser('review'); rv.add_argument('id')
    gv = rv.add_mutually_exclusive_group(required=True)
    gv.add_argument('--works', action='store_true'); gv.add_argument('--problem'); gv.add_argument('--change')
    rv.add_argument('--no-run', action='store_true', help='record the feedback only; rebuild later with run')
    a = ap.parse_args(argv)
    try:
        return _dispatch(a)
    except Busy as e:
        print(f'AX Branch: {e}', file=sys.stderr)
        return 2


def _dispatch(a):

    if a.cmd in (None, 'gui'):
        from .gui import main as gui
        return gui()
    engine = open_engine(log=lambda m: print('  ·', m, flush=True))
    store = engine.store
    if a.cmd == 'new':
        pid = store.new_project(a.goal)
        print(pid)
        if a.run:
            _show(engine.run(pid))
    elif a.cmd == 'run':
        _show(engine.run(a.id, stop_at=a.stop_at))
    elif a.cmd == 'check':
        problems = engine.consistency(a.id)
        print('consistent' if not problems else '\n'.join(problems))
        return 1 if problems else 0
    elif a.cmd == 'status':
        if a.id:
            print(json.dumps(store.handoff(a.id), ensure_ascii=False, indent=2))
        else:
            from .engine import activity
            for p in store.projects():
                print(f"{p['id']}  {p['state']:<25} v{p['iteration']}  {p['goal'][:70]}")
                a = activity(engine.workspace, p['id'])
                if a:
                    print(f"    ▶ {a['agent']} on {a.get('provider')} (CLI pid {a.get('pid', '-')}): "
                          f"{a.get('elapsed', 0)}s elapsed, {a.get('output_bytes', 0)} B output, last output {a.get('idle', 0)}s ago")
    elif a.cmd == 'resume':
        store.resume(a.id, a.rounds)
        _show(engine.run(a.id))
    elif a.cmd == 'review':
        verdict, text = ('works', '') if a.works else ('problem', a.problem) if a.problem else ('change', a.change)
        p = engine.owner_review(a.id, verdict, text)
        print(f"[{p['id']}] {p['state']} — Owner feedback recorded ({verdict})")
        if p['state'] == 'REWORK' and not a.no_run:
            _show(engine.run(a.id))
    elif a.cmd == 'upgrade-proposal':
        from . import providers, upgrade
        status, result = upgrade.propose(store, engine.workspace, providers.call)
        if status == 'locked':
            avg = result['average_satisfaction']
            print(f"Paid expansion is locked: average Owner satisfaction "
                  f"{'n/a' if avg is None else f'{avg:.0f}%'} over {len(result['owner_satisfaction'])} closed projects "
                  f"(gate {result['gate']}%). No proposal drafted; nothing purchased.")
        else:
            print(f'Draft written (NOT approved, nothing purchased): {result}')
    elif a.cmd == 'finish':
        p = engine.close(a.id, a.choice, a.confirm, a.satisfaction)
        if p['state'] == 'ARCHIVE_PENDING_APPROVAL':
            print('淸月 AI CEO: 프로젝트 지식을 저장할까요?\n'
                  '  A. --save     SAVE & CLOSE (Obsidian에 정리·검증 후 종료)\n'
                  '  B. --pause    PAUSE (상태 보존, 나중에 재개)\n'
                  '  C. --discard --confirm   CLOSE WITHOUT SAVE (지식 저장 없음, 되돌릴 수 없음)')
        _show(p)


def _show(p):
    print(f"\n[{p['id']}] {p['state']}" + (f" — {p['pause_reason']}" if p.get('pause_reason') else ''))
    if p.get('report') and p['state'] in ('OWNER_REVIEW', 'PENDING_CLOSE'):
        r = p['report']
        print(f"\n淸月 AI CEO 보고\n{r['summary']}\n\n판단: {r['judgment']}\n산출물: {r['artifact']} "
              f"(검증 {r['rounds']}회차 PASS)")
        for step in r['next_steps']:
            print(' -', step)
        if p['state'] == 'OWNER_REVIEW':
            print(f"\n테스트 방법: {r.get('how_to_test') or '-'}\n"
                  f"결과 알려주기: python -m axbranch review {p['id']} --works | --problem \"...\" | --change \"...\"")
    if p.get('archive_note'):
        print('Obsidian:', p['archive_note'])


if __name__ == '__main__':
    sys.exit(main())
