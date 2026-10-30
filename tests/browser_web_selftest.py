"""Headless Chrome self-test of the local web UI (not part of unittest discovery: it needs Chrome).

A test-mode server on a temporary workspace (fake launcher, no engine, no model) serves the page with ?selftest;
Chrome runs headless with its OWN temporary profile (the Owner's Chrome, profile and sessions are never used),
is killed as a process tree at the end, and the profile is deleted. Prints one line per check and a JSON summary.

    python -X utf8 tests/browser_web_selftest.py [out.json]"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from axbranch import web, departments, improvements, engine as E   # noqa: E402
from axbranch.state import Store              # noqa: E402

CHROME = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')


def cpu_ms(profile):
    """Total CPU (ms) of the Chrome processes using this temporary profile (and only those)."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*"
          + str(profile) + "*' } | ForEach-Object { (Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue).TotalProcessorTime.TotalMilliseconds } "
          "| Measure-Object -Sum | ForEach-Object Sum")
    out = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def main(out=None):
    tmp = Path(tempfile.mkdtemp(prefix='axb-web-selftest-'))
    ws, profile = tmp / 'ws', tmp / 'chrome-profile'
    ws.mkdir()
    fixture = Store(ws / 'axbranch.sqlite3')
    pid = fixture.new_project('H3 browser fixture (scripted recommendation data, no model)')
    departments.record_recommendations(fixture, pid, [
        {'id': 'research', 'reason': 'Synthetic browser fixture: inspect supplied evidence'},
        {'id': 'operations', 'reason': 'Synthetic browser fixture: check quantities'}])
    # Improvement candidate + capability decision + a project waiting for the Owner (synthetic records, no model).
    review = fixture.new_project('Synthetic browser fixture: improvement evidence')
    aid = fixture.add_artifact(review, 1, ws / 'a.py', 'sha', 'python', None)
    fixture.add_verification(review, aid, 1, 'FAIL', {'verdict': 'FAIL', 'findings': [], 'note': 'x'}, {'ok': False, 'exit_code': 1}, 'codex')
    sig = E.failure_code(fixture.verifications(review)[-1])
    fixture.event(review, 'decision', what='strategy: replan', why='synthetic: run the self-test before handing over', by='fixture')
    fixture.event(review, 'decision', what='repeated failure signature', why=sig, by='engine')
    fixture.add_verification(review, aid, 1, 'PASS', {'verdict': 'PASS', 'findings': [], 'note': 'x'}, {'ok': True, 'exit_code': 0}, 'codex')
    fixture.db.execute("UPDATE projects SET state='OWNER_REVIEW' WHERE id=?", (review,))
    fixture.event(review, 'capability_decision', capability='lora_training', status='needs_owner',
                  tried=[{'option': 'local_cpu_lora', 'ok': False, 'why': 'synthetic', 'seconds': 1}],
                  cost=['0'], minimal_approval=['synthetic sign-in'], next_action='Owner decides')
    fixture.db.commit()
    improvements.observe(fixture, review)
    fixture.close()
    launched = []

    def no_engine():
        raise AssertionError('no engine in the browser self-test')
    app, httpd = web.serve(ws, 0, launcher=lambda w, pid: launched.append(pid), engine_factory=no_engine, test_mode=True)
    app.port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{app.port}/?selftest=1'
    chrome = subprocess.Popen([str(CHROME), '--headless=new', f'--user-data-dir={profile}', '--no-first-run',
                               '--no-default-browser-check', '--disable-extensions', '--window-size=1400,1000', url],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    perf, results, started = {}, [], time.time()
    try:
        while time.time() - started < 240:
            for r in app.reports[len(results):]:
                results.append(r)
                if r['kind'] == 'perf-phase':
                    key = 'low' if r.get('low') else 'normal'
                    perf.setdefault(key, {})[r['edge']] = (time.time(), cpu_ms(profile))
                elif r['kind'] == 'selftest' and r.get('name') != 'done':
                    print(('PASS ' if r['ok'] else 'FAIL ') + f"[{r['phase']}] {r['name']} {r.get('detail', '')}", flush=True)
            if any(r['kind'] == 'selftest' and r.get('name') == 'done' for r in results):
                break
            time.sleep(0.3)
        else:
            print('FAIL self-test did not finish within 240 s', flush=True)
    finally:
        subprocess.run(['taskkill', '/PID', str(chrome.pid), '/T', '/F'], capture_output=True)
        httpd.shutdown()
        httpd.server_close()
    checks = [r for r in results if r['kind'] == 'selftest' and r.get('name') != 'done']
    cpu = {k: round(100 * (v['end'][1] - v['start'][1]) / 1000 / (v['end'][0] - v['start'][0]), 1)
           for k, v in perf.items() if 'start' in v and 'end' in v}
    summary = {'passed': sum(r['ok'] for r in checks), 'total': len(checks), 'launched': launched,
               'chrome_cpu_pct_one_core_while_animating': cpu,
               'finished': any(r.get('name') == 'done' for r in results)}
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if out:
        Path(out).write_text(json.dumps({'summary': summary, 'checks': checks}, ensure_ascii=False, indent=1), encoding='utf-8')
    time.sleep(1)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if summary['finished'] and summary['passed'] == summary['total'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
