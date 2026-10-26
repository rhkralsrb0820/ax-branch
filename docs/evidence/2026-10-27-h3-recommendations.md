# H3 recommendations — 2026-10-27 / 0.1.63 candidate

The existing CEO PLAN response now includes recommended_departments. No extra recommendation model call is added. Context includes eligible catalog entries and actual attached versions/modes. Missing/empty recommendations remain valid.

The persisted suggestion has a Goal/input/plan-version scope and department specification hash. Only eligible, distinct, unattached entries with reasons are recorded (maximum three). Invalid entries are ignored, never delegated.

The Owner explicitly accepts or dismisses in the existing web project screen. Acceptance takes the project execution lock and atomically records the decision and attaches the exact still-valid specification in available mode. Required attachments, permissions and the running plan are unchanged. Repeated acceptance is idempotent; another project's ID, changed scope/specification, quarantined package or active execution is refused. Reload/project switching preserve or clear the correct data.

Recommendations are suggestions for a later planning boundary; the CEO does not automatically stop every task waiting for optional suggestions to be accepted. The Owner can connect them when the project is stopped or in review, then use the existing feedback/replan path. They are not automatically made required.

## Checks completed before final regression

- Recommendation logic tests: 7/7 (2.161 s), including one scripted planning call that records a suggestion without attachment or another call.
- Actual temporary HTTP API test: 1/1 (0.790 s), including worker-lock conflict, acceptance/retry and reloaded decision. Fake launcher stayed unused.
- Node DOM recommendation tests: 3/3 (escaping, explicit decision, project isolation). Existing experience UI fixtures: 4/4.
- Real headless Chrome temporary-profile self-test: 31/31, including four new H3 checks. Only synthetic recommendation records/fake worker; no real models or Owner desktop interaction.
- Existing department/verifier-policy modules: 21/21 (124.983 s).
- Product/recommendation/Owner-run/release modules: 30/30 (43.227 s) before the later native-profile integration correction. Final whole-suite evidence must supersede that scope, not be inferred from it.

The browser report is in the chat's shared review directory: h3-browser-20261027.json. Real-model recommendation quality is UNVERIFIED. This is not experience-effectiveness evidence, a deployed server update or automatic harness promotion.
