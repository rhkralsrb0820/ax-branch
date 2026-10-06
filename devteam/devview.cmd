@echo off
rem AX Branch development view: Codex / workers pane on the right (observe only).
rem Keep Claude Code in the window on the left. Nothing here needs input.
start "CODEX CLI - AX Branch development" python -X utf8 "%~dp0devview.py"
