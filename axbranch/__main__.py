"""AX Branch command line.

  python -m axbranch gui                         Owner window
  python -m axbranch new "goal" [--run]          create a project (and run it)
  python -m axbranch run <id>                    continue a project from SQLite (any engine)
  python -m axbranch status [<id>]               projects / one project's handoff
  python -m axbranch check <id>                  SQLite <-> disk consistency (exit 1 if unsafe)
  python -m axbranch resume <id> [--rounds N]    resume a PAUSED project
  python -m axbranch finish <id> [--save|--pause|--discard --confirm] [--satisfaction N]
  python -m axbranch review <id> [--works | --broken "what happened"] [--request "what you want"] [--finish]
                                                 Owner review: does it work? / what next (plain language)
  python -m axbranch approve <id> --network yes|no   decide pending external connections
  python -m axbranch replan <id> --reason "..."  recovery: CEO strategy review for a stuck/misdirected project
  python -m axbranch supervise [--watch]          automatic stall detection and bounded recovery
  python -m axbranch effort [<id>]                Owner Effort KPI (measured / estimated / unknown)
  python -m axbranch upgrade-proposal           draft only, and only if Owner satisfaction >= 90%
"""
import argparse
import os
import json
import sys
import time

from . import __version__
from .engine import open_engine
from .state import ACTIVE, Busy


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
    ef = sub.add_parser('effort'); ef.add_argument('id', nargs='?')
    sv = sub.add_parser('supervise'); sv.add_argument('--watch', action='store_true')
    sub.add_parser('library', help='completed artifacts by type, with their current version and lineage')
    dv = sub.add_parser('develop', help='Owner: continue a completed artifact with a new goal (new project, new version)')
    dv.add_argument('id', help='the project of the artifact version to develop'); dv.add_argument('goal')
    dv.add_argument('--run', action='store_true')
    au = sub.add_parser('autostart', help='Owner: supervision while AX Branch is closed (Windows Task Scheduler)')
    au.add_argument('action', choices=('on', 'off', 'status'))
    rv = sub.add_parser('review'); rv.add_argument('id')
    gv = rv.add_mutually_exclusive_group()
    gv.add_argument('--works', action='store_true', help='it runs correctly')
    gv.add_argument('--broken', '--problem', dest='broken', metavar='TEXT', help='it does not work: what happened')
    rv.add_argument('--request', '--change', dest='request', metavar='TEXT',
                    help='anything you want changed, added or improved, in your own words')
    rv.add_argument('--finish', action='store_true', help='done: move toward closing the project')
    rv.add_argument('--no-run', action='store_true', help='record the feedback only; rebuild later with run')
    rp = sub.add_parser('replan'); rp.add_argument('id'); rp.add_argument('--reason', required=True)
    ru = sub.add_parser('ruling', help='Owner: what evidence satisfies an approved criterion in automated verification')
    ru.add_argument('id'); ru.add_argument('criterion', type=int); ru.add_argument('text')
    ap_ = sub.add_parser('approve'); ap_.add_argument('id'); ap_.add_argument('--network', choices=('yes', 'no'), required=True)
    ap_.add_argument('--note', default='', help='your guidance for the CEO when declining')
    a = ap.parse_args(argv)
    try:
        return _dispatch(a)
    except Busy as e:
        print(f'AX Branch: {e}', file=sys.stderr)
        return 2


