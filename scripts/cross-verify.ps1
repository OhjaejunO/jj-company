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
# Auth: split by design - the audit gets its OWN config dir via CODEX_HOME and
# never shares a login with JJ's interactive sessions.
#
# 2026-10-05 (infra backlog 31, JJ chose "subscription, not paid credits"): the
# default home is ~/.codex-xverify, a home that holds ONE ChatGPT login of its
# own, and the default model is gpt-6-astra. Why not the home that was there:
#   ~/.codex-jjcompany (API key) - "Quota exceeded" since 2026-09-18, re-measured
#     2026-10-05. Kept as it was; -CodexHome reaches it if credits come back.
#   ~/.codex (JJ's own) - its refresh token was revoked (refresh_token_invalidated,
#     2026-10-05), AND Orca keeps a byte-identical copy of its auth.json in
#     %APPDATA%\orca\codex-runtime-home\home (same sha256, measured). A ChatGPT
#     refresh rotates the token, so two homes holding one token cannot both stay
#     valid: an audit that refreshed in ~/.codex would log Orca out, or the other
#     way round. The old line "~/.codex keeps JJ's auth untouched" held only
#     while the audit stayed OUT of that home - and that is still the rule.
#   Orca's per-account homes are JJ's interactive logins themselves. Same answer.
# A separate `codex login` in ~/.codex-xverify is its own session with its own
# refresh token, so nothing it refreshes is held anywhere else.
#
# CODEX_HOME is set on THIS PROCESS ONLY - it never leaks to the parent shell or
# to JJ's interactive sessions. Do not move it to a user-scope variable.
#
# -CodexHome / -Model (2026-09-25). The choice lives in the param defaults below
# and NOWHERE ELSE: the scheduled wrappers pass neither, and the re-run command
# in a failure section echoes the values this run actually used. One place to
# change means no wrapper can drift back to a dead home (charter section 0,
# layer 1). Until the login exists the run stops on codex-home-not-authenticated
# - a named failure, and scripts\run_audit.py carries it to the session brief.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as
# the system ANSI codepage. All Korean text lives in scripts\prompts\*.md and is
# read as explicit UTF-8.
#
# WHAT THIS STILL CANNOT MEASURE (charter section 0, layer 4)
#   The lag guard below answers ONE question: "is $Hq's main BEHIND origin/main".
#   Not "equal to" - an AHEAD main, a detached or wrong HEAD, and a dirty working
#   tree all read as fine while the auditor sees different bytes.
#   It also does NOT answer "is the auditor reading the branch under audit".
#   $Hq is main; a PR's code is not in main until it merges, so an audit of a PR
#   branch still reads past it. The other half of the 2026-09-12 misread ("the
#   base is not main") sits exactly there. Fixing it means unpinning $Hq - a
#   separate change, backlog C-57.
#
# SELF-TEST
#   powershell -File scripts\cross-verify.ps1 -SelfTest
#   Deterministic only (no model calls): rules/author resolution, the
#   author!=auditor refusal in BOTH directions, template substitution, the
#   codex command line with and without -Model (and the Windows sandbox pair in
#   both), the stderr failure hint, the
#   bytes the live codex job puts on stdin (UTF-8, against a control that shows
#   the old '?'), and the home isolation guard - as a function and in the
#   program. Axis 6a hashes the REAL interactive auth.json files (hash only).

param(
    [string]$Report,
    [string]$Rules,
    [ValidateSet('codex', 'claude')][string]$Auditor = 'codex',
    [ValidateSet('codex', 'claude')][string]$Author,
    [int]$TimeoutSec = 600,
    # The repository the auditor is pointed at (`codex exec -C $Hq`) AND the one
    # the lag guard measures - one value, so the guard cannot end up checking a
    # different tree than the auditor reads. It is a parameter so the self-test
    # can run this script end to end against a repository that is deliberately
    # behind; without that the axes below measure a FUNCTION while the live call
    # site goes unmeasured (round-4 audit, measured).
    [string]$Hq = 'C:\Users\ojaej\jj-company',
    # The codex config dir the audit runs under (process-scoped CODEX_HOME, see
    # the header for why it is this one and not ~/.codex).
    [string]$CodexHome = 'C:\Users\ojaej\.codex-xverify',
    # codex --model. Pass -Model '' to send no --model at all and let codex pick.
    [string]$Model = 'gpt-6-astra',
    # MORE folders of Orca-style account homes to guard against. It ADDS to the
    # real Orca accounts folder ($ORCA_CODEX_ACCOUNTS), which is always listed -
    # it cannot remove or replace it. Exists so the self-test can run this
    # program against a folder whose listing is denied. (The first version took
    # the real folder's place, so a path that does not exist dropped every real
    # account from the guard - Codex recheck 2026-10-06.)
    [string[]]$ExtraOrcaAccounts = @(),
    [switch]$SelfTest
)

$ErrorActionPreference = 'Continue'

$Task      = 'cross-verify'
$Codex     = 'C:\Users\ojaej\AppData\Roaming\npm\codex.cmd'
$Claude    = 'C:\Users\ojaej\.local\bin\claude.exe'

$MODEL_LABEL = @{ 'codex' = 'codex default'; 'claude' = 'claude -p default' }

# The lag self-test builds real temp repos, and the environment decides WHICH
# repository and WHICH config a `git` call touches - those variables OUTRANK
# `git -C <path>`.
#
# THIS IS A PATTERN, NOT A LIST, and that is deliberate. Two audit rounds spent
# themselves naming variables a list had missed - GIT_CONFIG_PARAMETERS, then
# GIT_SHALLOW_FILE (measured: HEAD unchanged, commit count 635 -> 1),
# GIT_TEMPLATE_DIR (git init copies hooks out of it), GIT_GRAFT_FILE,
# GIT_REPLACE_REF_BASE. An enumeration of a vendor's variables is never finished
# and each new git release can extend it; "everything with this prefix" is.
#
# HOME and XDG_CONFIG_HOME are not GIT_-prefixed but still redirect which global
# config is read (measured, round 3). Rather than clear those - other things in
# this process need HOME - the temp-repo work is made HERMETIC: config is pinned
# to files that do not exist, so no user or system config is consulted at all.
$LAG_GIT_ENV_PREFIX = 'GIT_'
$LAG_GIT_ENV_ALLOWED = @('GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM', 'GIT_CONFIG_NOSYSTEM')

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

# Every line carries this run's pid inside the time bracket. One day's log holds
# several runs, and two can overlap (A start, B start, A STATUS, B STATUS): by
# position alone scripts\run_audit.py would hang both STATUS lines on B and read
# A as a run that died without one (Codex audit 2026-10-06). The bracket keeps
# run_audit's '^\[[^\]]+\] STATUS:' shape; it pairs by ' pid N]'.
function Write-Log {
    param([string]$Message)
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' pid ' + $PID + '] ' + $Message
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

    # The header's model label follows -Model, so an override run does not say
    # "codex default" above a run line that names another model. Without
    # -Model it is the same label as before.
    $modelLabel = if ($AuditorName -eq 'codex' -and $Model) { 'codex --model ' + $Model } else { $MODEL_LABEL[$AuditorName] }

    $text = $template.
        Replace('{{TIME}}',     (Get-Date -Format 'yyyy-MM-dd HH:mm')).
        Replace('{{AUDITOR}}',  $AuditorName).
        Replace('{{AUTHOR}}',   $(if ($AuthorName) { $AuthorName } else { 'unknown' })).
        Replace('{{MODEL}}',    $modelLabel).
        Replace('{{RULES}}',    $Rules).
        Replace('{{REPORT}}',   $Report).
        Replace('{{RERUN_ARGS}}', (Get-RerunArgs -AuditorName $AuditorName -HomeDir $CodexHome -ModelName $Model)).
        Replace('{{BODY}}',     $Body)

    # Which codex home and model this run was configured with: one line, in the
    # pass half and the failure half alike, and the same string the log gets.
    # A code span, so markdown does not eat the backslashes in the path.
    if ($AuditorName -eq 'codex') {
        $text = $text.TrimEnd() + "`r`n`r`n" + 'codex run: `' + (Get-CodexRunLine -HomeDir $CodexHome -ModelName $Model) + '`'
    }

    Append-Utf8 -Path $Report -Text ($text.TrimEnd() + "`r`n")
}

# --- codex invocation -----------------------------------------------------------
#
# The codex command line, built in ONE place so the self-test measures the array
# the live call hands to codex. Without -Model it is exactly the list this script
# always passed plus the Windows sandbox pair (self-test axis 6 compares it
# element by element). --model goes before '-': that is the positional "read
# the prompt from stdin" and stays last.
#
# windows.sandbox=unelevated (2026-10-05). Without a Windows sandbox configured,
# codex on Windows cannot enforce read-only, so with exec's approval "never"
# EVERY shell command is "Rejected ... blocked by policy" - the auditor cannot
# read the rules or the report and answers "cannot confirm". That is the
# 2026-09-10..17 no-verdict streak. Measured 2026-10-05 in ~/.codex-xverify, same
# prompt, one flag apart: without it the read was blocked by policy; with it the
# read returned CLAUDE.md's first line, and a write in the same sandbox failed
# with PermissionDenied (no file created). unelevated = restricted token, no
# admin setup; 'elevated' would need a one-time UAC setup per machine. Passed
# here and not in the home's config.toml so the choice stays in this repo.
# Unquoted on purpose: codex reads a value that is not valid TOML as a literal
# string, and an embedded '"' would not survive PS 5.1 -> codex.cmd.
function Get-CodexArgs {
    param([string]$Repo, [string]$AnswerPath, [string]$ModelName)
    $a = @(
        'exec',
        '-C', $Repo,
        '--sandbox', 'read-only',
        '-c', 'windows.sandbox=unelevated',
        '--skip-git-repo-check',
        '-o', $AnswerPath
    )
    if ($ModelName) { $a += @('--model', $ModelName) }
    $a += '-'
    return $a
}

