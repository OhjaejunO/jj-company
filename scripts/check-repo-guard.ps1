#requires -Version 5.1
#
# JJ Company OS - repo guard self-check (charter section 0 + section 3)
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as
# the system ANSI codepage, which mangles non-ASCII text.
#
# WHY THIS EXISTS
#   scripts\githooks\pre-commit only runs if `core.hooksPath` points at it. That
#   config is per-clone and is NOT carried by git. So the guard can be absent
#   while everything looks normal - the exact silent-failure shape charter
#   section 0 forbids.
#
#   Charter section 0 also requires that a detector be checked with an input
#   that MUST trip it. So this script does not merely read config: it RUNS the
#   hook in the primary worktree and fails if the hook lets it through.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-repo-guard.ps1
#   ... -Fix           also sets core.hooksPath
#   ... -Repo <path>   check a specific clone (default: the clone this script
#                      lives in, so the charter section 3 command needs no path)

[CmdletBinding()]
param(
    [string]$Repo,
    [switch]$Fix,
    # Internal. Set only on the nested run made by the targeting check below,
    # so that run does not recurse into another targeting check.
    [switch]$NoSelfTest
)

$ErrorActionPreference = 'Stop'
$problems = @()
$notes = @()

function Say([string]$m) { Write-Host ('[repo-guard] ' + $m) }

