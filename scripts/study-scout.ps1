#requires -Version 5.1
# JJ Company OS - study-scout wrapper (weekly, Sunday 15:00, stagger 10 min)
# ASCII-only on purpose (PS 5.1 decodes BOM-less .ps1 as the ANSI codepage).
#
# Chain (charter section 4):
#   lock -> stagger -> git pull -> deploy-skill -> study_watch.py (new/changed notes)
#   -> 0 notes: write a one-line report, STATUS: OK (no new notes), skip the agent
#   -> else: permission probe -> claude -p (study-scout, read-only) -> report exists
#   -> study_watch.py --mark  (only after success: a failed run leaves the notes "new")
# Mirrors blog-writer.ps1; differences are marked  # study:
$ErrorActionPreference = 'Continue'

$Task       = 'study-scout'
$StartDelayMinutes = 10

$Hq         = 'C:\Users\ojaej\jj-company'
$Claude     = 'C:\Users\ojaej\.local\bin\claude.exe'
$env:PONYTAIL_DEFAULT_MODE = 'off'
$PromptFile = Join-Path $Hq 'scripts\prompts\study-scout.md'

$SkillDir   = 'C:\Users\ojaej\.claude\skills\tomangchi'
$StudyRoot  = -join ([char]0x43, [char]0x3A, [char]0x5C, [char]0xACF5, [char]0xBD80)   # study: C:\공부 (Korean, built from code points)

$Stamp    = Get-Date -Format 'yyyyMMdd'
$IsoDate  = Get-Date -Format 'yyyy-MM-dd'
$Weekday  = (Get-Date).DayOfWeek.ToString()
$LogDir   = Join-Path $Hq 'logs\scheduled'
$LogFile  = Join-Path $LogDir ($Task + '_' + $Stamp + '.log')
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
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

if (Test-Path -LiteralPath $LockFile) {
    Write-Log ('lock file present: ' + $LockFile + ' -- aborting, another run owns it')
    Write-Log 'STATUS: FAIL lock-exists'
    exit 2
}

Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ', ' + $Weekday + ') ===')

$StartedFile = Join-Path $Hq ('logs\' + $Task + '.started')
Set-Content -LiteralPath $StartedFile -Encoding UTF8 -Value ('pid=' + $PID + ' started=' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))

if ($StartDelayMinutes -gt 0) {
    Write-Log ('start stagger: sleeping ' + $StartDelayMinutes + ' min')
    Start-Sleep -Seconds ($StartDelayMinutes * 60)
    Write-Log 'stagger complete'
}
if (Test-Path -LiteralPath $LockFile) {
    Write-Log 'lock file present after stagger -- aborting'
    Write-Log 'STATUS: FAIL lock-exists'
    Remove-Item -LiteralPath $StartedFile -Force -ErrorAction SilentlyContinue
    exit 2
}