# The job that runs codex. ONE scriptblock, used by the live call AND by self-test
# axis 8, so the test measures the block that runs rather than a copy of it.
#
# The prompt goes to codex on stdin, and PS 5.1 encodes a string piped to a
# native program with $OutputEncoding - which defaults to ASCII. Measured
# 2026-09-25 (infra backlog 31): every Hangul character of every audit prompt
# reached codex as '?' (codex's own session record: 0 Hangul, 421 '?'), so the
# audits that did return a verdict judged a prompt with its instructions erased.
# UTF-8 WITHOUT a BOM: a BOM would land in front of the first word of the prompt.
$CodexJobBlock = {
    param($bin, $binArgs, $promptPath, $stdoutPath, $stderrPath, $codexHome)
    # Set explicitly rather than relying on the job process inheriting it.
    $env:CODEX_HOME = $codexHome
    $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $text = Get-Content -LiteralPath $promptPath -Raw -Encoding UTF8
    $text | & $bin @binArgs 1> $stdoutPath 2> $stderrPath
    $LASTEXITCODE
}

# One line naming the codex home and model. Path and model name only - never
# anything read out of the home itself. The log and the appended section both
# take this string, so the two cannot disagree about what ran.
function Get-CodexRunLine {
    param([string]$HomeDir, [string]$ModelName)
    $m = if ($ModelName) { $ModelName } else { '(codex default)' }
    return ('CODEX_HOME=' + $HomeDir + ' | model=' + $m)
}

# --- codex home isolation -------------------------------------------------------
#
# The header's "the audit never shares a login with JJ's interactive sessions",
# made a check instead of a sentence. Two ways to share, two answers:
#   codex-home-interactive  -CodexHome IS one of JJ's interactive homes.
#   codex-home-shared-login -CodexHome is elsewhere but its auth.json is a
#                           byte-for-byte copy of one of theirs. Measured
#                           2026-10-05: Orca's runtime home held exactly such a
#                           copy of ~/.codex/auth.json. The tempting quick fix
#                           for a dead audit login - copy a live auth.json over -
#                           is this case, and it would log JJ out on the next
#                           token refresh.
#   codex-home-isolation-unknown - an auth.json could not be hashed, or the
#                           Orca accounts folder could not be listed; not
#                           compared is not a pass.
# Paths and SHA-256 only; no auth file is ever read for its content.
# NOT CAUGHT (charter section 0, layer 4): a copy that has since diverged (one
# side refreshed - by then one of the two is already dead), and interactive homes
# that are not on this list.
$INTERACTIVE_CODEX_HOMES = @(
    'C:\Users\ojaej\.codex',
    'C:\Users\ojaej\AppData\Roaming\orca\codex-runtime-home\home'
)

$ORCA_CODEX_ACCOUNTS = 'C:\Users\ojaej\AppData\Roaming\orca\codex-accounts'

# Orca's account homes: the real folder ALWAYS, plus any extra folders. A listing
# that FAILS throws: it used to be swallowed (-ErrorAction SilentlyContinue), and
# a folder whose listing is denied while its files stay readable by path
# (measured: an RD deny ACE does exactly that) then shrank the list to nothing -
# an account home passed as "isolated" (Codex audit 2026-10-06). A folder that
# does not exist is not an error: no accounts there.
# NOT CAUGHT (layer 4): Test-Path also answers "no" when the real folder's
# existence itself cannot be checked; that reads as "no Orca accounts".
function Get-InteractiveCodexHomes {
    param([string[]]$ExtraAccountsDirs)
    $h = @($INTERACTIVE_CODEX_HOMES)
    foreach ($dir in @($ORCA_CODEX_ACCOUNTS) + @($ExtraAccountsDirs | Where-Object { $_ })) {
        if (Test-Path -LiteralPath $dir) {
            $h += @(Get-ChildItem -LiteralPath $dir -Directory -ErrorAction Stop |
                ForEach-Object { Join-Path $_.FullName 'home' })
        }
    }
    return $h
}

# The one call both the run and self-test 6a make: the list, then the check. A
# list that could not be built is UNKNOWN - not compared is not a pass.
function Get-CodexHomeIsolation {
    param([string]$HomeDir, [string[]]$ExtraAccountsDirs)
    try { $ix = @(Get-InteractiveCodexHomes -ExtraAccountsDirs $ExtraAccountsDirs) } catch { return 'codex-home-isolation-unknown' }
    return (Test-CodexHomeIsolation -HomeDir $HomeDir -Interactive $ix)
}

