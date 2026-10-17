# Changelog

Semantic versioning. Every release needs an entry with all five sections (enforced by
`tests/test_release.py`).

## [0.1.37] - 2026-10-17

### Added
- Bounded capability inventory for CEO decisions, including execution limits and unsupported evidence.
  Stages declare only the capabilities they need. Unknown capabilities and unavailable browser harnesses
  stop before production, including resumed execution; no silent tool installation or authority expansion.
- Per-operation capability attachment/revocation for model calls and verification harnesses, linked to the
  existing actual-provider call authority. Interrupted audit scopes are closed under the project lock.
- `python -m axbranch.demo --root PATH` reproduces deterministic FAIL -> changed pipeline -> PASS,
  capability-gap refusal and quota-interruption recovery with real generated-program execution and evidence.
  `--live` exercises subscription providers in an isolated workspace.

### Changed
- New plans declare stage capabilities; legacy plans infer their existing reasoning/code/web grants.
  Existing lifecycle, acceptance contracts, attempt ledger and durable strategy reviews are preserved.

### Fixed
- Failed contained-process construction leaked temporary files, open streams and a Windows Job Object.
  Failed Windows process resumption now fails closed and cleans up the suspended process.
- A provider could start after cancellation if a slot and memory were immediately available.
- Capability audit traffic displaced hiring and engine-assignment entries from the bounded Owner timeline;
  keep the full audit in SQLite and filter scope traffic before selecting the visible activity window.

### Verification
- Capability, sandbox and provider-resource regressions; original-code comparison demonstrates both
  cleanup and pre-launch cancellation defects. Full-suite and E2E results recorded in the integration report.

### Known issues
- Capability needs are declared by the planner; completeness is not proven for arbitrary natural-language goals.
- Leases select existing adapters and harnesses, not OS permissions. Generated code still uses the current OS
  account; D-SEC-1 remains open. No GPU training, clean Windows machine or desktop interaction is acquired.
- Scripted failure/replan evidence proves engine routing, not the quality of autonomous model decisions.

## [0.1.36] - 2026-10-16

Restart-persistence evidence: the first capability added from real-use evidence (P-20261016-554d44's goal judgment:
"no test stopped and restarted the app"; P-3a4f60 and P-3e5ca9 showed persistence only indirectly).

### Added
- Runtime probe `http_method: "RESTART"` (web only): the program's whole process tree is killed, as when the Owner
  closes the window, and started again in the same folder; later probes check the saved data on the new instance
  (new process id recorded). With a restart, the flow's launches share one temporary user profile, so data kept in
  the profile is not lost artificially.

### Changed
- The exact Owner launch runs on a copy of the program folder AS BUILT with a fresh profile (what the first
  double-click sees). Its first page is judged on content when it is the first probe of the whole flow; a later GET
  only has to answer without a server error.

### Fixed
- The exact Owner launch re-checked fresh-state expectations against data the verification flow had already saved
  (false FAIL; folder and profile storage alike).
- Long browser action flows were killed by a fixed 90 s real-time limit when the browser did not fast-forward its
  virtual time (seen under load in this release's own test run); the limit now grows with the flow's budget.

### Verification
- New runtime tests: data in the folder and in the profile survives a restart, memory-only data does not; the
  no-argument launch serving an empty page fails; saved verification data never reaches the Owner launch; a GET after
  a seeding step is not "first" (executed mutation: this test fails on the previous code).
- Codex targeted reviews (inspection): R1 NOT_READY (2) -> R2 NOT_READY (1) -> R3 NOT_READY (1) -> R4 NOT_READY (1,
  a test that passed with the old bug; fixed and proven by mutation). Full suite: see the commit message.

### Known issues
- Restart is a kill, not a graceful shutdown (the realistic case for closing a console window).
- GUI (desktop window) programs still get startup/survival checks only.

## [0.1.35] - 2026-10-16

Usable-v1 critical path, steps 1-5: minimum EVIDENCE_GAP closure, runtime experience available without an Owner
archive, recorded call authority. Designed with an independent Codex architecture challenge
(workspace/handoff/CODEX_ARCHITECTURE_RESULT.v1.md).

### Added
- Direct HTTP probes: PUT / PATCH / DELETE and exact request headers (`http_headers`, "Name: value"), e.g. a hostile
  Origin that must be refused. Invalid, non-Latin-1 or framing headers are a harness defect, never sent.
- Browser actions in a BROWSER probe's http_body: `fill:SEL=>TEXT`, `select:SEL=>VALUE`, `wait:SEL`, `expect:TEXT`
  (intermediate visible-text assertion), `dialog:accept|dismiss`; a plain item is still a click. A disabled or read-only
  field (incl. a disabled fieldset) cannot be filled.
- `knowledge.experience`: PROVISIONAL runtime experience of other projects for the CEO at planning and re-planning
  (fixed-template cards: failure category, evidence class, attribution cause + status, honest outcome; never check names,
  problem text, findings, feedback or goals). Derived at query time; projects closed without saving are excluded.
  Traced like any retrieval (`runtime_experience`). The vault, K0 and the KI challenger gate are unchanged.
- `providers.authority`: every call records the authority it had on the provider that actually ran it.

### Changed
- "Any status" (expect_status 0) never accepts a server error (5xx); a probe that expects one says so.
- Planner prompt documents headers, verbs and browser actions.

### Fixed
- Runtime checks replayed the first HTTP probe after the flow even when it was a POST (mutating twice), and judged its
  content after the flow had changed the data; the exact Owner launch did the same. Only a GET is replayed, judged only
  on "answers without a server error".
- A BROWSER http_path like '@127.0.0.1:9999/' could leave the app under test; paths must start with '/'.
- A missing expected text that happened to contain words like "connection lost" was read as product evidence.
- A server error only in the exact Owner launch's flow was not product evidence.

### Verification
- Full suite sequential, coverage-checked (see the commit message for the count); new tests for every fix above,
  including a real headless-browser CRUD flow (type, select, confirm/dismiss, intermediate assert).
- Codex targeted reviews (inspection; its sandbox cannot run Python): E1 NOT_READY (5) -> E2 NOT_READY (5) ->
  E3 NOT_READY (1) -> E4 NOT_READY (2: use structured 5xx evidence, not message text) -> E5 READY; every confirmed
  defect fixed with a regression test.

### Known issues
- Not yet exercised on a real project (next: integration run).
- Browser evidence is read from the page's own DOM: page code could forge it (not independent security proof).
- Runtime experience ranking is plain term overlap + failure signature; quality is measured from real use.
- Generated code still runs under the Owner's OS account (D-SEC-1, Owner-governed).

## [0.1.34] - 2026-10-16

Test #3 harness fix (validated on a real project), Decision/Experience Trace, Knowledge Intelligence foundation (KI-0,
offline only) and Outcome Attribution v1 (observational). Phase records: docs/evidence/2026-10-15-decision-trace-phase-closure.md,
2026-10-16-outcome-attribution-phase-closure.md, 2026-10-16-knowledge-intelligence-baseline.md.

