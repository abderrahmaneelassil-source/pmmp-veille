# Sauvegarde quotidienne de la base pmmp_veille (Planificateur de taches Windows).
# pg_dump ne fait que LIRE la base : sans risque pour le collecteur, meme pendant un run.
# Identifiants : PMMP_DATABASE_URL du .env (compte pmmp_app), passes a pg_dump par la
# variable PGPASSWORD de ce seul processus : aucun mot de passe dans la tache ni sur disque.
# Sortie : storage\backups\pmmp_veille_<date>.dump (format -Fc, restauration : PASSATION.md),
# les $Conserver plus recentes sont gardees. Journal : storage\logs\backup_<date>.log.
# Enregistrement de la tache (une fois, PowerShell, utilisateur courant) :
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\chemin\pmmp_collector\scripts\backup_db.ps1" -WorkingDirectory "C:\chemin\pmmp_collector"
#   $t = New-ScheduledTaskTrigger -Daily -At 11:30
#   $s = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
#   Register-ScheduledTask -TaskName "PMMP-Sauvegarde" -Action $a -Trigger $t -Settings $s
# 11:30 : apres la fin de la fenetre de collecte (06:00-10:00) et de la limite de la tache
# PMMP-Veille (5 h), pour sauvegarder le resultat du run du matin.
# Codes de sortie : 0 sauvegarde faite, 1 echec (voir le journal).
param([int]$Conserver = 14)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

$Horodatage = Get-Date -Format "yyyyMMdd_HHmmss"
$LogDir = Join-Path $ProjectDir "storage\logs"
$BackupDir = Join-Path $ProjectDir "storage\backups"
New-Item -ItemType Directory -Force $LogDir, $BackupDir | Out-Null
$LogFile = Join-Path $LogDir "backup_$Horodatage.log"

function Journal([string]$Message) {
    $Ligne = "{0} {1}" -f (Get-Date -Format s), $Message
    Add-Content -Path $LogFile -Value $Ligne -Encoding utf8
    Write-Output $Ligne
}

try {
    $Ligne = Get-Content (Join-Path $ProjectDir ".env") -Encoding utf8 |
        Where-Object { $_ -match '^\s*PMMP_DATABASE_URL\s*=' } | Select-Object -First 1
    if (-not $Ligne) { throw "PMMP_DATABASE_URL introuvable dans .env" }
    $Uri = [System.Uri](($Ligne -split '=', 2)[1].Trim())
    $Identifiants = $Uri.UserInfo -split ':', 2
    $Utilisateur = [System.Uri]::UnescapeDataString($Identifiants[0])
    $Base = $Uri.AbsolutePath.TrimStart('/')
    $Port = if ($Uri.Port -gt 0) { $Uri.Port } else { 5432 }

    # pg_dump de la version de PostgreSQL la plus recente installee
    $PgDump = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]$_.Directory.Parent.Name } -Descending | Select-Object -First 1
    if (-not $PgDump) { throw "pg_dump.exe introuvable dans C:\Program Files\PostgreSQL\*\bin" }

    $Fichier = Join-Path $BackupDir "$($Base)_$Horodatage.dump"
    $env:PGPASSWORD = [System.Uri]::UnescapeDataString($Identifiants[1])
    & $PgDump.FullName -h $Uri.Host -p $Port -U $Utilisateur -d $Base -Fc --no-owner --no-privileges -f $Fichier 2>&1 |
        ForEach-Object { Journal "pg_dump : $_" }
    $Code = $LASTEXITCODE
    Remove-Item Env:PGPASSWORD
    if ($Code -ne 0) { throw "pg_dump a echoue (code $Code)" }

    $Taille = (Get-Item $Fichier).Length
    if ($Taille -lt 1024) { throw "sauvegarde anormalement petite ($Taille octets) : $Fichier" }
    Journal ("Sauvegarde faite : {0} ({1:N0} Ko)" -f $Fichier, ($Taille / 1KB))

    Get-ChildItem $BackupDir -Filter "$($Base)_*.dump" | Sort-Object Name -Descending |
        Select-Object -Skip $Conserver | ForEach-Object { Journal "Ancienne sauvegarde supprimee : $($_.Name)"; Remove-Item $_.FullName -Force }
    Get-ChildItem $LogDir -Filter "backup_*.log" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } | Remove-Item -Force
    exit 0
}
catch {
    if (Test-Path Env:PGPASSWORD) { Remove-Item Env:PGPASSWORD }
    Journal "ECHEC de la sauvegarde : $($_.Exception.Message)"
    exit 1
}
