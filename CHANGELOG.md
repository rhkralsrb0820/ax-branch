# Changelog

Semantic versioning. Every release needs an entry with all five sections (enforced by
`tests/test_release.py`).

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
