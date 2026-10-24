"""淸月's particle sphere: a Tk canvas of depth-sorted particles on a deforming sphere, driven only by the state the
caller gives it (never by a model call). Working states flow; Owner waits, stops, usage limits and errors freeze it.
It renders nothing while hidden or minimised, and has motion-off and low-power modes.

    python -m axbranch.orb      a standalone preview with simulated states (no engine, no model)."""
import math
import random
import time
import tkinter as tk

# state: (label, what is happening, next action). No listening/speaking states: no voice I/O is connected.
TEXT = {
    'idle': ('대기', '맡길 업무를 입력하면 淸月 CEO가 계획을 세웁니다.', '목표 입력창에 업무를 적어 주세요.'),
    'focus': ('목표 입력', '입력창이 선택되었습니다.', '업무를 적고 [淸月 AI CEO에게 맡기기]를 누르세요.'),
    'typing': ('목표 입력 중', '입력한 목표는 제출해야 전달됩니다.', '다 적었으면 [淸月 AI CEO에게 맡기기]를 누르세요.'),
    'submitted': ('목표 접수', '목표를 받았습니다. 계획을 준비합니다.', '기다리면 됩니다.'),
    'planning': ('계획 중', '淸月 CEO가 목표를 해석하고 단계와 담당 부서를 정합니다.', '기다리면 됩니다. 진행은 파이프라인에 표시됩니다.'),
    'delegating': ('위임·실행 중', '부서와 에이전트가 맡은 단계를 수행합니다.', '파이프라인에서 단계를 선택하면 작업 내용을 볼 수 있습니다.'),
    'verifying': ('독립 검증 중', '검증 에이전트가 결과를 승인된 기준과 대조합니다.', '기다리면 됩니다.'),
    'rework': ('재작업 중', '검증에서 나온 문제를 고칩니다 (횟수 제한 있음).', '기다리면 됩니다. 재작업 이유는 검증 기록에 있습니다.'),
    'done': ('결과 도착', '검증을 통과한 결과가 도착했습니다.', '[결과 실행]으로 확인하고 의견을 보내 주세요.'),
    'waiting': ('승인 대기 · 작업 정지', 'Owner의 결정이 필요해 작업을 멈췄습니다.', '프로젝트 화면의 안내에 따라 결정해 주세요.'),
    'paused': ('중단됨 · 작업 정지', '작업이 중단되었습니다. 자동으로 재개하지 않습니다.', '[수정 요청 / 계속]으로 재개할 수 있습니다.'),
    'limit': ('사용량 한도 · 작업 정지', '모델 사용량 한도로 작업을 멈췄습니다.', '사용량이 회복되면 이어서 진행할 수 있습니다.'),
    'error': ('오류 · 작업 정지', '작업이 실패했거나 응답이 멈췄습니다.', '프로젝트 화면에서 원인과 복구 방법을 확인하세요.'),
}
STOPPED = {'waiting', 'paused', 'limit', 'error'}         # work motion stops (a short settle, then no timer at all)
ANIMATED = {'focus', 'typing', 'submitted', 'planning', 'delegating', 'verifying', 'rework'}

