# Changelog

Semantic versioning. Every release needs an entry with all five sections (enforced by
`tests/test_release.py`).

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
