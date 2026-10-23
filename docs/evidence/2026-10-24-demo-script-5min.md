# 5-minute demo script — AX Branch 0.1.58 (Owner)

Package: `C:\Users\HP\Desktop\AX-Branch\demo-2026-11\package-0.1.58\AXBranch\AXBranch.exe` (double-click).
Workspace: `C:\Users\HP\Desktop\AX-Branch\demo-2026-11\workspace` (opened automatically; separate from production).
Everything in parts A–C is a RECORDED run from 2026-10-23/24. Say so. Part D is the only live execution.

## A. 淸月 home (0:00–0:45) — recorded state
- The summary and status graph come from the saved project states (2 projects in 검토).
- Optional: press "공개 정보 새로 수집". It reads the OpenAI News and Python.org jobs public feeds; each item shows
  its date and source. A collection failure or stale information is stated, never hidden.

## B. Demo project "문의 분류 라우팅 AI" (0:45–3:00) — recorded run, not re-executed
1. Click it on the left. The banner says 검토 대기 (verified result waiting for the Owner).
2. Pipeline: 淸月 CEO (Claude) → engineer (Claude) → Verification Agent (Codex, PASS) → Runtime Acceptance (19/19).
3. Click 타임라인. Point out:
   - v1–v3 failed verification: the download host was refused, a random-init substitute, LoRA at chance;
   - the CEO changed the pipeline itself;
   - v4–v6 builds produced nothing and the 6-build limit paused for the Owner;
   - v8 passed.
4. Click "Verification Agent" for the verifier's evidence.
5. Be explicit about what was manual:
   - the network approvals;
   - a provider routing switch;
   - the developer's tokenizer diagnosis, given as labelled feedback;
   - AX Branch code fixes 0.1.53/0.1.55.
   AX Branch made the v8 fix itself.
6. Results, official test set (n=3080), evaluated once after selecting on dev:
   - baseline TF-IDF+LR: accuracy 0.9088, macro-F1 0.9090, team routing 0.9669 (selected);
   - LoRA (real CPU training): 0.7432 / 0.7284 / 0.9159 → "lora_not_better". No LoRA gain is claimed.

## C. Use the delivered product (3:00–4:15) — verified result, launched now
1. Press [결과 실행]. The local app opens at http://127.0.0.1:8050 (this PC only, no public deployment).
2. Type an English bank inquiry, e.g. "I lost my card yesterday" → intent, team (카드팀), confidence (model score,
   not calibrated). The page names the method in use (baseline).

## D. Optional live run (4:15–5:00+) — NEW execution, real subscription calls, takes minutes
- Type a small goal in the top box and press [淸月 CEO에게 맡기기]. The cards give way to the live pipeline; the banner
  says 작업 중 and states that feedback is not applied during a run.
- The earlier live check (P-20261024-5bfdd1) took 6 calls and 389 s, including one real FAIL → rework → PASS.
- Skip this part if time or quota is short; parts A–C need no AI call.

## If something goes wrong
- 결과 실행 shows "학습 환경 ... 없어 실행하지 않았습니다": the training stack is missing on this PC. The message gives
  the recovery command (`python -X utf8 -m axbranch training-env`, free official downloads, about 1 GB).
- Do not use `ax-branch\dist\AXBranch\AXBranch.exe` (old build from 2026-10-08).
