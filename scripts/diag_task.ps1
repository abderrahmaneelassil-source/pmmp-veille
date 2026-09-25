# diag_task.ps1 - Diagnostic de la tache planifiee PMMP-Veille
$ErrorActionPreference = "Continue"
$out = New-Object System.Collections.Generic.List[string]

$out.Add("=== Diagnostic tache planifiee PMMP-Veille ===")
$out.Add("Date/heure du diagnostic (locale): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')")
$out.Add("")
$out.Add("--- Fuseau horaire systeme ---")
$out.Add((Get-TimeZone | Format-List | Out-String))

$out.Add("--- La tache existe-t-elle ? ---")
$task = Get-ScheduledTask -TaskName "PMMP-Veille" -ErrorAction SilentlyContinue
if ($task) {
    $out.Add("OUI, tache trouvee.")
    $out.Add(($task | Format-List * | Out-String))
    $out.Add("--- Get-ScheduledTaskInfo ---")
    $out.Add((Get-ScheduledTaskInfo -TaskName "PMMP-Veille" | Format-List * | Out-String))
    $out.Add("--- Actions ---")
    $out.Add(($task.Actions | Format-List * | Out-String))
    $out.Add("--- Triggers ---")
    $out.Add(($task.Triggers | Format-List * | Out-String))
    $out.Add("--- Settings ---")
    $out.Add(($task.Settings | Format-List * | Out-String))
    $out.Add("--- Principal ---")
    $out.Add(($task.Principal | Format-List * | Out-String))
} else {
    $out.Add("NON : aucune tache nommee 'PMMP-Veille' trouvee dans le Planificateur.")
    $out.Add("Toutes les taches existantes (nom + chemin) :")
    $out.Add((Get-ScheduledTask | Select-Object TaskName, TaskPath, State | Format-Table -AutoSize | Out-String))
}

$out.Add("")
$out.Add("--- Journal Historique du Planificateur (Operational log) ---")
try {
    $logObj = Get-WinEvent -ListLog "Microsoft-Windows-TaskScheduler/Operational" -ErrorAction Stop
    $logEnabled = $logObj.IsEnabled
    $out.Add("Journal actif (Activer l'historique de toutes les taches) : $logEnabled")
    if (-not $logEnabled) {
        try {
            wevtutil set-log Microsoft-Windows-TaskScheduler/Operational /enabled:true
            $out.Add("-> Journal active maintenant (etait desactive avant). L'historique ne couvrira que ce qui se passe a partir de maintenant.")
        } catch {
            $out.Add("-> Echec activation automatique (droits admin necessaires ?) : $_")
        }
    }
} catch {
    $out.Add("Impossible de verifier l'etat du journal : $_")
}

try {
    $events = Get-WinEvent -LogName "Microsoft-Windows-TaskScheduler/Operational" -MaxEvents 500 -ErrorAction Stop |
        Where-Object { $_.Message -match "PMMP-Veille" }
    if ($events) {
        $out.Add("Evenements trouves pour PMMP-Veille (parmi les 500 derniers evenements du journal) :")
        $out.Add(($events | Select-Object TimeCreated, Id, LevelDisplayName, Message | Format-List | Out-String))
    } else {
        $out.Add("Aucun evenement pour PMMP-Veille dans les 500 derniers evenements du journal Operational.")
    }
} catch {
    $out.Add("Impossible de lire le journal Operational : $_")
}

$out.Add("")
$out.Add("--- Contenu de storage\logs (le script run_nightly.ps1 ecrit ici a CHAQUE execution, planifiee ou non) ---")
$logDir = Join-Path (Split-Path -Parent $PSScriptRoot) "storage\logs"
if (Test-Path $logDir) {
    $out.Add((Get-ChildItem $logDir -Filter "run_*.log" | Sort-Object LastWriteTime -Descending | Format-Table Name, Length, LastWriteTime -AutoSize | Out-String))
} else {
    $out.Add("Dossier introuvable : $logDir")
}

$outPath = Join-Path $PSScriptRoot "diag_output.txt"
$out -join "`r`n" | Out-File -FilePath $outPath -Encoding utf8
Write-Output "Diagnostic termine. Voir $outPath"
