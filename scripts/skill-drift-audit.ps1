#requires -Version 5.1
#
# JJ Company OS - skill-drift-audit (grade A, read-only)
# Charter section 4 (scheduling protocol) compliance.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as
# the system ANSI codepage, which mangles non-ASCII text. The audit logic and
# its Korean report live in scripts\skill_drift_audit.py, read as explicit UTF-8.
#
# This audit is deterministic - it compares two folders and runs a self test.
# No agent is involved on purpose: charter section 0 forbids guessing, and a
# file comparison has an exact answer. Cheaper, repeatable, no model drift.

$ErrorActionPreference = 'Continue'

$Task    = 'skill-drift-audit'
$Hq      = 'C:\Users\ojaej\jj-company'
$Script  = Join-Path $Hq 'scripts\skill_drift_audit.py'

$Stamp    = Get-Date -Format 'yyyyMMdd'
$LogDir   = Join-Path $Hq 'logs\scheduled'
$LogFile  = Join-Path $LogDir ($Task + '_' + $Stamp + '.log')
$LockFile = Join-Path $Hq ('logs\' + $Task + '.lock')

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log {
    param([string]$Message)
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

# --- lock gate: charter 4 requires an immediate exit when the lock exists ---
if (Test-Path -LiteralPath $LockFile) {
    Write-Log ('lock file present: ' + $LockFile + ' -- aborting, another run owns it')
    Write-Log 'STATUS: FAIL lock-exists'
    exit 2
}

$lockTaken = $false
$prevEnc = [Console]::OutputEncoding
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    Write-Log ('=== ' + $Task + ' start ===')

    # The audit prints Korean. PowerShell 5.1 decodes native command output with
    # the console codepage (cp949 here), so the log came out as mush on the first
    # real run. The log IS the evidence trail - if it is mangled we cannot diagnose.
    # Charter section 6 flags this exact class of bug.
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    $env:PYTHONIOENCODING = 'utf-8'

    if (-not (Test-Path -LiteralPath $Script)) {
        Write-Log ('audit script missing: ' + $Script)
        Write-Log 'STATUS: FAIL script-missing'
        exit 2
    }

    # Grade A: read-only. Still no "git pull" - pulling would move a shared
    # working tree, and this job must not change what other sessions are holding.
    #
    # The audit itself does run "git fetch" (remote-tracking refs only, working
    # tree and HEAD untouched) because it compares the live folder against
    # origin/main - that is what deploy-skill.ps1 ships, per charter section 4.
    # It used to read the clone's working tree instead, which made a merely
    # out-of-date clone look like drift: on 2026-08-15 it printed a red
    # "cardcheck.py differs" minutes after that file was merged. A red alarm with
    # the wrong cause sends the reader to fix the wrong thing.
    #
    # Clone state (branch, behind, dirty) is still reported - as yellow, under
    # its own name, so it is never confused with drift.
    $out = & py $Script 2>&1
    $code = $LASTEXITCODE
    foreach ($line in $out) { Write-Log ([string]$line) }

    if ($code -eq 0) {
        Write-Log 'STATUS: OK'
    } else {
        Write-Log ('STATUS: FAIL drift-detected (exit ' + $code + ')')
    }
    exit $code
}
finally {
    [Console]::OutputEncoding = $prevEnc
    if ($lockTaken) { Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue }
    Write-Log ('=== ' + $Task + ' end ===')
}
