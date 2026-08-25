#requires -Version 5.1
#
# JJ Company OS - session claim (charter section 3, 2026-08-25)
#
# ASCII-only on purpose (see check-repo-guard.ps1).
#
# WHY THIS EXISTS
#   git worktrees keep two sessions from sharing HEAD. They do NOT keep two
#   sessions from doing the SAME job. 2026-08-25: one session left another
#   version of handoff_schema.py untracked in the primary tree while a second
#   session shipped PR #70 with a different one; the same day two sessions were
#   about to edit verify.py for two different features and only a human notice
#   ("this session touches the pre-flight section only") kept them apart.
#
#   A claim is a file: logs\claims\<topic>.claim. Take it when you start a job,
#   release it when you finish. If it already exists you are refused and told
#   who holds it and since when. Claims live under logs\ (gitignored) - they are
#   per machine, and sessions run on one machine, so that is enough.
#
# USAGE
#   powershell -File scripts\claim.ps1 -Topic <topic> [-Goal "<one line>"]   take
#   powershell -File scripts\claim.ps1 -Topic <topic> -Release               release
#   powershell -File scripts\claim.ps1 -List                                 show all
#   powershell -File scripts\claim.ps1 -SelfTest                             reverse check
#
# EXIT  0 taken / released / listed     1 refused (already claimed)     2 usage

[CmdletBinding()]
param(
    [string]$Topic,
    [string]$Goal = '',
    [switch]$Release,
    [switch]$List,
    [switch]$SelfTest,
    # where claims live; default is <repo>\logs\claims next to this script
    [string]$Dir
)

$ErrorActionPreference = 'Stop'
function Say([string]$m) { Write-Host ('[claim] ' + $m) }

if (-not $Dir) {
    $root = Split-Path -Parent $PSScriptRoot
    $Dir = Join-Path $root 'logs\claims'
}
New-Item -ItemType Directory -Path $Dir -Force | Out-Null

function Get-ClaimPath([string]$t) {
    if ($t -notmatch '^[A-Za-z0-9_.-]{1,64}$') {
        throw ('topic must be [A-Za-z0-9_.-]{1,64}: ' + $t)
    }
    return (Join-Path $Dir ($t + '.claim'))
}

function Take([string]$t, [string]$g) {
    $p = Get-ClaimPath $t
    if (Test-Path -LiteralPath $p) {
        Say ('REFUSED - ' + $t + ' is already claimed:')
        Get-Content -LiteralPath $p | ForEach-Object { Write-Host ('    ' + $_) }
        Write-Host 'STATUS: FAIL claim (held)'
        return 1
    }
    $body = @(
        ('topic: ' + $t),
        ('goal:  ' + $g),
        ('since: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')),
        ('pid:   ' + $PID),
        ('user:  ' + $env:USERNAME + '@' + $env:COMPUTERNAME),
        ('cwd:   ' + (Get-Location).ProviderPath)
    )
    # ASCII body; goal may carry Korean - write UTF-8 without BOM (charter 6).
    [IO.File]::WriteAllLines($p, $body, (New-Object System.Text.UTF8Encoding $false))
    Say ('taken - ' + $p)
    Write-Host 'STATUS: OK'
    return 0
}

function Free([string]$t) {
    $p = Get-ClaimPath $t
    if (-not (Test-Path -LiteralPath $p)) {
        Say ('nothing to release - ' + $t + ' was not claimed')
        Write-Host 'STATUS: OK'
        return 0
    }
    Remove-Item -LiteralPath $p -Force
    Say ('released - ' + $t)
    Write-Host 'STATUS: OK'
    return 0
}

if ($SelfTest) {
    # Charter section 0: a guard that never refuses is worse than none. Take a
    # throwaway topic twice - the second take MUST be refused - then release and
    # take again - which MUST pass. Both sides, or the test proves nothing.
    $t = 'selftest-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    $fails = 0
    if ((Take $t 'selftest') -ne 0) { $fails++; Say 'SELFTEST: first take was refused' }
    if ((Take $t 'selftest-dup') -eq 0) { $fails++; Say 'SELFTEST: duplicate take was NOT refused' }
    if ((Free $t) -ne 0) { $fails++; Say 'SELFTEST: release failed' }
    if ((Take $t 'selftest-again') -ne 0) { $fails++; Say 'SELFTEST: take after release was refused' }
    Free $t | Out-Null
    if ($fails -gt 0) { Write-Host ('STATUS: FAIL claim-selftest (' + $fails + ')'); exit 1 }
    Say 'selftest OK - duplicate refused, release frees, re-take passes'
    Write-Host 'STATUS: OK'
    exit 0
}

if ($List) {
    $items = Get-ChildItem -LiteralPath $Dir -Filter '*.claim' -ErrorAction SilentlyContinue
    if (-not $items) { Say 'no claims'; Write-Host 'STATUS: OK'; exit 0 }
    foreach ($i in $items) {
        Write-Host ('--- ' + $i.Name)
        Get-Content -LiteralPath $i.FullName | ForEach-Object { Write-Host ('    ' + $_) }
    }
    Write-Host 'STATUS: OK'
    exit 0
}

if (-not $Topic) {
    Write-Host 'usage: claim.ps1 -Topic <topic> [-Goal "..."] | -Topic <topic> -Release | -List | -SelfTest'
    exit 2
}

if ($Release) { exit (Free $Topic) }
exit (Take $Topic $Goal)