# Per-state targets, eased into each other: amp = deformation, spin = rotation (rad/s), swirl = latitude flow,
# breathe = radius pulse, scan = verification band, tint = pastel colour.
_P = {
    'idle':       dict(amp=.05, spin=.12, swirl=0., breathe=.015, scan=0., tint=(140, 155, 225)),
    'focus':      dict(amp=.07, spin=.25, swirl=0., breathe=.03, scan=0., tint=(150, 140, 230)),
    'typing':     dict(amp=.09, spin=.35, swirl=.2, breathe=.03, scan=0., tint=(150, 140, 230)),
    'submitted':  dict(amp=.14, spin=.8, swirl=.6, breathe=.05, scan=0., tint=(130, 170, 235)),
    'planning':   dict(amp=.12, spin=.45, swirl=.9, breathe=.03, scan=0., tint=(125, 150, 230)),
    'delegating': dict(amp=.10, spin=.6, swirl=.5, breathe=.02, scan=0., tint=(110, 185, 210)),
    'verifying':  dict(amp=.06, spin=.3, swirl=.1, breathe=.01, scan=1., tint=(140, 175, 215)),
    'rework':     dict(amp=.13, spin=-.4, swirl=.7, breathe=.03, scan=0., tint=(225, 170, 110)),
    'done':       dict(amp=.04, spin=.1, swirl=0., breathe=.01, scan=0., tint=(110, 195, 160)),
    'waiting':    dict(amp=.04, spin=0., swirl=0., breathe=0., scan=0., tint=(165, 150, 220)),
    'paused':     dict(amp=.03, spin=0., swirl=0., breathe=0., scan=0., tint=(150, 160, 180)),
    'limit':      dict(amp=.03, spin=0., swirl=0., breathe=0., scan=0., tint=(225, 175, 105)),
    'error':      dict(amp=.03, spin=0., swirl=0., breathe=0., scan=0., tint=(225, 135, 120)),
}
LEVELS = 12                                     # depth colour buckets (itemconfig only when a bucket changes)


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


