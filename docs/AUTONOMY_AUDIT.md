# AX Branch Autonomy Audit

AX Branch implements an autonomous artifact-production workflow: a Goal becomes a persisted plan, temporary agents produce versions, verification gates delivery, and a supervisor performs bounded recovery. The broader North Star remains **PARTIAL**: deciding how to investigate, remember attempts, change direction, challenge conclusions, and stop appropriately across different kinds of goals.

Scope: static inspection of permitted `axbranch/*.py`, relevant `tests/*.py`, `docs/TASK_STATE.md`, `CHANGELOG.md`, and the supplied evidence JSON. No projects, Python, tests, providers, or scheduler tasks were run. Test citations describe assertions in source, not a fresh passing run. Current code takes precedence over historical backlog descriptions.

`E` below means [`2026-10-10-autonomy-audit-evidence.json`](evidence/2026-10-10-autonomy-audit-evidence.json), selecting `projects[]` by the cited project ID. All observed quantities come from E. Missing event keys mean **not listed**, not measured zero. Proposed fields and tests below are future work.

## Capability matrix

IMPLEMENTED means executable behavior exists, not universal effectiveness. PARTIAL includes prompt-only assurances or incomplete enforcement. MISSING means no implementation found. Stop labels below describe semantics; most are not literal database states.

