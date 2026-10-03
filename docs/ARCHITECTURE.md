# AX Branch architecture (v0.1)

```
Owner ── GUI / CLI ──► Engine (淸月 AI CEO driver) ──► providers.call ──► claude -p | codex exec
                          │   ▲                              (quota → other provider)
                          ▼   │
                 SQLite runtime state (workspace/axbranch.sqlite3)  ◄── Source of Truth
                          │
      knowledge.retrieve (Obsidian, relevant excerpts)   knowledge.intel (GAI DB, read-only)
                          │
           Owner SAVE & CLOSE ──► knowledge.archive ──► Obsidian note (read back & verified)
```

## Modules (`axbranch/`)

| Module | Role |
|---|---|
| `governance.py` | Fixed Owner rules: round budget, strategy cadence, approval-only actions, paid lock, satisfaction gate. |
| `state.py` | SQLite tables (projects, agents, stage_outputs, artifacts, verifications, events), state machine, structured `handoff()`. |
| `providers.py` | Claude Code / Codex CLI as interchangeable engines; quota failover. |
| `engine.py` | CEO planning, staffing, build, deterministic checks, independent verification, rebuild, strategy review, CEO report, close/archive. |
| `knowledge.py` | Vault retrieval, GAI read-only search (relevance-gated, provenance recorded), verified archive notes. |
| `runtime.py` | Runtime Acceptance: launch the artifact the way the Owner will (cli / web / gui), run probes, record evidence. |
| `sandbox.py` | Runs generated self-tests: clean env, Job Object limits, whole tree killed. |
| `artifacts.py` | Single-file and multi-file (bundle) artifacts: safe paths, sha256 manifest, integrity, text view. |
| `gui.py`, `__main__.py` | Owner window and CLI. |

## Lifecycle

`CREATED → PLANNING → STAFFING → EXECUTING → VERIFYING → (REWORK → STAFFING → EXECUTING → VERIFYING)* → OWNER_REVIEW → PENDING_CLOSE → ARCHIVE_PENDING_APPROVAL → ARCHIVING → CLOSED`;
**Owner review loop (0.1.8):** in OWNER_REVIEW the Owner reports *works* (→ PENDING_CLOSE), *problem* or
*change* (→ REWORK on the same project, history kept). In REWORK with new Owner feedback the engine first
runs Runtime Acceptance on the delivered version (reproduction), the CEO diagnoses from the feedback and
that evidence and revises criteria / runtime spec / pipeline (plan_version+1), the revised acceptance is
run against the old version (it should fail if the problem is real), then the normal build → verify loop
runs and the verified version returns to OWNER_REVIEW.
`PAUSED` from any active state (Owner stop, provider fault, both quotas exhausted, missing tool,
round budget) remembers `resume_state`.

## Agents

- **淸月 AI CEO** (permanent): plans (goal interpretation, acceptance criteria, lenses, pipeline,
  provider per stage, required tools), reviews strategy every 2 FAILs (continue / switch provider /
  new pipeline), writes the Owner report — only after PASS.
- **Verification Agent** (permanent): separate prompt, schema with no content field (cannot fix),
  runs on the *other* provider than the producer when possible, sees deterministic check output and
  earlier findings. PASS is gated in code: model verdict PASS **and** every criterion met **and**
  no critical/major finding **and** deterministic checks pass (self-test via `--self-test`) **and**
  Runtime Acceptance passes (the artifact launched as the Owner launches it, primary flow exercised).
- **Temporary specialists**: one row per role+provider in `agents`; hired from the CEO's pipeline,
  kept across rework, marked `replaced` on strategy change, `terminated` at close.

Agent = role + goal + context + permissions + tools. The provider is just the engine for a turn.
Production agents get no shell and no file writes (CLI flags); they return content as JSON and the
engine writes the artifact. Web access only for stages the CEO marks `web`.

## Safety rails

- One session per project (`run.lock`, OS file lock). Refused sessions exit 2 / show in the GUI.
- Unexpected errors pause the project with the reason; traceback in `workspace/logs/engine-errors.log`.
- Schema version in `PRAGMA user_version`; older code refuses a newer database.

## Continuity

Every step commits to SQLite before the next; `run()` recomputes the next step from the DB. After
each step `workspace/projects/<id>/HANDOFF.md` is regenerated (goal, state, next action, plan,
agents, completed stages, artifacts + sha256, last findings, decisions, provider handoffs,
constraints, resume command). Any engine continues with `python -m axbranch run <id>`.
Within a run, a quota refusal moves the same turn to the other provider; the preferred provider is
tried again on the next turn, so work returns to it when its quota is back.
