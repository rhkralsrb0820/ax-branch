## CURRENT CHECKPOINT — Claude, 2026-10-31 (0.1.66 candidate built; development stopped at a checkpoint)
- Repo C:\Users\HP\Desktop\AX-Branch\ax-branch, branch dev/web-ui, code c192070 + records commit; tree clean.
- Owner server: 0.1.64-42b1bd2 (unchanged since the approved 2026-10-30 switch; rollback in shared
  outputs/server-switch/switch-20261030-202747.json). Candidates preserved: 0.1.65-3906e21, 0.1.66-c192070.
- **New:** before/after-training comparison (model_compare.py) + UI; four training states; producer predict.py rule.
- **Tests (raw):** full regression c192070 = 585 discovered: 584 passed, 1 skipped (test_native opt-in PyInstaller
  build), 0 failed, 0 errors. test_model_compare 8/8, browser 38/38. Packaged 0.1.66: data flow 18/18, comparison OK.
- **Unverified:** a real trained model comparison, any training effect, real-model behaviour, Owner confirmation.
- **Processes:** only the Owner server (AXBranch.exe 0.1.64, PID 64080 at last check).
- **Usage:** not readable from this session's tools; not estimated.
- **Approvals needed:** server switch to 0.1.66; BANKING77 predict.py rework (model call); web E2E (250k budget); A/B
  (on hold); external program folders for isolated runs.
- Next tasks and the copy-paste prompt: docs/CODEX_HANDOFF_PROMPT.md. Evidence: docs/evidence/2026-10-31-0.1.66-model-compare.md.

## HISTORICAL CHECKPOINT — superseded: — Claude, 2026-10-30 22:10 KST (server 0.1.64 applied; candidate 0.1.65 built; development stopped at a checkpoint)
- Repo C:\Users\HP\Desktop\AX-Branch\ax-branch, branch dev/web-ui, code 3906e21 + records commit; working tree clean.
- **Owner server switched (Owner-approved) to 0.1.64-42b1bd2**, same workspace/port; backup and rollback:
  shared outputs/server-switch/switch-20261030-202747.json. Data preserved (rows, states, files manifest identical).
- **New since 42b1bd2:** trained results usable under isolation (isolation.training_runtime, runners + verification),
  training records delivered/used/effect split, devroom to-dos/issues refreshed, version 0.1.65.
- **Tests (raw):** full regression 3906e21 "Ran 577 ... OK (skipped=1)" = 576 passed + 1 skipped (test_native real
  PyInstaller build, opt-in AXB_NATIVE_E2E=1) + 0 failed + 0 errors. 42b1bd2 was 576 discovered = 575 passed + 1 skipped.
- **Candidate 0.1.65-3906e21** (not serving): packaged data flow 18/18, packaged trained-result run in AppContainer.
- External tool adapters: not implemented by design (docs/CAPABILITY_LIFECYCLE.md); granting an installed program's
  folder to isolated runs is a permission expansion that needs the Owner.
- **Usage:** provider usage numbers are not readable from this session's tools; not estimated.
- Copy-paste prompt for Codex: docs/CODEX_HANDOFF_PROMPT.md (delivery to Codex NOT confirmed).
- Evidence: docs/evidence/2026-10-30-0.1.65-trained-results.md.

## HISTORICAL CHECKPOINT — superseded: — Claude, 2026-10-30 20:30 KST (0.1.64 candidate built)
- Branch dev/web-ui, code 42b1bd2 (+ records commit). Working tree clean. Owner server unchanged: 0.1.63-50aabe2.
- New since 098759f: a744f5b generalized capability-gap flow; 5fab908 evaluation projects out of the work list
  (devroom verification values fixed: b4d4dec would have failed test_web); 612ea51 training records; 42b1bd2 devroom.
- **Full regression 576 OK (1 skipped) on 42b1bd2**, hashes matched (supersedes the reaped b4d4dec run).
- **Candidate 0.1.64-42b1bd2:** C:/Users/HP/Documents/Codex/axbranch-builds/0.1.64-42b1bd2 (BUILD.json). Packaged
  Owner-data flow 18/18 (fixed test app), smoke of new views/APIs. No model call.
- Evidence: docs/evidence/2026-10-30-0.1.64-features.md.
- **Not done / Owner decisions:** server switch to the candidate (needs approval + backup/rollback as on 2026-10-29);
  one limited real-model run; improvement evaluation (no real candidate yet); A/B on hold.
- Correction: earlier notes said test_improvements 5/5 at 4f177db/b4d4dec; it was 4/4 then (5/5 now).

## HISTORICAL CHECKPOINT — superseded: — Claude, 2026-10-30 19:20 KST (0.1.64 dev source; full regression interrupted)
- Branch `dev/web-ui`, HEAD b4d4dec (+ this handoff commit). Working tree clean. Owner server unchanged: 0.1.63-50aabe2.
- **Newly usable in the dev source (not in any build yet):**
  - a8dfa81: uncommitted experience WIP found in the tree (lesson candidates, decision-change view; author not recorded)
    integrated with a unit test.
  - 4f177db: improvement candidates (`axbranch/improvements.py`, view "개선 후보 · 학습"): repeated failure -> proposal
    from the strategy change that later passed -> prepared evaluation -> Owner-approved baseline/variant projects
    (experience off) -> automatic comparison -> Owner apply (not-worse only) -> rollback. Applied rules reach CEO
    planning/strategy as reference context. Learning paths shown from real state.
  - 1076c6f: recommendation `gap` (missing capability), Owner-connected vs accepted-recommendation departments,
    capability attempts card (free options, results, minimal approval), home centred on running/waiting work.
  - e198820: project page "지금 단계 · 담당 / 멈춘 이유 / 다음 행동".
  - a3c2f3e: Owner data across the library lineage (continued project starts from the ancestor's last good data;
    original never changed).
  - b4d4dec: version 0.1.64, CHANGELOG, devroom features.
- **Checks run on this code:** test_improvements 5/5, test_recommendations 8/8, test_now 2/2, test_owner_data 12/12
  (real AppContainer, fixed developer test app), test_department_lessons 1/1, test_product_planning+test_decision_trace
  34/34, test_web 17/17, test_release 1/1, headless browser self-test 36/36 (synthetic fixtures). No model call.
- **Interrupted:** full single-process regression on b4d4dec was reaped by Claude Code for low system memory after
  ~446 tests, no failure seen, no orphan process. NOT restarted, per the rule. Not a pass.
- **Not done:** full regression, candidate build 0.1.64-b4d4dec, packaged checks, real-model run, server switch.
- **Resume (when memory allows / Owner asks):**
  1. `python -X utf8 -m unittest discover -s tests -t .` on b4d4dec (single process; close other heavy apps first).
  2. `python -X utf8 build_exe.py --output-dir C:/Users/HP/Documents/Codex/axbranch-builds/0.1.64-b4d4dec`
  3. `python -X utf8 tests/browser_owner_data_e2e.py <exe> <out.json>` and `python -X utf8 tests/browser_web_selftest.py`.
  4. Update devroom `candidate_build` / feature locations; then Owner decides a limited real-model run and the server.
