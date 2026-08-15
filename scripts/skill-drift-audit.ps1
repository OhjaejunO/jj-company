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
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    Write-Log ('=== ' + $Task + ' start ===')

    if (-not (Test-Path -LiteralPath $Script)) {
        Write-Log ('audit script missing: ' + $Script)
        Write-Log 'STATUS: FAIL script-missing'
        exit 2
    }

    # Grade A: read-only. No git pull here on purpose - this audit reads the
    # working trees as they are. Pulling would hide drift that exists right now,
    # which is the only thing this job is here to find.
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
    if ($lockTaken) { Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue }
    Write-Log ('=== ' + $Task + ' end ===')
}
