// AX Branch local web UI. Reads stored state through the local API and sends only named Owner actions; it has
// no approval, execution or verification logic of its own. Polling pauses while the tab is hidden.
(function () {
  const TOKEN = document.querySelector('meta[name=axb-token]').content;
  const $ = s => document.querySelector(s);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const S = {ov: null, view: 'home', pid: null, project: null, pending: [], files: [], stageKey: null,
             requestId: null, seen: {}, typing: 0, busy: false};
  window.AXB = S;

  async function api(path, body) {
    const opt = {headers: {'X-AXB-Token': TOKEN}};
    if (body !== undefined) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    const r = await fetch('/api/' + path, opt);
    const data = await r.json().catch(() => ({error: `HTTP ${r.status}`}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }
  function notice(text, ms) {
    const n = $('#notice'); n.textContent = text; n.hidden = !text;
    clearTimeout(notice.t); if (text && ms !== 0) notice.t = setTimeout(() => { n.hidden = true; }, ms || 8000);
  }
  const fail = e => notice(String(e.message || e), 12000);

  // ---- orb ----
  const orb = new window.AXOrb($('#orb'));
  window.AXB.orb = orb;
  function updateOrb() {
    const ov = S.ov; if (!ov) return;
    const motion = !$('#motionOff').checked, low = $('#lowPower').checked;
    const shown = (ov.test_mode && S.forceOrb) || ov.orb;   // forceOrb: test server only (performance runs)
    orb.set(shown, motion, low);
    if (ov.orb === 'delegating' && ov.delegated.length) orb.delegate(ov.delegated);
    for (const p of ov.projects) {                 // one completion effect when a verified result arrives
      if (p.state === 'OWNER_REVIEW' && S.seen[p.id] && S.seen[p.id] !== 'OWNER_REVIEW' && motion) orb.complete();
      S.seen[p.id] = p.state;
    }
    const [label, what, next] = ov.orb_text[ov.orb] || ov.orb_text.idle;
    $('#orbLabel').textContent = label;
    const detail = ov.orb === 'delegating' && ov.delegated.length ? `${ov.delegated.join('·')}에 위임된 단계를 수행합니다.` : what;
    $('#orbCaption').innerHTML = `<b>실제 상태: ${esc(label)}</b> — ${esc(detail)}<br>다음: ${esc(next)}`;
    $('#orbInput').hidden = !(Date.now() - S.typing < 1500);
  }

  // ---- overview / sidebar ----
  async function refreshOverview() {
    S.ov = await api('overview');
    $('#version').textContent = 'v' + S.ov.version;
    $('#motionOff').checked = !!S.ov.settings.motion_off; $('#lowPower').checked = !!S.ov.settings.low_power;
    const list = $('#projects'); list.innerHTML = '';
    for (const p of S.ov.projects) {
      const b = document.createElement('button'); b.className = 'proj' + (p.id === S.pid && S.view === 'project' ? ' on' : '');
      b.innerHTML = `<span class="t" title="${esc(p.goal)}">${esc(p.title)}</span><span class="dot ${p.indicator}"></span>`;
      b.onclick = () => openProject(p.id); list.appendChild(b);
    }
    if (!S.libraryBuilt) buildLibrary();
    $('#groups').innerHTML = S.ov.groups.map(g => `<div class="group" style="background:${g.color}22"><div>${esc(g.label)}</div><div class="n">${g.count}</div></div>`).join('');
    updateOrb();
  }
  function depName(id) { const d = S.ov.departments.find(x => x.id === id); return d ? d.name : id; }
  function buildLibrary() {
    S.libraryBuilt = true;
    const lib = $('#library'); lib.innerHTML = '';
    const menu = $('#depMenu');
    for (const d of S.ov.departments) {
      const c = document.createElement('div'); c.className = 'chip'; c.draggable = true; c.dataset.dep = d.id;
      c.textContent = '▣ ' + d.name; c.title = d.role;
      c.addEventListener('dragstart', e => { S.dropped = false; e.dataTransfer.setData('text/axb-dep', d.id); e.dataTransfer.effectAllowed = 'copy'; });
      c.addEventListener('dragend', e => {
        if (!S.dropped) notice(`연결되지 않았습니다: ${d.name} — 놓은 곳이 목표 입력 영역이나 프로젝트의 '연결된 부서' 칸이 아니었습니다. 부서를 클릭해 상세 화면의 버튼을 사용하세요.`);
      });
      c.addEventListener('click', () => departmentDetail(d.id));
      lib.appendChild(c);
      const o = document.createElement('option'); o.value = d.id; o.textContent = `${d.name} — ${d.provides.slice(0, 2).join(', ')}`; menu.appendChild(o);
    }
    $('#refused').textContent = S.ov.refused.length ? '명세 오류로 제외: ' + S.ov.refused.join(', ') : '';
  }
  function dropZone(el, onDep) {
    el.addEventListener('dragover', e => { if (e.dataTransfer.types.includes('text/axb-dep')) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; el.classList.add('over'); } });
    el.addEventListener('dragleave', () => el.classList.remove('over'));
    el.addEventListener('drop', e => { el.classList.remove('over'); const id = e.dataTransfer.getData('text/axb-dep'); if (id) { e.preventDefault(); S.dropped = true; onDep(id); } });
  }
  dropZone($('#composer'), id => addPending(id));
  dropZone($('#projectDeps'), id => attachToProject(id));

  function addPending(id) {
    if (S.pending.includes(id)) return notice(`이미 첨부한 부서입니다: ${depName(id)}`);
    S.pending.push(id); draft(); renderPending();
  }
  function renderPending() {
    $('#pendingDeps').innerHTML = S.pending.map(id => `<span class="chip">▣ ${esc(depName(id))}<button class="x" data-rm="${esc(id)}" title="첨부 해제">×</button></span>`).join('');
    $('#pendingDeps').querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { S.pending = S.pending.filter(x => x !== b.dataset.rm); renderPending(); });
  }
  async function attachToProject(id) {
    if (!S.pid) return;
    try { await api(`project/${S.pid}/department`, {action: 'attach', id}); await refreshProject(); }
    catch (e) { fail(e); }
  }
  function departmentDetail(id) {
    const d = S.ov.departments.find(x => x.id === id); if (!d) return;
    const li = a => a.map(x => `<li>${esc(x)}</li>`).join('');
    $('#modalBody').innerHTML = `<h3>▣ ${esc(d.name)} <span class="muted">v${esc(d.version)}</span></h3><p>${esc(d.role)}</p>
      <div class="kv">제공 기능</div><ul>${li(d.provides)}</ul>
      <div class="kv">도구: <b>${esc(d.tools.join(', '))}</b> · 네트워크: <b>${d.network ? '허용' : '없음'}</b> · 에이전트: <b>${esc(d.agent_role)}</b></div>
      <div class="kv">입력 (계획용 설명)</div><ul>${li(d.inputs)}</ul><div class="kv">출력 (계획용 설명)</div><ul>${li(d.outputs)}</ul>
      <div class="kv">수용 기준 (에이전트에게 전달)</div><ul>${li(d.acceptance_criteria)}</ul>
      <div class="muted">부서 연결은 기능 연결만 기록합니다. 결제·인증정보·게시·연락 승인은 바뀌지 않습니다.</div>
      <div class="row end">${S.view === 'project' && S.pid ? '<button class="primary" id="mAttach">프로젝트에 추가</button>' : '<button class="primary" id="mPend">목표에 첨부</button>'}</div>`;
    const m = $('#modal'); m.showModal();
    const a = $('#mAttach'), pn = $('#mPend');
    if (a) a.onclick = () => { m.close(); attachToProject(id); };
    if (pn) pn.onclick = () => { m.close(); addPending(id); };
  }
  $('#modalClose').onclick = () => $('#modal').close();
  $('#depMenu').onchange = e => { if (e.target.value) addPending(e.target.value); e.target.value = ''; };

  // ---- goal box ----
  function draft() { if (!S.requestId) S.requestId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)); }
  const goal = $('#goal');
  goal.addEventListener('focus', () => { S.typing = Date.now(); orb.pulse(.2); updateOrb(); });
  goal.addEventListener('input', () => { draft(); S.typing = Date.now(); orb.pulse(.3); updateOrb(); setTimeout(updateOrb, 1600); });
  $('#files').onchange = async e => {
    S.files = [];
    for (const f of e.target.files) {
      if (f.size > 20 * 2 ** 20) { notice(`파일이 너무 큽니다 (20MB 제한): ${f.name}`); continue; }
      const buf = new Uint8Array(await f.arrayBuffer()); let bin = '';
      for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
      S.files.push({name: f.name, data: btoa(bin)});
    }
    draft(); $('#fileNames').textContent = S.files.length ? `첨부 ${S.files.length}개: ` + S.files.map(f => f.name).join(', ') : '';
  };
  $('#submit').onclick = async () => {
    const text = goal.value.trim(); if (!text || S.busy) return;
    draft(); S.busy = true; $('#submit').disabled = true;
    try {
      const r = await api('projects', {goal: text, departments: S.pending, files: S.files, request_id: S.requestId});
      goal.value = ''; S.pending = []; S.files = []; S.requestId = null; renderPending(); $('#fileNames').textContent = ''; $('#files').value = '';
      orb.pulse(1.2);
      notice(r.created ? '목표를 접수했습니다. 淸月 CEO가 계획을 시작합니다.' : '이미 접수된 목표입니다 (중복 생성 안 함).');
      await refreshOverview(); openProject(r.id);
    } catch (e) { fail(e); }
    finally { S.busy = false; $('#submit').disabled = false; }
  };

  // ---- project view ----
  async function openProject(pid) { S.pid = pid; S.stageKey = null; show('project'); await refreshProject(); refreshOverview().catch(() => {}); }
  async function refreshProject() {
    if (!S.pid) return;
    const p = S.project = await api('project/' + S.pid);
    $('#crumb').textContent = '워크스페이스 / 실행 파이프라인';
    $('#banner').textContent = p.banner.text; $('#banner').style.background = p.banner.color;
    $('#pTitle').textContent = p.title;
    $('#pState').textContent = `${p.id} · ${p.state} · ${p.status} · v${p.iteration}` + (p.pause_reason ? ` · ${p.pause_reason.slice(0, 200)}` : '');
    $('#projectChips').innerHTML = p.attached.map(d => `<span class="chip">▣ ${esc(depName(d.id))}<button class="x" data-detach="${esc(d.id)}" title="해제 (다음 위임부터 적용)">×</button></span>`).join('') || '<span class="muted">없음 — 부서를 이 칸으로 끌어 놓거나 부서를 클릭해 [프로젝트에 추가]</span>';
    $('#projectChips').querySelectorAll('[data-detach]').forEach(b => b.onclick = async () => {
      try { await api(`project/${S.pid}/department`, {action: 'detach', id: b.dataset.detach}); notice('부서 해제: 다음 위임부터 적용 (실행 중인 단계는 끝까지 진행, 기록은 보존)'); refreshProject(); } catch (e) { fail(e); }
    });
    $('#pipeline').innerHTML = p.pipeline.map(r => `<div class="stage ${r.mark === '✓' ? 'done' : r.mark === '●' ? 'now' : ''} ${r.key === S.stageKey ? 'sel' : ''}" data-key="${esc(r.key || '')}">
        <div class="h">${esc(r.mark)} ${esc(r.title)}</div><div class="muted">${esc(r.engine)} · ${esc(r.detail)}</div></div>`).join('');
    $('#pipeline').querySelectorAll('.stage').forEach(el => el.onclick = () => { S.stageKey = el.dataset.key; loadRecords(); refreshProject(); });
    $('#verifs').innerHTML = (p.verifications.map(v => `<span class="verdict ${esc(v.verdict)}">v${v.iteration} ${esc(v.verdict)} · ${esc(v.provider)}</span>`).join('') || '<span class="muted">검증 기록 없음</span>')
      + (p.contract.length ? '<div class="muted" style="margin-top:6px">부서 계약 검사</div>' + p.contract.map(c => `<div class="kv">${esc(c.stage || '')} · <b>${esc(c.status || '')}</b> ${esc((c.problems || []).join('; '))}</div>`).join('') : '');
    $('#timeline').innerHTML = p.timeline.slice().reverse().map(t => `<div class="tl"><b>${esc(t.at)} ${esc(t.actor)}</b> ${esc(t.text)}</div>`).join('');
    renderOwner(p);
  }
  async function loadRecords() {
    if (!S.stageKey) return;
    try {
      const r = await api(`project/${S.pid}/records?key=${encodeURIComponent(S.stageKey)}`);
      const text = Array.isArray(r.records) ? r.records.join('\n') : String(r.records);
      $('#records').innerHTML = `<pre>${esc(text)}</pre>`;
    } catch (e) { fail(e); }
  }
  function renderOwner(p) {
    const box = $('#owner'), mode = p.owner.mode;
    if (!mode) { box.hidden = true; box.dataset.mode = ''; return; }
    box.hidden = false;
    if (box.dataset.mode === mode + p.iteration) return;   // keep what the Owner is typing
    box.dataset.mode = mode + p.iteration;
    if (mode === 'approval') {
      box.innerHTML = `<h3>승인 필요</h3><p>${esc(p.owner.note)}</p><textarea id="oNote" placeholder="거절할 때 淸月 CEO에게 줄 안내 (선택)"></textarea>
        <div class="row"><button class="primary" id="oYes">외부 연결 승인</button><button class="ghost" id="oNo">거절</button></div>`;
      $('#oYes').onclick = () => act('network', {approve: true});
      $('#oNo').onclick = () => act('network', {approve: false, note: $('#oNote').value});
      return;
    }
    const review = mode === 'review';
    box.innerHTML = `<h3>${review ? '결과 확인 및 피드백' : '결정 대기'}</h3>
      <p class="muted">${review ? '결과가 검증을 통과했습니다. [검증된 결과 열기]로 확인하고 의견을 적어 주세요. 수정이 필요하면 [수정 요청 / 계속], 끝내려면 [완료].'
        : esc(p.owner.note) + '<br>원하는 방향을 적고 [수정 요청 / 계속]을 누르면 淸月 CEO가 같은 프로젝트에서 다시 계획·작업·검증합니다. 비워 두면 같은 방향으로 계속합니다.'}</p>
      ${review ? `<div class="row"><button class="ghost" id="oRun">검증된 결과 열기</button><span class="muted">실행해 보니:</span>
        <label><input type="radio" name="works" value="yes"> 작동함</label><label><input type="radio" name="works" value="no"> 작동하지 않음</label>
        <label><input type="radio" name="works" value="unknown" checked> 아직 확인 안 함</label></div>` : ''}
      <textarea id="oText" placeholder="바꾸거나 더하고 싶은 점을 자유롭게 적어 주세요"></textarea>
      <div class="row"><button class="primary" id="oSend">수정 요청 / 계속</button><button class="ghost" id="oFinish">완료</button></div>`;
    if (review) $('#oRun').onclick = runResult;
    $('#oSend').onclick = () => {
      const w = document.querySelector('input[name=works]:checked'), works = w ? w.value : 'unknown', text = $('#oText').value.trim();
      if (review && works === 'unknown' && !text) return notice('바꾸고 싶은 점을 적거나, 작동 여부를 선택해 주세요.');
      act('review', {works, text}).then(() => { box.dataset.mode = ''; });
    };
    $('#oFinish').onclick = finishDialog;
  }
  async function act(action, body) {
    try { await api(`project/${S.pid}/${action}`, body || {}); await refreshProject(); refreshOverview().catch(() => {}); }
    catch (e) { fail(e); throw e; }
  }
  async function runResult() {
    try {
      const r = await api(`project/${S.pid}/result`, {});
      if (r.text !== undefined) { $('#modalBody').innerHTML = `<h3>${esc(r.title)}</h3><div class="result"><pre>${esc(r.text)}</pre></div>`; $('#modal').showModal(); }
      else notice(`${r.how === 'run' ? '실행함' : '열었음'}: ${r.path} (검증된 버전)`);
    } catch (e) { fail(e); }
  }
  async function finishDialog() {
    try { await api(`project/${S.pid}/close`, {}); } catch (e) { return fail(e); }
    $('#modalBody').innerHTML = `<h3>淸月 AI CEO</h3><p>프로젝트를 마칩니다. 이 프로젝트의 지식을 저장할까요?</p>
      <div class="row">만족도(%) <input id="cSat" type="number" min="0" max="100" value="90" style="width:70px"> 이유(선택) <input id="cWhy" style="flex:1"></div>
      <div class="row"><button class="primary" data-c="save">A. 저장하고 닫기</button><button class="ghost" data-c="pause">B. 일시중지</button><button class="ghost" data-c="discard">C. 저장하지 않고 닫기</button></div>`;
    const m = $('#modal'); m.showModal();
    m.querySelectorAll('[data-c]').forEach(b => b.onclick = async () => {
      const choice = b.dataset.c; let confirm = false;
      if (choice === 'discard' && !(confirm = window.confirm('저장하지 않고 닫으면 이 프로젝트의 지식과 Agent 컨텍스트가 영구히 버려집니다. 계속할까요?'))) return;
      m.close(); act('close', {choice, confirm, satisfaction: Number($('#cSat').value), why: $('#cWhy').value}).catch(() => {});
    });
  }
  $('#resume').onclick = () => act('resume').catch(() => {});
  $('#stop').onclick = () => act('stop').catch(() => {});

  // ---- feeds ----
  async function loadFeeds(target) {
    const data = await api('feeds');
    const render = cat => { const c = data[cat] || {}; return `<h3>${esc(cat)}</h3>` + ((c.items || []).slice(0, target ? 30 : 6).map(i =>
      `<div class="feed-item"><a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a><div class="muted">${esc(i.summary)}</div></div>`).join('')
      || `<div class="muted">${c.error ? '수집 실패: ' + esc(c.error) : '아직 수집한 자료가 없습니다. [공개 정보 새로 수집]을 누르세요.'}</div>`); };
    if (target) $('#feedFull').innerHTML = render(target);
    else { document.getElementById('feed-AI 동향').innerHTML = render('AI 동향'); document.getElementById('feed-AI 취업').innerHTML = render('AI 취업'); }
  }
  $('#refreshFeeds').onclick = async () => { notice('공개 출처에서 수집 중… (AI 호출 없음)', 0); try { await api('feeds/refresh', {}); notice('수집 결과를 확인하세요. 일부 출처만 포함하며 전체 시장 목록은 아닙니다.'); loadFeeds(); } catch (e) { fail(e); } };

  // ---- settings ----
  for (const id of ['motionOff', 'lowPower']) $('#' + id).onchange = async () => {
    try { S.ov.settings = await api('settings', {motion_off: $('#motionOff').checked, low_power: $('#lowPower').checked}); updateOrb(); } catch (e) { fail(e); }
  };

  // ---- views ----
  function show(view) {
    S.view = view.split(':')[0];
    for (const v of ['home', 'feed', 'project', 'devroom']) $('#view-' + v).hidden = v !== S.view;
    document.querySelectorAll('.nav').forEach(b => b.classList.toggle('on', b.dataset.view === view));
    if (S.view === 'home') { $('#crumb').textContent = '워크스페이스 / 청월 홈'; loadFeeds().catch(() => {}); orb.wake(); }
    if (S.view === 'feed') { $('#crumb').textContent = '워크스페이스 / ' + view.split(':')[1]; loadFeeds(view.split(':')[1]).catch(fail); }
    if (S.view === 'devroom') { $('#crumb').textContent = '오너 개발실 — AX Branch 자체의 개발 현황 (사용자 업무 프로젝트 아님)'; window.AXDev && window.AXDev.render().catch(fail); }
  }
  document.querySelectorAll('.nav').forEach(b => b.onclick = () => show(b.dataset.view));
  $('#newWork').onclick = () => { show('home'); goal.focus(); };
  window.AXB.show = show; window.AXB.api = api; window.AXB.notice = notice; window.AXB.esc = esc;

  // ---- polling (stops while the tab is hidden; reading never starts work) ----
  async function tick() {
    if (document.hidden) return;
    try { await refreshOverview(); if (S.view === 'project') await refreshProject(); } catch (e) { /* server gone: keep the page */ }
  }
  setInterval(tick, 2000);
  refreshOverview().then(() => {
    show('home');
    const q = new URLSearchParams(location.search);
    if (S.ov.test_mode && q.has('selftest')) { const s = document.createElement('script'); s.src = '/selftest.js'; document.body.appendChild(s); }
    if (S.ov.test_mode && q.has('perf')) setInterval(() => api('test/perf', Object.assign({at: Date.now(), state: orb.state, low: orb.low}, orb.stats)).catch(() => {}), 3000);
  }).catch(fail);
  const ds = document.createElement('script'); ds.src = '/devroom.js'; document.body.appendChild(ds);
})();
