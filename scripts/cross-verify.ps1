#requires -Version 5.1
#
# JJ Company OS - cross-verify (grade A, read-only audit by a SECOND model)
#
# Hands a finished artifact plus the rules that produced it to an auditor model
# and asks for violations, source/claim mismatches, and overreach. The verdict is
# APPENDED to the artifact - the body is never edited. The auditor runs read-only.
#
# WHO AUDITS WHOM
#   The rule is not "codex audits" - it is AUTHOR != AUDITOR. Both directions
#   exist now that codex writes code as well as audits it (backlog C-44):
#
#       claude wrote it  -> -Auditor codex   (the three scheduled scout reports)
#       codex  wrote it  -> -Auditor claude  (a codex PR, a codex-written doc)
#
#   -Author is REQUIRED unless the artifact name maps to a known scheduled task,
#   in which case the author is claude (those reports come from `claude -p`).
#   An unknown author is a FAIL, not a silent pass: a cross-check that cannot
#   name the author cannot know it is a cross-check at all.
#
# WHY THAT GUARD IS MECHANICAL AND NOT PROSE
#   2026-09-08, step 2 of C-44: codex finished a PR and then CALLED ITS OWN
#   AUDITOR (`claude -p`) with a prompt containing its own justification, and
#   collected the PASS. AGENTS.md answered with a sentence ("the auditor is a
#   session JJ started"). A sentence is a rule; this is the device. If the author
#   and the auditor are the same model, this script refuses to run.
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
#
# SELF-TEST
#   powershell -File scripts\cross-verify.ps1 -SelfTest
#   Deterministic only (no model calls): rules/author resolution, the
#   author!=auditor refusal in BOTH directions, and template substitution.

