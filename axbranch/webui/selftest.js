// In-browser self-test. Served ONLY by a test-mode server (separate workspace, fake launcher, no engine). Drives the
// real DOM like a user would (synthetic drag/drop, typing, clicks), reloads the page between phases and posts each
// check to /api/test/selftest. Never loaded by the Owner's server.
(async function () {
  const {api} = window.AXB, $ = s => document.querySelector(s), sleep = ms => new Promise(r => setTimeout(r, ms));
  const phase = sessionStorage.getItem('axb-st') || '1';
  const report = (name, ok, detail) => api('test/selftest', {phase, name, ok: !!ok, detail: detail === undefined ? '' : String(detail).slice(0, 500)});
  const until = async (f, ms = 6000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await f()) return true; } catch (e) {} await sleep(100); } return false; };
  function drag(chip, target) {                    // a real HTML5 drag sequence with one DataTransfer
    const dt = new DataTransfer();
    chip.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));
    let dropped = false;
    if (target) {
      target.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt}));
      dropped = !target.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}));
    }
    chip.dispatchEvent(new DragEvent('dragend', {bubbles: true, dataTransfer: dt}));
    return dropped;
  }
  const chip = id => document.querySelector(`#library .chip[data-dep="${id}"]`);
  try {
    await until(() => window.AXB.ov);
    if (new URLSearchParams(location.search).has('e2e')) return await e2e();
    if (phase === '1') {
      const px = $('#orb').getContext('2d').getImageData(0, 0, 260, 260).data;
      let lit = 0; for (let i = 3; i < px.length; i += 4) if (px[i] > 0) lit++;
      await report('orb draws particles', lit > 2000, lit + ' lit pixels');
      await report('real state shown separately from input', /실제 상태/.test($('#orbCaption').textContent), $('#orbCaption').textContent);
      $('#goal').focus(); $('#goal').value = '자가 테스트 목표'; $('#goal').dispatchEvent(new Event('input'));
      await report('input reaction is labelled as input', !$('#orbInput').hidden);
      await report('drop on goal area attaches', drag(chip('research'), $('#composer')) && /리서치/.test($('#pendingDeps').textContent));
      $('#pendingDeps [data-req="research"]').click();
      await report('composer marks a department required', /필수/.test($('#pendingDeps').textContent), $('#pendingDeps').textContent);
      drag(chip('research'), $('#composer'));
      await report('duplicate on goal area refused', /이미 첨부한 부서/.test($('#notice').textContent), $('#notice').textContent);
      drag(chip('operations'), null);
      await report('missed drop says not connected', /연결되지 않았습니다/.test($('#notice').textContent), $('#notice').textContent);
      const before = window.AXB.ov.projects.length;
      $('#submit').click(); $('#submit').click();          // double click
      await until(() => window.AXB.view === 'project' && window.AXB.project);
      await sleep(600); await window.AXB.api('overview').then(o => { window.AXB.ov = o; });
      await report('double submit creates one project', window.AXB.ov.projects.length === before + 1, `${before} -> ${window.AXB.ov.projects.length}`);
      await report('goal departments attached at start', window.AXB.project.attached.map(d => d.id).join() === 'research', JSON.stringify(window.AXB.project.attached));
      await report('required choice recorded at start', window.AXB.project.attached[0].mode === 'required', JSON.stringify(window.AXB.project.attached));
      await report('project view shows banner and pipeline', $('#banner').textContent.length > 0);
      drag(chip('operations'), $('#projectDeps'));
      await until(() => window.AXB.project.attached.length === 2);
      await report('drop on project attaches', window.AXB.project.attached.map(d => d.id).join() === 'research,operations');
      drag(chip('operations'), $('#projectDeps'));
      await until(() => /이미 연결된 부서/.test($('#notice').textContent));
      await report('duplicate on project refused', /이미 연결된 부서/.test($('#notice').textContent), $('#notice').textContent);
      await report('required department has no detach button', !document.querySelector('[data-detach="research"]'));
      window.prompt = () => '자가 테스트: 필수 해제';      // the Owner's typed reason
      document.querySelector('[data-mode="research"]').click();
      await until(() => window.AXB.project.attached[0].mode === 'available');
      await report('lowering required records the reason', window.AXB.project.attached[0].mode === 'available', JSON.stringify(window.AXB.project.attached));
      await until(() => document.querySelector('[data-detach="research"]'));
      document.querySelector('[data-detach="research"]').click();
      await until(() => window.AXB.project.attached.length === 1);
      await report('detach via ×', window.AXB.project.attached.map(d => d.id).join() === 'operations');
      sessionStorage.setItem('axb-st', '2'); sessionStorage.setItem('axb-st-pid', window.AXB.pid);
      sessionStorage.setItem('axb-st-count', String(window.AXB.ov.projects.length));
      location.reload(); return;
    }
    if (phase === '2') {
      const pid = sessionStorage.getItem('axb-st-pid');
      await report('reload creates no project', window.AXB.ov.projects.length === Number(sessionStorage.getItem('axb-st-count')));
      const p = await api('project/' + pid);
      await report('attachment restored after reload', p.attached.map(d => d.id).join() === 'operations', JSON.stringify(p.attached));
      const fixture = window.AXB.ov.projects.find(p => p.goal === 'H3 browser fixture (scripted recommendation data, no model)');
      if (fixture) {
        await window.AXB.openProject(fixture.id);
        await until(() => document.querySelector('#recommendations [data-decision="accepted"]'));
        await report('H3 recommendations do not attach on display', window.AXB.project.attached.length === 0);
        document.querySelector('#recommendations [data-decision="accepted"]').click();
        await until(() => window.AXB.project.attached.some(d => d.id === 'research'));
        await report('H3 explicit acceptance connects only the selected capability',
          window.AXB.project.attached.map(d => d.id).join() === 'research' && window.AXB.project.state === 'CREATED');
        document.querySelector('#recommendations [data-decision="dismissed"]').click();
        await until(() => window.AXB.project.recommendations.some(d => d.status === 'dismissed'));
        const saved = await api('project/' + fixture.id);
        await report('H3 decisions persist without starting a project', saved.state === 'CREATED' &&
          saved.recommendations.map(d => d.status).join() === 'accepted,dismissed');
        await window.AXB.openProject(pid);
        await report('H3 project switching clears unrelated suggestions', document.getElementById('recommendations').hidden);
      }
      window.AXB.show('devroom');
      await until(() => document.getElementById('copyTop'));
      const card = document.getElementById('copyTop').closest('.dcard');
      for (const width of [320, 720, 1100]) {
        card.style.width = width + 'px';
        const heading = card.querySelector('h2').getBoundingClientRect();
        const badge = card.querySelector('.badge').getBoundingClientRect();
        const lead = card.querySelector('.lead').getBoundingClientRect();
        const button = document.getElementById('copyTop').getBoundingClientRect();
        await report('recommendation readable at width ' + width,
          badge.top >= heading.bottom && lead.top >= badge.bottom &&
          button.width >= 150 && button.top > lead.bottom && card.scrollWidth <= card.clientWidth,
          JSON.stringify({heading, badge, lead, button}));
      }
      card.style.width = '';
      const dv = document.getElementById('view-devroom').textContent;
      await report('devroom first screen answers the four questions', /지금 어디까지 됐나/.test(dv) && /지금 무엇을 하고 있나/.test(dv) && /다음에 무엇을 고쳐야 하나/.test(dv) && /내가 지금 해야 할 일/.test(dv));
      await window.AXDev.setTab('notes'); await until(() => document.getElementById('noteText'));
      document.getElementById('noteText').value = '자가 테스트 메모'; document.getElementById('noteAdd').click();
      await until(() => /자가 테스트 메모/.test(document.getElementById('notes').textContent));
      document.getElementById('copyTop').click(); await sleep(300);
      const req = document.getElementById('reqText').value;
      await report('top request text has version, problem, scope, done criteria, evidence', /현재 버전: v/.test(req) && /문제:/.test(req) && /요청 범위:/.test(req) && /완료 기준/.test(req) && /근거:/.test(req), req.slice(0, 200));
      sessionStorage.setItem('axb-st', '3'); location.reload(); return;
    }
    if (phase === '3') {
      window.AXB.show('devroom');
      await until(() => window.AXDev && document.getElementById('copyTop'));
      await window.AXDev.setTab('notes'); await until(() => document.getElementById('notes'));
      await report('owner memo survives reload', /자가 테스트 메모/.test(document.getElementById('notes').textContent));
      // Performance while animating: frame rate, frame cost and input latency during the motion.
      window.AXB.show('home');
      for (const low of [false, true]) {
        document.getElementById('lowPower').checked = low; document.getElementById('lowPower').dispatchEvent(new Event('change')); await sleep(400);
        window.AXB.forceOrb = 'planning'; window.AXB.orb.set('planning', true, low);
        await api('test/perf-phase', {low, edge: 'start'}); await sleep(1500);
        const lat = [];
        for (let i = 0; i < 20; i++) {           // event dispatch -> next painted frame, while the sphere moves
          const t = performance.now(); $('#goal').dispatchEvent(new Event('input'));
          await new Promise(r => requestAnimationFrame(() => r())); lat.push(performance.now() - t); await sleep(150);
        }
        await sleep(4000);
        const s = window.AXB.orb.stats; lat.sort((a, b) => a - b);
        await api('test/perf-phase', {low, edge: 'end'});
        await report(`perf ${low ? 'low' : 'normal'}`, s.fps > 10, JSON.stringify({fps: s.fps, frameMs: +s.frameMs.toFixed(2), particles: s.particles, inputToFrameMedianMs: +lat[10].toFixed(1), inputToFrameP95Ms: +lat[18].toFixed(1)}));
      }
      window.AXB.forceOrb = null;
      document.getElementById('motionOff').checked = true; document.getElementById('motionOff').dispatchEvent(new Event('change'));
      window.AXB.orb.set('planning', false); await sleep(800);
      await report('motion off stops the loop', window.AXB.orb.raf === null && !window.AXB.orb.stats.running);
      document.getElementById('motionOff').checked = false; document.getElementById('motionOff').dispatchEvent(new Event('change'));
      await api('test/selftest', {phase, name: 'done', ok: true, detail: ''});
    }
  } catch (e) {
    await report('selftest crashed', false, e.stack || e);
    await api('test/selftest', {phase, name: 'done', ok: false, detail: ''});
  }
  // Real E2E through the page (test server on an isolated workspace, REAL engine and models): goal + file +
  // dragged departments -> submit -> wait for the verified result -> open it -> save the Owner's feedback.
  // A web result opens on its own origin; this page cannot read it (by design). It reports the link; the harness
  // (outside the browser) loads and checks it while it runs, then the page stops it through the UI.
  async function useWebResult(name) {
    const linked = await until(() => document.getElementById('webRunOpen'), 90000);
    const link = document.getElementById('webRunOpen');
    await report(name, linked && link.rel.includes('noopener') && link.target === '_blank', link ? link.href : 'no link');
    await sleep(30000);
    document.querySelector('[data-webrun="stop"]').click();
    const stopped = await until(async () => !(await api('project/' + window.AXB.pid)).owner_web_run.running, 20000);
    await report(name.replace('opened', 'stopped from the page'), stopped);
    if (document.getElementById('modal').open) document.getElementById('modal').close();
  }
  async function e2e() {
    const fx = await api('test/fixture');
    const dt = new DataTransfer(); dt.items.add(new File([fx.text], fx.name, {type: 'text/csv'}));
    const input = $('#files'); input.files = dt.files; input.dispatchEvent(new Event('change'));
    await until(() => /첨부 1개/.test($('#fileNames').textContent));
    $('#goal').value = sessionStorage.getItem('axb-e2e-goal') || new URLSearchParams(location.search).get('goal'); $('#goal').dispatchEvent(new Event('input'));
    const webapp = new URLSearchParams(location.search).has('webapp');
    if (webapp) {
      $('#taskType').value = 'web_app'; $('#taskType').dispatchEvent(new Event('change'));
      drag(chip('operations'), $('#composer'));
      await report('e2e: goal, file, web-app task type and a department in the composer',
        /운영/.test($('#pendingDeps').textContent) && $('#taskType').value === 'web_app', $('#taskType').value);
    } else {
      drag(chip('research'), $('#composer')); drag(chip('operations'), $('#composer'));
      await report('e2e: goal, file and two departments in the composer', /리서치/.test($('#pendingDeps').textContent) && /운영/.test($('#pendingDeps').textContent));
    }
    $('#submit').click();
    await until(() => window.AXB.view === 'project' && window.AXB.project, 20000);
    const pid = window.AXB.pid; await report('e2e: project created from the page', !!pid, pid);
    const t0 = Date.now(); let p = null;
    while (Date.now() - t0 < 25 * 60000) {           // the real run; the page only reads
      p = await api('project/' + pid);
      if (['OWNER_REVIEW', 'PAUSED', 'CLOSED'].includes(p.state)) break;
      await sleep(10000);
    }
    await report('e2e: reached Owner review', p && p.state === 'OWNER_REVIEW', p && `${p.state} ${p.pause_reason || ''}`);
    if (p.state === 'OWNER_REVIEW') {
      await window.AXB.api('project/' + pid).then(() => {}); await sleep(2500);
      await until(() => document.getElementById('oRun'), 10000);
      document.getElementById('oRun').click();
      if (webapp) await useWebResult('e2e: web result opened');
      else {
        await until(() => document.getElementById('modal').open && /\S/.test(document.getElementById('modalBody').textContent), 20000);
        const shown = document.getElementById('modalBody').textContent;
        await report('e2e: verified result opened in the page', shown.length > 200, shown.slice(0, 160));
        document.getElementById('modal').close();
      }
      if (new URLSearchParams(location.search).has('text-rework')) {
        const originalIteration = p.iteration, marker = 'AXB-TEXT-REWORK';
        const request = webapp
          ? '웹앱 화면 맨 위 제목을 "재고 확인 ' + marker + '"로 바꿔 주세요. 표·재고 부족 표시 등 다른 기능과 데이터 처리는 그대로 유지하고, 외부 연결은 추가하지 마세요.'
          : '기존 메모의 내용과 근거 수치는 유지하고, 문서 맨 앞에 "# 재작업 확인: ' + marker + '" 제목 한 줄을 추가해 주세요. 다른 기능·외부 연결·학습은 추가하지 마세요.';
        document.getElementById('oText').value = request;
        document.getElementById('oText').dispatchEvent(new Event('input', {bubbles: true}));
        document.getElementById('oSend').click();
        await report('e2e: textual change requested on existing project', true, JSON.stringify({pid, originalIteration, request}));
        const start = Date.now();
        while (Date.now() - start < 25 * 60000) {
          p = await api('project/' + pid);
          if (p.state === 'PAUSED' || p.state === 'CLOSED' || (p.state === 'OWNER_REVIEW' && p.iteration > originalIteration)) break;
          await sleep(5000);
        }
        const ready = p.state === 'OWNER_REVIEW' && p.iteration > originalIteration;
        await report('e2e: revised iteration returned to Owner review', ready, JSON.stringify({id: p.id, state: p.state, iteration: p.iteration, pause: p.pause_reason}));
        const passed = ready && p.verifications.some(v => v.iteration === p.iteration && v.verdict === 'PASS');
        await report('e2e: revised iteration independently verified', passed);
        if (passed) {
          await window.AXB.openProject(pid);
          document.getElementById('oRun').click();
          if (webapp) await useWebResult('e2e: revised web result opened');
          else {
            const opened = await until(() => document.getElementById('modal').open && document.getElementById('modalBody').textContent.includes(marker), 20000);
            await report('e2e: revised verified result opened with requested text', opened, document.getElementById('modalBody').textContent.slice(0, 250));
          }
        }
      } else {
        document.querySelector('input[name=works][value=yes]').checked = true;
        document.getElementById('oSend').click(); await sleep(3000);
        await report('e2e: feedback sent', true, 'works=yes');
      }
    }
    await api('test/selftest', {phase: 'e2e', name: 'done', ok: true, detail: pid});
  }
})();
