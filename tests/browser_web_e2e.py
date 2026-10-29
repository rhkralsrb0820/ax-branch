"""Real E2E through the web page of a PACKAGED build (not unittest discovery: real models, minutes, Chrome).

An isolated root (AXB_ROOT) gets a fresh workspace; the packaged `AXBranch.exe web --test-mode` serves it; headless
Chrome with its OWN temporary profile (the Owner's Chrome is never used) runs selftest.js?e2e: goal + attached file +
two dragged departments -> submit -> the real worker and models run -> open the verified result -> save feedback.
The harness then reads the isolated database (calls, tokens, contract, acceptance, feedback) and writes a JSON record.

    python -X utf8 tests/browser_web_e2e.py <AXBranch.exe> <fixture.csv> <out.json> [--text-rework]

--text-rework sends a textual request on the newly finished project, then checks its persisted REWORK,
revised PASS and opening a result containing the requested marker. No existing workspace is resumed."""
import json
import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

CHROME = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
GOAL = ('첨부한 검증 이력 CSV에서 실패 원인(attributed_cause)별 건수와 해당 행 번호를 근거로 정리하고, 그 근거로 운영 개선 '
        '메모를 마크다운 문서 한 개로 만들어 줘. 개선 항목은 2개 이내, 항목마다 근거 수치. UNKNOWN 원인은 단정하지 마. '
        '외부 서비스와 유료 API는 사용하지 마.')


GOAL_WEBAPP = ('(합성 자료, 시험 입력) 작은 매장용 재고 확인 웹앱을 만들어 줘. 첨부한 inventory.csv를 읽어 품목·수량을 표로 '
               '보여 주고, 수량이 5개 이하인 품목은 "재고 부족"으로 표시해야 한다. Python 표준 라이브러리만 사용, 127.0.0.1에서만 '
               '실행, 외부 연결·설치 없음. 결과물은 실행 가능한 프로그램 하나.')


def _check_web(url, expect):
    """The harness, outside the browser, uses the running result (the page cannot read another origin)."""
    import urllib.request
    try:
        body = urllib.request.urlopen(url, timeout=15).read().decode('utf-8', errors='replace')
        return {'ok': all(e in body for e in expect), 'status': 200, 'contains': {e: e in body for e in expect},
                'body_head': body[:300]}
    except OSError as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'[:200]}


def _refused(url):
    import urllib.request
    try:
        urllib.request.urlopen(url, timeout=5)
        return False
    except OSError:
        return True


