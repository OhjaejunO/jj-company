#requires -Version 5.1
#
# JJ Company OS - tomangchi-scout (grade B, proposal only)
# Charter section 4 (scheduling protocol) compliance.
# Automation body for TOMANGCHI LAB SKILL.md section 5.5 morning scan, steps 1-3.1.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as
# the system ANSI codepage, which mangles non-ASCII text. The Korean agent prompt
# lives in scripts\prompts\tomangchi-scout.md and is read as explicit UTF-8.
# The scan-log folder name is Korean, so it is built from code points below.

$ErrorActionPreference = 'Continue'

$Task       = 'tomangchi-scout'
# Start stagger (2026-08-19). All four tasks are StartWhenAvailable, so after a
# sleep/reboot they all fire in the same second and race on "git pull" in this
# shared tree (see scripts\git-sync.ps1). Time triggers have no deterministic
# delay in Task Scheduler, so the offset lives here: drift 0 / vault 2 /
# scout 4 / job 6 minutes. Applied to every run, not only catch-up runs - the
# scheduled times are 30 min apart so the shift is harmless there.
$StartDelayMinutes = 4

$Hq         = 'C:\Users\ojaej\jj-company'
$Claude     = 'C:\Users\ojaej\.local\bin\claude.exe'
$PromptFile = Join-Path $Hq 'scripts\prompts\tomangchi-scout.md'

# Read/write scopes granted per-run via --add-dir (least privilege).
# Do NOT move these into settings.json additionalDirectories - that would grant
# every session access. Charter section 2 allows writes ONLY under the scan-log folder.
$SkillDir   = 'C:\Users\ojaej\.claude\skills\tomangchi'
$ContentOps = 'C:\Users\ojaej\orca\content-ops'
$Workshop   = 'C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop'

# U+C2A4 U+CE94 U+B85C U+ADF8 - Korean folder name meaning "scan log".
# Written as code points to keep this file ASCII-only (see header).
$ScanLogFolder = -join ([char]0xC2A4, [char]0xCE94, [char]0xB85C, [char]0xADF8)
$ScanLogDir    = Join-Path $Workshop $ScanLogFolder

