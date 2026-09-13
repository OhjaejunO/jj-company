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
        $leaked = (& git -C $repoH config --get user.signingkey 2>$null)
        if ($null -eq $realHome) { Remove-Item -LiteralPath 'Env:HOME' -ErrorAction SilentlyContinue }
        else { $env:HOME = $realHome }
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

# Resolve-AuditorBinary runs the lag check itself, so there is no ordering here
# to get wrong and none to police: the binary cannot be obtained without it.
$Bin = $null
try {
    $Bin = Resolve-AuditorBinary -Auditor $Auditor -Repo $Hq
} catch {
    $lag = ([string]$_.Exception.Message) -replace '^hq-lag:', ''
    Write-Log ('hq lag check: ' + $lag + ' (' + $Hq + ')')
    Append-Section -Body (Get-LagFailureBody -Lag $lag -Repo $Hq) -Failed $true -AuditorName $Auditor -AuthorName $Author
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