# --- 0. resolve WHICH clone is being checked --------------------------------
# 2026-08-15: $Repo defaulted to a hardcoded 'C:\Users\ojaej\orca\jj-company'.
# Run inside the production clone it inspected the DEVELOPMENT clone instead and
# printed STATUS: OK while production had no core.hooksPath at all. The guard
# checker itself broke the charter section 0 rule it exists to enforce - a
# detector that reports on something other than its subject is worse than none,
# because the OK is read as proof.
#
# The default now follows the script. --git-common-dir returns the PRIMARY
# tree's .git from anywhere inside a clone (primary tree or linked worktree), so
# the documented `scripts\check-repo-guard.ps1 -Fix` installs into the clone it
# was launched from, with no path to remember and none to get wrong.
$RepoWasExplicit = $PSBoundParameters.ContainsKey('Repo')
if (-not $RepoWasExplicit) {
    $anchor = $PSScriptRoot
    if (-not $anchor) { $anchor = (Get-Location).ProviderPath }

    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $common = (& git -C $anchor rev-parse --path-format=absolute --git-common-dir 2>$null)
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $prev

    if ($rc -ne 0 -or [string]::IsNullOrWhiteSpace($common)) {
        Say ('cannot resolve a clone from ' + $anchor)
        Write-Host 'STATUS: FAIL repo-guard (no-repo)'
        exit 1
    }
    $Repo = Split-Path -Parent ($common.Trim() -replace '/', '\')
}

# Always name the subject. This line is what would have exposed the 2026-08-15
# bug on sight: the run said it allowed a worktree that the target clone does
# not have. Print it before any check can throw, so even a crash says what it
# was aimed at.
$how = if ($RepoWasExplicit) { 'explicit -Repo' } else { 'resolved from script location' }
Say ('target: ' + $Repo + '  (' + $how + ')')

if (-not (Test-Path -LiteralPath $Repo)) { throw ('repo missing: ' + $Repo) }

# -Repo must be the PRIMARY worktree. Point it at a linked worktree and every
# conclusion below inverts - the linked tree gets checked as if it were primary
# and the real primary is reported as "linked". The script would still print a
# confident verdict, which is worse than refusing. 2026-08-15: caught while
# testing this script by aiming it at a worktree.
$repoGitDir = (& git -C $Repo rev-parse --git-dir 2>$null)
if ($LASTEXITCODE -ne 0) { throw ('not a git repo: ' + $Repo) }
if ($repoGitDir -match '[\\/]worktrees[\\/]') {
    Write-Host ('  - -Repo points at a LINKED worktree (' + $Repo + '), not the primary one')
    Write-Host '    Pass the primary working tree instead; results would be inverted.'
    Write-Host 'STATUS: FAIL repo-guard (bad-target)'
    exit 1
}

# --- locate the sh git itself uses to run hooks -----------------------------
$sh = (Get-Command sh -ErrorAction SilentlyContinue)
if ($sh) {
    $ShExe = $sh.Source
} else {
    $cand = @(
        (Join-Path $env:ProgramFiles 'Git\bin\sh.exe'),
        (Join-Path $env:ProgramFiles 'Git\usr\bin\sh.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Git\bin\sh.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    $ShExe = $cand | Select-Object -First 1
}
if (-not $ShExe) { throw 'sh.exe not found - cannot run the hook for verification' }

# --- 1. config present and pointing at the committed hooks ------------------
$want = 'scripts/githooks'
$have = (& git -C $Repo config --local core.hooksPath 2>$null)
if ($have) { $have = $have.Trim() }

if ($have -ne $want) {
    if ($Fix) {
        & git -C $Repo config --local core.hooksPath $want
        Say ("core.hooksPath set to '" + $want + "'")
        $have = $want
    } else {
        $problems += ("core.hooksPath is '" + $have + "', expected '" + $want + "' (run with -Fix)")
    }
}

# --- 2. hook files exist ----------------------------------------------------
foreach ($h in @('pre-commit', 'post-checkout')) {
    $p = Join-Path $Repo (Join-Path $want $h)
    if (-not (Test-Path -LiteralPath $p)) { $problems += ('hook missing: ' + $h) }
}

# --- 3. primary worktree is on main ----------------------------------------
# A repo with no commits yet makes rev-parse fail. Under $ErrorActionPreference
# 'Stop' that killed the script mid-run instead of reporting - charter section 0
# calls that shape out by name. Report unknown as unknown and keep going.
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$branch = (& git -C $Repo rev-parse --abbrev-ref HEAD 2>$null)
$branchRc = $LASTEXITCODE
$ErrorActionPreference = $prev

if ($branchRc -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
    $branch = '?'
    $problems += 'cannot determine the branch of the primary worktree'
} else {
    $branch = $branch.Trim()
    if ($branch -ne 'main') {
        $problems += ("primary worktree is on '" + $branch + "', charter section 3 pins it to main")
    }
}

# --- 3b. local main must not lag origin/main --------------------------------
# 2026-08-22 (3 commits) and 2026-08-24 (2 commits): local main was behind and
# an already-MERGED kit PR was reported as "not deployed" several times; a git
# stash made in that confusion rolled the day's deployment back (caught before
# it went live). Charter section 3 already said "fetch after work" - a rule,
# broken twice. Charter section 0 / the 4-layer clause: move it from a rule to
# a device. The fetch happens HERE so the verdict is about the remote as it is
# now, not as it was last looked at.
function Get-BehindCount([string]$LocalRef, [string]$RemoteRef) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $n = (& git -C $Repo rev-list --count ($LocalRef + '..' + $RemoteRef) 2>$null)
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($rc -ne 0 -or [string]::IsNullOrWhiteSpace($n)) { return $null }
    return [int]($n.Trim())
}

$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$remotes = @(& git -C $Repo remote 2>$null)
$ErrorActionPreference = $prev

if ($remotes -contains 'origin') {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & git -C $Repo fetch --quiet origin main *>&1 | Out-Null
    $fetchRc = $LASTEXITCODE
    $ErrorActionPreference = $prev

    if ($fetchRc -ne 0) {
        # Not a note: an unfetched compare would answer from stale refs, which
        # is the very failure this check exists to catch.
        $problems += 'git fetch origin main failed - lag check could not run (offline?)'
    } else {
        $behind = Get-BehindCount 'main' 'origin/main'
        if ($null -eq $behind) {
            $problems += 'cannot compare main with origin/main (branch missing?)'
        } elseif ($behind -gt 0) {
            $problems += ('local main is ' + $behind + ' commit(s) behind origin/main - a session reading it takes a stale copy as canon. Run: git -C "' + $Repo + '" pull --ff-only origin main')
        } else {
            Say 'lag check OK - local main is not behind origin/main'
        }

        # Reverse check (charter section 0): the comparator must report a ref
        # that IS behind. main~1 is one commit behind by construction.
        $rev = Get-BehindCount 'main~1' 'origin/main'
        if ($null -eq $rev) {
            $notes += 'lag reverse check SKIPPED - main has no parent commit'
        } elseif ($rev -lt 1) {
            $problems += 'LAG REVERSE CHECK FAILED: main~1 was not reported as behind origin/main'
        } else {
            Say ('lag reverse check OK - main~1 reads as ' + $rev + ' behind')
        }
    }
} else {
    $notes += 'no origin remote - lag check SKIPPED'
}

# --- 4. REVERSE CHECK - the hook must REFUSE a commit here ------------------
# Charter section 0: a detector that never trips is worse than none. Feed it the
# input that must be rejected and fail if it passes.
function Invoke-Hook([string]$HookFile, [string]$WorkDir) {
    # Native stderr must not be fatal here. With $ErrorActionPreference='Stop' a
    # hook that writes to stderr (which is exactly what a REFUSING hook does)
    # raises NativeCommandError and the check dies instead of reporting.
    # 2026-08-15: that is how this script first failed - it crashed rather than
    # answering, which is the silent-failure shape charter section 0 forbids.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Push-Location $WorkDir
    try {
        & $ShExe $HookFile *>&1 | Out-Null
        return $LASTEXITCODE
    } finally {
        Pop-Location
        $ErrorActionPreference = $prev
    }
}

$hookPath = Join-Path $Repo (Join-Path $want 'pre-commit')
$hookHere = Test-Path -LiteralPath $hookPath

if ($hookHere) {
    $code = Invoke-Hook $hookPath $Repo
    if ($code -eq 0) {
        $problems += 'REVERSE CHECK FAILED: pre-commit allowed a commit from the primary worktree'
    } else {
        Say 'reverse check OK - hook refuses commits in the primary worktree'
    }
} else {
    $notes += 'reverse check SKIPPED - hook file not present in the primary worktree yet'
}

# --- 5. REVERSE CHECK (other side) - a linked worktree must PASS ------------
# Without this, a hook that refuses everything would look correct above.
$wt = @()
foreach ($line in (& git -C $Repo worktree list --porcelain)) {
    if ($line -match '^worktree (.+)$') { $wt += $Matches[1] }
}

# git prints forward slashes ("C:/Users/...") while $Repo arrives with
# backslashes. A raw string compare then fails to match the primary tree and it
# gets tested as if it were a LINKED worktree - which reported a REVERSE CHECK
# FAILURE against a perfectly good hook. 2026-08-15: seen on the first real run.
# The same bug can invert: a linked tree mistaken for primary would be skipped
# and the check would pass without ever testing the allow side.
function ConvertTo-ComparablePath([string]$p) {
    if ([string]::IsNullOrWhiteSpace($p)) { return '' }
    try { $p = (Resolve-Path -LiteralPath $p -ErrorAction Stop).ProviderPath } catch { }
    return ($p -replace '/', '\').TrimEnd('\').ToLowerInvariant()
}

$repoKey = ConvertTo-ComparablePath $Repo
$linked = $wt | Where-Object { (ConvertTo-ComparablePath $_) -ne $repoKey } | Select-Object -First 1

# If no linked worktree happens to exist, MAKE one. Leaving this side as
# UNVERIFIED is not neutral - the next reader skims the STATUS line and takes it
# for a pass, so the allow side silently stops being checked. Creating and
# removing the worktree inside this script keeps both directions running
# regardless of what the repo looked like when it was called.
$tempWt = $null
$usedTemp = $false

try {
    if ($hookHere -and -not ($linked -and (Test-Path -LiteralPath $linked))) {
        $tempWt = Join-Path ([System.IO.Path]::GetTempPath()) ('repo-guard-' + [guid]::NewGuid().ToString('N'))
        # --detach: no branch is created, so nothing to clean up in refs and no
        # chance of colliding with a name another session is using.
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & git -C $Repo worktree add --detach $tempWt HEAD *>&1 | Out-Null
        $addCode = $LASTEXITCODE
        $ErrorActionPreference = $prev

        if ($addCode -eq 0 -and (Test-Path -LiteralPath $tempWt)) {
            $linked = $tempWt
            $usedTemp = $true
        } else {
            $tempWt = $null
            $problems += 'could not create a temporary worktree - allow side could not be verified'
        }
    }

    if ($hookHere -and $linked -and (Test-Path -LiteralPath $linked)) {
        $code2 = Invoke-Hook $hookPath $linked
        $label = if ($usedTemp) { 'temporary worktree' } else { 'linked worktree' }
        if ($code2 -ne 0) {
            $problems += ('REVERSE CHECK FAILED: pre-commit also refused a ' + $label + ' (' + $linked + ') - the guard blocks all work')
        } else {
            Say ('reverse check OK - hook allows the ' + $label + ': ' + $linked)
        }
    } elseif (-not $hookHere) {
        # Charter section 0: report unverified as unverified. Do not claim a pass.
        $notes += 'linked-worktree side UNVERIFIED - hook file not present yet'
    }
}
finally {
    # Must run even when a check above threw. A leaked worktree would make the
    # NEXT run pick it up as a real one, and a leaked temp dir is litter.
    if ($tempWt) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & git -C $Repo worktree remove --force $tempWt *>&1 | Out-Null
        if (Test-Path -LiteralPath $tempWt) {
            Remove-Item -LiteralPath $tempWt -Recurse -Force -ErrorAction SilentlyContinue
        }
        & git -C $Repo worktree prune *>&1 | Out-Null
        $ErrorActionPreference = $prev

        if (Test-Path -LiteralPath $tempWt) {
            $problems += ('temporary worktree left behind: ' + $tempWt)
        } else {
            Say 'temporary worktree cleaned up'
        }
    }
}

# --- 6. REVERSE CHECK (targeting) - another clone must give ITS OWN answer ---
# The checks above all pass while reading the WRONG repo, which is exactly how
# the 2026-08-15 bug survived: every run reported the same clone, so the answer
# looked stable and therefore trustworthy. Charter section 0 says feed a
# detector the input that MUST trip it. Here that input is a different repo.
#
# Aim a nested run at a throwaway repo that cannot possibly pass, then require
# that the output (a) names that repo and (b) does not say OK. A hardcoded or
# ignored target reproduces this run's verdict instead and fails both.
# -Fix is deliberately NOT forwarded - fixing the probe would make it pass.
if (-not $NoSelfTest) {
    $probe = Join-Path ([System.IO.Path]::GetTempPath()) ('repo-guard-probe-' + [guid]::NewGuid().ToString('N'))
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        New-Item -ItemType Directory -Path $probe -Force | Out-Null
        & git init -q $probe *>&1 | Out-Null

        $out = (& powershell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath `
                    -Repo $probe -NoSelfTest *>&1 | Out-String)

        if ($out -notmatch [regex]::Escape($probe)) {
            $problems += ('TARGETING CHECK FAILED: a run aimed at ' + $probe +
                          ' never named it - the -Repo target is being ignored')
        } elseif ($out -match '(?m)^STATUS: OK') {
            $problems += ('TARGETING CHECK FAILED: an unconfigured repo (' + $probe +
                          ') reported STATUS: OK')
        } else {
            Say 'targeting check OK - a run aimed at another repo reports that repo, not this one'
        }
    } finally {
        Remove-Item -LiteralPath $probe -Recurse -Force -ErrorAction SilentlyContinue
        $ErrorActionPreference = $prev
    }
}

# --- report -----------------------------------------------------------------
foreach ($n in $notes) { Say ('NOTE: ' + $n) }

if ($problems.Count -gt 0) {
    Write-Host ''
    foreach ($p in $problems) { Write-Host ('  - ' + $p) }
    Write-Host ''
    Write-Host ('  (repo: ' + $Repo + ')')
    Write-Host ''
    Write-Host ('STATUS: FAIL repo-guard (' + $problems.Count + ')')
    exit 1
}

Say ('OK - repo=' + $Repo + ', hooksPath=' + $have + ', primary on ' + $branch)
Write-Host 'STATUS: OK'
exit 0
