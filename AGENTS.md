# AX Branch — rules for any coding agent (Claude Code, Codex CLI)

Read before working: `README.md`, `CHANGELOG.md`, `docs/PROJECT_STATE.md`, `docs/TASK_STATE.md`,
`docs/ARCHITECTURE.md`, `docs/DECISIONS.md`. Do not rely on chat history: persistent state is the truth.

## Continuing AX Branch runtime work (any engine)

When asked to continue AX Branch work, determine the next action from persistent state only:

1. In this folder run `python -X utf8 -m axbranch status`. It lists every project and its state
   (Source of Truth: `../workspace/axbranch.sqlite3`).
2. Continue **only** projects in an active state: CREATED, PLANNING, STAFFING, EXECUTING, VERIFYING, REWORK.
   For each one:
   - read `../workspace/projects/<id>/HANDOFF.md` (`next_action`, `ax_branch_git`, `consistency_problems`);
   - run `python -X utf8 -m axbranch check <id>`; if it is not `consistent`, stop and report;
   - run `python -X utf8 -m axbranch run <id>`. It calls the Claude/Codex CLIs itself and can take
     several minutes: give the command a long timeout (30 minutes). If it is cut off, run it again;
     it resumes from SQLite.
3. Do **not** touch other projects. PAUSED, PENDING_CLOSE, ARCHIVE_PENDING_APPROVAL and CLOSED are
   Owner decisions: never `resume`, `finish` or close them on your own.
4. Never do the production or verification agents' work yourself, and never edit artifacts,
   `HANDOFF.md` or the SQLite database by hand.
5. Report: project id, state before and after, `check` result, the last lines of `status <id>`,
   and `git log -1 --oneline`.

## Developing AX Branch

- Python 3.11+, standard library only. Run `python -X utf8 -m unittest discover -s tests -t .` before handing off.
- Never modify `../cheongwol`, `../ax-works`, `../global-ai-intelligence` from here. GAI's DB is read-only.
- No paid API, paid plan, publication or external contact. `governance.py` changes need the Owner.
- Every release: bump `axbranch/__init__.py:__version__`, add a CHANGELOG entry (date, added,
  changed, fixed, verification, known issues). `tests/test_release.py` fails if they disagree.
- Commit locally with what changed, test results and open issues. Do not push.
