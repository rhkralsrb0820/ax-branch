# AX Branch development team mode

Development of AX Branch itself (not the product's runtime agents):

| Who | Does |
|---|---|
| Claude Code — lead | architecture, cross-module integration, ambiguous decisions, review of delegated work |
| Codex — co-developer | bounded implementation, isolated bug fixes, tests, independent review |
| Local tools | tests, SQLite, git, hashes, process checks, builds — never an LLM |

These are not fixed roles. Each delegation and its outcome is logged in `DEV_LOG.jsonl`, so the split
can follow evidence.

## Delegating to Codex (no Owner relay)
1. The lead writes a structured handoff: `tasks/<id>.json` with goal, task, relevant files,
   **allowed files**, contract, constraints, acceptance tests and expected output.
2. Commit it, so the tree is clean and changes can be attributed.
3. Run `python devteam/delegate.py devteam/tasks/<id>.json`. Codex runs once (workspace-write sandbox)
   and exits. The script then checks deterministically: any changed file outside `allowed_files` is a
   scope violation, and the acceptance tests plus the full suite must pass. It also appends a measured record.
4. The lead reviews the diff, notes whether rework was needed in the log, and commits with attribution.

Rules learned so far:
- Don't edit the working tree while Codex runs. It breaks attribution.
- Codex's sandbox on this PC cannot run Python, so the host-side test run is the evidence.
- Check exit codes, never a piped `tail`.
- Parallelism only for genuinely independent files, within the 2 machine-wide provider slots.
- Use one watcher at most, and none when a completion notification exists.

## Record so far
| Task | Engine | Seconds | Scope | Host tests | Review |
|---|---|---|---|---|---|
| browser-click-probes | codex | 272 | ok | 64 pass | approved, then **rework needed**: proxy forwarded its own Host; found by the lead in live use |
| failed-call-observability | codex | 160 | ok | 68 pass | approved, no rework |
