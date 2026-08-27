ops-auditor 서브에이전트를 사용해 JJ-Brain vault 건강 감사를 1회 실행하라.

오늘 날짜는 {{DATE}} 이다.

- 감사 대상: C:\Obsidian.JJ\JJ-Brain (읽기 전용, 절대 수정 금지)
- 설정: departments/ops/config.md 를 먼저 읽고 그 값을 따르라
- 점검 항목은 .claude/agents/ops-auditor.md 정의를 그대로 따른다
- 감사 데이터는 **이미 산출돼 있다. 네가 스크립트를 돌리지 않는다** (2026-08-18 개편):
  - vault 감사 결과: {{VAULT_DATA}}
  - 열린 PR 목록: {{PR_DATA}}  (값이 UNAVAILABLE 이면 조회 실패 — "확인 불가"로 적고 0건으로 적지 마라)
  - 운영 서버 신선도: {{FRESH_DATA}}  (`BEHIND_COUNT=` · `LOCAL_HEAD=`. UNAVAILABLE 이면 "확인 불가")
  - **인증·마운트 점검**: {{AUTH_DATA}}  (`GH_AUTH=` · `DRIVE=` · `AUTH_ALL_OK=`. 🔴 **`AUTH_ALL_OK=no` 면 리포트에 🔴 로 올린다** — `GH_AUTH` 가 OK 가 아니면 «push·PR 막힘», `DRIVE` 가 OK 가 아니면 «폰 전달 막힘» 으로 적고 `*_FIX=` 줄을 «JJ가 할 일» 에 그대로 옮긴다. UNAVAILABLE 이면 «확인 불가». **이것 때문에 STATUS 를 FAIL 로 내리지 마라** — 감사는 성립한다)
  - 스케줄 무기록 종료: {{RUNS_DATA}}  (`RUNS_INCOMPLETE=` · `STARTED_RESIDUAL=` · `RUNS_VERDICT=`. RED 면 🔴, UNAVAILABLE 이면 "확인 불가")
  다섯 파일을 Read 로 읽어라. 파일이 없거나 값이 비면 "확인 불가 + 사유"로 기록하라.
- 데이터로 확인되지 않는 항목은 추측하지 말고 "확인 불가 + 사유"로 기록하라
- 각 수치는 어떤 방법으로 산출했는지 근거를 남겨라
- 전날 리포트가 reports/ 에 있으면 증감 비교 한 줄을 추가하라.
  🔴 **없으면 «최초 실행»으로 넘기지 마라** — 점검 항목 7 에 따라 «어제 리포트 부재»로 판정하라.

완성된 리포트를 reports\{{DATE}}_morning-vault-health.md 파일로 저장하라.
리포트 형식은 CLAUDE.md 5절을 따르고, 등급 A, 결론 3줄 먼저, 문제는 🔴/🟡/⚪ 로 분류하고 "JJ가 할 일" 목록을 포함한다.

reports/ 디렉토리 밖의 어떤 파일도 수정하거나 생성하지 마라. vault 파일은 절대 수정하지 마라.
너에게는 Bash 가 없다 — 스크립트를 돌리거나 만들려 시도하지 말고, 필요한 값은 위 데이터 파일에서 읽어라.

작업을 마치면 마지막 줄에 STATUS: OK 또는 STATUS: FAIL <사유> 만 출력하라.
