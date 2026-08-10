#requires -Version 5.1
#
# JJ Company OS - cross-verify (grade A, read-only audit by a second model)
#
# Hands a finished report plus the rules that produced it to codex and asks for
# violations, source/claim mismatches, and overreach. The verdict is APPENDED to
# the report - the body is never edited. codex itself runs read-only.
#
# Auth: split by design. codex ignores OPENAI_API_KEY when ~/.codex holds ChatGPT
# tokens (verified: an intentionally invalid key still succeeded), so the audit
# gets its OWN config dir via CODEX_HOME. ~/.codex-jjcompany is logged in with the
# API key; ~/.codex keeps JJ's interactive ChatGPT auth untouched.
#
# CODEX_HOME is set on THIS PROCESS ONLY - it never leaks to the parent shell or
# to JJ's interactive sessions. Do not move it to a user-scope variable.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as
# the system ANSI codepage. All Korean text lives in scripts\prompts\*.md and is
# read as explicit UTF-8.

param(
    [Parameter(Mandatory = $true)][string]$Report,
    [string]$Rules,
    [int]$TimeoutSec = 600
)

$ErrorActionPreference = 'Continue'

$Task      = 'cross-verify'
$Hq        = 'C:\Users\ojaej\jj-company'
$Codex     = 'C:\Users\ojaej\AppData\Roaming\npm\codex.cmd'
$Model     = 'codex default'
$CodexHome = 'C:\Users\ojaej\.codex-jjcompany'

$PromptFile  = Join-Path $Hq 'scripts\prompts\cross-verify.md'
$SectionFile = Join-Path $Hq 'scripts\prompts\cross-verify.section.md'

$Stamp   = Get-Date -Format 'yyyyMMdd'
$LogDir  = Join-Path $Hq 'logs\scheduled'
$LogFile = Join-Path $LogDir ($Task + '_' + $Stamp + '.log')

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log {
    param([string]$Message)
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Write-Utf8 {
    param([string]$Path, [string]$Text)
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

function Append-Utf8 {
    param([string]$Path, [string]$Text)
    [System.IO.File]::AppendAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

# Report file name is <yyyy-MM-dd>_<task>.md; the task picks the rules file.
$RULES_BY_TASK = @{
    'tomangchi-scout'      = '.claude\agents\content-scout.md'
    'job-scout'            = '.claude\agents\job-scout.md'
    'morning-vault-health' = '.claude\agents\ops-auditor.md'
}

function Resolve-Rules {
    param([string]$ReportPath)
    $name = [System.IO.Path]::GetFileNameWithoutExtension($ReportPath)
    $split = $name.IndexOf('_')
    if ($split -lt 0) { return $null }
    $taskName = $name.Substring($split + 1)
    if (-not $RULES_BY_TASK.ContainsKey($taskName)) { return $null }
    return Join-Path $Hq $RULES_BY_TASK[$taskName]
}

function Append-Section {
    param([string]$Body, [bool]$Failed)

    $templates = (Get-Content -LiteralPath $SectionFile -Raw -Encoding UTF8) -split '<!--SPLIT-->'
    $template = if ($Failed) { $templates[1] } else { $templates[0] }

    $text = $template.
        Replace('{{TIME}}',   (Get-Date -Format 'yyyy-MM-dd HH:mm')).
        Replace('{{MODEL}}',  $Model).
        Replace('{{RULES}}',  $Rules).
        Replace('{{REPORT}}', $Report).
        Replace('{{BODY}}',   $Body)

    Append-Utf8 -Path $Report -Text ($text.TrimEnd() + "`r`n")
}

Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ') ===')
Write-Log ('report: ' + $Report)

if (-not (Test-Path -LiteralPath $Report)) {
    Write-Log ('report not found: ' + $Report)
    Write-Log 'STATUS: FAIL report-missing'
    exit 1
}
if (-not (Test-Path -LiteralPath $PromptFile) -or -not (Test-Path -LiteralPath $SectionFile)) {
    Write-Log 'prompt or section template missing'
    Write-Log 'STATUS: FAIL prompt-missing'
    exit 1
}

if (-not $Rules) { $Rules = Resolve-Rules -ReportPath $Report }
if (-not $Rules -or -not (Test-Path -LiteralPath $Rules)) {
    Write-Log ('rules file not resolved for: ' + $Report)
    Append-Section -Body 'rules-unresolved (report name did not map to an agent definition)' -Failed $true
    Write-Log 'STATUS: FAIL rules-unresolved'
    exit 1
}
Write-Log ('rules: ' + $Rules)

if (-not (Test-Path -LiteralPath $Codex)) {
    Write-Log ('codex not found: ' + $Codex)
    Append-Section -Body ('codex-not-found: ' + $Codex) -Failed $true
    Write-Log 'STATUS: FAIL codex-not-found'
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $CodexHome 'auth.json'))) {
    Write-Log ('audit codex home not logged in: ' + $CodexHome)
    Append-Section -Body ('codex-home-not-authenticated: ' + $CodexHome) -Failed $true
    Write-Log 'STATUS: FAIL codex-home-not-authenticated'
    exit 1
}

