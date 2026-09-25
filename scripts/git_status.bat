@echo off
cd /d "%~dp0.."
echo === branch === > scripts\git_status_output.txt
git branch --show-current >> scripts\git_status_output.txt
echo === status === >> scripts\git_status_output.txt
git status >> scripts\git_status_output.txt
echo === log -8 === >> scripts\git_status_output.txt
git log --oneline -8 >> scripts\git_status_output.txt
echo === branch -a === >> scripts\git_status_output.txt
git branch -a >> scripts\git_status_output.txt
