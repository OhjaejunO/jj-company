# JJ Company OS - headroom proxy helper for scheduled agent runs (2026-09-04, JJ decision)
#
# What: put the local headroom proxy (headroomlabs-ai/headroom, PyPI headroom-ai) in front
#       of `claude -p` so tool outputs are compressed before they reach the model.
# Why:  one-off measurement on 2026-09-04 (headless read task, 2 calls via the proxy):
#       43.9% saved, 218,112 / 496,479 tokens. Scheduled agents dump big tool outputs
#       (yt-dlp, source_watch, reports) every day - that is exactly this seat.
# How:  dot-source this file, then call Start-HeadroomProxy before `claude -p`.
#       It returns $true when the proxy answers /health, and the caller sets
#       $env:ANTHROPIC_BASE_URL. It returns $false otherwise and the caller MUST log
#       'headroom: OFF (direct)' loudly - charter section 0, no silent failure. A missing
#       proxy never fails the run: the run goes direct, the log says so.
# Not:  `headroom wrap claude` is NOT used - it writes Serena MCP into ~/.claude.json.
#       Proxy mode only. The proxy process is left running after the run (shared by the
#       next job); it binds 127.0.0.1 only.
# Self-test (charter section 0 reverse check, both directions):
#       powershell -File scripts\headroom-proxy.ps1 -SelfTest
#       -> proxy comes up and /health is 200; a wrong port is reported as down (not up).
# ASCII-only on purpose (PS 5.1 reads BOM-less UTF-8 as ANSI).

param([switch]$SelfTest)

$HeadroomExe  = 'C:\Users\ojaej\.local\headroom-venv\Scripts\headroom.exe'
$HeadroomPort = 8787
$HeadroomUrl  = 'http://127.0.0.1:' + $HeadroomPort

function _HrLog($msg) {
    if (Get-Command Write-Log -ErrorAction SilentlyContinue) { Write-Log $msg } else { Write-Host $msg }
}

function Test-HeadroomHealth([int]$Port = $HeadroomPort) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri ('http://127.0.0.1:' + $Port + '/health') -TimeoutSec 3
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Start-HeadroomProxy {
    # Returns $true when a healthy proxy is listening on $HeadroomPort.
    if (-not (Test-Path -LiteralPath $HeadroomExe)) {
        _HrLog ('headroom: exe missing (' + $HeadroomExe + ') -> OFF (direct)')
        return $false
    }
    if (Test-HeadroomHealth) { _HrLog ('headroom: proxy already up at ' + $HeadroomUrl); return $true }
    try {
        Start-Process -FilePath $HeadroomExe -ArgumentList @('proxy', '--port', "$HeadroomPort", '--no-http2') `
            -WindowStyle Hidden -WorkingDirectory $env:USERPROFILE | Out-Null
    } catch {
        _HrLog ('headroom: start failed (' + $_.Exception.Message + ') -> OFF (direct)')
        return $false
    }
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-HeadroomHealth) { _HrLog ('headroom: proxy started at ' + $HeadroomUrl + ' (' + (($i + 1) * 0.5) + 's)'); return $true }
    }
    _HrLog 'headroom: proxy did not answer /health within 10s -> OFF (direct)'
    return $false
}

function Get-HeadroomSavedTokens {
    # Lifetime tokens_saved from `headroom savings --json`; -1 when unreadable.
    try {
        $raw = & $HeadroomExe savings --json 2>$null | Out-String
        $j = $raw | ConvertFrom-Json
        return [long]$j.lifetime.tokens_saved
    } catch { return -1 }
}

function Write-HeadroomSavings([long]$Before) {
    # Log the delta this run produced. A delta of 0 with the proxy ON is worth seeing too.
    $after = Get-HeadroomSavedTokens
    if ($Before -lt 0 -or $after -lt 0) { _HrLog 'headroom: savings ledger unreadable'; return }
    _HrLog ('headroom: saved this run ' + ($after - $Before) + ' tokens (lifetime ' + $after + ')')
}

if ($SelfTest) {
    $ok = $true
    $up = Start-HeadroomProxy
    Write-Host ('[headroom-selftest] proxy up: ' + $up)
    if (-not $up) { $ok = $false }
    $bad = Test-HeadroomHealth -Port 8798
    Write-Host ('[headroom-selftest] wrong port reported down (reverse check): ' + (-not $bad))
    if ($bad) { $ok = $false }
    $s = Get-HeadroomSavedTokens
    Write-Host ('[headroom-selftest] savings ledger readable: ' + ($s -ge 0) + ' (' + $s + ')')
    if ($s -lt 0) { $ok = $false }
    if ($ok) { Write-Host 'STATUS: OK'; exit 0 } else { Write-Host 'STATUS: FAIL headroom-selftest'; exit 1 }
}
