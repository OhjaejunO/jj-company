#requires -Version 5.1
#
# JJ Company OS - schedule log writer (shared by every wrapper)
#
# ASCII-only on purpose (see any schedule script header for why).
#
# WHY
#   2026-08-20: three wrappers ran to completion but their logs stopped after the
#   stagger line. Nothing was wrong with the wrappers - a `tail -f` from a
#   monitoring session held the three log files open, and `Add-Content` fails
#   with an IOException when the file is held that way. The wrappers ran with the
#   default $ErrorActionPreference ("Continue"), so every log line after that
#   point was dropped without a trace while the run itself kept going: locks were
#   taken, source_watch wrote its file, one report was produced - and the log
#   said none of it happened.
#
#   That is the charter section 0 failure mode exactly: a recording path that
#   fails silently is worse than no recording, because the log then reads as
#   "the run died here" when the run did not die.
#
# WHAT THIS FIXES
#   1. Open with FileShare.ReadWrite so a reader (tail -f, an editor, another
#      agent) cannot block the append. This alone removes the observed failure.
#   2. Retry a few times with a short backoff for the transient case (another
#      writer holds it for a moment).
#   3. If it still fails, DO NOT return quietly: write the line to a side file
#      (<log>.overflow) and echo it to stderr. The scheduler captures stderr, so
#      the line survives somewhere no matter what.
#
#   BOM: existing logs were written by Add-Content -Encoding UTF8 (which emits a
#   BOM on PS 5.1). We append without a BOM - a BOM belongs at the start of a
#   file, not in the middle of one, and readers handle the mix fine.
#
# USAGE
#   . (Join-Path $Hq 'scripts\logging.ps1')
#   function Write-Log { param([string]$Message) Write-LogLine -Path $LogFile -Message $Message }

function Write-LogLine {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Message,
        [int]$Attempts = 5
    )
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
    $enc  = New-Object System.Text.UTF8Encoding $false

    for ($i = 0; $i -lt $Attempts; $i++) {
        $fs = $null
        $sw = $null
        try {
            # FileShare.ReadWrite is the whole point - a reader must not block us.
            $fs = New-Object System.IO.FileStream(
                $Path,
                [System.IO.FileMode]::Append,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::ReadWrite)
            $sw = New-Object System.IO.StreamWriter($fs, $enc)
            $sw.WriteLine($line)
            $sw.Flush()
            return $true
        } catch {
            Start-Sleep -Milliseconds (50 * ($i + 1))
        } finally {
            if ($sw) { $sw.Dispose() }
            elseif ($fs) { $fs.Dispose() }
        }
    }

    # Every attempt failed. Losing the line silently is the bug we are fixing,
    # so put it somewhere a human can still find.
    try {
        [System.IO.File]::AppendAllText($Path + '.overflow', $line + [Environment]::NewLine, $enc)
    } catch { }
    try {
        [Console]::Error.WriteLine('WRITE-LOG FAILED (' + $Path + '): ' + $line)
    } catch { }
    return $false
}
