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

## 2-1. workshop-backup 등록 (2026-08-30 추가 · **사람 자리**)

인프라 백로그 21번 ㉰ 안전판. **에이전트는 등록할 수 없다** — S4U 작업 등록은 관리자
PowerShell 을 요구하고 일반 셸에서는 `액세스가 거부되었습니다`(0x80070005) 가 난다
(2026-08-30 실측). 아래를 **관리자 PowerShell** 에 붙여 넣는다.

🔴 **순서가 있다.** ① PR #138 머지 → ② 운영 서버 `git pull` → ③ 등록.
스크립트가 없는 상태로 등록하면 첫 회차가 **작업 스케줄러 층에서 죽어 로그도 안 남는다** —
래퍼의 `STATUS: FAIL script-missing` 은 래퍼가 떠야 찍힌다.

**①·② 는 2026-08-30 에 끝났다** (#138 머지 03:36 · 운영 서버 pull 완료 · 라이브 경로에서
`--self-test` 통과 확인). **남은 것은 ③ 뿐이고 그것이 사람 자리다.**

### 🔴 이 작업은 `deploy-skill` 을 건너뛴다 — **적어 둔 이탈** (2026-08-30 JJ 확정)

§4 는 모든 스케줄 작업에 «운영 서버 동기화 + 스킬 배포» 둘을 요구한다. 이 작업은
`git pull` 은 하되 **`deploy-skill.ps1` 은 부르지 않는다.**

- **사유**: 이 작업은 스킬을 한 번도 안 쓴다. 그런데 스킬 배포에 묶으면 **무관한 인증
  만료가 안전망을 꺼 버린다.** 가정이 아니다 — **2026-08-27 에 `gh` 토큰이 만료돼 세
  스케줄 작업이 정확히 그 단계에서 죽었고**(`STATUS: FAIL skill-sync`), 원인을 말해 줄
  검사는 그 뒤에 있어서 돌지도 못했다. 무관한 것이 만료된 날 꺼지는 백업은 백업이 아니라
  **백업 모양의 구멍**이고, 하필 그런 날이 일이 터지는 날이다.
- **선례**: `skill-drift-audit.ps1` 이 같은 꼴의 «적어 둔 이탈» 이다(그쪽은 `git pull`
  자체를 건너뛰고 사유를 주석에 적었다).
- **면허가 아니다**: **다른 스케줄 작업은 전부 둘 다 그대로 한다.** 이탈은 이 작업 하나이고,
  세 자리(래퍼 주석 · 이 문서 · 도입 PR)에 같은 사유가 적혀 있다.

```powershell
$act = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\ojaej\jj-company\scripts\workshop-backup.ps1" weekly'
$trg = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '13:00'
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$pri = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName 'workshop-backup' -TaskPath '\JJ\' `
  -Action $act -Trigger $trg -Settings $set -Principal $pri -Force
```

**일요일 13:00 인 이유**: 12:30 에 vault·drift 둘이 이미 뜬다. 백업은 마감이 없는
안전망이라 뒤에 세우고, 래퍼가 480초를 더 늦춘다(동시 기동 `git pull` 경쟁 회피 — §4).

**«편 발행 직후» 회차는 등록 대상이 아니다** — `publish-threads.ps1` 이 성공 경로에서
직접 부른다(best effort · 발행 STATUS 를 바꾸지 않는다).

등록 뒤에는 §3 대로 **실값을 다시 본다.** 아래가 «등록 전» 실측(2026-08-30)이고 대조 기준이다.

```
hermes-event-watch:   WakeToRun=True StartWhenAvailable=True Multi=IgnoreNew Limit=PT1H  trig=2026-08-26T07:40:00+09:00
job-scout:            WakeToRun=True StartWhenAvailable=True Multi=IgnoreNew Limit=PT1H  trig=2026-08-10T08:30:00+09:00
morning-vault-health: WakeToRun=True StartWhenAvailable=True Multi=IgnoreNew Limit=PT1H  trig=2026-08-10T12:30:00 days=62
skill-drift-audit:    WakeToRun=True StartWhenAvailable=True Multi=IgnoreNew Limit=PT72H trig=2026-08-15T12:30:00
tomangchi-scout:      WakeToRun=True StartWhenAvailable=True Multi=IgnoreNew Limit=PT1H  trig=2026-08-10T08:00:00+09:00
```

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