$Stamp    = Get-Date -Format 'yyyyMMdd'
$IsoDate  = Get-Date -Format 'yyyy-MM-dd'
$Weekday  = (Get-Date).DayOfWeek.ToString()
$LogDir   = Join-Path $Hq 'logs\scheduled'
$LogFile  = Join-Path $LogDir ($Task + '_' + $Stamp + '.log')
$LockFile = Join-Path $Hq ('logs\' + $Task + '.lock')

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Shared writer (2026-08-20): Add-Content dies with an IOException when any
# reader holds the log open (a `tail -f` did exactly that and every line after
# the stagger was dropped silently). scripts\logging.ps1 opens with
# FileShare.ReadWrite, retries, and spills to <log>.overflow + stderr rather
# than losing the line. Fallback stays inline so logging works even if the
# helper is missing.
$LogHelper = Join-Path $Hq 'scripts\logging.ps1'
if (Test-Path -LiteralPath $LogHelper) { . $LogHelper }

function Write-Log {
    param([string]$Message)
    if (Get-Command Write-LogLine -ErrorAction SilentlyContinue) {
        [void](Write-LogLine -Path $LogFile -Message $Message)
        return
    }
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

# --- lock gate: charter 4 requires an immediate exit when the lock exists ---
if (Test-Path -LiteralPath $LockFile) {
    Write-Log ('lock file present: ' + $LockFile + ' -- aborting, another run owns it')
    Write-Log 'STATUS: FAIL lock-exists'
    exit 2
}

Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ', ' + $Weekday + ') ===')

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
    if (-not (Test-Path -LiteralPath $ScanLogDir)) {
        Write-Log ('scan log dir missing: ' + $ScanLogDir)
        Write-Log 'STATUS: FAIL scanlog-dir-missing'
        exit 1
    }

    # scan_check --from-log reads this to locate the scan log folder.
    $env:SCAN_LOG_DIR = $ScanLogDir
    Write-Log ('SCAN_LOG_DIR=' + $ScanLogDir)

    # Record the pre-run state so the append policy can be verified afterwards.
    $ScanLog = Join-Path $ScanLogDir ($IsoDate + '.md')
    $existed = Test-Path -LiteralPath $ScanLog
    $sizeBefore = 0
    if ($existed) { $sizeBefore = (Get-Item -LiteralPath $ScanLog).Length }
    Write-Log ('scan log before: exists=' + $existed + ' bytes=' + $sizeBefore)

    # --- source-list watch (2026-08-19): collect BEFORE the agent runs ---
    # Step 1-1 of the agent (reels creator source list) needs yt-dlp; the
    # scheduled allowlist never had it, so the step was silently skipped
    # (2026-08-19 report had no source-list line at all, codex finding #2, and a
    # 2026-08-17 upload on @spoop-v7v went unobserved). Same wrapper-first
    # pattern as ops-auditor: the wrapper produces the data, the agent reads it.
    # Non-fatal: a scan without the source file is still worth running, but the
    # file then says UNAVAILABLE so the agent writes 'unverified', not 'none'.
    $ScoutDataDir = Join-Path $Hq 'logs\scout-data'
    New-Item -ItemType Directory -Force -Path $ScoutDataDir | Out-Null
    $SourceData = Join-Path $ScoutDataDir ('sources_' + $IsoDate + '.txt')
    $SourcePy   = Join-Path $Hq 'scripts\source_watch.py'
    $env:PYTHONIOENCODING = 'utf-8'
    Write-Log ('source_watch.py -> ' + $SourceData)
    if (-not (Test-Path -LiteralPath $SourcePy)) {
        Write-Log ('source watch script missing: ' + $SourcePy + ' - recording as unavailable')
        Set-Content -LiteralPath $SourceData -Value 'UNAVAILABLE script-missing' -Encoding UTF8
    } else {
        $srcOut  = & py $SourcePy 2>&1
        $srcCode = $LASTEXITCODE
        if ($srcCode -ne 0) {
            Write-Log ('source_watch.py exit code ' + $srcCode + ' - recording as unavailable')
            foreach ($l in $srcOut) { Write-Log ('  src| ' + $l) }
            Set-Content -LiteralPath $SourceData -Value ('UNAVAILABLE exit ' + $srcCode) -Encoding UTF8
        } else {
            Set-Content -LiteralPath $SourceData -Value $srcOut -Encoding UTF8
            # Prove the file carries per-source verdicts, not just a header (charter 0).
            $okCount = @(Select-String -LiteralPath $SourceData -Pattern '^STATUS=OK').Count
            $allCount = @(Select-String -LiteralPath $SourceData -Pattern '^STATUS=').Count
            Write-Log ('source data ok (' + (Get-Item -LiteralPath $SourceData).Length + ' bytes, ' + $allCount + ' sources, ' + $okCount + ' probed OK)')
            if ($allCount -eq 0) {
                Write-Log 'source data has no STATUS lines - recording as unavailable'
                Set-Content -LiteralPath $SourceData -Value 'UNAVAILABLE no-status-lines' -Encoding UTF8
            }
        }
    }

    $prompt = (Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8).Replace('{{DATE}}', $IsoDate).Replace('{{WEEKDAY}}', $Weekday)
    $prompt = $prompt.Replace('{{SOURCE_DATA}}', $SourceData)

    # Headless sessions cannot answer permission prompts, so the tools this job
    # actually needs are granted explicitly and narrowly. Deny rules in
    # settings.json still win over allow, so vault / tomangchi write blocks hold.
    $AllowedTools = @(
        'WebSearch',
        'WebFetch',
        'Bash(*python.exe *manage.py*)',
        # cwd does not survive between Bash calls, so a split "cd" then "python"
        # runs Django from the operations server and drops an empty db.sqlite3
        # there. content-ops commands must stay chained on one line.
        'Bash(cd * && *python.exe *manage.py*)',
        'Bash(dir*)',
        'Bash(type*)',
        'Bash(cd*)'
    )

    Write-Log ('claude -p (content-scout) start, allowed-tools: ' + ($AllowedTools -join ' '))
    $out = & $Claude -p (ConvertTo-NativeArg $prompt) --permission-mode acceptEdits `
        --allowed-tools @AllowedTools `
        --add-dir $SkillDir --add-dir $ContentOps --add-dir $ScanLogDir 2>&1
    $claudeCode = $LASTEXITCODE
    foreach ($l in $out) { Write-Log ('  cc| ' + $l) }
    Write-Log ('claude exit code ' + $claudeCode)

    if ($claudeCode -ne 0) {
        Write-Log ('STATUS: FAIL claude-exit-' + $claudeCode)
        exit 1
    }

    # --- artifact 1: report ---
    $Report = Join-Path $Hq ('reports\' + $IsoDate + '_' + $Task + '.md')
    if (-not (Test-Path -LiteralPath $Report)) {
        Write-Log ('report missing: ' + $Report)
        Write-Log 'STATUS: FAIL report-missing'
        exit 1
    }

    # --- artifact 2: scan log (created, or appended to without shrinking) ---
    if (-not (Test-Path -LiteralPath $ScanLog)) {
        Write-Log ('scan log missing: ' + $ScanLog)
        Write-Log 'STATUS: FAIL scanlog-missing'
        exit 1
    }
    $sizeAfter = (Get-Item -LiteralPath $ScanLog).Length
    Write-Log ('scan log after: bytes=' + $sizeAfter)
    if ($sizeAfter -le $sizeBefore) {
        Write-Log ('scan log did not grow (before=' + $sizeBefore + ' after=' + $sizeAfter + ')')
        Write-Log 'STATUS: FAIL scanlog-not-appended'
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
    Write-Log ('scan log: ' + $ScanLog)

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
