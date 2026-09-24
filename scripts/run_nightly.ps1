# Lancement nocturne du collecteur PMMP (Planificateur de tâches Windows).
# Enregistrement de la tâche (une fois, PowerShell administrateur) :
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\chemin\pmmp_collector\scripts\run_nightly.ps1"
#   $t = New-ScheduledTaskTrigger -Daily -At 23:30
#   $s = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
#   Register-ScheduledTask -TaskName "PMMP-Veille" -Action $a -Trigger $t -Settings $s
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

$LogDir = Join-Path $ProjectDir "storage\logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("run_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
# Redirection faite par cmd.exe et non par PowerShell : sous PowerShell 5.1, avec
# ErrorActionPreference=Stop, la premiere ligne ecrite par Python sur stderr (tous les
# logs Scrapy) arreterait le script, et "*>>" ecrirait le log en UTF-16.
cmd.exe /d /c "`"$Python`" -m pmmp_collector crawl >> `"$LogFile`" 2>&1"
$Code = $LASTEXITCODE
Add-Content -Path $LogFile -Value ("{0} code de sortie {1} (0=succes 1=echec 2=refuse 3=partiel)" -f (Get-Date -Format s), $Code) -Encoding utf8

Get-ChildItem $LogDir -Filter "run_*.log" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } | Remove-Item -Force
exit $Code
