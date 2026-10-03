# Evidence: Owner acceptance failure → OWNER_REVIEW loop → verified repair (P-20261003-bbad3c)

## 1. Owner report
"I tried to use stock_analyzer.py and it does not work — the page says the connection was lost /
disconnected." Recorded on the same project via `axbranch review P-20261003-bbad3c --problem …`
(Owner's words, plus a separately labelled AX Branch reproduction note).

## 2. Reproduction (before any change)
- `.py` opens with `py.exe` on this PC (Explorer OpenWithList). Double-click equivalent
  `py stock_analyzer.py` (no args, no stdin): **exit 0 after 304 ms**, output `PASS: self-test …`.
- v1 contains no server/socket code: no page exists, so any page pointed at it cannot connect.
  (The exact page message could not be produced from the artifact itself.)

## 3. Root cause (AX Branch, not only the file)
1. AX Branch's own execution contract (0.1.1) required no-argument launch = self-test, so a
   double-clicked program ran its tests and closed.
2. Verification never launched the program the way the Owner does.
3. The vague goal became a developer CLI; no criterion required a usable Owner launch.
CEO diagnosis (live, Claude) reached the same conclusion and listed the four acceptance gaps.

## 4. Loop (live, real subscriptions; same project, history kept)
| Step | Evidence |
|---|---|
| Reproduction under revised acceptance on v1 | `server start: process exited with code 0 before listening` |
| Plan v2 | web app (local page + JSON API), runtime spec with 6 HTTP probes |
| v2 (Codex) | Runtime: server up, page OK, CSV analysis OK, bad CSV → 400, survived; **FAIL**: demo JSON lacked disclaimer, self-test endpoint 500, `--self-test` exit 1 |
| v3 (Codex) | **PASS** (Claude verifier): self-test exit 0; all 8 runtime steps OK; 17/17 criteria |
| Strengthened acceptance re-run on v3 | + exact Owner launch (no args) on 8765: OK |
| Independent check | `py stock_analyzer.py` exactly: serves 127.0.0.1:8765, page/demo/posted CSV OK, alive after 20 more requests. With 8765 occupied: falls back to 8766 with a message, all OK (Windows `SO_REUSEADDR` disabled, so no port hijack). |

## 5. Defects found in AX Branch during this work (fixed in 0.1.8)
- Web plan with `launch_args: []` would bind a fixed port and could open the Owner's browser during
  verification → launch contract enforced in code; `BROWSER` neutralized under verification.
- Runtime check did not cover the exact double-click path (flagged by the Verification Agent) →
  added `exact Owner launch (no arguments)` step.
- Provider timeout/stop killed only npm's `cmd.exe` wrapper; the real CLI kept running
  (controlled experiment: grandchild counter 2 → 6 after "kill") → CLIs now run in a Job Object;
  whole tree killed on timeout/stop.
- `providers.py` prepended cheongwol's folder to `sys.path`, shadowing AX Branch's own `tests`
  package → appended instead.
- GUI worker thread held the window; ending after the window was destroyed aborted Python
  (`Tcl_AsyncDelete`) → workers hold no window reference.

## 6. "Stuck run" report (2026-10-04 00:56)
Diagnosed from SQLite + process tree: not stuck. No single call exceeded its limit (design 4.7 min,
v2 build 10.8 min, then v3 build in progress, codex.exe CPU active). The overall run was long because
it is several sequential calls. Visibility added: `call_start` events, live `ACTIVITY.json`
(agent, provider, CLI pid, elapsed, output bytes, seconds since last output) in CLI `status` and the window.
