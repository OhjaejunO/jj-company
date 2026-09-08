# .codex/hooks/pretooluse.ps1 -- Codex PreToolUse wrapper around the shared bash-escape-guard.
#
# Why a wrapper: on 2026-09-08 Codex showed "Hook failed - exited with code 1" and then ran the
# command anyway. Nothing recorded what the hook received or returned, so the failure could not
# be diagnosed (charter section 0: a detector must be shown to carry a value). This layer writes
# one JSON line per call to logs\hooks\codex-pretooluse.jsonl (logs\ is gitignored), then runs
# the real guard on the same stdin and exits with the guard's exit code (2 = block).
#
# Codex runs hooks with the session cwd as working directory, so paths are repo-relative.
# ASCII only on purpose - see charter section 3 on hook output.

$ErrorActionPreference = 'Continue'
$raw = [Console]::In.ReadToEnd()
$logDir = Join-Path (Get-Location) 'logs\hooks'
$logFile = Join-Path $logDir 'codex-pretooluse.jsonl'
$guard = Join-Path (Get-Location) '.claude\hooks\bash-escape-guard.ps1'

$toolName = ''; $cmd = ''
try {
    $p = $raw | ConvertFrom-Json
    $toolName = [string]$p.tool_name
    if ($p.tool_input -and $p.tool_input.command) { $cmd = [string]$p.tool_input.command }
} catch { }

function Write-HookLog([string]$verdict, [int]$code) {
    try {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $rec = @{
            ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            cwd = (Get-Location).Path
            tool_name = $toolName
            command = $cmd.Substring(0, [Math]::Min(200, $cmd.Length))
            stdin_bytes = $raw.Length
            verdict = $verdict
            exit = $code
        } | ConvertTo-Json -Compress
        [IO.File]::AppendAllText($logFile, $rec + "`n", (New-Object Text.UTF8Encoding $false))  # no BOM (charter section 6)
    } catch { }
}

if (-not (Test-Path -LiteralPath $guard)) {
    Write-HookLog 'guard-missing' 1
    [Console]::Error.WriteLine("codex pretooluse wrapper: guard not found at $guard (cwd=$((Get-Location).Path))")
    exit 1
}

$out = $raw | & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $guard 2>&1
$code = $LASTEXITCODE
$reason = if ($out) { ($out | Out-String).TrimEnd() } else { '' }
if ($reason) { [Console]::Error.WriteLine($reason) }
if ($code -eq 2) {
    # Codex source (codex-rs/hooks/src/events/pre_tool_use.rs): exit 2 blocks ONLY if stderr is
    # non-empty as Codex captured it, and then stdout is ignored; exit 0 + JSON permissionDecision
    # 'deny' blocks via the parsed block_reason regardless of stderr. 2026-09-09 00:21 measured:
    # exit 2 was logged here as 'block' yet the command still ran - stderr evidently arrived empty.
    # So: emit the deny JSON on stdout and exit 0. The guard's text still goes to stderr for humans.
    if (-not $reason) { $reason = 'blocked by bash-escape-guard (no reason text captured)' }
    $deny = @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = 'deny'; permissionDecisionReason = $reason } } | ConvertTo-Json -Compress -Depth 4
    [Console]::Out.WriteLine($deny)
    Write-HookLog 'block' 0
    exit 0
}
Write-HookLog $(if ($code -eq 0) { 'pass' } else { 'error' }) $code
exit $code
