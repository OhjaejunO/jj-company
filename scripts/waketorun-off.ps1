<#
  Turn OFF WakeToRun on the four JJ scheduled tasks. (2026-08-22, JJ decision "plan C")

  ASCII-only on purpose (same reason as every other script here): Windows
  PowerShell 5.1 reads a BOM-less UTF-8 .ps1 as the system ANSI codepage and
  mangles non-ASCII text. Korean belongs in scripts\prompts\*.md, not here.

  MUST RUN ELEVATED.
    Measured 2026-08-22: without admin, Set-ScheduledTask RETURNS SUCCESS and
    the value does not change. Reading the task XML afterwards still showed
    WakeToRun=true. That is the "silently failing code" the charter forbids,
    so this script re-reads the value after writing and exits FAIL if unchanged.

  WHY turn it off
    This PC is shut down (Fast Startup), not slept. RTC wake timers do not fire
    from a powered-off state, so WakeToRun cannot work here. Leaving it True
    keeps claiming a capability that does not exist, and the next person
    re-investigates the same dead end.

  DO NOT rebuild the Settings object - change ONE field on the existing one.
  Rebuilding drops StartWhenAvailable / MultipleInstances back to defaults.
#>
$ErrorActionPreference = 'Stop'
$path = '\JJ\'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$elev = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
          [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $elev) {
  Write-Host "STATUS: FAIL not elevated - Set-ScheduledTask would silently no-op. Re-run in an admin PowerShell."
  exit 1
}

Write-Host "== before =="
Get-ScheduledTask -TaskPath $path | ForEach-Object {
  '  {0,-24} WakeToRun={1,-5} StartWhenAvailable={2,-5} LogonType={3} Multiple={4}' -f `
    $_.TaskName, $_.Settings.WakeToRun, $_.Settings.StartWhenAvailable,
    $_.Principal.LogonType, $_.Settings.MultipleInstances
}

Write-Host "`n== change =="
foreach ($t in Get-ScheduledTask -TaskPath $path) {
  if (-not $t.Settings.WakeToRun) { Write-Host ('  {0}: already False' -f $t.TaskName); continue }
  $s = $t.Settings          # existing object - not a new one
  $s.WakeToRun = $false     # one field only
  Set-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Settings $s | Out-Null
  Write-Host ('  {0}: write requested' -f $t.TaskName)
}

Write-Host "`n== after - re-read the real value (success != applied) =="
$bad = @()
foreach ($t in Get-ScheduledTask -TaskPath $path) {
  $s = $t.Settings
  '  {0,-24} WakeToRun={1,-5} StartWhenAvailable={2,-5} LogonType={3} Multiple={4}' -f `
    $t.TaskName, $s.WakeToRun, $s.StartWhenAvailable, $t.Principal.LogonType, $s.MultipleInstances
  if ($s.WakeToRun) { $bad += "$($t.TaskName): WakeToRun is still True" }
  if (-not $s.StartWhenAvailable) { $bad += "$($t.TaskName): StartWhenAvailable was lost" }
  if ($t.Principal.LogonType -ne 'S4U') { $bad += "$($t.TaskName): LogonType is no longer S4U" }
}

if ($bad.Count) {
  $bad | ForEach-Object { Write-Host "  FAIL $_" }
  Write-Host ("STATUS: FAIL {0} item(s)" -f $bad.Count)
  exit 1
}
Write-Host "STATUS: OK  WakeToRun cleared on 4/4 - StartWhenAvailable and S4U preserved"
