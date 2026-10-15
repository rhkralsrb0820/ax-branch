# Development update — usable-v1 critical path steps 1-5, integration run (2026-10-16)

Release 0.1.35 (local commit 0b5050a). Real run P-20261016-554d44 (dev channel, nothing staged): a to-do web app
the Owner would use daily (add by typing, edit, done, confirmed delete, search, persistence, cross-site protection).
Evidence: workspace/handoff/integration_P-20261016-554d44.{log,json}; Codex rounds CODEX_REVIEW_RESULT.E1-E5.md.

## Result
v1 PASS on the first build (V-20261016-1d0ca9, 21 runtime steps), CEO goal judgment: deliver. State OWNER_REVIEW
(the Owner's acceptance is separate and pending). `check` consistent; chain checker: no integrity problems, no rule errors.

## New capabilities exercised for real (planned by the CEO, executed by the harness)
- PATCH / DELETE probes; exact headers: `Origin: http://evil.example` edit and delete refused 403, form-style
  cross-site POST refused 403, `Host: evil.example` (DNS rebinding) refused 403, data intact after the attacks.
- Browser flows: `wait:` / `fill:#new-title=>보고서 작성` / click / `expect:` / edit; reload persistence, then
  `dialog:accept` + delete + `expect:할 일이 없습니다`. Both passed.
- Mutation-safe post-flow check: only `GET /` replayed.

## Runtime experience without an Owner archive
Planning retrieved 3 vault notes (K0) and 3 PROVISIONAL runtime-experience cards (X0) from un-archived projects
P-20261015-3a4f60 and P-20261012-cfa1d6. The CEO ADOPTED all three with stated decision changes (e.g. "added wait:
actions before interacting with the page" from a cfa1d6 browser-check failure of UNKNOWN cause; the explicit --self-test
exit contract from a VERIFIED product failure), and rejected one vault note with a reason. Improvement: UNKNOWN
(no counterfactual).

## Least privilege
All 5 provider calls record their authority on the provider that ran them (no shell, no file writes, no MCP, web 0/5).

## Observations from real use (not defects; candidates by evidence class C)
- The CEO noted no probe restarts the app and re-checks data (restart persistence is shown indirectly): a probe
  capability "stop and relaunch the same instance's data" would close it.
- The CEO suggested checks should not assume fresh ids (probes use /api/todos/1 on a fresh instance: valid today).
- Browser evidence is page-controlled DOM (known limit; security claims here also rest on direct HTTP probes).
