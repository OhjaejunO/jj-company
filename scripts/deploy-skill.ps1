#requires -Version 5.1
#
# JJ Company OS - skill deployment (one-way, main only)
# Charter section 2 / 2026-08-15 diagnosis "SKILL symlink structure" plan 1.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as
# the system ANSI codepage, which mangles non-ASCII text.
#
# WHY THIS EXISTS
#   ~\.claude\skills\tomangchi used to be a SYMLINK into the working repo, so
#   whatever branch that repo had checked out became the live rulebook for every
#   session and every scheduled run. A session that stepped onto a feature branch
#   and walked away silently downgraded everyone else to unreviewed rules.
#   Nothing errored. Nothing logged which revision actually ran.
#
#   So the live skill is now a REAL folder that only ever receives origin/main,
#   pushed here by this script. Same shape as the schedule scripts syncing the
#   operations server with "git pull origin main" - live is always main.
#
# WHAT IT DOES NOT DO
#   It never touches the source repo's working tree, HEAD, or branches. It reads
#   origin/main as a tree object. Run it while any branch is checked out.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-skill.ps1
#   powershell ... -File scripts\deploy-skill.ps1 -WhatIf     (dry run)

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Repo = 'C:\Users\ojaej\orca\tomangchi-skill',
    [string]$SubPath = 'skills/tomangchi',
    [string]$Live = 'C:\Users\ojaej\.claude\skills\tomangchi'
)

$ErrorActionPreference = 'Stop'

function Say([string]$m) { Write-Host ('[deploy-skill] ' + $m) }

# Charter section 4 contract: a failed sync must be loud and machine-readable.
# The caller (a schedule script) greps this line and aborts the run - a stale or
# half-written rulebook must never be what a scheduled agent reads.
function Die([string]$reason) {
    Write-Host ('[deploy-skill] STATUS: FAIL skill-sync ' + $reason)
    exit 1
}

trap { Die $_.Exception.Message }

if (-not (Test-Path -LiteralPath $Repo)) { Die ('source repo missing: ' + $Repo) }

# --- read origin/main WITHOUT touching the repo working tree -----------------
#
# Never let git open an interactive credential prompt (2026-08-28). On 8/27 an
# expired gh token sent this fetch down the prompt path, where it spent time on
# "bash: line 1: /dev/tty: No such device or address" before dying with
# "could not read Username for 'https://github.com'". A scheduled run has no
# terminal, so the prompt can only ever fail - say so up front and get a clean
# error instead of a misleading one.
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'

# Retry like scripts\git-sync.ps1 does for the operations server: a wake-up
# stampede or a flaky network is transient and a single attempt turns it into a
# skipped run. An auth failure is NOT transient, so it breaks out immediately -
# retrying an expired token three times only delays the report by ten seconds.
$fetchErr = ''
$fetchOk = $false
foreach ($attempt in 1..3) {
    Say ('git fetch origin (attempt ' + $attempt + '/3)')
    # ErrorActionPreference is 'Stop' for this script, and under PowerShell 5.1 a
    # native command writing to stderr under '2>&1' then raises NativeCommandError,
    # which the trap at the top turns into an immediate Die. That skipped the retry
    # loop entirely and threw away the classification below - measured while writing
    # this. git talks on stderr even when it succeeds, so the preference is lifted
    # for the call and restored right after.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $fetchOut = & git -C $Repo fetch --quiet origin 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -eq 0) { $fetchOk = $true; break }
    $fetchErr = ($fetchOut | Out-String).Trim()
    foreach ($l in $fetchOut) { Say ('  git| ' + $l) }
    if ($fetchErr -match 'could not read Username|Authentication failed|terminal prompts disabled|Invalid username or token|401|403') {
        Die ('git fetch failed: credentials (gh token expired or missing) - run "gh auth login"')
    }
    if ($attempt -lt 3) { Start-Sleep -Seconds 5 }
}
if (-not $fetchOk) { Die ('git fetch failed after 3 attempts: ' + $fetchErr) }

