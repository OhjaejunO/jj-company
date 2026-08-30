# `scripts/githooks/` — 이 레포의 git 훅

훅 **본체는 여기 있고 커밋된다.** 훅이 실제로 돌게 하는 **연결은 클론마다 한 번** 걸어야 한다 —
git 이 옮겨 주지 않는 클론별 설정이라, 안 걸면 **가드가 조용히 사라진다.**

## 연결 (클론당 1회)

```
git config core.hooksPath scripts/githooks
```

또는 검사기가 대신 걸어 준다 — 그쪽을 권한다(설정·훅 존재·역검증까지 같이 본다):

```
powershell -File scripts\check-repo-guard.ps1 -Fix
```

## 지금 설정된 클론 (2026-08-30 실측)

| 클론 | 자리 | `core.hooksPath` |
|---|---|---|
| 작업장 (운영 기계) | `C:\Users\ojaej\orca\jj-company` | 🟢 `scripts/githooks` |
| 운영 서버 | `C:\Users\ojaej\jj-company` | 🟢 `scripts/githooks` |
| 작업장 (집 기계 · 2026-08-30 온보딩) | `C:\Users\opjj7\orca\jj-company` | 🟢 `scripts/githooks` |

**같은 기계의 다른 레포** — `core.hooksPath` 는 레포마다 따로 건다:

| 레포 | 자리 | `core.hooksPath` |
|---|---|---|
| `tomangchi-lab.github.io` | `C:\Users\opjj7\orca\tomangchi-lab.github.io` | 🟢 `scripts/githooks` |
| `tomangchi-workshop` (스테이징 클론) | `C:\Users\opjj7\tomangchi-workshop` | — **훅 폴더가 없다 · 대상 아님** |
| `tomangchi-skill` | — | 🔴 **이 기계에 클론이 없다** |

- 🔴 **«대상 아님» 과 «미설정» 을 같은 칸에 적지 않는다.** `tomangchi-workshop` 은 훅 폴더
  자체가 없어 걸 것이 없다. 둘을 뭉뚱그리면 다음 사람이 «빠뜨렸나» 를 매번 다시 확인한다.
- **집 기계는 사용자 폴더 이름이 다르다** — `ojaej` 가 아니라 `opjj7` 다. 이 표가 «자리» 를
  같이 적는 이유가 그것이다. 🔴 별개 사안이지만 같은 뿌리로, 워크숍 제작 코드 **100개 파일**이
  `C:\Users\ojaej\…` 를 상수로 박고 있어 집 기계에서 그대로 돌지 않는다
  (`docs\onboarding-report-2026-08-30.md`).

🔴 **새 클론은 이 설정이 필요하다.** `git clone` 만 하면 훅은 파일로 따라오지만 **돌지 않는다.**
새로 클론했으면 위 `-Fix` 를 한 번 돌려라.

## 무엇이 도는가

| 훅 | 언제 | 무엇 |
|---|---|---|
| `pre-commit` | 본 트리 커밋 | **거부한다** (정관 §3 — HEAD 는 공유 자원) |
| `pre-commit` | worktree 커밋 | 스테이지된 파일에 딸린 자체 검사 + **정본 폴더 untracked 검사** |
| `post-checkout` | 본 트리가 main 을 벗어남 | 경고 (git 에 `pre-checkout` 이 없어 차단은 못 한다) |

### 정본 폴더 untracked 검사 — **본 트리를 건너다본다**

`docs/directives/` 에 커밋 안 된 파일이 있으면 커밋을 거부한다. 백로그 18번이 근거다.

🔴 **왜 «여기» 가 아니라 «본 트리» 를 보는가.** 사람은 파일을 **본 트리**에 놓는다. 그런데 이 훅은
**worktree** 에서 도는데, worktree 는 자기 체크아웃만 본다 — 본 트리의 untracked 파일은 여기
아예 없으므로 로컬에서 `git ls-files --others` 를 돌리면 **빈 목록**이 나온다.
2026-08-29 실측: 같은 순간에 본 트리는 `docs/directives/_probe_seen.md` 를 보고 worktree 는
`[]` 를 냈다. 그대로 뒀으면 **검사가 영원히 통과**하면서 문제는 한 폴더 옆에 있었을 것이다.
`--git-common-dir` 의 부모가 본 트리이고, 거기를 본다.

## 🔴 이 장치가 못 막는 것 (§0 4층 ④)

- **사람이 파일을 놓는 순간**은 못 잡는다. 훅은 커밋에 걸리므로 **다음 커밋에서** 잡는다.
  놓고 아무도 커밋하지 않는 구간은 열려 있다 — 그 구간은 `check-repo-guard.ps1` 이 잡지만,
  그것은 **세션이 착수 시 돌려야 도는** 규율이다(2026-08-29 실측: 그날 한 세션이 열 회차 넘게
  돌면서 **한 번도 안 돌렸다**).
- **`core.hooksPath` 가 없는 클론**에서는 훅 자체가 안 돈다. 위 표 밖의 클론은 미설정으로 본다.
- 검사 대상은 **`docs/directives/` 뿐이다.** `reports\`·`logs\` 는 일부러 gitignore 라
  «untracked 전면 금지» 로 넓히면 매 회차 그 구분을 다시 배워야 한다.
