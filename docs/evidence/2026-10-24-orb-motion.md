# 淸月 particle sphere — AX Branch 0.1.60 motion (dev/departments)

**Component.** `axbranch/orb.py`.
- `ParticleOrb`: a Tk canvas of depth-sorted particles on a deforming sphere.
- `OrbPanel`: the sphere with its readable text.
- `python -m axbranch.orb`: a standalone preview labelled "상태 시뮬레이션 · 엔진/모델 호출 없음". It imports no
  engine and makes no model call.

The old 76 px `StatusOrb` was removed.

## What it does
- **Depth.** A Fibonacci sphere with perspective projection. Particles are drawn far to near; near particles are
  larger and more saturated, far ones fade toward the background. A static soft halo sits behind.
- **Organic shape.** Three travelling waves displace the radius over the surface. Working states also add a
  latitude flow: the equator moves faster than the poles.
- **Smooth transitions.** Every state parameter (deformation, spin, flow, pulse, scan band, colour) is eased
  toward the new state's target, never switched.

| Event / state (real, in the app) | Effect |
|---|---|
| Goal box focus / typing | "목표 입력" / "목표 입력 중"; a ripple per keystroke (not during a stopped state) |
| Goal submitted | "목표 접수" plus a ripple; it hands over to the real state once the worker runs |
| PLANNING | swirling latitude flow |
| STAFFING / EXECUTING | faster flow plus a **connection effect**: satellites named after the departments in this project's `department_delegation` events ("임시 에이전트" for a temporary agent), linked by curved streams with travelling packets |
| VERIFYING | a scanning band |
| REWORK | amber, reversed spin |
| A project enters OWNER_REVIEW while the window watches | **one** completion burst, then a still mint sphere "결과 도착" |
| Owner decision needed / Owner stop / usage limit / error | a ~0.8 s settle, then **no timer at all**; the colour and text say why and what to do |
| Idle (nothing to show) | still |

- **Text.** Under the sphere, the state name. In the composer, "what is happening · 다음: next action" for every
  state.
- **No voice states.** No listening or speaking state is shown, because no voice input or TTS is connected
  (tested).
- **Modes.** 모션 끄기 shows still frames only. 저부하 uses fewer particles and 15 fps. Both are saved in workspace
  `settings.json`.
- **Hidden or minimised.** Nothing is drawn and no timer runs; `<Map>` resumes (tested). The project view hides
  the composer, so the sphere is not rendered there either.
- **No model call.** The sphere reads only stored state the window already has.

## Performance on this PC (i7-8550U, 8 threads; visible preview window; no capture during measurement)
| Particles · mode | fps | CPU while animating (% of one core) |
|---|---|---|
| 160 · normal | 21.4 | 24.4 |
| 220 · normal | 21.4 | 27.8 |
| 280 · normal | 21.4 | 33.9 |
| 220 · normal, 60 fps target | 32.9 | 39.5 |
| 80–88 · low power | 12.8 | 12.7–14.5 |

- **Finding.** Tk's repaint sets the floor; adding particles costs little.
- **Choice.** The app uses 130 particles at a 140 px sphere (60 in low power). The preview uses 220.
- **Windows timer.** A 30 fps target gives about 21 fps.
- **EXE (ef5f8b5a…) with the sphere still**, measured for 10 s:
  - home: 1.9% of one core;
  - project view: 3.6%;
  - working set about 50 MB.

## Verified / not verified
- **Verified:**
  - `tests.test_orb` (6) and `tests.test_gui`: state mapping, readable text, no voice states, freeze in stopped
    states, one completion, delegation links from real events, goal-box reaction and hand-over, motion off,
    low power, nothing while hidden;
  - window-only captures of the preview (ui/2026-10-24-orb-preview-*.png);
  - the final EXE home view (ui/2026-10-24-pkg060-orb-home.png): "결과 도착", no model call
    (call_start 44 → 44).
- **Not verified in the EXE:** the moving states (planning, delegation links, verification, rework and the
  completion burst during a real run). Showing them needs a real run, and none was started for the motion check.
  They are verified in the preview and by tests. Owner check: OWNER-DRAG-CHECKLIST.txt, items 6–8.
- **Quality ceiling of Tk** (the current GUI technology):
  - no antialiasing, no alpha blending, no blur, so particles are hard-edged and there is no additive glow as in
    the reference videos;
  - painting about 200 ovals already costs about 25–30% of one core at about 21 fps.
- **Smallest alternative if that quality is required.** Render only the sphere in an embedded web view (canvas
  or WebGL) next to the Tk app. That would need a new dependency (for example pywebview / WebView2) and is NOT
  done here; the app was not rewritten.
