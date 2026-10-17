# Repeated failure / re-planning analysis — P-20261016-5fb8d6 (로펌 실사 계약 검토기), 2026-10-17

Source: runtime DB (read-only), artifacts v1-v22, workspace/logs. Project PAUSED at v22 (iteration 23 never built):
NEEDS_DECISION "the same failure ... recurred after a forced change of approach". v22: runtime 25/39, Verification FAIL.
Owner effort: 3 problem reports (v8, v15, v18: "local service is not responding / unreachable" in the Owner's own
launch), 3 resumes, 1 network approval (7 public research domains).

## 1. Remaining v22 failures by class
| Class | Steps | Evidence |
|---|---|---|
| Verification-tool (harness) defect | oversized body refused (forged Content-Length, refused by the probe rules); 2 BROWSER probes whose "actions" are prose scenarios ("on clean Windows without Python, double-click the hashed executable...") | probe_misconfigured; failed identically v7-v22 |
| Harness limit misread as product | 3 controller probes need >60 s (e.g. "SERVICE ALIVE AFTER 120S PASS") but CLI probes stop at 60 s | "did not finish within 60s" classified product |
| Environment / capability missing | standalone Windows .exe for a machine without Python; clean no-Python test machine; native double-click | controllers print UNVERIFIED (exit 1); no packaging tool installed; Owner launch declared as ".exe" |
| Possibly product (ambiguous) | HTML report lacks 'confirmed', CSV lacks the note, persisted records not shown after reload | expected text missing; not proven product |
| Owner decision | native standalone .exe (see 4) | requires new software or system setup |

## 2. change_pipeline rounds vs the same failure
Six change_pipeline decisions (v4->, v10->, v12->, v14->, v20->, v21->) changed the detection approach, pipeline order,
"capability discovery first", "patch v20 instead of rewrite". The products did change. The failing set did not, because
(a) the unexecutable checks were preserved by the contract rule (T5) and never reviewed — probe review ran only when
there was NO product evidence; (b) the native-.exe capability never existed; (c) the repeat signature counted the
harness-class steps, so every round looked like "the same failure".

## 3. Final producer losing earlier outputs
v9, v16, v17: "entry file DiligenceReviewDesk.zip.py is missing from the bundle"; v17: "the previously passing seven
source sections are lost". Cause: bundles were always regenerated whole (edits-only applied to single files only);
the bundle was 176 KB (two 88 KB files) returned in one model reply each round.

## 4. The Owner's real launch was never tested
owner_launch: "Extract DiligenceReviewDesk.zip and double-click DiligenceReviewDesk.exe ... No installed Python".
The harness's "exact Owner launch" ran `python DiligenceReviewDesk.zip.py` and reported PASS (v22 too). The Owner's
"service unreachable" was never reproduced: after the first report the delivered v7 passed acceptance; the revised
checks "failed" only because two of them could not execute, and that was recorded as reproduction.

## Structural fixes (0.1.38)
- F-A: an owner_launch that runs a native .exe/.msi is a declared capability gap (native_executable_launch): stops
  before production instead of a false Owner-launch PASS (uses the 0.1.37 capability gate).
- F-B: checks proven unexecutable are always sent to probe review (equivalent repair validated independently, or
  UNRESOLVED -> HARNESS_BLOCKED naming the checks), even when the product also failed.
- F-C: the repeat signature excludes harness-class steps.
- F-D: reproduction counts only executable checks; unexecutable ones are recorded separately.
- F-E: large bundles get edits-only builds; untouched files carry forward.
Each fix has a regression test that fails on the previous code (executed mutation).

## Not changed (honest limits)
- Whether the remaining HTML/CSV/persistence failures are product defects is UNKNOWN until checks execute validly.
- The Owner's "service unreachable" root cause is UNKNOWN: AX Branch cannot run the Owner's native-launch path.
