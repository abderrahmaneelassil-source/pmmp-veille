@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" "scripts\db_status.py"
