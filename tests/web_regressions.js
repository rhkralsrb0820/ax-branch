// Browser assertions against the real app.js; API calls are intercepted, never sent to a user workspace.
(async () => {
  const S = window.AXB, $ = s => document.querySelector(s), realFetch = window.fetch.bind(window);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const report = (name, ok, detail = '') => S.api('test/report', {name, ok: !!ok, detail});
  const until = async f => { for (let i = 0; i < 60; i++) { if (f()) return; await sleep(50); } throw Error('condition timed out'); };
  const a = 'P-20261025-aaaaaa', b = 'P-20261025-bbbbbb';
  const response = data => new Response(JSON.stringify(data), {headers: {'Content-Type': 'application/json'}});
  let approval = false, delayed, delayA = false, delayRecords = false, pendingRecords;
  window.fetch = async (url, opt) => {
    const r = await realFetch(url, opt);
    if (url === '/api/project/' + a && delayA) { delayA = false; await new Promise(resolve => { delayed = resolve; }); }
    if (String(url).includes('/records?') && delayRecords) { delayRecords = false; await new Promise(resolve => { pendingRecords = resolve; }); }
    if (String(url).match(/\/api\/project\/P-[^/]+$/) && (!opt || !opt.method)) {
      const p = await r.json();
      if (approval) p.owner = {mode: 'approval', note: p.id + ' 전용 승인 안내'};
      return response(p);
    }
    return r;
  };
  try {
    await S.openProject(a); $('#oText').value = 'A 수정';
    await sleep(2200);
    await report('W1 polling preserves same-project typing', $('#oText').value === 'A 수정');
    const staleSend = $('#oSend').onclick;
    await S.openProject(b);
    await report('W1 switching clears another project feedback', $('#oText').value === '');
    $('#oText').value = 'B 수정'; $('#oSend').click(); await sleep(200);
    const posts = await S.api('test/posts');
    await report('W1 review posts B text to B only', posts.some(p => p.path === `/api/project/${b}/review` && p.body.text === 'B 수정'));
    staleSend(); await sleep(100);
    await report('W1 detached A action rejected', (await S.api('test/posts')).filter(p => p.path.endsWith('/review')).length === posts.filter(p => p.path.endsWith('/review')).length);
    await S.openProject(a);
    await report('W1 returning restores own draft', $('#oText').value === 'A 수정');
    S.stageKey = 'engineer'; delayRecords = true;
    // Click the shipped pipeline loader with a synthetic row returned on the next fetch.
    const origFetch = window.fetch;
    window.fetch = async (url, opt) => {
      const r = await origFetch(url, opt);
      if (url === '/api/project/' + a) { const p = await r.json(); p.pipeline = [{key:'engineer', title:'engineer', mark:'✓', engine:'test', detail:''}]; return response(p); }
      return r;
    };
    await S.openProject(a); $('.stage').click(); await until(() => pendingRecords);
    await S.openProject(b); pendingRecords(); await sleep(100);
    await report('W1 delayed records cannot overwrite B', $('#records').textContent === '');
    delayA = true; const old = S.openProject(a); await until(() => delayed);
    await S.openProject(b); delayed(); await old;
    await report('W1 delayed A project cannot overwrite B', S.project.id === b && $('#pTitle').textContent === b);
    approval = true;
    await S.openProject(a); const staleYes = $('#oYes').onclick; $('#oNote').value = 'A 거절 안내';
    await S.openProject(b);
    await report('W1 approval displays B explanation and clears A note', $('#owner').textContent.includes(b + ' 전용 승인 안내') && $('#oNote').value === '');
    staleYes(); $('#oYes').click(); await sleep(150);
    const approvals = (await S.api('test/posts')).filter(p => p.path.endsWith('/network'));
    await report('W1 approve targets visible B only', approvals.length === 1 && approvals[0].path === `/api/project/${b}/network`);
    await S.openProject(a);
    await report('W1 A approval draft restored', $('#oNote').value === 'A 거절 안내');
  } catch (e) { await report('browser regression crashed', false, e.stack); }
  finally { await S.api('test/done', {}); }
})();
