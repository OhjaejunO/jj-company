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
    Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ', ' + $Weekday + ') ===')

    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

    # --- charter 4: sync the operations server to latest main before working ---
    Set-Location -LiteralPath $Hq
    Write-Log ('cwd: ' + (Get-Location).Path)
    Write-Log 'git pull origin main'
    $pullOut  = & git pull origin main 2>&1
    $pullCode = $LASTEXITCODE
    foreach ($l in $pullOut) { Write-Log ('  git| ' + $l) }
    if ($pullCode -ne 0) {
        Write-Log ('git pull exit code ' + $pullCode)
        Write-Log 'STATUS: FAIL git-sync'
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

    $prompt = (Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8).Replace('{{DATE}}', $IsoDate).Replace('{{WEEKDAY}}', $Weekday)

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
    $out = & $Claude -p $prompt --permission-mode acceptEdits `
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
    Write-Log 'STATUS: OK'
    exit 0
}
finally {
    if ($lockTaken -and (Test-Path -LiteralPath $LockFile)) {
        Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
        Write-Log 'lock released'
    }
}
