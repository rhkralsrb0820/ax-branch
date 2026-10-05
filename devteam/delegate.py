"""Delegate one bounded AX Branch development task to Codex — no Owner relay.

    python devteam/delegate.py devteam/tasks/<task>.json

The task file is a structured handoff (no conversation history):
  {"id", "goal", "task", "relevant_files", "allowed_files", "contract", "constraints",
   "acceptance_tests": ["python -X utf8 -m unittest tests.test_x", ...], "expected_output"}

Codex runs ONCE in this repository (workspace-write sandbox), then exits. Afterwards this script
checks the result deterministically — no model involved:
  * every changed file is in allowed_files (anything else is reported as a scope violation),
  * the acceptance tests and the full suite pass,
and appends a measured record to devteam/DEV_LOG.jsonl (engine, duration, result, rework).
Nothing is committed: the lead developer reviews the diff and commits.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOG = REPO / 'devteam' / 'DEV_LOG.jsonl'
TIMEOUT = 1800


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True, encoding='utf-8').stdout


def prompt(task, commit):
    return f"""You are a co-developer on the AX Branch repository (Python 3.11+, standard library only).
Work ONLY on this bounded task, then stop. Do not commit; the lead developer reviews and commits.

GOAL: {task['goal']}
TASK: {task['task']}
CURRENT COMMIT: {commit}
RELEVANT FILES (read these first): {', '.join(task['relevant_files'])}
ALLOWED FILES TO MODIFY (nothing else): {', '.join(task['allowed_files'])}
ARCHITECTURAL CONTRACT: {task['contract']}
CONSTRAINTS: {task['constraints']}
ACCEPTANCE TESTS (run them; they must pass): {'; '.join(task['acceptance_tests'])}
Also run the full suite: python -X utf8 -m unittest discover -s tests -t .
Follow AGENTS.md. Match the surrounding code style. Keep the change minimal.

Reply with exactly these sections:
FILES CHANGED / IMPLEMENTATION SUMMARY / TEST RESULTS (paste the final unittest summary lines) /
KNOWN ISSUES / EVIDENCE.
EXPECTED OUTPUT: {task['expected_output']}"""


def run_tests(cmds):
    results = []
    for cmd in cmds + ['python -X utf8 -m unittest discover -s tests -t .']:
        proc = subprocess.run(cmd, shell=True, cwd=REPO, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=1200)
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        results.append({'cmd': cmd, 'ok': proc.returncode == 0, 'tail': tail})
    return results


def main(task_file):
    task = json.loads(Path(task_file).read_text(encoding='utf-8'))
    if git('status', '--porcelain').strip():
        sys.exit('Working tree is not clean: commit or stash first, so Codex changes are attributable.')
    commit = git('rev-parse', '--short', 'HEAD').strip()
    out = REPO / 'devteam' / 'results' / f"{task['id']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    codex = shutil.which('codex')
    started = time.time()
    proc = subprocess.run([codex, 'exec', '-s', 'workspace-write', '-C', str(REPO), '--skip-git-repo-check',
                           '-o', str(out), '-'], input=prompt(task, commit), capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=TIMEOUT)
    seconds = round(time.time() - started)
    changed = sorted(set(git('diff', '--name-only').split() + git('ls-files', '--others', '--exclude-standard').split()))
    changed = [f for f in changed if not f.startswith('devteam/results/')]
    outside = [f for f in changed if f not in task['allowed_files']]
    tests = run_tests(task['acceptance_tests'])
    record = {'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'task': task['id'], 'task_type': task.get('task_type', 'UNKNOWN'),
              'engine': 'codex', 'base_commit': commit, 'seconds': seconds, 'exit_code': proc.returncode,
              'files_changed': changed, 'scope_violations': outside,
              'tests_passed': all(t['ok'] for t in tests), 'tests': tests,
              'result': 'ok' if proc.returncode == 0 and not outside and all(t['ok'] for t in tests) else 'needs_review',
              'rework_required': None}          # filled in by the lead after review
    with LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    print(json.dumps({k: record[k] for k in ('task', 'seconds', 'exit_code', 'files_changed', 'scope_violations',
                                             'tests_passed', 'result')}, ensure_ascii=False, indent=1))
    print('\nCodex report:', out)


if __name__ == '__main__':
    main(sys.argv[1])
