#requires -Version 5.1
#
# JJ Company OS - run-provenance lines for scheduled logs
# 2026-08-15 diagnosis "SKILL symlink structure", supplementary proposal.
#
# ASCII-only on purpose (see any schedule script header for why).
#
# WHY
#   Until 2026-08-15 nothing recorded WHICH revision of the rulebook a scheduled
#   run actually used. The live skill was a symlink into a working repo, so the
#   answer changed with whatever branch happened to be checked out - and the logs
#   were silent about it. The 8/14 diagnosis hit the same wall from the other
#   side ("8/13 has zero schedule logs" blocked root-cause tracing).
#
#   Two lines per run close that hole.
#
# WHAT IS AUTHORITATIVE
#   The LIVE stamp (.deployed), not the source repo. The live folder is a plain
#   copy now, so "git rev-parse" against it would mean nothing. The source repo
#   HEAD is logged too, but only as drift context - if live and source disagree,
#   that is expected while someone works on a branch, and it is exactly the state
#   that used to leak into production.
#
# USAGE
#   $h = Join-Path $Hq 'scripts\skill-version.ps1'
#   if (Test-Path -LiteralPath $h) { . $h; foreach ($l in (Get-SkillVersionLines)) { Write-Log $l } }

function Get-SkillVersionLines {
    param(
        [string]$Live = 'C:\Users\ojaej\.claude\skills\tomangchi',
        [string]$Repo = 'C:\Users\ojaej\orca\tomangchi-skill'
    )
    $out = @()

    # --- live (authoritative) ---
    $stamp = Join-Path $Live '.deployed'
    if (Test-Path -LiteralPath $stamp) {
        # Parsed off the WHOLE text, not line by line: a malformed single-line
        # stamp must still yield the revision rather than silently reporting
        # blanks. A provenance line that prints empty is worse than none - it
        # looks like it worked. (An early deploy build wrote exactly that.)
        $text = (Get-Content -LiteralPath $stamp -Raw -Encoding UTF8)
        $short = if ($text -match 'short:\s*([0-9a-f]{7,40})') { $Matches[1] } else { '' }
        $when = if ($text -match 'deployed:\s*(\S+)') { $Matches[1] } else { '' }
        if ($short) {
            $out += ('skill live: ' + $short + ' (deployed ' + $when + ')')
        } else {
            $out += 'skill live: .deployed stamp unreadable - provenance unknown'
        }
    } elseif (Test-Path -LiteralPath $Live) {
        $item = Get-Item -LiteralPath $Live -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            # The very thing plan 1 removed. If this ever prints, the deploy was undone.
            $out += 'skill live: SYMLINK - unpinned, branch of source repo decides. RUN deploy-skill.ps1'
        } else {
            $out += 'skill live: no .deployed stamp - provenance unknown'
        }
    } else {
        $out += ('skill live: MISSING ' + $Live)
    }

    # --- source repo (drift context only) ---
    if (Test-Path -LiteralPath (Join-Path $Repo '.git')) {
        $br = (& git -C $Repo branch --show-current 2>$null)
        $sha = (& git -C $Repo rev-parse --short HEAD 2>$null)
        $out += ('skill source: ' + $sha + ' on ' + $br + ' (context only - live is pinned to main)')
    }
    return $out
}