### Added
- Canonical probe semantics shared by planner, runtime and T5: expect_status <= 0 (incl. -1) = any status;
  expect_exit < 0 = any exit.
- Runtime failure classification from step evidence: product / harness / infra / ambiguous. Invalid probe
  specification is harness, and its quoted text is never crash evidence.
- CEO probe review (HARNESS_REPAIR / PRODUCT_DEFECT / UNRESOLVED) when there is no product evidence; a harness
  repair re-verifies the SAME artifact. The review is durable across interruption.
- Owner-grounded contract changes: on Owner-feedback rework, an existing acceptance criterion may be removed or
  replaced only with the Owner's verbatim words as provenance; otherwise it is restored, and the runtime contract
  is preserved.
- Decision/Experience Trace: retrieval (exact query, presented item, source/prompt hashes) -> CEO ADOPTED/REJECTED
  -> applied decision that declares the one action it causes -> action -> outcome; verification retrievals have their
  own chain; `Store.experience_chain`; Owner Effort counts only Owner-initiated resumes/re-plans.
- `axbranch/kindex.py` (KI-0): derived, rebuildable FTS5 index over vault sections and DB experience cards, offline
  evaluation against K0 with deterministic labels and a project-clustered promotion gate. The CEO still uses K0.
- `axbranch/attribution.py`: Outcome Attribution v1 (observational). Each FAIL, unnecessary rebuild and pause gets an
  append-only `attribution_trace` (PRIMARY VERIFIED cause or explicit UNKNOWN; model judgment only ESTIMATED; the CEO's
  self-assessment never a source); a validated harness repair supersedes the FAIL it was opened for.

### Changed
- T5 preserves exact positive statuses, explicit exit codes, assertions, probe inputs and runtime mode unless a
  repair is validated as equivalent.
- Product-failure accounting (budget, repeat detection, identical-build guard) uses the same bounded gate as
  verification; harness checks never spend the product budget.
- REWORK, its strategy obligation and any budget/recurrence stop commit in one transaction.
- Same-artifact recovery (still VERIFYING) cannot add unapproved network connections; the expansion is deferred and
  recorded.

### Fixed
- Outcome attribution: a missing deliverable is never VERIFIED agent blame; rule errors are recorded, not raised;
  replay uses only evidence that existed then; responsibility names the provider that actually ran (Codex A1).
- Test #3 (P-20261010-c88366): a correct product failed 4 times on "status 201, expected -1", was treated as a product
  defect, rebuilt, EXHAUSTED; T5 undid the CEO's correct probe repair.

### Verification
- Full suite 284/284 (sequential, coverage-checked against collected ids); git diff --check clean.
- Codex independent review (inspection; its sandbox cannot run Python): trace round 4 READY, attribution A2 READY.
- Real runs: P-20261015-3a4f60 (trace chain), P-20261016-3e5ca9 (attribution live == replay, no rule errors).
- Historical attribution replay over a DB copy (live DB hash unchanged); evidence in
  workspace/checkpoints/2026-10-16-outcome-attribution-closed/evidence.

### Known issues
- HIGH EVIDENCE_GAP: the probe schema cannot type into a browser, run multi-step UI flows, send headers (Origin)
  or PUT/DELETE; affected claims are judged from code.
- Knowledge Intelligence challenger HOLD (4 labeled situations / 2 projects; gate 50 / 20). Experience reaches the
  vault only on an Owner "save" close.
- Attribution v1: no CEO_DECISION / EVIDENCE / EXTERNAL_DEPENDENCY rules; runtime observations are not VERIFIED causes.

## [0.1.33] - 2026-10-10

Re-planning uses knowledge searched for the current problem (autonomy gap 6).

### Added
- `Engine._replan_knowledge(pid, stage, focus)`: before a strategy review (after FAILs) and before an Owner-feedback
  diagnosis, the vault is searched for the goal plus the current failure findings or the new Owner feedback.
  - Other projects only; the result goes to the CEO as `relevant_knowledge`.
  - Provenance is recorded as `context_used` {stage, vault_notes, projects}, even when nothing matched.
