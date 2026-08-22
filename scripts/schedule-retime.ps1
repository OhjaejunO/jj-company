<#
  Move the two audit tasks to 12:30. (2026-08-22, JJ decision)

  ASCII-only on purpose - PowerShell 5.1 mangles BOM-less non-ASCII .ps1 files.

  MUST RUN ELEVATED. Same reason as waketorun-off.ps1: without admin,
  Set-ScheduledTask returns success and changes nothing. This script re-reads
  the trigger afterwards and exits FAIL if the time did not move.

  WHAT MOVES AND WHY
    skill-drift-audit     07:00 -> 12:30   deterministic audit, timing irrelevant
    morning-vault-health  07:30 -> 12:30   vault audit, timing irrelevant
    tomangchi-scout       08:00  (unchanged)  "morning scan" - freshness IS the point
    job-scout             08:30  (unchanged)

    Measured actual first-run times (7 days): 09:48 09:03 11:18 11:46 12:04
    11:42 12:14 - latest 12:14, so 12:30 clears all seven with margin.

    The scouts stay early ON PURPOSE. Their scheduled time is already in the
    past when the PC boots, so StartWhenAvailable fires them immediately at
    boot - the earliest possible moment. Moving them to 12:30 would make them
    WAIT on days the PC boots earlier, which is a direct loss for a scan whose
    value is timeliness (SKILL 5.5: "morning scan = same starting line as the
    domestic summary accounts").

  The 0/2/4/6 minute stagger lives in the wrapper scripts and is unaffected.
  Note the two audits now share 12:30, so their stagger (0 and 2 min) is what
  keeps them off each other's git pull.
#>
$ErrorActionPreference = 'Stop'

$WANT = @{
  'skill-drift-audit'    = '12:30'
  'morning-vault-health' = '12:30'
}
$KEEP = @('tomangchi-scout', 'job-scout')

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$elev = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
          [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $elev) {
  Write-Host "STATUS: FAIL not elevated - Set-ScheduledTask would silently no-op. Re-run in an admin PowerShell."
  exit 1
}

function Show-Triggers($label) {
  Write-Host "== $label =="
  foreach ($t in Get-ScheduledTask -TaskPath '\JJ\') {
    foreach ($tr in $t.Triggers) {
      $b = if ($tr.StartBoundary) { ([datetime]$tr.StartBoundary).ToString('HH:mm') } else { '(none)' }
      '  {0,-24} {1}  [{2}]' -f $t.TaskName, $b, $tr.CimClass.CimClassName
    }
  }
}

Show-Triggers 'before'

Write-Host "`n== change =="
foreach ($name in $WANT.Keys) {
  $t = Get-ScheduledTask -TaskPath '\JJ\' -TaskName $name
  $trs = @($t.Triggers)
  if ($trs.Count -ne 1) {
    Write-Host ('  {0}: SKIP - expected 1 trigger, found {1}. Fix by hand.' -f $name, $trs.Count)
    continue
  }
  $tr = $trs[0]
  # Keep the existing StartBoundary date and every other trigger field.
  # Only the time-of-day moves.
  $old = [datetime]$tr.StartBoundary
  $hm = $WANT[$name].Split(':')
  $new = Get-Date -Year $old.Year -Month $old.Month -Day $old.Day `
                  -Hour ([int]$hm[0]) -Minute ([int]$hm[1]) -Second 0 -Millisecond 0
  $tr.StartBoundary = $new.ToString('yyyy-MM-ddTHH:mm:ss')
  Set-ScheduledTask -TaskName $name -TaskPath '\JJ\' -Trigger $tr | Out-Null
  Write-Host ('  {0}: {1} -> {2} requested' -f $name, $old.ToString('HH:mm'), $WANT[$name])
}

Write-Host ""
Show-Triggers 'after - re-read (success != applied)'

$bad = @()
foreach ($t in Get-ScheduledTask -TaskPath '\JJ\') {
  $tr = @($t.Triggers)[0]
  $hm = if ($tr.StartBoundary) { ([datetime]$tr.StartBoundary).ToString('HH:mm') } else { '' }
  if ($WANT.ContainsKey($t.TaskName) -and $hm -ne $WANT[$t.TaskName]) {
    $bad += "$($t.TaskName): wanted $($WANT[$t.TaskName]) but is $hm"
  }
  if (-not $t.Settings.StartWhenAvailable) { $bad += "$($t.TaskName): StartWhenAvailable was lost" }
  if ($t.Principal.LogonType -ne 'S4U')    { $bad += "$($t.TaskName): LogonType is no longer S4U" }
  if ($t.Settings.WakeToRun)               { $bad += "$($t.TaskName): WakeToRun came back True" }
}
foreach ($k in $KEEP) {
  $t = Get-ScheduledTask -TaskPath '\JJ\' -TaskName $k
  $hm = ([datetime](@($t.Triggers)[0].StartBoundary)).ToString('HH:mm')
  Write-Host ('  keep {0,-22} {1}' -f $k, $hm)
}

if ($bad.Count) {
  $bad | ForEach-Object { Write-Host "  FAIL $_" }
  Write-Host ("STATUS: FAIL {0} item(s)" -f $bad.Count)
  exit 1
}
Write-Host "STATUS: OK  audits moved to 12:30 - scouts unchanged, StartWhenAvailable/S4U/WakeToRun intact"
