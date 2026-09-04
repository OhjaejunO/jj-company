#requires -Version 5.1
#
# JJ Company OS - morning-vault-health (grade A, read-only vault audit)
# Charter section 4 (scheduling protocol) compliance.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes BOM-less .ps1 files as
# the system ANSI codepage, which mangles Korean. The Korean agent prompt lives
# in scripts\prompts\morning-vault-health.md and is read as explicit UTF-8.

$ErrorActionPreference = 'Continue'

$Task       = 'morning-vault-health'
# Start stagger (2026-08-19). All four tasks are StartWhenAvailable, so after a
# sleep/reboot they all fire in the same second and race on "git pull" in this
# shared tree (see scripts\git-sync.ps1). Time triggers have no deterministic
# delay in Task Scheduler, so the offset lives here: drift 0 / vault 2 /
# scout 4 / job 6 minutes. Applied to every run, not only catch-up runs - the
# scheduled times are 30 min apart so the shift is harmless there.
$StartDelayMinutes = 2

$Hq         = 'C:\Users\ojaej\jj-company'
$Claude     = 'C:\Users\ojaej\.local\bin\claude.exe'
# ponytail plugin trial (2026-09-04, dev sessions only): user default is lite; scheduled agents must not get the ruleset -> off here.
$env:PONYTAIL_DEFAULT_MODE = 'off'
$PromptFile = Join-Path $Hq 'scripts\prompts\morning-vault-health.md'

# Read access to the vault is granted per-run via --add-dir (least privilege).
# Do NOT move this into settings.json additionalDirectories: that would grant
# every session read access. The Edit() deny rule keeps writes blocked either way.
$VaultPath  = 'C:\Obsidian.JJ\JJ-Brain'

