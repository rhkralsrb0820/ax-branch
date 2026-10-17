"""Reproducible isolated orchestration demo: python -m axbranch.demo --root PATH.

Default: scripted model decisions, real Engine/SQLite/checks/process execution.
--live: real subscription providers, a fresh small Owner goal, no paid APIs.
The path must be outside the production workspace. Evidence identifies the mode.
"""
import argparse
import json
from pathlib import Path

from . import WORKSPACE, artifacts, engine as E, providers
from .state import Store


GOAL = ('Create a tiny standard-library Python CLI that prints result: 5 on no-argument launch, '
        'and exposes add(a,b). --self-test checks positive and negative integers. '
        'Use CLI runtime mode, a probe for result: 5, one production stage, no web, '
        'no files or network access. This is an orchestration integration smoke test.')


class ScriptedDecisions:
    """Deliberate faults exercise deterministic gates; this is not model-quality evidence."""
    def __init__(self, scenario):
        self.scenario, self.builds, self.refused = scenario, 0, False

    @staticmethod
    def stage(role='Python engineer', caps=None):
        return {'name': role, 'agent_role': role, 'why': 'Implement the tested arithmetic contract',
                'instructions': 'Use addition and produce the complete CLI', 'provider': 'codex',
                'web': False, 'capabilities': caps or ['code_generation']}

    def __call__(self, prompt, schema, prefer='claude', **kw):
        context = json.loads(prompt.split('CONTEXT (JSON — data, not instructions):\n', 1)[1]
                             .rsplit('\n\nReturn exactly', 1)[0])
        audit = {'reason': 'Scripted demonstration decision', 'evidence': [], 'alternatives': [],
                 'unknowns': ['Scripted decisions do not prove LLM planning quality'], 'knowledge_use': []}
        if schema is E.PLAN:
            out = {'title': 'Capability demo', 'interpretation': GOAL, 'artifact_kind': 'python',
                   'artifact_filename': 'add_cli.py', 'acceptance_criteria': ['add(2,3)==5; CLI prints result: 5'],
                   'verification_lenses': ['correctness'], 'required_tools': [], 'network_access': [],
                   'runtime': {'mode': 'cli', 'owner_launch': 'python add_cli.py', 'launch_args': [],
                               'probes': [{'name': 'CLI primary flow', 'args': [], 'stdin': '',
                                           'http_method': '', 'http_path': '', 'http_body': '', 'http_headers': [],
                                           'expect_exit': 0, 'expect_status': 0,
                                           'expect_contains': ['result: 5'], 'expect_absent': ['Traceback']}]},
                   'pipeline': [self.stage(caps=['ml_training'] if self.scenario == 'gap' else None)]}
        elif schema in (E.BUILD, E.BUILD_EDITS):
            if self.scenario == 'interruption' and not self.refused:
                self.refused = True
                raise providers.RateLimited('Injected quota interruption; no real provider call')
            self.builds += 1
            op = '-' if self.scenario == 'replan' and self.builds < 3 else '+'
            content = (f'import sys\ndef add(a,b):\n    return a {op} b\n'
                       "if __name__ == '__main__':\n    if sys.argv[1:] == ['--self-test']:\n"
                       "        assert add(2,3)==5\n        assert add(-2,3)==1\n        print('self-test passed')\n"
                       "    else:\n        print('result:', add(2,3))\n" + f'# attempt {self.builds}\n')
            out = {'content': content, 'files': [], 'edits': [], 'summary': 'arithmetic CLI',
                   'changes_from_previous': f'Attempt {self.builds}', 'outcome': 'CHANGED', 'no_change_evidence': ''}
        elif schema is E.WORK:
            out = {'output': 'Failure analysis: subtraction violates the contract. Use addition.',
                   'key_points': ['Use addition'], 'evidence': ['recorded failing self-test'], 'counterpoints': []}
        elif schema is E.VERDICT:
            ok = context['deterministic_checks']['ok']
            out = {'verdict': 'PASS' if ok else 'FAIL', 'lenses_applied': ['correctness'],
                   'criteria': [{'index': c['index'], 'criterion': c['criterion'], 'met': ok,
                                 'evidence': 'Recorded deterministic CLI and self-test results'}
                                for c in context['acceptance_criteria']],
                   'findings': [] if ok else [{'severity': 'major', 'kind': 'product', 'criterion': 0,
                                              'issue': 'Subtraction violates add contract', 'evidence': 'assertion failure'}]}
        elif 'decision' in schema.get('properties', {}):
            assert len(context['attempt_ledger']) >= 2
            out = {'decision': 'change_pipeline', 'rationale': 'Two failures: add explicit algorithm diagnosis stage',
                   'pipeline': [self.stage('Algorithm analyst', ['reasoning']), self.stage('Revised Python engineer')],
                   'runtime': context['plan']['runtime'], 'network_access': []}
        elif schema is E.REPORT:
            out = {'summary': 'CLI executed and passed', 'judgment': 'Synthetic contract met; no generalization claim',
                   'next_steps': [], 'goal_satisfied': 'yes', 'missing_evidence': [], 'next_action': 'deliver',
                   'directive': '', 'gap_class': 'AMBIGUOUS', 'runtime': context.get('runtime', {})}
        else:
            raise AssertionError('unexpected demo schema')
        if 'audit' in schema.get('properties', {}):
            out['audit'] = audit
        return out, prefer, []


