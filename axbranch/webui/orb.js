// 淸月 particle sphere (web). Driven only by the state the page gives it: real work state from the server, plus
// short input reactions that never change the real state. Additive glow sprites, depth sorting, organic
// deformation, eased transitions. Stops rendering when the tab is hidden, when a stopped state has settled,
// and with motion off (one still frame). No voice states exist.
(function () {
  const P = {   // per-state targets: amp deformation, spin rad/s, swirl latitude flow, breathe, scan band, rgb tint
    idle:       {amp: .05, spin: .10, swirl: 0,   breathe: .015, scan: 0, tint: [140, 155, 225]},
    planning:   {amp: .12, spin: .45, swirl: .9,  breathe: .03,  scan: 0, tint: [125, 150, 235]},
    delegating: {amp: .10, spin: .6,  swirl: .5,  breathe: .02,  scan: 0, tint: [100, 185, 215]},
    verifying:  {amp: .06, spin: .3,  swirl: .1,  breathe: .01,  scan: 1, tint: [140, 175, 225]},
    rework:     {amp: .13, spin: -.4, swirl: .7,  breathe: .03,  scan: 0, tint: [230, 170, 105]},
    done:       {amp: .04, spin: .08, swirl: 0,   breathe: .01,  scan: 0, tint: [105, 195, 160]},
    waiting:    {amp: .04, spin: 0,   swirl: 0,   breathe: 0,    scan: 0, tint: [165, 150, 225]},
    paused:     {amp: .03, spin: 0,   swirl: 0,   breathe: 0,    scan: 0, tint: [150, 160, 182]},
    limit:      {amp: .03, spin: 0,   swirl: 0,   breathe: 0,    scan: 0, tint: [228, 175, 100]},
    error:      {amp: .03, spin: 0,   swirl: 0,   breathe: 0,    scan: 0, tint: [228, 130, 118]},
  };
  const WORKING = new Set(['planning', 'delegating', 'verifying', 'rework']);
  const LEVELS = 10;

  function Orb(canvas) {
    this.c = canvas; this.ctx = canvas.getContext('2d');
    this.state = 'idle'; this.motion = true; this.low = false;
    this.p = JSON.parse(JSON.stringify(P.idle));
    this.t = 0; this.spin = 0; this.swirl = 0; this.impulse = 0; this.burst = 0; this.settleUntil = 0;
    this.links = []; this.raf = null; this.last = 0;
    this.stats = {fps: 0, frameMs: 0, frames: 0, particles: 0, running: false};
    this._fpsWin = []; this.build();
    document.addEventListener('visibilitychange', () => this.wake());
    this.wake();
  }
  Orb.prototype.build = function () {
    const n = this.low ? 260 : 480, pts = [], g = Math.PI * (3 - Math.sqrt(5));
    let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < n; i++) {
      const y = 1 - 2 * (i + .5) / n, r = Math.sqrt(1 - y * y), a = i * g + (rnd() - .5) * .16;
      pts.push([r * Math.cos(a), y, r * Math.sin(a), .7 + rnd() * .6]);
    }
    this.pts = pts; this.waves = [0, 1, 2].map(() => [rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1, .6 + rnd() * .8, rnd() * 6.28]);
    this.stats.particles = n; this.spriteKey = null;
  };
  Orb.prototype.sprites = function (tint) {   // pre-rendered soft glow dots per depth level (cheap to draw)
    const key = tint.map(Math.round).join(',');
    if (key === this.spriteKey) return this.sprite;
    this.spriteKey = key; this.sprite = [];
    for (let l = 0; l < LEVELS; l++) {
      const s = document.createElement('canvas'), size = 24; s.width = s.height = size;
      const x = s.getContext('2d'), gr = x.createRadialGradient(12, 12, 0, 12, 12, 12), a = .18 + .82 * l / (LEVELS - 1);
      gr.addColorStop(0, `rgba(255,255,255,${a})`);
      gr.addColorStop(.25, `rgba(${tint.map(Math.round).join(',')},${a})`);
      gr.addColorStop(1, `rgba(${tint.map(Math.round).join(',')},0)`);
      x.fillStyle = gr; x.fillRect(0, 0, size, size); this.sprite.push(s);
    }
    return this.sprite;
  };
  Orb.prototype.set = function (state, motion, low) {
    if (!P[state]) state = 'idle';
    if (low !== undefined && low !== this.low) { this.low = low; this.build(); }
    const changed = state !== this.state || motion !== this.motion;
    this.state = state; this.motion = motion;
    if (state !== 'delegating') this.links = [];
    if (changed) { this.settleUntil = performance.now() + 900; this.wake(); }
  };
  const STOPPED = new Set(['waiting', 'paused', 'limit', 'error']);
  Orb.prototype.pulse = function (s) {          // input reaction; never during a stopped work state
    if (STOPPED.has(this.state)) return;
    this.impulse = Math.min(1.5, this.impulse + s); this.wake();
  };
  Orb.prototype.complete = function () { this.burst = 1; this.settleUntil = performance.now() + 1800; this.wake(); };
  Orb.prototype.delegate = function (names) {
    const have = this.links.map(l => l.name);
    names.forEach(n => { if (!have.includes(n)) this.links.push({name: n, born: this.t}); });
    this.links = this.links.slice(-4); this.wake();
  };
  Orb.prototype.moving = function (now) {
    return this.motion && (WORKING.has(this.state) || now < this.settleUntil || this.impulse > .01 || this.burst > .01);
  };
  Orb.prototype.wake = function () {
    if (this.raf === null && !document.hidden) this.raf = requestAnimationFrame(ts => this.frame(ts));
  };
  Orb.prototype.frame = function (ts) {
    this.raf = null;
    if (document.hidden) { this.last = 0; this.stats.running = false; return; }   // hidden tab: nothing drawn
    const dt = this.last ? Math.min(.1, (ts - this.last) / 1000) : 1 / 60;
    if (this.low && this.last && ts - this.last < 1000 / 30 - 1) { this.raf = requestAnimationFrame(t => this.frame(t)); return; }
    this.last = ts;
    const t0 = performance.now();
    if (this.motion) this.step(dt); else { this.p = JSON.parse(JSON.stringify(P[this.state])); this.impulse = this.burst = 0; }
    this.draw();
    const ms = performance.now() - t0;
    this.stats.frameMs = this.stats.frameMs * .9 + ms * .1; this.stats.frames++;
    this._fpsWin.push(ts); while (this._fpsWin.length && ts - this._fpsWin[0] > 1000) this._fpsWin.shift();
    this.stats.fps = this._fpsWin.length;
    const go = this.moving(performance.now());
    this.stats.running = go;
    if (go) this.raf = requestAnimationFrame(t => this.frame(t)); else this.last = 0;
  };
  Orb.prototype.step = function (dt) {
    const tg = P[this.state], k = 1 - Math.exp(-dt * 3);
    for (const key in tg) {
      if (key === 'tint') this.p.tint = this.p.tint.map((v, i) => v + (tg.tint[i] - v) * k);
      else this.p[key] += (tg[key] - this.p[key]) * k;
    }
    this.t += dt; this.impulse *= Math.exp(-dt * 4); this.burst = Math.max(0, this.burst - dt / 1.5);
    this.spin += this.p.spin * dt; this.swirl += this.p.swirl * dt;
  };
  Orb.prototype.draw = function () {
    const ctx = this.ctx, W = this.c.width, H = this.c.height, cx = W / 2, cy = H / 2, p = this.p, t = this.t;
    ctx.globalCompositeOperation = 'source-over'; ctx.clearRect(0, 0, W, H);
    let tint = p.tint;
    if (this.burst) tint = tint.map(v => v + (255 - v) * .35 * this.burst);
    const halo = ctx.createRadialGradient(cx, cy, W * .1, cx, cy, W * .48);
    halo.addColorStop(0, `rgba(${tint.map(Math.round).join(',')},.16)`); halo.addColorStop(1, `rgba(${tint.map(Math.round).join(',')},0)`);
    ctx.fillStyle = halo; ctx.fillRect(0, 0, W, H);
    const spr = this.sprites(tint);
    const base = W * .3 * (1 + p.breathe * Math.sin(t * 1.6));
    const expand = this.burst ? 1 + .45 * Math.sin(Math.PI * (1 - this.burst)) * this.burst : 1;
    const amp = p.amp + .08 * this.impulse + .1 * this.burst, scanY = p.scan > .05 ? Math.sin(t * 1.3) : 9;
    const cs = Math.cos(this.spin), sn = Math.sin(this.spin), tc = Math.cos(.35), ts = Math.sin(.35);
    const out = new Array(this.pts.length);
    for (let i = 0; i < this.pts.length; i++) {
      let [x, y, z, w] = this.pts[i];
      const a = this.swirl * (1 - y * y) * 1.5, ca = Math.cos(a), sa = Math.sin(a);
      [x, z] = [x * ca - z * sa, x * sa + z * ca];
      let d = 0;
      for (const [wx, wy, wz, f, ph] of this.waves) d += Math.sin((x * wx + y * wy + z * wz) * 3 * f + t * 1.7 * f + ph);
      const r = base * expand * (1 + amp * d / 3 + .07 * this.impulse * Math.sin(t * 9 + y * 6));
      [x, z] = [x * cs - z * sn, x * sn + z * cs];
      [y, z] = [y * tc - z * ts, y * ts + z * tc];
      const depth = (z + 1) / 2, persp = 1 / (1 - .28 * z);
      let size = (3 + 9 * depth * depth) * w * (W / 260), lvl = Math.min(LEVELS - 1, Math.round(depth * (LEVELS - 1)));
      if (Math.abs(y - scanY) < .07) { lvl = LEVELS - 1; size *= 1.5; }
      out[i] = [z, cx + x * r * persp, cy + y * r * persp, size, lvl];
    }
    out.sort((a, b) => a[0] - b[0]);
    ctx.globalCompositeOperation = 'lighter';
    for (const [, x, y, s, l] of out) ctx.drawImage(spr[l], x - s / 2, y - s / 2, s, s);
    ctx.globalCompositeOperation = 'source-over';
    this.links.forEach((link, i) => {            // delegation: satellites named after the real departments
      const ang = Math.PI * [.1, .9, .3, .7][i % 4], fade = this.motion ? Math.min(1, (t - link.born) / .6) : 1;
      const tx = cx + Math.cos(ang) * base * 1.45, ty = cy + Math.sin(ang) * base * 1.45;
      const sx = cx + Math.cos(ang) * base * .95, sy = cy + Math.sin(ang) * base * .95;
      const mx = (sx + tx) / 2 + (ty - sy) * .3, my = (sy + ty) / 2 - (tx - sx) * .3;
      const col = `rgba(${tint.map(Math.round).join(',')},${.35 + .55 * fade})`;
      ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(sx, sy); ctx.quadraticCurveTo(mx, my, tx, ty); ctx.stroke();
      for (let k = 0; k < 3; k++) {
        const u = this.motion ? (t * .7 + k / 3) % 1 : (k + 1) / 4;
        const px = (1 - u) ** 2 * sx + 2 * (1 - u) * u * mx + u * u * tx, py = (1 - u) ** 2 * sy + 2 * (1 - u) * u * my + u * u * ty;
        ctx.fillStyle = col; ctx.beginPath(); ctx.arc(px, py, 2.4, 0, 6.283); ctx.fill();
      }
      ctx.fillStyle = col; ctx.beginPath(); ctx.arc(tx, ty, 6, 0, 6.283); ctx.fill();
      ctx.fillStyle = '#30364b'; ctx.font = '12px Malgun Gothic, sans-serif'; ctx.textAlign = 'center'; ctx.fillText(link.name, tx, ty + 18);
    });
  };
  window.AXOrb = Orb;
  window.AXOrbStates = P;
})();
