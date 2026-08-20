#requires -Version 5.1
#
# JJ Company OS - job-scout (grade B, discovery and scoring only)
# Charter section 4 (scheduling protocol) compliance.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as
# the system ANSI codepage, which mangles non-ASCII text. The Korean agent prompt
# lives in scripts\prompts\job-scout.md and is read as explicit UTF-8.

$ErrorActionPreference = 'Continue'

$Task       = 'job-scout'
# Start stagger (2026-08-19). All four tasks are StartWhenAvailable, so after a
# sleep/reboot they all fire in the same second and race on "git pull" in this
# shared tree (see scripts\git-sync.ps1). Time triggers have no deterministic
# delay in Task Scheduler, so the offset lives here: drift 0 / vault 2 /
# scout 4 / job 6 minutes. Applied to every run, not only catch-up runs - the
# scheduled times are 30 min apart so the shift is harmless there.
$StartDelayMinutes = 6

$Hq         = 'C:\Users\ojaej\jj-company'
$Claude     = 'C:\Users\ojaej\.local\bin\claude.exe'
$PromptFile = Join-Path $Hq 'scripts\prompts\job-scout.md'

$Stamp    = Get-Date -Format 'yyyyMMdd'
$IsoDate  = Get-Date -Format 'yyyy-MM-dd'
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

Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ') ===')

# Stagger BEFORE the lock (2026-08-21). On 8/20 all three wrappers died during
# this sleep and left their locks behind, which would have blocked the next
# morning outright (the gate above exits 2 on a stale lock). The finally block
# cannot cover that case: no PowerShell cleanup runs when the process is killed
# from outside. Holding no lock while we only sleep removes the failure mode.
if ($StartDelayMinutes -gt 0) {
    Write-Log ('start stagger: sleeping ' + $StartDelayMinutes + ' min')
    Start-Sleep -Seconds ($StartDelayMinutes * 60)
    # First mark after the sleep. 8/20 could not be traced past the stagger line
    # because nothing was written until the git step - this line makes "did it
    # come back from the sleep at all" answerable from the log alone.
    Write-Log ('stagger complete: resuming after ' + $StartDelayMinutes + ' min')
}

# Re-check: another run may have taken the lock while this one slept.
if (Test-Path -LiteralPath $LockFile) {
    Write-Log ('lock file present after stagger: ' + $LockFile + ' -- aborting')
    Write-Log 'STATUS: FAIL lock-exists'
    exit 2
}

