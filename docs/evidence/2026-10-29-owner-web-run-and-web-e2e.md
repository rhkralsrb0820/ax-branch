# Owner web-result execution and the real web-page E2E (2026-10-29)

## 1. Owner server switch (Owner-approved)
- Before: `0.1.63-18fbd6d` (PID 57684). After: **`0.1.63-50aabe2`** (PID 65848), on the same workspace
  `demo-2026-11/workspace` and port 8765.
- Pre-check: 5 projects, all OWNER_REVIEW; no worker process; 12 artifacts present; 653 event rows.
- Backup: SQLite backup API, integrity ok, plus `settings.json`. Record and rollback steps:
  `outputs/server-switch/switch-20261029-193311.json`.
- Post-check:
  - page 200; API lists 5 projects with unchanged states;
  - engine consistency OK for all 5;
  - 0 events written after start; no model call.
  - Chrome was not opened or closed.

## 2. New: open, use and stop a web/server result inside AX Branch (`axbranch/owner_runs.py`, web UI)
- **Implemented:**
  - one isolated run per project; opening again returns the running one;
  - the run uses a fresh copy of the verified version, its own AppContainer and the per-run server channel;
  - no network capability; child processes denied (a built .exe keeps its bootloader child only);
  - Job Object kill-on-close, so the program dies with AX Branch;
  - explicit [결과 종료]; a 4-hour lifetime; exited programs are reaped; leftover run folders are swept at start;
  - bounded output export to `projects/<id>/run/v<N>` on stop.
- **Origin separation:**
  - the result is served on its own port (another browser origin) and opened with `noopener noreferrer`;
  - AX Branch's API needs the session token (embedded only in AX Branch's own page) and refuses foreign Origins.
- **Refused with the reason, nothing started:**
  - non-web modes;
  - programs without a verified `{port}` launch;
  - trained-model results;
  - a missing or changed verified `.exe`.
- **Real-backend tests** (`tests/test_owner_web_run.py`, synthetic canaries):

  | Check | Result |
  |---|---|
  | page served; second open reuses the same run; two projects get separate runs | PASS |
  | from inside the result: the Owner canary file and the other project's run folder are denied | PASS |
  | host service, internet and child process are denied | PASS |
  | AX Branch API with the result's Origin is refused 403, without and with the token | PASS |
  | stop: process gone, run folder removed, run pipe gone, URL refused, start/stop events recorded | PASS |
  | program exit and lifetime are reaped and cleaned | PASS |
  | launch without `{port}` is refused, no run | PASS |

- **Limits:**
  - any process of the same Windows user can connect to the relay port while the result is open;
  - program data restarts from the verified version on each open (it is exported on stop);
  - WebSockets, HTTPS and multi-port programs are untested;
  - the Tk window still uses the older path (web results blocked there).

## 3. Real web-page E2E on candidate 0.1.63-3b3337c — FAILED, root cause found and fixed in source
- Build: exe sha256 `ed3676146f9bf1a19d79e1c40ad9a652dffd5620fbecf54fb5f3b7854fb4ab29`. Source 3b3337c: 546/546
  full regression, hashes matched.
- Harness: `tests/browser_web_e2e.py --text-rework --webapp`.
  - Packaged `AXBranch.exe web --test-mode` on an isolated root, port 8767, headless Chrome with a temporary
    profile.
  - Inputs are test inputs, not the Owner.
  - Record: `outputs/web-e2e-webapp-3b3337c.json`.
- From the page: goal, file `inventory.csv`, task type 웹·서버형 and the 운영 department → project
  P-20261029-d466df created.
- Calls:

  | # | Role | Provider | Tokens |
  |---|---|---|---|
  | 1 | CEO plan | claude | 17,568 |
  | 2 | operations producer | claude | 22,340 |
  | 3 | verification | **codex** | 28,034 (FAIL) |
  | 4 | producer | claude | 35,341 |
  | 5 | verification | **codex** | 28,596 (FAIL) |
  | 6 | CEO strategy | claude | 20,475 |
  | 7 | producer | codex | 40,292 |
  | 8 | verification | claude | 32,706 (FAIL) |

  - Project total **225,352 / 250,000**. Plus the separate Codex availability check: 11,505.
  - **Total: 236,857.**
- Outcome: PAUSED NEEDS_DECISION after the same deterministic failure recurred three times. Owner review, result
  use and the revision were **not reached**.
- **Root cause:**
  - every version defaulted the Owner launch to **port 8765**;
  - on this PC 8765 is the Owner's AX Branch server, and ports are machine-wide, so the program could not bind it
    and the step reported only "nothing listening on 8765";
  - the self-test and every `--port` probe passed, isolated, in all three rounds.
  - The same failure would happen on the Owner's real PC.
- **Fix (source, after the run):**
  - `runtime.RESERVED_PORTS`: an Owner launch announcing 8765 fails with that exact reason;
  - the CEO runtime rules and the producer's execution contract now state that 8765 is reserved and that a busy
    default must fall back to a free port with the real URL;
  - tests: `tests/test_reserved_port.py`.
- **Not done:** a second real web-page E2E after this fix. It needs a new project budget (250,000) and was not
  started without the Owner's decision.

## Status labels
- The earlier product-planning and CSV packaged runs stay **same-provider verified** (Codex was limited); they are
  not relabelled.
- None of these runs is an Owner confirmation.