class ParticleOrb(tk.Canvas):
    def __init__(self, parent, size=240, count=220, low_count=90, bg='#ffffff', fps=30, low_fps=15):
        super().__init__(parent, width=int(size * 1.4), height=size, bg=bg, highlightthickness=0)
        self.size, self.bg_rgb = size, tuple(c // 256 for c in self.winfo_rgb(bg))
        self.counts, self.fpss = (count, low_count), (fps, low_fps)
        self.state, self.motion, self.low_power = 'idle', True, False
        self.params = dict(_P['idle'])
        self.departments = []                   # [(name, born)] satellites of the current delegation
        self._impulse, self._burst, self._t, self._last = 0., 0., 0., None
        self._job, self._settle_until = None, 0.
        self.frames, self.frame_ms = 0, 0.      # for the preview's performance readout
        self._build()
        self.bind('<Map>', lambda e: self._wake(), add='+')
        self.winfo_toplevel().bind('<Map>', lambda e: self._wake(), add='+')
        self._render()

    # ---- public API: only real (or, in the preview, simulated and labelled) state drives it ----
    def set_state(self, state, motion=True):
        if state not in _P:
            state = 'idle'
        changed = (state, motion) != (self.state, self.motion)
        self.state, self.motion = state, motion
        if state != 'delegating':
            self.departments = []
        if changed:
            self._settle_until = time.monotonic() + (0.8 if state in STOPPED | {'idle', 'done'} else 0)
            self._wake()

    def pulse(self, strength=1.):
        """A keystroke or a submit: a short ripple (decays by itself)."""
        self._impulse = min(1.5, self._impulse + strength)
        self._wake()

    def delegate(self, name):
        """A department/agent received work: a satellite with a connection stream."""
        if name not in [n for n, _ in self.departments]:
            self.departments = (self.departments + [(name, self._t)])[-4:]
        self._wake()

    def complete(self):
        """A verified result arrived: ONE completion burst, then calm."""
        self._burst = 1.
        self._settle_until = time.monotonic() + 1.6
        self._wake()

    def set_low_power(self, on):
        if on != self.low_power:
            self.low_power = on
            self._build()
            self._wake()

    def destroy(self):
        self._cancel()
        super().destroy()

    # ---- internals ----
    def _build(self):
        self._cancel()
        self.delete('all')
        n = self.counts[self.low_power]
        rnd = random.Random(7)
        golden = math.pi * (3 - math.sqrt(5))
        self.points = []
        for i in range(n):                      # even Fibonacci sphere, a little jitter so it reads as particles
            y = 1 - 2 * (i + .5) / n
            r = math.sqrt(1 - y * y)
            a = i * golden + rnd.uniform(-.08, .08)
            self.points.append((r * math.cos(a), y, r * math.sin(a), rnd.uniform(.7, 1.3)))
        self.waves = [(rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(.6, 1.4), rnd.uniform(0, 6.28))
                      for _ in range(3)]
        self.glow = [self.create_oval(0, 0, 0, 0, outline='', fill='') for _ in range(6)]   # soft halo, depth cue
        self.items = [self.create_oval(0, 0, 0, 0, outline='', fill='') for _ in range(n)]
        self._levels = [None] * n
        self.links = self.create_line(0, 0, 0, 0, fill='', width=1, smooth=True)
        self.overlay = []

    def _cancel(self):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _visible(self):
        try:
            return bool(self.winfo_viewable()) and self.winfo_toplevel().state() != 'iconic'
        except tk.TclError:
            return False

    def _wake(self):
        if self._job is None:
            self._job = self.after(1, self._tick)

    def _tick(self):
        self._job = None
        if not self._visible():                 # hidden or minimised: no rendering, no timer (<Map> wakes it)
            self._last = None
            return
        now = time.monotonic()
        dt = min(.1, now - self._last) if self._last else 1 / 30
        self._last = now
        moving = self.motion and (self.state in ANIMATED or now < self._settle_until
                                  or self._impulse > .01 or self._burst > .01)
        if self.motion:
            self._step(dt)
        else:                                   # motion off: jump to the target, still frame
            self.params = dict(_P[self.state])
            self._impulse = self._burst = 0.
        started = time.perf_counter()
        self._render()
        self.frame_ms = (time.perf_counter() - started) * 1000
        self.frames += 1
        if moving:
            self._job = self.after(int(1000 / self.fpss[self.low_power]), self._tick)
        else:
            self._last = None

    def _step(self, dt):
        target = _P[self.state]
        k = 1 - math.exp(-dt * 3.0)             # smooth transitions between states
        for key, value in target.items():
            cur = self.params[key]
            self.params[key] = _mix(cur, value, k) if key == 'tint' else cur + (value - cur) * k
        self._t += dt
        self._impulse *= math.exp(-dt * 4)
        self._burst = max(0., self._burst - dt / 1.4)
        self._spin = getattr(self, '_spin', 0.) + self.params['spin'] * dt
        self._swirl = getattr(self, '_swirl', 0.) + self.params['swirl'] * dt

    def _render(self):
        p, t, size = self.params, self._t, self.size
        cx, cy = size * .7, size / 2
        base = size * .30 * (1 + p['breathe'] * math.sin(t * 1.6))
        spin, swirl = getattr(self, '_spin', 0.), getattr(self, '_swirl', 0.)
        burst = self._burst
        expand = 1 + .45 * math.sin(math.pi * (1 - burst)) * burst if burst else 1
        amp = p['amp'] + .08 * self._impulse + .1 * burst
        scan_y = math.sin(t * 1.3) if p['scan'] > .05 else 9
        tint = p['tint']
        if burst:
            tint = _mix(tint, (255, 255, 255), .35 * burst)
        palette = [tuple(int(c) for c in _mix(self.bg_rgb, tint, .25 + .75 * i / (LEVELS - 1))) for i in range(LEVELS)]
        key = tuple(palette[-1])
        if key != getattr(self, '_tint_drawn', None):   # colour changed: every bucket is redrawn once
            self._tint_drawn, self._levels = key, [None] * len(self.items)
            for k, item in enumerate(self.glow):          # halo: background -> faint tint, outer to inner
                self.itemconfigure(item, fill='#%02x%02x%02x' % tuple(int(c) for c in _mix(self.bg_rgb, tint, .05 + .03 * k)))
                g = size * .3 * (1.5 - .09 * k)       # static: large filled shapes are the costly repaint
                self.coords(item, cx - g, cy - g, cx + g, cy + g)
        cs, sn = math.cos(spin), math.sin(spin)
        tilt_c, tilt_s = math.cos(.35), math.sin(.35)
        out = []
        for (x, y, z, w) in self.points:
            a = swirl * (1 - y * y) * 1.5       # latitude flow: the equator moves faster than the poles
            ca, sa = math.cos(a), math.sin(a)
            x, z = x * ca - z * sa, x * sa + z * ca
            d = 0.
            for wx, wy, wz, f, ph in self.waves:  # organic deformation: travelling waves over the surface
                d += math.sin((x * wx + y * wy + z * wz) * 3 * f + t * 1.7 * f + ph)
            r = base * expand * (1 + amp * d / 3 + .07 * self._impulse * math.sin(t * 9 + y * 6))
            x, z = x * cs - z * sn, x * sn + z * cs
            y, z = y * tilt_c - z * tilt_s, y * tilt_s + z * tilt_c
            depth = (z + 1) / 2                 # 0 far .. 1 near
            persp = 1 / (1 - .28 * z)           # near particles project larger and further out
            sx, sy = cx + x * r * persp, cy + y * r * persp
            rad = (.6 + 2.2 * depth * depth) * w * (size / 240)
            lvl = int(depth * (LEVELS - 1) + .5)
            if abs(y - scan_y) < .08:           # verification band
                lvl = LEVELS - 1
                rad *= 1.4
            out.append((z, sx, sy, rad, lvl))
        out.sort()                              # painter's order: far particles under near ones
        coords, itemconfig = self.coords, self.itemconfigure
        for i, (z, sx, sy, rad, lvl) in enumerate(out):
            item = self.items[i]
            coords(item, sx - rad, sy - rad, sx + rad, sy + rad)
            if self._levels[i] != lvl:
                self._levels[i] = lvl
                itemconfig(item, fill='#%02x%02x%02x' % palette[lvl])
        self._draw_links(cx, cy, base, palette)

    def _draw_links(self, cx, cy, base, palette):
        for item in self.overlay:
            self.delete(item)
        self.overlay = []
        if not self.departments:
            return
        n, t = len(self.departments), self._t
        for idx, (name, born) in enumerate(self.departments):
            angle = math.pi * (.08, .92, .32, .68)[idx % 4]         # satellites at the sides, slightly below
            fade = min(1., (t - born) / .6) if self.motion else 1.
            tx, ty = cx + math.cos(angle) * base * 1.55, cy + math.sin(angle) * base * 1.55
            sx, sy = cx + math.cos(angle) * base * .95, cy + math.sin(angle) * base * .95
            mx, my = (sx + tx) / 2 + (ty - sy) * .25, (sy + ty) / 2 - (tx - sx) * .25
            col = '#%02x%02x%02x' % palette[int((LEVELS - 1) * (.4 + .6 * fade))]
            self.overlay.append(self.create_line(sx, sy, mx, my, tx, ty, smooth=True, fill=col, width=1.5))
            for k in range(3):                  # packets travelling from the sphere to the department
                u = ((t * .7 + k / 3) % 1) if self.motion else (k + 1) / 4
                px = (1 - u) ** 2 * sx + 2 * (1 - u) * u * mx + u * u * tx
                py = (1 - u) ** 2 * sy + 2 * (1 - u) * u * my + u * u * ty
                self.overlay.append(self.create_oval(px - 2.2, py - 2.2, px + 2.2, py + 2.2, fill=col, outline=''))
            self.overlay.append(self.create_oval(tx - 6, ty - 6, tx + 6, ty + 6, fill=col, outline=''))
            self.overlay.append(self.create_text(tx, ty + 14, text=name, fill='#30364b', font=('Malgun Gothic', 9)))


class OrbPanel(tk.Frame):
    """The sphere with its readable state text (what is happening, what to do next) underneath."""
    def __init__(self, parent, bg='#ffffff', **kw):
        super().__init__(parent, bg=bg)
        self.orb = ParticleOrb(self, bg=bg, **kw)
        self.orb.pack()
        self.title = tk.Label(self, bg=bg, fg='#30364b', font=('Malgun Gothic', 12, 'bold'))
        self.detail = tk.Label(self, bg=bg, fg='#6c7488', font=('Malgun Gothic', 9), wraplength=280, justify='center')
        self.next = tk.Label(self, bg=bg, fg='#8c7bc8', font=('Malgun Gothic', 9), wraplength=280, justify='center')
        for w in (self.title, self.detail, self.next):
            w.pack()
        self.set_state('idle')

    def set_state(self, state, motion=True, detail=None):
        self.orb.set_state(state, motion)
        label, what, nxt = TEXT.get(state, TEXT['idle'])
        for widget, text in ((self.title, label), (self.detail, detail or what), (self.next, '다음: ' + nxt)):
            if widget.cget('text') != text:
                widget.config(text=text)


def demo():
    """상태 시뮬레이션: buttons stand in for real events. Nothing here calls the engine or a model."""
    import os
    root = tk.Tk()
    root.title('淸月 모션 미리보기 — 상태 시뮬레이션')
    root.configure(bg='#f5f5fa')
    tk.Label(root, text='상태 시뮬레이션 · 엔진/모델 호출 없음', bg='#f5f5fa', fg='#b0573f',
             font=('Malgun Gothic', 10, 'bold')).pack(pady=(10, 0))
    card = tk.Frame(root, bg='#ffffff', padx=20, pady=16)
    card.pack(padx=20, pady=10)
    panel = OrbPanel(card)
    panel.pack()
    entry = tk.Entry(card, width=40, font=('Malgun Gothic', 10), relief='flat', bg='#f5f5fa')
    entry.pack(pady=(12, 4), ipady=4)
    state = {'s': 'idle'}

    def go(s, detail=None):
        state['s'] = s
        panel.set_state(s, motion=not off.get(), detail=detail)
    entry.bind('<FocusIn>', lambda e: state['s'] in ('idle', 'done') and go('focus'))
    entry.bind('<Key>', lambda e: (state['s'] in ('idle', 'done', 'focus') and go('typing'), panel.orb.pulse(.35)))

    def submit(_e=None):
        if entry.get().strip():
            entry.delete(0, 'end')
            go('submitted')
            panel.orb.pulse(1.2)
            root.after(1500, lambda: state['s'] == 'submitted' and go('planning'))
    entry.bind('<Return>', submit)
    row = tk.Frame(root, bg='#f5f5fa'); row.pack()
    for s in ('idle', 'planning', 'verifying', 'rework', 'waiting', 'paused', 'limit', 'error'):
        tk.Button(row, text=TEXT[s][0].split(' ·')[0], relief='flat', bg='#ece8f8',
                  command=lambda s=s: go(s)).pack(side='left', padx=2)
    row2 = tk.Frame(root, bg='#f5f5fa'); row2.pack(pady=6)

    def delegate(name):
        go('delegating', detail=f'{name} 부서가 맡은 단계를 수행합니다.')
        panel.orb.delegate(name)
    for name in ('리서치', '운영'):
        tk.Button(row2, text=f'위임 → {name}', relief='flat', bg='#e3f1f6', command=lambda n=name: delegate(n)).pack(side='left', padx=2)
    tk.Button(row2, text='결과 도착', relief='flat', bg='#e2f3ea',
              command=lambda: (go('done'), panel.orb.complete())).pack(side='left', padx=2)
    off, low = tk.BooleanVar(), tk.BooleanVar()
    tk.Checkbutton(row2, text='모션 끄기', variable=off, bg='#f5f5fa', command=lambda: go(state['s'])).pack(side='left', padx=6)
    tk.Checkbutton(row2, text='저부하', variable=low, bg='#f5f5fa',
                   command=lambda: panel.orb.set_low_power(low.get())).pack(side='left')
    perf = tk.Label(root, bg='#f5f5fa', fg='#6c7488', font=('Consolas', 9)); perf.pack(pady=(0, 10))
    last = {'frames': 0, 't': time.monotonic(), 'cpu': time.process_time()}

    def readout():
        now, cpu = time.monotonic(), time.process_time()
        fps = (panel.orb.frames - last['frames']) / (now - last['t'])
        load = 100 * (cpu - last['cpu']) / (now - last['t'])
        perf.config(text=f"입자 {len(panel.orb.points)} · {fps:4.1f} fps · 프레임 {panel.orb.frame_ms:4.1f} ms · "
                         f"CPU {load:4.1f}% (1코어 기준) · PID {os.getpid()}")
        last.update(frames=panel.orb.frames, t=now, cpu=cpu)
        root.after(1000, readout)
    readout()
    root.mainloop()


if __name__ == '__main__':
    demo()
