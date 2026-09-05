#requires -Version 5.1
# JJ Company OS - blog-writer wrapper (daily 09:00, stagger 8 min)
# ASCII-only on purpose (PS 5.1 decodes BOM-less .ps1 as the ANSI codepage).
#
# Chain (charter section 4):
#   lock -> stagger -> git pull -> deploy-skill -> blog_brief.py (deterministic material)
#   -> permission probe -> claude -p (blog-writer, default mode, narrow allowlist)
#   -> report exists -> draft exists (unless brief says 0 items) -> blogcheck.py OK
# Mirrors tomangchi-scout.ps1; differences are marked  # blog:
$ErrorActionPreference = 'Continue'

$Task       = 'blog-writer'
$StartDelayMinutes = 8                                   # blog: scout 4 / job 6 / blog 8

$Hq         = 'C:\Users\ojaej\jj-company'
$Claude     = 'C:\Users\ojaej\.local\bin\claude.exe'
$env:PONYTAIL_DEFAULT_MODE = 'off'
$PromptFile = Join-Path $Hq 'scripts\prompts\blog-writer.md'

$SkillDir   = 'C:\Users\ojaej\.claude\skills\tomangchi'
$Workshop   = 'C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop'   # blog: read-only material

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

    # blog: deterministic material first. The agent reads only this file.
    $DataDir = Join-Path $Hq 'logs\blog-data'
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $Brief   = Join-Path $DataDir ('brief_' + $IsoDate + '.md')
    $BriefPy = Join-Path $Hq 'scripts\blog_brief.py'
    $env:PYTHONIOENCODING = 'utf-8'
    if (-not (Test-Path -LiteralPath $BriefPy)) { Write-Log ('brief script missing: ' + $BriefPy); Write-Log 'STATUS: FAIL brief-script-missing'; exit 1 }
    $bOut = & py $BriefPy --date $IsoDate --out $Brief 2>&1
    $bCode = $LASTEXITCODE
    foreach ($l in $bOut) { Write-Log ('  brief| ' + $l) }
    if ($bCode -ne 0 -or -not (Test-Path -LiteralPath $Brief)) { Write-Log 'STATUS: FAIL brief'; exit 1 }
    $briefLast = (Get-Content -LiteralPath $Brief -Encoding UTF8 | Select-Object -Last 1)
    $zeroItems = ($briefLast -match '0')   # "STATUS: OK (소재 0건)" -> the only STATUS line with a digit
    Write-Log ('brief last line: ' + $briefLast + ' zeroItems=' + $zeroItems)

    $prompt = (Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8).Replace('{{DATE}}', $IsoDate).Replace('{{WEEKDAY}}', $Weekday).Replace('{{BRIEF}}', $Brief)

    $AllowedTools = @(
        'Agent',
        'Read', 'Glob', 'Grep',
        'ToolSearch', 'SendMessage',
        'Edit(reports/**)',
        'Bash(py scripts/blogcheck.py*)',
        'Bash(py scripts\blogcheck.py*)',
        'Bash(py *blogcheck.py*)',
        'Bash(dir*)',
        'Bash(type*)'
    )

    $ProbePy = Join-Path $Hq 'scripts\permission_probe.py'
    if (-not (Test-Path -LiteralPath $ProbePy)) { Write-Log 'STATUS: FAIL probe-script-missing'; exit 1 }
    $ProbeData  = Join-Path $DataDir ('probe_' + $IsoDate + '.txt')
    $ProbeDeny  = Join-Path $Hq 'docs\_probe_should_fail.md'
    $ProbeAllow = Join-Path $Hq 'reports\_probe_ok.md'
    $probeOut = & py $ProbePy --cwd $Hq --deny $ProbeDeny --allow $ProbeAllow --add-dir $SkillDir --add-dir $Workshop '--' @AllowedTools 2>&1
    $probeCode = $LASTEXITCODE
    Set-Content -LiteralPath $ProbeData -Value $probeOut -Encoding UTF8
    foreach ($l in $probeOut) { Write-Log ('  probe| ' + $l) }
    if ($probeCode -ne 0) {
        $pv = ($probeOut | Select-String -Pattern '^PROBE_VERDICT=' | Select-Object -Last 1)
        Write-Log ('STATUS: FAIL probe ' + $(if ($pv) { $pv.Line } else { 'no verdict line' }))
        exit 1
    }

    Write-Log ('claude -p (blog-writer) start, allowed-tools: ' + ($AllowedTools -join ' '))
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
        --add-dir $SkillDir --add-dir $Workshop 2>&1
    $claudeCode = $LASTEXITCODE
    foreach ($l in $out) { Write-Log ('  cc| ' + $l) }
    Write-Log ('claude exit code ' + $claudeCode)
    if ($hrOn) { Write-HeadroomSavings $hrBefore }
    if ($claudeCode -ne 0) { Write-Log ('STATUS: FAIL claude-exit-' + $claudeCode); exit 1 }

    $Report = Join-Path $Hq ('reports\' + $IsoDate + '_' + $Task + '.md')
    if (-not (Test-Path -LiteralPath $Report)) { Write-Log ('report missing: ' + $Report); Write-Log 'STATUS: FAIL report-missing'; exit 1 }
    $reportStatus = (Select-String -LiteralPath $Report -Pattern '^STATUS:' | Select-Object -Last 1).Line
    if ($null -eq $reportStatus) { Write-Log 'STATUS: FAIL report-status-missing'; exit 1 }
    Write-Log ('report status line: ' + $reportStatus)
    if ($reportStatus -notmatch 'STATUS:\s*OK') { Write-Log 'STATUS: FAIL agent-status-not-ok'; exit 1 }

    # blog: the draft is the product. Re-run the gate here - the agent's own claim is not the evidence.
    $drafts = @(Get-ChildItem -LiteralPath (Join-Path $Hq 'reports\blog') -Filter ($IsoDate + '_*.md') -ErrorAction SilentlyContinue)
    if ($drafts.Count -eq 0) {
        if ($zeroItems) { Write-Log 'no draft and brief had 0 items -- acceptable'; Write-Log 'STATUS: OK (no-draft: 0 items)'; exit 0 }
        Write-Log 'draft missing while brief had items'; Write-Log 'STATUS: FAIL draft-missing'; exit 1
    }
    $CheckPy = Join-Path $Hq 'scripts\blogcheck.py'
    foreach ($d in $drafts) {
        $cOut = & py $CheckPy $d.FullName 2>&1
        foreach ($l in $cOut) { Write-Log ('  gate| ' + $l) }
        $last = ($cOut | Select-String -Pattern '^STATUS:' | Select-Object -Last 1)
        if ($null -eq $last -or $last.Line -notmatch 'STATUS:\s*OK') { Write-Log ('STATUS: FAIL blogcheck ' + $d.Name); exit 1 }
        Write-Log ('draft OK: ' + $d.FullName)
    }
    Write-Log 'STATUS: OK'
    exit 0
}
finally {
    if ($lockTaken -and (Test-Path -LiteralPath $LockFile)) { Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue; Write-Log 'lock released' }
    if (Test-Path -LiteralPath $StartedFile) { Remove-Item -LiteralPath $StartedFile -Force -ErrorAction SilentlyContinue }
}
