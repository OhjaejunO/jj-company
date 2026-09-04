# docs/diagrams — archify 도식 (시범 · 2026-09-04)

`tt-a1i/archify` 스킬(사용자 범위 `~\.claude\skills\archify`)로 만든 **검증되는 도식**. JSON(IR)이 정본이고 HTML 은 산출물이다.

| 파일 | 무엇 | 검증 |
|---|---|---|
| `jj-company.architecture.json` / `.html` | **회사 구조** — 대표실 · 작업장(worktree→PR) · 운영 서버(스케줄러→래퍼→에이전트 5·리포트·승인 파일·발행 워커) · 자회사 SKILL 정본 · 출장지(읽기 전용)·외부 채널. 뷰 3개(아침 회차 · 발행 장치 · 경계와 정본) | `archify validate architecture … --quality showcase` 9항 통과 · 오류 0 (2026-09-04) |
| `schedule-pipeline.workflow.json` / `.html` | 스케줄 회차 파이프라인 — 작업 스케줄러 → lock → git-sync → auth_check → deploy-skill → permission_probe → `claude -p` → 리포트, 실패 분기 셋 | `archify validate workflow … --quality showcase` 9항 통과 · 오류 0 |

- 고치려면 JSON 을 고치고 `node bin\archify.mjs deliver workflow <json> <html> --quality showcase` 로 다시 낸다 — 검증을 못 넘으면 HTML 이 안 바뀐다.
- 정관 §4 의 실값과 어긋나면 **도식이 틀린 것**이다(정관 §0 «실물이 정본»). 래퍼 스크립트가 바뀌면 여기도 같이.
- 업데이트 체크는 `ARCHIFY_UPDATE_CHECK_DISABLED=1` 로 끄고 돌린다.
