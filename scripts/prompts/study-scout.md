study-scout 서브에이전트로 이번 주 공부 노트 분석을 1회 실행하라.

오늘은 {{DATE}} 이다.

## 정의
`.claude/agents/study-scout.md` 를 그대로 따른다. A등급 — 읽고 리포트만.

## 재료 (래퍼가 만들었다)
- 새 노트 목록: `{{NEW_LIST}}` — `NEW|경로|바이트` / `CHANGED|경로|바이트` 줄. **이 목록의 파일만 읽는다.**
- 본보기 리포트: `reports\2026-09-05_study-notes-apply.md` — 같은 꼴로 쓴다.
- 실물 대조 대상: `CLAUDE.md` · `scripts\` · `.claude\hooks\` · `.claude\agents\` · `docs\`(특히 `infra-backlog.md`·`clause-backlog.md`·`learnings.md`).

## 산출
`reports\{{DATE}}_study-scout.md` 하나. 노트별 «요지 → 실물 대조(연 파일 경로) → 판정 후보», 끝에 제안 총괄 표와 JJ 판정 자리.

## 쓰기 제한
위 리포트 외에는 어떤 파일도 만들거나 고치지 마라. `C:\공부` 는 읽기만.

리포트 마지막 줄에 `STATUS: OK` 또는 `STATUS: FAIL <사유>` 를 넣어라. 끝나면 무엇을 어디에 썼는지 3줄로 출력하라.