| Capability | Status | Evidence | Gap |
|---|---|---|---|
| CEO goal interpretation | IMPLEMENTED | `axbranch/engine.py:Engine._planning`, `PLAN`; interpretation and criteria are persisted. | No independent check that the interpretation preserves the Owner's whole goal. |
| Planning | IMPLEMENTED | `engine.py:Engine._planning`, `Engine._sanitize`; `state.py:Store.update`. | A bounded linear production pipeline, without an executable investigation graph. |
| Dynamic staffing / temporary roles | IMPLEMENTED | `engine.py:Engine._staffing`, `Engine._strategy`; `state.py:Store.add_agent`, `Store.end_agents`. | Role selection is dynamic; the production-only role restriction is prompt guidance. |
| Engine selection | PARTIAL | `engine.py:STAGE`, `Engine._strategy`; `providers.py:call`; `metrics.py:provider_record`. | Stage routing works, but build outcomes are attributed to the agent's configured engine, which can differ after failover. |
| Tool selection | PARTIAL | `engine.py:Engine._planning`, `TOOL_CANDIDATES`; `providers.py:run_claude`, `run_codex`; `test_engine.py:test_missing_tool_asks_owner`. | Installed-tool discovery and web toggles exist; arbitrary required tools have no execution dispatcher or fallback-selection loop. |
| Knowledge retrieval / RAG | IMPLEMENTED | `knowledge.py:terms`, `retrieve`, `intel`; `engine.py:Engine._planning`, `Engine._verifying`. | Keyword retrieval augments prompts; queries are fixed by the engine, and consumption is not enforced. |
| Previous-project knowledge reuse | PARTIAL | `knowledge.py:archive`, `retrieve`; `library.py:develop_context`; `test_knowledge_effort_autostart.py:test_readable_archive_keeps_every_original_record_and_is_retrieved_for_planning`. | Archive lessons and Develop context reach planning; adopted lessons are not tracked into actions or outcomes. |
| Failure memory | PARTIAL | `engine.py:failure_code`, `Engine._repeated_failure`, `Engine._executing`; `test_engine.py:test_failure_code_ignores_verifier_wording`. | Findings persist, but repeat codes need deterministic failures and do not identify recurring unsupported research claims. |
| Attempt memory | PARTIAL | `state.py:Store.save_output`, `Store.output`, `Store.events`; `engine.py:Engine._executing`, `Engine._strategy`. | Checkpoints and histories exist; no structured attempt links approach, evidence, novelty, outcome, and next decision. |
| Duplicate / novelty protection | MISSING | `engine.py:Engine._executing`, `Engine._repeated_failure`; `artifacts.py:sha`, `write_bundle`. | Hash integrity, duplicate-path rejection and failure repetition do not prevent repeating an unchanged idea or experiment. |
| Replanning: trigger and timing | PARTIAL | `engine.py:Engine._after_fail`, `Engine._owner_rework`, `Engine.replan`; `supervisor.py:_supervise`. | Engine triggers on FAIL cadence/repetition/misconfigured probes; supervisor on repeated worker failure; Owner on feedback/manual replan. Pending strategy work is not durable. |
| Retry / recovery | IMPLEMENTED | `providers.py:call`; `supervisor.py:_supervise`, `_provider_retry`; `test_supervisor.py:test_repeated_death_in_verifying_reverifies_instead_of_replanning`. | Bounded process recovery exists; quota retry requires a stated reset, and recovery cannot diagnose conceptual stagnation. |
| Verification | PARTIAL | `engine.py:Engine.checks`, `Engine._verifying`; `runtime.py:_check`, `_rendered`; `test_engine.py:test_fail_rebuild_pass_deliver_and_save`. | Deterministic failures override model approval; document substance and GUI usability lack comparable independent execution coverage. |
| Independent challenge: engine / role / deterministic / adversarial | PARTIAL | `engine.py:Engine._verifying`, `VERIFY_SYSTEM`, `VERDICT`; `test_engine.py:test_verifier_on_producer_engine_is_recorded`. | Separate role and deterministic checks exist; engine identity uses the planned producer, while adversarial method and lens coverage are unenforced. |
| Owner review | IMPLEMENTED | `engine.py:Engine.owner_review`, `Engine._owner_rework`, `Engine.add_ruling`; `gui.py:App.review`, `App._owner_panel`. | Feedback drives same-project diagnosis/rework; baseline preservation and successful reproduction are not mandatory gates. |
| Project lifecycle | IMPLEMENTED | `state.py:TRANSITIONS`, `ACTIVE`, `Store.set_state`; `engine.py:Engine._run`, `Engine._close`. | A failed archive can leave `ARCHIVING`, outside `ACTIVE` and supervisor candidates; unattended archive recovery is absent. |
| Artifact lifecycle / Library / Develop | IMPLEMENTED | `engine.py:Engine._executing`, `Engine.develop`; `library.py:entries`, `base_artifact`; `test_library.py:test_develop_is_a_new_autonomous_project_that_starts_from_the_artifact`. | Versions and pinned lineage are protected; Develop's real project run remains unrecorded in `docs/TASK_STATE.md`. |
| Supervisor / unattended operation | IMPLEMENTED | `supervisor.py:supervise`, `_supervise`; `autostart.py:task_xml`, `notify_waiting`; `test_supervisor.py:test_owner_stop_is_never_auto_resumed`. | The scheduled task needs an interactive logged-in user; current registration was not inspected. |
| Stop: VERIFIED | IMPLEMENTED | `engine.py:Engine._verifying`, `Engine._deliver`; `state.py:ACTIVE`. | PASS delivers to `OWNER_REVIEW`; this establishes approved artifact criteria, not unrestricted achievement of the original ambition. |
| Stop: SUFFICIENT | MISSING | `engine.py:STRATEGY`, `REPORT`, `Engine._deliver`; `state.py:TRANSITIONS`. | No evidence-based adequacy outcome distinct from PASS or an Owner decision. |
| Stop: EXHAUSTED | MISSING | `engine.py:STRATEGY`, `Engine._after_fail`; `state.py:TRANSITIONS`. | No exhausted-approaches outcome; repeated failure or a consumed budget instead asks the Owner. |
| Stop: BLOCKED | IMPLEMENTED | `engine.py:Engine._verifying` (`HARNESS_BLOCKED`, `INFRA_FAILED`); `supervisor.py:_classify`. | Blockage is encoded in pause strings; repairable probe configuration can fall into the broad harness pause. |
| Stop: BUDGET_REACHED | PARTIAL | `engine.py:Engine._after_fail`; `governance.py:MAX_ROUNDS`; `test_engine.py:test_budget_pauses_without_lowering_bar_and_strategy_switches`. | Counts FAIL records; the check follows the strategy call and can be skipped when that call raises and REWORK resumes. |
| Stop: OWNER_DECISION_REQUIRED | IMPLEMENTED | `engine.py:Engine._staffing`, `Engine._after_fail`; `supervisor.py:_supervise`, `_classify`; `governance.py:REQUIRES_OWNER`. | Approval gates and recovery escalation exist, but a structured stop-reason vocabulary is absent. |
| Owner Effort | PARTIAL | `metrics.py:effort`, `project_effort`; `engine.py:Engine._archive_inputs`; E: both principal projects' `effort`. | Review minutes are UNKNOWN; aggregate `manual_recovery_replans` also counts supervisor-triggered replan events. |
| Owner Escape | PARTIAL | `metrics.py:_owner_escapes`, `project_effort`; `supervisor.py:channel`; `test_metrics.py:test_owner_escapes_by_channel_and_action`. | Recorded CLI actions are counted with historical limits; escapes outside instrumentation and an effort-driven decision loop are absent. |
| Strategy / hypothesis lifecycle | MISSING | `engine.py:STRATEGY`, `WORK`, `Engine._strategy`; `state.py:SCHEMA`. | Strategy decisions and counterpoint prose exist, but no hypothesis identities, evidence-linked transitions, or retirement/revisit rules. |
| Execution strategy: standard / research / operation | MISSING | `engine.py:PLAN`, `Engine._run`; `runtime.py:SPEC`; `library.py:classify`. | Runtime interface modes and the Library's Research label do not select different execution policies. |

