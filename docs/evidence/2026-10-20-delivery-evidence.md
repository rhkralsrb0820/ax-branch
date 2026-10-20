# 0.1.47 delivery evidence for native EXE goals — 2026-10-20

## Problem (real Goal 3, P-20261019-32a79d)
Goal 3 had a verifier PASS, but the CEO judged it "partly" in three rounds. Each time it ordered the same evidence:
- the EXE delivery path and existence;
- its size and SHA-256, linked to the build and run records;
- a record that Python was absent from PATH when the EXE ran.

`_deliver` showed the CEO only runtime step names, ok flags and problems. The build record (path/size/SHA-256)
existed in `checks['native_build']`, but it went only to the verifier. Native runs used PATH=%SYSTEMROOT%\system32,
yet recorded only environment key names. No record held the hash of the executable copy that ran.

## Change
- runtime: `native_executable_sha256` (the bytes that ran) and `execution_environment` {PATH,
  python_on_path: python.exe/python3.exe/py.exe/python files found on it}.
- engine `_deliver`: `deterministic_evidence.native_build` (ok, exe, size, sha256, tool, config, reused) and
  `native_run` (executable, sha256, same_bytes_as_build, execution_environment, network, notes).

## Verification
- New test `test_delivery_judgment_receives_exe_identity_and_run_environment`: it fails on 0.1.46 with
  KeyError 'native_build'.
- The real-EXE E2E test now also asserts that the run hash equals the build hash and that `python_on_path == []`.
- F147, full suite: 376/376 in 43 sequential Job Object-audited batches with AXB_NATIVE_E2E=1 (the real PyInstaller
  build and run included). No skipped, failed or unrun tests, bad batches, or surviving test-job processes.
- Source/test hashes were recorded before the run and re-checked unchanged after it
  (2026-10-20-F147-code-hashes.sha256, 2026-10-20-F147-summary.json).

## Limits
- Same PC: Python is installed here but unreachable from the run's PATH. This is not a clean Windows machine.
- Network activity of a native EXE is unknown (no in-process audit hook); it is never reported as zero.
- Whether the CEO now stops re-requesting evidence is confirmed only by the real Goal 3 continuation (recorded separately).
