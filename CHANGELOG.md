# Changelog

Semantic versioning. Every release needs an entry with all five sections (enforced by
`tests/test_release.py`).

## [0.1.11] - 2026-10-07

Visible execution and the lifecycle fixes found by running Test Project #1 (P-20261003-bbad3c) for real.
The US-stock analyzer is 淸月's Test Project #1; its features are not extended — it validates the lifecycle.

### Added
- Live execution view in the window (`axbranch/live.py`, implemented by Codex, reviewed by the lead): project
  header (stage, real status, agent, engine, worker/provider pid, elapsed/timeout, last activity, version,
  recovery count, next action), agent table 淸月 CEO → hired agents → Verification → Runtime Acceptance (LOCAL)
  → OWNER_REVIEW with why hired / engine / task / status / last activity / result, and per-agent explicit
  records (claim, evidence, counterargument, decisions, verification, runtime steps, Owner feedback) plus a
  timeline. Everything is read from local state; opening or browsing makes no AI call. Hidden reasoning is
  neither stored nor shown.
- Plans state `why` each specialist is hired; workers record `evidence` and `counterpoints`.
- Development view: `devteam/devview.cmd` opens an observe-only pane (Claude Code dev CLI ACTIVE/IDLE by CPU,
  Codex task + live output, AX Branch project workers); `delegate.py` streams Codex output there and opens it
  automatically. No prompt relay.

### Changed
- Project runs are background processes (also from AXBranch.exe: `AXBranch.exe run <id>`); closing the window
  no longer stops them. Stop = end the worker tree + PAUSE ("Owner stopped"), never auto-resumed.
- The final build of a large single-file deliverable (>40k chars) uses an edits-only schema.
- An Owner action (resume, review, approve, stop …) starts a fresh automatic-recovery budget; workers started
  by the app/supervisor are not Owner actions.

