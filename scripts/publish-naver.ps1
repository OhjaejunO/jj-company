#requires -Version 5.1
#
# JJ Company OS - Naver blog publish worker wrapper
# Spec: docs\blog-format.md (step 5)   Charter section 0 (publishing, Naver clause 2026-09-06).
# Mirrors publish-threads.ps1 - same lock, same version gate.
#
# 2026-09-10: the permission probe that used to run here is GONE. It proved that the
# approval folder was out of reach, and JJ retired the approval device, so the probe
# had nothing left to measure. Qualification is now blogcheck.py --publish, which the
# worker runs on itself right before it would click Publish.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as the
# system ANSI codepage, which mangles Korean. Korean lives in the Python worker.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publish-naver.ps1 -Post 2026-09-07_Fable_Mythos5_1
#   ... -Post <stem> -Draft          <- STAGE 1: fills the editor and saves a temp draft. NEVER publishes.
#   ... -Post <stem> -Publish        <- actually publishes. Without it the worker is a dry run.
#   ... -Post <stem> -Update <logNo> <- refills an ALREADY PUBLISHED post from the draft.
#       The live post is untouched until Publish is clicked, so without -Publish this is a dry run too.
#   The worker needs the Orca browser tab logged in to Naver (person's job).
#
# WHY STAGE 1 LIVES HERE (2026-09-12)
#   Naver publishing is two stages: naver_draft.py saves a temp draft, publish_naver.py loads it
#   and clicks Publish. Only stage 2 had a wrapper, so stage 1 had no lock, no log the audit
#   can find, and no version gate - and on 2026-09-12 stage 2 failed with 'no-entry' on four
#   posts for the simple reason that nobody had run stage 1. Half of the pipeline was invisible.
#   Same wrapper, same lock: the lock also keeps stage 1 and stage 2 off the browser at once.
#   -Draft is strictly LESS consequential than -Publish, which this wrapper already does.

param(
    [Parameter(Mandatory = $true)][string]$Post,
    [string]$Update,
    [switch]$Draft,
    [switch]$Publish,
    [string]$Blog = 'ai-tomangchi-lab',
    [string]$Hq = 'C:\Users\ojaej\jj-company'
)

$ErrorActionPreference = 'Continue'

$Task    = 'publish-naver'
$Stamp   = Get-Date -Format 'yyyyMMdd'
$LogDir  = Join-Path $Hq 'logs\scheduled'
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

Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ') ===')
Write-Log ('post: ' + $Post)
if ($Draft) {
    Write-Log 'mode: DRAFT (stage 1 - save temp draft, never publishes)'
} else {
    Write-Log ('mode: ' + $(if ($Publish) { 'PUBLISH' } else { 'dry run (no publish)' }))
}
if ($Update) { Write-Log ('target: UPDATE existing post logNo ' + $Update) }

# Stage 1 saves a temp draft and stage 2 publishes one. Mixing the switches would read as
# 'write it and push it out in one go', which is not what either worker does - and the
# reader of the log could not tell which one ran. Refuse instead of guessing.
if ($Draft -and ($Publish -or $Update)) {
    Write-Log 'STATUS: FAIL draft-with-publish (stage 1 and stage 2 are separate runs)'
    exit 2
}

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

    # --- version gate: never publish from stale code (same as publish-threads.ps1) ---
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
        Write-Log 'STATUS: FAIL stale-version'
        exit 1
    }
    $rev = (& git -C $Hq rev-parse --short HEAD 2>&1 | Select-Object -First 1)
    Write-Log ('operations server now at ' + $rev)

    # --- worker ------------------------------------------------------------------
    $WorkerName = $(if ($Draft) { 'naver_draft.py' } else { 'publish_naver.py' })
    $WorkerPy = Join-Path $Hq ('scripts\' + $WorkerName)
    if (-not (Test-Path -LiteralPath $WorkerPy)) {
        Write-Log ('worker missing: ' + $WorkerPy)
        Write-Log 'STATUS: FAIL worker-missing'
        exit 1
    }
    $WorkerArgs = @('--post', $Post)
    if ($Draft) {
        $WorkerArgs += @('--blog', $Blog)
    } else {
        if ($Update) { $WorkerArgs += @('--update', $Update) }
        if ($Publish) { $WorkerArgs += '--publish' }
    }
    Write-Log ($WorkerName + ' ' + ($WorkerArgs -join ' '))
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
    Write-Log 'STATUS: OK'
    exit 0
}
finally {
    if ($lockTaken -and (Test-Path -LiteralPath $LockFile)) {
        Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
        Write-Log 'lock released'
    }
}
