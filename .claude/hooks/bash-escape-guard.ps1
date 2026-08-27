#requires -Version 5.1
#
# JJ Company OS - shell re-interpretation guard (PreToolUse / Bash)
# Design: docs\design-bash-escape-guard.md  (approved 2026-08-27)
#
# ASCII-only on purpose: PowerShell 5.1 decodes BOM-less .ps1 as the system ANSI
# codepage. Korean here would arrive mangled in the one moment the message matters.
#
# WHY
#   The failure mode is NOT "heredoc". It is "a place where the shell interprets
#   the payload a second time". Measured three times on 2026-08-27 alone:
#     1. py -c "<python with backticks>"  -> bash ran `gh auth login` inside it
#     2. py -c "<doc text with backticks>" -> identifiers committed as empty holes
#     3. (2026-08-25) py - <<EOF with \1  -> backslash collapsed to \x01
#   A quoted heredoc (<<'EOF') does NOT expand. A double-quoted -c argument DOES.
#
# WHAT IT BLOCKS  (narrow on purpose - normal commands must pass)
#   R1  unquoted heredoc (<<EOF / <<-EOF) whose body contains ` or $( or \
#   R2  a double-quoted argument to -c / -Command / --command containing ` or $( or $name
#
# CONTRACT
#   stdin  : PreToolUse JSON, command at .tool_input.command
#   exit 0 : no opinion            exit 2 : block, stderr goes back to the model
#   Anything else is a non-blocking hook error - the tool would RUN. That is why
#   scripts\check-bash-guard.ps1 exists and must be run from the session start.

$ErrorActionPreference = 'Stop'

function Test-BashEscapeRisk {
    <#
      .SYNOPSIS  Returns $null when the command is fine, or a reason string when it must be blocked.
      .NOTES     Single source of truth: the checker feeds this same script, so the
                 verdict never lives in two places.
    #>
    param([string]$Command)

    if ([string]::IsNullOrWhiteSpace($Command)) { return $null }

    # --- R1: unquoted heredoc -------------------------------------------------
    # <<EOF and <<-EOF expand $var, `cmd` and backslashes. <<'EOF' and <<"EOF" do not
    # (quoting ANY part of the delimiter turns expansion off).
    $lines = $Command -split "`r?`n"
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $m = [regex]::Match($lines[$i], '<<-?\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:$|\|)')
        if (-not $m.Success) { continue }
        # A quote anywhere in the delimiter position means it is a quoted heredoc.
        if ($lines[$i] -match "<<-?\s*['`"]") { continue }
        $delim = $m.Groups[1].Value
        $body = New-Object System.Text.StringBuilder
        for ($j = $i + 1; $j -lt $lines.Count; $j++) {
            if ($lines[$j].Trim() -eq $delim) { break }
            [void]$body.AppendLine($lines[$j])
        }
        $b = $body.ToString()
        if ($b -match '`' -or $b -match '\$\(' -or $b -match '\\') {
            return "unquoted heredoc <<$delim - its body is expanded by the shell (backtick / \$( ) / backslash found). Use <<'$delim' (quoted delimiter) or write the file with the Write/Edit tool."
        }
    }

    # --- R2: double-quoted -c / -Command payload ------------------------------
    # Walk the string so single-quoted regions are skipped (they are safe).
    $chars = $Command.ToCharArray()
    $inSingle = $false
    $i = 0
    while ($i -lt $chars.Count) {
        $c = $chars[$i]
        if ($c -eq "'" -and -not $inSingle) { $inSingle = $true; $i++; continue }
        elseif ($c -eq "'" -and $inSingle) { $inSingle = $false; $i++; continue }
        if ($inSingle) { $i++; continue }
        if ($c -eq '"') {
            # find the closing quote (backslash-escaped quotes stay inside)
            $start = $i + 1
            $j = $start
            while ($j -lt $chars.Count) {
                if ($chars[$j] -eq '\' -and $j + 1 -lt $chars.Count) { $j += 2; continue }
                if ($chars[$j] -eq '"') { break }
                $j++
            }
            $seg = -join $chars[$start..([Math]::Max($start, $j - 1))]
            if ($j -le $start) { $seg = '' }
            # Is this quoted segment the payload of -c / -Command / --command?
            $before = -join $chars[0..([Math]::Max(0, $i - 1))]
            if ($before -match '(?i)(^|\s)(-c|--command|-Command|-EncodedCommand)\s*$') {
                if ($seg -match '`') {
                    return "backtick inside a double-quoted -c payload - the shell runs it as a command before your program sees it. Use single quotes, or write the file with the Write/Edit tool."
                }
                if ($seg -match '\$\(') {
                    return "command substitution `$( ) inside a double-quoted -c payload - the shell evaluates it first. Use single quotes, or the Write/Edit tool."
                }
                if ($seg -match '\$[A-Za-z_{]') {
                    return "shell variable expansion inside a double-quoted -c payload - `$name is replaced by the shell (often with an empty string). Use single quotes, or the Write/Edit tool."
                }
            }
            $i = $j + 1
            continue
        }
        $i++
    }
    return $null
}

# --- entry point (skipped when dot-sourced by the checker) --------------------
if ($MyInvocation.InvocationName -ne '.') {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }   # unparseable input: no opinion
    if ($payload.tool_name -ne 'Bash') { exit 0 }
    $reason = Test-BashEscapeRisk -Command ([string]$payload.tool_input.command)
    if ($reason) {
        [Console]::Error.WriteLine("BLOCKED by bash-escape-guard: $reason")
        [Console]::Error.WriteLine("Charter section 6 / learnings L-001. Safe forms: <<'EOF' quoted heredoc, single-quoted -c, or Write/Edit then run the file.")
        exit 2
    }
    exit 0
}
