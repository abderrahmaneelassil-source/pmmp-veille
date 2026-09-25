# Lancement quotidien planifie du collecteur PMMP (Planificateur de taches Windows).
# Le nom "run_nightly" est historique : depuis le 25/09/2026 la tache tourne le MATIN,
# a 06:00, debut de la fenetre PMMP_ALLOWED_WINDOW=06:00-10:00 (choix du stagiaire,
# different de la consigne d'origine du chef de projet : nuit 23:00-06:00).
# Si la fenetre change dans .env, changer aussi l'heure de la tache (README section 8).
# Enregistrement de la tache (une fois, PowerShell, utilisateur courant) :
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\chemin\pmmp_collector\scripts\run_nightly.ps1" -WorkingDirectory "C:\chemin\pmmp_collector"
#   $t = New-ScheduledTaskTrigger -Daily -At 06:00
#   $s = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 5)
#   Register-ScheduledTask -TaskName "PMMP-Veille" -Action $a -Trigger $t -Settings $s
# Le collecteur verifie lui-meme la fenetre : lance hors fenetre, il refuse (code 2)
# sans aucune requete au portail.
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
