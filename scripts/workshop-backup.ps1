#requires -Version 5.1
#
# JJ Company OS - workshop-backup (grade B; workshop is READ-ONLY here)
# Charter section 4 (scheduling protocol).
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as
# the system ANSI codepage, which mangles non-ASCII text. All Korean output is
# produced by scripts\workshop_backup.py and read back as explicit UTF-8.
#
# WHAT THIS IS
#   Infra backlog item 21, option 3 - the stop-gap while option 1 (a private
#   repo for workshop sources) is still awaiting a decision. It zips only what
#   cannot be rebuilt (text sources + _official originals + the scan log and the
#   publication ledger) and copies that to Google Drive.
#
# WHY NO SKILL SYNC (deliberate deviation from charter section 4)
#   Charter section 4 asks every scheduled job to sync the ops server AND deploy
#   the skill before running. This job does the git pull - it must run the
#   current script - but deliberately SKIPS deploy-skill.ps1, because it never
#   loads the skill. Wiring the backup to skill deployment would mean an
#   unrelated credential expiry disables the safety net: on 2026-08-27 an expired
#   gh token killed three jobs at exactly that step. A backup that dies when
#   something unrelated expires is not a backup. skill-drift-audit.ps1 sets the
#   precedent for a written-down deviation of this shape.
#   >> Flagged for JJ. If the answer is "no deviations", add the deploy call.

$ErrorActionPreference = 'Continue'

$Task   = 'workshop-backup'
$Hq     = 'C:\Users\ojaej\jj-company'
$Script = Join-Path $Hq 'scripts\workshop_backup.py'
$Reason = if ($args.Count -ge 1) { [string]$args[0] } else { 'weekly' }

$Stamp    = Get-Date -Format 'yyyyMMdd'
$LogDir   = Join-Path $Hq 'logs\scheduled'
$LogFile  = Join-Path $LogDir ($Task + '_' + $Stamp + '.log')
$LockFile = Join-Path $Hq ('logs\' + $Task + '.lock')

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogHelper = Join-Path $Hq 'scripts\logging.ps1'
if (Test-Path -LiteralPath $LogHelper) { . $LogHelper }

function Write-Log {
    param([string]$Message)
    if (Get-Command Write-LogLine -ErrorAction SilentlyContinue) {
        [void](Write-LogLine -Path $LogFile -Message $Message)
        return
    }
    Add-Content -LiteralPath $LogFile -Encoding UTF8 `
        -Value ('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message)
}

if (Test-Path -LiteralPath $LockFile) {
    Write-Log ('lock file present: ' + $LockFile + ' -- aborting')
    Write-Log 'STATUS: FAIL lock-exists'
    exit 2
}

$lockTaken = $false
$prevEnc = [Console]::OutputEncoding
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ') ===')
    Write-Log ('reason: ' + $Reason)

    # Stagger, same reason as the other wrappers: after a sleep or reboot every
    # StartWhenAvailable job fires in the same second and the git pulls race.
    # This one is last in line - it is a safety net, not a deadline.
    Start-Sleep -Seconds 480

    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    $env:PYTHONIOENCODING = 'utf-8'

    $GitSync = Join-Path $Hq 'scripts\git-sync.ps1'
    if (Test-Path -LiteralPath $GitSync) {
        $sync = & powershell -NoProfile -ExecutionPolicy Bypass -File $GitSync -Repo $Hq 2>&1
        foreach ($l in $sync) { Write-Log ('  git| ' + $l) }
        if ($LASTEXITCODE -ne 0) {
            Write-Log 'STATUS: FAIL git-sync'
            exit 1
        }
    } else {
        Write-Log 'git-sync.ps1 missing - pulling inline'
        $pull = & git -C $Hq pull origin main 2>&1
        foreach ($l in $pull) { Write-Log ('  git| ' + $l) }
        if ($LASTEXITCODE -ne 0) {
            Write-Log 'STATUS: FAIL git-sync'
            exit 1
        }
    }

    # Charter section 0: a path that fails without a sound is the dangerous one.
    # A missing script must be loud, not a silent no-op that still logs OK.
    if (-not (Test-Path -LiteralPath $Script)) {
        Write-Log ('backup script missing: ' + $Script)
        Write-Log 'STATUS: FAIL script-missing'
        exit 2
    }

    $out = & py $Script '--reason' $Reason 2>&1
    $code = $LASTEXITCODE
    foreach ($l in $out) { Write-Log ('  bk| ' + $l) }

    $statusLine = ($out | Select-String -Pattern '^STATUS:' | Select-Object -Last 1)
    if ($null -eq $statusLine) {
        Write-Log 'STATUS: FAIL worker-status-missing'
        exit 1
    }
    Write-Log ('backup status: ' + $statusLine.Line)
    if ($code -ne 0) {
        Write-Log ('STATUS: FAIL backup-exit-' + $code)
        exit 1
    }
    Write-Log 'STATUS: OK'
    exit 0
}
finally {
    [Console]::OutputEncoding = $prevEnc
    if ($lockTaken) { Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue }
    Write-Log ('=== ' + $Task + ' end ===')
}
