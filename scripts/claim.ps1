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
# WHEN THE HOLDER IS GONE (2026-09-13)
#   A session that ends without releasing used to lock its topic forever, and
#   nothing could tell that from a claim taken a second ago. Measured that day:
#   ep58-class101 had been held since 01:11 by a process that was no longer
#   running, and the next session asking for it was simply refused.
#   Now the file records the SESSION process (found by walking up the parent
#   chain), and a take whose holder is provably gone says STALE and proceeds.
#   Three states, and only one of them acts: alive -> refuse, gone -> take over,
#   unknown -> refuse and print the release command. "Cannot tell" never means
#   "go ahead" (charter section 0).
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

# ONE directory per machine, not one per clone.
#
# The default used to be "<the repo this script lives in>\logs\claims", and this
# repo has more than one working copy: the workshop tree and the operations
# server. Measured 2026-09-13: seven claims sat in the workshop tree's directory
# and one in the operations server's, and neither side could see the other - so
# two sessions could hold "the same" topic at once and both be told OK. That is
# the exact collision this script exists to prevent, and it had been open the
# whole time because the header said "per machine" while the code said "per
# clone" (charter section 0: the real thing is the authority, not the sentence).
$CLAIM_DIR_MACHINE = 'C:\Users\ojaej\jj-company\logs\claims'

function Resolve-ClaimDir([string]$ScriptRoot, [string]$MachineDir) {
    if (Test-Path -LiteralPath (Split-Path -Parent $MachineDir)) { return $MachineDir }
    # Somewhere else entirely (another machine, a fresh clone). Fall back to the
    # old repo-relative directory, but SAY so - a silent fallback would bring
    # back the split this change closes.
    $d = Join-Path (Split-Path -Parent $ScriptRoot) 'logs\claims'
    Say ('WARNING - machine claim dir not found, using this clone only: ' + $d)
    return $d
}

if (-not $Dir) { $Dir = Resolve-ClaimDir $PSScriptRoot $CLAIM_DIR_MACHINE }
New-Item -ItemType Directory -Path $Dir -Force | Out-Null

# WHOSE claim is it - a handle that outlives this script.
#
# The file used to record `pid: $PID`, which is THIS process: claim.ps1 exits a
# moment after writing it, so that number is dead by the time anyone reads it.
# It looked like a liveness handle and was not one - the exact shape charter
# section 0 warns about (a field that carries no value still reads as evidence).
# Measured 2026-09-13: a claim from a session that ended at 01:11 was still held
# at 19:00, and nothing could tell that from a claim taken a second ago.
#
# The session process CAN be found by walking up: claim.ps1 -> bash -> ... ->
# claude.exe (measured: depth 4 from a Bash tool call). That process lives as
# long as the session does, so it is the handle. Start time goes in the file
# too: pids are reused, and "pid 21980 exists" is not "pid 21980 is still that
# session".
$OWNER_NAMES = @('claude.exe', 'codex.exe', 'node.exe')
$OWNER_MAX_DEPTH = 8

function Get-OwnerHandle {
    $p = $PID
    for ($i = 0; $i -lt $OWNER_MAX_DEPTH; $i++) {
        $o = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $p) -ErrorAction SilentlyContinue
        if (-not $o) { return $null }
        if ($OWNER_NAMES -contains $o.Name) {
            return [pscustomobject]@{
                Pid     = [int]$o.ProcessId
                Name    = [string]$o.Name
                Started = (Get-Date $o.CreationDate -Format 'yyyy-MM-dd HH:mm:ss')
            }
        }
        $p = [int]$o.ParentProcessId
        if ($p -le 0) { return $null }
    }
    return $null
}

# 'alive' / 'gone' / 'unknown'. 'unknown' is NOT 'gone': a claim we cannot judge
# is never taken away from whoever holds it (charter section 0 - "confirm or say
# you could not confirm", never guess in the direction that acts).
function Get-ClaimOwnerState([string[]]$Lines) {
    $pidLine   = $Lines | Where-Object { $_ -like 'owner_pid:*' }     | Select-Object -First 1
    $nameLine  = $Lines | Where-Object { $_ -like 'owner_name:*' }    | Select-Object -First 1
    $startLine = $Lines | Where-Object { $_ -like 'owner_started:*' } | Select-Object -First 1
    if (-not $pidLine -or -not $nameLine -or -not $startLine) { return 'unknown' }
    $opid  = ($pidLine  -replace '^owner_pid:\s*',     '').Trim()
    $oname = ($nameLine -replace '^owner_name:\s*',    '').Trim()
    $ostar = ($startLine -replace '^owner_started:\s*', '').Trim()
    if ($opid -notmatch '^\d+$') { return 'unknown' }
    $o = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $opid) -ErrorAction SilentlyContinue
    if (-not $o) { return 'gone' }
    # Same pid, different process: Windows reuses pids, and a reused pid must not
    # keep a dead session's lock alive.
    if ($o.Name -ne $oname) { return 'gone' }
    if ((Get-Date $o.CreationDate -Format 'yyyy-MM-dd HH:mm:ss') -ne $ostar) { return 'gone' }
    return 'alive'
}

