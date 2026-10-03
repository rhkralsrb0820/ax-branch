# AX Branch — rules for any coding agent (Claude Code, Codex CLI)

Read before working: `README.md`, `CHANGELOG.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`.
Project *runtime* state lives in `../workspace/axbranch.sqlite3`; each project's
`../workspace/projects/<id>/HANDOFF.md` says what is next. Do not rely on chat history.

- Python 3.11+, standard library only. Run `python -X utf8 -m unittest discover -s tests -t .` before handing off.
- Never modify `../cheongwol`, `../ax-works`, `../global-ai-intelligence` from here. GAI's DB is read-only.
- No paid API, paid plan, publication or external contact. `governance.py` changes need the Owner.
- Every release: bump `axbranch/__init__.py:__version__`, add a CHANGELOG entry (date, added,
  changed, fixed, verification, known issues). `tests/test_release.py` fails if they disagree.
- Commit with what changed, test results, and open issues so the other engine can continue.
