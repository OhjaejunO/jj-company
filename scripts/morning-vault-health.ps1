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

function Write-Log {
    param([string]$Message)
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

# --- lock gate: charter 4 requires an immediate exit when the lock exists ---
if (Test-Path -LiteralPath $LockFile) {
    Write-Log ('lock file present: ' + $LockFile + ' -- aborting, another run owns it')
    Write-Log 'STATUS: FAIL lock-exists'
    exit 2
}

$lockTaken = $false
try {
    New-Item -ItemType File -Path $LockFile -Force | Out-Null
    $lockTaken = $true
    Write-Log ('=== ' + $Task + ' start (pid ' + $PID + ') ===')
    if ($StartDelayMinutes -gt 0) {
        Write-Log ('start stagger: sleeping ' + $StartDelayMinutes + ' min')
        Start-Sleep -Seconds ($StartDelayMinutes * 60)
    }

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
        Write-Log 'STATUS: FAIL skill-sync'
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
    $DataDir  = Join-Path $Hq 'logs\audit-data'
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
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

    if (-not (Test-Path -LiteralPath $PromptFile)) {
        Write-Log ('prompt file missing: ' + $PromptFile)
        Write-Log 'STATUS: FAIL prompt-missing'
        exit 1
    }
    $prompt = (Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8).Replace('{{DATE}}', $IsoDate)
    $prompt = $prompt.Replace('{{VAULT_DATA}}', $VaultData).Replace('{{PR_DATA}}', $PrData)
    $prompt = $prompt.Replace('{{FRESH_DATA}}', $FreshData)

    Write-Log ('claude -p (ops-auditor) start, --add-dir ' + $VaultPath)
    $out        = & $Claude -p (ConvertTo-NativeArg $prompt) --permission-mode acceptEdits --add-dir $VaultPath 2>&1
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
}
