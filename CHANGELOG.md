# Changelog

Semantic versioning. Every release needs an entry with all five sections (enforced by
`tests/test_release.py`).

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