# $null when isolated, else a STATUS token. The interactive list is a parameter
# so the self-test can hand it temp directories.
function Test-CodexHomeIsolation {
    param([string]$HomeDir, [string[]]$Interactive)
    $norm = { param($p) [System.IO.Path]::GetFullPath($p).TrimEnd('\') }
    $mine = & $norm $HomeDir
    foreach ($i in @($Interactive)) {
        if ($i -and ((& $norm $i) -ieq $mine)) { return 'codex-home-interactive' }
    }
    $myAuth = Join-Path $HomeDir 'auth.json'
    if (-not (Test-Path -LiteralPath $myAuth)) { return $null }
    # A file that cannot be hashed is UNKNOWN, not "different" - the same rule
    # as lag-unknown above: not compared is not a pass.
    try {
        $myHash = (Get-FileHash -LiteralPath $myAuth -Algorithm SHA256 -ErrorAction Stop).Hash
        foreach ($i in @($Interactive)) {
            if (-not $i) { continue }
            $a = Join-Path $i 'auth.json'
            if ((Test-Path -LiteralPath $a) -and
                ((Get-FileHash -LiteralPath $a -Algorithm SHA256 -ErrorAction Stop).Hash -eq $myHash)) {
                return 'codex-home-shared-login'
            }
        }
    } catch {
        return 'codex-home-isolation-unknown'
    }
    return $null
}

# The tail of the re-run command in a failure section: the home and model THIS
# run used, so a manual retry reproduces it instead of quietly going back to
# whatever the defaults say on the day it is pasted (infra backlog 31: before
# this, the command carried neither and re-ran on the dead API-key home).
# Nothing for -Auditor claude - those two parameters do not steer it.
function Get-RerunArgs {
    param([string]$AuditorName, [string]$HomeDir, [string]$ModelName)
    if ($AuditorName -ne 'codex') { return '' }
    return (' -CodexHome "' + $HomeDir + '" -Model "' + $ModelName + '"')
}

# The failure hint that goes into the log.
#
# Measured 2026-09-25: from 2026-09-18 every scheduled run logged only
# "codex.cmd : OpenAI Codex v0.154.0". That is the version banner, which is
# always the FIRST stderr line, while the cause ("ERROR: stream disconnected
# before completion: You have no credits remaining...") sat further down - so
# eight days of failures carried no reason.
#
# Rule: the LAST line that is an "ERROR:" line, else the last non-empty line.
# Last, not first - measured the same day on a real failing run (a fake key in
# a scratch CODEX_HOME, same job shape): codex prints retry notices first,
# "ERROR: Reconnecting... 1/5" to "5/5", and the terminal cause ("ERROR:
# unexpected status 401 Unauthorized: ...") after them, so the first ERROR:
# line is a retry notice. The last non-empty line is no better: PS wraps long
# stderr lines in the file, so it is the tail of a wrapped message.
# PS 5.1 also prefixes the first stderr line of a native command with
# "<command> : " and follows it with its own error-record lines, so that prefix
# is allowed in front of ERROR:. The match is case-insensitive on purpose: a
# usage error from codex's argument parser reads "error:".
#
# Charter section 6: the old "first line only" was there so a secret-bearing
# payload could not reach the log. A deeper line gives that up - the 401 line
# above quotes the key, masked by OpenAI to its first and last characters - so
# sk- key shaped tokens are masked here before anything is returned, and the
# 200 character cap stays. NOT HANDLED (charter section 0, layer 4): other
# secret shapes.
function Get-StderrHint {
    param([string[]]$Lines)
    $pick = $null
    foreach ($l in @($Lines)) {
        $s = ([string]$l).Trim()
        if ($s -match '^(?:\S+ : )?(ERROR:.*)$') { $pick = $Matches[1] }
    }
    if ($null -eq $pick) {
        foreach ($l in @($Lines)) {
            $s = ([string]$l).Trim()
            if ($s) { $pick = $s }
        }
    }
    if (-not $pick) { return '' }
    $pick = $pick -replace '\bsk-[A-Za-z0-9_\-\*]{8,}', 'sk-<redacted>'
    $pick = $pick -replace '[\r\n]+', ' '
    if ($pick.Length -gt 200) { $pick = $pick.Substring(0, 200) }
    return $pick
}

# --- HQ lag ------------------------------------------------------------------
#
# The auditor reads its evidence from $Hq. Charter section 2 pins the operations
# server to "refreshed by git pull only", so $Hq being BEHIND origin/main is its
# normal resting state, not an anomaly - and an auditor pointed at a stale tree
# answers about code that no longer exists.
#
# 2026-09-12: the audit read gate_on_stop.py out of a lagging $Hq, found no
# newest_mtime, and filed a red finding. The function was sitting in the PR
# branch the whole time. That is a FALSE red, and charter section 0 names the
# cost: false alarms blunt the watch.
#
# This is lifted from check-repo-guard.ps1 (the same comparison charter section 3
# already makes a session run) rather than invented here. The fetch happens at
# call time so the verdict is about the remote as it is NOW.
#
# It STOPS instead of writing the warning into the prompt. Both are layer 3 of
# the 4-layer clause - this is a check, not a structural fix - but a check that
# refuses is worth more than one that hopes the model notices a note. Layer 1
# here would be not pinning $Hq at all, which is backlog C-57 and a separate
# change.
#
# WHAT IT DOES NOT ASK. Only "is $Hq behind origin/main". An AHEAD main, a
# detached or wrong HEAD, and a dirty working tree all pass while the auditor
# still reads bytes that are not origin/main. Those are open, and named in C-57.
function Get-BehindCount {
    param([string]$Repo, [string]$LocalRef, [string]$RemoteRef)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $n = (& git -C $Repo rev-list --count ($LocalRef + '..' + $RemoteRef) 2>$null)
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($rc -ne 0 -or [string]::IsNullOrWhiteSpace($n)) { return $null }
    return [int]($n.Trim())
}

# Returns $null when main is NOT BEHIND origin/main, else a STATUS token.
# "Not behind" is all it means - not "current", not "the same bytes".
# A fetch that did not run is 'lag-unknown', NOT a pass: an uncompared tree is
# unknown, and answering "not behind" from stale refs is the failure this exists
# to catch.
function Test-RepoLag {
    param(
        [string]$Repo,
        [string]$LocalRef = 'main',
        [string]$RemoteRef = 'origin/main'
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & git -C $Repo fetch --quiet origin main *>&1 | Out-Null
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($rc -ne 0) { return 'lag-unknown' }

    $behind = Get-BehindCount -Repo $Repo -LocalRef $LocalRef -RemoteRef $RemoteRef
    if ($null -eq $behind) { return 'lag-unknown' }
    if ($behind -gt 0) { return ('hq-behind-' + $behind) }
    return $null
}

# THE ONLY WAY TO GET AN AUDITOR BINARY.
#
# The lag check lives inside this function rather than above its call site, and
# that is the whole point: "the guard runs before the auditor" stops being an
# ordering somebody has to keep and becomes something with no other path.
#
# The earlier shape put the check above the call and had the self-test read this
# file to confirm the ordering. A lexical check cannot survive contact: the
# round-3 audit (2026-09-13) disabled the guard with
#   $lag = $false -and (Test-RepoLag -Repo $Hq)   # LAGGUARD-CALLSITE
# which short-circuits the call away while every marker and ordering assertion
# stayed green. Reading source is not evidence that code RAN. This function is
# called with a real lagging repo by self-test axis f instead.
#
# Throws 'hq-lag:<token>'; returns the binary path when the tree is usable.
function Resolve-AuditorBinary {
    param([string]$Auditor, [string]$Repo)
    $lag = Test-RepoLag -Repo $Repo
    if ($lag) { throw ('hq-lag:' + $lag) }
    if ($Auditor -eq 'codex') { return $Codex }
    return $Claude
}

# Turns whatever Resolve-AuditorBinary threw into a STATUS token and a report
# body. Only an 'hq-lag:' message is a lag verdict: anything else thrown in
# there is a DIFFERENT failure, and dressing it up as "your tree is behind"
# would send the reader to run a pull that fixes nothing. A wrong diagnosis is
# worse than none (charter section 0). The token is flattened to one line so a
# stray multi-line message cannot forge extra STATUS lines in the log.
function Get-LagCatchVerdict {
    param([string]$Message, [string]$Repo)
    if ($Message -like 'hq-lag:*') {
        $token = $Message.Substring(7)
        return @{ Token = ($token -replace '[\r\n]+', ' '); Body = (Get-LagFailureBody -Lag $token -Repo $Repo) }
    }
    return @{
        Token = 'lag-check-error'
        Body  = ('lag-check-error: the pre-audit check on ' + $Repo + ' did not complete, so nothing is known ' +
                 'about whether it is current. This is NOT a lag verdict. Underlying failure: ' + $Message)
    }
}

# The failure body is built HERE, not inline at the call site, so the self-test
# can measure it. Charter section 3: a guard that blocks without naming the way
# out sends the next session looking for a bypass.
function Get-LagFailureBody {
    param([string]$Lag, [string]$Repo)
    $recover = 'git -C "' + $Repo + '" pull --ff-only origin main'
    if ($Lag -eq 'lag-unknown') {
        return ('hq-lag-unknown: could not compare ' + $Repo + ' with origin/main (fetch failed - offline?). ' +
                'Not compared is not "up to date": the audit would read whatever the tree happens to hold. Run: ' + $recover)
    }
    return ('hq-behind: ' + $Repo + ' lags origin/main (' + $Lag + '). Charter section 2 refreshes the operations ' +
            'server by pull only, so the auditor would read code that is no longer current and file findings against ' +
            'it (2026-09-12: a false red on a function that existed in the PR branch). Run: ' + $recover)
}

# --- self-test ----------------------------------------------------------------
#
# What it measures, and why each half exists (charter section 0): a check that
# only shows the guard FIRING cannot tell a working guard from one that refuses
# everything. So every case here has its opposite next to it.
# 'pass' / 'findings' for an answer that actually judged, $null for one that did
# not. The contract is the prompt's own output format (scripts\prompts\cross-verify.md):
# first line is exactly PASS, or "FINDINGS: <count>". Nothing else is a verdict -
# not a "cannot review" sentence, not an apology, not an empty answer.
#
# Deliberately strict about the COUNT: "FINDINGS:" with no number is a half-written
# header, and accepting it would let a truncated answer read as a real audit.
function Get-VerdictKind {
    param([string]$FirstLine)
    $s = ([string]$FirstLine).Trim()
    if ($s -eq 'PASS') { return 'pass' }
    if ($s -match '^FINDINGS:\s*\d+') { return 'findings' }
    return $null
}

function Invoke-SelfTest {
    $fails = @()
    function t { param([string]$Name, [bool]$Ok, [string]$Got)
        if ($Ok) { Write-Host ('  OK   ' + $Name) }
        else { Write-Host ('  FAIL ' + $Name + '  got: ' + $Got); $script:stFails++ }
    }
    $script:stFails = 0

    # An Orca-accounts stand-in with one account home that holds a login. With
    # -DenyList the folder gets a deny ACE for "list folder" (RD) for the current
    # user: listing it fails while files inside stay readable by full path -
    # exactly the hole the 2026-10-06 audit named. Unlock-AccountsFixture removes
    # the ACE (in a finally) so the temp folder can be deleted.
    function New-AccountsFixture {
        param([string]$Root, [switch]$DenyList)
        $acct = Join-Path $Root 'codex-accounts'
        $homeDir = Join-Path $acct 'acct-1\home'
        New-Item -ItemType Directory -Force -Path $homeDir | Out-Null
        Write-Utf8 -Path (Join-Path $homeDir 'auth.json') -Text '{"fake":"orca account login"}'
        if ($DenyList) {
            $me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            & icacls.exe $acct /deny ($me + ':(RD)') | Out-Null
        }
        return @{ Dir = $acct; Home = $homeDir }
    }
    function Unlock-AccountsFixture {
        param([string]$Dir)
        $me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls.exe $Dir /remove:d $me | Out-Null
    }

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
                Replace('{{RERUN_ARGS}}', '').Replace('{{BODY}}', 'B')
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

    # 5. the HQ lag guard. Three axes, and the middle one is the point: a check
    #    that only ever fires looks identical to a correct one until you feed it
    #    the input it must stay QUIET on. Real repos on disk, no network - a fake
    #    return value would measure the test, not the comparator.
    $lagRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('jj-crossverify-lag-' + $PID + '-' + (Get-Date).Ticks)
    function New-LagRepo {
        param([string]$Root, [string]$Name, [int]$Commits, [switch]$BreakOrigin, [switch]$Behind)
        $bare = Join-Path $Root ($Name + '.git')
        $work = Join-Path $Root $Name

        # GUARD 1 - BEFORE the first git call. `git init` with GIT_DIR set
        # re-initialises the REAL repository, so a guard that waits for a repo to
        # exist is already too late; the check has to be on the environment.
        # `git -C <path>` LOSES to these variables, and this self-test runs from
        # pre-commit (charter section 3 registers it there), where git exports
        # them into the hook process. Measured 2026-09-13: without this the
        # temp-repo commits landed on the real branch, the plain 'git init'
        # below turned it into a BARE repository (with GIT_DIR set and no work
        # tree, that is what init does), 'branch -M main' clobbered main, and
        # 'push origin main' sent all of it to GitHub.
        $leftover = @(Get-ChildItem Env: |
            Where-Object { $_.Name -like ($LAG_GIT_ENV_PREFIX + '*') -and ($LAG_GIT_ENV_ALLOWED -notcontains $_.Name) } |
            ForEach-Object { $_.Name })
        if ($leftover.Count -gt 0) {
            throw ('lag self-test refused: git environment still set: ' + ($leftover -join ','))
        }

        & git init -q $work 2>$null | Out-Null

        # GUARD 2 - the repo git actually resolves to must be the one just made.
        # --show-toplevel alone is not the whole answer: GIT_DIR together with
        # GIT_WORK_TREE can make the work tree match while the git dir - which
        # holds the config, refs and objects the incident damaged - is somewhere
        # else. So both halves are checked.
        #
        # NOT PROVEN (charter section 0, layer 4): no self-test axis reaches
        # the git-dir half, because guard 1 refuses before anything gets this
        # far. Sabotaging only that half leaves every axis green (measured
        # 2026-09-13). It is depth under guard 1, not a measured check, and it is
        # written down here rather than counted as one.
        $want    = (Resolve-Path -LiteralPath $work).Path
        $wantGit = (Join-Path $want '.git')
        $top     = & git -C $work rev-parse --show-toplevel 2>$null
        $gitDir  = & git -C $work rev-parse --absolute-git-dir 2>$null
        if (-not $top -or ((Resolve-Path -LiteralPath ($top.Trim())).Path -ne $want)) {
            throw ('lag self-test refused: work tree of ' + $work + ' resolves to ' + $top)
        }
        if (-not $gitDir -or ((Resolve-Path -LiteralPath ($gitDir.Trim())).Path -ne $wantGit)) {
            throw ('lag self-test refused: git dir of ' + $work + ' resolves to ' + $gitDir)
        }

        & git -C $work config user.email 'selftest@local' 2>$null | Out-Null
        & git -C $work config user.name  'selftest'       2>$null | Out-Null
        for ($i = 1; $i -le $Commits; $i++) {
            & git -C $work commit -q --allow-empty -m ('c' + $i) 2>$null | Out-Null
        }
        & git -C $work branch -q -M main 2>$null | Out-Null
        # clone rather than 'init --bare $bare': a hijacked 'init' reaches the
        # real repository before any repo-shaped guard can look at it, and the
        # --bare form would also plant core.bare there. Cloning an
        # ALREADY-VERIFIED work tree has no such reach.
        & git clone -q --bare $work $bare 2>$null | Out-Null
        & git -C $work remote add origin $bare 2>$null | Out-Null
        & git -C $work push -q origin main 2>$null | Out-Null
        if ($BreakOrigin) {
            # Push FIRST, then break the URL. A repo that never had a remote also
            # has no origin/main ref, so rev-list fails on its own and the case
            # would pass with the fetch check DELETED - it would prove nothing.
            # Here the stale origin/main still resolves and reads "0 behind", so
            # only the fetch return code can tell that the answer is unknown.
            & git -C $work remote set-url origin (Join-Path $Root 'no-such-remote.git') 2>$null | Out-Null
        }
        if ($Behind) {
            # Push everything, then walk the local branch back one commit, so
            # main is genuinely behind origin/main the way a stale operations
            # server is. update-ref, not reset: nothing here has a work tree
            # state worth disturbing.
            & git -C $work update-ref refs/heads/main (& git -C $work rev-parse main~1 2>$null) 2>$null | Out-Null
        }
        return $work
    }
    # Fingerprint enough of a repository that a hijack cannot hide in the gap.
    # HEAD alone is not enough: the 2026-09-13 incident changed core.bare and the
    # origin URL, and an "untouched" verdict that reads only HEAD would have
    # called that clean.
    # A fingerprint that read NOTHING is not evidence of anything. Every git call
    # below hides its stderr, so a repository that has been destroyed outright
    # answers with empty strings - and two destroyed repositories then compare
    # EQUAL, which would render "left untouched" as a pass over rubble. The
    # caller checks this before believing a comparison. (Round-2 audit,
    # 2026-09-13: the first version had exactly that hole.)
    function Test-FingerprintUsable {
        param([string]$Fingerprint)
        # Any field git could not answer is stamped, so a PARTIAL reading is
        # refused too, not just an all-empty one.
        #
        # NOT PROVEN (charter section 0, layer 4): every partially-broken repo we
        # can actually build fails the HEAD test below as well - break object
        # access and HEAD itself becomes UNREADABLE - so deleting this line
        # leaves the self-test green (measured 2026-09-13). It stays because it
        # is the correct predicate for a field that fails while HEAD survives,
        # but it is depth, not a measured check, and it is written down as such
        # rather than counted.
        #
        # THE SAME IS TRUE OF THE `cat-file -e` PROBE BELOW, in the other
        # direction, and the two cover for each other (round-4 audit, measured
        # 2026-09-13): delete the probe and a broken repo is still refused,
        # because a missing HEAD object also kills `rev-list --count` and that
        # field is stamped UNREADABLE. Neither is proven NECESSARY, and no input
        # we can build separates them - anything that hides an object from
        # cat-file also stops the walk. They answer different lies (a hash for
        # an object that is not there, vs. a field git never answered) so both
        # stay, and this paragraph is the layer-4 record that the self-test does
        # not prove either one.
        if ($Fingerprint -like '*UNREADABLE*') { return $false }
        $head = ($Fingerprint -split '\|')[0]
        return ($head -match '^[0-9a-f]{40}$')
    }

    # Each field carries its own exit code. A field git FAILED to answer is not
    # an empty string next to five good ones - it is stamped UNREADABLE, because
    # "no answer" and "the answer is empty" are different facts and only the
    # second one may be compared. `config --get` legitimately exits 1 when a key
    # is simply absent, so that one exit code is not treated as a failure.
    function Get-RepoFingerprint {
        param([string]$Repo)
        function f {
            param([scriptblock]$Call, [int[]]$OkCodes = @(0))
            $out = & $Call
            if ($OkCodes -notcontains $LASTEXITCODE) { return 'UNREADABLE' }
            return ($out -join ',')
        }
        $head = f { & git -C $Repo rev-parse HEAD 2>$null }
        # rev-parse can hand back a well-formed hash for an object that is not
        # actually there; cat-file is what proves the repository can read it.
        if ($head -ne 'UNREADABLE') {
            & git -C $Repo cat-file -e ($head + '^{commit}') 2>$null
            if ($LASTEXITCODE -ne 0) { $head = 'UNREADABLE' }
        }
        return (@(
            $head,
            (f { & git -C $Repo rev-parse --abbrev-ref HEAD 2>$null }),
            (f { & git -C $Repo rev-list --count HEAD 2>$null }),
            (f { & git -C $Repo config --local --get core.bare 2>$null } @(0, 1)),
            (f { & git -C $Repo config --local --get remote.origin.url 2>$null } @(0, 1)),
            (f { & git -C $Repo for-each-ref --format='%(refname) %(objectname)' 2>$null })
        ) -join '|')
    }

    # Clear EVERY GIT_* variable - see the $LAG_GIT_ENV_PREFIX note for why this
    # is a prefix sweep and not a list - then pin config to files that do not
    # exist so HOME / XDG_CONFIG_HOME cannot steer what git reads either.
    # Removal is VERIFIED, not attempted: a Remove-Item that quietly failed would
    # leave the exact variable this block exists to get rid of.
    $gitEnvSaved = @{}
    foreach ($e in @(Get-ChildItem Env: | Where-Object { $_.Name -like ($LAG_GIT_ENV_PREFIX + '*') })) {
        $gitEnvSaved[$e.Name] = $e.Value
        Remove-Item -LiteralPath ('Env:' + $e.Name) -ErrorAction SilentlyContinue
    }
    $noConfig = Join-Path $lagRoot 'no-such-gitconfig'
    $env:GIT_CONFIG_GLOBAL   = $noConfig
    $env:GIT_CONFIG_SYSTEM   = $noConfig
    $env:GIT_CONFIG_NOSYSTEM = '1'
    $gitEnvStuck = @(Get-ChildItem Env: |
        Where-Object { $_.Name -like ($LAG_GIT_ENV_PREFIX + '*') -and ($LAG_GIT_ENV_ALLOWED -notcontains $_.Name) } |
        ForEach-Object { $_.Name })
    t 'lag: every GIT_* variable was actually cleared (not just asked to clear)' `
        ($gitEnvStuck.Count -eq 0) ($gitEnvStuck -join ',')
    try {
        New-Item -ItemType Directory -Force -Path $lagRoot | Out-Null

        # a/b share one repo because they ARE the two directions of one axis:
        # same comparator, opposite inputs, one commit apart by construction.
        $repoAB = New-LagRepo -Root $lagRoot -Name 'ab' -Commits 2
        $behindRef = Test-RepoLag -Repo $repoAB -LocalRef 'main~1'
        t 'lag: a ref that IS behind reads as behind' ($behindRef -eq 'hq-behind-1') ([string]$behindRef)
        $currentRef = Test-RepoLag -Repo $repoAB -LocalRef 'main'
        t 'lag: a current ref stays quiet (guard does not refuse everything)' ($null -eq $currentRef) ([string]$currentRef)

        # c gets its own repo: a broken remote in the a/b repo would also break
        # a/b, and then neither case would prove anything on its own.
        $repoC = New-LagRepo -Root $lagRoot -Name 'c' -Commits 1 -BreakOrigin
        $unknown = Test-RepoLag -Repo $repoC -LocalRef 'main'
        t 'lag: a failed fetch is lag-unknown, not a pass' ($unknown -eq 'lag-unknown') ([string]$unknown)

        # d. the two tokens must not render the same text, and both must carry
        #    the recovery command. The live FAIL path cannot be exercised here
        #    (it needs the operations server to actually lag), so the half that
        #    CAN be measured - what the reader is handed - is measured.
        $bBehind  = Get-LagFailureBody -Lag 'hq-behind-2' -Repo 'C:\hq'
        $bUnknown = Get-LagFailureBody -Lag 'lag-unknown' -Repo 'C:\hq'
        t 'lag body: behind names the recovery command'  ($bBehind  -match 'pull --ff-only origin main') $bBehind
        t 'lag body: unknown names the recovery command' ($bUnknown -match 'pull --ff-only origin main') $bUnknown
        t 'lag body: the two failures do not read alike' ($bBehind -ne $bUnknown) 'identical'
        t 'lag body: behind reports the count'           ($bBehind -match 'hq-behind-2') $bBehind

        # d2. the usability check needs its OWN case. No other axis produces a
        #     PARTIALLY readable repository, so without this one the check could
        #     be deleted and every axis would stay green (measured). The
        #     all-empty repo it was first built for is not the only way to read
        #     nothing: break object access and HEAD still looks like a hash.
        $repoH  = New-LagRepo -Root $lagRoot -Name 'h' -Commits 1
        $fpGood = Get-RepoFingerprint -Repo $repoH
        Remove-Item -LiteralPath (Join-Path $repoH '.git\objects') -Recurse -Force -ErrorAction SilentlyContinue
        $fpBroken = Get-RepoFingerprint -Repo $repoH
        t 'fingerprint: a healthy repo reads as usable' (Test-FingerprintUsable $fpGood) $fpGood
        t 'fingerprint: a partially readable repo is refused' (-not (Test-FingerprintUsable $fpBroken)) $fpBroken

        # d3. the hermetic config pin. HOME and XDG_CONFIG_HOME are not GIT_*, so
        #     the prefix sweep does not touch them; the pin is what stops an
        #     outside config being read. Point HOME at a planted .gitconfig and
        #     confirm a value from it does NOT reach a temp repo.
        $fakeHome = Join-Path $lagRoot 'fakehome'
        New-Item -ItemType Directory -Force -Path $fakeHome | Out-Null
        Write-Utf8 -Path (Join-Path $fakeHome '.gitconfig') -Text "[user]`n`tsigningkey = HIJACKED`n"
        $realHome = $env:HOME
        $env:HOME = $fakeHome
        # CONTROL FIRST. `-ne 'HIJACKED'` is also satisfied by git failing and
        # saying nothing at all, and "read nothing" is not "read and clean"
        # (the same mistake the fingerprint carries). So lift the pin and prove
        # the planted value DOES arrive; only then is its absence evidence.
        $pinnedG = $env:GIT_CONFIG_GLOBAL
        $pinnedN = $env:GIT_CONFIG_NOSYSTEM
        Remove-Item -LiteralPath 'Env:GIT_CONFIG_GLOBAL' -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath 'Env:GIT_CONFIG_NOSYSTEM' -ErrorAction SilentlyContinue
        $control = (& git -C $repoH config --get user.signingkey 2>$null)
        $env:GIT_CONFIG_GLOBAL   = $pinnedG
        $env:GIT_CONFIG_NOSYSTEM = $pinnedN
        $leaked = (& git -C $repoH config --get user.signingkey 2>$null)
        if ($null -eq $realHome) { Remove-Item -LiteralPath 'Env:HOME' -ErrorAction SilentlyContinue }
        else { $env:HOME = $realHome }
        t 'config: the planted HOME .gitconfig IS readable once the pin is lifted (control)' `
            ($control -eq 'HIJACKED') ([string]$control)
        t 'config: a planted HOME .gitconfig does not reach a temp repo' `
            ($leaked -ne 'HIJACKED') ([string]$leaked)

        # e. the net itself, and the axis this incident paid for. Put back the
        #    hook environment (GIT_DIR pointed at a decoy repo) and confirm the
        #    builder REFUSES instead of driving the decoy. Without this case the
        #    guard above is prose: nothing here would notice if it were deleted.
        $decoy = New-LagRepo -Root $lagRoot -Name 'decoy' -Commits 1
        $decoyBefore = Get-RepoFingerprint -Repo $decoy
        $env:GIT_DIR = (Join-Path $decoy '.git')
        $refused = $false
        try { New-LagRepo -Root $lagRoot -Name 'victim' -Commits 1 | Out-Null } catch { $refused = $true }
        Remove-Item -LiteralPath 'Env:GIT_DIR' -ErrorAction SilentlyContinue
        $stillSet = [Environment]::GetEnvironmentVariable('GIT_DIR')
        $decoyAfter = Get-RepoFingerprint -Repo $decoy
        # Both halves are answered by GUARD 1 in the normal case - guard 1 throws
        # before guard 2 is ever reached, so this axis does NOT separate the two
        # (round-3 audit; the earlier comment here claimed otherwise and was
        # wrong). What each half does earn its place for:
        #   'refused'   - the hijack is rejected at all
        #   'untouched' - it is rejected EARLY ENOUGH. Measured on this commit:
        #                 delete guard 1 and 'refused' still passes (guard 2
        #                 catches it) while core.bare goes false -> true.
        # That mutation comes from the plain `git init` - with GIT_DIR set and no
        # work tree, git initialises that directory as a BARE repository - not
        # from `clone --bare`, which never runs on that path.
        t 'lag: the before/after fingerprints are real readings, not empty' `
            ((Test-FingerprintUsable $decoyBefore) -and (Test-FingerprintUsable $decoyAfter)) `
            ([string]$decoyBefore + '  ->  ' + [string]$decoyAfter)
        t 'lag: a hijacked GIT_DIR is refused, not followed' $refused 'proceeded'
        t 'lag: the hijacked repo was left untouched (HEAD, branch, count, core.bare, origin, all refs)' `
            ($decoyBefore -eq $decoyAfter) ([string]$decoyBefore + '  ->  ' + [string]$decoyAfter)
        t 'lag: the decoy GIT_DIR was removed again' (-not $stillSet) ([string]$stillSet)

        # f. the live guard, EXERCISED. Earlier versions of this axis read this
        #    file to confirm the check sat above the auditor launch. That was
        #    lexical, and lexical does not survive contact: the round-3 audit
        #    disabled the guard with `$false -and (Test-RepoLag ...)` and every
        #    marker and ordering assertion stayed green (measured 2026-09-13).
        #    So the check moved INSIDE Resolve-AuditorBinary - the only way to
        #    get a binary - and this axis calls that function for real, against
        #    a repository that is genuinely behind its remote.
        $repoF = New-LagRepo -Root $lagRoot -Name 'f' -Commits 2 -Behind
        $threw = $null
        try { Resolve-AuditorBinary -Auditor 'claude' -Repo $repoF | Out-Null }
        catch { $threw = [string]$_.Exception.Message }
        t 'guard: a behind repo cannot yield an auditor binary' `
            ($threw -like 'hq-lag:hq-behind-*') ([string]$threw)

        # ...and the other direction, or a function that refused everything
        # would look identical here.
        $repoG = New-LagRepo -Root $lagRoot -Name 'g' -Commits 2
        $binOk = $null
        $threw2 = $null
        try { $binOk = Resolve-AuditorBinary -Auditor 'claude' -Repo $repoG }
        catch { $threw2 = [string]$_.Exception.Message }
        t 'guard: a current repo does yield the auditor binary' `
            (($null -eq $threw2) -and ($binOk -eq $Claude)) ([string]$threw2 + [string]$binOk)
        t 'guard: it picks the binary the caller asked for' `
            ((Resolve-AuditorBinary -Auditor 'codex' -Repo $repoG) -eq $Codex) 'wrong binary'

        # f1b. THE PROGRAM, not the function. Everything above measures
        #      Resolve-AuditorBinary; nothing above fails if the live call site
        #      stops calling it and picks a binary directly, because -SelfTest
        #      returns long before that line is ever reached (round-4 audit).
        #      That is the round-3 lesson one level out: a structure is only the
        #      only path while the program still walks it. So run THIS script as
        #      a real process against a repository that is behind, and read what
        #      it did - exit code, the STATUS token in its log, and the section
        #      it appended to the artifact.
        $repoE = New-LagRepo -Root $lagRoot -Name 'e2e' -Commits 2 -Behind
        $eRep  = Join-Path $lagRoot 'e2e-report.md'
        $eRul  = Join-Path $lagRoot 'e2e-rules.md'
        Write-Utf8 -Path $eRep -Text "# e2e artifact`r`nSTATUS: OK`r`n"
        Write-Utf8 -Path $eRul -Text "e2e rules`r`n"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath `
            -Report $eRep -Rules $eRul -Auditor codex -Author claude -Hq $repoE *>&1 | Out-Null
        $eCode = $LASTEXITCODE
        $eLog  = Join-Path $repoE ('logs\scheduled\' + $Task + '_' + $Stamp + '.log')
        $eLogText = if (Test-Path -LiteralPath $eLog) { Get-Content -LiteralPath $eLog -Raw } else { '<no log>' }
        $eRepText = Get-Content -LiteralPath $eRep -Raw
        # The exit code alone does not discriminate - measured: with the guard
        # bypassed the run still exits 1, on `codex-not-found`. The STATUS token
        # is the axis that carries the meaning; this one only says it stopped.
        t 'program: a behind Hq stops the whole run (exit 1)' ($eCode -eq 1) ([string]$eCode)
        t 'program: and the STATUS line names the lag' `
            ($eLogText -match 'STATUS: FAIL hq-behind-1') ([string]$eLogText)
        t 'program: and the artifact carries the recovery command' `
            ($eRepText -match 'pull --ff-only') ([string]$eRepText)

        # f1c. the home guard, IN THE PROGRAM, against a CURRENT repo so the lag
        #      guard lets the run through to it. Two runs, opposite inputs:
        #      ~/.codex (JJ's own, a real path - refused on the path alone, so
        #      nothing in it is opened) must stop BEFORE codex starts; an empty
        #      temp home must get PAST the guard and stop at the next check.
        $repoI = New-LagRepo -Root $lagRoot -Name 'iso' -Commits 2
        $iRul  = Join-Path $lagRoot 'iso-rules.md'
        Write-Utf8 -Path $iRul -Text "iso rules`r`n"
        $iLog  = Join-Path $repoI ('logs\scheduled\' + $Task + '_' + $Stamp + '.log')
        #      f1d (third run): -CodexHome is an Orca account home whose parent
        #      folder cannot be listed - the run must stop on
        #      isolation-unknown before codex, not read the short list as "none".
        $fxD = New-AccountsFixture -Root (Join-Path $lagRoot 'deny') -DenyList
        $iRuns = @(
            @{ N = 'interactive'; H = 'C:\Users\ojaej\.codex' },
            @{ N = 'empty';       H = (Join-Path $lagRoot 'empty-home') },
            @{ N = 'denied-list'; H = $fxD.Home; A = $fxD.Dir }
        )
        New-Item -ItemType Directory -Force -Path $iRuns[1].H | Out-Null
        $iOut = @{}
        try {
            foreach ($r in $iRuns) {
                $iRep = Join-Path $lagRoot ('iso-' + $r.N + '.md')
                Write-Utf8 -Path $iRep -Text "# iso artifact`r`nSTATUS: OK`r`n"
                if (Test-Path -LiteralPath $iLog) { Remove-Item -LiteralPath $iLog -Force }
                $more = @(); if ($r.A) { $more = @('-ExtraOrcaAccounts', $r.A) }
                & powershell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath `
                    -Report $iRep -Rules $iRul -Auditor codex -Author claude -Hq $repoI `
                    -CodexHome $r.H @more *>&1 | Out-Null
                $iOut[$r.N] = @{
                    Code = $LASTEXITCODE
                    Log  = $(if (Test-Path -LiteralPath $iLog) { [string](Get-Content -LiteralPath $iLog -Raw) } else { '<no log>' })
                    Rep  = [string](Get-Content -LiteralPath $iRep -Raw -Encoding UTF8)
                }
            }
        } finally {
            Unlock-AccountsFixture -Dir $fxD.Dir
        }
        $id = $iOut['denied-list']
        t 'program: an unlistable Orca accounts folder stops the run as isolation-unknown' `
            (($id.Code -eq 1) -and ($id.Log -match 'STATUS: FAIL codex-home-isolation-unknown')) ([string]$id.Log)
        t 'program: ...and codex never started' (-not ($id.Log -match 'exec start')) ([string]$id.Log)
        $ia = $iOut['interactive']; $ie = $iOut['empty']
        # f1e. the run tag scripts\run_audit.py pairs STATUS lines by: the STATUS
        #      line carries the SAME pid as this run's start line.
        $tagOk = ($ia.Log -match 'start \(pid (\d+)\)') -and ($ia.Log -match ('\[[^\]]* pid ' + $Matches[1] + '\] STATUS: FAIL'))
        t 'log: the STATUS line carries this run''s pid (run_audit pairs overlapping runs by it)' $tagOk ([string]$ia.Log)
        t 'program: -CodexHome ~/.codex is refused as JJ''s interactive home' `
            (($ia.Code -eq 1) -and ($ia.Log -match 'STATUS: FAIL codex-home-interactive')) ([string]$ia.Log)
        t 'program: ...and codex never started' (-not ($ia.Log -match 'exec start')) ([string]$ia.Log)
        t 'program: an isolated home passes the guard and stops at the login check' `
            ($ie.Log -match 'STATUS: FAIL codex-home-not-authenticated') ([string]$ie.Log)
        t 'program: ...and that failure names the one-time login command' `
            ($ie.Rep.Contains('codex login')) ([string]$ie.Rep)

        # g. the auditor's ANSWER, not the auditor's exit code. Measured
        #    2026-09-13: codex exited 0 having read nothing (it said "cannot review,
        #    was blocked") and the run logged STATUS: OK. Both directions are
        #    here, because a predicate that accepts everything and one that
        #    accepts nothing both look fine from one side.
        t 'verdict: PASS is a verdict'             ((Get-VerdictKind -FirstLine 'PASS') -eq 'pass') 'not pass'
        t 'verdict: FINDINGS with a count is one'  ((Get-VerdictKind -FirstLine 'FINDINGS: 3') -eq 'findings') 'not findings'
        # The real answer was Korean; this file is ASCII-only, so the sample is
        # the sample is rebuilt from code points rather than typed.
        $unread = (-join ([char]0xAC80, [char]0xD1A0, [char]0x20, [char]0xBD88, [char]0xAC00)) + '. Get-Content blocked'
        t 'verdict: an unread audit is NOT one'    ($null -eq (Get-VerdictKind -FirstLine $unread)) 'accepted'
        t 'verdict: an empty answer is NOT one'    ($null -eq (Get-VerdictKind -FirstLine '')) 'accepted'
        t 'verdict: a bare FINDINGS header is NOT one' ($null -eq (Get-VerdictKind -FirstLine 'FINDINGS:')) 'accepted'
        t 'verdict: PASS must be the whole line'   ($null -eq (Get-VerdictKind -FirstLine 'PASS is not quite the word for it')) 'accepted'

        # f2. what the caller does with what was thrown. A lag verdict and any
        #     other failure must not read alike: telling someone to pull when
        #     the check never ran sends them to fix a thing that is not broken.
        $vLag   = Get-LagCatchVerdict -Message 'hq-lag:hq-behind-3' -Repo 'C:\hq'
        $vOther = Get-LagCatchVerdict -Message 'something else went wrong' -Repo 'C:\hq'
        $vMulti = Get-LagCatchVerdict -Message "hq-lag:hq-behind-3`nSTATUS: OK" -Repo 'C:\hq'
        t 'catch: a lag message keeps its token'        ($vLag.Token -eq 'hq-behind-3') ([string]$vLag.Token)
        t 'catch: a lag message renders the lag body'   ($vLag.Body -match 'pull --ff-only') ([string]$vLag.Body)
        t 'catch: any other failure is NOT called lag'  ($vOther.Token -eq 'lag-check-error') ([string]$vOther.Token)
        t 'catch: and does not tell the reader to pull' (-not ($vOther.Body -match 'pull --ff-only')) ([string]$vOther.Body)
        t 'catch: the other failure carries its cause'  ($vOther.Body -match 'something else went wrong') ([string]$vOther.Body)
        t 'catch: a token cannot forge a second STATUS line' (($vMulti.Token -notmatch '[\r\n]')) ([string]$vMulti.Token)
    } catch {
        t 'lag: temp repos built without touching the real repo' $false ([string]$_)
    } finally {
        Remove-Item -LiteralPath $lagRoot -Recurse -Force -ErrorAction SilentlyContinue
        # Only variables that HAD a value are put back; one that was absent stays
        # absent rather than coming back as an empty string.
        foreach ($n in @($LAG_GIT_ENV_ALLOWED)) { Remove-Item -LiteralPath ('Env:' + $n) -ErrorAction SilentlyContinue }
        foreach ($n in @($gitEnvSaved.Keys)) {
            if ($null -ne $gitEnvSaved[$n]) { Set-Item -LiteralPath ('Env:' + $n) -Value $gitEnvSaved[$n] }
        }
    }

    # 6. -Model / -CodexHome (infra backlog 31). Both directions, and the
    #    no-model direction is held to the EXACT old list: "no --model" alone
    #    would also pass a builder that dropped or reordered something else,
    #    and -Model '' (the opt-out from the gpt-6-astra default) promises the
    #    old command line plus only the Windows sandbox pair.
    #    NOT MEASURED (charter section 0, layer 4): that the live call site
    #    hands this array to codex. Reaching that line takes a real codex run,
    #    and faking one needs an overridable binary path - the bigger hole the
    #    verdict note in the main flow declines for the same reason.
    $legacy    = @('exec', '-C', 'C:\hq', '--sandbox', 'read-only', '-c', 'windows.sandbox=unelevated', '--skip-git-repo-check', '-o', 'C:\ans.txt', '-')
    $argsNone  = @(Get-CodexArgs -Repo 'C:\hq' -AnswerPath 'C:\ans.txt' -ModelName '')
    $argsModel = @(Get-CodexArgs -Repo 'C:\hq' -AnswerPath 'C:\ans.txt' -ModelName 'gpt-6-astra')
    t 'model: without -Model the codex arguments are exactly the old list' `
        (($argsNone -join '|') -ceq ($legacy -join '|')) ($argsNone -join ' ')
    # Both lists, not one: the sandbox pair must not ride on -Model.
    foreach ($pair in @(@('none', $argsNone), @('model', $argsModel))) {
        $ci = [Array]::IndexOf($pair[1], 'windows.sandbox=unelevated')
        t ('sandbox: the ' + $pair[0] + ' arguments carry -c windows.sandbox=unelevated') `
            (($ci -ge 1) -and ($pair[1][$ci - 1] -ceq '-c')) ($pair[1] -join ' ')
    }
    t 'model: without -Model there is no --model' ($argsNone -notcontains '--model') ($argsNone -join ' ')
    $mi = [Array]::IndexOf($argsModel, '--model')
    t 'model: with -Model the arguments carry --model <name>' `
        (($mi -ge 0) -and ($argsModel[$mi + 1] -ceq 'gpt-6-astra')) ($argsModel -join ' ')
    t 'model: the stdin marker stays the last argument' ($argsModel[-1] -ceq '-') ($argsModel -join ' ')

    # 6a. the DEFAULT home - the one every scheduled run uses, since the wrappers
    #     pass nothing - measured against the REAL interactive homes on this
    #     machine, by path and by auth.json hash. Read before 6b reassigns
    #     $CodexHome. Run with -SelfTest alone so $CodexHome is the default.
    $defIso = Get-CodexHomeIsolation -HomeDir $CodexHome -ExtraAccountsDirs $ExtraOrcaAccounts
    t 'defaults: the default codex home shares no login with JJ''s interactive homes' `
        ($null -eq $defIso) ([string]$defIso + ' ' + $CodexHome)

    # 6b. the run record carries VALUES, not just a shape (the 2026-08-15
    #     lesson: a provenance stamp printed empty as "skill live:  (deployed )").
    #     Through the real Append-Section into a scratch report, both halves.
    #     Report, Model and CodexHome are set here and reach Append-Section by
    #     PowerShell's dynamic scope; the script-level values are not touched.
    $Model     = 'gpt-6-astra'
    $CodexHome = 'C:\home-b'
    $secPass   = ''
    foreach ($half in @($true, $false)) {
        $Report = Join-Path ([System.IO.Path]::GetTempPath()) ('jj-crossverify-sec-' + $PID + '-' + [int]$half + '.md')
        Write-Utf8 -Path $Report -Text "# scratch`r`n"
        Append-Section -Body 'B' -Failed $half -AuditorName 'codex' -AuthorName 'claude'
        # [string] so a report that could not be read fails the check below
        # instead of throwing past it - a method call on $null skips the t line.
        $sec = [string](Get-Content -LiteralPath $Report -Raw -Encoding UTF8)
        Remove-Item -LiteralPath $Report -Force -ErrorAction SilentlyContinue
        if (-not $half) { $secPass = $sec }
        t ('run line: the ' + $(if ($half) { 'failure' } else { 'pass' }) + ' section names the home and the model') `
            ($sec.Contains('codex run: `CODEX_HOME=C:\home-b | model=gpt-6-astra`')) $sec
        t ('run line: the ' + $(if ($half) { 'failure' } else { 'pass' }) + ' section has no placeholder left') `
            (-not ($sec -match '\{\{')) $sec
        # The re-run command must replay THIS run's home and model. Without them
        # a retry pasted from the report goes back to whatever the defaults are
        # that day - before 2026-10-05 that was the dead API-key home.
        if ($half) {
            t 'rerun: the failure section re-runs with the same -CodexHome and -Model' `
                ($sec.Contains('-Author claude -CodexHome "C:\home-b" -Model "gpt-6-astra"')) $sec
        }
    }
    # ...and not for -Auditor claude, where those two would only be ignored.
    $Report = Join-Path ([System.IO.Path]::GetTempPath()) ('jj-crossverify-sec-' + $PID + '-claude.md')
    Write-Utf8 -Path $Report -Text "# scratch`r`n"
    Append-Section -Body 'B' -Failed $true -AuditorName 'claude' -AuthorName 'codex'
    $secClaude = [string](Get-Content -LiteralPath $Report -Raw -Encoding UTF8)
    Remove-Item -LiteralPath $Report -Force -ErrorAction SilentlyContinue
    t 'rerun: a claude-audit failure section carries no codex arguments' `
        ($secClaude.Contains('-Author codex') -and -not $secClaude.Contains('-CodexHome') -and -not ($secClaude -match '\{\{')) $secClaude
    t 'run line: the pass header names the -Model it ran with, not codex default' `
        ($secPass.Contains('codex --model gpt-6-astra') -and -not $secPass.Contains('codex default')) $secPass
    $runDefault = Get-CodexRunLine -HomeDir 'C:\home-a' -ModelName ''
    t 'run line: without -Model it says codex default, not an empty model' `
        ($runDefault -ceq 'CODEX_HOME=C:\home-a | model=(codex default)') $runDefault

    # 7. the stderr failure hint (infra backlog 31). The sample follows the
    #    shapes measured 2026-09-25 in the codex job's own shape (stdin pipe,
    #    2> to a file): PS 5.1 prefixes the FIRST stderr line with
    #    "<command> : " and adds its own error-record lines; a real failing
    #    codex run then prints timestamped tracing lines, retry notices
    #    "ERROR: Reconnecting... n/5", the terminal ERROR: line, and the wrapped
    #    tail of it. So the first line is the banner, the first ERROR: line is a
    #    retry notice and the last line is a fragment - a picker that took any
    #    of those instead of the terminal line fails this case.
    $errHead = @(
        'codex.cmd : OpenAI Codex v0.154.0 (research preview)',
        'At line:5 char:9',
        '+         $text | & $bin @binArgs 1> $stdoutPath 2> $stderrPath',
        '+         ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~',
        '    + CategoryInfo          : NotSpecified: (OpenAI Codex v0.154.0 (research preview):String) [], RemoteException',
        '    + FullyQualifiedErrorId : NativeCommandError',
        ' ',
        '--------',
        'workdir: C:\Users\ojaej\jj-company',
        'model: gpt-6-astra',
        '--------'
    )
    $errText = 'ERROR: stream disconnected before completion: You have no credits remaining.'
    $errRun = @(
        '2026-09-25T08:34:22.629238Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: HTTP error:',
        '401 Unauthorized, url: wss://api.openai.com/v1/responses',
        'ERROR: Reconnecting... 1/5',
        'ERROR: Reconnecting... 2/5',
        $errText,
        'key at https://platform.openai.com/account/api-keys., url: https://api.openai.com/v1/responses',
        ' '
    )
    $hErr = Get-StderrHint -Lines ($errHead + $errRun)
    t 'hint: the terminal ERROR: line is the hint (not the banner, a retry notice or a wrapped tail)' `
        ($hErr -ceq $errText) $hErr
    # the other direction: with no ERROR: line the last non-empty line wins
    $hNone = Get-StderrHint -Lines ($errHead + @('last words', '   ', ''))
    t 'hint: without an ERROR: line it is the last non-empty line, not the banner' ($hNone -ceq 'last words') $hNone
    $hPrefixed = Get-StderrHint -Lines @('codex.cmd : ERROR: boom', 'after')
    t 'hint: an ERROR: line in the prefixed first slot is still found' ($hPrefixed -ceq 'ERROR: boom') $hPrefixed
    $hLong = [string](Get-StderrHint -Lines @('ERROR: ' + ('x' * 500)))
    t 'hint: capped at 200 characters' ($hLong.Length -eq 200) ([string]$hLong.Length)
    $hKey = [string](Get-StderrHint -Lines @('ERROR: 401 Incorrect API key provided: sk-proj-FAKEFAKEFAKEFAKE0000'))
    t 'hint: an sk- key shaped token is masked before it can reach the log' `
        ($hKey.Contains('sk-<redacted>') -and -not $hKey.Contains('FAKEFAKE')) $hKey

    # 8. the bytes codex receives on stdin (infra backlog 31). $CodexJobBlock is
    #    the LIVE job, run here with a stand-in program that writes back the hex
    #    of whatever arrived on its stdin. The prompt is a real template line
    #    with Hangul in it, rebuilt from code points (this file is ASCII-only).
    #    CONTROL FIRST: the same job WITHOUT the encoding line must turn the
    #    Hangul into '?', or the live case passing proves nothing - it could
    #    pass because the pipe was never lossy here at all.
    $encDir = Join-Path ([System.IO.Path]::GetTempPath()) ('jj-crossverify-enc-' + $PID)
    New-Item -ItemType Directory -Force -Path $encDir | Out-Null
    $encPrompt = (-join ([char]0xAC10, [char]0xB9AC, [char]0xC790)) + ' PASS ' + (-join ([char]0xADDC, [char]0xCE59)) + "`r`n"
    $encPromptPath = Join-Path $encDir 'prompt.txt'
    Write-Utf8 -Path $encPromptPath -Text $encPrompt
    $want = -join ((New-Object System.Text.UTF8Encoding($false)).GetBytes($encPrompt) | ForEach-Object { $_.ToString('x2') })
    $dump = @('-c', 'import sys;sys.stdout.write(sys.stdin.buffer.read().hex())')
    $oldBlock = {
        # the job exactly as it was before 2026-10-05: no $OutputEncoding
        param($bin, $binArgs, $promptPath, $stdoutPath, $stderrPath, $codexHome)
        $env:CODEX_HOME = $codexHome
        $text = Get-Content -LiteralPath $promptPath -Raw -Encoding UTF8
        $text | & $bin @binArgs 1> $stdoutPath 2> $stderrPath
        $LASTEXITCODE
    }
    $got = @{}
    foreach ($case in @(@{ N = 'old'; B = $oldBlock }, @{ N = 'live'; B = $CodexJobBlock })) {
        $outP = Join-Path $encDir ($case.N + '.out')
        $errP = Join-Path $encDir ($case.N + '.err')
        $j = Start-Job -ScriptBlock $case.B -ArgumentList 'py', $dump, $encPromptPath, $outP, $errP, $encDir
        if (Wait-Job $j -Timeout 60) { Receive-Job $j | Out-Null }
        Remove-Job $j -Force -ErrorAction SilentlyContinue
        # 1> in PS 5.1 writes UTF-16; the hex is ASCII, so any reader will do.
        # PS appends a newline to the piped string, so compare the prefix.
        $got[$case.N] = if (Test-Path -LiteralPath $outP) { ([string](Get-Content -LiteralPath $outP -Raw)).Trim() } else { '<no output>' }
    }
    Remove-Item -LiteralPath $encDir -Recurse -Force -ErrorAction SilentlyContinue
    t 'stdin: control - the old job shape DOES turn Hangul into ? (3f)' `
        ($got['old'].StartsWith('3f3f3f20') -and -not $got['old'].StartsWith($want)) $got['old']
    t 'stdin: the live job hands codex the prompt as UTF-8, byte for byte, no BOM' `
        ($got['live'].StartsWith($want) -and -not $got['live'].StartsWith('efbbbf')) ($got['live'] + ' want ' + $want)

    # 9. codex home isolation - the function, on temp directories. Each case
    #    moves ONE axis, so a pass is owed to the check it names:
    #    9a path only (the interactive dir has no auth.json, so the hash axis
    #    cannot fire), 9b hash only (different path, copied file), 9c the
    #    opposite of both (own path, own login), 9d path spelling.
    $isoRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('jj-crossverify-iso-' + $PID)
    $ixA = Join-Path $isoRoot 'interactive-a'      # no auth.json
    $ixB = Join-Path $isoRoot 'interactive-b'      # has a login
    $own = Join-Path $isoRoot 'audit-own'
    $cpy = Join-Path $isoRoot 'audit-copied'
    foreach ($d in @($ixA, $ixB, $own, $cpy)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
    Write-Utf8 -Path (Join-Path $ixB 'auth.json') -Text '{"fake":"interactive login"}'
    Write-Utf8 -Path (Join-Path $cpy 'auth.json') -Text '{"fake":"interactive login"}'
    Write-Utf8 -Path (Join-Path $own 'auth.json') -Text '{"fake":"audit login of its own"}'
    $ix = @($ixA, $ixB)
    $r9a = Test-CodexHomeIsolation -HomeDir $ixA -Interactive $ix
    $r9b = Test-CodexHomeIsolation -HomeDir $cpy -Interactive $ix
    $r9c = Test-CodexHomeIsolation -HomeDir $own -Interactive $ix
    $r9d = Test-CodexHomeIsolation -HomeDir ($ixA.ToUpperInvariant() + '\') -Interactive $ix
    # 9e. an interactive auth.json that cannot be read (held open exclusively).
    #     Own path, own login - only the unreadable file can make this fail.
    $lock = [System.IO.File]::Open((Join-Path $ixB 'auth.json'), 'Open', 'Read', 'None')
    try { $r9e = Test-CodexHomeIsolation -HomeDir $own -Interactive $ix } finally { $lock.Dispose() }
    # 9f. the account LISTING, through Get-CodexHomeIsolation (the call the run
    #     makes). Same account home both times; only the folder's list right
    #     differs. Control: listable -> the home is found and refused on its path.
    #     Denied -> unknown. Without the control a broken fixture that never lists
    #     anything would pass 9f for free.
    $fxOpen = New-AccountsFixture -Root (Join-Path $isoRoot 'open')
    $fxDeny = New-AccountsFixture -Root (Join-Path $isoRoot 'deny') -DenyList
    try {
        $r9fc = Get-CodexHomeIsolation -HomeDir $fxOpen.Home -ExtraAccountsDirs $fxOpen.Dir
        $r9f  = Get-CodexHomeIsolation -HomeDir $fxDeny.Home -ExtraAccountsDirs $fxDeny.Dir
    } finally {
        Unlock-AccountsFixture -Dir $fxDeny.Dir
    }
    # 9g. an extra folder ADDS, it never replaces the real one (Codex recheck
    #     2026-10-06): a REAL Orca account home with an extra folder that does
    #     not exist must still be refused. Real path, refused on the path
    #     alone, so its auth.json is never opened. Done on the function the run
    #     calls, NOT by running the program: if this guard ever regressed, a
    #     program run would start codex on JJ's live account login. The run's
    #     wiring to that function is f1d. No real account on this machine is
    #     "not measured", which fails - never a quiet pass.
    $realAcct = @(Get-ChildItem -LiteralPath $ORCA_CODEX_ACCOUNTS -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'home' } | Where-Object { Test-Path -LiteralPath $_ }) | Select-Object -First 1
    $r9g = if ($realAcct) {
        Get-CodexHomeIsolation -HomeDir $realAcct -ExtraAccountsDirs (Join-Path $isoRoot 'no-such-accounts')
    } else { 'not measured: no real Orca account home under ' + $ORCA_CODEX_ACCOUNTS }
    Remove-Item -LiteralPath $isoRoot -Recurse -Force -ErrorAction SilentlyContinue
    t 'isolation: a missing extra accounts folder does not hide the real Orca accounts' ($r9g -eq 'codex-home-interactive') ([string]$r9g + ' ' + [string]$realAcct)
    t 'isolation: control - a listable accounts folder finds the account home' ($r9fc -eq 'codex-home-interactive') ([string]$r9fc)
    t 'isolation: an unlistable accounts folder is unknown, not a pass'        ($r9f -eq 'codex-home-isolation-unknown') ([string]$r9f)
    t 'isolation: an interactive home itself is refused (path)'              ($r9a -eq 'codex-home-interactive') ([string]$r9a)
    t 'isolation: a copied interactive auth.json is refused (hash)'          ($r9b -eq 'codex-home-shared-login') ([string]$r9b)
    t 'isolation: a home with its own login passes (does not refuse all)'    ($null -eq $r9c) ([string]$r9c)
    t 'isolation: path case and a trailing backslash do not hide the match'  ($r9d -eq 'codex-home-interactive') ([string]$r9d)
    t 'isolation: an unreadable interactive login is unknown, not a pass'    ($r9e -eq 'codex-home-isolation-unknown') ([string]$r9e)

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

# -CodexHome and -Model only steer codex. Passed with -Auditor claude they do
# nothing, and doing nothing without a word is what charter section 0 forbids.
foreach ($k in @('CodexHome', 'Model')) {
    if ($Auditor -ne 'codex' -and $PSBoundParameters.ContainsKey($k)) {
        Write-Log ('-' + $k + ' applies to -Auditor codex only; ignored for ' + $Auditor)
    }
}

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

# Resolve-AuditorBinary runs the lag check itself, so there is no ordering here
# to get wrong and none to police: the binary cannot be obtained without it.
$Bin = $null
try {
    $Bin = Resolve-AuditorBinary -Auditor $Auditor -Repo $Hq
} catch {
    # Only an 'hq-lag:' message is a lag verdict. Anything else thrown in there
    # is a different failure, and dressing it up as "your tree is behind" would
    # send the reader to run a pull that fixes nothing - a wrong diagnosis is
    # worse than none (charter section 0). Tokens are one line by construction;
    # a stray message is flattened so it cannot forge extra STATUS lines.
    $verdict = Get-LagCatchVerdict -Message ([string]$_.Exception.Message) -Repo $Hq
    $lag  = $verdict.Token
    $body = $verdict.Body
    Write-Log ('hq lag check: ' + $lag + ' (' + $Hq + ')')
    Append-Section -Body $body -Failed $true -AuditorName $Auditor -AuthorName $Author
    Write-Log ('STATUS: FAIL ' + $lag)
    exit 1
}
Write-Log 'hq lag check OK - main is not behind origin/main'

if (-not (Test-Path -LiteralPath $Bin)) {
    Write-Log ($Auditor + ' not found: ' + $Bin)
    Append-Section -Body ($Auditor + '-not-found: ' + $Bin) -Failed $true -AuditorName $Auditor -AuthorName $Author
    Write-Log ('STATUS: FAIL ' + $Auditor + '-not-found')
    exit 1
}
if ($Auditor -eq 'codex') {
    $iso = Get-CodexHomeIsolation -HomeDir $CodexHome -ExtraAccountsDirs $ExtraOrcaAccounts
    if ($iso) {
        Write-Log ('audit codex home is not isolated: ' + $iso + ' (' + $CodexHome + ')')
        Append-Section -Body ($iso + ': ' + $CodexHome + ' shares a login with JJ''s interactive codex. A refresh here ' +
            'would invalidate the other copy. Give the audit its own login instead (see scripts\cross-verify.ps1 header).') `
            -Failed $true -AuditorName $Auditor -AuthorName $Author
        Write-Log ('STATUS: FAIL ' + $iso)
        exit 1
    }
}
if ($Auditor -eq 'codex' -and -not (Test-Path -LiteralPath (Join-Path $CodexHome 'auth.json'))) {
    Write-Log ('audit codex home not logged in: ' + $CodexHome)
    # Name the way out (charter section 3): the login is a one-time human step.
    Append-Section -Body ('codex-home-not-authenticated: ' + $CodexHome + ' has no login yet. One time, by hand, in ' +
        'PowerShell: $env:CODEX_HOME=''' + $CodexHome + '''; codex login; Remove-Item Env:CODEX_HOME') `
        -Failed $true -AuditorName $Auditor -AuthorName $Author
    Write-Log 'STATUS: FAIL codex-home-not-authenticated'
    exit 1
}

# Process-scoped only. The audit runs on its own home (header); -CodexHome can
# point it at another one, still for this process alone.
if ($Auditor -eq 'codex') {
    $env:CODEX_HOME = $CodexHome
    Write-Log (Get-CodexRunLine -HomeDir $CodexHome -ModelName $Model)
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
    # The prompt is piped on stdin so the Korean text never crosses the command
    # line, and $CodexJobBlock sets the pipe to UTF-8 (infra backlog 31).
    $codexArgs = Get-CodexArgs -Repo $Hq -AnswerPath $answerPath -ModelName $Model
    # codex is a .cmd shim; Start-Process -PassThru returns $null for it, so the
    # process never launches. Invoke it directly and pipe the prompt on stdin, with
    # a background job supplying the timeout.
    $job = Start-Job -ScriptBlock $CodexJobBlock `
        -ArgumentList $Bin, $codexArgs, $promptPath, $stdoutPath, $stderrPath, $CodexHome
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
    # stderr carries the auth or quota message. Get-StderrHint picks codex's LAST
    # ERROR: line (the first line is only the version banner, the first ERROR:
    # line a retry notice), masks key-shaped tokens and caps the length - see
    # there for the measurements behind it.
    $hint = ''
    if (Test-Path -LiteralPath $stderrPath) {
        $errHint = Get-StderrHint -Lines @(Get-Content -LiteralPath $stderrPath -ErrorAction SilentlyContinue)
        if ($errHint) { $hint = ' | stderr: ' + $errHint }
    }
    Write-Log ($Auditor + ' failed: ' + $failure + $hint)
    Append-Section -Body $failure -Failed $true -AuditorName $Auditor -AuthorName $Author
    Write-Log ('STATUS: FAIL ' + $failure)
} else {
    # An auditor that READ NOTHING must not look like an auditor that passed.
    # Measured 2026-09-13: codex returned "cannot review - Get-Content blocked",
    # exited 0, and this branch appended it as an ordinary section and logged
    # STATUS: OK. The prompt requires the first line to be PASS or FINDINGS: N,
    # so anything else is the audit saying it could not judge - and a run that
    # produced no judgement did not do its job (charter section 4: STATUS means
    # "did the task complete"). This is the L-016 lesson one layer out: a value
    # nobody read must not be compared against one somebody did.
    #
    # NOT MEASURED (charter section 0, layer 4): the self-test exercises
    # Get-VerdictKind, not this wiring. Reaching this branch end to end needs a
    # real auditor answer, and the only way to fake one is to make the binary
    # path overridable - a far bigger hole (an auditor that always says PASS)
    # than the one it would close. So the predicate is proven and the wiring is
    # not, and that is written here rather than counted as covered. The round-4
    # lesson above applies to this line too: reading it is not evidence it ran.
    $verdict = ($answer.Trim() -split "`n")[0].Trim()
    if ($null -eq (Get-VerdictKind -FirstLine $verdict)) {
        $flat = ($verdict -replace '[\r\n]+', ' ')
        if ($flat.Length -gt 300) { $flat = $flat.Substring(0, 300) }
        Write-Log ($Auditor + ' returned no verdict: ' + $flat)
        Append-Section -Body ('audit-no-verdict: the auditor answered without the required first line ' +
            '(PASS or "FINDINGS: <n>"), so NOTHING is known about this report - this is not a pass. ' +
            'What it said instead: ' + $flat) -Failed $true -AuditorName $Auditor -AuthorName $Author
        Write-Log 'STATUS: FAIL audit-no-verdict'
        foreach ($f in @($promptPath, $answerPath, $stdoutPath, $stderrPath)) {
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
        }
        exit 1
    }
    Append-Section -Body $answer.Trim() -Failed $false -AuditorName $Auditor -AuthorName $Author
    Write-Log ($Auditor + ' verdict: ' + $verdict)
    Write-Log ('appended to: ' + $Report)
    Write-Log 'STATUS: OK'
}

foreach ($f in @($promptPath, $answerPath, $stdoutPath, $stderrPath)) {
    Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
}

if ($failure) { exit 1 }
exit 0
