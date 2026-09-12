# .codex/hooks/sessionstart.ps1 -- Codex SessionStart: drop the timestamp the Stop gate measures from.
#
# Why: the Claude Stop gate finds "which episode did this session touch" by parsing the Claude
# transcript JSONL. Codex writes no such file, so that axis cannot be ported as-is. What the gate
# actually needs is not "what was written" but "which episode folder changed during this session",
# and a file mtime answers that without any transcript. This hook writes the "session started"
# mark; .codex/hooks/stop.ps1 compares episode folders against it.
#
# Codex runs hooks with the session cwd as working directory, so paths are repo-relative.
# ASCII only on purpose - see charter section 3 on hook output.

$ErrorActionPreference = 'Continue'
$raw = ''
try { $raw = [Console]::In.ReadToEnd() } catch { }

$logDir = Join-Path (Get-Location) 'logs\hooks'
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

try {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    [IO.File]::WriteAllText($stamp, (Get-Date).ToString('o'), (New-Object Text.UTF8Encoding $false))
    # payload_keys is recorded because the Codex Stop/SessionStart payload shape is not documented
    # anywhere we can read; the first real session tells us which id field actually arrives.
    $rec = @{
        ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        event = 'SessionStart'
        cwd = (Get-Location).Path
        session = $sid
        payload_keys = $keys
        stdin_bytes = $raw.Length
        stamp = $stamp
    } | ConvertTo-Json -Compress
    [IO.File]::AppendAllText((Join-Path $logDir 'codex-stop-gate.jsonl'), $rec + "`n", (New-Object Text.UTF8Encoding $false))
} catch { }
exit 0
