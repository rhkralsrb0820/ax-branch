# 0.1.46 native build evidence — 2026-10-20

## Problem and fix
Goal 3 P-20261019-32a79d v1 ran its actual textcount.exe successfully in all 11 runtime steps,
but the verifier received no packaging provenance. The engine now includes native build configuration,
result, executable hash and one-file mode in deterministic_checks.native_build. A cached EXE keeps the
recorded provenance after the existing configuration and hash checks. Failure gates are unchanged.

## Validation
375/375 tests, 43 sequential audited batches; no skips, failures, unrun tests or surviving test processes.
Native module separately passed 7/7, including a real PyInstaller build and reuse provenance check.
The regression failed with KeyError(native_build) before the fix. All 52 source/test hashes matched after F146.
The source/test hash manifest and the full-suite summary are stored beside this evidence file.
Raw batch logs remain in the development workspace outputs/0.1.40-evidence/F146*.
One engine batch includes a long overnight interruption; wall-clock durations are not performance measurements.

## Goal state and limits
- Goal 1: OWNER_REVIEW v3 (research); 50/50 selected claims supported in its last verification.
- Goal 2: OWNER_REVIEW v2 (CSV); totals 100 rows / 16 projects / 31 PASS / 69 FAIL match the baseline.
- Goal 3: PAUSED HARNESS_BLOCKED v1; 11/11 EXE runtime steps passed before this fix, but native network
  activity remains unobserved. Owner explicitly chose HOLD on 2026-10-20, preserving the evidence standard.
  No post-fix live re-verification or PASS is claimed. No firewall/system settings were changed.
- Verification took place on this PC, not a clean Windows installation. Generated code containment is not
  OS-level network isolation. The packaged AX Branch application itself was not rebuilt.
- Claude automatic continuation was cancelled and its Goal 3 worker stopped before Codex continued it.
- Owner authorized GitHub persistence; origin/main already contains 0.1.45 (7d2c381).