# THE one way to read a claim file. -Encoding UTF8 is not optional: the file is
# written UTF-8 (goals carry Korean) and PS 5.1 reads with the ANSI codepage by
# default, which turned the goal line - the line that tells the next session
# what is already being done - into garbage (measured 2026-09-13 at byte level).
# Both the refusal and -List go through here so there is one place to get right.
function Read-ClaimLines([string]$Path) {
    return @(Get-Content -LiteralPath $Path -Encoding UTF8)
}

function Get-ClaimPath([string]$t) {
    if ($t -notmatch '^[A-Za-z0-9_.-]{1,64}$') {
        throw ('topic must be [A-Za-z0-9_.-]{1,64}: ' + $t)
    }
    return (Join-Path $Dir ($t + '.claim'))
}

function Take([string]$t, [string]$g) {
    $p = Get-ClaimPath $t
    if (Test-Path -LiteralPath $p) {
        $held = Read-ClaimLines $p
        $state = Get-ClaimOwnerState -Lines $held
        if ($state -eq 'gone') {
            # The holder's session is provably over. Leaving the file would make
            # this a permanent lock on work nobody is doing, which is the
            # opposite of what the claim is for.
            Say ('STALE - ' + $t + ' was held by a session that is no longer running; taking it over:')
            $held | ForEach-Object { Write-Host ('    ' + $_) }
            Remove-Item -LiteralPath $p -Force
        } else {
            Say ('REFUSED - ' + $t + ' is already claimed (owner: ' + $state + '):')
            $held | ForEach-Object { Write-Host ('    ' + $_) }
            if ($state -eq 'unknown') {
                Say 'owner cannot be identified - release it by hand if that session is gone:'
                Say ('    powershell -File scripts\claim.ps1 -Topic ' + $t + ' -Release')
            }
            Write-Host 'STATUS: FAIL claim (held)'
            return 1
        }
    }
    $owner = Get-OwnerHandle
    $body = @(
        ('topic: ' + $t),
        ('goal:  ' + $g),
        ('since: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')),
        ('user:  ' + $env:USERNAME + '@' + $env:COMPUTERNAME),
        ('cwd:   ' + (Get-Location).ProviderPath)
    )
    if ($owner) {
        $body += ('owner_pid:     ' + $owner.Pid)
        $body += ('owner_name:    ' + $owner.Name)
        $body += ('owner_started: ' + $owner.Started)
    } else {
        # Say so instead of writing a number that means nothing. A claim with no
        # owner is never auto-released - it just cannot be judged.
        $body += 'owner_pid:     (not found - this claim cannot be judged stale)'
    }
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

    # One directory per machine. Two clones of this repo must land on the SAME
    # place, or a claim taken in one is invisible to the other - measured
    # 2026-09-13 with seven claims here and one there.
    $dirA = Resolve-ClaimDir 'C:\Users\ojaej\orca\jj-company\scripts' $CLAIM_DIR_MACHINE
    $dirB = Resolve-ClaimDir 'C:\Users\ojaej\jj-company\scripts'      $CLAIM_DIR_MACHINE
    if ($dirA -ne $dirB) { $fails++; Say ('SELFTEST: two clones resolved to different dirs: ' + $dirA + ' vs ' + $dirB) }
    # ...and the fallback is still there for a machine that has no such path -
    # without this case, "always return the constant" would pass the line above.
    $dirC = Resolve-ClaimDir 'C:\nowhere\repo\scripts' 'C:\nowhere\at\all\claims'
    if ($dirC -ne 'C:\nowhere\repo\logs\claims') { $fails++; Say ('SELFTEST: fallback dir wrong: ' + $dirC) }

    # The goal must survive being written and read back. It is the one line that
    # tells the next session what is already being done, and goals are Korean -
    # PS 5.1 reads with the ANSI codepage unless told otherwise, which turned
    # that line into garbage (measured 2026-09-13 at byte level).
    # This file is ASCII-only, so the sample is built from code points.
    $ko = -join ([char]0xD55C, [char]0xAE00, [char]0x20, [char]0xBAA9, [char]0xD45C)   # "Korean goal"
    $tKo = $t + '-ko'
    Take $tKo $ko | Out-Null
    $readBack = Read-ClaimLines (Get-ClaimPath $tKo)
    $goalLine = $readBack | Where-Object { $_ -like 'goal:*' } | Select-Object -First 1
    if ($goalLine -notlike ('*' + $ko + '*')) { $fails++; Say ('SELFTEST: the goal did not survive the round trip: ' + $goalLine) }
    Free $tKo | Out-Null

    # Staleness. Each case gets its OWN claim file: if two cases shared one, a
    # pass would not say which rule earned it (charter section 0 - separate the
    # reverse-check inputs).
    function Plant([string]$topic, [string[]]$ownerLines) {
        $pp = Get-ClaimPath $topic
        $b = @(('topic: ' + $topic), 'goal:  planted', ('since: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))) + $ownerLines
        [IO.File]::WriteAllLines($pp, $b, (New-Object System.Text.UTF8Encoding $false))
        return $pp
    }

    # A pid that is really gone: start one, let it exit, then use its number.
    $dead = Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile', '-Command', 'exit' -PassThru -WindowStyle Hidden
    $dead.WaitForExit()
    $deadPid = $dead.Id
    $live = Get-OwnerHandle

    $tDead = $t + '-dead'
    Plant $tDead @(('owner_pid:     ' + $deadPid), 'owner_name:    powershell.exe', 'owner_started: 2020-01-01 00:00:00') | Out-Null
    if ((Take $tDead 'take over the dead') -ne 0) { $fails++; Say 'SELFTEST: a claim from a dead session was NOT taken over' }
    Free $tDead | Out-Null

    # ...and the direction that matters more: a LIVE owner keeps its claim. A
    # rule that frees everything would pass the case above on its own.
    if ($live) {
        $tLive = $t + '-live'
        Plant $tLive @(('owner_pid:     ' + $live.Pid), ('owner_name:    ' + $live.Name), ('owner_started: ' + $live.Started)) | Out-Null
        if ((Take $tLive 'must be refused') -eq 0) { $fails++; Say 'SELFTEST: a LIVE session lost its claim' }
        Free $tLive | Out-Null

        # Pid reuse: same number, different process. Without the start-time
        # comparison this reads as alive and the lock never clears.
        $tReuse = $t + '-reuse'
        Plant $tReuse @(('owner_pid:     ' + $live.Pid), ('owner_name:    ' + $live.Name), 'owner_started: 2020-01-01 00:00:00') | Out-Null
        if ((Take $tReuse 'reused pid is not the same session') -ne 0) { $fails++; Say 'SELFTEST: a reused pid kept a dead session alive' }
        Free $tReuse | Out-Null

        # ...and the other half of pid reuse: the number is live but it is some
        # other program now. Start time alone would call this one alive, so this
        # case is what makes the NAME comparison load-bearing.
        $tName = $t + '-name'
        Plant $tName @(('owner_pid:     ' + $live.Pid), 'owner_name:    notreal.exe', ('owner_started: ' + $live.Started)) | Out-Null
        if ((Take $tName 'a different program on the same pid') -ne 0) { $fails++; Say 'SELFTEST: a pid belonging to another program read as the same session' }
        Free $tName | Out-Null
    } else {
        Say 'SELFTEST: no owner process found - live-owner cases SKIPPED (not proven)'
    }

    # No owner fields at all (a claim written by the old version): unjudgeable,
    # so it is refused, never taken. "Cannot tell" must not act like "gone".
    $tOld = $t + '-old'
    Plant $tOld @('pid:   4') | Out-Null
    if ((Take $tOld 'must be refused') -eq 0) { $fails++; Say 'SELFTEST: an unjudgeable claim was taken over' }
    Free $tOld | Out-Null

    if ($fails -gt 0) { Write-Host ('STATUS: FAIL claim-selftest (' + $fails + ')'); exit 1 }
    Say 'selftest OK - duplicate refused, release frees, re-take passes, dead owner yields, live owner does not'
    Write-Host 'STATUS: OK'
    exit 0
}

if ($List) {
    $items = Get-ChildItem -LiteralPath $Dir -Filter '*.claim' -ErrorAction SilentlyContinue
    if (-not $items) { Say 'no claims'; Write-Host 'STATUS: OK'; exit 0 }
    foreach ($i in $items) {
        Write-Host ('--- ' + $i.Name)
        Read-ClaimLines $i.FullName | ForEach-Object { Write-Host ('    ' + $_) }
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