- **Next development:** run one improvement evaluation when a real candidate exists (Owner approval); evaluation
  projects are listed among the Owner's projects (consider a filter); capability resolution covers training only.

## HISTORICAL CHECKPOINT — superseded: — Claude, 2026-10-29 23:25 KST
- Owner server unchanged: 0.1.63-50aabe2.
- **2f4cdc5:** the Owner-data contract is carried from the CEO plan (`runtime.data`) to the producer, executed in
  verification (write/read/save/restore/read) and enforced by the runner. Evidence:
  `docs/evidence/2026-10-29-owner-data-contract.md`.
- **Full regression 565/565 on 2f4cdc5** (the earlier d6f5b9c run was reaped by memory pressure; superseded).
- **Candidate 0.1.63-2f4cdc5 preserved:** packaged web-page data flow 18/18 with the fixed developer test app; no model
  call.
- **Not done:**
  - a real-model run proving the CEO/producer write and implement the contract (needs an Owner decision);
  - applying this to the Owner server;
  - A/B (on hold).

## HISTORICAL CHECKPOINT — superseded: — Claude, 2026-10-29 22:00 KST (Owner data persistence; full regression interrupted)
- Owner server unchanged: 0.1.63-50aabe2 (PID 65848).
- **Implemented (dev source):**
  - 6584135: `axbranch/userdata.py` data contract and snapshots; `owner_runs.py` restore / periodic save / save
    now / stop save, compatibility check with choices, port retry / announced port / reserved port; web UI.
  - d6f5b9c: packaged-web harness `tests/browser_owner_data_e2e.py` and the selftest `owner-data` mode; a stale
    result link fixed; devroom feature table; data rule for generated apps.
  - Fixed test app: `tests/fixtures/owner_data_app` (developer fixture from generated P-20261029-99cea3; not
    AI-produced).
- **Tests:**
  - focused: owner_data 10, owner_web_run 3, web, reserved_port, isolation, browser selftest 31/31 — all pass;
  - source-server dry run of the packaged-web harness: 18/18 checks
    (open → enter → save → stop → reopen/restore → revised v2 keeps data → incompatible v3 choices → previous
    version → periodic save → killed AX Branch → restart restores).
- **Interrupted:** the full single-process regression on d6f5b9c was reaped by Claude Code under system memory
  pressure (≈194 tests in, no failure seen, no orphan process left; 3.6 GB free afterwards). Not restarted, per the
  rule.
- **Next commands (when memory allows / Owner asks):**
  1. Full regression on d6f5b9c (single process).
  2. `python -X utf8 build_exe.py --output-dir C:/Users/HP/Documents/Codex/axbranch-builds/0.1.63-<commit>`.
  3. `python -X utf8 tests/browser_owner_data_e2e.py <exe> <out.json>`.
  4. Update the devroom `candidate_build` and the features' location.

## HISTORICAL CHECKPOINT — superseded: — Claude, 2026-10-29 21:10 KST
- **Owner server switched (Owner-approved)** to `0.1.63-50aabe2`, PID 65848, `demo-2026-11/workspace`, port 8765.
  Backup and rollback: `outputs/server-switch/switch-20261029-193311.json`.
- **New:** open, use and stop web/server results in AX Branch (`axbranch/owner_runs.py`, b04ee15): isolated,
  separate origin, cleaned on stop/exit/lifetime. Real-backend tests in `tests/test_owner_web_run.py`.
  NOT applied to the Owner server.
- **Packaged web E2E (`--webapp --text-rework`) on candidate 0.1.63-3b3337c (546/546): FAILED** before Owner review.
  - Cause: the generated app defaulted to port 8765, which is the Owner's AX Branch.
  - Fixed in source: `runtime.RESERVED_PORTS`, plus CEO/producer rules; `tests/test_reserved_port.py`.
  - Usage: 225,352 + precheck 11,505 = 236,857 tokens.
  - Evidence: `docs/evidence/2026-10-29-owner-web-run-and-web-e2e.md`.
- **Next (Owner decisions):**
  1. One more real web-page E2E on a new candidate built from the fixed source (new 250k project budget).
  2. Whether to apply the web-result runner to the Owner server.
  3. A/B stays on hold.
- Focused tests after the fix: runtime + engine + reserved_port + owner_web_run 139/139. The full regression on
  the fixed commit has NOT been run yet.

## HISTORICAL CHECKPOINT — superseded: — Claude, 2026-10-29 00:58 KST (usage checkpoint: 5-hour window 12% left)
- **Owner server:** 0.1.63-18fbd6d, PID 57684. Not touched.
- **Codex WIP:** budgets, completion reserve, stage reuse. Interrupted by Codex's limit at 21:35, backed up to
  `outputs/codex-wip-backup-20261028/`, reviewed and completed in 7a4e4cc.
- **Commits after 652e7e6:**
  - 7a4e4cc: task profiles, completion reserve, safe revision reuse, `time_basis=call_seconds`, A/B v3 proposal
    with `--owner-approved`.
  - f53ed1e: GUI tests report usage.
  - 7597373: Korean limit message → `usage_limit`.
  - 1fd997c: isolated Python tempfile fix (runtime v3 sitecustomize, run-folder WRITE_DAC).
  - 50aabe2: evidence.
  - Then docs.
- **Regression:**
  - 7a4e4cc: 540/542 (2 GUI contract failures, kept);
  - f53ed1e: 542/542;
  - **50aabe2: 543/543**, hashes matched.
- **Packaged real runs on candidate 0.1.63-f53ed1e** (`docs/evidence/2026-10-28-packaged-work-runs.md`):
  - product planning: completed, 68,532 tokens;
  - CSV + revision: completed with research reuse, 123,956 tokens;
  - web app: server channel worked, but self-test blocked by the tempfile harness defect (fixed after the run),
    210,948 tokens.
  - All verification was same-provider (Codex limited).
- **Candidate 0.1.63-50aabe2 preserved** (`axbranch-builds/`, BUILD.json). No packaged real run on it yet.
- **Web-app re-run done (2026-10-29 19:3x)** on 0.1.63-50aabe2: P-20261029-99cea3 → OWNER_REVIEW.
  - 152,819 tokens; Codex verifier (cross-provider); isolated self-test and server channel passed.
- **Next:**
  1. Owner: A/B v3 approval.
  2. Optional dev: drive the same three paths through the packaged web page (headless, separate profile).
  3. Owner-run of web results (still blocked).
- No processes running except the Owner server. No uncommitted changes after this commit.

## HISTORICAL CHECKPOINT — superseded: — Claude, 2026-10-28 01:05 KST (stabilization + real work runs)
- **Owner server:** 0.1.63-18fbd6d, PID 57684, http://127.0.0.1:8765/ (switched by Codex 2026-10-27 22:56; DB backup in
  `outputs/server-switch/`). Not restarted or replaced by Claude.
- **dev/web-ui commits this round** (on top of 0e13802):
  - 1f48687: Product Planning contract caught before verification; `PRODUCT_PLAN_RULES` given to the producer.
  - dbcf069: pre-call budget reserve.
  - 2761687: generated web/server verified inside the AppContainer via a per-run named-pipe channel; no Windows
    change.
  - a3a6cf6: A/B reserve preflight.
  - 0bf9914: B6 post-output Edge shutdown hang accepted narrowly.
  - ac83d2e: revisions verified against the reviewed version's diff.
  - Then docs.