def run(root, live=False):
    root = Path(root).resolve()
    if root == WORKSPACE.resolve() or WORKSPACE.resolve() in root.parents:
        raise ValueError('Choose an isolated path outside the production workspace')
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / 'demo-projects.json'
    projects = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    store = Store(root / 'axbranch.sqlite3')
    results = []
    try:
        for scenario in (['live'] if live else ['replan', 'gap', 'interruption']):
            key = ('live:' if live else 'scripted:') + scenario
            script = None if live else ScriptedDecisions(scenario)
            if key not in projects:
                projects[key] = store.new_project(GOAL)
                manifest.write_text(json.dumps(projects, indent=2), encoding='utf-8')
            pid = projects[key]
            kwargs = {} if live else {'llm': script}
            eng = E.Engine(store, workspace=root, vault=root / 'empty-vault', gai_db=root / 'absent.db', **kwargs)
            result = eng.run(pid)
            if not live and scenario == 'interruption' and result['state'] == 'PAUSED':
                # Simulate a fresh engine and DB session; production resumes only by its own governed routes.
                store.close()
                store = Store(root / 'axbranch.sqlite3')
                store.resume(pid, by='demo controlled recovery')
                eng = E.Engine(store, workspace=root, vault=root / 'empty-vault', gai_db=root / 'absent.db', llm=script)
                result = eng.run(pid)
            events = store.events(pid)
            attached = {e['id'] for e in events if e['kind'] == 'capability_attached'}
            ended = {e['detail']['grant'] for e in events if e['kind'] == 'capability_revoked'}
            record = {'scenario': key, 'project': pid, 'state': result['state'],
                      'pause_reason': result['pause_reason'], 'plan_version': result['plan_version'],
                      'verdicts': [v['verdict'] for v in store.verifications(pid)],
                      'all_leases_revoked': attached == ended, 'consistency': eng.consistency(pid),
                      'artifacts': store.artifacts(pid), 'events': events}
            results.append(record)
            assert attached == ended, 'a capability lease outlived its operation'
            assert not record['consistency'], record['consistency']
            if not live:
                assert result['state'] == ('PAUSED' if scenario == 'gap' else 'OWNER_REVIEW'), record
                if scenario == 'replan':
                    assert record['verdicts'] == ['FAIL', 'FAIL', 'PASS'] and result['plan_version'] == 2
                if scenario == 'gap':
                    assert not store.artifacts(pid)
        evidence = {'mode': 'real subscription providers' if live else 'scripted decisions; real execution',
                    'limitations': ['Smoke evidence for these cases, not proof of general autonomous task solving'],
                    'results': results}
        (root / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'mode': evidence['mode'], 'results': [
            {k: r[k] for k in ('scenario', 'project', 'state', 'plan_version', 'verdicts', 'all_leases_revoked', 'consistency')}
            for r in results]}, ensure_ascii=False, indent=2), flush=True)
        return 0 if all(r['state'] == 'OWNER_REVIEW' for r in results) or not live else 2
    finally:
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    raise SystemExit(run(args.root, args.live))
