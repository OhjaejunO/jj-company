content-scout 서브에이전트로 토망치랩 아침 스캔을 1회 실행하라.

오늘은 {{DATE}} ({{WEEKDAY}}) 이다.

## 정본 문서
- 토망치랩 SKILL.md: `C:\Users\ojaej\.claude\skills\tomangchi\SKILL.md` — **먼저 읽어라**
- 부서 설정: `departments/marketing/config.md`
- 에이전트 정의: `.claude/agents/content-scout.md` — 이 정의를 그대로 따른다

## 경로
- 스캔로그 폴더: `C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop\스캔로그`
- content-ops: `C:\Users\ojaej\orca\content-ops`
- 환경변수 `SCAN_LOG_DIR` 는 이미 설정돼 있다 (scan_check --from-log 용)

## 실행 순서 (에이전트 정의의 고정 순서)
1. 스캔로그 폴더에서 **가장 최근 로그 날짜**를 확인해 조사 범위를 정한다 (그 날짜 이후 ~ 현재). 고정 날짜 범위 금지.
2. 후보 수집 — AI 소식 / 기회 / 두드려봄 1차 후보 3축.
3. 스캔로그 `{{DATE}}.md` 에 기록한다.
   - 파일이 있으면 **기존 내용을 절대 수정·삭제하지 말고** 맨 아래에 `## content-scout 자동 스캔 (HH:MM)` 섹션으로 append 하라.
   - 파일이 없으면 새로 만든다.
   - 후보 전체 + 각각의 판정 사유를 남긴다 (채택분만 적지 마라).
4. 중복 판정:
   `cd C:\Users\ojaej\orca\content-ops` 후
   `./venv/Scripts/python.exe manage.py scan_check --from-log {{DATE}}`
   실패하면 후보를 인자로 직접 넘겨 재시도하고, 그래도 안 되면 리포트에 "확인 불가 + 사유"로 남겨라.
5. 판정 결과(1위 Topic·유사도·도구 라벨·에이전트 판정)를 스캔로그 네 섹션에 표로 추가한다.
6. 리포트 `reports\{{DATE}}_tomangchi-scout.md` 작성.

## 오늘이 일요일이면
리포트에 **"주간 요약 재료"** 섹션을 추가하라. 스캔로그 폴더의 이번 주 로그 전체를 읽어 §6.4 기준 본문 카드 후보 6~10건을 추린다. 재료 정리까지만 하고 제작은 하지 마라.

## 정확성
- 확인된 것만 써라. URL을 지어내지 마라. 접속 안 된 출처는 "확인 불가"로 명시.
- 이중 소스 대조(§6) 의무. 공식 페이지와 다르면 공식 페이지가 이긴다. 불일치는 반드시 기록.
- 영상 첨부 게시물에 "캡처 가능" 표기 금지.
- 기회는 판정 3조건(한국 참여 가능 / 마감 D-3 이상 / 공식 소스에서 마감일 직접 확인) 전부 충족한 것만.

## 쓰기 제한
`reports\` 와 스캔로그 파일 **외에는 어떤 파일도 만들거나 수정하지 마라.**
content-ops 는 조회만 (DB 쓰기·Deadline 등록 금지). SKILL.md 수정 금지.

## 산출
리포트 파일 마지막 줄에 `STATUS: OK` 또는 `STATUS: FAIL <사유>` 를 반드시 넣어라.
작업을 마치면 무엇을 어디에 썼는지 3줄 이내로 요약해 출력하라.
