# Phase 0 audit & reuse map (2026-10-03)

## Git state at audit

| Repo | Branch / HEAD | Working tree |
|---|---|---|
| `cheongwol` | main `87cfefa` | clean |
| `ax-works` | main `77f1927` | clean |
| `global-ai-intelligence` | main `a5bbe4c` | clean (fresh clone, no `data/`) |

No uncommitted Owner work existed. **AX Branch v0.1 modifies none of the three repos.**

## What each repo is

**cheongwol** (v0.5.1, Python stdlib only, 439 tests pass, 2 skipped). Control process + Runtime state
machine for a single CEO, append-only hash-chained SQLite journal, owner approval fingerprints,
web-source quote verification, Tkinter GUI, MCP server, PyInstaller one-folder build.
`connectors.py` runs `claude -p` / `codex exec` with locked-down tool flags, detects real quota
refusals (wordings observed live) and hands the same request to the other subscription only on
quota. Refuses to run if a paid API key is in the environment.

**ax-works** (0.2, Python stdlib server + vanilla JS web UI, pywebview desktop shell). Personal
workspace: documents, citation review, meeting notes, tasks/approvals, reports. AI intentionally
unconnected (`ai.py` seam). `scripts/collab.py` is a Claude→Codex review queue for *development*.

**global-ai-intelligence** (FastAPI/Jinja2, feedparser). RSS/arXiv/HF collectors into
SQLite `items`. Live library is **not** this clone: it is
`Desktop/AI-Trend-Collector/data/ai_intelligence.db` (209 items at audit), updated by a 07:00 KST
Windows task. Its owner forbids writes, resets or migrations.

**Vault** `obsidian/AX-Branch-Vault/Branch_DB/` — Obsidian config only, no notes.
**Tools found**: Python 3.12.10, claude 2.1.284, codex-cli 0.159.0, git, PyInstaller 6.22.3, tkinter.

## Reuse map

| Need | Reused from | How |
|---|---|---|
| Claude/Codex subprocess, quota detection, paid-key guard, cancel/timeout | cheongwol `connectors.py`, `policy.py` | **imported** (`axbranch/providers.py`), not copied |
| Desktop app (Tk + PyInstaller one-folder) | cheongwol `gui.py` / `build_exe.py` pattern | same approach, new small window |
| Owner-governance ideas (approval for sensitive acts, no paid fallback, observed-only reporting) | cheongwol ADRs, ax-works `QUALITY_AND_SPEND.md` | encoded in `axbranch/governance.py` |
| AI intelligence context | global-ai-intelligence DB | **read-only** SQLite URI (`mode=ro`) in `knowledge.intel()` |
| Workspace / task UI | ax-works | not used in v0.1 (see DECISIONS D4) |

## Conflicts & risks

- cheongwol's model is *one* CEO with Owner approval of every report; AX Branch's spec is an
  autonomous CEO + independent Verification Agent. Different contracts → separate orchestrator
  instead of bending cheongwol's frozen policy.
- Port 8765 is used by both cheongwol Control and ax-works. AX Branch opens no port.
- Importing cheongwol's underscore helpers couples AX Branch to cheongwol internals. Mitigated by
  the provider tests; if cheongwol renames them, `providers.py` fails at import (loud, not silent).
- Generated Python artifacts are executed during verification (self-test, 120 s timeout, isolated
  temp dir, `-I`). This is the same OS account — not a security sandbox.
