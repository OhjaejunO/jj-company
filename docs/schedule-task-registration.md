# 스케줄 작업 등록·재등록 절차 (2026-08-25 신설)

> 왜 있나. 8/22 16:42~16:52 작업 4개가 재등록됐고, 그때 8/21 에 켠 `WakeToRun` 이 **조용히 `False` 로 돌아갔다.**
> 백로그는 «적용 완료»라고 적혀 있었고 아무도 실값을 다시 보지 않았다. 8/23 12:30 회차가 절전으로 놓쳤는데도
> 그것이 설정 소실 때문인지는 8/25 판정 세션에서야 알았다. **재등록은 설정을 되돌린다 — 그래서 재등록 뒤엔 실값을 다시 본다.**

작업 경로: `\JJ\` (morning-vault-health · tomangchi-scout · job-scout · skill-drift-audit). 실행 계정 S4U → **변경은 관리자 PowerShell** 에서만 된다(일반 셸은 `0x80070005`).

## 1. 등록·재등록 전 — 현재 실값을 먼저 적어 둔다

```powershell
Get-ScheduledTask -TaskPath '\JJ\' | % { '{0}: WakeToRun={1} StartWhenAvailable={2} Multi={3} Limit={4} trig={5} days={6}' -f `
  $_.TaskName, $_.Settings.WakeToRun, $_.Settings.StartWhenAvailable, $_.Settings.MultipleInstances, `
  $_.Settings.ExecutionTimeLimit, $_.Triggers[0].StartBoundary, $_.Triggers[0].DaysOfWeek }
```

이 출력을 백로그(또는 PR 본문)에 붙인다. «전»이 없으면 «후»가 맞는지 알 수 없다.

## 2. 등록·재등록

`Register-ScheduledTask` / 작업 스케줄러 GUI 어느 쪽이든 된다. 단 **기존 작업을 지우고 새로 만들면 Settings 가 기본값으로 돌아간다** — 특히 `WakeToRun`(기본 False)·`ExecutionTimeLimit`(기본 PT72H)·`MultipleInstances`.

기준값 (2026-08-25 실측 + 판정):

| 항목 | 값 |
|---|---|
| Principal | `LogonType=S4U` (로그온 없이 실행) |
| StartWhenAvailable | `True` (놓친 회차 소급) |
| **WakeToRun** | **`True`** — 절전 중 기상. `RTCWAKE AC=1` 은 이미 허용돼 있다 |
| MultipleInstances | `IgnoreNew` |
| ExecutionTimeLimit | `PT1H` (drift 는 미설정) |
| 트리거 | vault 평일 12:30 · drift 매일 12:30 · scout 매일 08:00 · job 매일 08:30 |

## 3. 재등록 후 — 실값 재확인 (건너뛰면 절차를 안 한 것이다)

```powershell
# (관리자 PowerShell) WakeToRun 을 켜고, 켜졌는지 같은 명령으로 다시 본다
foreach ($n in 'morning-vault-health','skill-drift-audit','tomangchi-scout','job-scout') {
  $t = Get-ScheduledTask -TaskName $n -TaskPath '\JJ\'
  $t.Settings.WakeToRun = $true
  Set-ScheduledTask -InputObject $t | Out-Null
}
Get-ScheduledTask -TaskPath '\JJ\' | % { '{0}: WakeToRun={1} trig={2}' -f $_.TaskName, $_.Settings.WakeToRun, $_.Triggers[0].StartBoundary }
```

- 출력 4줄이 전부 `WakeToRun=True` 이고 트리거가 §2 표와 같아야 끝이다. **문서에 «적용했다»라고 적기 전에 이 출력을 붙인다.**
- 트리거를 바꿨으면 `CLAUDE.md` §4 «등록된 스케줄 (현황판)» 표를 실값으로 맞춘다 — 그 표는 조회 결과이지 정본이 아니다.
- 다음 «절전 중 예정 시각» 회차가 첫 실측이다. 판정 기준은 작업 스케줄러 Operational 로그 **id=114 부재**(정시 기동) + 래퍼 로그 첫 줄 타임스탬프. 기계가 깨어 있던 회차는 실측으로 치지 않는다.

## 4. 함께 볼 것

- `UNATTENDSLEEP`(무인 절전 시간 제한)이 stagger + 최장 실행(약 21분)을 덮어야 한다 — 8/21 에 1800s 로 올렸다고 기록돼 있으나 `powercfg /q` 로는 값이 안 보인다(숨김 속성). 확인: `powercfg /attributes SUB_SLEEP 7bc4a2f9-d8fc-4469-b07b-33eb785aaca0 -ATTRIB_HIDE` 뒤 `powercfg /q SCHEME_CURRENT SUB_SLEEP 7bc4a2f9-d8fc-4469-b07b-33eb785aaca0`.
- 래퍼는 stagger 전에 `logs\<작업>.started` 스탬프를 쓴다. 재등록 직후 수동 실행으로 스탬프가 생겼다 지워지는지(`started stamp removed` 로그 줄) 한 번 본다.
