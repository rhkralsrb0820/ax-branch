# Pastel dashboard redesign — 0.1.59

Owner reference images informed the layout, not the displayed data. The latest Owner direction is pastel
colours and rounded corners, superseding the dark sidebar intermediate design.

## Changes
- Lavender navigation, a static CEO identity sphere, rounded goal composer and feed cards.
- Pastel blue/lavender/peach/mint status cards; bars and donut use stored project states only.
- Goal composer folds in project view; New task restores it without starting a job.
- Actual sequential pipeline, agent detail, timeline and approval controls retain their existing handlers.
- Project commands are grouped in a menu. The agent table has both scrollbars.
- Scrollbars use rounded pastel thumbs without native arrows/grips. Record panes use the same scrollbar;
  table and notebook borders are flattened. Project status shows a short summary instead of debug fields.

## Verification
- Final related tests: `python -X utf8 -m unittest tests.test_home tests.test_gui tests.test_live` —
  30 passed in 112.681 seconds, including composer folding/restoration without starting a project.
- F159 (Codex) finished 400/400, but UI files were edited during it, so it is NOT counted.
- F159b (Claude, 2026-10-24) on the unchanged final code: 401/401 in 46 sequential Job Object-audited batches with
  AXB_NATIVE_E2E=1 (the real generated-program EXE build test included); hashes recorded before and unchanged after.
- Package demo-2026-11/package-0.1.59/AXBranch/AXBranch.exe rebuilt from that code (sha256 e9570eb8...):
  - opened through the shell and showed "AX Branch 0.1.59" on the demo workspace (2 projects);
  - the demo DB counters were unchanged (events 387, call_start 29, training_run 4).
  - In two later openings the window was minimized / closed within ~2 s. No code in the app minimizes or quits
    it; this was most likely interaction on the Owner's active desktop. Not reproduced as an app defect, and not
    proven either. Project navigation and 결과 실행 were checked in-process (preview with execution disabled)
    and, for the same code paths, on the 0.1.58 package.
- Screenshots (PrintWindow of the app window only): ui/2026-10-24-v059-home.png, -v059-project-verification.png.
- Visual inspection uses a SQLite backup in a separate workspace with supervisor, project execution and result
  execution disabled. The production and demo databases are not edited for inspection.
- Dashboard and pipeline were inspected through native window screenshots on this PC.

## Limits
- Tk native buttons and window chrome are not web/CSS components; no glass blur is implemented.
- No invented feed entries, historical performance series or progress percentages.
- Existing feed coverage, generated-app dependencies and unverified cross-PC portability remain unchanged.
- Visual changes do not demonstrate new autonomous model capabilities.
