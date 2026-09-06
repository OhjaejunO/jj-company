#requires -Version 5.1
#
# JJ Company OS - Naver blog publish worker wrapper
# Spec: docs\blog-format.md (step 5)   Charter section 0 (publishing, Naver clause 2026-09-06).
# Mirrors publish-threads.ps1 - same lock, same version gate, same permission probe.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as the
# system ANSI codepage, which mangles Korean. Korean lives in the Python worker.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publish-naver.ps1 -Post 2026-09-07_Fable_Mythos5_1
#   ... -Post <stem> -Publish        <- actually publishes. Without it the worker is a dry run.
#   The worker needs the Orca browser tab logged in to Naver (person's job).

param(
    [Parameter(Mandatory = $true)][string]$Post,
    [switch]$Publish,
    [string]$Hq = 'C:\Users\ojaej\jj-company'
)

$ErrorActionPreference = 'Continue'

$Task    = 'publish-naver'
$Stamp   = Get-Date -Format 'yyyyMMdd'
$IsoDate = Get-Date -Format 'yyyy-MM-dd'
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

    # --- check 2 of the three checks: the approval folder must be out of reach ----
    $AllowedTools = @(
        'Read', 'Glob', 'Grep',
        'Edit(reports/**)'
    )
    $ProbePy = Join-Path $Hq 'scripts\permission_probe.py'
    if (-not (Test-Path -LiteralPath $ProbePy)) {
        Write-Log ('permission probe missing: ' + $ProbePy)
        Write-Log 'STATUS: FAIL probe-script-missing'
        exit 1
    }
    $DataDir = Join-Path $Hq 'logs\publish-data'
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $ProbeData  = Join-Path $DataDir ('probe_naver_' + $Post + '_' + $IsoDate + '.txt')
    $ProbeDeny  = Join-Path $Hq 'publish_approval\_probe_should_fail.json'
    $ProbeAllow = Join-Path $Hq 'reports\_probe_ok.md'
    $MoveBat    = Join-Path $Hq 'scripts\move-approval.bat'
    $ExecMarker = Join-Path $Hq 'logs\_move-approval-ran.marker'
    Write-Log ('permission_probe.py -> ' + $ProbeData)
    $probeOut  = & py $ProbePy --cwd $Hq --deny $ProbeDeny --allow $ProbeAllow `
        --deny-exec ('"' + $MoveBat + '" --probe') --exec-marker $ExecMarker `
        '--' @AllowedTools 2>&1
    $probeCode = $LASTEXITCODE
    Set-Content -LiteralPath $ProbeData -Value $probeOut -Encoding UTF8
    foreach ($l in $probeOut) { Write-Log ('  probe| ' + $l) }
    if ($probeCode -ne 0) {
        $pv = ($probeOut | Select-String -Pattern '^PROBE_VERDICT=' | Select-Object -Last 1)
        Write-Log ('STATUS: FAIL probe ' + $(if ($pv) { $pv.Line } else { 'no verdict line' }))
        exit 1
    }
    Write-Log 'probe OK - approval folder refused, move batch not runnable, reports writable'

    # --- worker ------------------------------------------------------------------
    $WorkerPy = Join-Path $Hq 'scripts\publish_naver.py'
    if (-not (Test-Path -LiteralPath $WorkerPy)) {
        Write-Log ('worker missing: ' + $WorkerPy)
        Write-Log 'STATUS: FAIL worker-missing'
        exit 1
    }
    $WorkerArgs = @('--post', $Post)
    if ($Publish) { $WorkerArgs += '--publish' }
    Write-Log ('publish_naver.py ' + ($WorkerArgs -join ' '))
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