def main(exe, fixture, out, port=8767, text_rework=False, webapp=False):
    root = Path(tempfile.mkdtemp(prefix='axb-web-e2e-'))
    (root / 'workspace').mkdir()
    (root / 'obsidian').mkdir()
    env = {**os.environ, 'AXB_ROOT': str(root), 'AXB_TEST_FIXTURE': str(fixture), 'AXB_DEV': '1'}
    server = subprocess.Popen([exe, 'web', '--port', str(port), '--test-mode'], env=env)
    reports_file, profile = root / 'workspace' / 'test-reports.jsonl', root / 'chrome-profile'
    for _ in range(60):
        if (root / 'workspace' / 'web-server.json').exists():
            break
        time.sleep(0.5)
    url = f'http://127.0.0.1:{port}/?selftest=1&e2e=1&goal=' + urllib.parse.quote(GOAL_WEBAPP if webapp else GOAL)
    if text_rework:
        url += '&text-rework=1'
    if webapp:
        url += '&webapp=1'
    used = {}
    chrome = subprocess.Popen([str(CHROME), '--headless=new', f'--user-data-dir={profile}', '--no-first-run',
                               '--no-default-browser-check', '--disable-extensions', '--window-size=1400,1000', url],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started, reports = time.time(), []
    try:
        while time.time() - started < (55 if text_rework else 30) * 60:
            if reports_file.exists():
                reports = [json.loads(line) for line in reports_file.read_text(encoding='utf-8').splitlines() if line.strip()]
                for r in reports:
                    name = r.get('name', '')
                    if name.endswith('web result opened') and r.get('ok') and name not in used:
                        expect = ['재고 부족'] + (['AXB-TEXT-REWORK'] if name.startswith('e2e: revised') else [])
                        used[name] = {'url': r.get('detail'), **_check_web(r.get('detail'), expect)}
                    if name.endswith('stopped from the page') and name not in used:
                        opened = used.get(name.replace('stopped from the page', 'opened'), {})
                        used[name] = {'url_refused_after_stop': bool(opened.get('url')) and _refused(opened['url'])}
                if any(r.get('name') == 'done' for r in reports):
                    break
            time.sleep(2)
    finally:
        subprocess.run(['taskkill', '/PID', str(chrome.pid), '/T', '/F'], capture_output=True)
        subprocess.run([exe, 'web', '--stop'], env=env, capture_output=True, timeout=30)
        time.sleep(2)
        if server.poll() is None:
            server.kill()
    db = sqlite3.connect(root / 'workspace' / 'axbranch.sqlite3')
    db.row_factory = sqlite3.Row
    pid = next((r.get('detail') for r in reports if r.get('name') == 'done'), None)
    record = {'exe': exe, 'exe_sha256': hashlib.sha256(Path(exe).read_bytes()).hexdigest(),
              'started': started, 'seconds': round(time.time() - started), 'project': pid,
              'checks': [r for r in reports if r.get('name') != 'done'], 'isolated_root': str(root),
              'text_rework': text_rework, 'finished': any(r.get('name') == 'done' for r in reports),
              'interventions': [r for r in reports if r.get('ok') and r.get('name') in (
                  'e2e: project created from the page', 'e2e: textual change requested on existing project')]}
    if pid:
        p = db.execute('SELECT state, pause_reason, iteration FROM projects WHERE id=?', (pid,)).fetchone()
        events = [(r['kind'], json.loads(r['detail'])) for r in db.execute(
            'SELECT kind, detail FROM events WHERE project_id=? ORDER BY id', (pid,))]
        calls = [{'who': d['who'], 'provider': d['provider'], 'seconds': d['seconds'], 'tokens': d.get('tokens')}
                 for k, d in events if k == 'call']
        record.update(state=dict(p), calls=calls,
                      call_count=len(calls),
                      failed_calls=[d for k, d in events if k == 'call_failed'],
                      transitions=[d for k, d in events if k == 'state'],
                      contract=[d for k, d in events if k == 'department_contract'],
                      acceptance=[d for k, d in events if k == 'department_acceptance'],
                      reused=[d for k, d in events if k in ('stage_reused', 'stage_discarded')],
                      owner_actions=[d for k, d in events if k == 'owner_action'],
                      feedback=[dict(r) for r in db.execute('SELECT * FROM owner_feedback WHERE project_id=?', (pid,))],
                      verifications=[dict(r) for r in db.execute(
                          'SELECT iteration, verdict, provider FROM verifications WHERE project_id=?', (pid,))])
    if text_rework:
        rework_seen = any(d.get('to') == 'REWORK' and 'Owner feedback' in str(d.get('reason', ''))
                          for d in record.get('transitions', []))
        same_project = bool(pid) and db.execute('SELECT COUNT(*) FROM projects').fetchone()[0] == 1
        request_saved = any(f['verdict'] == 'request' and 'AXB-TEXT-REWORK' in f['text']
                            for f in record.get('feedback', []))
        record['checks'].extend([
            {'name': 'e2e: persisted Owner feedback REWORK transition', 'ok': rework_seen},
            {'name': 'e2e: textual modification persisted as request feedback', 'ok': request_saved},
            {'name': 'e2e: text modification kept the same project', 'ok': same_project},
        ])
    if webapp:
        record['web_use'] = used
        for name, u in used.items():
            if 'opened' in name:
                record['checks'].append({'name': name.replace('opened', 'used by the harness (page content)'), 'ok': u.get('ok'),
                                         'detail': json.dumps({k: u.get(k) for k in ('url', 'contains', 'error')}, ensure_ascii=False)})
            else:
                record['checks'].append({'name': name.replace('stopped from the page', 'refused after stop'),
                                         'ok': u.get('url_refused_after_stop')})
        record['checks'].append({'name': 'e2e: both web results were used', 'ok': len([n for n in used if 'opened' in n]) == (2 if text_rework else 1)})
    record['passed'] = bool(record['finished'] and pid and record['checks'] and
                            all(c.get('ok') for c in record['checks']))
    Path(out).write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    for c in record['checks']:
        print(('PASS ' if c.get('ok') else 'FAIL ') + c.get('name', '') + ' ' + str(c.get('detail', ''))[:160])
    print(json.dumps({k: record.get(k) for k in ('project', 'state', 'seconds')}, ensure_ascii=False, default=str))
    db.close()
    shutil.rmtree(profile, ignore_errors=True)
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe')
    parser.add_argument('fixture')
    parser.add_argument('out')
    parser.add_argument('--text-rework', action='store_true')
    parser.add_argument('--webapp', action='store_true')
    args = parser.parse_args()
    sys.exit(main(args.exe, args.fixture, args.out, text_rework=args.text_rework, webapp=args.webapp))
