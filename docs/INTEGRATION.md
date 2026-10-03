# Integration: Global AI Intelligence and AX Works

Principle: the three existing systems stay separate repos and keep working on their own.
AX Branch connects to them through narrow, read-only or Owner-mediated seams. It never
writes into their data stores.

## Global AI Intelligence (GAI) — implemented

| What | Status |
|---|---|
| Read-only access to the live library (`Desktop/AI-Trend-Collector/data/ai_intelligence.db`, `AXB_GAI_DB` to override) via SQLite `mode=ro` | done (0.1.0) |
| Relevant items (≤5) given to the CEO at planning; never the whole library | done |
| Relevance: an item must match ≥30% of the goal's terms (min 2) — stray two-word matches were injecting off-topic papers | done (0.1.5) |
| Provenance: `context_used` event records exactly which vault notes and GAI items (title + URL) the CEO saw; archived under Evidence | done (0.1.5) |
| GAI collection/scheduling | stays in GAI (07:00 KST task). AX Branch does not collect. |

Next candidates (not started): let a Research agent request GAI items by topic during a stage;
use GAI's `verification_status` to rank evidence.

## AX Works — planned, not implemented

Audit 2026-10-03: AX Works has never run on this PC (no `data/workspace.sqlite3` exists), and
its rules forbid other tools from overwriting its data. So there is nothing live to integrate
against yet, and nothing could be verified.

Planned seams, in order, each only when AX Works has real data and the Owner wants it:
1. **Read-only knowledge source.** Owner documents in AX Works (`items` table) offered to the CEO the
   way vault notes are: `mode=ro`, relevant excerpts only, provenance recorded.
2. **Deliverable hand-over.** Verified artifacts exported as Markdown into a folder the Owner imports
   through AX Works' own upload screen (AX Works keeps sole write access to its DB).
3. **Owner work surface (later product decision).** AX Works' approval/task screens as a richer Owner
   UI for AX Branch. Changes AX Works' scope, so it is an Owner decision.
