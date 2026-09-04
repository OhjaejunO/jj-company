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
| 세션 내용 | `~\.claude\projects\<프로젝트>\<세션>.jsonl` 꼬리 3MB — `ai-title` · `last-prompt` · `pr-link` · 마지막 user/assistant |
| 스케줄 에이전트 | `C:\Users\ojaej\jj-company\logs\scheduled\*_<오늘>.log` |

## 한계 (1판 · 못 잡는 것을 적어 둔다)

- **세션 ↔ 터미널 짝은 작업 디렉토리로 맞춘다.** 같은 폴더에 최근 1시간 안에 쓰인 세션이 둘 이상이면 가장 최근 것을 고르고 카드에 `짝 추정` 을 단다.
- «작업 중» 판정은 «마지막 터미널 출력이 6초 안» 이다 — 긴 도구 호출 중에 출력이 없으면 «대기» 로 보일 수 있다.
- 비용은 안 센다(기록 전체를 읽어야 해서). 컨텍스트 토큰은 마지막 응답의 usage 로 잰다.
- **127.0.0.1 에만 묶는다.** 폰에서 보려면 Tailscale 같은 사설망으로 이 PC 에 붙어 `http://<PC>:8765` 로 연다 — 그때 바인드 주소를 바꾸는 옵션을 붙인다(2판).
- 입력창의 전송은 사람이 누르는 것이고, 대시보드 자신은 아무것도 보내지 않는다.

## 다음 판 후보

- 그림 2(오피스 뷰): 같은 `/api/snapshot` 을 사무실 그림으로 그리고 책상 클릭 = `switch`.
- 세션 ↔ 터미널 짝을 프로세스 목록(`claude.exe --resume <id>`)으로 확정.
- 폰 접근(바인드 옵션 + 토큰).