### Fixed
- Regenerating a 115-164 KB file per call timed out or came back empty (v10-v21 of Test Project #1).
- Windows refused the heartbeat/activity `os.replace`/`unlink` while the window read the file → project
  PAUSED with an internal error or a hung worker.
- The liveness probe briefly took the run lock; a starting session could exit "Busy".
- Closing the window cancelled runs ("오너가 중단했습니다"), and the supervisor then auto-resumed them.
- Codex's independent review (8 findings, 7 fixed): failed re-plan escaped the recovery cap / left a dead
  end; Owner resume not recorded; stop on a failed-paused project auto-resumed; stop missed a worker waiting
  for a provider slot; edits-only could not delete a bundle file; looking at a project created files.
- A windowed-exe worker blocked forever on the uncaught-exception dialog; it now logs and exits.
- GUI tests silently skipped on any Tcl error; they skip only without a display.

### Verification
- 114 tests pass (`python -X utf8 -m unittest discover -s tests -t .`), none skipped; GUI tests repeated 6×
  with no flake after the race fixes.
- AXBranch.exe: window opens with no provider child except the supervisor's recovery worker; the packaged
  worker exits with code 1 and a log on error (no dialog).
- Live: opening AXBranch.exe recovered the STALLED Test Project #1 by itself and started its final build.

### Known issues
- Codex review #7: two stages with the same agent_role in one plan share one call history in the view.
- D-AUTO-1: with the window closed, nothing restarts a worker that dies (no OS-level supervisor yet).
- Test Project #1 has not reached OWNER_REVIEW yet (see the release note for its live state).

## [0.1.10] - 2026-10-06

Stabilization: the Owner is no longer the watchdog. Evidence of the 2 h 20 min non-converging run (v10–v15)
and the fixes: `docs/evidence/2026-10-06-long-run-incident-and-supervisor.md`.

### Added
- `axbranch/supervisor.py`: deterministic execution status (ACTIVE / WAITING_FOR_OWNER / WAITING_FOR_PROVIDER /
  STALLED / RECOVERING / FAILED / PAUSED / COMPLETED) with project, stage, agent, provider, worker pid, call
  elapsed/timeout, heartbeat, last activity, checkpoint, retry count, failure signature, next action.
  Engine heartbeat (`HEARTBEAT.json`). Bounded automatic recovery: resume → same signature → replan+resume →
  NEEDS_DECISION (≤5 per project), whole-tree stop of a hung worker, no duplicate launch. The window runs it
  every 30 s; `axbranch supervise [--watch]`.
- Permission reuse (`axbranch/permissions.py`, Codex): approved public read-only domains are reused across
  projects; api_key / login / paid / posting / trading / personal data / destructive / governance always ask.
- OWNER_ESCAPE metric in `axbranch effort` (Owner actions through cli / developer_cli; in-app and dev mode
  excluded) and automatic-recovery count; every Owner action records its channel.
- Strategy reviews can revise the program's `network_access` (still through the approval gate).

### Changed
- The same failure signature twice in a row forces a strategy change ("continue" removed), once per signature.
- A declined connection is explained to the CEO as "not these domains", not as a network ban.

### Fixed
- A domain proposed again after a decline waited forever for an approval nobody could give; it is now a new
  pending request.
- Owner rework before anything was built crashed (no artifact); rework now uses the latest real version.
- Supervisor defects found by Codex's independent acceptance tests: escalation was a no-op on a PAUSED project;
  a stale RECOVERING marker disabled the watchdog; a replacement could launch while the old lock was held.

### Verification
- 95 tests pass (`python -X utf8 -m unittest discover -s tests -t .`), including acceptance A (stalled worker
  tree → stop → resume, no duplicate), B (provider wait left untouched), C/D (same-project rework for a
  software project and a math-proof document with Korean feedback), E (permission reuse / re-ask on higher
  risk), F (test-started processes all gone).
- Live: supervisor recovered P-20261003-bbad3c (STALLED → resume → approval gate) without an Owner CLI step.

### Known issues
- P-20261003-bbad3c waits for the Owner's in-app decision on 5 runtime domains; its failure budget is used up,
  so after one more FAIL it pauses and an in-app resume adds 3 rounds.
- Codex's sandbox cannot run Python on this PC; delegated work is tested by the host.

## [0.1.9] - 2026-10-05

Owner review redesign, governed external connections, and the fixes from a real continuity event
(genuine Claude usage limit + 13.7 h PC sleep + host interruption). Evidence:
`docs/evidence/2026-10-05-recovery-continuity.md`; analysis: `docs/GAP_ANALYSIS.md`.

### Added
- Development team mode: `devteam/delegate.py` (bounded Claude→Codex handoff, deterministic scope/test
  check, `devteam/DEV_LOG.jsonl`); BROWSER probes can click (via an injecting loopback proxy);
  `expect_absent` (forbidden text, e.g. fabricated values); `call_failed` events and preserved switch
  reasons; WORKING/WAITING/STALLED/FAILED/PAUSED status from recorded state; `harness_retry`.
- OWNER_REVIEW asks two separate questions: does it work? / what next? Plain-language feedback (no
  classification), `works` alone keeps the project open, only an explicit finish moves toward closing.
  CLI `review <id> [--works | --broken T] [--request T] [--finish]`; window dialog "리뷰 / 피드백…".
- External-connection approval gate: plans declare `network_access`; the build waits for the Owner
  (`approve <id> --network yes|no`, window buttons); a decline goes back to the CEO. `external_connection`
  added to Owner-only actions (tightening).
- Rendered-page Runtime Acceptance: `BROWSER` probes load the page in headless Edge (scripts run) and
  check rendered text (script source excluded).
- Resource awareness: machine-wide limit of 2 concurrent provider CLIs (OS file-lock slots), 1 GB free
  memory floor before launch, sleep-aware provider timeouts.
- `axbranch effort [<id>]`: Owner Effort KPI split into MEASURED / ESTIMATED / UNKNOWN.
- Provider track record (measured per engine) given to the CEO when planning, re-planning, diagnosing.
- `axbranch replan <id> --reason …` recovery: CEO strategy review for a stuck/misdirected project.
- Claude runs stream progress (stream-json), so live activity shows real output growth.

### Changed
- Every rework stage receives the latest non-empty version and the Owner-confirmed version in full
  (was: final stage only; notes stages ≤ 60 000 chars).
- Pipelines are production-only; the final stage must be the producer of the whole deliverable.
- A strategy review can revise the runtime spec (never silently weakening it).

### Fixed
- Empty builds were stored and sent to verification; now rejected deterministically (no call).
- Rework baseline could be an empty artifact.
- PC sleep was counted as provider work (false timeout after 13.7 h).
- GUI could abort (`Tcl_AsyncDelete`) when the cyclic GC freed dialog objects on a worker thread.

### Verification
- 71 unit tests pass (exit code checked, twice).
- P-20261003-bbad3c recovered without restarting: v4 kept as base after deterministic checks; one
  reproduced defect (`103 104` → 103104) fixed by **edit-based builds on Codex** (84 s and 50 s; the two
  previous whole-file attempts timed out at 1 800 s). v8 PASS (24/24 criteria, self-test exit 0, 20/20
  runtime steps incl. click-driven rendered analysis and exact Owner launch) → OWNER_REVIEW.
- Independent check of v8: the reported inputs parse to distinct prices; real-browser click on a sample shows
  the one-line interpretation, evidence, risks and the not-investment-advice notice.
- Development by delegation: Codex implemented the click-probe proxy (272 s; needed one rework found in
  review) and failed-call observability (160 s; no rework) via `devteam/delegate.py`.

### Known issues
- v7 was failed by a headless-Edge hang (harness, not the product) and rebuilt once; fixed afterwards
  (`harness_retry`), but the hang's root cause is unknown. `effort` still counts that FAIL as a caught defect.
- BROWSER probes can click but not type; typed-input flows are covered by HTTP probes only.
- While Claude emits its final structured deliverable, streamed output may pause for minutes.
- Experience improves engine choice only through the track record shown to the CEO; nothing else learns.

## [0.1.8] - 2026-10-04

Owner acceptance found a delivered program that was unusable (closed 0.3 s after a double-click; no
page). This release adds the Owner review loop and Runtime Acceptance Verification, and repairs that
project through the normal loop. Evidence: `docs/evidence/2026-10-04-owner-review-stock-analyzer.md`.

### Added
- **OWNER_REVIEW** state after delivery. Owner reports *works* (→ PENDING_CLOSE), *problem* or
  *change* (→ REWORK on the SAME project). `owner_feedback` table (schema v3). On new feedback the
  engine reproduces (runtime run of the delivered version), the CEO diagnoses (feedback + evidence)
  and revises criteria / runtime spec / pipeline, the revised acceptance is run on the old version,
  then build → verify → back to OWNER_REVIEW. Round budget refreshed per Owner request.
- **Runtime Acceptance Verification** (`axbranch/runtime.py`): the plan declares how the Owner
  launches the artifact (cli / web / gui / none) and probes for the primary flow; the engine runs them
  contained. Web: server start on a free port, HTTP flow, connection loss detection, survival, a
  repeat request, and the **exact Owner launch** (no arguments). PASS requires it.
- CLI `axbranch review <id> --works | --problem "…" | --change "…"`; window buttons
  작동함 / 문제 있음… / 수정 요청…; report shows how to test; detail shows runtime steps and feedback.
- Live activity: `call_start` events; `ACTIVITY.json` (agent, provider, CLI pid, elapsed, output
  bytes, seconds since last output) shown by `status` and the window; `call` events carry duration.

### Changed
- Self-test runs as `python <file> --self-test`; a no-argument launch is the Owner's program.
- Web launch contract (`--port {port} --no-browser`) enforced in code; `BROWSER` is a no-op under verification.
- Provider CLIs run inside a Job Object (no caps): timeout / Owner stop kill the whole tree.

### Fixed
- Provider timeout killed only npm's `cmd.exe` wrapper; the real CLI kept running (proven).
- cheongwol's folder was prepended to `sys.path`, shadowing AX Branch's own `tests` package.
- A GUI worker thread outliving the window aborted Python (`Tcl_AsyncDelete`).

### Verification
- 47 unit tests pass, including runtime acceptance against real servers (dropped connection, crash,
  exact-launch failure), the Owner review loop, provider tree kill on timeout and stop, live activity.
- Live: P-20261003-bbad3c reproduced → diagnosed → v2 FAIL (runtime + self-test) → v3 PASS (17/17,
  8/8 runtime steps, exact Owner launch OK); independent exact-launch check with 8765 free and taken.

### Known issues
- `gui` mode only checks that a window starts and stays up; window content is not exercised.
- Claude reports output only at the end, so its "last output" stays 0 until the call completes.
- Delivered projects from before 0.1.8 stay in PENDING_CLOSE; they can still receive problem reports.

## [0.1.7] - 2026-10-03

### Added
- `axbranch upgrade-proposal` (`axbranch/upgrade.py`): locked unless average Owner satisfaction over
  closed projects is ≥ 90%; when open, the CEO drafts a proposal (problem, capability, improvement,
  cost, ROI, security, alternatives, lock-in) from measured SQLite evidence into
  `workspace/proposals/`, marked DRAFT / NOT APPROVED. Nothing is ever purchased or enabled.
- Evidence: `docs/evidence/2026-10-03-v0.1.7-retrieval-and-exe.md`.

### Changed
- Nothing else.

### Fixed
- Nothing.

### Verification
- 33 unit tests pass.
- Live in the packaged 0.1.6 exe: an archived project's knowledge was retrieved, recorded
  (`context_used`) and used by a new project; self-tests ran contained in the frozen app; v1 FAIL → v2 PASS;
  independent round-trip check against the archived project's artifact: 0/20,008 mismatches.
- Live gate: `upgrade-proposal` reports locked without calling a model.

### Known issues
- The upgrade gate needs satisfaction scores: give one when closing (`finish … --satisfaction N` or the dialog).
- A genuine usage-limit failover, a recorded human click-through, and AX Works data remain open.

## [0.1.6] - 2026-10-03

Containment for generated code run during verification.

### Added
- `axbranch/sandbox.py`: self-tests (single file and bundle) run with a clean environment (only what
  Python needs; no API keys or CLI session tokens), inside a Windows Job Object (≤8 processes, ≤1 GiB
  for the whole tree). When the main process exits or times out, the whole tree is killed at once.
  Non-Windows: new session + killpg.
- `tests/test_sandbox.py` with real processes: parent secret invisible, orphaned grandchild killed,
  timeout kills the tree, process cap enforced.

### Changed
- Output is captured to a file and only the main process is awaited.

### Fixed
- Generated code inherited the full parent environment, including CLI session tokens.
- On timeout only the direct child was killed; a spawned grandchild kept running. And while reading
  output through a pipe, a grandchild holding the pipe could finish its own work before the check
  ended (found by the new test).

### Verification
- 31 unit tests pass.
- The four delivered live artifacts (906ead v2, 06983b v1, 4e3292 v2 bundle — its tests start
  subprocesses — and 46185d v4) all still pass their self-tests under containment.

### Known issues
- Same OS account: generated code can still read the user's files. A separate low-privilege
  account is the upgrade path (D12). Network access is not blocked.

## [0.1.5] - 2026-10-03

Windows app end to end, multi-file artifacts, live provider failover, and the robustness fixes those
runs exposed. Evidence: `docs/evidence/2026-10-03-v0.1.5-live-runs.md`.

### Added
- Multi-file `bundle` artifacts (`axbranch/artifacts.py`): builder returns `files`; only safe relative
  paths are written (no absolute, drive, `..`; ≤40 files / 400 KB); refused paths fail verification;
  per-file sha256 manifest, artifact hash = manifest hash; `check` detects changed, missing and
  unexpected files; the entry file runs with no args and empty stdin.
- `AXBranch.exe --goal "…"` and `--resume <id>` (drive the window's own handlers).
- GUI end-to-end test through real Tk widgets; GUI is injectable (workspace, engine factory).
- `context_used` event: the vault notes and GAI items (title + URL) the CEO saw; archived as Evidence.
- `decision` event when verification had to run on the producer's engine.
- Schema version (`PRAGMA user_version`=2); `docs/INTEGRATION.md`.

### Changed
- Bundle self-tests run with `python -E -s` (`-I` drops the script folder from `sys.path`).
- GAI items must match ≥30% of the goal's terms (min 2); stray two-word matches added off-topic papers.
- All SQLite inserts name their columns.

### Fixed
- An unexpected engine error killed the GUI worker silently and stranded the project in EXECUTING. Now
  the project pauses with the reason and a traceback goes to `workspace/logs/engine-errors.log`.
- Older code running against a newer database crashed mid-run; it now refuses up front ("Update AX Branch").
- Closing the window left the refresh timer firing into a destroyed window.

### Verification
- 27 unit tests pass (engine, lock, GUI, bundle, robustness, release).
- Live: packaged exe goal -> FAIL -> (crash found) -> 0.1.5 exe `--resume` -> PASS -> report, no stage
  re-run beyond the lost build; bundle project v1 FAIL (Windows CRLF) -> v2 PASS (20 tests); failover
  project all 11 turns on real Codex after a stand-in Claude refusal, 3 FAIL -> PASS. Independent checks
  of all three artifacts passed (see evidence).

### Known issues
- The failover test simulated Claude's refusal; a genuine usage-limit event has not occurred yet.
- No person has yet clicked through the exe; the GUI path is covered by automated widget tests and `--goal`/`--resume`.
- AX Works integration is planned only (it has no data on this PC). Self-test still not sandboxed.

## [0.1.4] - 2026-10-03

### Added
- One session per project: `run` and `finish` hold an exclusive OS lock
  (`workspace/projects/<id>/run.lock`, msvcrt on Windows / flock elsewhere). The OS releases it
  when the holder exits or crashes, so no stale locks. A refused session raises `state.Busy`
  before writing anything; the CLI exits 2 with a message; the GUI shows it in the status bar.
- `tests/test_lock.py`: second thread refused mid-build without writing; separate process refused;
  killed holder releases the lock.

### Changed
- Nothing else.

### Fixed
- 0.1.0 known issue "two runners on the same project are not locked out".

### Verification
- 17 unit tests pass.
- Live CLI (scratch AXB_ROOT): while process A held the lock, `axbranch run` and `axbranch finish --save`
  each exited 2 with "Already running in another session"; project stayed CREATED; lock free after A exited.

### Known issues
- The lock is per machine (file lock); two machines sharing one workspace folder are not supported.
- Remaining: Windows-app end-to-end run, live quota failover, multi-file artifacts, AX Works integration.

## [0.1.3] - 2026-10-03

First live SAVE & CLOSE (project `P-20261003-06983b`).

### Added
- Archive note sections: Goal (interpretation, criteria, pipeline), Decisions, Lessons, Verification
  Findings (every round), Evidence (audit and provider-handoff events), CEO Report, Artifacts.

### Changed
- Archives hold durable knowledge only: artifacts are referenced by path + sha256, never copied
  (0.1.2 embedded up to 4,000 characters of artifact source).
- Archive verification now requires every section in addition to the byte-exact sha256 read-back.

### Fixed
- Findings from PASS rounds were dropped from the archive (only FAIL rounds were kept); a project
  that passed first time lost its residual minor findings.
- Evidence (e.g. the Codex continuation audit) was not archived.

### Verification
- 15 unit tests pass; the archive test now asserts no artifact source, every round present, artifacts by hash.
- Live: `finish P-20261003-06983b --save` -> PENDING_CLOSE -> ARCHIVE_PENDING_APPROVAL -> ARCHIVING -> CLOSED.
  Note sha256 on disk == recorded; all 7 sections present; agent `terminated`; stage outputs (agent
  context) deleted; artifact and verification records kept. Source lines in the note are only the
  verifier's quoted evidence. `P-20261003-906ead` unchanged (state, updated, last event, outputs, agents).

### Known issues
- Archive retrieval (`knowledge.retrieve`) has not yet fed a later live project.
- Earlier items remain: quota failover not exercised live, no cross-process run lock, self-test not sandboxed, single-file artifacts.

## [0.1.2] - 2026-10-03

Real Codex CLI continuation test passed: Codex, given only "Continue the AX Branch work.", read
persistent state and finished an interrupted project without re-running completed work.

### Added
- `axbranch run <id> --stop-at STATE`: end a session at a controlled checkpoint (project stays active).
- `axbranch check <id>`: SQLite <-> disk consistency (artifact sha256 vs bytes, plan/state sanity); exit 1 if unsafe.
- `session` events (OS pid + names of CODEX*/CLAUDE* environment variables, never values) as evidence of the driving CLI.
- HANDOFF.md now includes `ax_branch_git` (commit, subject, uncommitted files) and `consistency_problems`.
- AGENTS.md continuation protocol; `.gitattributes` (LF); `docs/GITHUB_PLAN.md`; evidence record
  `docs/evidence/2026-10-03-codex-continuation.md`.

### Changed
- `.gitignore` hardened for a public-host push (runtime DBs, agent context, logs, keys, tool state, builds).

### Fixed
- CHANGELOG 0.1.1 test count corrected (13, not 14).

### Verification
- 15 unit tests pass, including stop-at + second-session continuation without rerun and tamper detection.
- Live: project `P-20261003-06983b` stopped at VERIFYING by a Claude Code session; the Owner launched
  `codex exec` with no task context; Codex read AGENTS/HANDOFF/state docs, ran `check`, then `run`.
  SQLite shows a Codex session (CODEX_SESSION_ID), only Verification + CEO report calls, stage output
  unchanged, VERIFYING -> PENDING_CLOSE, `check` consistent, the other project untouched.
- Delivered `won_reader.py`: self-test exit 0; 0 mismatches vs an independent reference on 20,010 inputs.

### Known issues
- Quota failover between providers still not exercised live.
- Codex as driver needs `-s danger-full-access` (writes outside the repo, temp dir, nested CLI with network).
- Earlier items remain: no cross-process run lock, self-test not sandboxed, single-file artifacts, ax-works not integrated.

## [0.1.1] - 2026-10-03

First live end-to-end run (project `P-20261003-906ead`, Korean business-registration-number
validator) completed: plan -> 2 agents -> v1 FAIL -> rebuild -> v2 PASS -> CEO report. Fixes below
were found by that run.

### Added
- `docs/PROJECT_STATE.md`, `docs/TASK_STATE.md` (development continuity for Claude Code / Codex sessions).
- Regression tests: recorded artifact hash equals bytes on disk; self-test runs with no args and empty stdin.

### Changed
- Provider turn timeout 900 s -> 1800 s (a full-file build+review turn exceeded 15 min live).
- CEO and final-stage builder are now told the exact execution contract: the engine runs
  `python <file>` with no arguments and empty stdin, and that must run the self-test.

### Fixed
- Artifacts and archive notes were written with `write_text`, so on Windows the bytes on disk (CRLF)
  did not match the recorded sha256 (LF). Now written/verified as exact bytes. The two live-run
  artifacts were content-identical and were restored to their recorded bytes (audit event
  `artifact_bytes_restored`).
- Self-test subprocess inherited the parent's stdin; now `DEVNULL` (a stdin-reading program could hang).

### Verification
- 13 unit tests pass (`python -X utf8 -m unittest discover -s tests -t .`); the new hash assertion fails on 0.1.0 code. (Corrected: an earlier note said 14.)
- Live run: Claude CEO plan; Codex engineer stage; Claude finalizer; independent Verification on Codex;
  v1 FAIL (self-test not reachable with no args — harness contract was unstated), v2 PASS; CEO report.
- Resume: paused on Claude timeout, resumed from SQLite; no re-plan, Codex stage not re-run (call ledger).
- Independent check of v2: self-test exit 0; CLI/stdin behave; 0/20,000 random numbers disagree with an
  independent reference of the NTS checksum; disk sha256 == SQLite sha256 for v1 and v2.

### Known issues
- Claude->Codex quota failover is unit-tested only; no live quota event has occurred.
- Codex CLI has not yet driven a project as the *session* (running `python -m axbranch run`); only as a per-turn provider.
- A non-quota provider fault (e.g. timeout) pauses the project; it does not fail over (by design, from cheongwol).
- The v1 FAIL was caused by an unstated harness contract, not an artifact defect; the gate behaved correctly.
- Items from 0.1.0 remain: no cross-process run lock, self-test not sandboxed, single-file artifacts, ax-works not integrated.

## [0.1.0] - 2026-10-03

### Added
- Phase 0 audit and reuse map of cheongwol, ax-works and global-ai-intelligence (`docs/AUDIT.md`).
- SQLite runtime state with an enforced project lifecycle (CREATED … CLOSED, PAUSED with resume state).
- 淸月 AI CEO: goal interpretation, acceptance criteria, dynamic pipeline, temporary agent staffing,
  provider choice per stage, strategy review every 2 FAILs (continue / switch provider / new pipeline),
  Owner report only after PASS.
- Independent Verification Agent: no-fix schema, other provider than the producer, deterministic
  checks (compile + self-test for Python) that override a model PASS.
- Build → Verify → Rebuild loop with a round budget that pauses for the Owner instead of lowering the bar.
- Claude Code / Codex CLI providers (reusing cheongwol's connectors) with quota failover.
- Checkpoint/resume from SQLite and per-project `HANDOFF.md` for any engine.
- Obsidian: relevant-note retrieval, verified archive on SAVE & CLOSE; PAUSE and CLOSE WITHOUT SAVE (confirmed).
- Global AI Intelligence read-only context for CEO planning.
- Tk Owner window, CLI, PyInstaller Windows build (`dist/AXBranch/AXBranch.exe`).

### Changed
- Nothing (first release).

### Fixed
- Prompts state that production agents cannot execute code, after the first live plan asked
  agents to "run the self-test" (would invite fabricated output).

### Verification
- `python -X utf8 -m unittest discover -s tests -t .` — engine/provider/release tests with a scripted provider.
- Live end-to-end run on the subscriptions: see "Live run" below.

### Known issues
- Two runners on the same project at once (GUI + CLI) are not locked out; a duplicate stage write fails loudly.
- Generated Python is executed for its self-test in a temp dir with a timeout under the same OS account — not a sandbox.
- Artifacts are single files; multi-file / repo-editing agents are not yet supported.
- Upgrade proposals: only the satisfaction gate exists; no proposal document generator yet.
- ax-works is not integrated.
