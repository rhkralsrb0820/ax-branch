// Run the shipped page in a separate headless Chrome against a model-free HTTP fixture.
// node tests/browser_web_regressions.js [evidence.json]
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const {spawn} = require('node:child_process');
const root = path.resolve(__dirname, '..'), checks = [], posts = [], requests = [];
const profile = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'axb-regression-'));
const project = id => ({id, title: id, state: 'OWNER_REVIEW', status: 'WAITING_OWNER', iteration: 2,
  banner: {text: id, color: '#fff'}, attached: [], pipeline: [], verifications: [], acceptance: {}, conflicts: [], contract: [], timeline: [],
  owner: {mode: 'review', note: id + ' 안내'}});
const server = http.createServer(async (req, res) => {
  let body = ''; for await (const chunk of req) body += chunk;
  const url = new URL(req.url, 'http://localhost');
  requests.push(url.pathname);
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (req.method === 'POST') {
    const data = JSON.parse(body || '{}'); posts.push({path: url.pathname, body: data});
    if (url.pathname === '/api/test/report') { checks.push(data); return res.end('{}'); }
    if (url.pathname === '/api/test/done') { finished = true; return res.end('{}'); }
    return res.end('{}');
  }
  if (url.pathname === '/api/overview') return res.end(JSON.stringify({version: 'test', settings: {motion_off: true},
    projects: [], groups: [], departments: [], refused: [], delegated: [], orb: 'idle', orb_text: {idle: ['대기', '', '']}, test_mode: true}));
  if (url.pathname === '/api/feeds') return res.end('{}');
  if (url.pathname === '/api/test/posts') return res.end(JSON.stringify(posts));
  if (url.pathname.startsWith('/api/project/')) {
    if (url.pathname.endsWith('/records')) return res.end(JSON.stringify({records: ['기록']}));
    return res.end(JSON.stringify(project(url.pathname.split('/')[3])));
  }
  if (url.pathname === '/api/devroom') return res.end(JSON.stringify({status: {}, notes: []}));
  let file = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
  let full = file === 'selftest.js' ? path.join(__dirname, 'web_regressions.js') : path.join(root, 'axbranch/webui', file);
  if (!['index.html', 'app.js', 'orb.js', 'devroom.js', 'app.css', 'selftest.js'].includes(file)) { res.statusCode = 404; return res.end('{}'); }
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html; charset=utf-8');
  res.end(fs.readFileSync(full, 'utf8').replace('__AXB_TOKEN__', 'fixture'));
});
let finished = false, chrome, chromeError = '';
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--disable-gpu', '--window-size=1400,1000', `http://127.0.0.1:${port}/?selftest=1`], {stdio: ['ignore', 'ignore', 'pipe'], windowsHide: true});
  chrome.stderr.on('data', d => { chromeError += d.toString(); });
  chrome.on('exit', code => { if (!finished) { checks.push({name: 'Chrome stayed running', ok: false, detail: String(code) + ' ' + chromeError.slice(-1500)}); finished = true; } });
  chrome.on('error', e => { checks.push({name: 'Chrome launch', ok: false, detail: e.message}); finished = true; });
  const start = Date.now();
  while (!finished && Date.now() - start < 60000) await new Promise(resolve => setTimeout(resolve, 100));
  if (!finished) checks.push({name: 'finished within 60 seconds', ok: false, detail: requests.join(', ') + ' ' + chromeError.slice(-1500)});
  for (const c of checks) console.log(`${c.ok ? 'PASS' : 'FAIL'} ${c.name} ${c.detail || ''}`);
  const summary = {passed: checks.filter(c => c.ok).length, total: checks.length, finished, checks};
  if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(summary, null, 2));
  process.exitCode = finished && checks.length > 0 && checks.every(c => c.ok) ? 0 : 1;
})().catch(e => {console.error(e); process.exitCode = 1;}).finally(async () => {
  if (chrome && chrome.pid) await new Promise(resolve => spawn('taskkill', ['/PID', String(chrome.pid), '/T', '/F'], {stdio: 'ignore', windowsHide: true}).on('exit', resolve));
  server.close();
  // Only this test's newly-created, resolved temporary directory may be removed.
  if (path.dirname(profile) === path.resolve(require('node:os').tmpdir()) && path.basename(profile).startsWith('axb-regression-')) fs.rmSync(profile, {recursive: true, force: true, maxRetries: 5, retryDelay: 200});
});
