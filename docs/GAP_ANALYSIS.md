# AX Branch gap analysis — 2026-10-05 (v0.1.9)

Question for every item: does it reduce the work the Owner must personally do, at equal or better
quality, safety and verifiability? Evidence = SQLite/project files/tests/this repo, not intent.

## 1. Why use AX Branch instead of Claude/ChatGPT/Gemini directly?

| Claim | Evidence | Verdict |
|---|---|---|
| Owner manages the goal, not the AI | P-bbad3c: 3 Owner instructions → 32 AI turns run by AX Branch (10.7 per instruction); 8 automatic provider switches with no Owner relay | **Real, measured** |
| Results are verified before the Owner sees them | v2 (HTTP 500, missing disclaimer) and v4 (data-integrity bug) were stopped by self-test + Runtime Acceptance + Verification Agent | **Real** |
| Survives provider limits and interruptions | genuine Claude usage limit (2026-10-04 02:27) → Codex continued; 13.7 h PC sleep → state intact, resumed | **Real** |
| Less Owner effort than direct AI | 4 of 7 engine sessions on P-bbad3c were started by an operator (Claude Code), not the app; 2 recovery re-plans were manual; v1 escaped to the Owner unusable | **Not yet demonstrated** |
| Faster than direct AI | the stock analyzer took hours of wall time and ~30+ calls; a direct chat would have produced a first version in minutes (unverified) | **No — slower; value is verification and continuity, not speed** |

Honest position: AX Branch already does things direct AI use does not (verified delivery, continuity,
same-project feedback loop, audit trail). It does **not yet** demonstrably reduce total Owner effort:
the Owner still needs an operator for recovery, and there is no measured baseline against direct use.

## 2. Capability classification

| Capability | Status | Evidence / demonstrated problem | Priority |
|---|---|---|---|
| CEO goal interpretation & dynamic pipeline | IMPLEMENTED | every project; CEO reinterpreted vague goal after Owner feedback | — |
| Dynamic temporary agents | IMPLEMENTED | agents hired/replaced per plan; but CEO once made *verifier* roles producers → BLOCKED/empty builds | fixed 0.1.9 (rule + empty-build gate) |
| Claude/Codex routing | PARTIAL | per-stage provider chosen by CEO from prose reasoning only; no track record used | **P8: add provider track record to CEO context** |
| Automatic delegation Claude → Codex | PARTIAL | sequential stage handoff + quota failover work; no parallel independent tasks | parallel: NOT NOW (resource evidence) |
| Verification gate | IMPLEMENTED | self-test, model verdict, criteria, gate override | — |
| Runtime Acceptance | IMPLEMENTED | cli/web/gui, exact Owner launch, lost-connection detection; rendered pages via headless Edge (0.1.9) | — |
| Owner feedback loop | IMPLEMENTED | two-question review, plain-language requests, same project (live on P-bbad3c) | — |
| Continuity / provider handoff | IMPLEMENTED | genuine usage limit → Codex; Codex CLI as driving session (0.1.2) | — |
| Crash / interruption recovery | PARTIAL | state always recoverable; but resuming after a misdirected plan needed a manual `replan` | P6 |
| Observability | IMPLEMENTED | call_start/call events, live ACTIVITY (provider, pid, elapsed, streamed output) | — |
| Resource management | IMPLEMENTED (basic) | machine-wide 2 provider slots, 1 GB memory floor, sleep-aware timeouts (0.1.9) | — |
| Security boundaries | PARTIAL | generated code: clean env + Job Object; same OS account can still read files / use network | needs Owner (separate account) |
| Permissions / governance | IMPLEMENTED | Owner-only actions, external-connection approval gate (0.1.9), paid lock | — |
| Auditability | IMPLEMENTED | events, hashes, evidence docs, git | — |
| Knowledge reuse | PARTIAL | archive retrieved into a later plan once (P-d356e8); only on SAVE & CLOSE | — |
| Experience → better decisions | MISSING | knowledge is retrieved as text; nothing feeds engine choice, pipeline shape or verification strategy | **P8 (track record)** |
| Impact measurement | PARTIAL | `axbranch effort` (0.1.9): measured counts; minutes and direct-AI baseline UNKNOWN | P9: record Owner review time |
| AI Intelligence | PARTIAL | read-only retrieval at planning + provenance; no Owner-facing digest / "what matters today" | P10 (later) |
| AX Works | MISSING | no AX Works data on this PC; integration plan only (`INTEGRATION.md`) | P11 (later) |

## 3. Samsung AI Forum 2026 principles (design principles from public event information; not a Samsung architecture)

| Principle | AX Branch today |
|---|---|
| Intelligence → execution → measurable impact | Executes and verifies real artifacts; impact measured only as counts (no business outcome yet) |
| evidence → plan → action → approval → verify → feedback → result | All links exist; the "evidence" link (GAI/knowledge) is weak, "result" is not tied to business outcomes |
| More autonomy needs stronger permissions/governance/escalation/audit | Approval gates, Owner-only actions, audit trail; generated code is contained, not isolated |
| Observable and recoverable execution | Yes (activity, events, checkpoints); recovery from a bad plan still needs a human `replan` |
| Feedback & experience improve future execution, governed | Feedback improves the *same* project; cross-project improvement is MISSING |
| AI output ≠ impact | Effort KPI added; Owner minutes and direct-AI baseline not yet measured |

## 4. Deliberately NOT implemented now
- Parallel agent execution: no demonstrated independent work units; the low-memory reap was caused by
  stacked watcher loops (operator), and sequential runs met every deadline. Slots now cap concurrency.
- Flutter / Docker / new frameworks or databases: no demonstrated need.
- Email / notifications: external communication needs Owner authorization; nothing to deliver yet.
- AI Intelligence digest and AX Works integration: below priority 1–9; AX Works has no data here.
- Automatic plan re-generation on every resume: `replan` is explicit until there is evidence of when
  it should trigger automatically.
