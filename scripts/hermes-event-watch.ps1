#requires -Version 5.1
#
# JJ Company OS - hermes-event-watch (grade A, read-only watch; alerts only)
# Charter section 4 (scheduling protocol) compliance. Hermes worker #2 (event
# trigger watch) - spec: docs\workers\hermes-02-event-trigger-watch.md
#
# ASCII-only on purpose (see tomangchi-scout.ps1 header).
#
# TRIAL ENDED 2026-09-13 (JJ call) - NO MODEL IS CALLED ANY MORE
#   The Hermes judgement layer ran 14 times over two weeks and its own success
#   metric was never measured once (every report left "JJ fills in ___" empty).
#   What did produce value is the deterministic watcher: 120/120 polls, no model,
#   no cost. So the model call is gone and event_watch_report.py runs with
#   --no-judge. Evidence: reports\2026-09-13_hermes-trial.md.
#   The task name still says "hermes" because renaming a scheduled task is a
#   human seat (docs\schedule-task-registration.md) - the name is historical.
#   To reopen a trial, restore the `hermes -p sagun -z` call and drop --no-judge;
#   event_watch.py still writes the prompt file (EVENT_PROMPT=) for that.
#
# WHY A WRAPPER AT ALL (decision 2026-08-26, still true)
#   A job outside this wrapper has no .started stamp, lock file, git-sync or
#   STATUS line, and scripts\run_audit.py detects "started but never finished"
#   runs from exactly those artifacts - charter section 0 silent-failure shape.
#
# PIPELINE
#   1. git-sync (charter 4)            3. py scripts\event_watch_report.py --no-judge
#   2. py scripts\event_watch.py          -> alerts + report + STATUS line
#      (deterministic fetch/diff)

param(
    # Operations server by default. Override only for a trial from a worktree
    # (logs/ and reports/ are gitignored there too).
    [string]$Hq = 'C:\Users\ojaej\jj-company',
    # Skip git-sync for a worktree trial (the ops server always syncs).
    [switch]$NoSync
)

$ErrorActionPreference = 'Continue'

$Task     = 'hermes-event-watch'
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
        # 2026-09-13: the dot-source only DEFINES Invoke-GitPullRetry. This
        # wrapper never called it, so charter section 4 sync had been a no-op
        # since 2026-08-26 - silently (no log line either way). The other seven
        # wrappers all call it; see the USAGE block in git-sync.ps1.
        $r = Invoke-GitPullRetry -Log ${function:Write-Log}
        if (-not $r.Ok) { Write-Log 'STATUS: FAIL git-sync'; exit 1 }
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
    # --- 3. report + alerts: done in Python (Korean text must not live in this
    #      ASCII-only .ps1 - PS 5.1 reads BOM-less UTF-8 as ANSI).
    $rp = & $Py (Join-Path $Hq 'scripts\event_watch_report.py') --date $IsoDate --state $StateDir --report $Report --alerts $Alerts --no-judge 2>&1
    $rpCode = $LASTEXITCODE
    foreach ($l in $rp) { Write-Log ('  rp| ' + $l) }
    Write-Log ('report: ' + $Report)
    if ($rpCode -ne 0) {
        Write-Log 'STATUS: FAIL report (see report file)'
        exit 1
    }
    Write-Log ('alerts: ' + $Alerts)
    # The Python side decides the verdict string. Re-deriving it here would give
    # two verdicts that can disagree (charter s0). Python prints ASCII on purpose
    # - PS 5.1 decodes native output with the console codepage.
    $statusLine = ($rp | ForEach-Object { [string]$_ } | Where-Object { $_ -like 'STATUS:*' } | Select-Object -Last 1)
    if ($statusLine) { Write-Log $statusLine } else { Write-Log 'STATUS: OK' }
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
