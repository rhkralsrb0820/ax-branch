# Forum demo evidence — 2026-10-24 (AX Branch 0.1.55)

Demo workspace: `C:\Users\HP\Desktop\AX-Branch\demo-2026-11`. It is separate from production and validation.
Owner launcher: `C:\Users\HP\Desktop\AX-Branch\demo-2026-11\AXBranch-Demo.cmd`, which opens the 淸月 CEO app
(source, Python 3.12) on the demo workspace. No EXE is provided for AX Branch itself; `dist/AXBranch.exe` is stale.

## 1. Demo project P-20261023-2a0e75 "문의 분류 라우팅 AI" (customer inquiry → intent → team)

### Final results (v8, verified PASS by Codex)
Evaluation is independent: selection uses dev only, and the official test split was evaluated exactly once by a
runtime check after selection.

| Method | dev macro-F1 | test accuracy | test macro-F1 | test team-routing accuracy |
|---|---|---|---|---|
| Baseline TF-IDF + logistic regression (**selected**) | 0.9213 | 0.9088 | 0.9090 | **0.9669** |
| LoRA, google/bert_uncased_L-4_H-256_A-4, CPU, 2 epochs | 0.7320 | 0.7432 | 0.7284 | 0.9159 |

LoRA genuinely learned once its input was fixed: dev macro-F1 went 0.0034 (v3) → 0.7320 (v8). It did NOT beat
the baseline, so `selection.json` records `lora_not_better` and the app serves the baseline. No LoRA improvement
is claimed.

- Data: Banking77 (PolyAI, CC BY 4.0), official train/test, with a stratified 10% dev split from train.
- Model: Apache-2.0, pinned revision 387825ce. Sources, versions and licences are recorded in the training
  outputs (`SOURCE.json`, `metrics.json`).
- Product: a local web app/API on 127.0.0.1:8050 (POST /api/classify → intent, team, confidence, top 3).
  - Verified by 19 runtime steps, including the browser flow, cross-origin refusal and the exactly-once test.
  - Owner path (결과 실행) verified for real: health = baseline with 77 labels; 3 new inquiries routed to
    카드팀 / 송금·이체팀 / 충전·환전팀. Screenshot: `ui/2026-10-24-demo-app.png`.
- Deployment: LOCAL only. No external or public deployment.

### What AX Branch did autonomously (engine records)
- CEO plan v1:
  - data and licence checks, baseline vs LoRA, dev-only selection, exactly-once test, local app;
  - network_access declared, and approval requested before any download.
- Capability resolver attached model_training after a real CPU LoRA probe (local_cpu_lora).
- Round history, each with Claude/Codex builds and independent verification:
  - v1: LoRA was blocked by its own allowed-host list → FAIL.
  - v2: a random-init substitute (disclosed) → FAIL.
  - Replan, CEO strategy change_pipeline: approve the redirect host first; ban random init.
  - v3: real weights, but LoRA stayed at chance → FAIL.
  - v4–v6: no usable deliverable. The edits did not apply ("find occurs 0 times") and then the reply was empty.
    The CEO changed provider and contract; the 6-build budget then paused it for the Owner.
  - v8: after the tokenizer finding (below), one edit build → PASS → CEO acceptance → OWNER_REVIEW.
- Training ran 4 times (159, 807, 794, 793 s), contained, with outputs kept and hashed. Finished runs are reused on
  resume.

### Manual interventions (developer / Owner — NOT autonomy)
- Owner approvals recorded through `Engine.decide_network`: the public data/model hosts and the HF CDN redirect.
- Developer routing: after a Claude build hit the 1800 s timeout, the driver switched to the CEO's own provider
  choice (`--follow-ceo`).
- Developer error: a `timeout 60` wrapper killed one call (exit 143). Recorded as such.
- Developer code fixes made in AX Branch itself:
  - 0.1.53: edit-mode contract and the kept rejected replies;
  - 0.1.55: the Owner-run parity for trained results.
