# 온보딩 리포트 — 집 기계 (2026-08-30 실측)

> **기계**: `컴퓨터` (Windows 11 Home 10.0.26200) · 사용자 `opjj7`
> **성격**: 🔴 **작업장 전용 — 운영 서버가 아니다.**
> 워커 실행 · 스케줄 등록 · 승인 폴더(`publish_approval\`) 생성 · `THREADS_*` 보관 **금지**.
> 이 회차는 그 금지를 지켰다 — 아래 «하지 않은 것» 절이 무엇을 왜 안 했는지 적는다.

## 한 줄

**레포·훅·문서 층은 섰다. 제작 층은 서지 못했다** — 이 기계에 **Python 이 없고**, 워크숍
제작 코드 **100개 파일이 다른 기계의 사용자 경로를 상수로 박고 있다.** 그래서 4번 과제
«렌더 동일성 실측» 은 **수행하지 못했고, «집 제작 완전 개방» 을 기록하지 않는다.**

## 이 기계의 판정 — **작업장(제작 미개방)**

🔴 **이 회차의 결론은 «작업장까지» 다.** 온보딩은 **여기서 중단**됐고, 그 상태를 문서에
그대로 적는다 — 클론 표(`scripts\githooks\README.md`)의 이 기계 칸은
**«작업장 (집 기계 · 제작 미개방)»** 이다.

| 층 | 상태 |
|---|---|
| 레포 클론 | 🟢 3/4 (`tomangchi-skill` 없음) |
| 훅 (`core.hooksPath`) | 🟢 대상 2개 전부 · 역검증 양방향 통과 |
| 정본 가독 | 🟢 7파일 UTF-8 |
| 자체 검사 | 🟢 4건 `STATUS: OK` |
| 자격 | 🔴 미완료 — `gh` 미로그인 · 드라이브 없음 · API 키 3종 미등록 |
| **제작(렌더)** | 🔴 **미개방 — 재지 못했다** |

🔴 **«미개방» 과 «다름» 을 같은 칸에 적지 않는다.** 렌더가 다르다고 밝혀진 것이 아니라
**측정 자체가 서지 못했다.** 둘을 뭉개면 다음 사람이 «집에서는 다르게 나온다» 로 읽는다.

**렌더 실측·경로 헬퍼 건은 폐기가 아니라 이월이다** — 여는 조건·재개 조건·순서는
`docs\infra-backlog.md` **23번**에 적었다.

---

## 1. 클론 — 4개 중 3개

| 레포 | 자리 | 원격 | HEAD | `origin/main` 대비 |
|---|---|---|---|---|
| `jj-company` | `C:\Users\opjj7\orca\jj-company` | `OhjaejunO/jj-company` | `c645cb5` | 🟢 동일 (0/0) |
| `tomangchi-lab.github.io` | `C:\Users\opjj7\orca\tomangchi-lab.github.io` | `tomangchi-lab/…` | `cc97f2f` | 🟢 동일 (0/0) |
| `tomangchi-workshop` | `C:\Users\opjj7\tomangchi-workshop` | **`OhjaejunO/…`** | `fabe3e4` | 🟢 동일 (0/0) |
| `tomangchi-skill` | — | — | — | 🔴 **없다** |

- 🟢 **워크숍 클론은 새 주소로 받았다** — 이전이 이 기계에 반영되어 있다.
- 🔴 **`tomangchi-skill` 클론이 없다.** `C:\Users\opjj7\orca\workspaces\` 라는 **빈 폴더**가
  대신 있다. 절차서(`docs\workshop-repo-sync.md`)의 온보딩 ① 은 네 개를 받으라고 적었고
  **셋만 받았다.** 자회사 정본(스킬·게이트)이 이 기계에 없으므로 **편 게이트를 돌릴 수 없다** —
  4번 과제의 두 번째 결번이다.

### `core.hooksPath` (1번 과제)

`check-repo-guard.ps1 -Fix` 로 걸었다. 이 검사기는 **설정을 읽는 데서 그치지 않고 §0 역검증을
한다** — 본 트리에서 훅을 실제로 돌려 거부되는지, 임시 worktree 에서는 통과하는지 **양쪽**을 본다.

| 레포 | 결과 |
|---|---|
| `jj-company` | 🟢 `STATUS: OK` — 설정 + 역검증 양방향 + lag 검사 + 타겟팅 검사 통과 |
| `tomangchi-lab.github.io` | 🟢 `STATUS: OK` — 설정 + 역검증 양방향 + 타겟팅 검사 통과 |
| `tomangchi-workshop` | — **대상 아님** (`scripts\githooks` 폴더가 없다) |
| `tomangchi-skill` | 🔴 **클론이 없어 못 걺** |

표는 `scripts\githooks\README.md` 에 반영했다.

---

## 2. 정본 가독 · 자체 검사 (2번 과제)

### 정본 가독 — 🟢 전부 통과

엄격 UTF-8 디코드 + 한글 글자 수로 쟀다. **«열린다» 가 아니라 «깨지지 않고 열린다» 를 본다** —
BOM 없는 UTF-8 을 ANSI 로 읽으면 열리기는 열리고 내용만 깨진다.

| 파일 | 인코딩 | 한글 |
|---|---|---|
| `CLAUDE.md` (정관) | 🟢 UTF-8 (BOM 없음) | 10,929자 |
| `docs\infra-backlog.md` | 🟢 UTF-8 | 16,911자 |
| `docs\clause-backlog.md` | 🟢 UTF-8 | 22,317자 |
| `docs\directives\제작지시서_v1_2026-08-29.md` | 🟢 UTF-8 | 5,583자 |
| `docs\directives\README.md` | 🟢 UTF-8 | 623자 |
| `docs\workshop-repo-sync.md` | 🟢 UTF-8 | 1,114자 |
| `docs\onboarding-credentials.md` | 🟢 UTF-8 | 874자 |

정관은 224줄 — 자기 규정인 «500줄» 안이다.

### 이 기계에서 돈 검사

| 검사 | 결과 | 비고 |
|---|---|---|
| `check-repo-guard.ps1` ×2 | 🟢 `STATUS: OK` | 역검증 양방향 포함 |
| `check-bash-guard.ps1` | 🟢 `STATUS: OK` | **역검증 9건 전부 정확** (차단 5 · 통과 4) + 부재 검사 |
| `claim.ps1 -SelfTest` | 🟢 `STATUS: OK` | 중복 거부 · 해제 · 재획득 |

🔴 **`check-bash-guard.ps1` 이 한 줄 남겼다**: `NOTE: no user-level copy - the guard covers
sessions on THIS repo only`. 가드가 `jj-company\.claude\hooks\` 에만 있고 `~\.claude\` 에는
없다. 다른 레포에서 여는 세션은 **가드 없이** 돈다. 자격 문서가 «`~\.claude\hooks\`
(bash-escape-guard) 는 레포로 안 온다» 고 적어 둔 그 자리이며, **아직 안 옮겼다.**

🟡 **`claim.ps1` 이 기계 이름을 깨뜨려 적는다.** 자체 검사는 통과했지만 클레임 파일의
`user:` 칸이 `opjj7@而댄벂??` 로 찍혔다 — 이 기계 이름이 한글(`컴퓨터`)이고 PowerShell 5.1
이 ANSI 코드페이지(`ks_c_5601-1987`)로 다루는 자리다. **지금은 무해하다** — 클레임은 한
기계 안에서만 유효하므로 이름이 깨져도 중복 판정은 정확하다. 다만 «누가 잡았나» 를 사람이
읽는 칸이 깨진 것이라 적어 둔다.

### 못 돌린 검사 — 🔴 Python 이 없다

`python.exe` 는 **0바이트 Microsoft Store 별칭 스텁**이다(실측: 길이 0). 실제 설치는 없고
`py` 런처도 없다. 그래서 `.py` 검사가 **한 건도 돌지 않았다**:

`permission_probe.py`(+`--self-test`) · `auth_check.py` · `vault_audit.py` · `run_audit.py` ·
`consistency_audit.py` · `skill_drift_audit.py` · `align_check.py` · `handoff_schema._selftest()`

🔴 **이 중 `permission_probe.py` 가 특히 아프다.** 정관 §0 은 그것을 «에이전트보다 먼저
실제로 한 번 막혀 본다» 는 자리로 못박았다. 이 기계에서는 **권한 게이트를 실측할 수단이
없다.** 워커를 안 띄우므로 지금 사고는 없지만, **띄우려면 이것부터 서야 한다.**

---

## 3. 자격 대조 (3번 과제) — **미완료**

값은 읽지 않았다. **이름·자리·길이만** 쟀다(정관 §6).

### 🟢 «집에 복제» 3건 — **셋 다 없다**

| 자격 | 기대 | 실측 (User/Machine/Process) |
|---|---|---|
| `X_BEARER_TOKEN` | 114자 | 🔴 **0 / 0 / 0 — 미등록** |
| `OPENAI_API_KEY` | 164자 | 🔴 **0 / 0 / 0 — 미등록** |
| `OPENROUTER_API_KEY` | 73자 | 🔴 **0 / 0 / 0 — 미등록** |

**«확인» 이 아니라 «미등록» 이 나왔다.** 셋 다 사람이 손으로 넣어야 하고 아직 안 넣었다.
막히는 것: X 조회 MCP(`x-search` 서버가 읽는 유일한 변수) · xreview 계열 · 헤르메스.

### 🟡 «집에서 새 발급» — 하나도 안 됐다

| 자격 | 실측 |
|---|---|
| GitHub `gh` | 🔴 설치는 됨(`C:\Program Files\GitHub CLI\gh.exe`) · **로그인 안 됨** (`not logged into any GitHub hosts`) |
| 구글 드라이브 | 🔴 **`G:` 없음** — 파일시스템 드라이브가 `C:` 뿐이다 |
| Anthropic / Claude Code | 🟢 이 세션이 돌고 있으므로 서 있다 |
| Higgs MCP | 🟢 커넥터 목록에 붙어 있다 |

🔴 **`gh` 미로그인이 5번 과제(PR)를 막았다.** 아래 «하지 못한 것» 참조.

### 🔴 «이 기계 전용» — 지켜졌다. 다만 **자 하나가 두 가지를 재고 있었다**

| 이름 | User | Machine | Process | 판정 |
|---|---|---|---|---|
| `THREADS_TOKEN` | 0 | 0 | 0 | 🟢 **없다 — 맞다** |
| `THREADS_APP_ID` | 0 | 0 | 0 | 🟢 **없다 — 맞다** |
| `CLAUDE_CODE_MESSAGING_TOKEN` | 0 | 0 | **32** | 🟢 아래 참조 |
| `ORCA_*` (17개) | 0 | 0 | **있음** | 🟢 아래 참조 |
| `HERMES_*` | 0 | 0 | 0 | 🟢 없다 |

**발행 자격은 이 기계에 없다. 금지 조건은 지켜졌다.**

🔴 **그런데 `ORCA_*`·`CLAUDE_CODE_MESSAGING_TOKEN` 은 «있으면 FAIL» 로 재면 안 된다.**
자격 문서는 🔴 칸에 **성격이 다른 둘**을 같이 넣어 두었다 —

- **옮기면 안 되는 것**(발행 자격 `THREADS_*`): 판정은 «없어야 한다». 🟢 없다.
- **옮겨도 뜻이 없는 것**(실행 환경 값 `ORCA_*` 등): 이 값들은 **터미널이 자기 세션에
  스스로 만든다.** 실측이 그것을 가른다 — **User·Machine 범위에 0, Process 범위에만 있다.**
  즉 **복제된 것이 아니라 이 기계가 새로 낸 값**이다. 판정은 «없어야 한다» 가 아니라
  **«영속 범위에 없어야 한다»** 다.

**같은 🔴 인데 통과 조건이 다르다.** 문서가 그 구분을 안 적어 두면 다음 사람이 «`ORCA_*`
가 있네 → FAIL» 로 읽거나, 반대로 «Process 에 있으니 괜찮겠지» 로 `THREADS_*` 를 넘긴다.
🔴 **조문 안건 후보로 남긴다** — 이번 회차에서는 실측으로 갈랐고 문서는 안 고쳤다.

---

## 4. 렌더 동일성 (4번 과제) — 🔴 **수행하지 못했다**

**«집 제작 완전 개방» 을 기록하지 않는다.** 다르다고도 적지 않는다 — **재지 못했다.**
아래는 «왜 못 쟀나» 의 실측이고, 짐작이 아니다.

### 4-1. 절차의 앞단은 돌았다 — 🟢 robocopy · 단방향 불변 확인

`docs\workshop-repo-sync.md` 의 ② 를 그대로 돌렸다:

```
robocopy tomangchi-workshop tomangchi-lab.github.io\workshop /E /XD .git
```

| 확인 | 실측 |
|---|---|
| 복사 | 🟢 **710개 / 710개** · 55.57 MiB · 실패 0 |
| 워크숍이 작업 트리가 아님 | 🟢 `workshop\` 하위 `.git` **0개** — 단방향 구조 유지 |
| 사이트 레포가 `workshop\` 을 안 본다 | 🟢 `git status` 비어 있음 (gitignore 유효) |

레포에 기록된 «710개» 와 **수가 맞는다.**

### 4-2. 대조 대상은 있다 — 🟢

`검증로그.md` 5-3 절에 **덱 9장의 규격·바이트·sha256(앞 16)** 이 표로 있다.
1장을 고른다면 `02_what.png`(1080x1350 · 221,050 바이트 · `a54201a4ce885775`) 가 맞다 —
PNG 라 영상 도구 없이 조판되는 카드다.

### 4-3. 🔴 조판이 안 된다 — 막은 것 넷

| # | 막은 것 | 실측 | 성격 |
|---|---|---|---|
| ① | **Python 없음** | `python.exe` 0바이트 스텁 · 실설치 없음 · `py` 없음 | 설치하면 풀린다 |
| ② | **`numpy`·`Pillow` 없음** | ① 때문에 확인조차 못 함 | 설치하면 풀린다 |
| ③ | **`ffmpeg`·`ffprobe` 없음** | `NOT FOUND` | 설치하면 풀린다 (영상 카드·`hashtable.py` 에 필요) |
| ④ | 🔴 **제작 코드가 다른 기계의 사용자 경로를 상수로 박았다** | 워크숍 **100개 파일**이 `C:\Users\ojaej\…` | **설치로 안 풀린다** |

**④ 가 본체다.** ①~③ 은 이 기계의 준비 부족이고 고치면 끝나지만, ④ 는 **코드에 박힌 결함**이라
이 기계에 무엇을 깔아도 그대로 남는다. ep39 만 봐도 여섯 파일이 걸린다:

| 파일 | 줄 | 상수 |
|---|---|---|
| `build_ep39.py` | 19 | `WS` |
| `build_cover_fit.py` | 36 | `WS` |
| `build_own.py` | 19 | `WS` |
| `build_plate_video.py` | 27 | `EP_DIR` |
| `hashtable.py` | 28 | `EP_DIR` |
| `packfill.py` | 22 | `EP_DIR` |

여섯 다 값이 같다 — `C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop`.
`00_브랜드에셋\xreview.py` 는 한 술 더 떠 `C:\Users\ojaej\jj-company\...` 를 본다.

🔴 **대조표를 만드는 `hashtable.py` 자신이 걸려 있다.** 4번 과제가 요구한 «레포에 기록된
해시와 대조» 는 그 도구가 돌아야 성립하는데, 그 도구가 운영 기계의 경로를 본다.

🔴 **이 자리는 백로그 15번이 «절대경로로 고쳤다» 고 적어 둔 그 자리다.** 15번은 «상위 폴더
상대 계산» 을 고치려고 절대경로로 바꿨고, 그래서 **한 기계 안에서는** 옳다. 그런데 절대경로는
**기계 경계를 넘는 순간 틀린다** — 상대경로의 결함을 고치면서 **기계 이식성을 대신 내줬고,
두 기계 체제에서 그 대가가 지금 청구됐다.** 15번의 해결책이 이 결함을 만들었다.

### 4-4. 폰트 — 🟢 실제로 쓰는 것은 전부 있다

「다르면 원인(폰트·라이브러리 판본)을 실측하라」 는 지시가 있었으므로, **조판은 못 했지만
폰트 축은 미리 쟀다.** 다음 회차가 이 값과 대조하면 된다.

| 폰트 | 이 기계 | sha256(앞 16) | 바이트 |
|---|---|---|---|
| `NotoSansKR-VF.ttf` | 🟢 있음 | `018174E8CDD366AF` | 10,415,532 |
| `malgun.ttf` | 🟢 있음 | `7A183CF1C6C56B96` | 13,459,196 |
| `malgunbd.ttf` | 🟢 있음 | `E8CBC0B2AFCC14FB` | 12,600,392 |
| `consola.ttf` | 🟢 있음 | `CF00B507B3286870` | 453,088 |
| `seguiemj.ttf` | 🟢 있음 | `F07CBD7886F4A1A5` | 12,450,664 |
| `NotoSansCJK-Bold.ttc` · `-Black.ttc` | 없음 | — | — |

**없는 둘은 결함이 아니다.** `template.py` 가 `/usr/share/fonts/…` 를 먼저 시도하는 **리눅스
분기**이고, 코드에 «윈도우에는 NotoSansCJK `.ttc` 컬렉션이 없다» 고 적혀 있다. 운영 기계도
같은 상태다. **실제로 쓰이는 다섯은 전부 있고, 경로도 같은 `C:\Windows\Fonts\` 다.**

**✅ 맞댔다 — 5/5 일치 (2026-08-30 · 운영 기계 실측 추가).** 위 지문을 남긴 목적대로
운영 기계에서 같은 다섯 줄을 떠서 대조했고, **sha256 앞 16과 바이트 수가 전부 같다.**
경로도 같은 `C:\Windows\Fonts\` 다. 🔴 **폰트 축은 닫혔다** — 나중에 조판이 열려 결과가
다르게 나오더라도 **폰트는 용의선상에서 빠진 채로 시작한다.**

🔴 **남은 축은 라이브러리 판본이고 그것은 못 쟀다.** 이 기계에 Python 이 없어
`Pillow`·`numpy` 판본을 **조회할 수조차 없었다** — «없다» 가 아니라 «확인 불가» 다.

### 4-5. 그래서 무엇을 해야 여기가 열리나

**최소 경로** (PNG 카드 1장 대조까지):

1. Python 실설치(Store 별칭 말고) → `pip install pillow numpy`
2. ④ 를 푼다 — `WS`·`EP_DIR` 을 **기계 상수에서 빼낸다.** 정관 §0 4층 ① 자리다:
   환경변수나 «자기 위치에서 거슬러 올라가 찾기» 로 바꾸면 **검사가 필요 없어진다.**
   🔴 100개 파일이라 **한 회차 작업이고, 이 PR 범위 밖이다.**
3. 그 뒤 `02_what.png` 를 조판해 `a54201a4ce885775` 와 대조.

**영상 카드까지 열려면** `ffmpeg`·`ffprobe` 추가. **편 게이트까지 열려면** `tomangchi-skill`
클론.

🔴 **이 절은 «다음에 한다» 로 끝나지 않는다.** 정관 §0 이 「«다음에 정한다» 로 미룬 것은
목록 파일에 적는다」 고 못박았으므로 **`docs\infra-backlog.md` 23번**에 등재했다 —
후보 3안·재개 조건 3개·여는 순서. **미루는 쪽이 감시처를 함께 적지 않으면 미룬 것이
아니라 버린 것이다.**

---

## 하지 않은 것 (금지 조건 준수)

| 금지 | 이 회차 |
|---|---|
| 워커 실행 | 🟢 안 했다 — 헤르메스·스카우트·유통 계열 **0건** |
| 스케줄 등록 | 🟢 안 했다 — `schtasks`·크론 **0건** |
| 승인 폴더 생성 | 🟢 안 했다 — `publish_approval\` 을 만들지도 건드리지도 않았다 |
| `THREADS_*` 보관 | 🟢 안 했다 — 실측도 **길이만** 읽었고 셋 다 0이다 |
| 발행 경로 | 🟢 안 했다 |

**바꾼 것**: `core.hooksPath` 2건(레포 로컬 설정) · git 전역 신원 · 사이트 레포
`workshop\`(gitignore 대상) · 이 브랜치의 문서 6개.

---

## push 는 됐다 · PR 열기만 사람 손이 필요하다

🔴 **처음에 «자격이 없어 push 도 안 된다» 고 적었는데 틀렸다. 실측하니 됐다.**
`gh auth status` 만 보고 «GitHub 자격이 없다» 로 넘겨짚은 것이고, **`gh` 와 `git` 은
자격을 다른 데서 가져온다.**

| 경로 | 자리 | 상태 |
|---|---|---|
| `git push` | **Git Credential Manager** (`C:\Program Files\Git\etc\gitconfig` 의 `credential.helper=manager`) | 🟢 **토큰 있음 — push 성공** |
| `gh pr create` | `gh` 자체 keyring + `hosts.yml` | 🔴 **미로그인** |

- 🟢 브랜치 `onboarding-repo-owner` **원격에 올라갔다** (`origin` 에 새 브랜치).
- 🔴 **PR 은 못 열었다** — `gh` 가 미로그인이다.

🔴 **자격 문서가 이 갈림을 안 적어 두었다.** `docs\onboarding-credentials.md` 는 GitHub 줄
하나에 «`gh` OAuth 토큰 · 자격 증명 관리자(gh keyring) + `hosts.yml`» 을 묶어 놓았는데,
**실제로는 소비자가 둘이고 저장소도 둘이다.** 이 기계가 그 증거다 — GCM 에는 토큰이 있고
`gh` 에는 없어 **한쪽만 되는 상태**가 나왔다. 「GitHub 자격」 한 칸으로는 이 상태를 적을
수 없다. 🔴 **자격 문서 정비 후보**로 남긴다.

**사람이 한 번 해야 하는 것** — 터미널에서:

```
gh auth login
```

스코프는 자격 문서대로 `repo`·`read:org`·`gist`. 그 뒤 `gh pr create` 로 PR 을 연다.
브랜치는 이미 올라가 있으므로 **웹에서 바로 열어도 된다**:
`https://github.com/OhjaejunO/jj-company/pull/new/onboarding-repo-owner`

🔴 **머지는 실장 승인이다** — 지시대로 이 회차는 PR 까지이고, 머지하지 않는다.

---

## 이 PR 이 담은 것

| 파일 | 무엇 |
|---|---|
| `docs\workshop-repo-sync.md` | 주소 3군데 + 이전 경위·리다이렉트 주의 |
| `docs\infra-backlog.md` | 21번 ㉮ 기록 · **22번 갱신**(이전 완료 · 갱신 자리 목록 · 남은 판정) |
| `docs\plan-workshop-source-repo.md` | 경로 A 상태 줄 |
| `scripts\workshop_repo_sync.py` | 머리 도해 + **`REMOTE` 상수** |
| `docs\clause-backlog.md` | **C-35 등재** — 소유 계정은 자산 경계 판정 사항 |
| `scripts\githooks\README.md` | 클론 표에 이 기계 추가 + 다른 레포 표 |
| `docs\onboarding-report-2026-08-30.md` | 이 문서 |

🔴 **바꾸지 않은 `PU3-Lab` 이 하나 있다** — 워크숍 레포 안
`99_지원제출\그룹바이\텍스트_교체본_v2.md` 의 `PU3-Lab/factory-space` 는 **다른 레포**다.
낱말로 일괄 치환했으면 남의 주소를 틀리게 고쳤다.