$lockTaken = $false
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    Write-Log ('lock acquired: ' + $LockFile)

    $VerHelper = Join-Path $Hq 'scripts\skill-version.ps1'
    if (Test-Path -LiteralPath $VerHelper) { . $VerHelper; foreach ($vl in (Get-SkillVersionLines)) { Write-Log $vl } }

    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
    Set-Location -LiteralPath $Hq
    Write-Log ('cwd: ' + (Get-Location).Path)

    foreach ($h in @('scripts\git-sync.ps1', 'scripts\native-arg.ps1')) {
        $p = Join-Path $Hq $h
        if (-not (Test-Path -LiteralPath $p)) { Write-Log ('helper missing: ' + $p); Write-Log 'STATUS: FAIL helper-missing'; exit 1 }
        . $p
    }
    $pull = Invoke-GitPullRetry -Log ${function:Write-Log}
    if (-not $pull.Ok) { Write-Log 'STATUS: FAIL git-sync'; exit 1 }

    $Deploy = Join-Path $Hq 'scripts\deploy-skill.ps1'
    if (-not (Test-Path -LiteralPath $Deploy)) { Write-Log ('skill deploy script missing: ' + $Deploy); Write-Log 'STATUS: FAIL skill-sync'; exit 1 }
    Write-Log 'deploy-skill (live <- origin/main)'
    $depOut  = & powershell -NoProfile -ExecutionPolicy Bypass -File $Deploy 2>&1
    $depCode = $LASTEXITCODE
    foreach ($l in $depOut) { Write-Log ('  skill| ' + $l) }
    if ($depCode -ne 0) {
        if (($depOut | Out-String) -match 'credentials') { Write-Log 'STATUS: FAIL skill-sync-auth (gh token expired or missing)' }
        else { Write-Log 'STATUS: FAIL skill-sync' }
        exit 1
    }

    if (-not (Test-Path -LiteralPath $PromptFile)) { Write-Log ('prompt file missing: ' + $PromptFile); Write-Log 'STATUS: FAIL prompt-missing'; exit 1 }
    if (-not (Test-Path -LiteralPath $StudyRoot)) { Write-Log ('study root missing: ' + $StudyRoot); Write-Log 'STATUS: FAIL study-root-missing'; exit 1 }

    # study: deterministic new-note detection first.
    $DataDir = Join-Path $Hq 'logs\study-data'
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $NewList = Join-Path $DataDir ('new_' + $IsoDate + '.txt')
    $WatchPy = Join-Path $Hq 'scripts\study_watch.py'
    $env:PYTHONIOENCODING = 'utf-8'
    if (-not (Test-Path -LiteralPath $WatchPy)) { Write-Log 'STATUS: FAIL watch-script-missing'; exit 1 }
    $wOut = & py $WatchPy --root $StudyRoot --date $IsoDate --out $NewList 2>&1
    $wCode = $LASTEXITCODE
    foreach ($l in $wOut) { Write-Log ('  watch| ' + $l) }
    if ($wCode -ne 0 -or -not (Test-Path -LiteralPath $NewList)) { Write-Log 'STATUS: FAIL study-watch'; exit 1 }
    $newLine = ($wOut | Select-String -Pattern '^STUDY_NEW=' | Select-Object -Last 1)
    $newCount = 0
    if ($newLine) { $newCount = [int]($newLine.Line -replace '^STUDY_NEW=', '') }
    Write-Log ('new notes: ' + $newCount)

    $Report = Join-Path $Hq ('reports\' + $IsoDate + '_' + $Task + '.md')
    if ($newCount -eq 0) {
        # study: nothing to read -> the wrapper writes the report itself; no model call.
        $body = @(('# study-scout ' + $IsoDate), '', ('- new or changed notes under ' + $StudyRoot + ': 0'), ('- list: ' + $NewList), '', 'STATUS: OK (no new notes)')
        Set-Content -LiteralPath $Report -Value $body -Encoding UTF8
        Write-Log ('report (no new notes): ' + $Report)
        Write-Log 'STATUS: OK (no new notes)'
        exit 0
    }

    $prompt = (Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8).Replace('{{DATE}}', $IsoDate).Replace('{{NEW_LIST}}', $NewList)

    $AllowedTools = @(
        'Agent',
        'Read', 'Glob', 'Grep',
        'ToolSearch', 'SendMessage',
        'Edit(reports/**)'
    )

    $ProbePy = Join-Path $Hq 'scripts\permission_probe.py'
    if (-not (Test-Path -LiteralPath $ProbePy)) { Write-Log 'STATUS: FAIL probe-script-missing'; exit 1 }
    $ProbeData  = Join-Path $DataDir ('probe_' + $IsoDate + '.txt')
    $ProbeDeny  = Join-Path $Hq 'docs\_probe_should_fail.md'
    $ProbeAllow = Join-Path $Hq 'reports\_probe_ok.md'
    $probeOut = & py $ProbePy --cwd $Hq --deny $ProbeDeny --allow $ProbeAllow --add-dir $SkillDir --add-dir $StudyRoot '--' @AllowedTools 2>&1
    $probeCode = $LASTEXITCODE
    Set-Content -LiteralPath $ProbeData -Value $probeOut -Encoding UTF8
    foreach ($l in $probeOut) { Write-Log ('  probe| ' + $l) }
    if ($probeCode -ne 0) {
        $pv = ($probeOut | Select-String -Pattern '^PROBE_VERDICT=' | Select-Object -Last 1)
        Write-Log ('STATUS: FAIL probe ' + $(if ($pv) { $pv.Line } else { 'no verdict line' }))
        exit 1
    }

    Write-Log ('claude -p (study-scout) start, allowed-tools: ' + ($AllowedTools -join ' '))
    $HrHelper = Join-Path $Hq 'scripts\headroom-proxy.ps1'
    $hrOn = $false; $hrBefore = -1
    if (Test-Path -LiteralPath $HrHelper) {
        . $HrHelper
        $hrOn = Start-HeadroomProxy
        if ($hrOn) { $env:ANTHROPIC_BASE_URL = $HeadroomUrl; $hrBefore = Get-HeadroomSavedTokens; Write-Log ('headroom: ON -> ' + $HeadroomUrl) }
        else { Remove-Item Env:ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue; Write-Log 'headroom: OFF (direct)' }
    } else { Write-Log 'headroom: helper missing -> OFF (direct)' }
    $out = & $Claude -p (ConvertTo-NativeArg $prompt) --permission-mode default `
        --allowed-tools @AllowedTools `
        --add-dir $SkillDir --add-dir $StudyRoot 2>&1
    $claudeCode = $LASTEXITCODE
    foreach ($l in $out) { Write-Log ('  cc| ' + $l) }
    Write-Log ('claude exit code ' + $claudeCode)
    if ($hrOn) { Write-HeadroomSavings $hrBefore }
    if ($claudeCode -ne 0) { Write-Log ('STATUS: FAIL claude-exit-' + $claudeCode); exit 1 }

    if (-not (Test-Path -LiteralPath $Report)) { Write-Log ('report missing: ' + $Report); Write-Log 'STATUS: FAIL report-missing'; exit 1 }
    $reportStatus = (Select-String -LiteralPath $Report -Pattern '^STATUS:' | Select-Object -Last 1).Line
    if ($null -eq $reportStatus) { Write-Log 'STATUS: FAIL report-status-missing'; exit 1 }
    Write-Log ('report status line: ' + $reportStatus)
    if ($reportStatus -notmatch 'STATUS:\s*OK') { Write-Log 'STATUS: FAIL agent-status-not-ok'; exit 1 }

    # study: only now are the notes "seen". A failed run above never reaches this line.
    $mOut = & py $WatchPy --root $StudyRoot --mark 2>&1
    foreach ($l in $mOut) { Write-Log ('  mark| ' + $l) }

    $verify = Join-Path $Hq 'scripts\cross-verify.ps1'
    if (Test-Path -LiteralPath $verify) {
        & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $verify -Report $Report | Out-Null
        Write-Log ('cross-verify exit code ' + $LASTEXITCODE + ' (does not affect this run)')
    }
    Write-Log ('report: ' + $Report)
    Write-Log 'STATUS: OK'
    exit 0
}
finally {
    if ($lockTaken -and (Test-Path -LiteralPath $LockFile)) { Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue; Write-Log 'lock released' }
    if (Test-Path -LiteralPath $StartedFile) { Remove-Item -LiteralPath $StartedFile -Force -ErrorAction SilentlyContinue }
}
