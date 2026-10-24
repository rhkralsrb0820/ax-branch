"""Real E2E through the web page of a PACKAGED build (not unittest discovery: real models, minutes, Chrome).

An isolated root (AXB_ROOT) gets a fresh workspace; the packaged `AXBranch.exe web --test-mode` serves it; headless
Chrome with its OWN temporary profile (the Owner's Chrome is never used) runs selftest.js?e2e: goal + attached file +
two dragged departments -> submit -> the real worker and models run -> open the verified result -> save feedback.
The harness then reads the isolated database (calls, tokens, contract, acceptance, feedback) and writes a JSON record.

    python -X utf8 tests/browser_web_e2e.py <AXBranch.exe> <fixture.csv> <out.json>"""
import json
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


def main(exe, fixture, out, port=8767):
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
    url = f'http://127.0.0.1:{port}/?selftest=1&e2e=1&goal=' + urllib.parse.quote(GOAL)
    chrome = subprocess.Popen([str(CHROME), '--headless=new', f'--user-data-dir={profile}', '--no-first-run',
                               '--no-default-browser-check', '--disable-extensions', '--window-size=1400,1000', url],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started, reports = time.time(), []
    try:
        while time.time() - started < 30 * 60:
            if reports_file.exists():
                reports = [json.loads(line) for line in reports_file.read_text(encoding='utf-8').splitlines() if line.strip()]
                if any(r.get('name') == 'done' for r in reports):
                    break
            time.sleep(5)
    finally:
        subprocess.run(['taskkill', '/PID', str(chrome.pid), '/T', '/F'], capture_output=True)
        subprocess.run([exe, 'web', '--stop'], env=env, capture_output=True, timeout=30)
        time.sleep(2)
        if server.poll() is None:
            server.kill()
    db = sqlite3.connect(root / 'workspace' / 'axbranch.sqlite3')
    db.row_factory = sqlite3.Row
    pid = next((r.get('detail') for r in reports if r.get('name') == 'done'), None)
    record = {'exe': exe, 'started': started, 'seconds': round(time.time() - started), 'project': pid,
              'checks': [r for r in reports if r.get('name') != 'done'], 'isolated_root': str(root)}
    if pid:
        p = db.execute('SELECT state, pause_reason, iteration FROM projects WHERE id=?', (pid,)).fetchone()
        events = [(r['kind'], json.loads(r['detail'])) for r in db.execute(
            'SELECT kind, detail FROM events WHERE project_id=? ORDER BY id', (pid,))]
        calls = [{'who': d['who'], 'provider': d['provider'], 'seconds': d['seconds'], 'tokens': d.get('tokens')}
                 for k, d in events if k == 'call']
        record.update(state=dict(p), calls=calls,
                      contract=[d for k, d in events if k == 'department_contract'],
                      acceptance=[d for k, d in events if k == 'department_acceptance'],
                      reused=[d for k, d in events if k in ('stage_reused', 'stage_discarded')],
                      owner_actions=[d for k, d in events if k == 'owner_action'],
                      feedback=[dict(r) for r in db.execute('SELECT * FROM owner_feedback WHERE project_id=?', (pid,))],
                      verifications=[dict(r) for r in db.execute(
                          'SELECT iteration, verdict, provider FROM verifications WHERE project_id=?', (pid,))])
    Path(out).write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    for c in record['checks']:
        print(('PASS ' if c.get('ok') else 'FAIL ') + c.get('name', '') + ' ' + str(c.get('detail', ''))[:160])
    print(json.dumps({k: record.get(k) for k in ('project', 'state', 'seconds')}, ensure_ascii=False, default=str))
    db.close()
    shutil.rmtree(profile, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