- The STRATEGY and DIAGNOSE prompts ask the CEO to use what applies and name it.

### Changed
- Nothing else; the keyword retrieval is unchanged (no vector search).

### Fixed
- Knowledge was retrieved only at initial planning. A re-plan after a failure or Owner feedback never looked for
  lessons matching that failure.

### Verification
- engine tests pass (72 + 1 new): a matching lesson from another project reaches the strategy prompt with recorded
  provenance; the project's own note is excluded; a missing vault yields an empty result.
- Specified for Codex; Codex hit its usage limit before writing code, so Claude implemented it (engine failover per
  plan).

- Live (2026-10-10, no code change), P-20261009-bd147a:
  - the 0.1.33 CEO judgment was applied once to the legacy v5 PASS (no re-verification);
  - result: PARTLY → one autonomous rework → v6 PASS → DELIVER with gaps classified (outside authority / low
    value / minor).

### Known issues
- Whether the CEO's decisions change because of a retrieved lesson is not yet observed on a real project.

## [0.1.32] - 2026-10-10

CEO executive acceptance: Verification PASS is no longer automatically handed to the Owner.

### Added
- After a PASS, the CEO decides on the Owner's GOAL, not on the task list. The decision fields are
  `goal_satisfied` (yes/partly/no/unknown), `missing_evidence`, `next_action` (deliver/rework/owner_decision) and
  `directive`.
  - When a concrete change within its authority can close a material gap, the CEO orders the next production round
    itself (`ceo_directive`: objective, expected outcome, required evidence).
  - Bounded: at most 2 such rounds per Owner action, inside the failure budget.
  - The approved verification gate is unchanged.
- The acceptance decision sees the deterministic/runtime evidence and its own previous directive. The decision is
  recorded as 'executive rework' / 'executive acceptance'.
- Stop outcome OWNER_DECISION_REQUIRED when the CEO's next action is an Owner decision.

### Changed
- Producers of an executive rework get the CEO's directive (not the "previous version FAILED" instruction).
- Owner feedback replaces any pending CEO directive.

### Fixed
- Test #1: the CEO's own final judgment said the core goal (real prices) had no evidence of being solved, yet the
  engine delivered it to the Owner as done.
- A recorded PASS whose CEO report call was interrupted (quota) was verified again on resume. It now resumes at
  the acceptance step.

### Verification
- engine/supervisor/library/GUI tests pass (97+). New: rework once then deliver, cap, cap reset by an Owner
  action, no directive → deliver, owner_decision, budget, Owner feedback replaces the directive, REPORT failover,
  interrupted acceptance resumes without re-verifying, owner_decision stop outcome.
- Implemented by Claude. Tests and adversarial review by Codex: 5 findings, all fixed.

### Known issues
- Whether the live CEO uses rework well (not too eager, not too lax) is unproven on real projects.

## [0.1.31] - 2026-10-10

Strategy reviews can no longer lower the verification bar (autonomy gap 5).

### Added
- `engine.preserve_probes(old, new)`, applied when a strategy review returns a runtime spec.
  - Every existing Runtime Acceptance probe is kept.
  - A same-name probe may change how it runs (args, stdin, method, path, selectors), but its assertions only
    stay or grow: expect_contains/absent are united, and the status/exit expectations are kept.
  - New probes are added.

### Changed
- The decision "runtime probes dropped by strategy" became "runtime probes preserved", listing what was kept.
  STRATEGY_SYSTEM says probes are kept automatically.
- Owner-feedback diagnosis (an Owner change) is unchanged.

### Fixed
- In Test #1, strategy reviews dropped probes 13 times without the Owner. Verification checks could be removed or
  weakened under the same name.
- 0.1.28 identical-build guard: a bundle rebuild that dropped a refused (unsafe) file has the same hash as the
  refused build. It was wrongly rejected as identical; the guard now also compares the refused-files list.

### Verification
- Full suite 175: all pass except test_prose_or_missing_click_selector (headless Edge under load; passes alone).
  The bundle regression found by the full run was fixed and re-tested (bundle + engine: 65 pass).
- engine/runtime/supervisor tests pass (104). New: a dropped probe is restored; weakened assertions are restored
  and additions kept; integration with a scripted strategy.
- Implemented by Codex; reviewed by Claude.

### Known issues
- An existing probe whose expectation is itself wrong can only be changed through the Owner (feedback/ruling),
  by design.

## [0.1.30] - 2026-10-10

Explicit stop outcome (autonomy gap 1, minimal): why the engine stopped is recorded as one code.

### Added
- `state.stop_outcome(project)`, a deterministic mapping with no lifecycle change. Codes:
  - VERIFIED (OWNER_REVIEW);
  - BUDGET_REACHED;
  - EXHAUSTED (the same failure recurred after a forced change of approach);
  - OWNER_DECISION_REQUIRED (decisions, approvals, tools);
  - BLOCKED (harness/infra/quota/rejected/internal error);
  - OWNER_STOPPED;
  - CLOSING.
- A `stop_outcome` event is recorded when an engine session ends, without duplicating an unchanged outcome.
  HANDOFF shows the outcome.

### Changed
- Nothing else; pause texts and transitions are unchanged.

### Fixed
- A budget pause and an exhausted approach were indistinguishable to the Owner and the next session
  (both "paused, needs the Owner").

