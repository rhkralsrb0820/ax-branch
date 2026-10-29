"""Owner data flow through the web page of a PACKAGED build, on the FIXED test app (no model; not unittest discovery).

An isolated AXB_ROOT gets one project whose verified versions are the developer fixtures in
tests/fixtures/owner_data_app (v1 -> v2 compatible revision -> v3 incompatible revision). The packaged
`AXBranch.exe web --test-mode` serves it; headless Chrome with its OWN temporary profile clicks AX Branch's real buttons
(selftest.js?owner-data). The result tab is another origin, so the harness plays the Owner's use of the result app
(form posts, page reads) and adds the next code version between steps. Afterwards it crashes the packaged server
(process tree killed) and restarts it to check that the last periodic save comes back.

    python -X utf8 tests/browser_owner_data_e2e.py <AXBranch.exe> <out.json>"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
CHROME = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
FIXTURE = Path(__file__).parent / 'fixtures' / 'owner_data_app'
SPEC = {'mode': 'web', 'owner_launch': 'double-click inventory_app.py', 'launch_args': ['--port', '{port}'], 'probes': []}


def seed(root):
    """One OWNER_REVIEW project with fixture v1 verified (source code writes the isolated database before start)."""
    os.environ['AXB_ROOT'] = str(root)
    from axbranch import engine as E
    from axbranch.state import Store
    ws = root / 'workspace'
    store = Store(ws / 'axbranch.sqlite3')
    pid = store.new_project('(시험 자료) 매장 재고 웹앱 — 고정 시험 앱, AI 제작 아님')
    store.update(pid, plan={'artifact_filename': 'inventory_app.py', 'artifact_kind': 'python', 'acceptance_criteria': ['x'],
                            'runtime': SPEC, 'pipeline': [], 'interpretation': 'fixed test app', 'verification_lenses': []})
    eng = E.Engine(store, workspace=ws, vault=root / 'obsidian', gai_db=root / 'none.db', llm=None)
    eng.attach_inputs(pid, [str(FIXTURE / 'inventory.csv')])
    add_version(store, ws, pid, 'v1_inventory_app.py')
    store.db.execute("UPDATE projects SET state='OWNER_REVIEW' WHERE id=?", (pid,))
    store.db.commit()
    store.close()
    return pid


def add_version(store, ws, pid, fixture):
    it = len(store.artifacts(pid)) + 1
    folder = ws / 'projects' / pid / 'artifacts' / f'v{it}'
    folder.mkdir(parents=True)
    path = folder / 'inventory_app.py'
    shutil.copyfile(FIXTURE / fixture, path)
    store.update(pid, iteration=it)
    aid = store.add_artifact(pid, it, path, hashlib.sha256(path.read_bytes()).hexdigest(), 'python', None)
    store.add_verification(pid, aid, it, 'PASS', {'verdict': 'PASS', 'findings': [], 'note': 'fixed test version'},
                           {'ok': True}, 'fixture')
    return it


def get(url):
    return urllib.request.urlopen(url, timeout=15).read().decode('utf-8')


def post_update(url, item, qty):
    body = urllib.parse.urlencode({'item': item, 'qty': qty}).encode()
    urllib.request.urlopen(urllib.request.Request(url + 'update', data=body, method='POST'), timeout=15).read()


def main(exe, out, port=8768):
    root = Path(tempfile.mkdtemp(prefix='axb-owner-data-e2e-'))
    (root / 'workspace').mkdir()
    (root / 'obsidian').mkdir()
    pid = seed(root)
    ws = root / 'workspace'
    env = {**os.environ, 'AXB_ROOT': str(root), 'AXB_DEV': '1', 'AXB_SAVE_INTERVAL': '2',
           'AXB_GAI_DB': str(root / 'none.db')}
    checks, harness = [], []

    def start_server():
        (ws / 'web-server.json').unlink(missing_ok=True)
        proc = subprocess.Popen([exe, 'web', '--port', str(port), '--test-mode'], env=env)
        for _ in range(60):
            if (ws / 'web-server.json').exists():
                break
            time.sleep(0.5)
        return proc

    def api(path, body=None):
        info = json.loads((ws / 'web-server.json').read_text(encoding='utf-8'))
        req = urllib.request.Request(f'http://127.0.0.1:{port}/api/{path}', method='POST' if body is not None else 'GET',
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={'X-AXB-Token': info['token'], 'Content-Type': 'application/json'})
        return json.loads(urllib.request.urlopen(req, timeout=120).read())

    def signal(name, **value):
        f = ws / 'test-signals.json'
        data = json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
        data[name] = value or True
        f.write_text(json.dumps(data), encoding='utf-8')

    def check(name, ok, detail=''):
        harness.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:300]})

    from axbranch.state import Store
    server = start_server()
    profile = root / 'chrome-profile'
    chrome = subprocess.Popen([str(CHROME), '--headless=new', f'--user-data-dir={profile}', '--no-first-run',
                               '--no-default-browser-check', '--disable-extensions', '--window-size=1400,1000',
                               f'http://127.0.0.1:{port}/?selftest=1&owner-data=1&pid={pid}'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    reports_file, done, handled, started = ws / 'test-reports.jsonl', False, set(), time.time()
    try:
        while time.time() - started < 15 * 60 and not done:
            reports = [json.loads(l) for l in reports_file.read_text(encoding='utf-8').splitlines() if l.strip()] \
                if reports_file.exists() else []
            for r in reports:
                name = r.get('name', '')
                if name in handled:
                    continue
                handled.add(name)
                url = (json.loads(r['detail']) if str(r.get('detail', '')).startswith('{') else {}).get('url')
                if name == 'od: opened v1':
                    post_update(url, '빨대', 40)                   # the Owner enters data in the result tab
                    check('harness: data entered in the running v1', '>40<' in get(url).replace(' ', ''))
                    signal('entered')
                elif name == 'od: reopened with restored data':
                    check('harness: reopened result shows the saved data', '>40<' in get(url).replace(' ', ''))
                    signal('checked_restore')
                elif name == 'ready for v2':
                    store = Store(ws / 'axbranch.sqlite3'); add_version(store, ws, pid, 'v2_inventory_app.py'); store.close()
                    signal('v2')
                elif name == 'od: revised version opened':
                    html = get(url)
                    check('harness: revised v2 runs with the earlier data', '수정 버전 v2' in html and '>40<' in html.replace(' ', ''))
                    post_update(url, '종이컵', 77)
                    signal('checked_v2')
                elif name == 'ready for v3':
                    store = Store(ws / 'axbranch.sqlite3'); add_version(store, ws, pid, 'v3_incompatible_inventory_app.py'); store.close()
                    signal('v3')
                elif name == 'od: previous version opened with the data':
                    html = get(url)
                    check('harness: previous version shows the kept data', '>77<' in html.replace(' ', '') and '>40<' in html.replace(' ', ''))
                    signal('checked_previous')
                elif name == 'done':
                    done = True
            time.sleep(1)
        page = [r for r in (json.loads(l) for l in reports_file.read_text(encoding='utf-8').splitlines() if l.strip())
                if r.get('name', '').startswith('od: ')]
        checks += [{'name': r['name'], 'ok': r.get('ok'), 'detail': r.get('detail', '')[:300]} for r in page]
        # Abnormal end: data changed while open, a periodic save, then the packaged server process tree is killed.
        r = api(f'project/{pid}/result', {'choice': 'previous'})
        post_update(r['url'], '냅킨', 5)
        saved, t0 = None, time.time()
        while time.time() - t0 < 30 and not saved:
            s = api(f'project/{pid}')['owner_web_run']
            if s.get('last_saved') and s['last_saved'].get('reason') == 'periodic':
                saved = s['last_saved']
            time.sleep(1)
        check('harness: periodic save while open', saved, saved)
        subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], capture_output=True)
        time.sleep(3)
        try:
            urllib.request.urlopen(r['url'], timeout=5)
            check('harness: result died with the killed AX Branch', False)
        except OSError:
            check('harness: result died with the killed AX Branch', True)
        server = start_server()
        back = api(f'project/{pid}/result', {'choice': 'previous'})
        check('harness: after restart the last periodic save is restored',
              back.get('restored') and saved and back['restored']['snapshot'] == saved['snapshot'] and
              '>5<' in get(back['url']).replace(' ', ''), json.dumps(back.get('restored'), ensure_ascii=False))
        api(f'project/{pid}/result-stop', {})
        latest = api(f'project/{pid}/result', {})
        check('harness: incompatible latest version still refused, data intact', latest.get('incompatible'), latest.get('reason'))
    finally:
        subprocess.run(['taskkill', '/PID', str(chrome.pid), '/T', '/F'], capture_output=True)
        subprocess.run([exe, 'web', '--stop'], env=env, capture_output=True, timeout=30)
        time.sleep(2)
        if server.poll() is None:
            server.kill()
    checks += harness
    record = {'exe': exe, 'exe_sha256': hashlib.sha256(Path(exe).read_bytes()).hexdigest(), 'project': pid,
              'isolated_root': str(root), 'seconds': round(time.time() - started), 'finished': done,
              'fixture': 'tests/fixtures/owner_data_app (developer fixture from generated P-20261029-99cea3; not AI-produced)',
              'checks': checks, 'model_calls': 0}
    record['passed'] = bool(done and checks and all(c.get('ok') for c in checks))
    Path(out).write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    for c in checks:
        print(('PASS ' if c.get('ok') else 'FAIL ') + c['name'] + ' ' + str(c.get('detail', ''))[:140])
    print(json.dumps({k: record[k] for k in ('project', 'finished', 'passed', 'seconds')}))
    shutil.rmtree(profile, ignore_errors=True)
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe')
    parser.add_argument('out')
    args = parser.parse_args()
    sys.exit(main(args.exe, args.out))