- **Evidence:**
  - `docs/evidence/2026-10-27-isolated-server-channel.md`;
  - `docs/evidence/2026-10-27-b6-browser-stall.md` (updated);
  - `docs/evidence/2026-10-28-real-work-runs.md`.
- **Real-model runs** (source 0bf9914 / ac83d2e, isolated roots, synthetic data): 20 calls, 379,314 tokens, no
  overshoot, no fallback.
  - web app → OWNER_REVIEW (isolated server checks passed);
  - product planning → reserve stop before v2 verification;
  - CSV → v1 PASS; the revision v2 PASSED after the ac83d2e fix (resume); reserve stop before CEO acceptance.
- **Tests this round** (focused):
  - document_contract 4;
  - budget_reserve 5;
  - isolation 13 (real backend, incl. the server channel);
  - browser_stall 2;
  - revision_context 1;
  - runtime 42/42 (before 0bf9914);
  - engine + departments 110;
  - product_planning, required, harness_safety, owner_run, sandbox, verification_policy, web, release.
- **Full regression on frozen 0f5e8cb: 518/518 OK**, 2,058 s, hashes matched (`outputs/0.1.40-evidence/FULL-0f5e8cb-single-process.log`).
- **Candidate build preserved:** `C:/Users/HP/Documents/Codex/axbranch-builds/0.1.63-0f5e8cb` (exe sha256 95b92b28…8715, BUILD.json). Packaged web smoke on an isolated root: page 200, departments listed, stop OK. NOT deployed.
- **Interrupted:** one B6 diagnostic batch was reaped by Claude Code under system memory pressure after 17/20
  runs. Its orphaned python was killed; not restarted.
- **NOT done / next:**
  1. Packaged-exe check of the new paths (server channel, contract skip, reserve) on the preserved candidate.
  2. IB-6: reuse unchanged stages on revisions (measured 44,362 tokens of re-run).
  3. IB-8: Owner budget decision.
  4. A/B: not run. The preflight shows the best case fits 60k and the worst case is refused at CEO acceptance.
  5. Untested in the server channel: WebSockets, HTTPS, multi-port.
- **Owner approvals needed:** per-task budgets (IB-8); whether to run the A/B; any persistent Windows change (none
  proposed now).
- Do not start another Codex CLI. No proof that Codex received this handoff.

## HISTORICAL CHECKPOINT — superseded: — Claude, 2026-10-27 22:40 KST (after Codex 0.1.63)
- dev/web-ui:
  - 1434811 / 9684256: test contracts only, no production code;
  - then docs.
  - Candidate build 0.1.63-18fbd6d contains all production code (later commits are tests/docs).
- **Full single-process regression on 9684256: 504/504 OK**, 1,787 s, hashes matched
  (`outputs/0.1.40-evidence/FULL-9684256-single-process.log`). The 1434811 run was 502/504 (2 test_training
  contract failures, fixed). F163 (Codex) remains a stopped, failed run, not a pass.
- Fixed contracts:
  - executive failover asserts the sanitized `usage_limit` category;
  - harness-safety mocks require and assert `isolate=True` and return fresh dicts;
  - the trained-output Owner run is refused without a recorded isolation exception, while the stack and
    recovery-message checks are kept.
- B6: 1/13 isolated stalls; root cause unresolved (`docs/evidence/2026-10-27-b6-browser-stall.md`).
- `docs/IMPROVEMENT_BACKLOG.md` (developer-created) and the 1–20 matrix update in
  `docs/IN_PLACE_EVOLUTION_REVIEW.md` were added.
- Known wording defect, deliberately left: the `axbranch/runtime.py` ISOLATED_MODES comment says
  "administrator-only exemption" (unverified). Not changed, so the tested source stays identical; fix it with the
  next code change.
- A/B: two attempts, both stopped in task A. Do not rerun without a new Owner decision. The Owner server is still
  0.1.61-67d9095.
- Next:
  - Owner decisions: loopback exemption (IB-5), any A/B retry, server switch to a candidate.
  - Optional dev: IB-1 / IB-2 implementation with a regression.

## HISTORICAL CHECKPOINT — superseded: Codex stopped at actual 5% remaining, 2026-10-27
- Implementation source: 18fbd6d, dev/web-ui. Read docs/evidence/2026-10-27-codex-163.md first.
- H3, supported Owner CLI/native isolation and packaging implemented; actual packaged text-rework E2E 11/11, 12 calls, 718 sec. Candidate EXE hash 27de6cb17ca30dff831468387a0d16f37eb2c1216da9cd4c34e9da8a499b5af2.
- Compact A/B ran ONCE: stopped task A after 64,487 reported tokens; nonempty excluded/experiments missing in v1. No comparison, UNPROVEN. Do not rerun without a new decision.
- Full F163 was STOPPED at usage threshold; NOT a full PASS. Partial batch evidence is in the shared chat outputs/0.1.40-evidence/F163_batches.jsonl. Remaining batches are NOT RUN.
- Confirmed failures needing follow-up: test_engine executive failover assertion still expects raw notes removed by earlier sanitization; harness-safety mocked check callbacks reject isolate keyword. Correct adapters to explicitly assert isolate=True and assert sanitized usage_limit categories, do not restore raw CLI text or weaken security. Edge runtime timeouts also recurred; cause remains unknown.
- Next: fix those test contracts, run affected checks, then one fixed-source full regression. Do not claim existing tests pass. The runtime implementation has not been changed since packaged E2E.
- Owner server PID 54292 / 0.1.61-67d9095 preserved. No main merge, push, server switch, OS exemption or new credentials. No extra model work should start automatically.
- H3 is initial planning recommendations with explicit acceptance, not autonomous attachment or proven recommendation quality. Protected generated web/server/GUI/foreign training interpreters remain unsupported.
# Codex CLI handoff — AX Branch

## HISTORICAL CHECKPOINT — superseded (Claude, 2026-10-27 00:55 KST, usage checkpoint)
- **Why stopped:** the Claude 5-hour window is at 12% remaining (88% used; reset 02:00 KST). The 7-day window is at
  74% remaining. This is a checkpoint before the 7% rule, so no new long task was started.
- **Verified facts:**
  - Repository rhkralsrb0820/ax-branch is **PUBLIC**; default branch main (old README). No license.
  - Screenshot history was rewritten by Codex: former 884bc68 = 3bb8c05 and former 85f8f00 = 38e40c7; 8f94d88
    removed the README image embeds.
  - Never push old clones or the private recovery bundles.
  - Owner server unchanged: `builds/0.1.61-67d9095`, PID 54292. Candidate builds exist but are not deployed.
