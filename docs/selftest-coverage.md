# 자체 검사 실행 원장 — «있는데 안 돌던 검사» 전수 (2026-08-27)

> **왜 있나.** `scenes.self_test()` 는 존재했고 통과 조건도 옳았는데 **8/26~8/27 열흘 동안 아무도 부르지 않았다.** 그 사이 키워드 그림자 둘이 조용히 생겨 다른 씬을 돌려주고 있었다. **부르는 자리가 없는 검사는 검사가 아니라 메모다** — 정관 §0 «감지 장치가 실제로 값을 담는지»의 한 겹 바깥이다.
> 이 문서는 5개 레포의 자체 검사를 전수해 **«무엇이 자동으로 도는가»** 로 가른다. 조회: `grep -rn "def self_test\|def _selftest\|def selftest"` + 호출처 역추적.

## 자동으로 도는 것 (🟢 — 손댈 것 없음)

| 검사 | 언제 도나 | 근거 |
|---|---|---|
| `cardcheck._ensure_self_test()` · `_ensure_number_self_test()` | **카드 검수를 시작할 때마다** — 검사기가 헛돌면 검수를 시작조차 안 한다 | `cardcheck.py` 192·417행, `epcheck` 도 부른다 |
| `epcheck` `[R]` 역검증 블록 | **편 게이트를 돌릴 때마다** (약 40건) | `epcheck.py` `[R]` 절 |
| `skill_drift_audit._ensure_self_test()` + 사본 `_selftest.py` | **매일 12:30 스케줄** — 감사 시작 전에 판정기 자신을 시험하고, 사본을 실제로 돌린다 | `skill_drift_audit.py` 258·391행 |
| `deliver._selftest()` | **드라이브 전달 때마다** | `deliver.py` 209·216행 |

## 오늘 자동화한 것 (2026-08-27)

| 검사 | 종전 | 지금 |
|---|---|---|
| `scenes.self_test()` (content-ops) | ❌ 수동 — **열흘 잠복, 그림자 2건** | **런타임 진입부**(`_concept_key` 가 `_ensure_self_test()` 를 부른다, 그림자면 예외) + **pre-commit**(`cards/scenes.py` 가 스테이지되면 실행) |
| `freshness.self_test()` (content-ops) | ❌ 수동 | pre-commit |
| `handoff_schema._selftest()` (jj-company) | ❌ 수동 | pre-commit |
| `consistency_audit.selftest()` | ❌ 수동 | pre-commit |
| `distcheck.selftest()` | ❌ 수동 | pre-commit |
| `check-bash-guard.ps1` (신설) | — | pre-commit (가드 파일이 스테이지되면) |

**pre-commit 은 스테이지된 파일이 그 검사의 대상일 때만 돈다** — 문서만 고친 커밋이 값을 치르지 않게. 각 검사는 0.2~0.4초다(실측).

## 아직 수동인 것 (🟡 — 남은 목록)

| 검사 | 왜 남겼나 |
|---|---|
| `check-repo-guard.ps1` (jj-company) | **조문이 «세션 착수 시»로 부르는 자리를 이미 정해 뒀다**(정관 §3). 자동화하면 매 커밋이 임시 worktree 를 만들게 되어 비싸다 |
| `claim.ps1 -SelfTest` | 클레임 자체가 세션 착수 절차라 같은 이유 |
| `compare.self_test()` (tomangchi-skill·workshop 사본) | **부르는 자리가 없다.** 편 게이트가 `compare` 를 안 쓰는 편이 많아 `_ensure_*` 로 넣으면 안 쓰는 편까지 값을 치른다 — 쓰는 자리(비교 카드)에서 부르도록 다음 정비에 넣는다 |
| `preflight.py` · `kitchain.py` (workshop) | 자체 검사가 **없다**. 둘 다 편 제작 경로에서만 돌고 실패가 요란해서 우선순위는 낮다 |
| `OhjaejunO.github.io` 사이트 | Astro 빌드(`.github/workflows/deploy.yml`)가 CI 다. 전사 맵 생성기(`logs/sysmap`)는 **gitignore 라 CI 밖** — 기하 검사는 생성할 때 돌지만 «생성을 잊는 것»은 못 잡는다 |

## 규칙 (제안)

1. **검사를 만들면 부르는 자리를 같이 만든다.** 런타임 진입부(`_ensure_*`) > pre-commit > 스케줄 > 수동 순으로 가깝게.
2. **수동으로 남기면 이 표에 사유와 함께 적는다.** 적히지 않은 수동 검사는 «잠복»이다.
3. pre-commit 은 **스테이지된 파일과 관련된 것만** 돌린다. 전부 돌리면 커밋이 느려지고, 느려지면 `--no-verify` 가 나온다.
