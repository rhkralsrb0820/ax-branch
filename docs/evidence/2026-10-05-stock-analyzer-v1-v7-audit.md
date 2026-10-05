# Audit: why P-20261003-bbad3c produced v1 … v6 (v7 never built)

Source: SQLite (artifacts, verifications, stage_outputs, events), artifact files, Windows System log.

| Ver | Producer (engine) | Verifier | Result | Root cause of failure / verifier finding | New or repeated cause | Was the rebuild justified? |
|---|---|---|---|---|---|---|
| v1 | Senior Python engineer (codex) | claude | PASS | — (old verification: no runtime acceptance) → **escaped**: Owner found it unusable (double-click ran the self-test) | new: AX Branch contract + no runtime check | yes (Owner problem) |
| v2 | Senior Python engineer (codex) | claude | FAIL | self-test fixture wrong (exit 1); HTTP 500 on self-test endpoint; demo JSON lacked disclaimer | new: product defects | yes |
| v3 | Senior Python engineer (codex) | claude | PASS | — (Owner later confirmed it works; asked for improvements) | — | yes (Owner request) |
| v4 | UX/finance reviewer as final producer (claude, 1 568 s) | codex | FAIL | (a) mixed separators fabricate prices (`103 104` → 103104) — real; (b) "rendered page unproven" — **AX Branch could not verify rendered pages** | (a) new product defect; (b) AX Branch capability gap | (a) yes; (b) no — needed engine work, not a rebuild |
| v5 | "Browser workflow and release verifier" (codex) | codex | FAIL (empty file) | producing stages had **no v3/v4 source** (engine gave it only to the final stage) and the CEO made **verifier roles the producers** → BLOCKED, 0-byte artifact | new: AX Branch pipeline defects | **no** — waste |
| v6 | same (codex) | codex | FAIL (empty file) | identical to v5; rework passed the **empty v5** forward as "previous version" | **repeated** | **no** — waste |
| (v7) | "Python engineer, final producer" (claude) | — | not built | regenerating a ~150 KB file in one turn: Claude timed out at 1 800 s; a later attempt switched to Codex, which also timed out | new: whole-file rewrite does not scale | **no** — an edit was needed, not a rewrite |

## Verdict
**Mostly B, inefficient pipeline.** v1→v4 were legitimate progressive discovery: one escape, then real product
defects and Owner requests. v5, v6 and the v7 attempts were waste caused by AX Branch itself:
- **missing context** to production stages;
- **verifier roles as producers**;
- an **empty build** reused as the baseline;
- **whole-file regeneration**.

The same root cause (no source given to producers) failed twice in a row (v5, v6).

## Usage (successful calls; failed calls were not recorded before 0.1.9)
- Claude 16, Codex 17.
- Largest Claude costs:
  - v4 full-file build 1 568 s;
  - v7 attempt 1 800 s (lost to timeout);
  - spec stages 527 s, 225 s and 221 s;
  - 15 calls refused by the usage limit (cheap, but they show heavy prior use).
- Owner/operator interventions on this project:
  - 3 instructions (goal, problem, request);
  - 1 confirmation;
  - 1 resume;
  - 4 recovery re-plans;
  - 6 of 9 engine sessions started by the operator (Claude Code), not the app.

## Fixed in 0.1.9 because of this audit
- Every stage gets the latest non-empty version and the Owner-confirmed one.
- Production-only pipelines.
- Empty builds are rejected without a verification call.
- Edit-based builds.
- Rendered-page probes with clicks.
- `expect_absent`.
- Failed calls are recorded (`call_failed`).
- Switch reasons are preserved.
- Sleep-aware timeouts.
- Machine-wide provider slots.

## Not rebuilt (reused instead)
- v4 was kept as the base: it passes its self-test and 20 of 23 original probes, and its real-browser click flow renders
  the one-line interpretation, evidence, risks and disclaimer.
- The remaining work was narrowed to one reproduced defect, fixed by edits.

## Outcome (2026-10-05 evening)
| Ver | Producer (engine) | Result | Note |
|---|---|---|---|
| v7 | edit-based fix on v4 (codex, 84 s, 4 edits) | FAIL | **harness flake**: headless Edge hung twice on the home probe; v7's page loads in 2–3 s (3/3 re-runs). Wasted one rebuild → `harness_retry` added |
| v8 | 4 more edits on v7 (codex, 50 s) | **PASS** | 24/24 criteria; 20/20 runtime steps; independently confirmed |

Not repeated: planning, the design/spec stages, v4's working code. Claude today: 8 calls (CEO re-plans,
verification, report; ~826 s); Codex: 2 product calls (134 s) + 2 development delegations (432 s).
