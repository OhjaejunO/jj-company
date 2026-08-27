#requires -Version 5.1
#
# JJ Company OS - guard self-check for the shell re-interpretation guard
# Charter section 0 (a detector that never trips is worse than none) + design doc
# docs\design-bash-escape-guard.md section 4.
#
# ASCII-only on purpose (see any wrapper header).
#
# WHY THIS EXISTS
#   A Claude Code hook that is missing, unreadable or broken is a NON-BLOCKING
#   error: the tool call runs anyway and nothing says the guard is gone. That is
#   the same shape as core.hooksPath silently missing (charter section 3), so the
#   guard needs its own checker, and the checker must test BOTH directions:
#   dangerous input must be refused, ordinary input must pass. A guard that
#   refuses everything looks identical to a working one if you only test one side.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-bash-guard.ps1
#   ... -Guard <path>   check a specific guard script (default: repo .claude\hooks\)

[CmdletBinding()]
param(
    [string]$Guard,
    [string]$Settings
)

$ErrorActionPreference = 'Stop'
$problems = @()
$notes = @()
function Say([string]$m) { Write-Host ('[bash-guard] ' + $m) }

$repo = Split-Path -Parent $PSScriptRoot
if (-not $Guard) { $Guard = Join-Path $repo '.claude\hooks\bash-escape-guard.ps1' }
if (-not $Settings) { $Settings = Join-Path $repo '.claude\settings.json' }
Say ('guard   : ' + $Guard)
Say ('settings: ' + $Settings)

# --- 1. the guard script exists ---------------------------------------------
if (-not (Test-Path -LiteralPath $Guard)) {
    Say 'guard script MISSING - every Bash call is unguarded right now'
    Write-Host 'STATUS: FAIL bash-guard (no-script)'
    exit 1
}

# --- 2. it is registered as a PreToolUse hook --------------------------------
# Registration lives in settings.json, which git DOES carry - unlike core.hooksPath.
# Still checked here: a merge or an edit can drop it and nothing would say so.
if (Test-Path -LiteralPath $Settings) {
    $raw = Get-Content -LiteralPath $Settings -Raw -Encoding UTF8
    if ($raw.Length -gt 0 -and [int]$raw[0] -eq 0xFEFF) {
        $problems += 'settings.json starts with a BOM - the whole file fails to parse (charter section 2)'
    }
    try {
        $cfg = $raw | ConvertFrom-Json
        $found = $false
        foreach ($item in @($cfg.hooks.PreToolUse)) {
            foreach ($h in @($item.hooks)) {
                if ([string]$h.command -match 'bash-escape-guard') { $found = $true }
            }
        }
        if (-not $found) { $problems += 'PreToolUse hook for bash-escape-guard is NOT registered in settings.json' }
        else { Say 'registration OK - PreToolUse/Bash points at the guard' }
    } catch {
        $problems += ('settings.json does not parse: ' + $_.Exception.Message)
    }
} else {
    $problems += ('settings.json missing: ' + $Settings)
}

# --- 3. REVERSE CHECK - feed the guard the inputs it must refuse / allow -----
# The cases below are fed to the REAL script over stdin, exactly as Claude Code
# feeds it. Verdict logic therefore lives in one place only.
function Invoke-Guard([string]$Command) {
    $payload = @{ hook_event_name = 'PreToolUse'; tool_name = 'Bash'; tool_input = @{ command = $Command } } | ConvertTo-Json -Depth 5 -Compress
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($tmp, $payload, (New-Object System.Text.UTF8Encoding $false))
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $out = (Get-Content -LiteralPath $tmp -Raw | & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Guard 2>&1)
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prev
        return @{ code = $code; out = ($out -join ' ') }
    } finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}

# BLOCK cases - the three real incidents of 2026-08-27/08-25 plus one evasion.
# If a fixture below stops being refused, the guard has regressed to a no-op.
$bt = [char]0x60          # backtick, kept out of the literals below
$cases = @(
    @{ name = 'INCIDENT-1 mem update (-c " with backtick)'; block = $true;
       cmd  = 'cd /memory && py -c "' + "`n" + 'import io' + "`n" + 't=t.replace(' + $bt + 'gh auth login -h github.com' + $bt + ', x)' + "`n" + '"' },
    @{ name = 'INCIDENT-2 PR ledger (-c " with backtick)'; block = $true;
       cmd  = 'py -c "t += ' + $bt + 'scenes.self_test()' + $bt + ' + rest"' },
    @{ name = 'INCIDENT-3 unquoted heredoc with backslash'; block = $true;
       cmd  = 'py - <<EOF' + "`n" + 'import re' + "`n" + 're.sub(r"(a)", r"\1", s)' + "`n" + 'EOF' },
    @{ name = 'EVASION command substitution in -c'; block = $true;
       cmd  = 'py -c "print($(cat secrets.txt))"' },
    @{ name = 'EVASION shell var in -c'; block = $true;
       cmd  = 'py -c "print(''$HOME'')"' },
    @{ name = 'SAFE quoted heredoc with backticks'; block = $false;
       cmd  = 'py - <<' + "'EOF'" + "`n" + 'print("' + $bt + 'not a command' + $bt + '")' + "`n" + 'EOF' },
    @{ name = 'SAFE single-quoted -c'; block = $false;
       cmd  = "py -c 'import io; print(1)'" },
    @{ name = 'SAFE ordinary regex in quotes'; block = $false;
       cmd  = "grep -n '\d+' file.txt && git commit -m ""fix: something""" },
    @{ name = 'SAFE plain git/gh call'; block = $false;
       cmd  = 'gh pr view 8 --json state,mergeable --jq ".state"' }
)

$fails = 0
foreach ($c in $cases) {
    $r = Invoke-Guard $c.cmd
    $blocked = ($r.code -eq 2)
    $good = ($blocked -eq $c.block)
    if (-not $good) { $fails++ }
    $verdict = if ($good) { 'OK  ' } else { 'FAIL' }
    $what = if ($blocked) { 'blocked' } else { 'passed ' }
    Say ($verdict + ' ' + $what + ' | ' + $c.name)
    if (-not $good) { Say ('       guard said: ' + $r.out) }
}
if ($fails -gt 0) { $problems += ("reverse check: $fails case(s) wrong") }

# --- 4. REVERSE CHECK (missing guard) - the checker itself must notice -------
# Charter section 0: prove the absence branch works, do not assume it.
$ghost = Join-Path ([System.IO.Path]::GetTempPath()) ('no-guard-' + [guid]::NewGuid().ToString('N') + '.ps1')
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$probe = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -Guard $ghost -Settings $Settings *>&1 | Out-String)
$probeCode = $LASTEXITCODE
$ErrorActionPreference = $prev
if ($probeCode -eq 0 -or $probe -notmatch 'no-script') {
    $problems += 'ABSENCE CHECK FAILED: a run aimed at a missing guard did not report no-script'
} else {
    Say 'absence check OK - a missing guard is reported, not silently passed'
}

foreach ($n in $notes) { Say ('NOTE: ' + $n) }
if ($problems.Count -gt 0) {
    Write-Host ''
    foreach ($p in $problems) { Write-Host ('  - ' + $p) }
    Write-Host ''
    Write-Host ('STATUS: FAIL bash-guard (' + $problems.Count + ')')
    exit 1
}
Say ('OK - guard present, registered, ' + $cases.Count + ' reverse cases correct')
Write-Host 'STATUS: OK'
exit 0
