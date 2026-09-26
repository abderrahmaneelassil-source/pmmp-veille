# test_run.ps1 - Declenche PMMP-Veille comme le ferait le Planificateur (Start-ScheduledTask
# est l'equivalent programmatique exact du clic droit > Executer dans l'interface du
# Planificateur : meme appel COM ITaskService::Run, action et contexte non supervises
# identiques - contrairement a "python -m pmmp_collector crawl --force" qui court-circuite
# la verification de fenetre horaire du collecteur).
$ErrorActionPreference = "Continue"
$out = New-Object System.Collections.Generic.List[string]

$out.Add("=== Test de declenchement de PMMP-Veille via le Planificateur ===")
$out.Add("Heure locale avant declenchement : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")

$before = Get-ScheduledTaskInfo -TaskName "PMMP-Veille"
$out.Add("LastRunTime avant : $($before.LastRunTime)")
$out.Add("LastTaskResult avant : $($before.LastTaskResult)")

Start-ScheduledTask -TaskName "PMMP-Veille"
$out.Add("Start-ScheduledTask envoye.")

Start-Sleep -Seconds 10

$after = Get-ScheduledTaskInfo -TaskName "PMMP-Veille"
$out.Add("")
$out.Add("Heure locale apres attente : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
$out.Add("LastRunTime apres : $($after.LastRunTime)")
$out.Add("LastTaskResult apres : $($after.LastTaskResult)")

$out.Add("")
$out.Add("--- storage\logs (fichiers run_*.log) ---")
$logDir = Join-Path (Split-Path -Parent $PSScriptRoot) "storage\logs"
$files = Get-ChildItem $logDir -Filter "run_*.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
if ($files) {
    $out.Add(($files | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize | Out-String))
    $latest = $files | Select-Object -First 1
    $out.Add("--- Contenu du plus recent : $($latest.Name) ---")
    $out.Add((Get-Content $latest.FullName -Raw))
} else {
    $out.Add("AUCUN fichier run_*.log trouve.")
}

$out.Add("")
$out.Add("--- Evenements du journal Operational pour PMMP-Veille (depuis l'activation de l'historique) ---")
try {
    $events = Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 100 -ErrorAction Stop |
        Where-Object { $_.Message -match "PMMP-Veille" }
    if ($events) {
        $out.Add(($events | Select-Object TimeCreated, Id, LevelDisplayName, Message | Format-List | Out-String))
    } else {
        $out.Add("Aucun evenement (l'historique vient d'etre active, ou pas encore ecrit).")
    }
} catch {
    $out.Add("Impossible de lire le journal : $_")
}

$outPath = Join-Path $PSScriptRoot "test_run_output.txt"
$out -join "`r`n" | Out-File -FilePath $outPath -Encoding utf8
Write-Output "Termine."
