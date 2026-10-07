@echo off
rem AX Branch in development mode: the latest source, no console window. For GUI checks between exe builds.
cd /d "%~dp0"
start "" pythonw -X utf8 -m axbranch
