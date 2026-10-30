// AX Branch local web UI. Reads stored state through the local API and sends only named Owner actions; it has
// no approval, execution or verification logic of its own. Polling pauses while the tab is hidden.
(function () {
  const TOKEN = document.querySelector('meta[name=axb-token]').content;
  const $ = s => document.querySelector(s);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const S = {ov: null, view: 'home', pid: null, project: null, pending: [], files: [], stageKey: null,
             requestId: null, seen: {}, typing: 0, busy: false, navigation: 0, ownerDrafts: {}};
  window.AXB = S;

  async function api(path, body) {
    const opt = {headers: {'X-AXB-Token': TOKEN}};
    if (body !== undefined) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    const r = await fetch('/api/' + path, opt);
    const data = await r.json().catch(() => ({error: `HTTP ${r.status}`}));
    if (!r.ok) {
      const error = new Error(data.error || `HTTP ${r.status}`);
      if (r.status === 400 && data.submission === 'rejected_before_creation') error.rejectedRequest = data.request_id;
      throw error;
    }
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
    renderTaskBudgets();
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
    if (S.view === 'home') renderHomeActive().catch(() => {});
  }
  // While work runs, the home centres on that project's real pipeline and folds the info cards (once per project:
  // an Owner who reopens them keeps them open).
  async function renderHomeActive() {
    const box = $('#homeActive');
    const run = S.ov.projects.find(p => ['ACTIVE', 'RECOVERING'].includes(p.status))
      || S.ov.projects.find(p => p.status === 'WAITING_FOR_OWNER' && ['OWNER_REVIEW', 'PAUSED'].includes(p.state) && p.state !== 'CLOSED');
    if (!run) { box.hidden = true; S.homeFolded = null; return; }
    const p = await api('project/' + run.id);
    if (S.view !== 'home') return;
    const now = p.pipeline.find(r => r.mark === '●'), active = ['ACTIVE', 'RECOVERING'].includes(run.status);
    box.hidden = false;
    box.innerHTML = `<div class="row"><h3>${active ? '진행 중인 업무' : 'Owner 확인을 기다리는 업무'}: ${esc(p.title)}</h3><span class="grow"></span><button class="primary" id="homeOpen">파이프라인 보기</button></div>
      <div class="banner" style="background:${esc(p.banner.color)}">${esc(p.banner.text)}</div>
      <div class="muted">${esc(p.id)} · v${p.iteration} · ${now ? '현재 단계: ' + esc(now.title) + ' (' + esc(now.engine) + ')' : esc(p.state)}${S.ov.delegated.length && active ? ' · 위임 부서: ' + esc(S.ov.delegated.join(', ')) : ''}</div>
      <div class="pipeline">${p.pipeline.map(r => `<div class="stage ${r.mark === '✓' ? 'done' : r.mark === '●' ? 'now' : ''}"><div class="h">${esc(r.mark)} ${esc(r.title)}</div><div class="muted">${esc(r.detail)}</div></div>`).join('')}</div>`;
    $('#homeOpen').onclick = () => openProject(run.id);
    if (S.homeFolded !== run.id) { S.homeFolded = run.id; $('#homeFeeds').open = false; }
  }
  const LC = {legacy: '기존 부서(행동 검증 미판정)', candidate: '후보', verified: '검증됨', quarantined: '격리됨', retired: '폐기됨'};
  function depName(id) { const d = S.ov.departments.find(x => x.id === id); return d ? d.name : id; }
  function buildLibrary() {
    S.libraryBuilt = true;
    const lib = $('#library'); lib.innerHTML = '';
    const menu = $('#depMenu');
    for (const d of S.ov.departments) {
      const lc = d.lifecycle || {status: 'legacy'}, usable = ['verified', 'legacy'].includes(lc.status);
      const c = document.createElement('div'); c.className = 'chip' + (usable ? '' : ' blocked'); c.draggable = usable; c.dataset.dep = d.id;
      c.textContent = '▣ ' + d.name + (lc.status === 'legacy' ? '' : ` · ${LC[lc.status] || lc.status}`);
      c.title = usable ? d.role : `${LC[lc.status] || lc.status}: ${lc.reason || ''}`;
      c.addEventListener('dragstart', e => { S.dropped = false; e.dataTransfer.setData('text/axb-dep', d.id); e.dataTransfer.effectAllowed = 'copy'; });
      c.addEventListener('dragend', e => {
        if (!S.dropped) notice(`연결되지 않았습니다: ${d.name} — 놓은 곳이 목표 입력 영역이나 프로젝트의 '연결된 부서' 칸이 아니었습니다. 부서를 클릭해 상세 화면의 버튼을 사용하세요.`);
      });
      c.addEventListener('click', () => departmentDetail(d.id));
      lib.appendChild(c);
      if (!usable) continue;                       // quarantined/retired/candidate: visible, never attachable
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
    S.required = (S.required || []).filter(x => S.pending.includes(x));
    $('#pendingDeps').innerHTML = S.pending.map(id => { const req = S.required.includes(id);
      return `<span class="chip${req ? ' req' : ''}">▣ ${esc(depName(id))}<button class="x mode" data-req="${esc(id)}" aria-pressed="${req}" title="필수로 지정하면 淸月 CEO가 반드시 이 부서에 단계를 맡기고, 그 결과가 수용 기준을 통과해야 Owner 검토로 넘어갑니다">${req ? '🔒 필수' : '사용 가능'}</button><button class="x" data-rm="${esc(id)}" title="첨부 해제">×</button></span>`; }).join('');
    $('#pendingDeps').querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { S.pending = S.pending.filter(x => x !== b.dataset.rm); renderPending(); });
    $('#pendingDeps').querySelectorAll('[data-req]').forEach(b => b.onclick = () => { const id = b.dataset.req;
      S.required = S.required.includes(id) ? S.required.filter(x => x !== id) : [...S.required, id]; renderPending(); });
  }
  async function attachToProject(id) {
    if (!S.pid) return;
    try { await api(`project/${S.pid}/department`, {action: 'attach', id}); await refreshProject(); }
    catch (e) { fail(e); }
  }
  function departmentDetail(id) {
    const d = S.ov.departments.find(x => x.id === id); if (!d) return;
    const li = a => a.map(x => `<li>${esc(x)}</li>`).join('');
    const lc = d.lifecycle || {status: 'legacy'}, usable = ['verified', 'legacy'].includes(lc.status);
    $('#modalBody').innerHTML = `<h3>▣ ${esc(d.name)} <span class="muted">v${esc(d.version)}</span></h3><p>${esc(d.role)}</p>
      <div class="kv">상태: <b>${esc(LC[lc.status] || lc.status)}</b> — ${esc(lc.reason || '')}</div>
      ${(lc.evidence || []).length ? `<div class="kv">근거</div><ul>${li(lc.evidence)}</ul>` : ''}
      ${(lc.history || []).length ? `<details><summary>상태 변경 기록 ${lc.history.length}건</summary><ul>${li(lc.history.map(h => `${h.at} ${h.from} → ${h.to}: ${h.reason} (${h.by})`))}</ul></details>` : ''}
      <div class="kv">제공 기능</div><ul>${li(d.provides)}</ul>
      <div class="kv">도구: <b>${esc(d.tools.join(', '))}</b> · 네트워크: <b>${d.network ? '허용' : '없음'}</b> · 에이전트: <b>${esc(d.agent_role)}</b></div>
      <div class="kv">입력 (계획용 설명)</div><ul>${li(d.inputs)}</ul><div class="kv">출력 (계획용 설명)</div><ul>${li(d.outputs)}</ul>
      <div class="kv">수용 기준 (에이전트에게 전달)</div><ul>${li(d.acceptance_criteria)}</ul>
      <div class="muted">부서 연결은 기능 연결만 기록합니다. 결제·인증정보·게시·연락 승인은 바뀌지 않습니다.</div>
      <div class="row end">${!usable ? '<span class="muted">이 상태에서는 새로 연결할 수 없습니다 (Owner의 기록된 결정 필요).</span>' : S.view === 'project' && S.pid ? '<button class="primary" id="mAttach">프로젝트에 추가</button>' : '<button class="primary" id="mPend">목표에 첨부</button>'}</div>`;
    const m = $('#modal'); m.showModal();
    const a = $('#mAttach'), pn = $('#mPend');
    if (a) a.onclick = () => { m.close(); attachToProject(id); };
    if (pn) pn.onclick = () => { m.close(); addPending(id); };
  }
  $('#modalClose').onclick = () => $('#modal').close();
  $('#depMenu').onchange = e => { if (e.target.value) addPending(e.target.value); e.target.value = ''; };

  // ---- goal box ----
  const tokenNumber = n => Number(n).toLocaleString('ko-KR');
  function renderTaskBudgets() {
    const profiles = S.ov.task_budgets || [], menu = $('#taskType');
    if (!profiles.length) return;
    const selected = menu.value || 'general';
    menu.innerHTML = profiles.map(p => `<option value="${esc(p.id)}">${esc(p.label)} · ${tokenNumber(p.max_reported_tokens)}토큰</option>`).join('');
    menu.value = profiles.some(p => p.id === selected) ? selected : 'general';
    renderTaskBudgetNote();
  }
  function renderTaskBudgetNote() {
    const profile = (S.ov?.task_budgets || []).find(p => p.id === $('#taskType').value);
    $('#taskBudgetNote').textContent = profile
      ? `수정·재개까지 합계 ${tokenNumber(profile.max_reported_tokens)}토큰 · 구독 사용량 한도이며 추가 결제 승인이 아닙니다.`
      : '수정·재개를 포함한 프로젝트 누적 한도입니다. 추가 결제를 승인하지 않습니다.';
  }
  $('#taskType').onchange = () => { draft(); renderTaskBudgetNote(); };
  const submissionKey = 'axb-pending-submission';
  let submission = null, submissionUnavailable = false;
  try { submission = JSON.parse(sessionStorage.getItem(submissionKey) || 'null'); }
  catch (e) { submissionUnavailable = true; notice('이전 접수 기록을 읽지 못했습니다. 저장소 접근을 복구한 뒤 새로고침하세요.', 0); }
  function draft() { if (!S.requestId) S.requestId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)); }
  const goal = $('#goal');
  const fileList = () => S.files.map(f => ({name: f.name, bytes: f.data.length}));
  async function accepted(r, recovered = false) {
    sessionStorage.removeItem(submissionKey); submission = null;
    goal.value = ''; S.pending = []; S.files = []; S.requestId = null; renderPending(); $('#fileNames').textContent = ''; $('#files').value = '';
    orb.pulse(1.2);
    notice(recovered ? '이전 제출의 접수를 확인해 복구했습니다. 프로젝트를 다시 만들지 않았습니다.'
      : r.created ? '목표를 접수했습니다. 淸月 CEO가 계획을 시작합니다.' : '이미 접수된 목표입니다 (중복 생성 안 함).');
    await refreshOverview(); await openProject(r.id);
  }
  async function recoverSubmission() {
    if (!submission) return false;
    const r = await api('submission?request_id=' + encodeURIComponent(submission.id));
    if (r.id) { await accepted(r, true); return true; }
    S.requestId = submission.id; goal.value = submission.goal; S.pending = submission.departments.slice(); renderPending();
    $('#taskType').value = submission.task_type || 'general'; renderTaskBudgetNote();
    S.required = (submission.required || []).slice(); renderPending();
    $('#fileNames').textContent = submission.files.length ? '다시 첨부 필요: ' + submission.files.map(f => f.name).join(', ') : '';
    notice('이전 제출의 접수가 아직 확인되지 않았습니다. 같은 목표로 재시도하세요.' + (submission.files.length ? ' 파일 내용은 저장하지 않았으므로 같은 파일을 다시 첨부해 주세요.' : ''), 0);
    return false;
  }
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
    if (submissionUnavailable) return notice('이전 접수 기록을 읽을 수 없어 중복 방지를 위해 제출을 멈췄습니다. 저장소 접근을 복구한 뒤 새로고침하세요.', 0);
    const text = goal.value.trim(); if (!text || S.busy) return;
    draft(); S.busy = true; $('#submit').disabled = true;
    try {
      if (submission) {
        const r = await api('submission?request_id=' + encodeURIComponent(submission.id));
        if (r.id) { await accepted(r, true); return; }
        if (text !== submission.goal || JSON.stringify(S.pending) !== JSON.stringify(submission.departments) || JSON.stringify(fileList()) !== JSON.stringify(submission.files)
            || ($('#taskType').value || 'general') !== (submission.task_type || 'general')
            || JSON.stringify((S.required || []).filter(x => S.pending.includes(x)).slice().sort()) !== JSON.stringify((submission.required || []).slice().sort())) {
          return notice('이전 제출을 확인 중입니다. 같은 목표·부서·첨부 파일·업무 종류로 재시도한 뒤 새 목표를 제출하세요.', 0);
        }
        S.requestId = submission.id;
      } else {
        const pending = {id: S.requestId, goal: text, departments: S.pending.slice(), files: fileList(),
          task_type: $('#taskType').value || 'general', required: (S.required || []).filter(x => S.pending.includes(x))};
        sessionStorage.setItem(submissionKey, JSON.stringify(pending)); // failure stops submission before any POST
        submission = pending;
      }
      const r = await api('projects', {goal: text, departments: S.pending, required: (S.required || []).filter(x => S.pending.includes(x)),
        files: S.files, task_type: submission.task_type || 'general', request_id: S.requestId});
      await accepted(r);
    } catch (e) {
      if (submission && e.rejectedRequest === submission.id) {
        try {
          sessionStorage.removeItem(submissionKey); submission = null; S.requestId = null;
          notice('프로젝트를 만들기 전에 제출이 거절됐습니다. 첨부·부서·목표를 수정하고 다시 제출하세요. ' + e.message, 0);
        } catch (storageError) {
          submissionUnavailable = true;
          notice('거절된 접수 기록을 지우지 못했습니다. 저장소 접근을 복구한 뒤 새로고침하세요.', 0);
        }
      } else notice('접수 확인이 끝나지 않았습니다. 새로고침 또는 재시도로 기존 접수를 먼저 확인합니다. ' + String(e.message || e), 0);
    }
    finally { S.busy = false; $('#submit').disabled = false; }
  };

  // ---- project view ----
  function renderExecutionBudget(budget) {
    const box = $('#executionBudget');
    box.hidden = !budget;
    if (!budget) return;
    const known = budget.reported_tokens !== null && budget.reported_tokens !== undefined;
    const used = known ? tokenNumber(budget.reported_tokens) : '집계 대기·미확인';
    const title = budget.acceptance_pending ? '검증 통과 · 청월의 최종 수락 대기'
      : budget.paused ? '사용 한도 때문에 일시 중단' : '이 프로젝트의 사용량';
    const limit = budget.configured ? `${tokenNumber(budget.max_reported_tokens)}토큰` : '설정 기록 없음';
    const phaseNames = {planning: '계획', production: '제작', verification: '검증', acceptance: '최종 수락', decision: '다음 행동 판단'};
    const stop = budget.stop;
    const reserve = stop ? `<p>다음 호출과 남은 필수 단계에 ${tokenNumber(stop.reserve || 0)}토큰을 남겨야 합니다.`
      + `${stop.remaining !== null && stop.remaining !== undefined ? ` 현재 남은 양은 ${tokenNumber(stop.remaining)}토큰입니다.` : ''}</p>`
      + ((stop.downstream || []).length ? `<div class="muted">남겨 둔 단계: ${stop.downstream.map(s => esc(phaseNames[s.phase] || s.phase)).join(' → ')}</div>` : '') : '';
    box.innerHTML = `<div class="row"><h3>${esc(title)}</h3><span class="grow"></span><span class="badge">${esc(budget.label || '이전 프로젝트')}</span></div>`
      + `<div class="budget-figures"><span>누적 사용 <b>${used}${known ? '토큰' : ''}</b></span><span>프로젝트 한도 <b>${limit}</b></span></div>`
      + (!known ? `<p class="muted">확인된 사용량 ${tokenNumber(budget.known_tokens || 0)}토큰. 진행 중이거나 사용량이 남지 않은 호출이 있어 전체를 0으로 표시하지 않습니다.</p>` : '')
      + (budget.acceptance_pending ? '<p>현재 버전의 검증은 통과했습니다. 최종 수락은 아직 끝나지 않았으며 결과와 검증 기록은 보존됩니다.</p>' : '')
      + reserve
      + '<div class="muted">수정·재시작에도 누적 사용량을 유지합니다. 토큰은 구독 사용량이며 추가 결제 승인이 아닙니다. 구독 한도가 먼저 끝날 수 있습니다.</div>'
      + (budget.configured ? `<details><summary>사용 한도 상세</summary><div class="muted">호출 ${tokenNumber(budget.started_calls || 0)} / ${tokenNumber(budget.max_calls)}회 · 실행 시간 한도 ${tokenNumber(budget.max_seconds)}초 · 호출별 지시문 ${tokenNumber(budget.max_prompt_chars)}자 이하.<br>예약량은 이전 실측에 따른 추정치입니다. 제공자가 더 많이 사용하면 한 번의 호출이 토큰 한도를 넘을 수 있습니다.</div></details>` : '');
  }
  function saveOwnerDraft() {
    const box = $('#owner'), text = $('#oText') || $('#oNote'), works = $('input[name=works]:checked');
    if (box.dataset.mode && text) S.ownerDrafts[box.dataset.mode] = {text: text.value, works: works ? works.value : 'unknown'};
  }
  async function openProject(pid) {
    saveOwnerDraft(); S.navigation++; S.pid = pid; S.project = null; S.stageKey = null;
    $('#owner').hidden = true; $('#owner').dataset.mode = ''; $('#owner').innerHTML = '';
    for (const id of ['records', 'pipeline', 'verifs', 'timeline', 'projectChips', 'pTitle', 'pState', 'banner', 'experience', 'executionBudget', 'webRun', 'capabilities', 'pNow']) $('#' + id).textContent = '';
    $('#capabilities').hidden = true;
    $('#webRun').hidden = true;
    $('#executionBudget').hidden = true;
    show('project'); await refreshProject(); refreshOverview().catch(() => {});
  }
  async function refreshProject() {
    if (!S.pid) return;
    const pid = S.pid, navigation = S.navigation;
    const p = await api('project/' + pid);
    if (pid !== S.pid || navigation !== S.navigation || S.view !== 'project') return;
    S.project = p;
    $('#crumb').textContent = '워크스페이스 / 실행 파이프라인';
    $('#banner').textContent = p.banner.text; $('#banner').style.background = p.banner.color;
    $('#pTitle').textContent = p.title;
    $('#pState').textContent = `${p.id} · ${p.state} · ${p.status} · v${p.iteration}` + (p.pause_reason ? ` · ${p.pause_reason.slice(0, 200)}` : '');
    const n = p.now || {};
    $('#pNow').innerHTML = (n.stage ? `지금 단계: <b>${esc(n.stage)}</b> · 담당 ${esc(n.engine)}` : '')
      + (n.next ? `${n.stage ? '<br>' : ''}멈춘 이유: ${esc(n.reason || n.stop)}<br>다음 행동: <b>${esc(n.next)}</b>` : '');
    renderExecutionBudget(p.execution_budget);
    renderWebRun(p.owner_web_run);
    renderCapabilities(p.capabilities || []);
    $('#projectChips').innerHTML = (p.attached.map(d => { const req = d.mode === 'required';
      return `<span class="chip${req ? ' req' : ''}">▣ ${esc(depName(d.id))} v${esc(d.version)}${d.via === 'ceo_recommendation' ? ' <small title="청월이 추천하고 Owner가 수락해 연결">추천 수락</small>' : ''}<button class="x mode" data-mode="${esc(d.id)}" data-req="${req}" title="${req ? '필수 해제 (이유 필요, 기록됨)' : '필수로 지정 (다음 계획·실행·수용부터 적용)'}">${req ? '🔒 필수' : '사용 가능'}</button>${req ? '' : `<button class="x" data-detach="${esc(d.id)}" title="해제 (다음 위임부터 적용)">×</button>`}</span>`; }).join('') || '<span class="muted">없음 — 부서를 이 칸으로 끌어 놓거나 부서를 클릭해 [프로젝트에 추가]</span>')
      + (p.state === 'PAUSED' && (p.required_unmet.problems || p.required_unmet.reason) && /required department|quarantined|retired|candidate/.test(p.pause_reason || '')
         ? `<div class="kv" role="status">수용을 막는 검사: ${esc((p.required_unmet.problems || [p.required_unmet.reason]).join('; '))}</div>` : '');
    $('#projectChips').querySelectorAll('[data-mode]').forEach(b => b.onclick = async () => {
      const req = b.dataset.req === 'true';
      const reason = req ? window.prompt('필수를 해제하는 이유 (기록됩니다)') : '';
      if (req && !reason) return;
      try { await api(`project/${pid}/department`, {action: req ? 'optional' : 'require', id: b.dataset.mode, reason}); notice(req ? '필수 해제: 기록됨' : '필수로 지정: 다음 계획·실행·수용부터 적용'); refreshProject(); } catch (e) { fail(e); }
    });
    $('#projectChips').querySelectorAll('[data-detach]').forEach(b => b.onclick = async () => {
      try { await api(`project/${pid}/department`, {action: 'detach', id: b.dataset.detach}); notice('부서 해제: 다음 위임부터 적용 (실행 중인 단계는 끝까지 진행, 기록은 보존)'); refreshProject(); } catch (e) { fail(e); }
    });
    const suggestions = p.recommendations || [];
    const canConnect = ['CREATED', 'PAUSED', 'OWNER_REVIEW'].includes(p.state);
    $('#recommendations').hidden = !suggestions.length;
    $('#recommendations').innerHTML = '<h3>淸月의 부서 추천</h3><div class="muted">필요한 기능만 제안합니다. 수락은 부서를 연결하며 실행·권한 부여·필수 부서 변경은 하지 않습니다.</div>'
      + (!canConnect ? '<div role="status">작업이 멈추거나 결과가 도착하면 연결할 수 있습니다.</div>' : '')
      + suggestions.map(d => `<div class="kv"><b>${esc(depName(d.department))}</b> · v${esc(d.version)} · ${esc(d.lifecycle === 'legacy' ? '기존 부서 · 작업 품질 미판정' : d.lifecycle)}<p>${esc(d.reason)}</p>${d.gap ? `<div class="muted">지금 연결된 부서로 부족한 기능: ${esc(d.gap)}</div>` : ''}`
        + (d.status === 'pending' ? `<button data-recommend="${esc(d.id)}" data-decision="accepted" ${!canConnect || !d.available ? 'disabled' : ''}>프로젝트에 연결</button> <button class="ghost" data-recommend="${esc(d.id)}" data-decision="dismissed" ${!canConnect ? 'disabled' : ''}>닫기</button>`
          + (!d.available ? '<span class="muted">명세·상태가 바뀌었거나 이미 연결된 부서입니다.</span>' : '')
          : `<span class="muted">${d.status === 'accepted' ? '연결됨' : '닫음'}</span>`)
        + `<div class="muted">${esc(d.note)}</div></div>`).join('');
    $('#recommendations').querySelectorAll('[data-recommend]').forEach(b => b.onclick = async () => {
      b.disabled = true;
      try {
        await api(`project/${pid}/recommendation`, {id: Number(b.dataset.recommend), decision: b.dataset.decision});
        if (pid === S.pid && navigation === S.navigation) {
          notice(b.dataset.decision === 'accepted' ? '부서 연결됨. 현재 계획은 유지되며 다음 계획부터 사용할 수 있습니다.' : '추천을 닫았습니다.');
          await refreshProject();
        }
      } catch (e) { fail(e); b.disabled = false; }
    });
    $('#pipeline').innerHTML = p.pipeline.map(r => `<div class="stage ${r.mark === '✓' ? 'done' : r.mark === '●' ? 'now' : ''} ${r.key === S.stageKey ? 'sel' : ''}" data-key="${esc(r.key || '')}">
        <div class="h">${esc(r.mark)} ${esc(r.title)}</div><div class="muted">${esc(r.engine)} · ${esc(r.detail)}</div></div>`).join('');
    $('#pipeline').querySelectorAll('.stage').forEach(el => el.onclick = () => { S.stageKey = el.dataset.key; loadRecords(); refreshProject(); });
    $('#verifs').innerHTML = (p.verifications.map(v => `<span class="verdict ${esc(v.verdict)}">v${v.iteration} ${esc(v.verdict)} · ${esc(v.provider)}</span>`).join('') || '<span class="muted">검증 기록 없음</span>')
      + ((p.acceptance.results || []).length ? `<div class="muted" style="margin-top:6px">부서 수용 기준 (독립 검증, v${p.acceptance.iteration})</div>` + p.acceptance.results.map(a => `<div class="kv">[${esc(a.department)}] <b>${esc(a.status)}</b> ${esc(a.criterion)}</div>`).join('') : '')
      + (p.conflicts.length ? '<div class="muted">기준 충돌</div>' + p.conflicts.map(c => `<div class="kv">[${esc(c.department)}] ${esc(c.criterion)} — <b>${esc(c.decision)}</b></div>`).join('') : '')
      + (p.contract.length ? '<div class="muted" style="margin-top:6px">부서 계약 검사 (형식만 — 내용 정확성은 독립 검증)</div>' + p.contract.map(c => `<div class="kv">${esc(c.stage || '')} · <b>${esc(c.status || '')}</b> ${esc((c.problems || []).join('; '))}</div>`).join('') : '');
    $('#timeline').innerHTML = p.timeline.slice().reverse().map(t => `<div class="tl"><b>${esc(t.at)} ${esc(t.actor)}</b> ${esc(t.text)}</div>`).join('');
    const experience = p.experience || {records: [], uses: [], searches: []};
    const count = experience.records.length, uses = experience.uses;
    const lessons = experience.records.flatMap(r => (r.lesson_candidates || []).map(l => ({...l, department: r.department})));
    $('#experience').innerHTML = `<h3>업무 경험</h3><div class="muted">최근 기록 ${count}개 · 이번 과제의 활용 판단 ${uses.length}개 · 품질 개선은 비교 평가 전까지 미확인</div>`
      + ((experience.errors || []).length ? '<div role="status">경험 기록에 실패한 항목이 있습니다. 기술 근거를 확인하세요.</div>' : '')
      + improvementsLine(p.improvements)
      + (lessons.length ? `<details><summary>근거가 있는 교훈 후보 ${lessons.length}개 · 개선 효과 미확인</summary>`
        + lessons.slice(-12).map(l => `<div class="kv"><b>${esc(l.title)}</b> · ${esc(l.department)}<br>${esc(l.observation)}<br>다음 업무 참고: ${esc(l.suggestion)}<br><span class="muted">근거 이벤트: ${esc((l.evidence_events || []).join(', '))} · 자동 추출 규칙에 따른 후보</span></div>`).join('') + '</details>' : '')
      + (uses.length ? uses.map(u => `<div class="kv"><b>${esc(u.experience)}</b> · ${esc(u.disposition)}<br>선택·미사용 이유: ${esc(u.reason || '기록 없음')}<br>이번 과제와의 차이: ${esc(u.difference || '기록 없음')}<br>청월이 보고한 판단 변경: ${esc(u.claimed_change || '기록 없음')}<br>연결된 실행: ${esc(u.applied_action || '기록 없음')}<br><span class="muted">판단 반영 기록이며 품질 개선의 증거는 아닙니다.</span></div>`).join('')
        : `<div class="muted">${experience.searches.some(s => s.status === 'none') ? '관련 경험을 찾지 못했습니다.' : '아직 경험 활용 판단이 없습니다.'}</div>`)
      + `<details><summary>경험·검증 근거 펼치기</summary><pre>${esc(JSON.stringify({records: experience.records, searches: experience.searches, uses, errors: experience.errors || [], document_contract: p.document_contract || []}, null, 2))}</pre></details>`;
    renderOwner(p);
  }
  const OPTION = {local_cpu_lora: '로컬 CPU 소형 LoRA (무료)', free_cloud_gpu: '무료 클라우드 GPU (Owner 로그인 필요)',
    installed_browser: '설치된 Chrome·Edge 확인', installed_tool: '설치된 프로그램 확인', pyinstaller_native_build: 'PyInstaller로 .exe 만들기 (무료, 지원)',
    supported_runtime_modes: '지원하는 실행 방식으로 다시 계획'};
  const CAP_STATUS = {resolved: '확보됨', needs_owner: 'Owner 승인 필요', needs_replan: '지원되는 대안으로 다시 계획 필요 (아직 확보 안 됨)', unsupported: '지원하지 않는 기능'};
  function renderCapabilities(list) {
    const box = $('#capabilities');
    box.hidden = !list.length;
    box.innerHTML = '<h3>필요한 기능 확보</h3><div class="muted">부족한 기능은 무료 대안부터 실제로 시도한 결과만 표시합니다. 권한·비용은 자동으로 부여하지 않습니다.</div>'
      + list.map(c => `<div class="kv"><b>${esc(c.capability)}</b> · ${c.status === 'resolved' ? '확보됨: ' + esc(OPTION[c.chosen] || c.chosen) : esc(CAP_STATUS[c.status] || c.status)}`
        + (c.tried || []).map(t => `<div class="muted">시도: ${esc(OPTION[t.option] || t.option)} → ${t.ok ? '성공' : '실패'}${t.why ? ' · ' + esc(String(t.why).slice(0, 200)) : ''} (${t.seconds}초)</div>`).join('')
        + (c.status !== 'resolved' ? ((c.minimal_approval || []).length ? `<div>필요한 최소 승인: ${esc(c.minimal_approval.join(' / '))}</div>` : '')
          + `<div class="muted">비용: ${esc((c.cost || []).join(' / ') || '-')} · 다음 행동: ${esc(c.next_action || '')}</div>` : '')
        + '</div>').join('');
  }
  function improvementsLine(im) {
    if (!im) return '';
    const ev = im.evaluation, used = im.used || [];
    return (ev ? `<div class="kv" role="status">개선 후보 평가용 프로젝트입니다: ${esc(ev.candidate)} · ${ev.arm === 'variant' ? '개선안 적용' : '기준(개선안 없음)'} · 원래 업무 ${esc(ev.source)} · 경험 검색 꺼짐</div>` : '')
      + (used.length ? `<div class="kv">청월에게 전달된 승인 개선 규칙: ${used.map(u => `${esc(u.stage)} 단계 ${esc((u.ids || []).join(', '))}`).join(' · ')}<br><span class="muted">참고 자료로만 전달되며 검증 기준·승인을 바꾸지 않습니다.</span></div>` : '');
  }

  // ---- 개선 후보 · 학습 경로 (axbranch/improvements.py through the API) ----
  async function loadImprovements() {
    const d = await api('improvements'), box = $('#improvementList');
    const when = t => t ? new Date(t * 1000).toLocaleString() : '';
    const arm = a => a ? `${a.passed}/${a.n} 통과 · 같은 실패 재발 ${a.recurred}회` : '-';
    box.innerHTML = '<h3>학습·개선 경로 (이 PC에서 실제로 하는 일)</h3>' + d.learning.map(l => `<div class="kv"><b>${esc(l.name)}</b> <span class="tag">${esc(l.status)}</span><br>${esc(l.detail)}${l.runs ? '<br>' + esc(l.runs) : ''}<br><span class="muted">효과: ${esc(l.effect)}</span></div>`).join('')
      + '<h3>학습 기록 (생성 결과물의 실제 학습 실행)</h3>'
      + ((d.training || []).map(t => `<div class="kv"><b>${esc(t.project)}</b> · ${esc(when(t.at))}<br>실행: ${esc(t.run.status)}${t.run.why ? ' · ' + esc(t.run.why) : ''}${t.run.seconds != null ? ` (${t.run.seconds}초 / 한도 ${t.run.time_limit}초)` : ''}
        <br>입력 자료: ${t.inputs.length ? t.inputs.map(i => esc(i.name) + ' ' + esc(i.sha256)).join(', ') : '없음'} · 기반 모델: ${esc(t.base_model)}
        <br>결과: 파일 ${t.result.files}개${t.result.adapter_files.length ? ' · 어댑터 ' + esc(t.result.adapter_files.join(', ')) : ''}
        <br>평가: 학습 스크립트 자체 지표 ${esc(t.evaluation.self_reported_metrics ? JSON.stringify(t.evaluation.self_reported_metrics).slice(0, 200) : '없음')} · 독립 검증 ${esc(t.evaluation.independent_verification)}
        <br>Owner에게 전달: ${esc(t.delivered)}
        <br>실행에 사용: 검증 실행 ${t.used.verification_runs}회 · Owner 실행 ${t.used.owner_runs}회 <span class="muted">(${esc(t.used.note)})</span>
        <br>평가에서 효과 확인: ${esc(t.effect)}</div>`).join('') || '<div class="muted">아직 학습 실행 기록이 없습니다. 결과물이 모델 학습을 요구하면 여기에 실행·결과·전달·사용·효과 확인이 따로 기록됩니다.</div>')
      + `<h3>개선 후보 (${d.candidates.length})</h3><div class="muted">평가용 프로젝트는 업무 목록에 나오지 않고 아래 각 후보에서 열 수 있습니다. 기록은 모두 보존됩니다.</div>`
      + (d.candidates.map(c => `<div class="item"><h4>${esc(c.id)} <span class="tag">${esc(c.label)}</span></h4>
        <div class="kv">반복 실패: <code>${esc(c.signature)}</code><br>근거: ${c.evidence.map(e => esc(e.project)).join(', ')} (${c.evidence.length}건) · 갱신 ${esc(when(c.updated))}</div>
        <div class="kv">개선안: ${c.proposal ? esc(c.proposal.rule) + `<br><span class="muted">${esc(c.proposal.origin)}</span>` : '아직 없음 — 같은 실패가 해결된 기록이 생기면 자동으로 붙습니다.'}</div>`
        + (c.eval ? `<div class="kv">평가: 원래 업무 ${c.eval.cases.length}건 × (기준·개선안) · 경험 검색 꺼짐 · 최대 ${Number(c.eval.max_tokens_total).toLocaleString()} 토큰${(c.eval.projects || []).length ? '<br>평가 프로젝트: ' + c.eval.projects.map(p => `<a href="#" data-proj="${esc(p.project)}">${esc(p.project)}</a>(${p.arm === 'variant' ? '개선안' : '기준'} · ${esc(p.state || '')}${p.last_verdict ? ' · 검증 ' + esc(p.last_verdict) : ''})`).join(' ') : ''}</div>` : '')
        + (c.comparison ? `<div class="kv">비교 결과 — 기준: ${arm(c.comparison.baseline)} / 개선안: ${arm(c.comparison.variant)}<br><b>${c.comparison.not_worse ? (c.comparison.better ? '개선안이 더 나았음' : '개선안이 나쁘지 않았음') : '개선안이 더 나빴음'}</b> · <span class="muted">${esc(c.comparison.limits)}</span></div>` : '')
        + `<div class="row">${improvementButtons(c)}</div>`
        + `<details><summary>상태 기록</summary>${(c.history || []).map(h => `<div class="muted">${esc(when(h.at))} ${esc(h.from)} → ${esc(h.to)} · ${esc(h.what)} · ${esc(h.by)}</div>`).join('')}</details></div>`).join('')
        || '<div class="muted">아직 개선 후보가 없습니다. 같은 원인의 검증 실패가 연속으로 기록되면 근거와 함께 자동 등록됩니다.</div>');
    box.querySelectorAll('[data-proj]').forEach(a => a.onclick = e => { e.preventDefault(); openProject(a.dataset.proj); });
    box.querySelectorAll('[data-imp]').forEach(b => b.onclick = () => improvementAction(b.dataset.imp, b.dataset.act, b));
  }
  function improvementButtons(c) {
    const b = (act, label, cls = 'ghost') => `<button class="${cls}" data-imp="${esc(c.id)}" data-act="${act}">${label}</button>`;
    return {CANDIDATE: (c.proposal ? b('prepare', '평가 준비', 'primary') : '') + b('reject', '거절'),
            EVAL_READY: b('evaluate', '평가 실행 승인 (실제 모델 호출)', 'primary') + b('reject', '거절'),
            EVALUATING: '<span class="muted">평가 프로젝트가 끝나면 비교 결과가 자동 기록됩니다.</span>',
            COMPARED: (c.comparison && c.comparison.not_worse ? b('approve', '운영 규칙에 적용 승인', 'primary') : '') + b('reject', '거절'),
            APPLIED: b('rollback', '되돌리기')}[c.state] || '';
  }
  async function improvementAction(cid, act, button) {
    const body = {};
    if (act === 'evaluate') {
      if (!window.confirm('원래 업무를 기준·개선안으로 새로 실행해 비교합니다. 실제 모델을 호출하며 토큰을 사용합니다. 승인할까요?')) return;
      body.approve = true;
    }
    if (act === 'reject') { body.why = window.prompt('거절 이유 (기록됩니다)') || ''; }
    button.disabled = true;
    try { await api(`improvement/${cid}/${act}`, body); notice({prepare: '평가를 준비했습니다.', evaluate: '평가 프로젝트를 시작했습니다.', approve: '적용했습니다. 다음 계획·전략부터 청월에게 참고로 전달됩니다.', rollback: '되돌렸습니다. 다음 계획부터 전달하지 않습니다.', reject: '거절했습니다.'}[act]); await loadImprovements(); }
    catch (e) { fail(e); button.disabled = false; }
  }

  async function loadRecords() {
    if (!S.stageKey) return;
    const pid = S.pid, key = S.stageKey, navigation = S.navigation;
    try {
      const r = await api(`project/${pid}/records?key=${encodeURIComponent(key)}`);
      if (pid !== S.pid || key !== S.stageKey || navigation !== S.navigation || S.view !== 'project') return;
      const text = Array.isArray(r.records) ? r.records.join('\n') : String(r.records);
      $('#records').innerHTML = `<pre>${esc(text)}</pre>`;
    } catch (e) { fail(e); }
  }
  function renderOwner(p) {
    const box = $('#owner'), mode = p.owner.mode;
    const revision = JSON.stringify([p.id, mode, p.iteration, p.owner.note]);
    if (!mode) { box.hidden = true; box.dataset.mode = ''; box.innerHTML = ''; return; }
    box.hidden = false;
    if (box.dataset.mode === revision) return;   // keep typing only for this project's decision
    saveOwnerDraft(); box.dataset.mode = revision;
    const navigation = S.navigation;
    const current = () => S.pid === p.id && S.navigation === navigation && box.dataset.mode === revision && S.view === 'project';
    const send = (action, body) => current() ? act(action, body, p.id) : Promise.resolve();
    const restore = () => {
      const d = S.ownerDrafts[revision]; if (!d) return;
      ($('#oText') || $('#oNote')).value = d.text;
      box.querySelectorAll('input[name=works]').forEach(w => { w.checked = w.value === d.works; });
    };
    if (mode === 'approval') {
      box.innerHTML = `<h3>승인 필요</h3><p>${esc(p.owner.note)}</p><textarea id="oNote" placeholder="거절할 때 淸月 CEO에게 줄 안내 (선택)"></textarea>
        <div class="row"><button class="primary" id="oYes">외부 연결 승인</button><button class="ghost" id="oNo">거절</button></div>`;
      $('#oYes').onclick = () => send('network', {approve: true});
      $('#oNo').onclick = () => current() && send('network', {approve: false, note: $('#oNote').value});
      restore();
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
    if (review) $('#oRun').onclick = () => current() && runResult(p.id);
    $('#oSend').onclick = () => {
      if (!current()) return;
      const w = document.querySelector('input[name=works]:checked'), works = w ? w.value : 'unknown', text = $('#oText').value.trim();
      if (review && works === 'unknown' && !text) return notice('바꾸고 싶은 점을 적거나, 작동 여부를 선택해 주세요.');
      send('review', {works, text}).then(() => {
        delete S.ownerDrafts[revision];
        if (current()) { box.dataset.mode = ''; refreshProject(); }
      }).catch(() => {});
    };
    $('#oFinish').onclick = () => current() && finishDialog(p.id);
    restore();
  }
  async function act(action, body, pid = S.pid) {
    try { await api(`project/${pid}/${action}`, body || {}); if (pid === S.pid) await refreshProject(); refreshOverview().catch(() => {}); }
    catch (e) { fail(e); throw e; }
  }
  async function runResult(pid = S.pid) {
    const navigation = S.navigation, view = S.view, request = S.resultRequest = (S.resultRequest || 0) + 1;
    try {
      const r = await api(`project/${pid}/result`, {});
      if ((view === 'project' && pid !== S.pid) || navigation !== S.navigation || S.view !== view || request !== S.resultRequest) return;
      if (r.how === 'web') { showWebRun(pid, r); await refreshProject(); }
      else if (r.text !== undefined) { $('#modalBody').innerHTML = `<h3>${esc(r.title)}</h3><div class="result"><pre>${esc(r.text)}</pre></div>`; $('#modal').showModal(); }
      else notice(`${r.how === 'run' ? '실행함' : '열었음'}: ${r.path} (검증된 버전)`);
    } catch (e) { fail(e); }
  }
  // A web result runs isolated on its OWN port (another browser origin): the link opens it in a new tab without a
  // reference back to this page (noopener noreferrer), so the result's code cannot reach AX Branch's window or token.
  // Every action carries the project id it was rendered for; a click after switching projects never acts on another.
  function webRunLink(r, id = '') {
    return `<a class="primary-link web-run-link"${id ? ` id="${id}"` : ''} href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">결과 웹앱 열기 (v${esc(r.version)})</a>`;
  }
  function savedText(s) {
    if (!s) return '아직 저장된 데이터가 없습니다.';
    return `마지막 정상 저장: ${esc(s.saved_at)} (데이터 ${esc(s.data_version)}번째 저장, 파일 ${esc(s.files)}개${s.code_iteration ? `, v${esc(s.code_iteration)}에서 저장` : ''})`;
  }
  function webRunDetails(r) {
    const restored = r.restored
      ? `이번 실행은 ${r.restored.from_project ? `원본 결과물(${esc(r.restored.from_project)})에서 ` : ''}${esc(r.restored.saved_at)}에 저장한 데이터(v${esc(r.restored.code_iteration)}, 파일 ${esc(r.restored.files)}개)를 복원해 시작했습니다.${r.restored.from_project ? ' 원본의 데이터는 바꾸지 않으며, 이제부터는 이 프로젝트에 따로 저장됩니다.' : ''}`
      : (r.choice === 'empty' ? '빈 데이터로 시작했습니다(저장된 데이터는 그대로 보존).' : '복원할 저장 데이터가 없어 처음 상태로 시작했습니다.');
    if (r.data_kept === false) return `<div class="kv">사용 중인 결과: <b>v${esc(r.version)}</b></div>
      <div class="kv" role="status">이 결과에는 데이터 저장 명세가 없어, 입력한 데이터는 종료하면 남지 않습니다. 같은 프로젝트에 "입력한 데이터가 다음에도 남게 해 달라"고 수정 요청을 보내면 저장·복원되는 버전이 만들어집니다.</div>
      <div class="muted">${esc(r.protection || '')}.</div>`;
    return `<div class="kv">사용 중인 결과: <b>v${esc(r.version)}</b>${r.choice === 'previous' ? ' (이전 버전을 선택해 실행)' : ''}</div>
      <div class="kv">${restored}</div>
      <div class="kv">${savedText(r.last_saved)} · 실행 중에는 ${Math.round((r.save_interval_seconds || 60))}초마다 바뀐 데이터를 자동 저장합니다.</div>
      ${r.save_error ? `<div class="kv" role="alert">저장 실패(${esc(r.save_error.at)}): ${esc(r.save_error.reason)} — 마지막 정상 데이터는 그대로입니다. 프로그램에서 저장을 마친 뒤 [지금 저장]을 다시 누르세요.</div>` : ''}
      <div class="muted">${esc(r.protection || '')}. 다른 프로젝트·사용자 파일·인터넷에 접근할 수 없습니다. 최대 ${Math.round((r.lifetime_seconds || 0) / 3600)}시간 뒤 저장 후 자동 종료됩니다.</div>`;
  }
  function webRunButtons(pid, r) {
    if (r && r.data_kept === false) return `<button class="ghost" data-webrun="stop" data-pid="${esc(pid)}">종료</button>`;
    return `<button class="ghost" data-webrun="save" data-pid="${esc(pid)}">지금 저장</button><button class="ghost" data-webrun="stop" data-pid="${esc(pid)}">저장하고 종료</button>`;
  }
  function bindWebRun(scope) {
    scope.querySelectorAll('[data-webrun]').forEach(b => b.onclick = () => webRunAction(b.dataset.pid, b.dataset.webrun, b));
  }
  async function webRunAction(pid, what, button) {
    if (S.webRunBusy) return;                       // one action at a time (double clicks)
    S.webRunBusy = true; if (button) button.disabled = true;
    try {
      const r = await api(`project/${pid}/result-${what}`, {});
      notice(what === 'save' ? savedText(r.last_saved) : `결과 웹앱을 종료했습니다. ${savedText(r.last_saved)} 프로세스와 임시 권한을 정리했습니다.`);
      if (what === 'stop' && $('#modal').open) $('#modal').close();
    } catch (e) { fail(e); }
    finally { S.webRunBusy = false; if (button) button.disabled = false; if (pid === S.pid) await refreshProject(); }
  }
  function showWebRun(pid, r) {
    if (r.incompatible) return showIncompatible(pid, r);
    $('#modalBody').innerHTML = `<h3>결과 웹앱 실행 중</h3><p>${webRunLink(r, 'webRunOpen')}</p>${webRunDetails(r)}
      <div class="row end">${webRunButtons(pid, r)}</div>`;
    $('#modal').showModal();
    bindWebRun($('#modalBody'));
  }
  function showIncompatible(pid, r) {
    $('#modalBody').innerHTML = `<h3>저장 데이터와 맞지 않는 버전입니다</h3><p>${esc(r.reason)}</p>
      <p>저장된 데이터는 바꾸거나 지우지 않았습니다. 어떻게 열지 선택하세요.</p>
      <div class="row">${(r.options || []).map(o => `<button class="ghost" data-choice="${esc(o.choice)}">${esc(o.label)}</button>`).join('')}${r.origin_project ? `<button class="ghost" id="openOrigin">원본 결과물(${esc(r.origin_project)})을 데이터와 함께 열기</button>` : ''}</div>
      <div class="muted">또는 같은 프로젝트에 "기존 데이터 형식을 읽을 수 있게 해 달라"고 수정 요청을 보낼 수 있습니다.</div>`;
    $('#modal').showModal();
    if (r.origin_project) $('#openOrigin').onclick = async () => { $('#modal').close(); await openProject(r.origin_project); runResult(r.origin_project); };
    $('#modalBody').querySelectorAll('[data-choice]').forEach(b => b.onclick = async () => {
      if (S.webRunBusy) return; S.webRunBusy = true; b.disabled = true;
      try { const again = await api(`project/${pid}/result`, {choice: b.dataset.choice}); showWebRun(pid, again); }
      catch (e) { fail(e); } finally { S.webRunBusy = false; if (pid === S.pid) await refreshProject(); }
    });
  }
  function renderWebRun(run) {
    const box = $('#webRun');
    const pid = S.pid;
    box.hidden = !run || (!run.running && !run.last_saved);
    if (box.hidden) return;
    box.innerHTML = run.running
      ? `<div class="row"><b>결과 웹앱 실행 중</b><span class="grow"></span>${webRunLink(run)}</div>${webRunDetails(run)}<div class="row end">${webRunButtons(pid, run)}</div>`
      : `<div class="row"><b>결과 웹앱 · 꺼져 있음</b></div><div class="kv">${savedText(run.last_saved)} [결과 보기]를 누르면 이 데이터를 복원해 다시 엽니다.</div>`;
    bindWebRun(box);
  }
  async function finishDialog(pid = S.pid) {
    const navigation = S.navigation;
    try { await api(`project/${pid}/close`, {}); } catch (e) { return fail(e); }
    if (pid !== S.pid || navigation !== S.navigation || S.view !== 'project') return;
    $('#modalBody').innerHTML = `<h3>淸月 AI CEO</h3><p>프로젝트를 마칩니다. 이 프로젝트의 지식을 저장할까요?</p>
      <div class="row">만족도(%) <input id="cSat" type="number" min="0" max="100" value="90" style="width:70px"> 이유(선택) <input id="cWhy" style="flex:1"></div>
      <div class="row"><button class="primary" data-c="save">A. 저장하고 닫기</button><button class="ghost" data-c="pause">B. 일시중지</button><button class="ghost" data-c="discard">C. 저장하지 않고 닫기</button></div>`;
    const m = $('#modal'); m.showModal();
    m.querySelectorAll('[data-c]').forEach(b => b.onclick = async () => {
      const choice = b.dataset.c; let confirm = false;
      if (choice === 'discard' && !(confirm = window.confirm('저장하지 않고 닫으면 이 프로젝트의 지식과 Agent 컨텍스트가 영구히 버려집니다. 계속할까요?'))) return;
      if (pid !== S.pid || navigation !== S.navigation || S.view !== 'project') return;
      m.close(); act('close', {choice, confirm, satisfaction: Number($('#cSat').value), why: $('#cWhy').value}, pid).catch(() => {});
    });
  }
  $('#resume').onclick = () => act('resume').catch(() => {});
  $('#stop').onclick = () => act('stop').catch(() => {});

  // ---- artifact library + 이어서 개발 (engine.develop through the API) ----
  async function loadLibrary() {
    const lib = await api('library'), box = $('#libraryList');
    const when = t => t ? new Date(t * 1000).toLocaleString() : '';
    box.innerHTML = lib.types.map(type => {
      const group = lib.entries.filter(e => e.type === type);
      if (!group.length) return '';
      return `<h3>${esc(type)} (${group.length})</h3>` + group.map(e => `<div class="item"><h4>${esc(e.title)} <span class="tag">v${esc(e.version)}</span> <span class="tag">검증 ${esc(e.verification)}</span></h4>
        <div class="kv">업데이트 ${esc(when(e.updated))} · 버전 ${e.versions.map(v => `v${esc(v.version)}`).join(', ')}</div>
        <div class="row"><button class="ghost" data-open="${esc(e.project)}">${e.type === 'Apps' ? '실행' : '보기'}</button>
        <button class="primary" data-dev="${esc(e.project)}" data-title="${esc(e.title)}" data-v="${esc(e.version)}">이어서 개발</button>
        <button class="ghost" data-proj="${esc(e.project)}">관련 프로젝트</button></div></div>`).join('');
    }).join('') || '<div class="muted">아직 완료된 결과물이 없습니다.</div>';
    box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => runResult(b.dataset.open));
    box.querySelectorAll('[data-proj]').forEach(b => b.onclick = () => openProject(b.dataset.proj));
    box.querySelectorAll('[data-dev]').forEach(b => b.onclick = () => developDialog(b.dataset.dev, b.dataset.title, b.dataset.v));
  }
  function developDialog(base, title, version) {
    const rid = crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);
    $('#modalBody').innerHTML = `<h3>이어서 개발 — ${esc(title)} v${esc(version)}</h3>
      <p class="muted">이 결과물의 현재 버전을 바탕으로 새 프로젝트를 만듭니다. 이어서 할 일만 적어 주세요.</p>
      <textarea id="devGoal" rows="5"></textarea><div class="row end"><button class="primary" id="devGo">淸月 CEO에게 맡기기</button></div>`;
    const m = $('#modal'); m.showModal();
    $('#devGo').onclick = async () => {
      const goal = $('#devGoal').value.trim(); if (!goal) return;
      $('#devGo').disabled = true;
      try { const r = await api('develop', {base, goal, request_id: rid}); m.close(); await refreshOverview(); openProject(r.id); }
      catch (e) { fail(e); $('#devGo').disabled = false; }
    };
  }

  // ---- feeds ----
  async function loadFeeds(target) {
    const data = await api('feeds');
    const when = stamp => new Date(stamp * 1000).toLocaleString();
    const host = url => { try { return new URL(url).hostname; } catch (e) { return '출처 미상'; } };
    const render = cat => {
      const c = data[cat] || {}, stale = c.fetched && Date.now() / 1000 - c.fetched > 86400;
      const items = (c.items || []).slice().sort((a, b) => (b.published || 0) - (a.published || 0)).slice(0, target ? 30 : 3);
      return `<h3>${esc(cat)}</h3><div class="muted">출처: ${esc(c.source ? host(c.source) : '출처 미상')} · ${c.fetched ? '마지막 성공 수집: ' + esc(when(c.fetched)) : '수집 전'}</div>`
        + (stale ? '<div class="muted">오래된 정보 (24시간 초과) — 새로 수집하세요.</div>' : '')
        + (c.error ? `<div class="feed-error" role="status">갱신 실패: ${esc(c.error)}${items.length ? ' · 이전 수집 자료를 표시합니다.' : ''}</div>` : '')
        + (items.map(i => `<div class="feed-item"><a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a><div class="muted">${esc(host(i.url))} · ${i.published ? '게시: ' + esc(when(i.published)) : '게시일 미상'}</div><div class="muted">${esc(i.summary)}</div></div>`).join('')
          || '<div class="muted">아직 수집한 자료가 없습니다. [공개 정보 새로 수집]을 누르세요.</div>');
    };
    if (target) $('#feedFull').innerHTML = render(target);
    else { document.getElementById('feed-AI 동향').innerHTML = render('AI 동향'); document.getElementById('feed-AI 취업').innerHTML = render('AI 취업'); }
  }
  $('#refreshFeeds').onclick = async (ev) => { ev.preventDefault(); ev.stopPropagation(); notice('공개 출처에서 수집 중… (AI 호출 없음)', 0); try { await api('feeds/refresh', {}); notice('수집 결과를 확인하세요. 일부 출처만 포함하며 전체 시장 목록은 아닙니다.'); loadFeeds(); } catch (e) { fail(e); } };

  // ---- settings ----
  for (const id of ['motionOff', 'lowPower']) $('#' + id).onchange = async () => {
    try { S.ov.settings = await api('settings', {motion_off: $('#motionOff').checked, low_power: $('#lowPower').checked}); updateOrb(); } catch (e) { fail(e); }
  };

  // ---- views ----
  function show(view) {
    S.view = view.split(':')[0];
    for (const v of ['home', 'feed', 'project', 'devroom', 'library', 'improve']) $('#view-' + v).hidden = v !== S.view;
    document.querySelectorAll('.nav').forEach(b => b.classList.toggle('on', b.dataset.view === view));
    if (S.view === 'home') { $('#crumb').textContent = '워크스페이스 / 청월 홈'; loadFeeds().catch(() => {}); orb.wake(); }
    if (S.view === 'feed') { $('#crumb').textContent = '워크스페이스 / ' + view.split(':')[1]; loadFeeds(view.split(':')[1]).catch(fail); }
    if (S.view === 'library') { $('#crumb').textContent = '워크스페이스 / 결과물 라이브러리'; loadLibrary().catch(fail); }
    if (S.view === 'improve') { $('#crumb').textContent = '워크스페이스 / 개선 후보 · 학습'; loadImprovements().catch(fail); }
    if (S.view === 'devroom') { $('#crumb').textContent = '오너 개발실 — AX Branch 자체의 개발 현황 (사용자 업무 프로젝트 아님)'; window.AXDev && window.AXDev.render().catch(fail); }
  }
  document.querySelectorAll('.nav').forEach(b => b.onclick = () => show(b.dataset.view));
  $('#newWork').onclick = () => { show('home'); goal.focus(); };
  window.AXB.show = show; window.AXB.api = api; window.AXB.notice = notice; window.AXB.esc = esc;
  window.AXB.openProject = openProject;

  // ---- polling (stops while the tab is hidden; reading never starts work) ----
  async function tick() {
    if (document.hidden) return;
    try { await refreshOverview(); if (S.view === 'project') await refreshProject(); } catch (e) { /* server gone: keep the page */ }
  }
  setInterval(tick, 2000);
  refreshOverview().then(async () => {
    const start = decodeURIComponent((location.hash || '').slice(1));   // e.g. #devroom, #library (read-only views)
    show(['library', 'devroom', 'improve'].includes(start) ? start : 'home');
    if (submission) await recoverSubmission();
    const q = new URLSearchParams(location.search);
    if (S.ov.test_mode && q.has('selftest')) { const s = document.createElement('script'); s.src = '/selftest.js'; document.body.appendChild(s); }
    if (S.ov.test_mode && q.has('perf')) setInterval(() => api('test/perf', Object.assign({at: Date.now(), state: orb.state, low: orb.low}, orb.stats)).catch(() => {}), 3000);
  }).catch(fail);
  const ds = document.createElement('script'); ds.src = '/devroom.js'; document.body.appendChild(ds);
})();
