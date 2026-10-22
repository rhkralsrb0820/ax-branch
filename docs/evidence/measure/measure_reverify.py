"""Fixed small task for cost/quality comparison: one verification and one same-artifact re-verification of a
fixed cited report. CEO/producer are scripted (identical input every run); only the Verification agent is a real
provider. Separate scratch workspace; never the validation or production workspace.
Usage: python measure_reverify.py <tag> [claude|codex]"""
import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(r'C:\Users\HP\Desktop\AX-Branch\ax-branch')
OUT = Path(__file__).resolve().parents[1] / 'outputs' / 'measure'
sys.path.insert(0, str(REPO))
from axbranch import __version__, providers, engine as E   # noqa: E402
from axbranch.state import Store                            # noqa: E402
from tests.test_engine import Script                        # noqa: E402

# Ground truth: claims 1-3 are true on their cited pages; claim 4 is false (PEP 8 prefers spaces).
REPORT = """# Python 표준 도구 메모

1. `json.dumps`는 객체를 JSON 형식의 문자열로 직렬화한다 (https://docs.python.org/3/library/json.html).
2. `csv` 모듈은 CSV 형식의 표 데이터를 읽고 쓰는 클래스를 제공한다 (https://docs.python.org/3/library/csv.html).
3. PEP 8은 모든 줄을 최대 79자로 제한하라고 권한다 (https://peps.python.org/pep-0008/).
4. PEP 8은 들여쓰기에 공백보다 탭을 쓰라고 권한다 (https://peps.python.org/pep-0008/).
"""
FALSE_CLAIM_URL = 'https://peps.python.org/pep-0008/'

tag, verifier = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else 'codex')


class Fixed(Script):
    def __call__(self, prompt, schema, prefer='claude', web=False, cancel=None, **kw):
        if schema is E.VERDICT:                                 # the only real call
            return providers.call(prompt, schema, prefer=verifier, web=web, cancel=cancel, on_tick=kw.get('on_tick'))
        result, used, notes = super().__call__(prompt, schema, prefer, web, cancel, **kw)
        if schema is E.PLAN:
            result.update(artifact_kind='markdown', artifact_filename='notes.md',
                          runtime={'mode': 'none', 'owner_launch': 'read it', 'launch_args': [], 'probes': []})
        return result, used, notes


ws = OUT / tag / 'ws'
shutil.rmtree(OUT / tag, ignore_errors=True)
store = Store(ws / 'axbranch.sqlite3')
eng = E.Engine(store, workspace=ws, vault=ws / 'vault', gai_db=ws / 'none', llm=Fixed([REPORT, REPORT], ['PASS'] * 4))
pid = store.new_project('공개 원문을 인용한 짧은 Python 표준 도구 메모를 작성해 줘. 인용한 주장은 원문으로 확인할 수 있어야 해.')
t0 = time.monotonic()
eng.run(pid, stop_at='REWORK')
artifact = store.artifacts(pid)[-1]
eng._reverify_same(pid, artifact, 'measurement: same artifact re-verification')
eng.run(pid, stop_at='REWORK')
calls = [e['detail'] for e in store.events(pid, {'call'}) if e['detail']['who'] == 'Verification']
vs = store.verifications(pid)


def verdicts(v):
    return [(c['source_url'], c['checked_verdict'], c.get('reused_from')) for c in v['result'].get('claim_checks', [])]


summary = {'tag': tag, 'version': __version__, 'verifier': verifier, 'seconds': round(time.monotonic() - t0),
           'verification_calls': [{k: c.get(k) for k in ('provider', 'seconds', 'prompt_chars', 'tokens')} for c in calls],
           'verifications': [{'id': v['id'], 'verdict': v['verdict'],
                              'false_claim_caught': any(u == FALSE_CLAIM_URL and cv == 'contradicted'
                                                        for u, cv, _ in verdicts(v)),
                              'claims': verdicts(v)} for v in vs]}
(OUT / tag / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=1))
store.close()