- **Directive in force:** shared `CLAUDE_FINAL_DIRECTIVE_2026-10-27.md` (Phases A–D plus the improvement backlog).
- **Done this round** (local commit 2058648 on dev/web-ui; pushed with this checkpoint):
  - **Phase A — OS isolation** (`axbranch/isolation.py`): Windows AppContainer plus the existing Job Object. No
    admin rights and no OS, account or firewall change.
    - Isolated: verification self-tests (file/bundle) and Runtime Acceptance in cli/gui mode.
    - Blocked with an actionable pause: server/web runtime modes (loopback into an AppContainer needs an
      admin-only exemption) and foreign interpreters (training stack). Owner exception:
      `axbranch isolation <id> --allow-unisolated --reason`.
    - Real-backend canary tests (`tests/test_isolation.py`, 8/8): outside read/write, profile, loopback, internet,
      child process, credential env and stale grant are denied; allowed work runs; descendants are killed.
    - Private runtime copy: `%LOCALAPPDATA%/AXBranch/sandbox-runtime/py312-v2` (stdlib + site-packages without
      pip).
  - **Phase B1/B2:**
    - Sanitized provider failure categories (no raw CLI output).
    - `verification_policy cross_provider=required` stops acceptance on a same-provider fallback
      (`tests/test_verification_policy.py`).
  - **Focused tests:** test_engine 92/92 (before the B change), test_isolation 8/8, test_verification_policy 3/3,
    test_sandbox, test_departments.
  - test_runtime: 41/42. One failure is the known intermittent headless-Edge 90 s stall in
    `test_rendered_page_is_checked_not_just_served`. That test does not use isolation, and it ran concurrently with
    other suites.
- **NOT done yet, in order:**
  1. B3: DONE 00:58 — lineage regressions (positive edit-only + negative cases in tests/test_departments.py) pass on 2058648; no code change.
  2. B5: H1/H2 packaged denial checks.
  3. B6: bounded browser-stall diagnostics (single test, phase/process record; no timeout increase).
  4. Full regression on frozen code, preserved candidate build, then B4: one packaged web text-rework E2E on it.
  5. Phase C: H3 recommendations (CEO plan field `recommended_departments`, max 3, web accept/dismiss).
  6. Phase D: corrected A/B pre-registration plus ONE attempt (budgets 60k×3 + 25k×2, max 230k; count probes).
  7. Improvement backlog; README / 1–20 matrix / devroom update.
- **Uncommitted changes:** none. **Processes:** only the Owner server. No test or experiment running.
- Do not start another Codex CLI. The Owner relays the next prompt.

# ===== HISTORY BELOW (older checkpoints, kept for the record; superseded) =====

## [HISTORICAL — superseded, do not act on] Checkpoint (Claude, 2026-10-26 23:10 KST)
- Branch `dev/web-ui`. Not merged into main. The Owner's server is unchanged (`builds/0.1.61-67d9095`, PID 54292).
- Pushed to origin/dev/web-ui: up to 6366383 (README). Later commits are local until the next authorized push.
- Repository visibility: **PRIVATE**. Publication is stopped pending four Owner decisions (e-mail in all commits,
  law-firm project mention, screenshots in history, license). Audit: Codex work folder
  `outputs/ceo-demo-review/PUBLICATION_AUDIT_2026-10-26.md`. No history rewrite without approval.
- **Done this round** (deterministic tests; no real model run for any of it):
  - README rewritten (Korean product intro + English lead), `docs/README.md` index, two synthetic screenshots.
  - caaa1a4 — Product Planning 1.0.1. The conditional source criterion and the same headings/JSON contract
    reach planning (`summary.document_contract`), production and verification (`required_document`). A preflight
    refuses a non-markdown plan before any agent call.
  - ce7bebc — H1 registry lifecycle: `departments/<id>/lifecycle.json`, kept outside department.json so the
    spec digest is stable.
    - Absent = legacy, usable. Unreadable = quarantined.
    - `axbranch lifecycle` (Owner CLI); verified needs 2+ evidence references.
    - Enforced at attach, staffing, every execution entry, and before each stage call and the final build.
  - f3ec8cb / bdc5b07 — H2: attachment `mode` available/required plus `department_mode` events.
    - Required work is checked at staffing, at execution entry and at acceptance (`_deliver` →
      `required_unmet`).
    - Detaching needs a reasoned lowering first.
    - Web chips/toggles; browser self-test 27/27.
- **A/B experiment: paused.** It needs a new Owner-approved pre-registration (task text); no budget increase.
- **Validated (23:55 KST):**
  - Full single-process suite on 85f8f00: 479/479 OK, hashes matched
    (`outputs/0.1.40-evidence/FULL-85f8f00-single-process.log`).
  - Candidate build preserved: `demo-2026-11/builds/0.1.62-85f8f00` (BUILD.json; packaged smoke on an isolated
    AXB_ROOT).
  - One real-model H2 run P-20261026-3973d8: OWNER_REVIEW, Codex verification, 92,851 tokens
    (`docs/evidence/2026-10-26-h2-required-real-run.md`).
  - Pushed origin/dev/web-ui up to 85f8f00; this docs commit is pushed after it.
- **Next:**
  - Owner decisions: A/B pre-registration, publication (4 findings), any server switch to the candidate.
  - Optional: a real-model run of the blocking path.
- H3/H4, training, paid services and the server switch stay out of scope.
- [Correction 2026-10-27] Statements above about PRIVATE visibility, local-only commits and screenshots are stale: the repository is PUBLIC, screenshot history was rewritten (884bc68→3bb8c05, 85f8f00→38e40c7, then 8f94d88 removed the README embeds). Old hashes in this block are historical evidence identities.


## [HISTORICAL — superseded, do not act on] Checkpoint (Claude, 2026-10-26, after Codex review of bf6da8d)
- Branch `dev/web-ui`. Code commit 786834f (review fixes) plus a docs commit on top. Not merged into main; not
  pushed. The Owner's server is unchanged (`builds/0.1.61-67d9095`).
- Codex review P1/P2 fixed in 786834f:
  - historical stage evidence only through a valid edit lineage (fail closed otherwise);
  - experience levels from the recorded producer/verifier provenance.
- The P2 documentation finding is resolved by this section and the HISTORICAL markers below.
- **Original evolution directive:** found at `C:/Users/HP/.codex/attachments/358305e6-3b45-4598-a748-d8199e092b69/붙여넣은 텍스트.txt` (located by Codex). Its 20 area names match
  `docs/IN_PLACE_EVOLUTION_REVIEW.md`. My earlier "missing source" statement is withdrawn.
- **Evidence limits that stay true:**
  - b7e96f0 full single-process suite: 455/457, two Edge timeouts, not a clean pass;
  - e62d440 scoped tests: 134/134, not a full-suite result;
  - the packaged web text-rework E2E used same-provider verification fallback and a harness interruption, so it
    is not cross-engine independent;
  - the product A/B was never started, and no improvement is established.
- **Next, in order:**
  1. Full regression on the frozen current code.
  2. Check provider availability once (actual call).
  3. If both providers are available: a preserved candidate build, then ONE bounded A/B comparison (new root).
  4. H1–H4 and switching the server wait for the Owner.
