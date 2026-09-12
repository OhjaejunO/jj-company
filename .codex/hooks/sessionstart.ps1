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

# The unread-RED briefing (charter section 4: the reading place is the start of a session).
# Only the briefing is ported. context_watch's handoff memo is NOT: reading it RENAMES the file to
# .consumed.md, so a Codex session would eat a memo written for the Claude session. Read-only here.
$brief = ''
try {
    $sb = Join-Path (Get-Location) 'scripts\session_brief.py'
    if (Test-Path -LiteralPath $sb) {
        # PS 5.1 decodes native stdout with the ANSI code page unless told otherwise (the Korean
        # briefing arrived as mojibake in cross-verify for exactly this reason, 2026-09-11).
        try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
        $env:PYTHONIOENCODING = 'utf-8'
        $o = & py $sb --hook 2>$null
        if ($o) { $brief = ($o | Out-String).Trim() }
    }
} catch { $brief = '[session-brief] lookup failed: ' + $_.Exception.Message }

try {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    [IO.File]::WriteAllText($stamp, (Get-Date).ToString('o'), (New-Object Text.UTF8Encoding $false))
    if ($brief) {
        # Two ways out on purpose. The JSON is the Claude-shaped SessionStart contract and Codex has
        # matched that schema everywhere we could measure (PreToolUse), but the SessionStart response
        # shape is NOT documented - so the same text also lands in a file the session can be told to
        # read. Which one actually arrives is settled by the first real session, not by us guessing.
        [IO.File]::WriteAllText((Join-Path $logDir 'codex-brief.txt'), $brief, (New-Object Text.UTF8Encoding $false))
        $ctx = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $brief } } | ConvertTo-Json -Compress -Depth 4
        [Console]::Out.WriteLine($ctx)
    }
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
        brief_bytes = $brief.Length
    } | ConvertTo-Json -Compress
    [IO.File]::AppendAllText((Join-Path $logDir 'codex-stop-gate.jsonl'), $rec + "`n", (New-Object Text.UTF8Encoding $false))
} catch { }
exit 0