$Stamp    = Get-Date -Format 'yyyyMMdd'
$IsoDate  = Get-Date -Format 'yyyy-MM-dd'
$LogDir   = Join-Path $Hq 'logs\scheduled'
$LogFile  = Join-Path $LogDir ($Task + '_' + $Stamp + '.log')
$LockFile = Join-Path $Hq ('logs\' + $Task + '.lock')

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Shared writer (2026-08-20): Add-Content dies with an IOException when any
# reader holds the log open (a `tail -f` did exactly that and every line after
# the stagger was dropped silently). scripts\logging.ps1 opens with
# FileShare.ReadWrite, retries, and spills to <log>.overflow + stderr rather
# than losing the line. Fallback stays inline so logging works even if the
# helper is missing.
$LogHelper = Join-Path $Hq 'scripts\logging.ps1'
if (Test-Path -LiteralPath $LogHelper) { . $LogHelper }

function Write-Log {
    param([string]$Message)
    if (Get-Command Write-LogLine -ErrorAction SilentlyContinue) {
        [void](Write-LogLine -Path $LogFile -Message $Message)
        return
    }
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

# --- lock gate: charter 4 requires an immediate exit when the lock exists ---
if (Test-Path -LiteralPath $LockFile) {
    Write-Log ('lock file present: ' + $LockFile + ' -- aborting, another run owns it')
    Write-Log 'STATUS: FAIL lock-exists'
    exit 2
}

Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ') ===')

# Stagger BEFORE the lock (2026-08-21). On 8/20 all three wrappers died during
# this sleep and left their locks behind, which would have blocked the next
# morning outright (the gate above exits 2 on a stale lock). The finally block
# cannot cover that case: no PowerShell cleanup runs when the process is killed
# from outside. Holding no lock while we only sleep removes the failure mode.
# Started stamp (2026-08-25). On 8/25 two wrappers were killed by a reboot
# during this sleep: the log ended at 'start stagger' with no STATUS line, no
# report, no lock and no scheduler completion event - nothing anyone would
# notice. The stamp is written BEFORE the sleep and removed on every normal
# exit path (finally below), so a leftover stamp whose pid is dead means
# exactly "died without a record". scripts\run_audit.py reads it and the
# ops-auditor turns it into a red item. Not a lock: it never blocks a run.
$StartedFile = Join-Path $Hq ('logs\' + $Task + '.started')
Set-Content -LiteralPath $StartedFile -Encoding UTF8 -Value ('pid=' + $PID + ' started=' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Log ('started stamp: ' + $StartedFile)

if ($StartDelayMinutes -gt 0) {
    Write-Log ('start stagger: sleeping ' + $StartDelayMinutes + ' min')
    Start-Sleep -Seconds ($StartDelayMinutes * 60)
    # First mark after the sleep. 8/20 could not be traced past the stagger line
    # because nothing was written until the git step - this line makes "did it
    # come back from the sleep at all" answerable from the log alone.
    Write-Log ('stagger complete: resuming after ' + $StartDelayMinutes + ' min')
}

# Re-check: another run may have taken the lock while this one slept.
if (Test-Path -LiteralPath $LockFile) {
    Write-Log ('lock file present after stagger: ' + $LockFile + ' -- aborting')
    Write-Log 'STATUS: FAIL lock-exists'
    Remove-Item -LiteralPath $StartedFile -Force -ErrorAction SilentlyContinue
    exit 2
}

$lockTaken = $false
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    Write-Log ('lock acquired: ' + $LockFile)

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

    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

    # --- charter 4: sync the operations server to latest main before working ---
    Set-Location -LiteralPath $Hq
    Write-Log ('cwd: ' + (Get-Location).Path)
    # Retry (2026-08-19): see scripts\git-sync.ps1 header - a wake-up stampede
    # made three wrappers pull the same tree in the same second and two lost.
    $SyncHelper = Join-Path $Hq 'scripts\git-sync.ps1'
    if (-not (Test-Path -LiteralPath $SyncHelper)) {
        Write-Log ('git sync helper missing: ' + $SyncHelper)
        Write-Log 'STATUS: FAIL git-sync-helper-missing'
        exit 1
    }
    . $SyncHelper
    # Quote-safe prompt passing (2026-08-19): see scripts\native-arg.ps1 - PS 5.1
    # cut the -p prompt at its first inner double quote and dropped the rest.
    $ArgHelper = Join-Path $Hq 'scripts\native-arg.ps1'
    if (-not (Test-Path -LiteralPath $ArgHelper)) {
        Write-Log ('native arg helper missing: ' + $ArgHelper)
        Write-Log 'STATUS: FAIL arg-helper-missing'
        exit 1
    }
    . $ArgHelper
    $pull = Invoke-GitPullRetry -Log ${function:Write-Log}
    if (-not $pull.Ok) {
        Write-Log 'STATUS: FAIL git-sync'
        exit 1
    }

    # --- auth / mount pre-flight BEFORE the skill sync (moved 2026-08-28) -------
    #
    # It used to run after the agent's data collection, which is one step too late:
    # on 8/27 an expired gh token made deploy-skill's "git fetch" fail with
    # "could not read Username for 'https://github.com'", the wrapper aborted at
    # STATUS: FAIL skill-sync, and the check that would have NAMED the cause never
    # ran. Three jobs died the same way that morning with the same cryptic line.
    # The diagnostic must not sit behind the step it diagnoses.
    #
    # Still NOT fatal on its own (charter section 4 - STATUS means "did the work
    # complete"). It only records facts; the agent raises the flag in the report.
    $DataDir  = Join-Path $Hq 'logs\audit-data'
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $AuthData = Join-Path $DataDir ('auth_' + $IsoDate + '.txt')
    # cp949 stdout mangles the Korean values these scripts print (see the longer
    # note at the vault_audit call below). Set once here - the pre-flight needs it too.
    $env:PYTHONIOENCODING = 'utf-8'
    Write-Log ('auth_check.py -> ' + $AuthData)
    $AuthPy = Join-Path $Hq 'scripts\auth_check.py'
    $authAllOk = 'unknown'
    if (-not (Test-Path -LiteralPath $AuthPy)) {
        Write-Log ('auth check script missing: ' + $AuthPy + ' - recording as unavailable')
        Set-Content -LiteralPath $AuthData -Value 'UNAVAILABLE' -Encoding UTF8
    } else {
        $authOut  = & py $AuthPy 2>&1
        $authCode = $LASTEXITCODE
        if ($authCode -ne 0) {
            Write-Log ('auth_check.py exit code ' + $authCode + ' - recording as unavailable')
            Set-Content -LiteralPath $AuthData -Value 'UNAVAILABLE' -Encoding UTF8
        } else {
            Set-Content -LiteralPath $AuthData -Value $authOut -Encoding UTF8
        }
        foreach ($l in $authOut) { Write-Log ('  auth| ' + $l) }
        $m = $authOut | Select-String -Pattern '^AUTH_ALL_OK=(\S+)' | Select-Object -First 1
        if ($m) { $authAllOk = $m.Matches[0].Groups[1].Value }
    }
    Write-Log ('auth all ok: ' + $authAllOk)

    # Same charter 4 step, second half (2026-08-15): the live rulebook is synced
    # here too. The live skill folder is a plain copy of origin/main now, so
    # nothing updates it unless we push it - a stale live folder is exactly the
    # silent failure this structure was built to remove.
    $Deploy = Join-Path $Hq 'scripts\deploy-skill.ps1'
    if (-not (Test-Path -LiteralPath $Deploy)) {
        Write-Log ('skill deploy script missing: ' + $Deploy)
        Write-Log 'STATUS: FAIL skill-sync'
        exit 1
    }
    Write-Log 'deploy-skill (live <- origin/main)'
    $depOut  = & powershell -NoProfile -ExecutionPolicy Bypass -File $Deploy 2>&1
    $depCode = $LASTEXITCODE
    foreach ($l in $depOut) { Write-Log ('  skill| ' + $l) }
    if ($depCode -ne 0) {
        Write-Log ('deploy-skill exit code ' + $depCode)
        # Name the cause in the STATUS line itself (2026-08-28). run_audit.py reads
        # this line and the next morning's report carries the reason verbatim, so
        # "skill-sync" alone would send the reader back into the log. When the
        # pre-flight above already said the credentials are gone, say so here.
        if ($authAllOk -eq 'no') {
            Write-Log 'STATUS: FAIL skill-sync-auth (gh/drive pre-flight said AUTH_ALL_OK=no)'
        } else {
            Write-Log 'STATUS: FAIL skill-sync'
        }
        exit 1
    }

    # --- grade boundary (2026-08-18): collect data BEFORE the agent runs ---
    #
    # The auditor used to hold the Bash tool so it could run vault_audit.py itself.
    # Bash also opens git and gh, and permissions in Claude Code are per-session,
    # not per-agent - so a grade A agent inherited the project allowlist including
    # Bash(gh pr *). Nothing in settings could scope that down.
    #
    # So the wrapper runs the data collection and the agent only reads the output.
    # Bash is removed from its tools: the boundary is now tool absence, not a rule.
    # See docs\ops-grade-boundary.md.
    $VaultData = Join-Path $DataDir ('vault_' + $IsoDate + '.txt')
    $PrData    = Join-Path $DataDir ('openprs_' + $IsoDate + '.txt')

    $AuditPy = Join-Path $Hq 'scripts\vault_audit.py'
    if (-not (Test-Path -LiteralPath $AuditPy)) {
        Write-Log ('audit script missing: ' + $AuditPy)
        Write-Log 'STATUS: FAIL audit-script-missing'
        exit 1
    }
    # Python on Windows encodes stdout as the ANSI codepage (cp949 here), so Korean
    # values arrived as mojibake that still decoded as valid UTF-8 - the file looked
    # fine and only the values were unreadable (charter section 0, silent failure).
    # Measured 2026-08-18: BACKUP_STATUS went from unreadable bytes to
    # "BACKUP_STATUS=<Korean>" with this one variable set.
    # Same pattern the content-ops query in departments\marketing\config.md uses.
    $env:PYTHONIOENCODING = 'utf-8'

    Write-Log ('vault_audit.py -> ' + $VaultData)
    $auditOut  = & py $AuditPy 2>&1
    $auditCode = $LASTEXITCODE
    # stdout carries KEY=value lines; stderr carries progress. Keep both, the agent
    # needs the values and we need the progress when something goes wrong.
    Set-Content -LiteralPath $VaultData -Value $auditOut -Encoding UTF8
    if ($auditCode -ne 0) {
        Write-Log ('vault_audit.py exit code ' + $auditCode)
        Write-Log 'STATUS: FAIL vault-audit'
        exit 1
    }
    # An empty or value-less file would let the agent report "no problems found"
    # off nothing at all. Prove the file actually carries values before continuing.
    $auditProbe = Select-String -LiteralPath $VaultData -Pattern '^BROKEN_LINKS_COUNT=' -Quiet
    if (-not $auditProbe) {
        Write-Log ('vault data has no BROKEN_LINKS_COUNT line: ' + $VaultData)
        Write-Log 'STATUS: FAIL vault-audit-empty'
        exit 1
    }
    Write-Log ('vault data ok (' + (Get-Item -LiteralPath $VaultData).Length + ' bytes)')

    # Open PR list (charter: gh pr list is a read, so it stays inside grade A -
    # but the agent no longer has Bash, so the wrapper produces it).
    Write-Log ('gh pr list -> ' + $PrData)
    $prOut  = & gh pr list --state open --json number,title,createdAt,mergeStateStatus 2>&1
    $prCode = $LASTEXITCODE
    if ($prCode -ne 0) {
        # Not fatal: a vault report is still worth producing. Record the failure so
        # the agent writes "unverified" instead of silently reporting zero open PRs.
        Write-Log ('gh pr list exit code ' + $prCode + ' - recording as unavailable')
        Set-Content -LiteralPath $PrData -Value 'UNAVAILABLE' -Encoding UTF8
        foreach ($l in $prOut) { Write-Log ('  gh| ' + $l) }
    } else {
        Set-Content -LiteralPath $PrData -Value $prOut -Encoding UTF8
        Write-Log ('open pr data ok (' + (Get-Item -LiteralPath $PrData).Length + ' bytes)')
    }

    # Operations-server freshness. The agent has no Bash, so git state must be
    # collected here. Measured 2026-08-18: this tree sat 14 commits behind
    # origin/main while scheduled jobs kept running against the stale copy.
    $FreshData = Join-Path $DataDir ('freshness_' + $IsoDate + '.txt')
    Write-Log ('freshness -> ' + $FreshData)
    $null = & git fetch origin 2>&1
    $behind = & git rev-list --count 'HEAD..origin/main' 2>&1
    $fetchOk = $LASTEXITCODE
    $localHead = & git rev-parse --short HEAD 2>&1
    if ($fetchOk -ne 0 -or $behind -notmatch '^\d+$') {
        Write-Log ('freshness check failed - recording as unavailable')
        Set-Content -LiteralPath $FreshData -Value 'UNAVAILABLE' -Encoding UTF8
    } else {
        $lines = @(('BEHIND_COUNT=' + $behind), ('LOCAL_HEAD=' + $localHead))
        Set-Content -LiteralPath $FreshData -Value $lines -Encoding UTF8
        Write-Log ('freshness ok (behind ' + $behind + ', head ' + $localHead + ')')
    }

    # Silent-death detection (2026-08-25): logs that start but never reach a
    # STATUS line, and leftover .started stamps with a dead pid. Same shape as
    # the vault data - the wrapper produces it, the agent only reads it.
    $RunsData = Join-Path $DataDir ('runs_' + $IsoDate + '.txt')
    $RunsPy   = Join-Path $Hq 'scripts\run_audit.py'
    Write-Log ('run_audit.py -> ' + $RunsData)
    if (-not (Test-Path -LiteralPath $RunsPy)) {
        Write-Log ('run audit script missing: ' + $RunsPy + ' - recording as unavailable')
        Set-Content -LiteralPath $RunsData -Value 'UNAVAILABLE' -Encoding UTF8
    } else {
        $runsOut  = & py $RunsPy --date $IsoDate 2>&1
        $runsCode = $LASTEXITCODE
        if ($runsCode -ne 0 -or -not ($runsOut -match '^RUNS_VERDICT=')) {
            Write-Log ('run_audit.py exit code ' + $runsCode + ' - recording as unavailable')
            foreach ($l in $runsOut) { Write-Log ('  runs| ' + $l) }
            Set-Content -LiteralPath $RunsData -Value 'UNAVAILABLE' -Encoding UTF8
        } else {
            Set-Content -LiteralPath $RunsData -Value $runsOut -Encoding UTF8
            foreach ($l in $runsOut) { Write-Log ('  runs| ' + $l) }
        }
    }

    if (-not (Test-Path -LiteralPath $PromptFile)) {
        Write-Log ('prompt file missing: ' + $PromptFile)
        Write-Log 'STATUS: FAIL prompt-missing'
        exit 1
    }
    $prompt = (Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8).Replace('{{DATE}}', $IsoDate)
    $prompt = $prompt.Replace('{{VAULT_DATA}}', $VaultData).Replace('{{PR_DATA}}', $PrData)
    $prompt = $prompt.Replace('{{FRESH_DATA}}', $FreshData).Replace('{{RUNS_DATA}}', $RunsData)
    $prompt = $prompt.Replace('{{AUTH_DATA}}', $AuthData)
    $ProbeData = Join-Path $DataDir ('probe_' + $IsoDate + '.txt')
    $prompt = $prompt.Replace('{{PROBE_DATA}}', $ProbeData)

    Write-Log ('claude -p (ops-auditor) start, --add-dir ' + $VaultPath)
    # Whitelist from ACTUAL tool calls in the 6 scheduled runs after the 2026-08-18
    # ops-auditor overhaul (CLAUDE.md section 4). Pre-overhaul runs also used Edit
    # and Monitor; excluded on purpose - this is a grade-A read-only job and Edit
    # does not belong to it. Evidence: session transcripts under
    # ~/.claude/projects/C--Users-ojaej-jj-company/, matched 1:1 against the
    # 'claude -p (ops-auditor) start' lines in this job's own log files.
    # If a run fails on a missing tool, add it FROM THE LOG - do not guess.
    #
    # Gate trial (2026-08-25, this job only; JJ verdict after 8/26-8/28).
    # Four days of transcripts showed the list was not the gate: under
    # acceptEdits the main session ran Edit 9 times (not on the list) and it
    # went through. With --permission-mode default a headless run has nobody to
    # ask, so anything outside the list is refused instead of silently allowed.
    # File writing is therefore listed WITH a path: only reports\ is writable.
    # Measured 2026-08-25: Claude Code warns that 'Write(path)' rules are not
    # consulted by file permission checks - 'Edit(path)' rules cover every
    # file-editing tool (Write included). Same fact as the deny note in
    # CLAUDE.md section 2. So one Edit rule, not a Write rule. Probe: Write and
    # Edit under reports\ passed, Write under docs\ was refused.
    # Trial verdict 2026-08-28: 8/26 and 8/28 completed with STATUS: OK and no
    # refusal-caused failure; 8/27 never reached the agent (skill-sync, see above),
    # so it carries no evidence either way. Kept, and now proven per run by the
    # probe below rather than by this block being present in the file.
    $AllowedTools = @(
        'Agent', 'Bash', 'Glob', 'Grep', 'Read', 'SendMessage', 'ToolSearch',
        'Edit(reports/**)'
    )

    # --- approval-refusal probe, every run (2026-08-28) -----------------------
    #
    # The gate above is a flag on a command line. Nothing proved it was still
    # closed ON THIS RUN: a revert to acceptEdits, a typo in the list, a BOM in
    # settings.json - all of them leave the report looking exactly the same.
    # Charter section 0: a detector must be shown to actually hold a value.
    #
    # So the run first tries, for real, to write one file it must NOT be able to
    # write (docs\) and one it must (reports\). Both directions, because refusal
    # alone cannot tell a working gate from a session that refuses everything.
    # The verdict is the FILES, not what the bot says about them.
    # A failing probe aborts the run: an open gate means the next step would be an
    # ungated agent, which is the thing being guarded against.
    $ProbePy = Join-Path $Hq 'scripts\permission_probe.py'
    if (-not (Test-Path -LiteralPath $ProbePy)) {
        Write-Log ('permission probe missing: ' + $ProbePy)
        Write-Log 'STATUS: FAIL probe-script-missing'
        exit 1
    }
    $ProbeDeny  = Join-Path $Hq 'docs\_probe_should_fail.md'
    $ProbeAllow = Join-Path $Hq 'reports\_probe_ok.md'
    Write-Log ('permission_probe.py -> ' + $ProbeData)
    $probeOut = & py $ProbePy --cwd $Hq --deny $ProbeDeny --allow $ProbeAllow `
        --add-dir $VaultPath '--' @AllowedTools 2>&1
    $probeCode = $LASTEXITCODE
    Set-Content -LiteralPath $ProbeData -Value $probeOut -Encoding UTF8
    foreach ($l in $probeOut) { Write-Log ('  probe| ' + $l) }
    if ($probeCode -ne 0) {
        $pv = ($probeOut | Select-String -Pattern '^PROBE_VERDICT=' | Select-Object -Last 1)
        Write-Log ('STATUS: FAIL probe ' + $(if ($pv) { $pv.Line } else { 'no verdict line' }))
        exit 1
    }

    $out        = & $Claude -p (ConvertTo-NativeArg $prompt) --permission-mode default `
        --allowed-tools @AllowedTools `
        --add-dir $VaultPath 2>&1
    $claudeCode = $LASTEXITCODE
    foreach ($l in $out) { Write-Log ('  cc| ' + $l) }
    Write-Log ('claude exit code ' + $claudeCode)

    if ($claudeCode -ne 0) {
        Write-Log ('STATUS: FAIL claude-exit-' + $claudeCode)
        exit 1
    }

    $Report = Join-Path $Hq ('reports\' + $IsoDate + '_' + $Task + '.md')
    if (-not (Test-Path -LiteralPath $Report)) {
        Write-Log ('report missing: ' + $Report)
        Write-Log 'STATUS: FAIL report-missing'
        exit 1
    }

    # The report file is the artifact of record (charter section 5), so the verdict
    # is read from its trailing STATUS line. Agent stdout is a conversational summary
    # and does not reliably carry the STATUS line.
    $reportStatus = (Select-String -LiteralPath $Report -Pattern '^STATUS:' | Select-Object -Last 1).Line
    if ($null -eq $reportStatus) {
        Write-Log ('no STATUS line in report: ' + $Report)
        Write-Log 'STATUS: FAIL report-status-missing'
        exit 1
    }
    Write-Log ('report status line: ' + $reportStatus)
    if ($reportStatus -notmatch 'STATUS:\s*OK') {
        Write-Log 'STATUS: FAIL agent-status-not-ok'
        exit 1
    }

    Write-Log ('report: ' + $Report)
    Write-Log 'STATUS: OK'
    exit 0
}
finally {
    if ($lockTaken -and (Test-Path -LiteralPath $LockFile)) {
        Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
        Write-Log 'lock released'
    }
    # Every exit inside the try block (including 'exit N') passes through here.
    # Only an external kill skips it - which is precisely what the stamp reports.
    if (Test-Path -LiteralPath $StartedFile) {
        Remove-Item -LiteralPath $StartedFile -Force -ErrorAction SilentlyContinue
        Write-Log 'started stamp removed'
    }
}
