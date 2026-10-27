# B6 — intermittent headless-browser stall: bounded diagnostics (2026-10-27) — root cause UNRESOLVED

**Method.**
- The single test `tests.test_runtime.RuntimeTests.test_rendered_page_is_checked_not_just_served` was run
  sequentially with nothing else running, on source 9684256 (the same commit as the 504/504 full regression).
- 13 runs in two batches; script: session scratchpad `b6_diag.py`. No timeout change and no retry-until-pass.
- Per run: outcome, phase timings, request list, free memory and browser process count.
- Records: Codex work folder `outputs/b6-browser-diag-9684256.jsonl` (5 runs) and `...-b.jsonl` (8 runs).

## Observations (measured)
- **1 stall in 13 runs** (batch 1, run 4; 114 s).
  - The test renders twice: a positive render and a negative render whose content is expected to fail.
  - The stall was in the negative render. Requests were seen at 1.25–1.47 s, then Edge never exited before the
    90 s limit (`outcome: time limit`). The positive render of the same run exited normally.
- **Memory and processes:** free memory stayed between 5.9 and 6.2 GB. The browser process count was the same
  before and after every run (23, the Owner's own browsers included), so no leaked browser process was observed.
- **Request counts:** the stalled render saw 3 requests instead of the usual 2. Batch 2 identified the third as
  `GET /favicon.ico -> 200`. That same extra request occurred in **5 renders that exited normally**, so favicon
  alone is **not** a sufficient explanation.
- The stall also appeared during the concurrent test_runtime run on 2026-10-27 00:39 and in earlier full runs.
  It did **not** occur in the 504/504 full regression on 9684256.

## Status
- Root cause: **not established**. Ruled out as sufficient: low memory and leaked browser processes (as measured
  here), and the favicon request alone.
- Not measured: the browser's internal virtual-time state. Sleep or swapping are not claimed.
- Next bounded step (IB-3): when a render reaches the time limit, record the Edge process tree and the open
  connections to the test server before killing it. Still no timeout increase.

## Update — 2026-10-28: snapshot at the time limit narrows the cause
Source 2761687 with `runtime.stall_snapshot`, the same single test run alone. Records: `outputs/b6-browser-diag-2761687.jsonl` (15 runs) and `...-b.jsonl` (20 runs).
- **Stalls: 1/15 and 3/20.** All 4 stalls show the same state at the 90 s limit:
  - Processes: only the Edge **browser main process and crashpad-handler**. No renderer, GPU or network/utility
    process was alive.
  - Connections: none open on the app or proxy ports. Earlier connections were `TimeWait` (closed); only the
    harness's own `Listen` sockets remained.
  - Output: `stdout_bytes_at_limit` 8,237–8,242. The `--dump-dom` output had already been printed.
- **Conclusion (evidence-based, narrow):** the page load, scripts and requests had finished and the DOM was dumped.
  The browser main process then failed to exit. This is a browser shutdown hang after output, not an app or
  network wait.
  - Its internal cause inside Edge is still UNKNOWN.
  - Not established: whether Chrome behaves the same, and whether `--disable-features`/crashpad flags avoid it.
- **Change:** `runtime.shutdown_hang()` accepts a stalled load only when all three hold:
  1. the printed DOM is complete (ends with `</html>`);
  2. nothing but the browser main process and crashpad is left;
  3. no connection is open.

  The result is then judged on that DOM and the hang is recorded (`browser_shutdown_hang`). Every other stall still
  fails. No timeout was increased; a hang still costs the full limit.