$Sha = (& git -C $Repo rev-parse --short origin/main).Trim()
$Full = (& git -C $Repo rev-parse origin/main).Trim()
$When = (& git -C $Repo log -1 --format=%cI origin/main).Trim()
$Subj = (& git -C $Repo log -1 --format=%s origin/main).Trim()
Say ('origin/main = ' + $Sha + '  (' + $When + ')')

# Already current? Then nothing to do - keeps the schedule fast and idempotent.
$Stamp = Join-Path $Live '.deployed'
if ((Test-Path -LiteralPath $Live) -and (Test-Path -LiteralPath $Stamp)) {
    $prev = (Get-Content -LiteralPath $Stamp -Raw -Encoding UTF8)
    if ($prev -match [regex]::Escape($Full)) {
        Say 'already at origin/main - nothing to do'
        exit 0
    }
}

# --- replace the live folder atomically-ish ---------------------------------
# A symlink must be removed as a reparse point. Remove-Item -Recurse on a
# directory symlink can follow it and delete the TARGET, so the link case is
# handled with rmdir, which deletes the link only.
$item = $null
if (Test-Path -LiteralPath $Live) { $item = Get-Item -LiteralPath $Live -Force }
$isLink = $item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)

$Staging = $Live + '.new'
$Backup = $Live + '.old'
if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }

if ($PSCmdlet.ShouldProcess($Live, 'deploy origin/main')) {
    New-Item -ItemType Directory -Force -Path $Staging | Out-Null

    # git archive gives the subtree at the archive root, so it lands flat.
    # ZIP, not tar: "tar" on this box resolves to Git Bash's /usr/bin/tar, which
    # reads a "C:\..." path as a remote host and dies with "Cannot connect to C".
    # Expand-Archive ships with PowerShell and has no PATH ambiguity.
    Say ('export ' + $SubPath + ' -> staging')
    $zipPath = Join-Path $env:TEMP ('skill_' + $Sha + '.zip')
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    & git -C $Repo archive --format=zip -o $zipPath ('origin/main:' + $SubPath)
    if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $Staging -Force
    Remove-Item -LiteralPath $zipPath -Force

    $count = (Get-ChildItem -LiteralPath $Staging -Recurse -File).Count
    if ($count -lt 1) { throw 'staging is empty - refusing to deploy' }
    if (-not (Test-Path -LiteralPath (Join-Path $Staging 'SKILL.md'))) {
        throw 'SKILL.md missing in staging - refusing to deploy'
    }
    Say ($count.ToString() + ' files staged')

    # Record which revision is live. This is the line the schedule logs read -
    # the live folder is no longer a git repo, so rev-parse on it means nothing.
    # One field per line, UTF-8 with NO BOM.
    #   - not -join "`n": an earlier build joined with the default output field
    #     separator (a space) and produced a single-line stamp the log parser
    #     read as empty.
    #   - not Set-Content -Encoding UTF8: PowerShell 5.1 writes a BOM there, and
    #     charter section 2 bans BOM for exactly the parse failures it causes.
    # Every element is parenthesised on purpose. In PowerShell the comma operator
    # binds TIGHTER than '+', so an unparenthesised list like
    #     @('a: ' + $x, 'b: ' + $y)
    # parses as  'a: ' + ($x, 'b: ') + $y  -> ONE joined string, not two elements.
    # That is what produced the earlier single-line stamp.
    $stampLines = [string[]]@(
        ('revision: ' + $Full),
        ('short: ' + $Sha),
        ('committed: ' + $When),
        ('subject: ' + $Subj),
        ('deployed: ' + (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')),
        ('source: ' + $Repo + ' (origin/main)')
    )
    [IO.File]::WriteAllLines($Stamp.Replace($Live, $Staging), $stampLines,
                             (New-Object Text.UTF8Encoding $false))

    if ($item) {
        if ($isLink) {
            Say 'removing old SYMLINK (reparse point only - target untouched)'
            & cmd.exe /c rmdir "`"$Live`"" | Out-Null
        } else {
            Say 'moving old folder aside'
            Move-Item -LiteralPath $Live -Destination $Backup
        }
    }
    Move-Item -LiteralPath $Staging -Destination $Live
    if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }

    Say ('live = ' + $Live + '  @ ' + $Sha)
}
exit 0