- Status of this round's validation: see the newest entry of the shared `IMPLEMENTATION_STATUS.md`.
- **Round result (2026-10-26 07:53 KST).** Claude usage: 5-hour window 70% remaining, 7-day window 87%
  remaining.
  - **Codex review fixes** (786834f), regression-tested:
    - P1: historical stage evidence only through a valid edit lineage; fails closed with the reason recorded;
    - P2: experience cards derive `CROSS_PROVIDER_PASS`, `SAME_PROVIDER_ROLE_SEPARATED_PASS` or
      `PASS_PROVENANCE_UNKNOWN` from the recorded producer/verifier provenance;
    - docs P2: one current handoff checkpoint, older blocks marked historical, missing-source claim withdrawn.
  - **Full single-process suite on 786834f:** 460/460 OK, hashes matched (`outputs/0.1.40-evidence/
    FULL-786834f-single-process.log`, `tested-code-786834f.sha256`). No Edge timeout in this run; that is not
    evidence that the Edge issue is fixed.
  - **Provider check (one real call each, 07:47):** Codex OK, Claude OK.
  - **Candidate build** `demo-2026-11/builds/0.1.62-bcd2a84` (fd65a29d…), preserved, NOT serving. No packaged
    web E2E on this exact build.
  - **Product A/B attempt 1:** stopped by its own budget (Task A: 64,995 reported tokens > 60,000 after 4 turns).
    No comparison; UNPROVEN (`docs/evidence/2026-10-26-product-ab-attempt.md`). Not rerun.
  - **Owner decision needed:** a per-project budget able to hold one full cycle (measured about 175k reported
    tokens for a comparable flow). Options (a)/(b)/(c) are in that evidence file.
  - **Running:** only the Owner web server (PID 54292, `builds/0.1.61-67d9095`); safe to leave. No test or
    experiment processes.

