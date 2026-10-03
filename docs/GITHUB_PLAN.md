# GitHub repository

**Done 2026-10-03 (Owner approved):** `https://github.com/rhkralsrb0820/ax-branch`, visibility
PRIVATE, `main` tracks `origin/main`. Verified after push: remote HEAD == local HEAD (`fa8daf7`),
remote file set identical to `git ls-files` (26 files), no DB/log/exe/key/build files on the remote.
The other three repositories are unchanged with their own remotes.

---

Plan as prepared before the push:

Target: a new **private** repository `rhkralsrb0820/ax-branch`, separate from the existing three
(`rhkralsrb0820/-` = cheongwol, `ax-works`, `global-ai-intelligence`), which are not touched.

Checked 2026-10-03: `gh` is logged in as `rhkralsrb0820` (scopes include `repo`); the name
`ax-branch` is free; full-history scan found no secrets (OpenAI/GitHub/AWS key patterns, private
keys) and no database, log, exe, key or build files in any commit.

## What is excluded (`.gitignore`)
Runtime SQLite and agent context (`*.sqlite3*`, `*.db`, `workspace/`, `projects/`, `HANDOFF.md`),
build outputs (`build/`, `dist/`, `*.spec`, `build.log`), logs, caches, `.env*`, keys and
credentials files, `.claude/`, `.codex/`, editor/OS files. Runtime state lives outside the repo in
`../workspace/` and the vault in `../obsidian/`, so they cannot be committed from here.

## Commands (Owner runs, or tells the agent to run)
```powershell
cd C:\Users\HP\Desktop\AX-Branch\ax-branch
git status --short            # must be empty
gh repo create rhkralsrb0820/ax-branch --private --source . --remote origin --push
gh repo view rhkralsrb0820/ax-branch --json visibility   # expect "PRIVATE"
```

## Note for a fresh clone
AX Branch imports cheongwol's provider layer from the sibling folder `../cheongwol/ceo`.
Clone both side by side under one AX-Branch folder (with `workspace/` and `obsidian/` next to them).
