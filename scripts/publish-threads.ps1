#requires -Version 5.1
#
# JJ Company OS - Threads publish worker wrapper
# Spec: docs\workers\publish-threads.md   Charter section 0 (publishing) / section 4.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as the
# system ANSI codepage, which mangles Korean. Korean lives in the Python worker.
#
# WHAT THIS WRAPPER IS FOR
#   The worker itself is a deterministic script - it does not need an agent. What it
#   DOES need is proof, taken on this run, that the approval folder is out of reach.
#   That proof is the whole of check 2 in the spec's three checks, so it runs FIRST
#   and a failure stops the run before the worker is ever started.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publish-threads.ps1 -Ep ep39
#   ... -Ep ep39 -Publish        <- actually posts. Without it the worker is a dry run.

param(
    [Parameter(Mandatory = $true)][string]$Ep,
    [switch]$Publish
)

$ErrorActionPreference = 'Continue'

$Task    = 'publish-threads'
$Hq      = 'C:\Users\ojaej\jj-company'
$Stamp   = Get-Date -Format 'yyyyMMdd'
$IsoDate = Get-Date -Format 'yyyy-MM-dd'
$LogDir  = Join-Path $Hq 'logs\scheduled'
$LogFile = Join-Path $LogDir ($Task + '_' + $Ep + '_' + $Stamp + '.log')
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

Write-Log ('=== ' + $Task + ' ' + $Ep + ' start (pid ' + $PID + ') ===')
Write-Log ('mode: ' + $(if ($Publish) { 'PUBLISH' } else { 'dry run (no publish)' }))

$lockTaken = $false
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
    $env:PYTHONIOENCODING = 'utf-8'

    # --- check 2 of the three checks: the approval folder must be out of reach ----
    #
    # The list below is the permission surface a session gets for this job. The
    # approval folder appears in NO rule, so a write there must be refused. That is
    # a claim until something measures it, so the probe measures it - on this run,
    # in both directions, judged by whether the files exist rather than by what the
    # model says about them. See scripts\permission_probe.py and charter section 4.
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
    $ProbeData  = Join-Path $DataDir ('probe_' + $Ep + '_' + $IsoDate + '.txt')
    # Deny target sits INSIDE the approval folder on purpose - probing a neighbour
    # would prove nothing about the folder we actually care about.
    $ProbeDeny  = Join-Path $Hq 'publish_approval\_probe_should_fail.json'
    $ProbeAllow = Join-Path $Hq 'reports\_probe_ok.md'
    Write-Log ('permission_probe.py -> ' + $ProbeData)
    $probeOut  = & py $ProbePy --cwd $Hq --deny $ProbeDeny --allow $ProbeAllow '--' @AllowedTools 2>&1
    $probeCode = $LASTEXITCODE
    Set-Content -LiteralPath $ProbeData -Value $probeOut -Encoding UTF8
    foreach ($l in $probeOut) { Write-Log ('  probe| ' + $l) }
    if ($probeCode -ne 0) {
        $pv = ($probeOut | Select-String -Pattern '^PROBE_VERDICT=' | Select-Object -Last 1)
        Write-Log ('STATUS: FAIL probe ' + $(if ($pv) { $pv.Line } else { 'no verdict line' }))
        exit 1
    }
    Write-Log 'probe OK - approval folder refused, reports writable'

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
    Write-Log 'STATUS: OK'
    exit 0
}
finally {
    if ($lockTaken -and (Test-Path -LiteralPath $LockFile)) {
        Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
        Write-Log 'lock released'
    }
}