## Autonomy Gaps - ranked

These proposals reuse plan JSON, the events table and existing engine/supervisor paths. They require no new dependencies, database tables, schema-breaking migrations, vector database, LLM providers, or governance changes. Existing plans retain current behavior through defaults; Owner-only approvals, stops and closing decisions remain authoritative.

### 1. Goal-aware execution and stopping

- **Why:** The CEO must choose the kind of work and recognize a justified stopping point; a verified report is not automatically a solved research goal or an operated service.
- **Evidence:** `engine.py:PLAN`, `Engine._run`, `Engine._deliver` use the same build/verify/deliver loop. `library.py:classify` only labels artifacts. `STRATEGY` cannot express sufficiency or exhaustion.
- **Bounded proposal:** Add an execution strategy and explicit completion evidence to plan JSON. Keep standard behavior; research tracks supported/unresolved claims against approved criteria; operation performs a bounded, declared observation/check cycle through existing runtime probes. Do not introduce perpetual scheduling.
- Record an outcome event using VERIFIED, SUFFICIENT, EXHAUSTED, BLOCKED, BUDGET_REACHED or OWNER_DECISION_REQUIRED, linked to evidence. Reuse `OWNER_REVIEW` or `PAUSED` instead of new database states. SUFFICIENT must satisfy an already approved bounded goal; EXHAUSTED must identify tried approaches and unresolved work, never masquerade as PASS. Neither closes a project automatically.
- **Files to touch:** `axbranch/engine.py`, `axbranch/state.py` (handoff only), `axbranch/supervisor.py`, `axbranch/gui.py`, `tests/test_engine.py`, `tests/test_supervisor.py`, `tests/test_gui.py`.
- **Acceptance tests:** Legacy plans retain their flow; an unsupported proof cannot become VERIFIED through report quality alone; bounded research stops with cited unresolved claims; operation stops at its declared boundary; supervisor never restarts a terminal outcome or an Owner stop.

### 2. Durable autonomous replanning

- **Why:** When evidence demands a change, the next action must remain a CEO decision across interruptions instead of falling back to another build or waiting for an operator.
- **Evidence:** `Engine._after_fail` commits REWORK before `_strategy` and checks the budget afterward; `Engine._rework` proceeds to STAFFING without replaying that decision. `CHANGELOG.md` explicitly records a refused strategy call being skipped on resume. `Engine._verifying` returns on harness-only findings before `_misconfigured_probes` can route them through `_after_fail`.
- **Bounded proposal:** Persist pending strategy work and its triggering verification in plan JSON or an event before calling the CEO. Consume it at REWORK entry; apply the new plan and completion event transactionally. Recheck existing budget limits before another build, including after a failed strategy call.
- Route deterministic `probe_misconfigured` evidence to a constrained `_strategy` repair and reverify the existing artifact, preserving criterion coverage. Keep unknown harness failures blocked. Reuse `_after_fail` and supervisor recovery records for bounded no-progress escalation; a heartbeat alone is not evidence of conceptual progress.
- **Files to touch:** `axbranch/engine.py`, `axbranch/supervisor.py`, `tests/test_engine.py`, `tests/test_supervisor.py`.
- **Acceptance tests:** Quota refusal and process interruption during strategy review resume the pending review before building; a committed strategy is not applied again; exhausted failure budget prevents another build; a repairable harness selector error reverifies unchanged bytes; Owner stops remain untouched.

### 3. Strategy, hypothesis and attempt memory

