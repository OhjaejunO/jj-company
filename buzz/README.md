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

## 앱에서 만든 에이전트를 VPS 에서 돌리는 길 (`backend/`)

Buzz 데스크톱은 에이전트 실행을 **원격 기질**에 위임할 수 있다 — 규격은 buzz 레포
`docs/remote-agents.md` 이고, 방식은 PATH 에 있는 `buzz-backend-<id>` 실행파일이다.
앱이 그것을 한 번에 한 동작씩 띄워 stdin 으로 JSON 하나를 주고 stdout 에서 하나를 읽는다
(`info` · `deploy` 둘뿐). `deploy` 페이로드에 신원·릴레이·시스템 프롬프트·모델·런타임·
팀 지시문이 전부 들어 있어, 받아서 systemd 유닛으로 세우면 그것이 곧 «적합한 런처» 다
(규격 §Launchers 가 systemd 유닛을 명시적으로 그 자리에 놓는다).

`buzz/backend/` 가 우리 구현이다. 빌드는 **VPS 에서 크로스 컴파일**한다 — 이 PC 에
컴파일러가 없다(cargo·rustc·go·gcc·cl 전부 부재, 2026-09-13 실측).

```sh
# PC 에서
scp -i ~/.ssh/buzz_vps -r buzz/backend/Cargo.toml buzz/backend/src root@187.127.100.11:/root/build/jjvps/
# VPS 에서
cd /root/build/jjvps && PATH=$HOME/.cargo/bin:$PATH cargo build --release --target x86_64-pc-windows-gnu
# 다시 PC 로 - 앱이 ~/.local/bin 을 PATH 와 별개로 뒤진다(discover_provider_candidates)
scp -i ~/.ssh/buzz_vps root@187.127.100.11:/root/build/jjvps/target/x86_64-pc-windows-gnu/release/buzz-backend-jjvps.exe ~/.local/bin/
```

역검증은 `buzz-backend-jjvps.exe --self-test`(축 11개). 🔴 **그 검사는 `handle()` 만 잰다** —
stdin/stdout 배관은 실제로 파이프를 물려 따로 봤다(정상 요청 · 깨진 JSON · 빈 입력 셋 다 exit 0).

### 🟢 탐침이 답을 냈다 — 길은 열려 있다 (2026-09-14 실측)

탐침을 심은 이유는 둘이었다.

- 규격이 **「v1 provider 범위는 macOS+Linux」** 라고 선언했다(DECISION B). 우리는 Windows 다.
- **알려진 결함 1**: Windows 에서 `.exe` 접미사가 provider id 에 남아 **deploy 에서 id 검증에 걸린다** —
  「드롭다운엔 뜨고, info 는 통과하고, deploy 만 깨진다」. 설치본이 2026-09-06 판이라 이 결함이
  살아 있을 수 있었다(소스 클론 9/08 판에는 접미사를 떼는 코드가 있다 — 두 판이 다르다).

그래서 `deploy` 를 다 짜 놓고 그 자리에서 막히는 대신, **뜨는지·id 가 뭔지부터** 탐침으로 쟀다.
**두 결과가 서로 다른 글자를 내도록** 갈라 뒀다 — 탐침의 `deploy` 는
`probe build: deploy is not implemented yet` 을 in-band 실패로 내므로,
그 문구가 보이면 id 검증을 통과한 것이고 다른 오류가 나면 결함 1 이 살아 있는 것이다.

**2026-09-14 JJ 가 데스크톱에서 쟀다 (버리는 에이전트 하나를 `Run on: jjvps` 로 만들어 저장):**

- 에이전트 생성 폼의 **Run on** 드롭다운에 `This computer` 와 나란히 **`jjvps`** 가 떴다.
  🔴 **`.exe` 가 안 붙었다** — 탐색 단계에서 이미 접미사가 떨어진다.
- 저장하니 기동이 실패하며 **`probe build: deploy is not implemented yet.`** 이 그대로 올라왔다.
  즉 `deploy` 가 **id 검증을 통과해 우리 바이너리까지 도달했다.**

**판정 — 이 설치본에서 결함 1 은 살아 있지 않다.** DECISION B(범위 선언)는 「지원하지 않는다」이지
「막혀 있다」가 아니었고, 실물은 통과였다(§0 «실물이 정본이다»).

🔴 **쟀다고 끝난 것이 아니다 — 아직 안 쟀는데 다음 판에서 갈릴 것들:**

- **판올림하면 다시 재야 한다.** 지금 판정은 **2026-09-06 설치본 한 판**에 대한 것이다.
- **`deploy` 페이로드의 실값을 못 봤다** — 탐침은 `op` 만 보고 되돌려 보냈다. 신원·릴레이·
  시스템 프롬프트가 **어떤 꼴로** 오는지는 `deploy` 를 채울 때 로그로 먼저 찍어 확인한다.
- **v1 범위 선언은 그대로다.** 지금 도는 것이 다음 판에도 돈다는 보장이 아니다.

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
