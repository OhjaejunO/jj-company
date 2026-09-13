# Buzz 봇 — 배선과 추가 절차

> **여기 적힌 것은 조회 결과다. 실물이 정본이다**(정관 §0).
> 실물은 VPS 의 `/etc/systemd/system/buzz-acp@.service`·`/etc/buzz-acp/*.env` 와 `systemctl` 상태다.

## 무엇이 어디에 있나

| 것 | 자리 | 비고 |
|---|---|---|
| 릴레이 | `wss://buzz-lku2.srv1967073.hstgr.cloud` | Hostinger VPS `187.127.100.11` · SSH 키 `~\.ssh\buzz_vps` |
| 하네스 | `/usr/local/bin/buzz-acp` | 에이전트 CLI 를 **자식 프로세스로** 띄운다 |
| 유닛 템플릿 | `/etc/systemd/system/buzz-acp@.service` | 정본 사본은 이 폴더의 `buzz-acp@.service` |
| 공통 env | `/etc/buzz-acp/common.env` | 릴레이 주소 · owner pubkey · MCP |
| 역할 env | `/etc/buzz-acp/<이름>.env` | CLI · **역할 정의 파일 경로** |
| 키 | `/root/buzz-keys/<이름>.env` (0600) | 🔴 **어디에도 옮겨 적지 않는다** |
| 역할 정의 | **이 레포 `buzz/agents/<이름>.md`** | 미러를 통해 봇에 도달한다 |
| 작업 자리 | `/srv/work/<이름>/<주제>` | 미러 **밖** 링크 worktree |

## 🔴 정의는 레포가 정본이다

봇의 인격은 `BUZZ_ACP_SYSTEM_PROMPT_FILE` 이 가리키는 **레포 안의 파일**이다.
VPS 에 사본을 두지 않는다 — 두면 갈리고, 갈리면 «어느 쪽이 정본인가» 를 매번 사람이 판단하게 된다.

바꾸는 길은 하나다: **레포에서 고치고 → PR → 머지 → 15분 안에 미러가 받는다.**
봇은 다음 턴부터 새 정의로 답한다(하네스가 세션마다 파일을 읽는다).

## 미러는 덮인다

`/srv/company` 는 15분마다 `git fetch` + `reset --hard` + `clean -fd` 다(`company-sync.timer`).
**추적되지 않는 파일까지 지워진다** — 2026-09-13 실측: 미러에 둔 파일은 사라지고,
`/srv/work` 의 링크 worktree 에 둔 파일은 **대조군으로 남았다.**

그래서 봇의 작업 자리는 미러 밖이다:

```sh
git -C /srv/company worktree add /srv/work/dev/<주제> -b bot/dev/<주제> origin/main
```

`core.hooksPath` 는 `/srv/company` 에 설정돼 있어 **링크 worktree 에도 적용된다**
(2026-09-13 양방향 실증: 미러에서 커밋하면 거부 · worktree 에서는 통과).

## 봇 하나 추가하기

```sh
# 1. 레포에 역할 정의를 넣고 머지한다 (buzz/agents/<이름>.md)
# 2. 미러가 받을 때까지 기다린다 (최대 15분) 또는 company-sync 를 직접 부른다
# 3. VPS 에서
bash /srv/company/buzz/new-agent.sh <이름> "<표시이름>" "<소개>" [에이전트CLI]
```

스크립트가 하는 일 — 신원 발급 · 릴레이 멤버 · **채널 멤버(`role='member'`)** ·
**`reconcile-channels`** · 프로필 · 역할 env · 기동 · **검증**.

🔴 **손으로 하지 않는 이유가 두 가지 있고 둘 다 조용히 실패한다.**
- `reconcile-channels` 를 빼면 DB 에 행이 있어도 봇은 `discovered 0 channel(s)` 로 앉는다.
- `role='bot'` 으로 넣으면 앱이 «관리형 에이전트»로 분류해 **@ 멘션 목록에서 숨긴다.**

둘 다 2026-09-10 에 실제로 겪은 것이고, 어느 쪽도 오류를 내지 않는다.

## 로스터

