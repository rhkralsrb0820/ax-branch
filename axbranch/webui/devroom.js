// 오너 개발실: AX Branch's OWN development status, read from docs/devroom/status.json (written by the developer at
// each work unit). No model call, no automatic development. Owner memos live in the workspace and are never
// overwritten by a status update. "개발 중" means "as of the last report", never a live process.
(function () {
  const {api, esc, notice} = window.AXB;
  let D = null, picked = new Set(), selArea = null;
  const impl = s => `<span class="tag impl-${esc(String(s).replace(/\s/g, ''))}">${esc(s)}</span>`;
  const ver = s => `<span class="tag v-${esc(String(s).replace(/\s/g, ''))}">${esc(s)}</span>`;
  const list = a => (a && a.length) ? '<ul>' + a.map(x => `<li>${esc(x)}</li>`).join('') + '</ul>' : '<span class="muted">없음</span>';
  const pick = id => `<label class="muted"><input type="checkbox" data-pick="${esc(id)}" ${picked.has(id) ? 'checked' : ''}> 개발 요청에 담기</label>`;

  async function render() {
    D = await api('devroom');
    const s = D.status, el = document.getElementById('view-devroom');
    if (s.error) { el.innerHTML = `<div class="card">${esc(s.error)}</div>`; return; }
    const area = selArea && s.areas.find(a => a.id === selArea);
    el.innerHTML = `
    <div class="card"><h2>현재 상태 요약 <span class="muted">— AX Branch 자체의 개발 현황 (사용자 업무 프로젝트와 별개)</span></h2>
      <div class="kv">최신 개발 기록: <b>v${esc(s.version)} · ${esc(s.branch)} · 커밋 ${esc(s.commit)}</b> · 마지막 현황 갱신 <b>${esc(s.updated_at)}</b> (마지막 보고 기준)</div>
      <div class="kv">지금 보고 있는 화면(실행 중 코드): <b>v${esc(D.running.version)} · ${esc(D.running.code)}</b>${D.running.code !== s.commit ? ' <span class="tag bad">기록과 다른 코드일 수 있음</span>' : ''}</div>
      <p>${esc(s.stage_text)}</p>
      <div class="dev-grid"><div><b>이번에 완료</b>${list(s.summary.done)}</div><div><b>진행 중 (마지막 보고 기준)</b>${list(s.summary.in_progress)}</div></div>
      <b>중요한 미해결 문제</b>${list(s.summary.open_issues)}
      <div class="kv">지금 할 수 있는 것 → 아래 '개발 현황'의 구현 완료·검증 수준 / 안 되거나 검증 안 된 것 → '검증·문제 기록' / 다음 개발 → '다음 개발 제안'</div></div>
    <div class="dev-grid">
      <div class="card"><h3>AX Branch 구조 지도</h3><div class="map">${s.areas.map(a => `<button class="lv${a.level} ${a.id === selArea ? 'on' : ''}" data-area="${esc(a.id)}">${esc(a.name)}</button>`).join('')}</div></div>
      <div class="card">${area ? `<h3>${esc(area.name)}</h3><p>${esc(area.role)}</p><b>구현된 기능</b>${list(area.implemented)}<b>미구현</b>${list(area.missing)}<b>근거</b>${list(area.evidence)}`
        : '<span class="muted">왼쪽 영역을 선택하면 역할, 구현된 기능, 미구현 항목, 근거가 표시됩니다.</span>'}</div>
    </div>
    <div class="card"><h3>개발 현황 <span class="muted">— 구현 상태와 검증 수준은 별개입니다 ('코드 있음' ≠ '검증됨')</span></h3>
      ${s.items.map(i => `<div class="item"><h4>${esc(i.title)} ${impl(i.impl)} ${ver(i.verify)}</h4>
        <div class="kv">해결하는 것: <b>${esc(i.solves)}</b></div><div class="kv">구현 범위: <b>${esc(i.scope)}</b></div>
        <div class="kv">검증한 버전/커밋: <b>${esc(i.verified_at || 'UNKNOWN')}</b> · 테스트: <b>${esc(i.tests || '-')}</b></div>
        <div class="kv">증거: <b>${esc((i.evidence || []).join(', ') || '-')}</b></div>
        <div class="kv">알려진 실패·한계: <b>${esc((i.limits || []).join(' / ') || '-')}</b></div>
        <div class="kv">완료 조건: <b>${esc(i.done_when)}</b></div>${pick('item:' + i.id)}</div>`).join('')}</div>
    <div class="card"><h3>검증·문제 기록 <span class="muted">— 실패와 미확인 원인 포함. 시뮬레이션·자동 테스트·실제 모델 E2E·Owner 확인을 구분</span></h3>
      ${s.issues.map(i => `<div class="item"><h4>${esc(i.title)} <span class="tag ${i.status === '해결' ? '' : 'bad'}">${esc(i.status)}</span> <span class="tag">${esc(i.kind)}</span> <span class="tag">우선순위 ${esc(i.priority)}</span></h4>
        <div class="kv">재현 조건: <b>${esc(i.repro)}</b></div><div class="kv">영향: <b>${esc(i.impact)}</b></div>
        <div class="kv">확인 버전: <b>${esc(i.seen_at)}</b> · 다음 조치: <b>${esc(i.next)}</b></div>${pick('issue:' + i.id)}</div>`).join('')}</div>
    <div class="card"><h3>다음 개발 제안 <span class="muted">— 표시만 합니다. 자동으로 개발을 시작하지 않습니다.</span></h3>
      ${s.proposals.map(p => `<div class="item"><h4>${esc(p.title)} <span class="tag">${p.source === 'owner' ? '확정된 Owner 지시' : '개발자 추천'}</span> <span class="tag">우선순위 ${esc(p.priority)}</span></h4>
        <div class="kv">추천 이유: <b>${esc(p.why)}</b></div><div class="kv">선행 작업: <b>${esc(p.depends || '-')}</b></div>
        <div class="kv">구현 범위: <b>${esc(p.scope)}</b></div><div class="kv">완료 기준: <b>${esc(p.done_when)}</b></div>
        <div class="kv">검증 방법: <b>${esc(p.verify)}</b></div><div class="kv">비용·권한 승인: <b>${esc(p.approval)}</b></div>${pick('proposal:' + p.id)}</div>`).join('')}</div>
    <div class="card"><h3>Owner 메모와 전달 <span class="muted">— 메모는 현황 갱신으로 덮어쓰지 않습니다. Claude/Codex에 자동 전송하지 않습니다.</span></h3>
      <div id="notes">${D.notes.map((n, k) => `<div class="item"><div class="kv">${esc(n.at ? new Date(n.at).toLocaleString() : '')} ${n.item ? '· ' + esc(n.item) : ''}</div><div>${esc(n.text)}</div>
        <button class="ghost" data-del="${k}">삭제</button> ${pick('note:' + k)}</div>`).join('') || '<span class="muted">메모 없음</span>'}</div>
      <textarea id="noteText" placeholder="원하는 변경·피드백을 적어 주세요"></textarea>
      <div class="row"><button class="ghost" id="noteAdd">메모 저장</button><span class="grow"></span><button class="primary" id="copyReq">다음 개발 요청 복사</button></div>
      <textarea id="reqText" class="copybox" readonly placeholder="'개발 요청에 담기'로 고른 항목으로 요청 문구를 만듭니다."></textarea></div>`;
    el.querySelectorAll('[data-area]').forEach(b => b.onclick = () => { selArea = b.dataset.area; render(); });
    el.querySelectorAll('[data-pick]').forEach(c => c.onchange = () => { c.checked ? picked.add(c.dataset.pick) : picked.delete(c.dataset.pick); });
    el.querySelectorAll('[data-del]').forEach(b => b.onclick = () => saveNotes(D.notes.filter((_, k) => k !== Number(b.dataset.del))));
    document.getElementById('noteAdd').onclick = () => {
      const t = document.getElementById('noteText').value.trim(); if (!t) return;
      saveNotes(D.notes.concat([{id: String(Date.now()), text: t, at: Date.now()}]));
    };
    document.getElementById('copyReq').onclick = copyRequest;
  }
  async function saveNotes(notes) { try { await api('devroom/notes', {notes}); await render(); notice('메모를 저장했습니다.'); } catch (e) { notice(String(e.message)); } }
  function requestText() {
    const s = D.status, out = [`[AX Branch 다음 개발 요청]`, `현재 버전: v${s.version} · ${s.branch} · 커밋 ${s.commit} (현황 갱신 ${s.updated_at})`, ''];
    for (const key of picked) {
      const [kind, id] = key.split(':');
      if (kind === 'item') { const i = s.items.find(x => x.id === id); if (i) out.push(`■ 개발 현황: ${i.title} [${i.impl} / ${i.verify}]`, `- 문제/한계: ${(i.limits || []).join(' / ') || '-'}`, `- 요청 범위: ${i.scope}`, `- 완료 기준: ${i.done_when}`, `- 근거: ${(i.evidence || []).join(', ')}`, ''); }
      if (kind === 'issue') { const i = s.issues.find(x => x.id === id); if (i) out.push(`■ 문제: ${i.title} [${i.status}, 우선순위 ${i.priority}]`, `- 재현: ${i.repro}`, `- 영향: ${i.impact}`, `- 요청 범위(다음 조치): ${i.next}`, `- 근거: ${(i.evidence || []).join(', ') || i.seen_at}`, ''); }
      if (kind === 'proposal') { const p = s.proposals.find(x => x.id === id); if (p) out.push(`■ 제안: ${p.title} (${p.source === 'owner' ? '확정된 Owner 지시' : '개발자 추천'})`, `- 이유: ${p.why}`, `- 요청 범위: ${p.scope}`, `- 완료 기준: ${p.done_when}`, `- 검증: ${p.verify}`, `- 비용·권한: ${p.approval}`, ''); }
      if (kind === 'note') { const n = D.notes[Number(id)]; if (n) out.push(`■ Owner 메모: ${n.text}`, ''); }
    }
    out.push('원칙: main 병합 금지, 검증 기준 완화 금지, 새 비용·credential·민감 권한은 별도 승인.');
    return out.join('\n');
  }
  async function copyRequest() {
    if (!picked.size) return notice("'개발 요청에 담기'로 항목을 먼저 고르세요.");
    const box = document.getElementById('reqText'); box.value = requestText();
    try { await navigator.clipboard.writeText(box.value); notice('다음 개발 요청 문구를 복사했습니다. Codex와 검토한 뒤 Claude에 전달하세요.'); }
    catch (e) { box.select(); notice('자동 복사가 막혀 문구를 선택해 두었습니다. Ctrl+C로 복사하세요.'); }
  }
  window.AXDev = {render, requestText, picked};
})();
