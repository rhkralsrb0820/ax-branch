# In-place evolution checkpoint — 2026-10-25

Scope: existing `dev/web-ui`, base commit `5f70f97`, including the preserved product-planning working changes. This is a source-level gap review, not proof of autonomous business success or OS isolation. Keep the existing Engine, Store, approval policy and web UI. No replacement CEO or parallel execution engine.

| Area | Current state and evidence | Disposition / next acceptance criterion |
|---|---|---|
| 1 Model | EXISTING: providers.py, existing Claude/Codex routing | KEEP; preserve reported usage and UNKNOWN when absent |
| 2 Harness | EXISTING: engine.py state machine, rework and verification | KEEP; exercise existing-project text rework through the web |
| 3 Sandbox/security | PARTIAL: sandbox.py/runtime.py; not OS isolation | DEFER stronger isolation; do not claim executable containment |
| 4 Knowledge | EXISTING: knowledge.py/kindex.py bounded retrieval | EXTEND with pinned department experience; verify exclusion and cutoff |
| 5 Capability | EXISTING: capabilities.py inventory, leases, gap decisions | KEEP; missing capability must not become an implicit grant |
| 6 Governance | EXISTING: governance.py and stored Owner approvals | KEEP unchanged; CEO cannot approve its own restricted action |
| 7 Policy | PARTIAL: permissions.py and department contracts | EXTEND through existing enforcement points, not a second policy layer |
| 8 Least privilege | PARTIAL: check_stage rejects unattached tools/network and privilege unions | KEEP; OS process isolation remains separate and unverified |
| 9 Organization harness | PARTIAL: reusable research/operations, new product-planning package | IMPLEMENT NOW; pinned attachment, structured output and bounded rework |
| 10 Autonomous verification | EXISTING: independent verifier and runtime checks | KEEP; scripted tests are not real-model E2E evidence |
| 11 Experience | PARTIAL: event-derived cards, source references and outcomes | IMPLEMENT NOW; no source free text exported, discarded projects excluded |
| 12 Learned routing | PARTIAL: metrics.provider_record records history, not a trained router | DEFER learning; compare routing quality/cost before promoting policy |
| 13 Agentic memory | PARTIAL: Store events, knowledge retrieval and adoption traces | EXTEND existing store; no duplicate memory database |
| 14 World model | MISSING as a predictive model | DEFER; product assumptions/scenarios are not a world model |
| 15 Skill learning | PARTIAL: reusable department packages; no proven automatic skill induction | DEFER promotion; candidate must survive multiple independent tasks |
| 16 Reinforcement learning | MISSING in this workflow | DEFER; no reward dataset or reliable repeated evaluation yet |
| 17 Neuro-symbolic checks | PARTIAL: model planning plus deterministic contract/arithmetic checks | EXTEND bounded validation; reject malformed data without crashing |
| 18 Verified self-improvement | PARTIAL: comparison rubric and HOLD decision in kindex.py | EXTEND only after real control/treatment evidence; no automatic deployment |
| 19 Trajectory | EXISTING/PARTIAL: event histories and knowledge_trace | KEEP references and provenance; avoid logging raw private data in shared cards |
| 20 Predictive verification | MISSING as a validated predictor | DEFER; do not replace deterministic or independent verification |

## Priority and completion boundaries

1. Finish current product-planning implementation and regression before adding more subsystems.
2. Validate headless web flow independently of Node fixtures. Preserve the serving build until a replacement is verified.
3. Run one bounded, isolated real product experiment only after the web baseline is verified. Research and operations departments may be reused under their pinned permissions.
4. Compare control and experience-assisted outputs with identical task/input/rubric/budget, and record calls, tokens, failures and interventions. A single comparison is exploratory and cannot establish general quality improvement.
5. Record improvement candidates with evidence, risk, isolated implementation, regression, independent review and required Owner approval. No automatic policy changes, training, external release or promotion from a favorable score alone.

## Important limits

- Experience cards currently transfer structured outcomes and references. They do not yet transfer a verified, generalizable product-planning lesson. Do not market this as a self-improving system.
- RAG retrieval is available without training. LoRA/fine-tuning is not required for this phase and is not started here.
- Product scenario math is checked; willingness to pay, real revenue and market validity remain UNKNOWN without external evidence.
- Existing runtime restrictions do not establish an OS security boundary.
