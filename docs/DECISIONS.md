# Decisions

**D1 (2026-10-03) Separate orchestrator repo, no monorepo merge.** `AX-Branch/ax-branch` is a new
repo. cheongwol / ax-works / global-ai-intelligence stay untouched and keep working. Why: all three
are working systems with their own contracts; merging would break them for no v0.1 gain.

**D2 Import cheongwol's provider layer instead of copying.** Its quota/paid-key handling encodes
live-observed CLI behavior. Cost: coupling to private helpers (see AUDIT risks).

**D3 Standard library only, Tk GUI, PyInstaller one-folder.** Same proven approach as cheongwol.
Nothing to install to run from source.

**D4 ax-works not integrated in v0.1.** Its UI/task module is not on the critical path of the
Goal → verified artifact loop. Revisit when AX Branch needs a richer workspace UI.

**D5 Artifacts are single files returned as JSON; agents get no shell.** Keeps production agents
inside the subscription CLIs' restricted mode and keeps every artifact hashable and versioned
(`artifacts/v<N>/`). Multi-file / repo-editing agents are a later capability.

**D6 Deterministic checks gate PASS.** Evidence beats confidence: a failing self-test fails the
round even if the verifier model says PASS.

**D7 Round budget pauses, never lowers the bar.** After `MAX_ROUNDS` FAILs the project pauses for
the Owner; resume grants more rounds.

**D8 Provider order is retried every turn; no reset-time guessing.** Matches cheongwol's rule.
