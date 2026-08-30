# 자격·설정 목록 — 집 컴퓨터 온보딩 (2026-08-30 실측)

> 🔴 **값은 이 문서에 없다.** 정관 §6 «시크릿/토큰을 리포트나 로그에 기록» 금지 —
> **이름과 자리만** 적는다. 길이는 «채워져 있는가» 를 보려는 것이고 값이 아니다.
> 🔴 **레포에 담기지 않는다.** 아래 전부 `~\.claude\` 나 사용자 환경변수에 있고,
> `git clone` 으로는 하나도 안 따라온다.

## 3분류

| 자격 | 이름 | 자리 | 분류 | 비고 |
|---|---|---|---|---|
| GitHub | `gh` OAuth 토큰 | **Windows 자격 증명 관리자**(gh keyring) + `~\AppData\Roaming\GitHub CLI\hosts.yml` | 🟡 **집에서 새 발급** | `gh auth login` 한 번. 스코프 `repo`·`read:org`·`gist` |
| X 조회 | `X_BEARER_TOKEN` (114자) | 사용자 환경변수 | 🟢 **집에 복제** | 같은 키를 두 기계가 써도 된다 — 아래 «쿼터» |
| Threads 발행 | `THREADS_TOKEN` (207자) · `THREADS_APP_ID` (16자) | 사용자 환경변수 (+ `HKCU\Environment` 대체 경로) | 🔴 **이 기계 전용** | 발행은 이 기계에서만. 아래 «왜» |
| 구글 드라이브 | (토큰 아님 — 데스크톱 앱 로그인) | Google Drive 데스크톱 · 마운트 `G:\내 드라이브` | 🟡 **집에서 새 발급** | 앱 설치 + 로그인. 드라이브 문자는 고정하지 않는다 |
| Anthropic | `ANTHROPIC_*` / Claude Code 로그인 | Claude Code 자체 | 🟡 **집에서 새 발급** | |
| OpenAI | `OPENAI_API_KEY` (164자) | 사용자 환경변수 | 🟢 **집에 복제** | xreview 계열 |
| OpenRouter | `OPENROUTER_API_KEY` (73자) | 사용자 환경변수 | 🟢 **집에 복제** | 헤르메스 |
| Higgs (이미지 생성) | MCP 커넥터 | Claude 계정에 붙은 커넥터 | 🟡 **집에서 새 발급** | 로그인하면 따라온다 |
| 오케스트레이션 | `ORCA_*` · `CLAUDE_CODE_MESSAGING_TOKEN` · `HERMES_*` | 사용자 환경변수 | 🔴 **이 기계 전용** | 이 기계의 실행 환경에 묶인 값 |

**분류 기준**
- 🟢 **집에 복제** — 계정 단위 키다. 두 기계가 같은 값을 써도 되고, 쿼터만 나눠 쓴다.
- 🟡 **집에서 새 발급** — 기기·세션에 묶인 인증이다. 옮기는 것보다 다시 로그인이 맞다.
- 🔴 **이 기계 전용** — 옮기면 안 되거나(발행 자격) 옮겨도 뜻이 없다(실행 환경 값).

## 🔴 Threads 토큰을 «이 기계 전용» 으로 두는 이유

기술적으로는 복제된다. 그런데 **발행은 되돌림 비용이 가장 큰 동작**이고, 정관 §0 의 승인
장치(`publish_approval\` 3확인 · 매 회차 권한 프로브)는 **한 기계의 파일 상태**를 근거로
선다. 두 기계에 토큰이 있으면 «어느 기계가 무엇을 올렸나» 를 영수증만으로 못 가른다
(영수증은 `logs\publish-receipts\` 에 있고 **레포에 안 담긴다**). 발행은 이 기계에서 한다.

## MCP — X 조회 경로

`~\.claude.json` → `mcpServers.x-search` → `node ~\.claude\mcp-servers\x-search\server.mjs`.
그 서버가 읽는 환경변수는 **`X_BEARER_TOKEN` 하나**다(소스 확인).
서버 파일 자체도 `~\.claude\` 아래라 **레포에 없다** — 집에서 따로 옮겨야 한다.

## X API 쿼터 — 두 기계가 같은 키를 써도 되는가

**된다.** 2026-08-30 실측:

| 값 | 실측 | 뜻 |
|---|---|---|
| `project_cap` | **3,000,000** / 월 | 프로젝트 월 조회 상한 |
| `project_usage` | **1,099** | 이번 달 쓴 양 — **0.04%** |
| `cap_reset_day` | **16일** | 매월 리셋일 |
| `x-rate-limit-limit` (search/recent) | **450** / 15분 | 순간 한도 |

조회량 기준으로 **문제 되지 않는다.** 한 편 조사에 쓰는 양이 수십 건이고 월 한도는 300만이다.
15분 450건 한도도 두 기계가 동시에 대량 조회하지 않는 한 닿지 않는다.

🔴 **티어 «이름» 은 확인 불가다.** API 가 돌려주지 않는다 — 한도 값으로 미루어 볼 뿐이고,
확정은 x.com 개발자 포털에서 사람이 본다(정관 §0).

## 자격 밖 — 레포로 안 오는 것

- `~\.claude\settings.json` (**deny rules 18건**) · `~\.claude\CLAUDE.md` · `hooks\`(bash-escape-guard) ·
  `skills\`(라이브 스킬 사본 — `deploy-skill.ps1` 로 재생성 가능)
- 각 레포의 `.claude\settings.local.json`
- 운영 서버의 `reports\`·`logs\`·`publish_approval\` (정관이 로컬 전용으로 못박은 자리)

## 점검

`scripts\auth_check.py` 가 아침 회차에서 `gh auth status` 와 드라이브 마운트를 조회한다.
집 기계를 세운 뒤 그것부터 한 번 돌려 `AUTH_ALL_OK` 를 본다.
