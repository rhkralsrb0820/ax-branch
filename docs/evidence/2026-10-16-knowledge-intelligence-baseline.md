# Development update — Knowledge Intelligence: evidence baseline (2026-10-16) — verdict HOLD

Read-only measurement (runtime DB sha256 identical before/after). Evidence: workspace/handoff/ki-evidence/
(eval-20261016-003330.json from `python -m axbranch.kindex eval`, ki_baseline.py/.json). No code changed.

## Evidence gate (project-level independence)
| | historical baseline | now | gate |
|---|---|---|---|
| situations | 37 | 40 | — |
| projects | 11 | 13 | — |
| deterministic labeled situations | 2 | 4 | >= 50 |
| labeled independent projects | 1 | 2 | >= 20 |
| challenger verdicts K1 / S / K1+S | HOLD | HOLD | — |

On the 4 labeled situations: K0 recall@3 0.50, K1 1.00, K1+S nDCG 1.00. Not evidence: 2 projects, gate unmet. HOLD.

## Findings
- Missed relevant experience (VERIFIED, cause): both K0 misses (P-3a4f60 failure + planning -> P-cfa1d6) happen
  because K0 reads only the vault, and the vault gets experience only when the Owner closes a project with "save"
  (Owner-authorized archive). Branch_DB holds 3 notes for 13 projects; 5 delivered projects sit in OWNER_REVIEW.
  The derived index (K1: DB experience cards, read-only) recovers both. The gap is availability of experience,
  not ranking technology.
- Noise: K0 top-3 noise 0.78 over all situations (mostly situations with nothing relevant); live CEO rejected 2 of 9
  presented items (22%).
- Live retrieval chain: 21 retrievals in 3 projects (CEO planning 6, Verification 12, legacy 3); 7 ADOPTED with a
  stated decision change, 7 reached an action, outcomes recorded. Improvement: UNKNOWN (no counterfactual).
- Attribution confounding of labeled failure situations: c88366 V-474d43 UNKNOWN; 3a4f60 V-90c893 PRODUCT VERIFIED.
- Korean (deterministic probes): particle stripping works (원화 금액을 == 원화 금액). Compounds written without a space
  (원화금액, 주식분석, 상태코드, 업무도구) get 0 hits in K0 and K1; inflected verbs (분석하는) miss in K0.
  Impact on real situations UNPROVEN: 0 of 40 historical queries had zero hits.
- Latency/resources: K0 median 6.6 ms (max 9.2 ms), K1 2.7 ms, index 225 KB, vault 3 notes / 305 KB. No resource gap.

## Decision
HOLD. No technology discovery: no measured gap that a new retriever, embedding or dependency would close. The
demonstrated gap (experience availability) is already covered by the derived index, whose promotion waits for the
evidence gate. Labeled evidence grows with each independent real project (about 1 labeled project per web-tool run).
Candidate hypothesis for when labels exist: Hangul character n-gram tokens for compounds (stdlib), A/B on the same gate.

## Phase-boundary evaluation of HIGH EVIDENCE_GAP
The executive acceptance of each of the last 5 web-tool projects lists unverifiable evidence the probe schema cannot
express: browser text entry + multi-step clicks (cfa1d6 x3, 3a4f60, 3e5ca9, c88366), cross-Origin headers and
PUT/DELETE (7f20e6, cfa1d6). Deliveries rest on code reading for these claims, and missing deterministic evidence is a
main source of attribution UNKNOWN (30 of 52 replayed subjects). Recommendation: EVIDENCE_GAP is the next priority,
ahead of roadmap expansion.