- **Round result — option (c), 2026-10-26 21:30 KST.** Claude usage: 5-hour window 82% remaining, 7-day window
  83% remaining.
  - The compact A/B design is implemented (cb4d834): `product_experiment --design compact`, with fixed
    developer-designed tasks, pre-registration and a measured feasibility gate.
  - **Ran with 0 model calls** (`outputs/product-ab-compact-1`): NOT_STARTED_INFEASIBLE under the unchanged 60k
    cap. A with revision: 96,595–128,641 tokens; B-experience with evaluation: 61,609–85,163.
    `docs/evidence/2026-10-26-product-ab-compact.md`.
  - Corrected figure: the comparable web E2E MEASURED 234,981 tokens over 10 calls; the earlier "175k" was the cache
    part only.
  - **Compact prompt JSON tried, then reverted** (ad1d8cb). The cb4d834 full run failed (461 run: 9 failures,
    7 errors) because format-coupled tests match indented prompt substrings. engine.py is byte-identical to 786834f
    again; engine + harness_safety 116/116 after the revert.
  - **Full single-process run on ad1d8cb:** 461 run, 457 passed, 4 failed. Failing tests: test_lock crash release,
    2 test_owner_run launcher tests, test_supervisor stalled worker. All are timing/subprocess tests, and the run
    took 46,108 s (machine stalled or suspended during memory pressure; the session's shell was also reaped).
    Rerun of those three modules alone: 25/25 OK. NOT a clean full pass; a clean full run on ad1d8cb is still to
    be done when memory allows.
  - Attempt 1 (`outputs/product-ab-786834f`) is preserved unchanged.
  - **Owner decision needed for the comparison:** both, either or neither of (1) drop the text revision from the
    comparison, already shown in the web E2E, and (2) a separate pre-registered evaluation budget. Even then the
    measured MAXIMUM exceeds 60k by up to about 5k.
  - **Running:** only the Owner web server (PID 54292). No test or experiment processes.

- **Round result — approved compact A/B, 2026-10-26 22:10 KST.** Claude usage: 5-hour window 65% remaining,
  7-day window 81% remaining.
  - b088cdf implements the approved design:
    - no textual revision in A (the revision is evidenced by the web E2E P-20261026-3ca452, NOT re-verified here);
    - separate blind evaluation budget of 25k per B result; production 60k per project; experiment maximum 230k;
    - estimates labelled as estimates;
    - usage per project plus the total.
  - **Ran once** (`outputs/product-ab-compact-2`, after one real availability call per provider): STOPPED in
    Task A.
    - 5 calls, 77,546 reported tokens, all in A. Evaluation 0; B not started.
    - v1 failed verification: length (669 words against about 600), the exact Korean-heading / product_plan JSON
      contract (my task text did not name them), and an inapplicable Product Planning provenance criterion.
    - The rework's v2 verification overshot the cap in flight (59,807 → 77,546; stop-after-usage limitation).
    - No comparison; UNPROVEN. Evidence: `docs/evidence/2026-10-26-product-ab-compact-run.md`.
  - **Final full single-process regression on b088cdf, stable environment:** 463/463 OK (24 min, hashes matched,
    `outputs/0.1.40-evidence/FULL-b088cdf-single-process.log`).
  - The 4 failures of the ad1d8cb run stay UNRESOLVED. They did not recur here; their cause is not confirmed.
    - Facts: that run took 46,108 s, and Claude Code reaped its shell for low memory.
    - Inference only: a machine suspension or swapping.
  - **Next (Owner approval needed):** a new pre-registration with
    - task text naming the exact contract headings, the JSON block and the length limit;
    - Product Planning 1.0.1 with a conditional provenance criterion;
    - no budget increase.
  - **Running:** only the Owner web server (PID 54292). No test or experiment processes.



## [HISTORICAL — superseded, do not act on] START HERE — Claude takeover round, 2026-10-26 02:22 KST (review checkpoint; NOT a usage-limit stop)
**Claude usage at checkpoint.** 5-hour window 36% remaining (resets ~05:00 KST); 7-day window 91% remaining.

**Git.** Branch `dev/web-ui`, HEAD = the commit containing this section (code e62d440). Not merged into main; not
pushed in this round.
- Commits this round:
  - 180dd64 — Codex's preserved product-planning / experience work, unchanged;
  - b7e96f0 — test_orb Tcl lifecycle fix, restart test, harness proposal;
  - 3a7f432 — 0.1.62 version and changelog;
  - e62d440 — rework-plan stage-results fix.
- Before this section is committed, the only uncommitted change is Codex's own desktop START HERE edit to this
  file. It is preserved below as-is.

**Completed with evidence:**
- Corrected Codex's "full regression running / browser pending". The log has no summary and ends in a
  `Tcl_AsyncDelete` abort, so it is NOT a pass.
- Root cause: `test_orb` Tk roots collected on another test's thread (test lifecycle). Fixed.
  - Full single-process suite on b7e96f0: 457 run, 455 passed, 2 failed (known headless-Edge 90 s timeouts in
    unchanged browser tests).
  - Log `outputs/0.1.40-evidence/FULL-b7e96f0-single-process.log`, hashes `tested-code-b7e96f0.sha256`.
- Targeted:
  - product_planning, departments, web, inputs: 46/46;
  - new restart test (budget kept, experience not duplicated);
  - on e62d440: departments, product_planning, engine, web: 134/134;
  - Node UI fixtures 4/4; JS syntax OK.
- **Real web text-rework E2E** (`docs/evidence/2026-10-26-web-text-rework-e2e.md`):
  - run 1 (build 3a7f432) found an engine defect: an edit-only rework plan gave the verifier no stage results.
    Fixed in e62d440;
  - run 2 (build 0.1.62-e62d440) passed every page check: goal + file + departments → PASS → result → text
    request on the SAME project → REWORK → PASS → revised result containing the requested heading. 10 calls,
    537 s, output 60,363 tokens;
  - **verification was NOT engine-independent**: Codex usage limit, so Claude fell back (recorded);
  - the harness process was reaped for memory pressure; the run completed in the page and its record was
    collected from the isolated DB.
- **Edge stall localized:** after page load (requests at 1.6–2.3 s), the browser never exits the virtual-time
  dump. Root cause unknown.
- **Department Harness proposal** (design only): `docs/DEPARTMENT_HARNESS_PROPOSAL.md`.
  - External source anthropics/knowledge-work-plugins @ 33d3dea, Apache-2.0; partner packages MIT/Apache.
  - **STOP for Owner review**: nothing of H1–H4 is implemented.

**Blocked / not run:**
- **Product A/B comparison** (`python -m axbranch.product_experiment --root <NEW dir>`). Codex CLI: "You've hit
  your usage limit … try again at 5:41 AM", so no independent evaluator is possible. Nothing was started; no
  partial experiment exists.
- Missing source: the "AX BRANCH IN-PLACE EVOLUTION DIRECTIVE" text (20 areas) is not in either attachment, the
  repository or the shared folder.

**Builds** (preserved, BUILD.json each; NOT serving):
- `demo-2026-11/builds/0.1.62-3a7f432` (5ddad583…);
- `demo-2026-11/builds/0.1.62-e62d440` (d619d7ef…).

The Owner's server is unchanged: `builds/0.1.61-67d9095`, http://127.0.0.1:8765/.

**Running processes:** only the Owner's web server (PID 54292), safe to leave. All E2E test processes were
stopped.

**Next, in order:**
1. After Codex recovers, run the A/B comparison once (new root), recording calls, tokens, retries, interventions
   and independence.
2. Owner decision on `DEPARTMENT_HARNESS_PROPOSAL.md` (H1 → H2 …).
3. Persist the provider's unavailability reason in call events.
4. Investigate the Edge cause.

Do not switch the serving build without Owner authorization.


## [HISTORICAL — superseded, do not act on] START HERE — Desktop takeover (2026-10-25 evening KST)
- Owner authorized Codex desktop to continue development before handing back to Claude after 22:00. Do not assume the older CLI is still developing: its latest turn ended at the usage limit. Preserve the inherited product-planning changes.
- Base `dev/web-ui` / `5f70f97`; this continuation is not a release or main merge. Serving web build and user databases are unchanged.
- Python works here with scoped approved execution. The earlier CLI denial and legacy hook failure are NOT shown to be repaired globally. Do not repeat the same environment investigation in this working session.
- Read `docs/evidence/2026-10-25-product-takeover.md` for exact validation results and remaining work, and `docs/IN_PLACE_EVOLUTION_REVIEW.md` for the 20-area directive mapping.
- Preserved implementation: product-planning department, pinned department snapshots, scoped experience cards and UI, experimental budgets and comparison driver. Added malformed scenario-name validation fix and regression test.
- Validation is in progress. Do not start a concurrent test, model run or edit until this turn's final checkpoint is recorded.
- Next order: finish regression and isolated headless web validation; then preserved build and bounded real text-rework/product experiment. Do not call structured experience retrieval proven quality improvement. Do not start LoRA, a replacement CEO or a second engine.
- Owner will manually relay the handoff to Claude. No direct CLI delivery or acceptance is claimed.

## Historical checkpoint — 실행 환경 진단 (2026-10-25 13:09 KST)
- `dev/web-ui`, 수정 코드 `b1275d9`. 이번 시작 기준 `8a5530d`, clean 확인. 새 기능 중단.
- 최신 공유 리뷰의 생성 전 제출 거절 후 수정 불가 문제 수정. 확정된 생성 전 거절만 ID 해제; 응답 유실/부분 생성의 중복 방지는 유지. 프로젝트와 접수 ID는 한 트랜잭션으로 저장.
- 이번 코드 Node DOM 45/45 및 JS 구문 통과. Python API 회귀 추가했으나 실행 경로 접근 거부로 미실행.
- 실패 Hook: `legacy_notify`, 현재 설정 `codex-computer-use.exe turn-ended`, Windows `os error 206`. Python 접근 거부/Chrome `0xC0000022`와 인과관계 근거 없음. Hook 신뢰/보안/notify 설정 변경 없음.
- 현재 셸은 `codexsandboxoffline`. Python 설치 경로 및 HP 레지스트리 접근 거부로 설치 유무를 확정할 수 없음. 경로 한정 읽기/실행 허용 요청 대기.
- Chrome 프로필을 workspace 안으로 옮긴 비교 1회도 동일 GPU 하위 프로세스 접근 거부로 종료. 실제 JS 검사 미도달. 같은 시도 반복 금지.
- 최소 Owner 조치·정확한 명령: `docs/evidence/runtime-2026-10-25/README.md`. 즉시 필요한 범위는 `C:\Users\HP\AppData\Local\Programs\Python\Python312\` 읽기/실행이며 쓰기/관리자 권한은 요청하지 않음.
- 다음: 관련 Python 검사 → 실제 headless Chrome → 전체 회귀 → 보존 빌드 → 텍스트 수정 E2E. 통과 전 서버 전환/오너 개발실 갱신 없음. 이번 `docs/devroom/status.json`은 변경하지 않음.
- 사용자 DB/산출물/Chrome/마우스 보존. main 병합/푸시 없음. 아래는 이전 checkpoint.

## [HISTORICAL — superseded, do not act on] START HERE — Codex checkpoint 2026-10-25 12:16:36 KST
- 브랜치 `dev/web-ui`, 코드 `83a17dd` (이후 문서 상태 커밋). 시작 기준 `1a8df78`, clean 확인.
- W1/W2/W3는 순서대로 수정·로컬 커밋. 현재 코드 Node DOM 35/35 및 JS 구문 통과. 실제 브라우저/서버/모델 검증 아님.
- **4번 실제 텍스트 수정 E2E는 미실행**. `--text-rework` 검증 절차만 준비됨. Python 실행 경로 접근 거부, headless Chrome GPU subprocess 시작 실패.
- 새 EXE 빌드/BUILD.json/서버 전환 없음. 기존 서버·DB·산출물·오너 메모 보존, main 병합/푸시 없음.
- 다음: 실행 환경 복구 → 전체 회귀/Chrome → 보존 빌드 → 같은 격리 프로젝트 텍스트 요청·REWORK·새 PASS·수정 결과 열기.
- 근거: `docs/evidence/2026-10-25-codex-continuation.md`. 보고: 저장소 `outputs/ceo-demo-review/IMPLEMENTATION_STATUS.md` (공유 경로는 쓰기 허용 밖).
- 이전 441/441과 이전 E2E를 이번 검증으로 사용하지 않음. 아래 인계 내용은 역사 기록.

## Codex 착수 — 2026-10-25 12:03 KST
- 브랜치 `dev/web-ui`, HEAD `1a8df78408931fb7fb3edc5d4402c5ea2ceb40fd`, 착수 전 작업 트리 clean. 인계 기준과 일치.
- START HERE와 공유 CODEX_REVIEW.md(07:53 KST) 확인. 완료된 화면 수정은 반복하지 않음.
- 첫 작업: W1 프로젝트별 승인/피드백 폼 및 지연 응답 분리. 이어서 W2 제출 복구, W3 뉴스, 텍스트 수정 E2E 순서.
- 기존 DB/산출물 보존, main 병합/푸시 없음. 사용자 Chrome/마우스 사용 없음.
- 현재 셸에서 인계에 적힌 Python 실행 경로를 찾지 못함. 실행 환경 확인 중이며 이전 테스트는 이번 검증으로 사용하지 않음.

# Codex CLI handoff — AX Branch (Claude usage at 8%: handed over 2026-10-25 ~12:00 KST)

## [HISTORICAL — superseded, do not act on] START HERE (Owner order of 2026-10-25, step 2 done by Claude, step 3 is yours)
- Repo `C:\Users\HP\Desktop\AX-Branch\ax-branch`, branch `dev/web-ui`, HEAD = this commit (code 67d9095).
  Not merged into main; do not merge.
- **Step 2 is DONE.** Codex's screen fix (devroom `.recommendation` card, sidebar saved titles) was reviewed and
  committed as 67d9095.
  - Tests: `tests.test_web` 10/10, `tests.test_gui`, headless Chrome self-test 23/23.
  - Built as `demo-2026-11/builds/0.1.61-67d9095` (AXBranch.exe sha256 c4ea707a…).
  - The demo web server was switched to it: http://127.0.0.1:8765/. The Owner must REFRESH their tab.
  - **No full regression on 67d9095.** F161b 441/441 is for 7fae36f and must NOT be shown as 67d9095's result.
- **Step 3, in order** (re-check `outputs/ceo-demo-review/CODEX_REVIEW.md` first):
  1. Switching projects in the web UI can leave another project's approval note or feedback text visible. The
     owner panel keeps `box.dataset.mode = mode + iteration`; key it by project id too, and clear the text when
     switching. Add a self-test.
  2. Duplicate project if the submit response is lost and the page reloads. The page creates `S.requestId` in
     memory only. Persist the draft request id in `sessionStorage` until the server confirms. On reload with a
     pending id, ask the server (`created_by`) instead of re-creating. Test with the server responding but the
     client dropping the response.
  3. News: show the fetch time and refresh failures per source (`home-feeds.json` has `fetched` and `error`), and
     show the latest 3 on the home screen.
  4. Then a real web flow on an existing project: send a TEXT change request (review with text) → REWORK →
     verification → result open. Use `tests/browser_web_e2e.py` as the model, on an isolated root with a copy of
     a finished project or a fresh small one. Record calls, tokens and interventions. Never resume unrelated
     projects. No LoRA training.
- After each unit:
  - commit;
  - update `docs/devroom/status.json` in plain Korean (keep Owner memos, they are in the workspace);
  - write `outputs/ceo-demo-review/IMPLEMENTATION_STATUS.md`;
  - build into `demo-2026-11/builds/<version>-<commit>/` with BUILD.json (never overwrite);
  - switch the server only after its checks pass.
- Do not open or close the Owner's Chrome. Use headless Chrome with a temporary profile only. No paid API, new
  credentials or sensitive permissions.

# Codex CLI handoff — AX Branch (kept current by Claude)

## [HISTORICAL — superseded, do not act on] LATEST (2026-10-25 06:50): HEAD ad9b3f4 (code 7fae36f), F161b 441/441
- Added since 02:40:
  - web artifact library + 이어서 개발 (`actions.develop`);
  - 오너 개발실 redesign (`status.json` schema 2);
  - preserved builds in `demo-2026-11/builds/` with BUILD.json;
  - web-path E2E harness `tests/browser_web_e2e.py` and two runs (`docs/evidence/2026-10-25-web-e2e.md`);
  - fix 7fae36f: the verifier gets the earlier stages' results.
- **Running:** the web server from `demo-2026-11/builds/0.1.61-ad9b3f4` (stop it with `AXBranch.exe web --stop`).
  The Owner's Tk window is untouched.
- **Codex review loop:** read `outputs/ceo-demo-review/CODEX_REVIEW.md`; write results to `IMPLEMENTATION_STATUS.md`
  there.

## [HISTORICAL — superseded, do not act on] CURRENT (2026-10-25 02:40): branch `dev/web-ui`, version 0.1.61, final code 7884507, NOT merged into main
- The single structured status record is `docs/devroom/status.json`, shown in the web UI's 오너 개발실. Update it
  at each work unit; never mark code as verified without evidence.
- Done (all tested on 7884507; F161 439/439, hash list in the Codex evidence folder `tested-code-161.sha256`):
  - shared Owner actions (`axbranch/actions.py`);
  - local web UI (`axbranch/web.py`, `axbranch/webui/`) and 오너 개발실;
  - engine 1: contract format check;
  - engine 2: department acceptance gate;
  - engine 3: cross-version reuse, dependents re-run, reasons recorded;
  - engine 4: Owner-run network allowlist — Python audit hook, best effort, not OS isolation;
  - engine 5: browser phase timing.
- Real E2E P-20261025-1d2aec on package 5a38799c (commit 90bb049): `docs/evidence/2026-10-25-e2e-161.md`. It
  found a contract false positive, fixed in 7884507.
- Final package: `demo-2026-11/package-0.1.61-web` (rebuilt from 7884507 plus this status record; its hash is in
  README-WEB.txt). The old Tk package `package-0.1.60` is kept.
- **Running processes:**
  - the web server `package-0.1.61-web\AXBranch\AXBranch.exe web` on the demo workspace, http://127.0.0.1:8765/,
    started by Claude. Stop it with `AXBranch.exe web --stop`;
  - the Owner's own Tk window (`package-0.1.60`): not started by Claude, left untouched.
- Owner checks open: README-WEB.txt items 1–3. Confirmed by the Owner: only the old Tk window's drag into the home
  goal area.
- Next: see the proposals in status.json. OS isolation needs Owner approval (admin rights).
- Rules: no paid API, credentials or sensitive permissions without approval; never weaken tests; do not touch the
  Owner's browser windows, profile, mouse or keyboard (headless with a temporary profile only); no main merge.

# Codex CLI handoff — department harness (kept current by Claude)

Repository: `C:\Users\HP\Desktop\AX-Branch\ax-branch`. Branch `dev/departments` (pushed to origin), based on `main`
11a36bf (0.1.59). Version 0.1.60, final reliability pass committed on this branch (see `git log`). Not merged into main (Owner).

## Done (0.1.60)
- Department harness:
  - `axbranch/departments.py` + `departments/{research,operations}/department.json`: validated, versioned
    packages; per-project attach/detach as events;
  - engine `STAGE.department`, enforced at staffing and before execution (only attached departments, tools and
    network within the department); `department_delegation`, `temporary_agent`, `department_result` records;
  - each stage receives only its own department brief; independent verification is unchanged.
- Window:
  - sidebar department library (drag onto the composer or a project, or click → details → [프로젝트에 추가]);
  - composer [부서 첨부]; the project's "연결된 부서" row with detach;
  - pipeline titles `[부서] agent` / `[임시 에이전트] agent`; a reused stage shows ✓ "재사용".
- Motion: `home.StatusOrb` from real state only (no timer when idle, in error or done); "모션 끄기" in workspace
  settings.json; the current pipeline node and the hand-off into it are statically emphasised.
- `AXBranch.exe --open <id>` (view only) and `axbranch result <id>` / `AXBranch.exe result <id>` (= [결과 실행]).
- Fixes: a duplicate refresh loop from direct refresh() calls; the orb timer is cancelled on destroy.
- Reliability pass (final 0.1.60):
  - temporary agents are bound by the attached departments' tools and network and may not take an unattached
    department's agent role (`check_stage`, CEO rule); `temporary_agent` records its tools and web flag;
  - a drag drop that lands nowhere (or on a covered spot) says "연결되지 않았습니다" and points to
    [프로젝트에 추가];
  - `axbranch department <id> list|attach|detach` (also `AXBranch.exe department …`): the window's rules,
    mouse-free.

## After the reliability pass (2026-10-24, later)
- Real E2E on the final code: P-20261024-304eb4.
  - Pinned: commit 9483c1e, package 77db6aa9.
  - Sequence: research → operations, Codex FAIL then PASS, CEO accepted. 7 calls, 653 s, tokens recorded.
  - See `docs/evidence/2026-10-24-final-e2e.md`.
- The `code_generation` exception was traced: it allows writing only; execution runs through the engine's
  contained verification and the Owner's own launch. See the enforcement doc.
- Motion:
  - `axbranch/orb.py` particle sphere wired to real state in the composer;
  - preview: `python -m axbranch.orb` (상태 시뮬레이션);
  - see `docs/evidence/2026-10-24-orb-motion.md`.
- Package rebuilt with the motion: sha256 ef5f8b5a… (replaces 77db6aa9, which the E2E used).
- Owner checks open: `demo-2026-11/package-0.1.60/OWNER-DRAG-CHECKLIST.txt` (real drag, motion during a real
  run). None of these items is marked as passed.

## Evidence
- `docs/evidence/2026-10-24-departments.md`: the completion criteria mapped to tests, the real E2E, suites and the
  package check.
- Real E2E P-20261024-5dd942 (demo workspace): research → operations, Codex FAIL then PASS, CEO accepted. Driver
  and logs are in the Codex work folder
  `C:\Users\HP\Documents\Codex\2026-10-17\referenced-chatgpt-conversation-this-is-an`:
  `work/run_department_e2e.py`, `outputs/department-e2e*`.
- Tests:
  - F160d, final code, hash-matched: 413/414. The one failure is a headless-Edge 90 s timeout in an unchanged
    browser test; it passed 3/3 when run alone.
  - F160b's failure was isolated 10× per checkout: branch 8/10, main 9/10, same message.
  - See `docs/evidence/2026-10-24-F160b-runtime-failure.md`.
- Enforced versus declared department fields: `docs/evidence/2026-10-24-department-enforcement.md`. There is no
  OS isolation.
- Package: `C:\Users\HP\Desktop\AX-Branch\demo-2026-11\package-0.1.60\AXBranch\AXBranch.exe` (sha256
  77db6aa9…818f), README-DEMO.txt beside it.
  - Verified: department attach / duplicate / detach / relaunch restore in an isolated root; `--open` for 2 demo
    projects; `result` → the inquiry app, no model call.
  - The drag gesture itself was not done on the package (no real mouse).

## Exact notes carried from 0.1.59
- Selecting an agent shows its record: role and engine, department, why hired, task/instructions, its stage
  output, and for the Verification Agent every verification round with its findings and evidence.
- The 0.1.59 EXE did not check project navigation or [결과 실행] by click. In 0.1.60 both paths were checked on the
  EXE through `--open` and `result` (no real mouse clicks, by Owner rule).

## Remaining (not done)
- Merging dev/departments into main (left for the Owner/Codex decision).
- More departments beyond research and operations.
- Headless-Edge 90 s timeouts on this PC in browser runtime tests (intermittent, also on main; root cause not
  investigated, limit not raised).
- Real-model E2E of a temporary agent / refusal / detach (deterministic tests only).
- Not verified: another PC, Windows without Python, other display scalings.

## Reproduce
- Tests: `python -X utf8 -m unittest tests.test_departments tests.test_gui tests.test_live`.
- Full suite: in the Codex work folder, `AXB_NATIVE_E2E=1 python -X utf8 outputs/0.1.40-evidence/suite2.py <TAG>`.
- Package: `python -X utf8 -m PyInstaller --noconfirm --clean --onedir --windowed --name AXBranch --paths
  ..\cheongwol\ceo --hidden-import cheongwol.connectors --add-data "<abs repo>\departments;departments"
  --distpath <out> axbranch_app.py`. Use an absolute --add-data source.

## Rules (Owner)
- No paid API, no new credentials, no global installs, no external publishing or customer contact, no governance
  relaxation, never weaken tests.
- Do not resume the production law-firm project or held reviews. No full-screen capture and no real mouse movement;
  use a DB copy with execution disabled, or the exe's `--open`/`result`.
- Do not run heavy tests and model runs at the same time.

## Running processes
- None started by Claude.

## Codex W1 checkpoint — 2026-10-25 12:06 KST
- 프로젝트·판정별 폼, 각 프로젝트 초안 보존, 지연 프로젝트/기록 응답과 오래된 폼 액션 차단 구현.
- 새 코드: node --check 및 Node DOM 회귀 10/10. 실제 Chrome은 GPU subprocess 접근 거부로 종료(통과 아님). Python/새 EXE 빌드/실제 모델 E2E는 접근 제한으로 미실행.
- 다음 W2 제출 ID 복구. 기존 서버는 변경하지 않음.

## Codex W2 checkpoint — 2026-10-25 12:09 KST
- 제출 직전 sessionStorage 기록, GET /api/submission으로 created_by 조회, 확인된 접수 복구. 파일 내용은 저장하지 않으며 미접수 첨부는 재선택 필요. 의도적으로 바꾼 목표에는 미확인 ID 재사용 금지.
- Node DOM W1 10/10 + W2 11/11; 서버 unittest 추가했으나 Python 접근 제한으로 미실행. 빌드/서버 전환 없음. 다음 W3.

## Codex W3 checkpoint — 2026-10-25 12:10 KST
- 출처별 마지막 성공 수집 시각·24시간 경과·갱신 실패를 캐시 유무와 무관하게 표시. 출처/게시일, 홈 최신 3개씩, 전체 목록 유지.
- Node DOM 9/9, JS 구문 확인. Python 캐시 보존/출처별 실패 회귀 추가했으나 미실행. 빌드/서버 전환 없음. 다음 텍스트 수정 E2E.

