# AX Branch

Owner-governed autonomous AI execution. The Owner gives a Goal; **淸月 AI CEO** interprets it,
designs a pipeline, hires temporary specialist agents, runs them on the Claude Code / Codex CLI
subscriptions, and only receives artifacts the independent **Verification Agent** has passed.
Failed artifacts go back to the production agents and are rebuilt until they pass. The bar is
never lowered.

```sh
python -m axbranch                         # Owner window (or dist/AXBranch/AXBranch.exe)
python -m axbranch new "goal..." --run     # CLI
python -m axbranch status [<id>]
python -m axbranch run <id>                # continue any project from SQLite (Claude or Codex session)
python -m axbranch resume <id> [--rounds N]
python -m axbranch review <id> [--works | --broken "..."] [--request "..."] [--finish]   # Owner review
python -m axbranch approve <id> --network yes|no      # external connections the program would make
python -m axbranch replan <id> --reason "..."         # recovery: CEO strategy review
python -m axbranch effort [<id>]                      # Owner Effort KPI
python -m axbranch finish <id> [--save | --pause | --discard --confirm] [--satisfaction N]
```

Product principle: *you manage the goal; AX Branch manages the AI work* — planning, agents, engine
choice, verification (incl. running the result the way you will), recovery and handoffs between
Claude Code and Codex.

Requirements: Python 3.11+, `claude` and/or `codex` CLI logged in with a subscription,
and the sibling `../cheongwol` repo (its provider layer is reused). No paid API is used;
a paid API key in the environment stops the run.

Where things live (all under the AX-Branch folder):

| What | Where |
|---|---|
| Runtime state (Source of Truth) | `workspace/axbranch.sqlite3` |
| Artifacts, per version | `workspace/projects/<id>/artifacts/v<N>/` |
| Handoff for any engine | `workspace/projects/<id>/HANDOFF.md` |
| Long-term knowledge (Save & Close only) | `obsidian/AX-Branch-Vault/Branch_DB/Projects/` |
| AI intelligence (read-only) | `Desktop/AI-Trend-Collector/data/ai_intelligence.db` (`AXB_GAI_DB` to override) |

Tests: `python -X utf8 -m unittest discover -s tests -t .` · Build exe: `python -X utf8 build_exe.py`

Docs: [Architecture](docs/ARCHITECTURE.md) · [Phase 0 audit & reuse map](docs/AUDIT.md) ·
[Decisions](docs/DECISIONS.md) · [Changelog](CHANGELOG.md) · agent rules [AGENTS.md](AGENTS.md)