# Process-scoped only. The audit runs on the API key; JJ's ~/.codex is untouched.
$env:CODEX_HOME = $CodexHome
Write-Log ('CODEX_HOME=' + $CodexHome)

$prompt = (Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8).
    Replace('{{RULES}}',  $Rules).
    Replace('{{REPORT}}', $Report)

$tmp        = [System.IO.Path]::GetTempPath()
$promptPath = Join-Path $tmp ('jj-crossverify-prompt-' + $PID + '.txt')
$answerPath = Join-Path $tmp ('jj-crossverify-answer-' + $PID + '.txt')
$stdoutPath = Join-Path $tmp ('jj-crossverify-out-' + $PID + '.txt')
$stderrPath = Join-Path $tmp ('jj-crossverify-err-' + $PID + '.txt')
Write-Utf8 -Path $promptPath -Text $prompt

# read-only sandbox: codex may read the workspace but cannot write anything.
# The prompt is piped on stdin so the Korean text never crosses the command line.
$codexArgs = @(
    'exec',
    '-C', $Hq,
    '--sandbox', 'read-only',
    '--skip-git-repo-check',
    '-o', $answerPath,
    '-'
)

Write-Log ('codex exec start (timeout ' + $TimeoutSec + 's)')
$failure = $null
$code = $null

# codex is a .cmd shim; Start-Process -PassThru returns $null for it, so the
# process never launches. Invoke it directly and pipe the prompt on stdin, with
# a background job supplying the timeout.
$job = Start-Job -ScriptBlock {
    param($codex, $codexArgs, $promptPath, $stdoutPath, $stderrPath, $codexHome)
    # Set explicitly rather than relying on the job process inheriting it.
    $env:CODEX_HOME = $codexHome
    $text = Get-Content -LiteralPath $promptPath -Raw -Encoding UTF8
    $text | & $codex @codexArgs 1> $stdoutPath 2> $stderrPath
    $LASTEXITCODE
} -ArgumentList $Codex, $codexArgs, $promptPath, $stdoutPath, $stderrPath, $CodexHome

if (Wait-Job $job -Timeout $TimeoutSec) {
    $code = Receive-Job $job
    Write-Log ('codex exit code ' + $code)
} else {
    Stop-Job $job
    $failure = 'codex-timeout (' + $TimeoutSec + 's)'
}
Remove-Job $job -Force -ErrorAction SilentlyContinue

# The answer file is the artifact of record. codex prints a non-fatal
# models-manager warning on startup and its exit code has proven unreliable
# through the shim, so a written answer is what counts as success.
$answer = ''
if (-not $failure) {
    if (Test-Path -LiteralPath $answerPath) {
        $answer = (Get-Content -LiteralPath $answerPath -Raw -Encoding UTF8)
    }
    if (-not $answer -or -not $answer.Trim()) {
        $failure = if ($code) { 'codex-exit-' + $code } else { 'codex-empty-answer' }
    }
}

if ($failure) {
    # stderr can carry an auth or quota message; keep the first line only so no
    # secret-bearing payload is copied into the log (charter section 6).
    $hint = ''
    if (Test-Path -LiteralPath $stderrPath) {
        $errLine = (Get-Content -LiteralPath $stderrPath -TotalCount 1 -ErrorAction SilentlyContinue)
        if ($errLine) { $hint = ' | stderr: ' + $errLine.Substring(0, [Math]::Min(200, $errLine.Length)) }
    }
    Write-Log ('codex failed: ' + $failure + $hint)
    Append-Section -Body $failure -Failed $true
    Write-Log ('STATUS: FAIL ' + $failure)
} else {
    Append-Section -Body $answer.Trim() -Failed $false
    $verdict = ($answer.Trim() -split "`n")[0].Trim()
    Write-Log ('codex verdict: ' + $verdict)
    Write-Log ('appended to: ' + $Report)
    Write-Log 'STATUS: OK'
}

foreach ($f in @($promptPath, $answerPath, $stdoutPath, $stderrPath)) {
    Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
}

if ($failure) { exit 1 }
exit 0
