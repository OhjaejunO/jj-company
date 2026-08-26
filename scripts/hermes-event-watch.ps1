#requires -Version 5.1
#
# JJ Company OS - hermes-event-watch (grade A, read-only watch; alerts only)
# Charter section 4 (scheduling protocol) compliance. Hermes worker #2 (event
# trigger watch) - spec: docs\workers\hermes-02-event-trigger-watch.md
#
# ASCII-only on purpose (see tomangchi-scout.ps1 header).
#
# WHY THIS WRAPPER AND NOT HERMES CRON (decision 2026-08-26)
#   Hermes has its own scheduler (`hermes cron`), but it only fires while the
#   Hermes gateway service runs, and it knows nothing about our .started stamp,
#   lock file, git-sync or STATUS line. scripts\run_audit.py detects "started
#   but never finished" runs from exactly those artifacts. A job that lives
#   outside this wrapper is invisible to that detector - the charter section 0
#   silent-failure shape. So the job is registered as \JJ\hermes-event-watch
#   and this wrapper calls `hermes -p sagun -z` as a subprocess, the same way
#   the other wrappers call `claude -p`.
#
# PIPELINE
#   1. git-sync (charter 4)            4. hermes -p sagun -z <prompt> --usage-file
#   2. py scripts\event_watch.py       5. pin check: usage.model must start with $Pin
#      (deterministic fetch/diff)          -> otherwise "not performed", STATUS: FAIL provider
#   3. build prompt (public info only) 6. write alerts + report, STATUS line

param(
    # Operations server by default. Override only for a trial from a worktree
    # (logs/ and reports/ are gitignored there too).
    [string]$Hq = 'C:\Users\ojaej\jj-company',
    # Skip git-sync for a worktree trial (the ops server always syncs).
    [switch]$NoSync
)

$ErrorActionPreference = 'Continue'

$Task     = 'hermes-event-watch'
$Hermes   = Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.exe'
$Profile  = 'sagun'
$Pin      = 'nemotron-3.5-lightning-free'
$Py       = 'py'
$StartDelayMinutes = 0      # 07:40 slot - no other JJ task starts in that minute