- Developer LoRA diagnosis (3 local runs, no model calls; scratchpad `lora_diag.py`):
  - under transformers 5.20.2, `BertTokenizer(Fast)(vocab_file=...)` ignored the vocab file, giving a 5-token
    vocabulary and 100% `[UNK]`; `from_pretrained(<model folder>)` gives 30,522 tokens;
  - with it, a 64-example LoRA overfit reached loss 0.025 and train accuracy 1.0.
  - The finding was given to the project as LABELLED developer feedback through the Owner channel. AX Branch then
    made the fix itself in v8.

### Cost and time (CLI-reported usage; none estimated)
- 20 successful calls (Claude 10, Codex 10) plus 2 failed calls. Provider time 6,582 s, about 110 min.
- Tokens:
  - input 586,090;
  - Claude cache creation 430,269 and cache read 362,859;
  - Codex cached 0;
  - output 329,513.
- One early Claude build alone emitted 118,930 output tokens in 995 s.

## 2. Live end-to-end flow from the home screen (P-20261024-5bfdd1, 2026-10-24)
- Who entered the goal: Claude, through the real GUI (`AXB_DEV=1`, so it is recorded as development, not as the
  Owner).
- Goal: "a CLI that counts inquiries and their share per team from a classification CSV, with clear errors".
- Flow:
  - the home cards folded and the project view showed live status;
  - CEO plan (Claude, 98 s) → engineer v1 (Claude) → Codex verification FAIL: a real defect, rows with a blank
    team were dropped and the total understated;
  - rework v2 → Codex PASS (7/7 runtime steps) → CEO acceptance → OWNER_REVIEW.
- 6 calls, 389 s of provider time.
- 결과 실행 opened the tool in its own console. On a 5-row sample it showed 카드팀 2 (40%), (미지정) 1, 송금/이체팀 1,
  충전·환전팀 1, total 5.
- Screenshots: `ui/2026-10-24-flow-1-goal-accepted.png`, `-flow-2-verified-owner-review.png`, `-flow-3-owner-run.png`.

## 3. Demo script (for the Owner)
1. Double-click `AXBranch-Demo.cmd`. The 淸月 home shows the summary, the status graph, and the AI trend / job cards
   (press 공개 정보 새로 수집 for live feeds with dates and sources).
2. Open "문의 분류 라우팅 AI" on the left. Show:
   - the pipeline;
   - the Agent 기록 / 타임라인 tabs with the failure history v1–v8 and the CEO strategy changes;
   - the verification evidence.
   These are RECORDED runs from 2026-10-23/24, not a new run.
3. Press 결과 실행. The local app opens at 127.0.0.1:8050; type an English bank inquiry to see intent, team and
   confidence. State that the method is the baseline and that LoRA was tested and lost.
4. Optional live part: type a small goal in the home input and press 淸月 CEO에게 맡기기. Plan, agents, verification
   and delivery run for real, taking minutes and using subscription calls.

## 4. Regression on the final code (0.1.55, commit 3096612)
- F155, full suite: 394/394 in 45 sequential Job Object-audited batches with AXB_NATIVE_E2E=1 (the real PyInstaller
  build and run included). No skipped, failed or unrun tests, bad batches, or surviving test-job processes.
- Source/test/CHANGELOG hashes were recorded before the run and re-checked unchanged after it:
  `2026-10-24-F155-summary.json`, `2026-10-24-F155-code-hashes.sha256`.

## 5. Limits (honest)
- LoRA on this CPU (2 epochs, about 450 s) is below the baseline. A GPU or longer training might change that;
  that is not demonstrated.
- The training stack is a per-user pinned environment (`%LOCALAPPDATA%\axb\te-9af54a16`), not packaged; the
  result is not portable to another PC as is.
- The AX Branch app runs from source (Python 3.12); no fresh EXE.
- The generated code's network use is controlled by policy, not by OS isolation.
- `permissions.classify` mislabels huggingface.co as an api_key risk (the word "tokenizer"); not fixed yet.
- Layout: the agent table is squeezed at the default window size. The AI trends come from a single publisher feed,
  and job items carry no dates.
- Verifier and CEO judgments are model judgments; deterministic checks bound them but do not replace them.