- **Why:** The CEO cannot choose a genuinely different next attempt without knowing what was tried, which claim it tested, and what new evidence it produced.
- **Evidence:** `state.py:Store.save_output` preserves stage checkpoints, but `Engine._executing` reuses upstream notes within a plan and exposes only recent findings to production. `failure_code` returns no repeat code when deterministic checks pass. Artifact hashes protect integrity without rejecting duplicate work.
- **Bounded proposal:** Record attempt events linking plan version, approach/hypothesis ID, input/artifact/check hashes, evidence references, outcome and next action. Keep hypothesis status in plan JSON: proposed, active, supported, refuted or exhausted; every status change cites an attempt and evidence.
- Pass a bounded attempt summary into `_strategy` and production. Reuse `artifacts.sha` on canonical inputs and the proposed action to detect exact repeats; require a recorded changed premise, source, check or approach before repeating. Explicitly allow re-verification after harness/infra changes. Do not claim semantic novelty detection from hashes.
- **Files to touch:** `axbranch/engine.py`, `axbranch/state.py` (handoff only), `axbranch/knowledge.py` (archive summaries), `tests/test_engine.py`, `tests/test_knowledge_effort_autostart.py`.
- **Acceptance tests:** Restart retains active/refuted hypotheses and evidence links; an unchanged attempt routes to strategy without rebuilding; a changed harness permits re-verification; unsupported hypothesis promotion is rejected; old projects need no migration.

### 4. Independent challenge with correct engine provenance

- **Why:** The CEO needs reliable opposition before accepting its team's output; apparent engine diversity and a requested review lens are insufficient evidence of a challenge.
- **Evidence:** `Engine._write_version` records actual `used` in `stage_outputs`, but `_verifying` chooses and compares against `plan['pipeline'][-1]['provider']`. A producer failover can therefore yield the same actual producer/verifier without the intended warning. `metrics.py:provider_record` also joins the configured agent provider. `lenses_applied` is not checked against required lenses.
- **Bounded proposal:** Resolve the artifact's actual producer from its recorded final stage output; use that identity for verifier routing, diversity records and provider metrics. Preserve an explicit UNKNOWN for legacy records whose working context was discarded, rather than inventing provenance.
- Extend the existing verdict with evidence-linked challenge results for the plan's required methods: contrary case, independent derivation, or deterministic check as applicable. Require declared challenge coverage before PASS; if a different engine is unavailable, record the limitation and require the declared alternative method, otherwise block. The challenger must not repair its own target.
- **Files to touch:** `axbranch/engine.py`, `axbranch/metrics.py`, `tests/test_engine.py`, `tests/test_metrics.py`.
- **Acceptance tests:** Producer failover changes verifier preference; same-actual-engine fallback is detected; missing challenge coverage cannot PASS; deterministic contradictions still override approval; provider statistics and legacy UNKNOWN attribution remain correct.

### 5. Preservation of verification contracts

- **Why:** Autonomous replanning must improve the approach without making success easier by silently removing the checks that exposed a problem.
- **Evidence:** `Engine._strategy` replaces a nonempty runtime spec and logs dropped probe names; it does not retain them or reject weaker expectations under an unchanged name. `Engine._owner_rework` similarly replaces criteria/probes, while preservation is principally in `DIAGNOSE_SYSTEM`. E records dropped-probe decisions in both principal projects; their counts alone do not establish unjustified weakening.
- **Bounded proposal:** Keep approved criteria and normalized probes in plan JSON with stable references. Strategy changes may add checks or repair execution details while retaining assertions. Removing criteria, removing assertions or weakening expected outcomes needs an explicit recorded Owner authorization for that change; logging a deletion is not authorization.
- Compare full probe assertions rather than names. Carry baseline checks through feedback rework; record reproduction failures honestly and do not treat an unreproduced defect as demonstrated fixed. Reuse `owner_ruling`, Owner feedback records and the existing gate; no new verification service.
- **Files to touch:** `axbranch/engine.py`, `axbranch/runtime.py`, `tests/test_engine.py`, `tests/test_runtime.py`.
- **Acceptance tests:** Strategy cannot remove an existing probe or weaken it under the same name; a selector repair keeps the assertions; an explicit Owner scope change can supersede the corresponding check; unchanged requirements survive feedback; recommendations remain non-gating.

### 6. Adaptive knowledge retrieval and accountable reuse

