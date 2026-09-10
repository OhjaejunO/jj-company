#requires -Version 5.1
#
# JJ Company OS - Threads publish worker wrapper
# Spec: docs\workers\publish-threads.md   Charter section 0 (publishing) / section 4.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as the
# system ANSI codepage, which mangles Korean. Korean lives in the Python worker.
#
# WHAT THIS WRAPPER IS FOR
#   The worker itself is a deterministic script - it does not need an agent. What the
#   wrapper adds is the lock, the log the audit can find, the version gate (never
#   publish from stale code) and the post-publish backup.
#
#   2026-09-10: the permission probe that used to run here is GONE. It proved that
#   the approval folder was out of reach, and JJ retired the approval device, so the
#   probe had nothing left to measure. Qualification is now the gate itself, checked
#   inside the worker (sidecar body_sha256 + gate_failed). See the worker's docstring.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publish-threads.ps1 -Ep ep39
#   ... -Ep ep39 -Publish        <- actually posts. Without it the worker is a dry run.

param(
    [Parameter(Mandatory = $true)][string]$Ep,
    [switch]$Publish,
    # Test-only override of the operations server path. A run that uses it says so in
    # the log, the same way the Python worker labels --out-dir as a test detour.
    # Never pass this for a real publish.
    [string]$Hq = 'C:\Users\ojaej\jj-company'
)

$ErrorActionPreference = 'Continue'

$Task    = 'publish-threads'
$Stamp   = Get-Date -Format 'yyyyMMdd'
$LogDir  = Join-Path $Hq 'logs\scheduled'
# run_audit.py looks for exactly '<task>_<yyyyMMdd>.log'. The episode used to sit in
# the file name, which made every publish log invisible to the audit - the start line
# was written but nothing ever opened the file. The episode is in the start line
# instead, so nothing is lost and the audit can find the run.
$LogFile = Join-Path $LogDir ($Task + '_' + $Stamp + '.log')
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

# run_audit.py matches '=== <task> start' with the task name immediately followed by
# ' start'. The episode used to sit in between, so the audit counted zero starts even
# when it could open the file - it saw a log with no runs in it. The episode goes on
# its own line instead: still in the log, out of the pattern's way.
Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ') ===')
Write-Log ('episode: ' + $Ep)
Write-Log ('mode: ' + $(if ($Publish) { 'PUBLISH' } else { 'dry run (no publish)' }))

$lockTaken = $false
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
    $env:PYTHONIOENCODING = 'utf-8'

    if ($Hq -ne 'C:\Users\ojaej\jj-company') {
        Write-Log ('TEST DETOUR - operations server overridden: ' + $Hq)
        Write-Log 'this is not a real run'
    }

    # --- version gate: never publish from stale code -----------------------------
    #
    # Charter section 4, "know when a fix starts running". Schedule wrappers pull at
    # the top of every run; a wrapper a person calls by hand had no such step. On
    # 2026-08-29 the operations server sat on c010f43 while three merges (receipts,
    # reconcile, duplicate-live) waited on the remote. Running the publish command
    # then would have used a worker with NO duplicate-publish protection at all, on
    # the single most expensive run there is - the first real post.
    #
    # A failed pull does NOT fall through to the old code. It stops the run. Backlog
    # item 17 offered two options; JJ chose this one (pull, matching the schedule
    # path) over "check and refuse", so the two paths now behave the same way.
    #
    # WHAT THIS DOES AND DOES NOT REFRESH
    #   The Python worker is started AFTER this, so it runs the pulled code. This
    #   .ps1 file was read whole by PowerShell before the pull, so changes to the
    #   WRAPPER itself only take effect on the NEXT run. That is charter section 4
    #   again ("a running script finishes on the old version"), and it is why the
    #   check lives here rather than being trusted to a person's memory.
    $SyncHelper = Join-Path $Hq 'scripts\git-sync.ps1'
    if (-not (Test-Path -LiteralPath $SyncHelper)) {
        Write-Log ('git-sync helper missing: ' + $SyncHelper)
        Write-Log 'STATUS: FAIL stale-version'
        exit 1
    }
    . $SyncHelper
    Push-Location -LiteralPath $Hq
    try {
        $sync = Invoke-GitPullRetry -Log ${function:Write-Log}
    } finally {
        Pop-Location
    }
    if (-not $sync.Ok) {
        Write-Log ('git pull failed after ' + $sync.Attempts + ' attempts (exit ' + $sync.ExitCode + ')')
        Write-Log 'refusing to publish from code that may be behind the remote'
        Write-Log 'STATUS: FAIL stale-version'
        exit 1
    }
    $rev = (& git -C $Hq rev-parse --short HEAD 2>&1 | Select-Object -First 1)
    Write-Log ('operations server now at ' + $rev)

    # --- worker ------------------------------------------------------------------
    # The worker defaults to a dry run; -Publish is the only way past that, and it
    # has to be typed here as well. Two deliberate acts, not one.
    $WorkerPy = Join-Path $Hq 'scripts\publish_threads.py'
    if (-not (Test-Path -LiteralPath $WorkerPy)) {
        Write-Log ('worker missing: ' + $WorkerPy)
        Write-Log 'STATUS: FAIL worker-missing'
        exit 1
    }
    # Not $args - that is an automatic variable in PowerShell.
    $WorkerArgs = @('--ep', $Ep)
    if ($Publish) { $WorkerArgs += '--publish' }
    Write-Log ('publish_threads.py ' + ($WorkerArgs -join ' '))
    $out  = & py $WorkerPy @WorkerArgs 2>&1
    $code = $LASTEXITCODE
    foreach ($l in $out) { Write-Log ('  worker| ' + $l) }
    Write-Log ('worker exit code ' + $code)

    $statusLine = ($out | Select-String -Pattern '^STATUS:' | Select-Object -Last 1)
    if ($null -eq $statusLine) {
        Write-Log 'STATUS: FAIL worker-status-missing'
        exit 1
    }
    Write-Log ('worker status: ' + $statusLine.Line)
    if ($code -ne 0) {
        Write-Log ('STATUS: FAIL worker-exit-' + $code)
        exit 1
    }
    # Backup right after a successful publish (infra backlog 21, option 3).
    # A published episode is exactly when the workshop sources are worth the
    # most and have just changed. Best effort ON PURPOSE: a backup failure must
    # not turn a successful publish into a FAIL - the posts are already live and
    # rewriting the status would misreport what happened. It gets its own line
    # in this log instead, so a failure is still visible.
    $Bk = Join-Path $Hq 'scripts\workshop-backup.ps1'
    if (Test-Path -LiteralPath $Bk) {
        Write-Log 'post-publish backup (best effort - does not change publish status)'
        $bkOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $Bk ('after-publish:' + $Ep) 2>&1
        foreach ($l in $bkOut) { Write-Log ('  backup| ' + $l) }
        Write-Log ('post-publish backup exit ' + $LASTEXITCODE)
    } else {
        Write-Log 'post-publish backup skipped - workshop-backup.ps1 not found'
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
