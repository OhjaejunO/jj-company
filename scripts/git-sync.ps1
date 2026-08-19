#requires -Version 5.1
#
# JJ Company OS - "git pull origin main" with retry, for the schedule wrappers.
# 2026-08-19 diagnosis "wake-up stampede".
#
# ASCII-only on purpose (see any schedule script header for why).
#
# WHY
#   On 2026-08-19 the PC slept through 07:00-08:30 and woke at 11:40. All four
#   tasks have StartWhenAvailable, so all four fired at 11:46:15 and three of
#   them ran "git pull origin main" in the SAME working tree at the same second.
#   One won; the other two died with
#     error: fetching ref refs/remotes/origin/main failed: incorrect old value provided
#   and exited "STATUS: FAIL git-sync". Nothing was wrong with git or the
#   network - the ref was updated between their read and their write. Two
#   morning reports were lost to a one-second race.
#
#   The stagger in each wrapper (0/2/4/6 min) is the primary fix. This retry is
#   the second layer: it turns a transient ref race into a 5-second pause instead
#   of a lost run. It does NOT retry forever - a real network/auth failure still
#   ends in FAIL git-sync after 3 attempts, and every attempt is logged, so a
#   retry that "fixed" something is visible in the log, not hidden.
#
# USAGE
#   . (Join-Path $Hq 'scripts\git-sync.ps1')
#   $r = Invoke-GitPullRetry -Log ${function:Write-Log}
#   if (-not $r.Ok) { Write-Log 'STATUS: FAIL git-sync'; exit 1 }
#
# The caller must already be in the repo directory (Set-Location $Hq).

function Invoke-GitPullRetry {
    param(
        [scriptblock]$Log,
        [int]$Retries = 2,
        [int]$DelaySeconds = 5,
        [string]$Remote = 'origin',
        [string]$Branch = 'main'
    )
    $attempts = $Retries + 1
    for ($i = 1; $i -le $attempts; $i++) {
        & $Log ('git pull ' + $Remote + ' ' + $Branch + ' (attempt ' + $i + '/' + $attempts + ')')
        $out  = & git pull $Remote $Branch 2>&1
        $code = $LASTEXITCODE
        foreach ($l in $out) { & $Log ('  git| ' + $l) }
        if ($code -eq 0) {
            if ($i -gt 1) { & $Log ('git pull succeeded on retry ' + $i) }
            return @{ Ok = $true; Attempts = $i; ExitCode = 0 }
        }
        & $Log ('git pull exit code ' + $code)
        if ($i -lt $attempts) {
            & $Log ('retrying in ' + $DelaySeconds + 's')
            Start-Sleep -Seconds $DelaySeconds
        }
    }
    return @{ Ok = $false; Attempts = $attempts; ExitCode = $code }
}
