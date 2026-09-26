# fix_task.ps1 - Active "Reveiller l'ordinateur pour executer cette tache" sur PMMP-Veille.
# Root cause identifiee : la tache existe, est correctement configuree (action, working
# dir, trigger quotidien 06:00) et un declenchement manuel (Start-ScheduledTask) fonctionne
# parfaitement (log ecrit, refus correct hors fenetre). Mais ce matin la tache s'est
# reellement declenchee a 11:46 (StartWhenAvailable = rattrapage tardif) au lieu de 06:00 :
# preuve que le PC n'etait pas disponible (eteint/veille) a 06:00, et comme WakeToRun=False,
# Windows n'a pas reveille la machine, attendant que l'utilisateur revienne pour rattraper -
# bien apres la fin de la fenetre (06:00-10:00), d'ou un refus systematique.
$ErrorActionPreference = "Stop"
$out = New-Object System.Collections.Generic.List[string]

try {
    $task = Get-ScheduledTask -TaskName "PMMP-Veille"
    $settings = $task.Settings

    $out.Add("WakeToRun avant : $($settings.WakeToRun)")
    $settings.WakeToRun = $true
    Set-ScheduledTask -TaskName "PMMP-Veille" -Settings $settings | Out-Null

    $verif = (Get-ScheduledTask -TaskName "PMMP-Veille").Settings
    $out.Add("WakeToRun apres : $($verif.WakeToRun)")
    $out.Add("StartWhenAvailable : $($verif.StartWhenAvailable)")
    $out.Add("DisallowStartIfOnBatteries : $($verif.DisallowStartIfOnBatteries)")
    $out.Add("StopIfGoingOnBatteries : $($verif.StopIfGoingOnBatteries)")
    $out.Add("Enabled : $($verif.Enabled)")
    $out.Add("STATUT : OK, WakeToRun active avec succes (pas d'elevation necessaire, tache possedee par l'utilisateur courant).")
} catch {
    $out.Add("ECHEC : $_")
}

$out -join "`r`n" | Out-File -FilePath (Join-Path $PSScriptRoot "fix_task_output.txt") -Encoding utf8
Write-Output "Termine."