### Verification
- engine/supervisor/library/GUI/live tests pass (99). New: table over all stop texts, no duplicate outcome on a
  repeated run, VERIFIED in handoff.
- Implemented by Codex; reviewed by Claude.

### Known issues
- Classification follows the existing reason wording (an unknown pause defaults to OWNER_DECISION_REQUIRED).
- SUFFICIENT is not produced: verified sufficiency is PASS against the approved criteria.

## [0.1.29] - 2026-10-10

Independent verification is routed by the engine that actually built the artifact (autonomy gap 4, provenance).

### Added
- `Engine._actual_producer(pid, artifact)`: the provider recorded for the artifact's final production stage
  (stage_outputs). It falls back to the configured engine only when that record is gone, and says so.

### Changed
- `_verifying` prefers the engine other than the actual producer. The "verification ran on the producer's engine"
  decision compares against the actual producer and records `actual_producer` and `producer_source`.
- `metrics.provider_record` attributes verified/passed builds to the actual producer when recorded.

### Fixed
- After a quota failover of the final producer (e.g. configured claude, used codex), verification could run on the
  same engine that built the artifact without the same-engine warning (Test #1 had 31 provider handoffs).

### Verification
- engine/metrics/supervisor/library tests pass (82). New: failover routing, same-engine detection after failover,
  artifact-iteration scoping, metrics attribution, legacy fallback.
- Implemented by Codex; reviewed and integrated by Claude.

### Known issues
- Projects closed with their working context discarded have no stage records: their builds use the configured
  engine (marked 'configured fallback').

## [0.1.28] - 2026-10-10

Attempt memory (autonomy gap 3, minimal): the CEO sees which approach led to which result and does not pay to
re-verify a known failure.

### Added
- `engine.attempt_ledger(store, pid)`: each verification paired with the approach recorded before it (strategy
  decision or Owner-feedback diagnosis): verdict, stable failure code, top gating findings. It is derived from
  existing records only.
- The strategy review gets `attempt_ledger` and is told not to re-propose, unchanged, an approach that already
  failed with the same failure code.

### Changed
- A rebuild byte-identical to an earlier version that FAILED with a product finding is not verified again. It
  becomes an engine FAIL ("identical to vN"), whose stable failure code drives the existing forced change of
  approach. After a harness/infra-only FAIL, identical bytes are still verified.

### Fixed
- Identical rebuilds were re-verified, spending a verification round on a known failure.

### Verification
- engine/supervisor/library/GUI tests pass (80 + 1 new). New: ledger links approach → outcome (incl. ordering and
  bounds); an identical rebuild is not verified again; an identical rebuild after a harness-only FAIL is verified.
- Implemented by Codex; reviewed and integrated by Claude, who restricted the guard to product FAILs.

### Known issues
- The approach is the recorded decision text; semantic sameness of differently-worded approaches is not detected
  (only identical bytes and identical failure codes).

## [0.1.27] - 2026-10-10

Durable strategy review (autonomy gap 2): the CEO's decision to rethink after a FAIL survives interruptions.

### Added
- `strategy_pending` / `strategy_done` events around every strategy review that `_after_fail` decides.

### Changed
- `_rework` first runs an unfinished strategy review (newest only) before any rebuild. It also refuses to build
  when the failure budget is used up; Owner-feedback rework is unchanged.

### Fixed
- A strategy review refused for quota (or interrupted) was skipped on resume, and the project rebuilt the same way
  (P-20261003-bbad3c, FAIL #30).

### Verification
- engine + supervisor + library tests pass (70). New: a refused review runs before the next build, exactly once;
  an exhausted budget never builds again on resume.
- Implemented by Codex; reviewed and integrated by Claude (fix: only the newest pending review counts).

### Known issues
- A crash between the strategy commit and `strategy_done` can repeat that review once (harmless, bounded).

## [0.1.26] - 2026-10-10

Artifact Library + Develop.

### Added
- `axbranch/library.py`: the Artifact Library as an index over the existing projects/artifacts/verifications (no file
  copies).
  - Item = a lineage's verified result: title, type (Apps / Reports / Documents / Research / Data / Other,
    deterministic), current version, path, source project, created/updated, verification, versions and projects.
  - Version = depth in the lineage (v1 = the root project).
- Develop: `Engine.develop(base_project, goal)` creates a NEW project plus one immutable `develop_from` event that
  pins the exact verified base artifact (sha256 checked).
  - The CEO's planning gets `develop_from`: the base excerpt, base plan, Owner feedback, verification lessons,
    lineage and vault knowledge.
  - The first build starts from the pinned base version (`previous_artifact`; edit mode works on it).
  - Everything after that is the normal autonomous lifecycle. The base project and its versions are never changed.
- GUI [Library] window:
  - artifacts grouped by type, each with its current version, and its versions as children;
  - [실행] for Apps, [보기] for the others;
  - [Develop], which asks only for the goal;
  - [관련 프로젝트].
- CLI: `axbranch library`, `axbranch develop <project> "<goal>"`.

### Changed
- The archive evidence records a project's Develop lineage.
- `project_title` moved to `library` (the GUI imports it).

### Fixed
- Nothing.

### Verification
- 160 tests run: 159 pass; 1 headless-Edge test (test_collapsed_details) errored while two suites ran concurrently and passes when run alone (2/2). Scripted end to end:
  - develop → plan with develop_from → first build gets the base as previous_artifact → PASS → OWNER_REVIEW;
  - the library shows one artifact v2 with versions [base, new];
  - the base project, artifacts and verifications are unchanged.
- Branches keep their depth, and a changed base file is refused.
- Live (real DB, no AI call):
  - `axbranch library` lists 7 artifacts by type;
  - the develop context for 주식 분석 프로그램 holds lineage, v33 files, 35 base criteria, 9 Owner feedback
    entries, 10 lessons and its archive note.
- Independent Codex review: 6 findings fixed.

### Known issues
- Sibling branches of one artifact share a version number (both v2). The Library shows them as separate version
  rows, with their source project.
- No real Develop project has been run yet (no AI calls were spent).

## [0.1.25] - 2026-10-09

The Owner sees the verified result in one click, whatever its type.

### Added
- `Engine.result_info` / `Engine.open_result`: the verified result as the Owner should see it.
  - A document or a report of a command-line deliverable is shown. `.md` and `.txt` open in a read-only viewer
    inside AX Branch, with [프로그램 실행] when the result has a program. HTML, PDF and other documents open in
    their default app.
  - Web and window programs run as before.
  - Always from a fresh copy, never the recorded version. Event `owner_view`.
- The Owner panel button reads [결과 보기] or [결과 실행] to match.

### Changed
- A command-line program started for the Owner runs in a console that stays open (`cmd /k`), so its output stays
  on screen.

### Fixed
- P-20261009-bd147a (Test #2): [결과 실행] did run `python rh_lab.py` (3 owner_run events). The program printed its
  summary and exited, and the new console closed at once, so nothing was visible. The result itself,
  RESEARCH_REPORT.md, was never shown.

### Verification
- Engine + GUI tests pass (new: report shown inside AX Branch vs web app run; label; CLI console stays open).
- Live on a copy of the real DB, P-20261009-bd147a:
  - button label [결과 보기];
  - one click opens "AX Branch — RESEARCH_REPORT.md" with text identical to the verified report (10,546 chars);
  - [프로그램 실행] starts `cmd /k python rh_lab.py` in a new console;
  - v1 sha256 unchanged, verification still PASS.

### Known issues
- Markdown is shown as plain text (no rendering).

## [0.1.24] - 2026-10-09

[중단] works on a project that waits for the Owner.

### Added
- Nothing.

### Changed
- [계속 실행 / 재개] on a project paused from OWNER_REVIEW / PENDING_CLOSE / ARCHIVE_PENDING_APPROVAL restores that
  stage without launching a worker (there is no engine work there) and records the Owner action.

### Fixed
- [중단] did nothing on OWNER_REVIEW / PENDING_CLOSE / ARCHIVE_PENDING_APPROVAL projects. The window skipped the pause
  for those states. They now PAUSE as an Owner stop: `resume_state` keeps the exact stage, the supervisor never
  auto-resumes it, and the project, artifacts, knowledge and history are untouched. CLOSED is unchanged.

### Verification
- GUI + supervisor tests pass (new: stop → PAUSED → supervise leaves it → explicit resume → same stage, no worker;
  CLOSED untouched).
- Live on a copy of the real DB, P-20261003-97494b: PENDING_CLOSE → [중단] → PAUSED (resume_state PENDING_CLOSE);
  one real `axbranch supervise` pass reports "[PAUSED] Owner stopped" and leaves it paused;
  [계속 실행 / 재개] → PENDING_CLOSE; 0 workers started.

### Known issues
- None new.

## [0.1.23] - 2026-10-09

Project list layout.

### Added
- Hover tooltip with the full project title.

### Changed
- The list pane starts at ~280 px and keeps its width when the window is resized; the main area takes the rest.
  The divider can be dragged.
- Titles stay on one line and are cut with '…' only when they do not fit the measured pixel width. The status
  dot sits on a right-aligned tab at the pane's right edge, and the title gets all space left of it.

### Fixed
- 0.1.22 cut every title at 22 characters inside a narrow list, so projects were hard to tell apart.

### Verification
- GUI and release tests pass (new: cut only when needed, ~280 px pane, one line per project, full title on hover).
- Live layout check on a copy of the real DB:
  - 1180 px window: list 280 px, dots at x≈252;
  - resized to 900 px: list still 280 px, main area shrank;
  - divider dragged to 420 px: longer titles shown in full, dots at x≈392.

### Known issues
- The divider position is not remembered between sessions.

## [0.1.22] - 2026-10-09

Readable project list.

### Added
- The CEO's existing planning call also returns a short `title` (stored in the plan, no extra AI call). Older
  projects show a title derived from the goal; the goal itself is never changed.
- A status dot after each title, mapped from the internal state / supervisor status (DB state unchanged):
  green = 작업 중, orange = Owner 확인/승인 필요, blue = 대기/일시정지 (also not started yet), red = 오류/복구 필요,
  gray ✓ = 완료.

### Changed
- The left list shows only `title  ●`, not the internal state and the whole goal. The exact internal state stays in
  the project view on the right. No animation.

### Fixed
- The project list was hard to read (internal state prefix, the full goal as the name).

### Verification
- GUI, engine and release tests pass (new: the list shows title + dot, not the goal or the internal state;
  status mapping; click selection; goal unchanged).

### Known issues
- The list is a read-only text view: no keyboard navigation (mouse selection only).

## [0.1.21] - 2026-10-09

0.2 preparation: reuse past experience, measure Owner Effort, supervise while AX Branch is closed (D-AUTO-1).

### Added
- Readable Korean-first archive notes: 요약 / 최종 결과 / 문제 → 원인 → 해결 / Verification Lessons / Owner Feedback /
  남은 과제 / 재사용 지식 (each line names its source) / Owner Effort. The complete original record follows,
  unchanged, under Evidence, plus full Owner rulings and approvals.
  `Engine.rearchive(pid)` restructures a saved note in place: it keeps the Owner's file name, backs the old
  note up in the project folder and takes the closure date from the record.
- Satisfaction reason: an optional field in the finish dialog and `Engine.note_satisfaction`; written into the archive.
- `metrics.project_effort`: Owner interventions, feedback rounds, rework rounds, verification rounds, manual
  recovery, Owner Escape, automatic recoveries, elapsed hours, agent-active minutes, satisfaction. Counts
  predating the owner_action records are marked UNKNOWN. Stored as an `owner_effort` event at every close
  and restructure.
- D-AUTO-1: `axbranch autostart on|off|status` registers a per-user Windows Task Scheduler task (at logon + every
  5 minutes, one instance, no elevation) that runs the existing deterministic `axbranch supervise` pass: same
  recovery rules, supervise.lock, no AI. The pass sends one Windows notification per waiting episode when a
  project reaches OWNER_REVIEW or needs an Owner decision (closing steps excluded; a failed toast is retried)
  and appends `workspace/logs/supervisor.log`.

### Changed
- `knowledge.retrieve` (already in the CEO's planning context): a structured note is matched and excerpted by
  its title, 재사용 지식 and 요약, and returns note, project and evidence location. Korean request stopwords are
  dropped, and one trailing particle is stripped from Korean words.
- Detached workers leave the launcher's job object when allowed (a scheduled pass ends right after launching).
- `new`, `ruling` and the finish-dialog choices are recorded as Owner actions.

### Fixed
- Planning context received the first 1500 characters of a 200 KB archive (title and goal), not its lessons.

### Verification
- 152 tests pass. Live: Test #1 archive restructured with 0 original lines lost. Retrieval returns Test #1's
  reusable knowledge for related goals and nothing for an unrelated one. A real scheduled task in a throwaway
  workspace recovered a dead STAFFING worker with one resume and one worker, with no window open, then
  notified once. The real task is registered: LastResult 0, pass logged. Independent Codex review: 8 findings fixed.

### Known issues
- The scheduled task runs the source checkout (development mode); AXBranch.exe is still 0.1.12.
- A Task Scheduler task is per user and logon-bound: no supervision while the user is logged off.
- Retrieval is keyword-based; vector search was not added (not needed for the current vault).

## [0.1.20] - 2026-10-09

A project paused for provider quota resumes by itself after the stated reset time.

### Added
- `supervisor.provider_reset_at()`: the earliest reset time stated in the provider refusals.
  Handles "resets 12:10am" (next such local time after the pause) and "try again at Oct 9th, 2026 12:15 AM".
- Supervisor: a PAUSED `RateLimited` project resumes from its checkpoint with one worker once that time has
  passed (event `provider_retry`). It is not a failure recovery (no re-plan, no recovery count), retries at
  most once per 15 minutes, and holds the RECOVERING marker so no second worker starts.

### Changed
- Nothing else. A quota pause without a stated reset time still waits.

### Fixed
- P-20261003-bbad3c stayed in WAITING_FOR_PROVIDER after the Claude reset (00:10 KST). The supervisor only acted
  on STALLED/FAILED, so a quota pause was never re-checked.

### Verification
- 147 tests pass. Live (2026-10-09 00:20): Claude available on one minimal call; P-bbad3c resumed from its
  REWORK checkpoint with one detached worker.

### Known issues
- The automatic retry runs where the supervisor runs: the open AX Branch window, or `axbranch supervise --watch`.
  With both closed it waits for D-AUTO-1 (OS scheduler, still blocked by Owner decision).
- At the 10-08 23:53 pause the scheduled strategy review (FAIL #30) had not run, because its CEO call was the one refused.
  The resume continues from REWORK without it.

## [0.1.19] - 2026-10-08

The Owner can run the verified result from AX Branch.

### Added
- [결과 실행] in the Owner panel at OWNER_REVIEW: starts the latest verified (PASS) version the way the Owner
  launches it, using the runtime contract's exact launch (`python <entry>`, no arguments, its own console
  window). It runs from a fresh copy in `projects/<id>/run/v<N>`, so the recorded version is never touched.
  Documents open in their default app. Event `owner_run`.
- `Engine.launch_verified(pid)`.

### Changed
- The OWNER_REVIEW note points to [결과 실행].

### Fixed
- At OWNER_REVIEW the Owner needed the CLI or Explorer to run the verified artifact.

### Verification
- 146 tests pass. Dry run on P-20261003-bbad3c with a fake launcher: v31 copied to run/v31 (bytes
  identical), started as `stock_analyzer.py` with no arguments in a new console; v31 sha256 unchanged.

### Known issues
- Every press starts a new instance (the program picks the next free port if 8765 is taken).

## [0.1.18] - 2026-10-08

Harness evidence for approved criteria: click wait and visible result order (P-bbad3c #6); Owner rulings (#3).

### Added
- BROWSER clicks wait until the page's own fetch/XHR requests have completed AND CLICK_WAIT_MS (500 ms) have
  passed without request activity, up to SETTLE_MS (10 s). The counters are installed right after `<head>`,
  before the page's scripts. A timeout stops the sequence and reports incomplete harness evidence.
  Each click records `details_before`/`details_after`.
- Visible result order: the visible element holding each expected text (tag, id, DOM index, rendered top),
  `visible_order`, and `visible_order_ambiguous` for texts held by several visible elements or sharing one element.
- `axbranch ruling <id> <criterion> <text>`: an Owner decision on which evidence satisfies an approved
  criterion in automated verification. It is bound to the criterion's text (never moves to another
  requirement after an Owner change), passed to the Verification Agent as binding, and never adds or
  changes a criterion.

### Changed
- The browser time budget covers the per-click settle window.

### Fixed
- The fixed 300 ms post-click sleep did not follow the approved "completed requests plus at least 500 ms" rule.

### Verification
- 145 tests pass. Codex review: 5 findings fixed (quiet window restarted by
  request activity, element-based order with ambiguity, wrappers before page scripts, sync-XHR exception,
  ruling bound to criterion text).

### Known issues
- Requests from workers, WebSocket, EventSource and images are not counted in the settle window.

## [0.1.17] - 2026-10-08

Verification gate = approved criteria only; artifact versions are never overwritten (D-ART-1).

### Added
- Verdict schema: criteria carry their approved `index`; findings carry the `criterion` they violate
  (-1 = not an approved criterion).
- `verification_recommendations` event: findings outside the approved criteria, kept for the Owner.

### Changed
- PASS/FAIL = the deterministic checks + the approved acceptance criteria (project start or Owner change).
  Recommendations never gate a version. The model's own overall verdict is no longer the gate. An approved
  criterion the verifier did not judge blocks the PASS.
- The verifier is told not to demand evidence the approved runtime spec does not produce. OS-level network
  isolation is a separate capability (D-SEC-1), outside the gate.
- A build claims its version folder exclusively. An existing folder makes it the next free version, and a
  failed commit removes only the new folder.

### Fixed
- A failed rebuild could overwrite an existing version's files (P-bbad3c v31, 10-08).

### Verification
- 143 tests pass. Independent Codex review: 5 correctness findings fixed (recommendations kept out of
  rework/strategy/diagnosis and failure codes, one index rule, checks-only failure not attributed to a criterion,
  a committed version folder is never deleted on cancel). New tests: recommendations do not gate; a leftover version folder
  is never written; a failed commit leaves the earlier version's sha256 intact.

### Known issues
- No read-only file attributes on disk (the engine refuses the write; the OS does not).
- D-SEC-1 (OS firewall isolation) is not implemented; it needs Owner-approved system setup.

## [0.1.16] - 2026-10-08

Verification no longer reaches the internet; the exact Owner launch judges transport, not launch-specific content.

### Added
- The audit-hook wrapper refuses non-local connects, sendto/sendmsg and name lookups (getaddrinfo,
  gethostbyname/addr, getnameinfo) with PermissionError and records them as blocked;
  `network.external_unblocked` counts what was not refused.

### Changed
- Exact Owner launch, HTTP flow on the same process: a lost connection, a failed request or a 5xx response fails
  the step. Content expectations are recorded only, because probes target the verification launch arguments
  (e.g. --offline).

### Fixed
- 0.1.15 ran the spec's probes on the online no-argument launch: P-bbad3c's v31 then contacted its approved hosts
  (Google News, SEC, Stooq) during verification, and an --offline-only expectation failed.
- Bytes host names (b'localhost') were logged as external.

### Verification
- 139 tests pass. Independent Codex review of the delta: 4 findings, 3 fixed.
  The 4th is a documented limit (below).

### Known issues
- The refusal is in-process and best effort, not an OS firewall. Child processes, native code and the Windows
  asyncio Proactor connect path are not intercepted, and connect() to a host name resolves it before the
  refusal. A real zero-egress guarantee needs an OS firewall rule, which is system setup and needs the Owner.

## [0.1.15] - 2026-10-08

Runtime Acceptance harness: the four verifier gaps reported on P-20261003-bbad3c v31 (HARNESS_BLOCKED).

### Added
- BROWSER probes judge the visible text: `document.body.innerText`, captured at the end of the browser's
  time budget after the scripted clicks. Recorded: browser exe and user agent, click records, every
  `<details>` open state, page loads in the tab (no-reload), elements holding must-not-contain text with
  `checkVisibility()` and their `<details>` state, proxied browser requests, browser stderr separately.
- Outbound record: every artifact launch runs through an audit-hook wrapper (socket connect/sendto/getaddrinfo,
  subprocess, os.system/startfile, webbrowser.open); `runtime.check()` returns `network` with external
  connections (by address; loopback, IPv4-mapped loopback and local IPC separated) and browser-open requests.
- Exact Owner launch: full command, browser-open requests of that process, observation of at least 10 s,
  the HTTP flow on the same process (failures fail the step), and a second launch while the port is busy
  (observation only).
- Subprocess probe records: executable, full command, cwd, environment keys, separate stdout/stderr, start time.

### Changed
- Probes without `http_path` no longer get `http_method` GET in web mode (they run as subprocesses; noted).
- `sandbox.start/run`: optional `extra_env` and `split` (separate stderr).

### Fixed
- Collapsed `<details>` content was judged as shown (`--dump-dom` serialized it). Browser stderr was mixed
  into the judged text.

### Verification
- 138 tests pass (new: collapsed vs opened details in real headless Edge, late content and placeholder-like
  selectors, outbound/browser-open record, subfolder entry imports, address classification, exact-launch
  observation and flow failure, subprocess probe dispatch).
- Independent Codex review: 7 findings, all fixed.

### Known issues
- D-ART-1 (immutable artifact versions) is recorded as P0 backlog, not implemented.
- Under the wrapper `sys.argv[0]` is the absolute entry path (`__file__` and `sys.path[0]` match a direct run).
- AXBranch.exe is still 0.1.12.

## [0.1.14] - 2026-10-08

Orchestration defect D-ORCH-1 (P-20261003-bbad3c v25→v31): no product rebuild for verifier or machine
failures, stable repeat detection, stage-correct recovery.

### Added
- Verification findings carry `kind`: product | harness | infra.
- `engine.failure_code()`: a structured failure code (finding kinds + failing deterministic steps / engine
  rejection) for repeat detection.
- Heartbeats carry sleep-excluded time (`supervisor.awake()`).

### Changed
- A FAIL without a blocking product finding no longer rebuilds: PAUSED `HARNESS_BLOCKED` (waits for a verifier
  fix) or `INFRA_FAILED` (automatic re-verify), same version, resume_state VERIFYING.
- The same failure code after a forced change of approach pauses with NEEDS_DECISION instead of rebuilding again.
- A project that died in VERIFYING is recovered by re-verifying, never by a re-plan.
- One supervisor pass per project at a time; the RECOVERING marker stays until the relaunched worker starts.
- `review <id>` runs the engine for any active state it returns (incl. VERIFYING).

### Fixed
- Recovery re-plan from VERIFYING rebuilt into the already-built iteration → `IntegrityError` on stage_outputs.
- PC sleep made a live worker look stalled (heartbeat and provider idle on wall-clock time) and recovery killed it.
- One worker death recorded as two recoveries by two supervisor passes 2 s apart.
- Repeat detection compared the verifier's wording; the same findings in new words never matched.

### Verification
- 130 tests pass (new: harness-only pause and re-verify, rebuild iteration guard, failure codes, PASS with
  harness-only findings, duplicate/concurrent supervisor passes, VERIFYING recovery, sleep vs heartbeat).
- Independent Codex review: 6 findings, all fixed in this release.

### Known issues
- Not yet verified live on P-20261003-bbad3c (PAUSED by the Owner).
- v31's worker exit (10-08 ~19:16–19:43) has no traceback or crash record; its cause is not established.
- D-AUTO-1 (OS scheduler) is still not implemented, by Owner decision, until these fixes are verified live.
- AXBranch.exe is still 0.1.12.

## [0.1.13] - 2026-10-08

A project waiting for the Owner can now be answered inside AX Branch.

### Added
- Owner panel in the project view, shown only while the project is WAITING_FOR_OWNER: plain-language
  feedback, [수정 요청 / 계속], [완료], [중단]; "실행해 보니" (works?) when a verified version is under
  review; approve/decline for connection approvals.
- `AXBranch-dev.cmd`: double-click to run the latest source (development-mode GUI checks between exe builds).

### Changed
- `owner_review` also answers a project paused for the Owner (failure budget used up, NEEDS_DECISION):
  feedback → same project REWORK (CEO diagnosis, re-planned agents/pipeline, rebuild, verification) with a
  fresh round budget and all history and findings kept; no text → +3 rounds; finish → PENDING_CLOSE.

### Fixed
- At WAITING_FOR_OWNER the review dialog failed ("the Owner reviews a delivered project") and only the CLI
  could continue the project (Test Project #1 after v24).

### Verification
- 122 tests pass, including the GUI flow: paused project → panel → feedback → [수정 요청 / 계속] → the
  same project reaches OWNER_REVIEW with the feedback recorded.

### Known issues
- AXBranch.exe is still 0.1.12 (the Owner had it open); rebuild at the next milestone.

## [0.1.12] - 2026-10-08

Test Project #1 (v21) failed verification for reasons that were mostly AX Branch's, not the product's.
Re-checking v21 unchanged with the fixed harness: 7 runtime failures → 3, all misconfigured probes.

### Added
- Every agent (stages, producer, verifier, strategy, Owner rework) receives `external_connections`: the
  Owner's recorded decision per domain, authoritative over older notes.
- A misconfigured probe is reported as such, with the element ids on the page, and sends the FAIL to a CEO
  strategy review (the probe's author) instead of developer rework.

### Changed
- Planning prompt: BROWSER `http_body` = CSS selectors separated by `||` (clicks exist since 0.1.9; the
  prompt still said "clicking is not available"); web-mode probes with no path run as command lines.
- A strategy review cannot silently drop Owner-approved connections.

### Fixed
- Web mode sent command-line probes to the server as `GET ''` and reused one for "again after flow" and the
  exact Owner launch (4 of 7 v21 failures).
- HTTP probe responses were read only up to 200 000 bytes (a 236 KB JSON lost its last keys); now 5 MB.
- A prose or missing click selector stopped the clicks silently and was reported as "page lacks …".
- v21 hard-disabled fetching ("Owner 승인 대기") although the Owner had approved all five domains: a strategy
  review (10-06 22:04) had set network access to none and agents saw a stale "declined" note. bbad3c's plan
  was repaired from approvals #16–20.

### Verification
- 119 tests pass; new tests for CLI probes in web mode, large responses, misconfigured selectors (headless
  Edge), CEO routing of misconfigured probes, and approved connections surviving a strategy review.
- Live: the CEO's next review (plan v16) restored network access, rewrote the 3 probes with real selectors
  and removed the "pending Owner authorization" instruction; Test Project #1 resumed (+3 rounds).

### Known issues
- Same as 0.1.11 (D-AUTO-1, review #7). The strategy review dropped some probes it judged redundant; this is
  recorded as a decision and visible in the timeline.

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