def _dispatch(a):
    if (a.cmd in ('run', 'resume', 'review', 'approve', 'replan', 'finish') and getattr(a, 'id', None)
            and os.environ.get('AXB_SUPERVISED') != '1'):      # a worker the app/supervisor started: not the Owner
        from .supervisor import channel
        from .state import Store
        from . import DB_PATH
        s = Store(DB_PATH)
        try:
            s.event(a.id, 'owner_action', action=a.cmd, channel=channel())
        finally:
            s.close()

    if a.cmd in (None, 'gui'):
        from .gui import main as gui
        return gui()
    engine = open_engine(log=lambda m: print('  ·', m, flush=True))
    store = engine.store
    if a.cmd == 'new':
        from .supervisor import channel
        pid = store.new_project(a.goal)
        store.event(pid, 'owner_action', action='new', channel=channel())
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
            from .engine import liveness
            for p in store.projects():
                label, detail = liveness(engine.workspace, store, p['id'])
                print(f"{p['id']}  {p['state']:<25} v{p['iteration']}  {p['goal'][:60]}")
                print(f"    [{label}] {detail}")
    elif a.cmd == 'resume':
        store.resume(a.id, a.rounds)
        _show(engine.run(a.id))
    elif a.cmd == 'review':
        works = True if a.works else False if a.broken else None
        p = engine.owner_review(a.id, works, a.broken or a.request or '', a.finish)
        print(f"[{p['id']}] {p['state']} — Owner review recorded")
        if p['state'] in ACTIVE and not a.no_run:          # incl. VERIFYING (re-verify after HARNESS_BLOCKED)
            _show(engine.run(a.id))
    elif a.cmd == 'replan':
        p = engine.replan(a.id, a.reason)
        print(f"[{p['id']}] {p['state']} plan v{p['plan_version']} — CEO strategy reviewed; continue with: "
              f"python -m axbranch run {p['id']}")
    elif a.cmd == 'ruling':
        engine.add_ruling(a.id, a.criterion, a.text)
        print(f'[{a.id}] Owner ruling recorded for approved criterion {a.criterion}')
    elif a.cmd == 'approve':
        p = engine.decide_network(a.id, a.network == 'yes', a.note)
        print(f"[{p['id']}] external connection(s) {'approved' if a.network == 'yes' else 'declined'}; "
              f"continue with: python -m axbranch resume {p['id']}")
    elif a.cmd == 'library':
        from . import library
        for e in library.entries(store):
            print(f"[{e['type']}] {e['title']}  v{e['version']}  ({e['verification']})  <- {e['project']}")
            for v in e['versions']:
                print(f"    v{v['version']} <- {v['project']}  {v['goal'][:60]}")
    elif a.cmd == 'develop':
        from .supervisor import channel
        pid = engine.develop(a.id, a.goal)
        store.event(pid, 'owner_action', action='develop', channel=channel())
        print(pid)
        if a.run:
            _show(engine.run(pid))
    elif a.cmd == 'autostart':
        from . import autostart
        if a.action == 'on':
            autostart.register()
        elif a.action == 'off':
            print(autostart.unregister())
        if a.action in ('on', 'status'):
            print(autostart.status())
    elif a.cmd == 'supervise':
        from . import autostart, supervisor
        while True:
            done = []
            for pid in supervisor.candidates(store):
                rec = supervisor.status(engine.workspace, store, pid)
                action = supervisor.supervise(engine, pid,
                                              launch=lambda p: supervisor.launch_detached(engine.workspace, p),
                                              stop=lambda p, w: supervisor.stop_worker(w, pid=p))
                print(f"{pid} [{rec['status']}] {rec['reason'][:120]}" + (f' -> {action}' if action else ''))
                done.append(f"{pid}:{rec['status']}" + (f'->{action}' if action else ''))
            sent = autostart.notify_waiting(engine)
            autostart.log_pass(engine.workspace, f"supervised [{', '.join(done)}] notified {sent} {autostart.memory_line()}")
            if not a.watch or not any(supervisor.status(engine.workspace, store, p)['status'] in
                                      ('ACTIVE', 'RECOVERING', 'STALLED', 'FAILED', 'WAITING_FOR_PROVIDER')
                                      for p in supervisor.candidates(store)):
                break
            time.sleep(30)
    elif a.cmd == 'effort':
        from .metrics import effort
        print(json.dumps(effort(store, a.id), ensure_ascii=False, indent=2))
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
                  f"1) 작동하나요?  python -m axbranch review {p['id']} --works   (안 되면 --broken \"무슨 일이 있었는지\")\n"
                  f"2) 더 원하는 것이 있나요?  --request \"자유롭게\"   /  마무리하려면 --finish")
    if p.get('archive_note'):
        print('Obsidian:', p['archive_note'])


if __name__ == '__main__':
    sys.exit(main())
