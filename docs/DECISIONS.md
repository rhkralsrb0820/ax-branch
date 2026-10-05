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

**D5 Artifacts are returned as JSON (one file, or a bundle of files since 0.1.5); agents get no shell.** Keeps production agents
inside the subscription CLIs' restricted mode and keeps every artifact hashable and versioned
(`artifacts/v<N>/`). Agents that edit an existing repository in place are a later capability.

**D6 Deterministic checks gate PASS.** Evidence beats confidence: a failing self-test fails the
round even if the verifier model says PASS.

**D7 Round budget pauses, never lowers the bar.** After `MAX_ROUNDS` FAILs the project pauses for
the Owner; resume grants more rounds.

**D8 Provider order is retried every turn; no reset-time guessing.** Matches cheongwol's rule.

**D9 (0.1.4) One session per project via an OS file lock.** Released by the OS on crash, so no stale
locks; refused sessions change nothing.

**D10 (0.1.5) Bundles are hash-addressed by manifest; model paths are untrusted.** Only safe relative
paths are written; refusals fail verification rather than pausing the project.

**D11 (0.1.5) Unexpected errors pause, never strand; schema is versioned.** Learned live: an older
packaged exe crashed on a newer schema and the project sat in EXECUTING with no trace.

**D12 (0.1.6) Generated code runs contained, not isolated.** Clean environment + Job Object (process
and memory caps, whole tree killed at the end). Reading the user's files and network access remain
possible under the same account; a dedicated low-privilege Windows account is the upgrade path and
needs Owner setup (account creation is an Owner action).

**D13 (0.1.8) Verification includes Runtime Acceptance.** Owner acceptance found a program that passed
source review and its self-test but closed 0.3 s after a double-click with no usable surface. PASS now
also requires the artifact to work when launched the way the Owner launches it. The self-test moved to
`--self-test`; a no-argument launch is the Owner's program. Launch contracts are enforced in code.

**D14 (0.1.8) Owner feedback reopens the same project.** History, agents and knowledge are kept; the
engine reproduces the problem and the CEO diagnoses before any rebuild. Normal rework never spawns a
new project.

**D15 (0.1.9) "Does it work?" and "What next?" are separate questions.** A working version can still
be improved; confirming it works must not close or freeze the project. The Owner writes plain
language and the CEO interprets it into requirements, pipeline and agents. Closure only on an explicit
finish.

**D16 (0.1.9) A delivered program's new external connections need the Owner.** Added
`external_connection` to the Owner-only actions (tightening, per the Owner's governance list). The CEO
declares domains; the engine waits for approval before building.