| 봇 | 부서 | 등급 | 담당 | CLI |
|---|---|---|---|---|
| `dev` | 개발팀 | B | worktree 코드 작업 · 검사기 · 커밋 · PR | `codex-acp` |
| `review` | 감리 | A | 교차검증 · 역검증 점검 (작성자 ≠ 감리자) | `claude-agent-acp` |
| `plan` | 대표실 | B | 소재·회차 정리 · 백로그 조회 | `claude-agent-acp` |
| `marketing` | 마케팅팀 | B | 카드·캡션·블로그 문안 초안 | `claude-agent-acp` |
| `ops` | 운영팀 | A | 회차 상태 · intent · 레포 상태 조회 | `claude-agent-acp` |
| `media` | 마케팅팀 | B | 영상·이미지 | 🔴 **켜지 않았다** — 생성 경로가 없다 |

**옛 봇 셋(`claude`·`codex`·`hermes`)은 그대로 돈다.** 역할 정의가 없는 범용 신원이고,
`dev`·`review` 가 그 자리를 대신하므로 **중복이다** — 끄는 것은 JJ 판정 자리로 남긴다.

## 끄는 명령이 듣게 하는 것 (`Restart`)

Buzz 원격 에이전트 규격(`docs/remote-agents.md`)의 **[L1] 5항**은 «의도적인 정상 종료를 되살리는
supervisor 는 그 자체로 부적합» 이라고 못박는다. 종전 유닛 넷은 전부 `Restart=always` 였다.

**2026-09-13 실측 — 축을 셋으로 갈라 쟀다** (내려둔 `ops` 로, 운영 봇은 건드리지 않고):

| 넣은 것 | 하네스가 한 일 | 코드 |
|---|---|---|
| `BUZZ_ACP_EXIT_AFTER_INACTIVITY=60` (의도적 종료) | 「inactivity bound reached — exiting gracefully」 | **0** · `Result=success` |
| 같은 것 + `Restart=always` | **5초 뒤 되살아났다** (`NRestarts=1` · `Scheduled restart job`) | — |
| `BUZZ_ACP_AGENT_COMMAND=/nonexistent-agent-binary` (진짜 실패) | 「all 1 agents failed to start」 | **1** · `Result=exit-code` |
| `BUZZ_RELAY_URL=wss://…invalid` (릴레이 불통) | 종료하지 않는다 — 백오프로 재시도 | — |

그래서 `Restart=on-failure` 가 두 축을 다 만족한다. **되살아나는 것을 실제로 재현한 뒤에 고쳤다** —
「always 는 나쁘다」는 추론이 아니라 `NRestarts` 가 0에서 1로 올라가는 것을 보고 고쳤다.

🔴 **드롭인의 `Environment=` 는 `EnvironmentFile=` 을 못 덮는다.** 이 측정 중에 두 번 헛돌았다
(릴레이 주소·에이전트 명령을 드롭인에 넣었는데 그대로 정상 동작했다). 역할 env 파일에 넣어야 먹는다 —
**그 사이의 결과는 「안 죽었다」가 아니라 「안 바뀐 것을 쟀다」였다.**

## 🔴 이 배선이 못 막는 것

- **PC 세션과 봇이 같은 일을 두 번 하는 것.** `claim.ps1` 은 이 기계에서 돌지 않는다
  (`pwsh` 부재 · 디렉터리가 PC 한 곳 고정). 지금 막는 것은 **역할 분리뿐**이다 — `docs/clause-backlog.md` C-61.
- **봇의 도구 실행 경계.** 하네스 기본값이 `--permission-mode bypass-permissions` 라
  봇은 도구 호출을 승인 없이 실행한다. PC 세션의 `settings.json` deny 규칙에 해당하는 것이 **없다.**
- **봇이 `/root` 를 읽는 것.** 유닛에 `User=` 가 없어 봇은 root 로 돈다 —
  다른 봇의 키 파일(`/root/buzz-keys/*.env`)이 **읽을 수 있는 자리에 있다.**
  구조로 닫으려면 `User=` 를 두고 키는 systemd 가 주입하게 해야 하는데,
  그러면 CLI 구독 인증(`/root/.claude`·`/root/.codex`)을 다시 붙여야 한다 — **JJ 판정 자리**.
- **구독 한도.** 봇 여럿이 JJ 의 같은 구독 로그인을 쓴다. 한도는 나눠 쓰는 것이고 **재 본 적 없다.**
