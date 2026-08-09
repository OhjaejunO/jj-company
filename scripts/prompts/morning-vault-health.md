ops-auditor 서브에이전트를 사용해 JJ-Brain vault 건강 감사를 1회 실행하라.

오늘 날짜는 {{DATE}} 이다.

- 감사 대상: C:\Obsidian.JJ\JJ-Brain (읽기 전용, 절대 수정 금지)
- 설정: departments/ops/config.md 를 먼저 읽고 그 값을 따르라
- 점검 항목은 .claude/agents/ops-auditor.md 정의를 그대로 따른다
- 데이터로 확인되지 않는 항목은 추측하지 말고 "확인 불가 + 사유"로 기록하라
- 각 수치는 어떤 방법으로 산출했는지 근거를 남겨라
- 전날 리포트가 reports/ 에 있으면 증감 비교 한 줄을 추가하고, 없으면 "최초 실행"이라고 적어라

완성된 리포트를 reports\{{DATE}}_morning-vault-health.md 파일로 저장하라.
리포트 형식은 CLAUDE.md 5절을 따르고, 등급 A, 결론 3줄 먼저, 문제는 🔴/🟡/⚪ 로 분류하고 "JJ가 할 일" 목록을 포함한다.

reports/ 디렉토리 밖의 어떤 파일도 수정하거나 생성하지 마라. vault 파일은 절대 수정하지 마라.

작업을 마치면 마지막 줄에 STATUS: OK 또는 STATUS: FAIL <사유> 만 출력하라.
