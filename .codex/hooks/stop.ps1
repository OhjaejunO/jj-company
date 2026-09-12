# .codex/hooks/stop.ps1 -- Codex Stop: run the episode gate before the session is allowed to finish.
#
# Why: charter section 3 registered gate-on-stop for Claude so a session cannot say "done" while a
# deck fails its gate. Codex had the same hole and AGENTS.md carried it as a layer-4 "cannot catch".
# The Stop event does exist in Codex (measured 2026-09-13 in the Orca runtime hooks.json); what was
# missing was an episode-selection axis that does not read a Claude transcript. That axis is now
# --codex in .claude\hooks\gate_on_stop.py: episodes whose files changed after the SessionStart
# stamp. This wrapper owns the Codex-side protocol and nothing else.
#
# Exit contract of the gate: 0 = nothing to block, 3 = gate failed.
# ASCII only on purpose - see charter section 3 on hook output.

$ErrorActionPreference = 'Continue'
$raw = ''
try { $raw = [Console]::In.ReadToEnd() } catch { }

$logDir = Join-Path (Get-Location) 'logs\hooks'
$logFile = Join-Path $logDir 'codex-stop-gate.jsonl'
$gate = Join-Path (Get-Location) '.claude\hooks\gate_on_stop.py'

$sid = 'default'
$keys = ''
try {
    $p = $raw | ConvertFrom-Json
    $keys = (($p.PSObject.Properties | ForEach-Object { $_.Name }) -join ',')
    foreach ($k in @('session_id', 'sessionId', 'thread_id', 'threadId', 'conversation_id')) {
        $v = $p.$k
        if ($v) { $sid = [string]$v; break }
    }
} catch { }
$safe = ($sid -replace '[^A-Za-z0-9_.-]', '_')
$stamp = Join-Path $logDir ('codex-session-' + $safe + '.stamp')

function Write-HookLog([string]$verdict, [int]$code, [string]$note) {
    try {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        $rec = @{
            ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            event = 'Stop'
            cwd = (Get-Location).Path
            session = $sid
            payload_keys = $keys
            stdin_bytes = $raw.Length
            stamp_exists = (Test-Path -LiteralPath $stamp)
            verdict = $verdict
            exit = $code
            note = $note.Substring(0, [Math]::Min(400, $note.Length))
        } | ConvertTo-Json -Compress
        [IO.File]::AppendAllText($logFile, $rec + "`n", (New-Object Text.UTF8Encoding $false))
    } catch { }
}

if (-not (Test-Path -LiteralPath $gate)) {
    Write-HookLog 'gate-missing' 0 $gate
    [Console]::Error.WriteLine("codex stop gate: gate script not found at $gate")
    exit 0
}

# The gate prints Korean; PS 5.1 decodes native stdout with the ANSI code page unless told otherwise.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = 'utf-8'
$out = & py $gate --codex --stamp $stamp 2>&1
$code = $LASTEXITCODE
$text = if ($out) { ($out | Out-String).TrimEnd() } else { '' }

if ($code -eq 3) {
    if (-not $text) { $text = 'gate-codex: gate failed (no report text captured)' }
    [Console]::Error.WriteLine($text)
    # Same lesson as PreToolUse (2026-09-09): a non-zero exit was ignored while stdout JSON was
    # honoured. So the decision is carried as JSON on stdout with exit 0. The Stop payload/response
    # shape is NOT documented for Codex - the jsonl above records what actually arrives so the first
    # real session can settle it instead of us guessing twice.
    $block = @{ decision = 'block'; reason = $text } | ConvertTo-Json -Compress -Depth 4
    [Console]::Out.WriteLine($block)
    # Re-stamp so the next Stop only sees folders edited AFTER this block: one block per change,
    # never a loop on an untouched failure.
    try { [IO.File]::WriteAllText($stamp, (Get-Date).ToString('o'), (New-Object Text.UTF8Encoding $false)) } catch { }
    Write-HookLog 'block' 0 $text
    exit 0
}

if ($text) { [Console]::Error.WriteLine($text) }
Write-HookLog $(if ($code -eq 0) { 'pass' } else { 'error' }) $code $text
exit 0