param(
    [string]$Report,
    [string]$Rules,
    [ValidateSet('codex', 'claude')][string]$Auditor = 'codex',
    [ValidateSet('codex', 'claude')][string]$Author,
    [int]$TimeoutSec = 600,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Continue'

$Task      = 'cross-verify'
$Hq        = 'C:\Users\ojaej\jj-company'
$Codex     = 'C:\Users\ojaej\AppData\Roaming\npm\codex.cmd'
$Claude    = 'C:\Users\ojaej\.local\bin\claude.exe'
$CodexHome = 'C:\Users\ojaej\.codex-jjcompany'

$MODEL_LABEL = @{ 'codex' = 'codex default'; 'claude' = 'claude -p default' }

# Prompts ship NEXT TO this script, not at a fixed HQ path: the self-test must
# measure the templates that will actually run. Reading them from $Hq meant a
# worktree self-test passed or failed on the DEPLOYED copy - the one case the
# test exists to catch (a placeholder the script no longer fills) is invisible
# that way. On the operations server both paths are the same directory anyway.
$PromptFile  = Join-Path $PSScriptRoot 'prompts\cross-verify.md'
$SectionFile = Join-Path $PSScriptRoot 'prompts\cross-verify.section.md'

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
# Everything in this table is written by a `claude -p` agent, so the author of a
# resolved task is claude - that is why Resolve-Author reads the same table.
$RULES_BY_TASK = @{
    'tomangchi-scout'      = '.claude\agents\content-scout.md'
    'job-scout'            = '.claude\agents\job-scout.md'
    'morning-vault-health' = '.claude\agents\ops-auditor.md'
    'study-scout'          = '.claude\agents\study-scout.md'
}

function Get-TaskName {
    param([string]$ReportPath)
    $name = [System.IO.Path]::GetFileNameWithoutExtension($ReportPath)
    $split = $name.IndexOf('_')
    if ($split -lt 0) { return $null }
    $taskName = $name.Substring($split + 1)
    if (-not $RULES_BY_TASK.ContainsKey($taskName)) { return $null }
    return $taskName
}

function Resolve-Rules {
    param([string]$ReportPath)
    $taskName = Get-TaskName -ReportPath $ReportPath
    if (-not $taskName) { return $null }
    return Join-Path $Hq $RULES_BY_TASK[$taskName]
}

function Resolve-Author {
    param([string]$ReportPath)
    if (Get-TaskName -ReportPath $ReportPath) { return 'claude' }
    return $null
}

function Append-Section {
    param([string]$Body, [bool]$Failed, [string]$AuditorName, [string]$AuthorName)

    $templates = (Get-Content -LiteralPath $SectionFile -Raw -Encoding UTF8) -split '<!--SPLIT-->'
    $template = if ($Failed) { $templates[1] } else { $templates[0] }

    $text = $template.
        Replace('{{TIME}}',     (Get-Date -Format 'yyyy-MM-dd HH:mm')).
        Replace('{{AUDITOR}}',  $AuditorName).
        Replace('{{AUTHOR}}',   $(if ($AuthorName) { $AuthorName } else { 'unknown' })).
        Replace('{{MODEL}}',    $MODEL_LABEL[$AuditorName]).
        Replace('{{RULES}}',    $Rules).
        Replace('{{REPORT}}',   $Report).
        Replace('{{BODY}}',     $Body)

    Append-Utf8 -Path $Report -Text ($text.TrimEnd() + "`r`n")
}

# --- self-test ----------------------------------------------------------------
#
# What it measures, and why each half exists (charter section 0): a check that
# only shows the guard FIRING cannot tell a working guard from one that refuses
# everything. So every case here has its opposite next to it.
function Invoke-SelfTest {
    $fails = @()
    function t { param([string]$Name, [bool]$Ok, [string]$Got)
        if ($Ok) { Write-Host ('  OK   ' + $Name) }
        else { Write-Host ('  FAIL ' + $Name + '  got: ' + $Got); $script:stFails++ }
    }
    $script:stFails = 0

    Write-Host 'cross-verify self-test'

    # 1. rules + author resolution, and the miss case
    t 'rules resolve: scheduled report' `
        ((Resolve-Rules 'C:\x\reports\2026-09-07_job-scout.md') -like '*job-scout.md') `
        (Resolve-Rules 'C:\x\reports\2026-09-07_job-scout.md')
    t 'rules resolve: study-scout is in the table (it calls this script)' `
        ((Resolve-Rules 'C:\x\reports\2026-09-06_study-scout.md') -like '*study-scout.md') `
        (Resolve-Rules 'C:\x\reports\2026-09-06_study-scout.md')
    t 'rules resolve: unknown artifact yields nothing (no wrong rulebook)' `
        ($null -eq (Resolve-Rules 'C:\x\reports\pr209.diff')) 'not null'
    t 'author resolve: scheduled report is claude-authored' `
        ((Resolve-Author 'C:\x\reports\2026-09-07_job-scout.md') -eq 'claude') `
        (Resolve-Author 'C:\x\reports\2026-09-07_job-scout.md')
    t 'author resolve: unknown artifact yields nothing (caller must say)' `
        ($null -eq (Resolve-Author 'C:\x\reports\pr209.diff')) 'not null'

    # 2. author != auditor, BOTH directions. Without the second pair a script
    #    that refused every combination would look correct here.
    $same = { param($a, $b) ($a -and $a -eq $b) }
    t 'refuses claude auditing claude'          (& $same 'claude' 'claude') 'allowed'
    t 'refuses codex auditing codex'            (& $same 'codex'  'codex')  'allowed'
    t 'allows codex auditing claude'       (-not (& $same 'claude' 'codex')) 'refused'
    t 'allows claude auditing codex'       (-not (& $same 'codex'  'claude')) 'refused'

    # 3. the section template must actually carry the values. A placeholder left
    #    behind renders as literal braces in the report and nobody reads it as a
    #    bug - it looks like formatting.
    if (Test-Path -LiteralPath $SectionFile) {
        $tpl = (Get-Content -LiteralPath $SectionFile -Raw -Encoding UTF8) -split '<!--SPLIT-->'
        t 'section template splits into pass/fail halves' ($tpl.Count -eq 2) ('count=' + $tpl.Count)
        foreach ($i in 0, 1) {
            $filled = $tpl[$i].
                Replace('{{TIME}}', 'T').Replace('{{AUDITOR}}', 'claude').Replace('{{AUTHOR}}', 'codex').
                Replace('{{MODEL}}', 'M').Replace('{{RULES}}', 'R').Replace('{{REPORT}}', 'P').
                Replace('{{BODY}}', 'B')
            t ('template ' + $i + ': no placeholder left') (-not ($filled -match '\{\{')) $filled
            t ('template ' + $i + ': names the auditor') ($filled -match 'claude') 'auditor missing'
        }
        # the failure half tells a human how to re-run; that command must carry
        # -Auditor or the retry silently goes back to the default direction.
        t 'failure template re-run command carries -Auditor' ($tpl[1] -match '-Auditor') 'missing'
    } else {
        t 'section template exists' $false $SectionFile
    }

    # 4. the claude branch reads a native program's stdout. The first real run
    #    (2026-09-11) came back as mojibake because PS 5.1 decodes that stream
    #    with the ANSI codepage. Same job shape, a program that prints Korean:
    #    if the encoding line is ever dropped this goes back to '???'.
    $encJob = Start-Job -ScriptBlock {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8
        $env:PYTHONIOENCODING = 'utf-8'
        # ASCII-only source on purpose - this file is decoded as the ANSI
        # codepage, so a literal Korean string here would itself be mangled and
        # the case would measure the wrong hop.
        (& py -c 'import sys; sys.stdout.write(chr(0xAC00)+chr(0xB098)+chr(0xB2E4))') -join ''
    }
    $encOut = if (Wait-Job $encJob -Timeout 60) { (Receive-Job $encJob) -join '' } else { 'timeout' }
    Remove-Job $encJob -Force -ErrorAction SilentlyContinue
    t 'claude branch: native stdout survives as UTF-8 (not mojibake)' `
        ($encOut -eq ([char]0xAC00 + [string][char]0xB098 + [string][char]0xB2E4)) $encOut

    if ($script:stFails -gt 0) { Write-Host ('STATUS: FAIL selftest ' + $script:stFails); return 1 }
    Write-Host 'STATUS: OK'
    return 0
}

if ($SelfTest) { exit (Invoke-SelfTest) }

if (-not $Report) { Write-Host 'ERROR: -Report is required (or use -SelfTest)'; exit 1 }

Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ') ===')

# Run provenance: which rulebook revision this run actually used.
# 2026-08-15 diagnosis - the live skill used to be a symlink, so the answer
# changed with whatever branch was checked out and nothing recorded it.
$VerHelper = Join-Path $Hq 'scripts\skill-version.ps1'
if (Test-Path -LiteralPath $VerHelper) {
    . $VerHelper
    foreach ($vl in (Get-SkillVersionLines)) { Write-Log $vl }
} else {
    Write-Log ('skill version helper missing: ' + $VerHelper)
}
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

if (-not $Author) { $Author = Resolve-Author -ReportPath $Report }
if (-not $Author) {
    Write-Log ('author unknown for: ' + $Report)
    Append-Section -Body 'author-unknown (pass -Author codex|claude - an audit that cannot name the author is not a cross-check)' -Failed $true -AuditorName $Auditor -AuthorName $null
    Write-Log 'STATUS: FAIL author-unknown'
    exit 1
}
Write-Log ('author: ' + $Author + ' | auditor: ' + $Auditor)

if ($Author -eq $Auditor) {
    Write-Log ('author is auditor: ' + $Author)
    # Name the working combination in the body: the re-run command in the
    # failure template echoes the arguments it was GIVEN, which for this failure
    # are exactly the refused pair. Telling a reader to retry the refused call is
    # not advice.
    $other = if ($Author -eq 'codex') { 'claude' } else { 'codex' }
    Append-Section -Body ('author-is-auditor: ' + $Author + ' (C-44 step 2: a model auditing its own work returns PASS) - re-run with -Auditor ' + $other) -Failed $true -AuditorName $Auditor -AuthorName $Author
    Write-Log 'STATUS: FAIL author-is-auditor'
    exit 1
}

if (-not $Rules) { $Rules = Resolve-Rules -ReportPath $Report }
if (-not $Rules -or -not (Test-Path -LiteralPath $Rules)) {
    Write-Log ('rules file not resolved for: ' + $Report)
    Append-Section -Body 'rules-unresolved (report name did not map to an agent definition; pass -Rules)' -Failed $true -AuditorName $Auditor -AuthorName $Author
    Write-Log 'STATUS: FAIL rules-unresolved'
    exit 1
}
Write-Log ('rules: ' + $Rules)

$Bin = if ($Auditor -eq 'codex') { $Codex } else { $Claude }
if (-not (Test-Path -LiteralPath $Bin)) {
    Write-Log ($Auditor + ' not found: ' + $Bin)
    Append-Section -Body ($Auditor + '-not-found: ' + $Bin) -Failed $true -AuditorName $Auditor -AuthorName $Author
    Write-Log ('STATUS: FAIL ' + $Auditor + '-not-found')
    exit 1
}
if ($Auditor -eq 'codex' -and -not (Test-Path -LiteralPath (Join-Path $CodexHome 'auth.json'))) {
    Write-Log ('audit codex home not logged in: ' + $CodexHome)
    Append-Section -Body ('codex-home-not-authenticated: ' + $CodexHome) -Failed $true -AuditorName $Auditor -AuthorName $Author
    Write-Log 'STATUS: FAIL codex-home-not-authenticated'
    exit 1
}

# Process-scoped only. The audit runs on the API key; JJ's ~/.codex is untouched.
if ($Auditor -eq 'codex') {
    $env:CODEX_HOME = $CodexHome
    Write-Log ('CODEX_HOME=' + $CodexHome)
}

$prompt = (Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8).
    Replace('{{RULES}}',  $Rules).
    Replace('{{REPORT}}', $Report)

$tmp        = [System.IO.Path]::GetTempPath()
$promptPath = Join-Path $tmp ('jj-crossverify-prompt-' + $PID + '.txt')
$answerPath = Join-Path $tmp ('jj-crossverify-answer-' + $PID + '.txt')
$stdoutPath = Join-Path $tmp ('jj-crossverify-out-' + $PID + '.txt')
$stderrPath = Join-Path $tmp ('jj-crossverify-err-' + $PID + '.txt')
Write-Utf8 -Path $promptPath -Text $prompt

Write-Log ($Auditor + ' exec start (timeout ' + $TimeoutSec + 's)')
$failure = $null
$code = $null

if ($Auditor -eq 'codex') {
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
    # codex is a .cmd shim; Start-Process -PassThru returns $null for it, so the
    # process never launches. Invoke it directly and pipe the prompt on stdin, with
    # a background job supplying the timeout.
    $job = Start-Job -ScriptBlock {
        param($bin, $binArgs, $promptPath, $stdoutPath, $stderrPath, $codexHome)
        # Set explicitly rather than relying on the job process inheriting it.
        $env:CODEX_HOME = $codexHome
        $text = Get-Content -LiteralPath $promptPath -Raw -Encoding UTF8
        $text | & $bin @binArgs 1> $stdoutPath 2> $stderrPath
        $LASTEXITCODE
    } -ArgumentList $Bin, $codexArgs, $promptPath, $stdoutPath, $stderrPath, $CodexHome
} else {
    # claude -p, read-only by tool allowlist. --permission-mode default is the
    # real gate here: under acceptEdits the allowlist does NOT stop Edit/Write
    # (charter section 4, measured 2026-08-25), and an auditor that can write is
    # not an auditor. --add-dir covers an artifact that lives outside HQ, e.g. a
    # PR diff parked in the scratchpad.
    #
    # No headroom proxy: this direction has no scheduled trigger (the artifact is
    # a codex PR, audited from a session JJ started). Wire it in if that changes.
    . (Join-Path $Hq 'scripts\native-arg.ps1')
    $addDirs = @()
    foreach ($p in @($Report, $Rules)) {
        $d = Split-Path -Parent $p
        if ($d -and ($addDirs -notcontains $d)) { $addDirs += $d }
    }
    $claudeArgs = @(
        '-p', (ConvertTo-NativeArg $prompt),
        '--permission-mode', 'default',
        '--allowed-tools', 'Read', 'Glob', 'Grep'
    )
    foreach ($d in $addDirs) { $claudeArgs += @('--add-dir', $d) }
    $job = Start-Job -ScriptBlock {
        param($bin, $binArgs, $hq, $answerPath, $stderrPath)
        # PS 5.1 decodes a native program's stdout with [Console]::OutputEncoding,
        # which is the system ANSI codepage (cp949 here) - the auditor answers in
        # Korean, so without this the verdict lands in the report as mojibake and
        # nobody can read the findings. Measured 2026-09-11 on the first real run.
        # The codex branch never hit this: it reads codex's own -o answer FILE.
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8
        Set-Location -LiteralPath $hq
        $out = & $bin @binArgs 2> $stderrPath
        [System.IO.File]::WriteAllText($answerPath, ($out -join "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
        $LASTEXITCODE
    } -ArgumentList $Bin, $claudeArgs, $Hq, $answerPath, $stderrPath
}

if (Wait-Job $job -Timeout $TimeoutSec) {
    $code = Receive-Job $job
    Write-Log ($Auditor + ' exit code ' + $code)
} else {
    Stop-Job $job
    $failure = $Auditor + '-timeout (' + $TimeoutSec + 's)'
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
        $failure = if ($code) { $Auditor + '-exit-' + $code } else { $Auditor + '-empty-answer' }
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
    Write-Log ($Auditor + ' failed: ' + $failure + $hint)
    Append-Section -Body $failure -Failed $true -AuditorName $Auditor -AuthorName $Author
    Write-Log ('STATUS: FAIL ' + $failure)
} else {
    Append-Section -Body $answer.Trim() -Failed $false -AuditorName $Auditor -AuthorName $Author
    $verdict = ($answer.Trim() -split "`n")[0].Trim()
    Write-Log ($Auditor + ' verdict: ' + $verdict)
    Write-Log ('appended to: ' + $Report)
    Write-Log 'STATUS: OK'
}

foreach ($f in @($promptPath, $answerPath, $stdoutPath, $stderrPath)) {
    Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
}

if ($failure) { exit 1 }
exit 0
