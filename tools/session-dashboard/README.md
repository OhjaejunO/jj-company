# 세션 대시보드 — «지금 어느 에이전트가 무슨 일을 하나» 한 페이지 (2026-09-04 · 1판)

```
py tools\session-dashboard\dashboard.py            → http://127.0.0.1:8765
py tools\session-dashboard\dashboard.py --once     → JSON 한 번 (검사용)
py tools\session-dashboard\dashboard.py --self-test
```

## 무엇을 보여주나

카드 하나 = 살아 있는 Orca 터미널 하나. 카드에는 레포·브랜치·**작업 중/대기**(마지막 출력 시각) ·
AI 제목 · **마지막 지시** · **마지막 답** · 모델·effort · 컨텍스트 토큰 · PR 링크 · 터미널 미리보기 한 줄이 있다.
제목이나 «↗ 세션으로» 를 누르면 Orca 의 그 탭이 앞으로 온다(`orca terminal switch`).
아래 입력창은 그 터미널에 지시를 보낸다(`orca terminal send --enter`). Enter 전송 · Shift+Enter 줄바꿈.
터미널이 없는 스케줄 에이전트(스카우트·감사)는 오늘 로그의 `STATUS` 줄로 점선 카드가 된다.

## 데이터 출처 (전부 읽기)

| 무엇 | 어디서 |
|---|---|
| 살아 있는 터미널 | `orca terminal list --json` — tmux 없는 Windows 에서 Orca 가 그 자리다 |
| 세션 내용 · claude | `~\.claude\projects\<프로젝트>\<세션>.jsonl` 꼬리 3MB — `ai-title` · `last-prompt` · `pr-link` · 마지막 user/assistant |
| 세션 내용 · codex | `~\.codex\sessions\<연>\<월>\<일>\rollout-*.jsonl` — `session_meta.cwd` 로 짝 · `turn_context.model` · message user/assistant · token_count |
| 세션 내용 · grok | `~\.grok\sessions\<작업폴더 URL 인코딩>\<세션>\` — `summary.json`(모델·effort·요약) · `chat_history.jsonl` · `prompt_history.jsonl` |
| 세션 내용 · hermes | `%LOCALAPPDATA%\hermes\state.db` — `sessions`·`messages` (읽기 전용 열기). 작업 폴더 개념이 없어 **늘 «짝 추정»** |
| 사람 확인 대기 | Orca 터미널의 `agentWait` — 값이 있으면 카드가 «확인 필요»(앰버)로 맨 앞에 선다 |
| 스케줄 에이전트 | `C:\Users\ojaej\jj-company\logs\scheduled\*_<오늘>.log` |

## 한계 (1판 · 못 잡는 것을 적어 둔다)

- **세션 ↔ 터미널 짝은 작업 디렉토리로 맞춘다.** 같은 폴더에 최근 1시간 안에 쓰인 세션이 둘 이상이면 가장 최근 것을 고르고 카드에 `짝 추정` 을 단다.
- «작업 중» 판정은 «마지막 터미널 출력이 6초 안» 이다 — 긴 도구 호출 중에 출력이 없으면 «대기» 로 보일 수 있다.
- 비용은 안 센다(기록 전체를 읽어야 해서). 컨텍스트 토큰은 마지막 응답의 usage 로 잰다.
- **127.0.0.1 에만 묶는다.** 폰에서 보려면 Tailscale 같은 사설망으로 이 PC 에 붙어 `http://<PC>:8765` 로 연다 — 그때 바인드 주소를 바꾸는 옵션을 붙인다(2판).
- 입력창의 전송은 사람이 누르는 것이고, 대시보드 자신은 아무것도 보내지 않는다.

## 오피스 뷰 — `/office` (2026-09-04 · 그림 2)

같은 `/api/snapshot` 을 사무실 그림으로 그린다. 책상 하나 = 터미널 하나, 클릭 = `orca terminal switch`.
캐릭터는 `assets/<agent>_<pose>.png` 12장(클로디 v2·그록봇·헤르메스·코덱스 × 타자·기댐·손 듦) — Higgs nano_banana_pro 로 뽑고 배경 제거 뒤 1024px 로 줄인 컷아웃.
상태 매핑: `agentWait` → `hand`(앰버 «확인이 필요해요» 말풍선) · 작업 중 → `typing`(초록 바닥 광) · 대기 → `idle`(채도 낮춤).
스케줄 에이전트는 «야간 근무» 줄의 램프(OK 초록 · FAIL 빨강 · 실행 중 깜빡임). `?demo` 를 붙이면 시연용 가짜 책상 셋이 뒤에 붙는다(클릭 무효).
캐릭터 원본·엘리먼트: 클로디 v2 element `ca26eff9…` + 옷(흰 셔츠·빨간 타이·갈색 반바지, JJ 판정 C) · 그록봇(ep39 마스코트 + 헤드셋 + 후디 2) · 헤르메스(JJ 참고 → 토이판 G) · 코덱스(로고 → 구름 머리 + 후디 C). 로스터 등재는 토망치 트랙(JJ).

## 다음 판 후보

- 세션 ↔ 터미널 짝을 프로세스 목록(`claude.exe --resume <id>`)으로 확정.
- 폰 접근(바인드 옵션 + 토큰).
