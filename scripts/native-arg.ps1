#requires -Version 5.1
#
# JJ Company OS - quote a string so a native .exe receives it INTACT as one arg.
# 2026-08-19 diagnosis "prompt cut at the first double quote".
#
# ASCII-only on purpose (see any schedule script header for why).
#
# WHY
#   Windows PowerShell 5.1 does not escape embedded double quotes when it hands
#   an argument to a native executable. It wraps the value in "..." because it
#   contains spaces, and leaves every inner " as-is - so the receiving process
#   sees the argument END at the first inner quote and the rest of the text
#   arrive as extra, unquoted arguments.
#
#   Measured 2026-08-19 with an argv echo:
#     $p = 'aaa bbb (x "check" y) ccc'   ->   ['-p', 'aaa bbb (x check', 'y) ccc']
#   and with claude itself:
#     'Reply with the last word: alpha "beta gamma" delta'   ->   'beta'
#   i.e. claude -p received the prompt only up to the first inner quote and
#   dropped everything after it. All three agent prompt files contain a
#   quoted "..." phrase in their first lines, so every scheduled agent ran on a
#   truncated prompt and nothing logged it - the exact "silent failure" of
#   charter section 0. The ops-auditor of 2026-08-19 12:11 flagged it itself
#   ("the request prompt was cut off at ...").
#
# WHAT
#   Applies the MSVCRT/CommandLineToArgvW rules: every inner " becomes \" and
#   any run of backslashes right before it (or at the very end of the value,
#   where PowerShell will append the closing quote) is doubled. PowerShell then
#   wraps the result in quotes as before and the callee reassembles one arg.
#
# USAGE
#   . (Join-Path $Hq 'scripts\native-arg.ps1')
#   $out = & $Claude -p (ConvertTo-NativeArg $prompt) ...
#
# NOTE this is for PowerShell 5.1 (the scheduled tasks run powershell.exe).
# PowerShell 7.3+ escapes natively; feeding it pre-escaped text would double up.

function ConvertTo-NativeArg {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    $ev = [System.Text.RegularExpressions.MatchEvaluator]{
        param($m)
        ($m.Groups[1].Value * 2) + '\"'
    }
    $s = [regex]::Replace($Value, '(\\*)"', $ev)
    # trailing backslashes would escape the closing quote PowerShell adds
    $s = [regex]::Replace($s, '(\\+)$', { param($m) $m.Groups[1].Value * 2 })
    return $s
}