$lockTaken = $false
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    Write-Log ('lock acquired: ' + $LockFile)

    # Run provenance: which rulebook revision this run actually used.
    # 2026-08-15 diagnosis - the live skill used to be a symlink, so the answer
    # changed with whatever branch was checked out and nothing recorded it.
    $VerHelper = Join-Path $Hq 'scripts\skill-version.ps1'
    if (Test-Path -LiteralPath $VerHelper) {
        . $VerHelper
        foreach ($vl in (Get-SkillVersionLines)) { Write-Log $vl }
    } else {
        Write-Log ('skill version helper missing: ' + $VerHelper)
    }

    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

    # --- charter 4: sync the operations server to latest main before working ---
    Set-Location -LiteralPath $Hq
    Write-Log ('cwd: ' + (Get-Location).Path)
    # Retry (2026-08-19): see scripts\git-sync.ps1 header - a wake-up stampede
    # made three wrappers pull the same tree in the same second and two lost.
    $SyncHelper = Join-Path $Hq 'scripts\git-sync.ps1'
    if (-not (Test-Path -LiteralPath $SyncHelper)) {
        Write-Log ('git sync helper missing: ' + $SyncHelper)
        Write-Log 'STATUS: FAIL git-sync-helper-missing'
        exit 1
    }
    . $SyncHelper
    # Quote-safe prompt passing (2026-08-19): see scripts\native-arg.ps1 - PS 5.1
    # cut the -p prompt at its first inner double quote and dropped the rest.
    $ArgHelper = Join-Path $Hq 'scripts\native-arg.ps1'
    if (-not (Test-Path -LiteralPath $ArgHelper)) {
        Write-Log ('native arg helper missing: ' + $ArgHelper)
        Write-Log 'STATUS: FAIL arg-helper-missing'
        exit 1
    }
    . $ArgHelper
    $pull = Invoke-GitPullRetry -Log ${function:Write-Log}
    if (-not $pull.Ok) {
        Write-Log 'STATUS: FAIL git-sync'
        exit 1
    }

    # Same charter 4 step, second half (2026-08-15): the live rulebook is synced
    # here too. The live skill folder is a plain copy of origin/main now, so
    # nothing updates it unless we push it - a stale live folder is exactly the
    # silent failure this structure was built to remove.
    $Deploy = Join-Path $Hq 'scripts\deploy-skill.ps1'
    if (-not (Test-Path -LiteralPath $Deploy)) {
        Write-Log ('skill deploy script missing: ' + $Deploy)
        Write-Log 'STATUS: FAIL skill-sync'
        exit 1
    }
    Write-Log 'deploy-skill (live <- origin/main)'
    $depOut  = & powershell -NoProfile -ExecutionPolicy Bypass -File $Deploy 2>&1
    $depCode = $LASTEXITCODE
    foreach ($l in $depOut) { Write-Log ('  skill| ' + $l) }
    if ($depCode -ne 0) {
        Write-Log ('deploy-skill exit code ' + $depCode)
        Write-Log 'STATUS: FAIL skill-sync'
        exit 1
    }

    if (-not (Test-Path -LiteralPath $PromptFile)) {
        Write-Log ('prompt file missing: ' + $PromptFile)
        Write-Log 'STATUS: FAIL prompt-missing'
        exit 1
    }
    $prompt = (Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8).Replace('{{DATE}}', $IsoDate)

    # This job only reads files inside the operations server, so no --add-dir is
    # needed. Bash is not granted either - applied.md is read with the Read tool.
    $AllowedTools = @('WebSearch', 'WebFetch')

    Write-Log ('claude -p (job-scout) start, allowed-tools: ' + ($AllowedTools -join ' '))
    $out = & $Claude -p (ConvertTo-NativeArg $prompt) --permission-mode acceptEdits `
        --allowed-tools @AllowedTools 2>&1
    $claudeCode = $LASTEXITCODE
    foreach ($l in $out) { Write-Log ('  cc| ' + $l) }
    Write-Log ('claude exit code ' + $claudeCode)

    if ($claudeCode -ne 0) {
        Write-Log ('STATUS: FAIL claude-exit-' + $claudeCode)
        exit 1
    }

    $Report = Join-Path $Hq ('reports\' + $IsoDate + '_' + $Task + '.md')
    if (-not (Test-Path -LiteralPath $Report)) {
        Write-Log ('report missing: ' + $Report)
        Write-Log 'STATUS: FAIL report-missing'
        exit 1
    }

    # The report file is the artifact of record (charter section 5), so the verdict
    # is read from its trailing STATUS line. Agent stdout is a conversational summary
    # and does not reliably carry the STATUS line.
    $reportStatus = (Select-String -LiteralPath $Report -Pattern '^STATUS:' | Select-Object -Last 1).Line
    if ($null -eq $reportStatus) {
        Write-Log ('no STATUS line in report: ' + $Report)
        Write-Log 'STATUS: FAIL report-status-missing'
        exit 1
    }
    Write-Log ('report status line: ' + $reportStatus)
    if ($reportStatus -notmatch 'STATUS:\s*OK') {
        Write-Log 'STATUS: FAIL agent-status-not-ok'
        exit 1
    }

    Write-Log ('report: ' + $Report)

    # Cross-verification is an add-on: a codex failure must never fail the scout
    # itself. cross-verify.ps1 writes its own "not performed" note into the report.
    $verify = Join-Path $Hq 'scripts\cross-verify.ps1'
    if (Test-Path -LiteralPath $verify) {
        Write-Log 'cross-verify start'
        & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $verify -Report $Report | Out-Null
        Write-Log ('cross-verify exit code ' + $LASTEXITCODE + ' (does not affect this run)')
    } else {
        Write-Log ('cross-verify script missing: ' + $verify)
    }

    Write-Log 'STATUS: OK'
    exit 0
}
finally {
    if ($lockTaken -and (Test-Path -LiteralPath $LockFile)) {
        Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
        Write-Log 'lock released'
    }
}
