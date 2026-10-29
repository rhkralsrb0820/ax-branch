// 오너 개발실: AX Branch's OWN development status (not user projects), read from docs/devroom/status.json, which the
// developer updates at each work unit. No model call, nothing sent or started automatically. Owner memos live in the
// workspace and survive status updates. "개발 중" is the last development report, never a live process.
(function () {
  const {api, esc, notice} = window.AXB;
  let D = null, tab = null, selArea = null;
  const picked = new Set();
  const list = a => (a && a.length) ? '<ul>' + a.map(x => `<li>${esc(x)}</li>`).join('') + '</ul>' : '<span class="muted">없음</span>';
  const evid = e => (e && e.length) ? `<details class="evidence"><summary>근거 보기</summary>${list(e)}</details>` : '';
  const pick = id => `<label class="pick"><input type="checkbox" data-pick="${esc(id)}" ${picked.has(id) ? 'checked' : ''}> 개발 요청에 담기</label>`;

  function firstScreen(s) {
    const cw = s.current_work, top = s.next[0], rest = s.next.slice(1);
    const src = p => p.source === 'owner' ? '확정된 Owner 지시' : '개발자 제안';
    return `
    <div class="dev">
    <section class="dcard"><h2>1. 지금 어디까지 됐나</h2><p class="lead">${esc(s.now.can_do)}</p>
      ${features(s.features || [])}
      <h4>핵심 제한</h4>${list(s.now.limits)}
      <div class="meta">현황 갱신 ${esc(s.updated_at)} · 기준 소스 커밋 ${esc(s.commit)} · 현재 사용 서버 ${esc(s.serving_build || '기록 없음')} · 후보 빌드 ${esc(s.candidate_build || '없음')} · 지금 화면의 코드 ${esc(D.running.code)}</div></section>
    <section class="dcard"><h2>2. 지금 무엇을 하고 있나</h2>${cw && cw.state === '개발 중'
      ? `<p class="lead"><b>${esc(cw.title)}</b></p><p>왜: ${esc(cw.why)}</p><p>끝나면: ${esc(cw.after)}</p><div class="meta">${esc(cw.basis)}</div>`
      : `<p class="lead">진행 중으로 보고된 작업이 없습니다.</p><div class="meta">마지막 개발 보고 ${esc(s.updated_at)} (기준 소스 커밋 ${esc(s.commit)}) — 실시간 상태가 아닙니다.</div>`}</section>
    <section class="dcard recommendation"><h2>3. 다음에 무엇을 고쳐야 하나</h2>${top ? `
      <div class="badge">${src(top)}</div><p class="lead"><b>${esc(top.title)}</b></p>
      <p><b>왜 먼저:</b> ${esc(top.why)}</p><p><b>나아지는 점:</b> ${esc(top.improves)}</p><p><b>완료 기준:</b> ${esc(top.done_when)}</p>
      <p><b>비용·권한 승인:</b> ${esc(top.approval)}</p>
      <div class="row"><button class="primary" id="copyTop">다음 개발 요청 복사</button></div>${evid(top.evidence)}
      ${rest.length ? `<details class="later"><summary>후속 작업 ${rest.length}개 보기</summary>${rest.map(p => `<div class="sub"><b>${esc(p.title)}</b> <span class="badge">${src(p)}</span>
        <div>왜: ${esc(p.why)}</div><div>완료 기준: ${esc(p.done_when)}</div><div>승인: ${esc(p.approval)}</div>${pick('proposal:' + p.id)}</div>`).join('')}</details>` : ''}`
      : '<p>추천 작업 없음</p>'}</section>
    <section class="dcard"><h2>4. 내가 지금 해야 할 일</h2>${s.owner_todo.length ? s.owner_todo.map(t => `<div class="sub"><p class="lead"><b>${esc(t.action)}</b></p>
      <p>이유: ${esc(t.why)}</p><details><summary>확인 방법 보기</summary><p>${esc(t.how)}</p></details></div>`).join('') : '<p class="lead">지금 Owner가 할 일은 없습니다.</p>'}</section>
    <section class="dcard"><h2>5. 최근 달라진 점</h2>${s.recent.slice(0, 3).map(r => `<div class="sub"><b>${esc(r.title)}</b> — ${esc(r.change)}
      <div class="meta">확인 수준: ${esc(r.level)}</div></div>`).join('')}</section>
    </div>`;
  }

  // 🟢 = implemented ONLY. Verification level and where it is applied are separate columns, never implied by the icon.
  const IMPL = {'구현됨': '🟢', '일부 구현': '🟡', '미구현': '⚪'};
  const LEVELS = ['자동 테스트', '실제 실행', 'Owner 확인'], PLACES = ['개발 소스', '후보 빌드', '현재 사용 서버'];
  const marks = (have, all) => all.map(x => `<span class="${(have || []).includes(x) ? 'yes' : 'no'}">${(have || []).includes(x) ? '✔' : '–'} ${esc(x)}</span>`).join(' ');
  function features(fs) {
    if (!fs.length) return '';
    return `<table class="tbl features"><tr><th>기능</th><th>구현 상태</th><th>확인 수준</th><th>적용 위치</th><th>남은 개발 · 다음 행동</th></tr>${fs.map(f => `<tr>
      <td><b>${esc(f.title)}</b>${f.note ? `<div class="muted">${esc(f.note)}</div>` : ''}</td>
      <td>${IMPL[f.impl] || ''} ${esc(f.impl)}</td><td>${marks(f.verified, LEVELS)}</td><td>${marks(f.location, PLACES)}</td>
      <td>${esc(f.remaining || '-')}${f.next ? `<div class="muted">다음: ${esc(f.next)}</div>` : ''}${evid(f.evidence)}</td></tr>`).join('')}</table>
      <div class="muted">🟢 구현됨 · 🟡 일부 구현 · ⚪ 미구현. 🟢는 구현됐다는 뜻만 있으며, 검증 완료나 현재 서버 적용은 옆 칸에서 따로 표시합니다.</div>`;
  }

  function issueCard(i) {
    const dev = i.owner === '개발 담당' && i.category !== '해결·과거 기록';
    const det = i.detail || {};
    return `<div class="issue"><h4>${esc(i.title)}</h4><p>${esc(i.impact)}</p>
      <div class="facts"><span><b>상태</b> ${esc(i.status)}</span><span><b>우선순위</b> ${esc(i.priority)}</span><span><b>담당</b> ${esc(i.owner)}</span><span><b>마지막 확인</b> ${esc(i.checked || '현재 상태 재확인 필요')}</span></div>
      <p><b>다음 조치:</b> ${esc(i.next)}</p>
      ${i.how_to_check ? `<details><summary>확인 방법 보기</summary><p>${esc(i.how_to_check)}</p></details>` : ''}
      <details class="evidence"><summary>상세 및 근거</summary>
        ${det.solved ? `<p>해결된 범위: ${esc(det.solved)}</p>` : ''}${det.remaining ? `<p>남은 제한: ${esc(det.remaining)}</p>` : ''}
        ${det.repro ? `<p>재현·확인: ${esc(det.repro)}</p>` : ''}${list(det.evidence)}
        <div class="meta">변경 이력: ${(i.history || []).map(h => `${esc(h.date)} ${esc(h.change)}`).join(' → ')}</div></details>
      ${dev ? pick('issue:' + i.id) : ''}</div>`;
  }

  function details(s) {
    const tabs = [['map', 'AX Branch 구조 지도'], ['items', '전체 개발 목록'], ['tests', '테스트와 실행 근거'], ['issues', '알려진 문제와 미구현'], ['log', '변경 이력'], ['notes', 'Owner 메모']];
    let body = '';
    if (tab === 'map') {
      const a = selArea && s.areas.find(x => x.id === selArea);
      body = `<div class="dev-grid"><div class="map">${s.areas.map(x => `<button class="lv${x.level} ${x.id === selArea ? 'on' : ''}" data-area="${esc(x.id)}">${esc(x.name)}</button>`).join('')}</div>
        <div>${a ? `<h3>${esc(a.name)}</h3><p>${esc(a.role)}</p><h4>되는 것</h4>${list(a.implemented)}<h4>안 되는 것</h4>${list(a.missing)}${evid(a.evidence)}` : '<p class="muted">영역을 선택하세요.</p>'}</div></div>`;
    } else if (tab === 'items') {
      body = s.items.map(i => `<div class="issue"><h4>${esc(i.title)}</h4><div class="facts"><span><b>구현</b> ${esc(i.impl)}</span><span><b>검증</b> ${esc(i.verify)}</span></div>
        <p>${esc(i.solves)}</p><p><b>남은 한계:</b> ${esc((i.limits || []).join(' / ') || '없음')}</p><p><b>완료 조건:</b> ${esc(i.done_when)}</p>
        <details class="evidence"><summary>근거 보기</summary><p>범위: ${esc(i.scope)}</p><p>자동 테스트: ${esc(i.auto || '-')}</p><p>실제 모델 E2E: ${esc(i.e2e || '-')}</p>
        <p>검증 버전: ${esc(i.verified_at || '현재 상태 재확인 필요')}</p>${list(i.evidence)}</details>${pick('item:' + i.id)}</div>`).join('');
    } else if (tab === 'tests') {
      body = `<p class="muted">자동 테스트(모델 없음)와 실제 모델 E2E는 따로 표시합니다. 과거 버전의 결과는 그 버전 표시와 함께만 보여 줍니다.</p>
        <table class="tbl"><tr><th>항목</th><th>자동 테스트</th><th>실제 모델 E2E</th><th>확인 버전</th></tr>${s.items.map(i =>
        `<tr><td>${esc(i.title)}</td><td>${esc(i.auto || '-')}</td><td>${esc(i.e2e || '-')}</td><td>${esc(i.verified_at || '재확인 필요')}</td></tr>`).join('')}</table>`;
    } else if (tab === 'issues') {
      const group = (c, open) => { const g = s.issues.filter(i => i.category === c); return `<details ${open ? 'open' : ''} class="group"><summary>${esc(c)} (${g.length})</summary>${g.map(issueCard).join('') || '<p class="muted">없음</p>'}</details>`; };
      body = group('현재 문제', true) + group('Owner 확인', true) + group('해결·과거 기록', false);
    } else if (tab === 'log') {
      body = s.changelog.map(c => `<div class="sub"><b>${esc(c.date)} · v${esc(c.version)}</b> — ${esc(c.summary)}</div>`).join('');
    } else if (tab === 'notes') {
      body = `<div id="notes">${D.notes.map((n, k) => `<div class="sub"><div class="meta">${esc(n.at ? new Date(n.at).toLocaleString() : '')}</div><div>${esc(n.text)}</div>
        <button class="ghost" data-del="${k}">삭제</button> ${pick('note:' + k)}</div>`).join('') || '<p class="muted">메모 없음</p>'}</div>
        <textarea id="noteText" placeholder="원하는 변경·피드백을 적어 주세요 (현황 갱신으로 덮어쓰지 않습니다)"></textarea>
        <div class="row"><button class="ghost" id="noteAdd">메모 저장</button></div>`;
    }
    return `<section class="dcard"><h2>상세 정보</h2><div class="tabs">${tabs.map(([k, l]) => `<button class="${tab === k ? 'on' : ''}" data-tab="${k}">${l}</button>`).join('')}</div>${body}
      <div class="row"><span class="grow"></span><button class="ghost" id="copyReq">고른 항목으로 개발 요청 복사</button></div>
      <textarea id="reqText" class="copybox" readonly placeholder="복사된 요청 문구가 여기에도 표시됩니다. Codex와 검토한 뒤 Claude에 전달하세요. 자동 전송하지 않습니다."></textarea></section>`;
  }

  async function render() {
    D = await api('devroom');
    const s = D.status, el = document.getElementById('view-devroom');
    if (s.error || s.schema !== 2) { el.innerHTML = `<div class="card">${esc(s.error || '현황 기록 형식이 다릅니다 (재확인 필요).')}</div>`; return; }
    el.innerHTML = firstScreen(s) + details(s);
    el.querySelectorAll('[data-area]').forEach(b => b.onclick = () => { selArea = b.dataset.area; render(); });
    el.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { tab = tab === b.dataset.tab ? null : b.dataset.tab; render(); });
    el.querySelectorAll('[data-pick]').forEach(c => c.onchange = () => { c.checked ? picked.add(c.dataset.pick) : picked.delete(c.dataset.pick); });
    el.querySelectorAll('[data-del]').forEach(b => b.onclick = () => saveNotes(D.notes.filter((_, k) => k !== Number(b.dataset.del))));
    const add = document.getElementById('noteAdd');
    if (add) add.onclick = () => { const t = document.getElementById('noteText').value.trim(); if (t) saveNotes(D.notes.concat([{id: String(Date.now()), text: t, at: Date.now()}])); };
    const top = document.getElementById('copyTop');
    if (top) top.onclick = () => copy(['proposal:' + s.next[0].id]);
    document.getElementById('copyReq').onclick = () => picked.size ? copy([...picked]) : notice("'개발 요청에 담기'로 항목을 먼저 고르세요.");
  }
  async function saveNotes(notes) { try { await api('devroom/notes', {notes}); await render(); notice('메모를 저장했습니다.'); } catch (e) { notice(String(e.message)); } }

  function requestText(keys) {
    const s = D.status, out = ['[AX Branch 다음 개발 요청]', `현재 버전: v${s.version} · ${s.branch} · 커밋 ${s.commit} (현황 갱신 ${s.updated_at})`, ''];
    for (const key of keys) {
      const [kind, id] = key.split(':');
      if (kind === 'proposal') { const p = s.next.find(x => x.id === id); if (p) out.push(`■ ${p.title} (${p.source === 'owner' ? '확정된 Owner 지시' : '개발자 제안'})`, `- 문제: ${p.why}`, `- 요청 범위: ${p.scope}`, `- 완료 기준: ${p.done_when}`, `- 검증: ${p.verify}`, `- 비용·권한: ${p.approval}`, `- 근거: ${(p.evidence || []).join(', ') || '-'}`, ''); }
      if (kind === 'item') { const i = s.items.find(x => x.id === id); if (i) out.push(`■ ${i.title} [구현: ${i.impl} / 검증: ${i.verify}]`, `- 문제: ${(i.limits || []).join(' / ') || i.solves}`, `- 요청 범위: ${i.scope}`, `- 완료 기준: ${i.done_when}`, `- 근거: ${(i.evidence || []).join(', ') || '-'}`, ''); }
      if (kind === 'issue') { const i = s.issues.find(x => x.id === id); if (i) out.push(`■ 문제: ${i.title} [${i.status}, 우선순위 ${i.priority}]`, `- 영향: ${i.impact}`, `- 요청 범위: ${i.next}`, `- 완료 기준: 원인과 조치가 근거로 확인됨`, `- 근거: ${((i.detail || {}).evidence || []).join(', ') || '-'}`, ''); }
      if (kind === 'note') { const n = D.notes[Number(id)]; if (n) out.push(`■ Owner 메모: ${n.text}`, ''); }
    }
    out.push('원칙: main 병합 금지, 검증 기준 완화 금지, 새 비용·credential·민감 권한은 별도 승인.');
    return out.join('\n');
  }
  async function copy(keys) {
    const box = document.getElementById('reqText'); box.value = requestText(keys);
    try { await navigator.clipboard.writeText(box.value); notice('개발 요청 문구를 복사했습니다. Codex와 검토한 뒤 Claude에 전달하세요.'); }
    catch (e) { box.select(); notice('자동 복사가 막혀 문구를 선택해 두었습니다. Ctrl+C로 복사하세요.'); }
  }
  window.AXDev = {render, requestText, picked, setTab: t => { tab = t; return render(); }};
})();
