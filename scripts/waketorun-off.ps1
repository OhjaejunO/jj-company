<#
  WakeToRun 해제 — 네 스케줄 작업 (2026-08-22 · JJ 판정 «C안»)

  🔴 관리자 PowerShell 에서 실행해야 한다.
     비권한으로 돌리면 Set-ScheduledTask 가 «성공»을 돌려주고 **값은 안 바뀐다** —
     2026-08-22 실측으로 확인했다(정관 §0 «조용히 실패하는 코드»). 그래서 이 스크립트는
     **변경 후 값을 다시 읽어** 안 바뀌었으면 STATUS: FAIL 로 끝난다.

  왜 끄나: 이 PC 는 절전이 아니라 **종료(Hybrid Shutdown)** 한다. 종료 상태에서는
  RTC 기상 타이머가 발화하지 않으므로 WakeToRun 은 성립하지 않는다.
  켜 둔 채로 두면 «설정은 됐는데 안 된다»가 남아 다음에 또 원인을 찾게 된다.

  ⚠️ Settings 를 통째로 새로 만들지 않는다 — 기존 객체에서 **한 필드만** 바꾼다.
     새로 만들면 StartWhenAvailable·MultipleInstances 가 기본값으로 날아간다.
#>
$ErrorActionPreference = 'Stop'
$path = '\JJ\'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$elev = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
          [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $elev) {
  Write-Host "STATUS: FAIL 관리자 권한이 아니다 — 이대로는 조용히 실패한다. 관리자 PowerShell 로 다시 실행할 것"
  exit 1
}

Write-Host "== 변경 전 =="
Get-ScheduledTask -TaskPath $path | ForEach-Object {
  '  {0,-24} WakeToRun={1,-5} StartWhenAvailable={2,-5} LogonType={3} Multiple={4}' -f `
    $_.TaskName, $_.Settings.WakeToRun, $_.Settings.StartWhenAvailable,
    $_.Principal.LogonType, $_.Settings.MultipleInstances
}

Write-Host "`n== 변경 =="
foreach ($t in Get-ScheduledTask -TaskPath $path) {
  if (-not $t.Settings.WakeToRun) { Write-Host ('  {0}: 이미 False' -f $t.TaskName); continue }
  $s = $t.Settings          # 기존 객체 — 새로 만들지 않는다
  $s.WakeToRun = $false     # 한 필드만
  Set-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Settings $s | Out-Null
  Write-Host ('  {0}: 요청 보냄' -f $t.TaskName)
}

Write-Host "`n== 변경 후 — 실제 값을 다시 읽는다 (요청 성공 != 반영) =="
$bad = @()
foreach ($t in Get-ScheduledTask -TaskPath $path) {
  $s = $t.Settings
  '  {0,-24} WakeToRun={1,-5} StartWhenAvailable={2,-5} LogonType={3} Multiple={4}' -f `
    $t.TaskName, $s.WakeToRun, $s.StartWhenAvailable, $t.Principal.LogonType, $s.MultipleInstances
  if ($s.WakeToRun) { $bad += "$($t.TaskName): WakeToRun 이 여전히 True" }
  if (-not $s.StartWhenAvailable) { $bad += "$($t.TaskName): StartWhenAvailable 이 날아갔다" }
  if ($t.Principal.LogonType -ne 'S4U') { $bad += "$($t.TaskName): LogonType 이 S4U 가 아니다" }
}

if ($bad.Count) {
  $bad | ForEach-Object { Write-Host "  🔴 $_" }
  Write-Host "STATUS: FAIL $($bad.Count)건"
  exit 1
}
Write-Host "STATUS: OK  WakeToRun 4/4 해제 · StartWhenAvailable·S4U 보존 확인"