$Stamp    = Get-Date -Format 'yyyyMMdd'
$IsoDate  = Get-Date -Format 'yyyy-MM-dd'
$LogDir   = Join-Path $Hq 'logs\scheduled'
$LogFile  = Join-Path $LogDir ($Task + '_' + $Stamp + '.log')
$LockFile = Join-Path $Hq ('logs\' + $Task + '.lock')
$StateDir = Join-Path $Hq 'logs\event-watch'
$Report   = Join-Path $Hq ('reports\' + $IsoDate + '_event-watch.md')
$Alerts   = Join-Path $StateDir ('alerts_' + $IsoDate + '.md')
$Usage    = Join-Path $StateDir ('usage_' + $IsoDate + '.json')

New-Item -ItemType Directory -Force -Path $LogDir, $StateDir | Out-Null

$LogHelper = Join-Path $Hq 'scripts\logging.ps1'
if (Test-Path -LiteralPath $LogHelper) {
    . $LogHelper
    function Write-Log { param([string]$Message) Write-LogLine -Path $LogFile -Message $Message }
} else {
    function Write-Log { param([string]$Message) Add-Content -LiteralPath $LogFile -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $Message) }
}

Write-Log ('=== start ' + $Task + ' (pid ' + $PID + ')')

# started stamp - read by scripts\run_audit.py (charter 4, 2026-08-25)
$StartedFile = Join-Path $Hq ('logs\' + $Task + '.started')
Set-Content -LiteralPath $StartedFile -Encoding UTF8 -Value ('pid=' + $PID + ' started=' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Log ('started stamp: ' + $StartedFile)

if ($StartDelayMinutes -gt 0) {
    Write-Log ('start stagger: sleeping ' + $StartDelayMinutes + ' min')
    Start-Sleep -Seconds ($StartDelayMinutes * 60)
    Write-Log 'stagger complete'
}

if (Test-Path -LiteralPath $LockFile) {
    Write-Log ('lock file present: ' + $LockFile + ' -- aborting')
    Write-Log 'STATUS: FAIL lock-exists'
    Remove-Item -LiteralPath $StartedFile -Force -ErrorAction SilentlyContinue
    exit 2
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding $false))
}

$lockTaken = $false
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    Write-Log ('lock acquired: ' + $LockFile)
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

    Set-Location -LiteralPath $Hq
    if ($NoSync) {
        Write-Log 'git-sync skipped (-NoSync, worktree trial)'
    } else {
        $SyncHelper = Join-Path $Hq 'scripts\git-sync.ps1'
        if (-not (Test-Path -LiteralPath $SyncHelper)) {
            Write-Log 'STATUS: FAIL git-sync-helper-missing'
            exit 1
        }
        . $SyncHelper
    }

    if (-not (Test-Path -LiteralPath $Hermes)) {
        Write-Log ('hermes missing: ' + $Hermes)
        Write-Log 'STATUS: FAIL hermes-missing'
        exit 1
    }

    # --- 2. deterministic watch ------------------------------------------------
    $env:PYTHONIOENCODING = 'utf-8'
    $ew = & $Py (Join-Path $Hq 'scripts\event_watch.py') --state $StateDir --date $IsoDate 2>&1
    $ewCode = $LASTEXITCODE
    foreach ($l in $ew) { Write-Log ('  ew| ' + $l) }
    if ($ewCode -ne 0) {
        Write-Log ('STATUS: FAIL event-watch-exit-' + $ewCode)
        exit 1
    }
    $promptLine = ($ew | Where-Object { $_ -like 'EVENT_PROMPT=*' } | Select-Object -Last 1)
    if (-not $promptLine) {
        Write-Log 'STATUS: FAIL event-watch-no-prompt'
        exit 1
    }
    $PromptFile = $promptLine.Substring(13)
    $prompt = [IO.File]::ReadAllText($PromptFile, [System.Text.Encoding]::UTF8)

    # --- 4. hermes (subprocess, one-shot) ----------------------------------------
    $ArgHelper = Join-Path $Hq 'scripts\native-arg.ps1'
    if (Test-Path -LiteralPath $ArgHelper) { . $ArgHelper } else { function ConvertTo-NativeArg([string]$s) { return $s } }
    if (Test-Path -LiteralPath $Usage) { Remove-Item -LiteralPath $Usage -Force }
    Write-Log ('hermes -p ' + $Profile + ' -z start (prompt ' + $prompt.Length + ' chars)')
    $out = & $Hermes -p $Profile -z (ConvertTo-NativeArg $prompt) --usage-file $Usage 2>&1
    $hCode = $LASTEXITCODE
    foreach ($l in $out) { Write-Log ('  hm| ' + $l) }
    Write-Log ('hermes exit code ' + $hCode)

    # --- 5/6. pin check + report + alerts: done in Python (Korean text must not
    #      live in this ASCII-only .ps1 - PS 5.1 reads BOM-less UTF-8 as ANSI).
    $OutTxt = Join-Path $StateDir ($IsoDate + '.out.txt')
    Write-Utf8NoBom $OutTxt ((($out | ForEach-Object { [string]$_ }) -join "`n"))
    $rp = & $Py (Join-Path $Hq 'scripts\event_watch_report.py') --date $IsoDate --state $StateDir --out $OutTxt --usage $Usage --report $Report --alerts $Alerts --pin $Pin --profile $Profile --hermes-exit $hCode 2>&1
    $rpCode = $LASTEXITCODE
    foreach ($l in $rp) { Write-Log ('  rp| ' + $l) }
    Write-Log ('report: ' + $Report)
    if ($rpCode -ne 0) {
        Write-Log 'STATUS: FAIL provider (judgement not performed - see report)'
        exit 1
    }
    Write-Log ('alerts: ' + $Alerts)
    Write-Log 'STATUS: OK'
    exit 0
}
finally {
    if ($lockTaken -and (Test-Path -LiteralPath $LockFile)) {
        Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
        Write-Log 'lock released'
    }
    if (Test-Path -LiteralPath $StartedFile) {
        Remove-Item -LiteralPath $StartedFile -Force -ErrorAction SilentlyContinue
        Write-Log 'started stamp removed'
    }
}