- **Why:** The CEO should choose what it needs to learn after new evidence, and apply prior lessons without the Owner supplying them again.
- **Evidence:** `knowledge.retrieve` is invoked for initial planning, Develop planning and verification. `Engine._strategy` and `_owner_rework` do not refresh retrieved knowledge; normal production contexts do not directly receive the retrieved planning excerpts. `context_used` records initial exposure, not application.
- **Bounded proposal:** Let the existing CEO response identify bounded knowledge queries and relevant source references. Use `knowledge.retrieve` before strategy/diagnosis decisions with the goal plus current failure or hypothesis, then forward selected excerpts to the affected production stage. Keep the keyword implementation.
- Record retrieval provenance and adopted/rejected lesson references in events, linked to the changed plan/check. Invalidate cached upstream work only when its referenced inputs or assigned instructions change. Do not add extra search calls when existing evidence is sufficient.
- **Files to touch:** `axbranch/engine.py`, `axbranch/knowledge.py`, `tests/test_engine.py`, `tests/test_knowledge_effort_autostart.py`.
- **Acceptance tests:** A newly relevant failure retrieves a previously missed lesson; the affected producer receives its provenance; unrelated notes stay out; changed knowledge inputs invalidate stale notes; unchanged inputs reuse checkpoints; missing vault yields an explicit empty result without stopping work.

## What the real-project evidence shows

The snapshot contains 8 projects. The following values are E's recorded fields, not reconstructed history or measurements from this audit. E contains aggregated events and current plan metadata, not the full plans, feedback text, source citations or mathematical arguments.

| Measure / JSON field | Test #1: stock analyzer (`P-20261003-bbad3c`) | Test #2: Riemann hypothesis research (`P-20261009-bd147a`) |
|---|---|---|
| State / close mode | CLOSED / save | EXECUTING / null |
| `iteration` / `plan_version` | 33 / 19 | 4 / 4 |
| `verifications` | PASS 5; FAIL 30 | PASS 3; FAIL key not listed |
| `effort.verification_rounds` | 35 | 3 |
| `effort.rework_rounds` | 39 | 3 |
| `event_kinds.recovery_replan` | 9 | Not listed |
| `decision_kinds` strategy entries | change_pipeline 12; continue 7; switch_provider 2 | No strategy entries listed |
| `decision_kinds.owner feedback diagnosis` | 6 | 3 |
| Dropped-probe decisions | By strategy 13; by revised plan 5 | By revised plan 3; by strategy not listed |
| `event_kinds.owner_feedback` / `effort.owner_feedback_rounds` | 9 / 9 | 5 / 5 |
| `effort.owner_interventions` | 15, recorded only since 2026-10-06 06:18; earlier UNKNOWN | 6 |
| `effort.manual_recovery` | 9, same recording limit | 0 |
| `effort.owner_escape` | 10, same recording limit | 0 |
| `effort.automatic_recoveries` | 12 | 0 |
| `event_kinds.provider_handoff` | 31 | Not listed |
| Same-engine verification decision key | 7 (`verification ran on the producer's engin`, as truncated in E) | Not listed |
| `event_kinds.agent_hired` | 42 | 6 |
| `event_kinds.reproduction` | 6 | 3 |
| `event_kinds.owner_run` / `owner_view` | 3 / not listed | 8 / 4 |
| `effort.elapsed_hours` / `agent_active_minutes` | 139.5 / 374 | 4.0 / 67 |
| `effort.satisfaction` / `owner_review_minutes` | 60 / UNKNOWN | UNKNOWN / UNKNOWN |

**Test #1:** E demonstrates real verification/rework, strategy changes, provider handoffs and eventual saved closure, alongside substantial recorded Owner intervention and escape. It does not demonstrate that those strategy changes were effective or that recovery was wholly autonomous. `plan_version` is a version marker, not a count of autonomous replans; `recovery_replan` is an event count, not clean manual attribution (`engine.py:Engine.replan`, `supervisor.py:_supervise`).

**Test #2:** E demonstrates verified intermediate deliveries, Owner feedback diagnoses and continuing execution without recorded manual recovery or escape. Its PASS records do not establish a proof of the Riemann hypothesis, autonomous hypothesis exploration, or completion of the Owner's goal. No strategy-decision entries are listed; revised plans following feedback must not be relabeled as autonomous research replanning.

**Measurement limits:** `metrics.py:project_effort` counts REWORK transitions and all feedback rows, including confirmations/finish; these are not necessarily distinct product defects or failed builds. Its automatic-recovery count includes recovery events, including escalation, not exclusively successful restarts. Review minutes remain UNKNOWN. Different goals, recording windows and completion states prevent an evidence-based claim that Test #2 proves a general reduction in Owner effort.

Only this audit document was created. Runtime behavior and current scheduler/provider availability were not checked; source-level defects and proposed fixes remain unexecuted.
