# 헤르메스 ⑤ 스카우트 보조 — 양식 4 · 층: 제안 · 상태: 설계 (2026-08-26)

**JOB** content-scout 가 못 닿는 소스(스케줄 allowlist 밖 — 승인 거부 14건 실측: `yt-dlp`·`curl`·`python -c`)를 대신 훑어 **인계 레코드 후보**를 낸다. 제출은 **`handoff_schema.py` 경유만** — 검사기 🟢 블록만 넘긴다.

**TRIGGER** tomangchi-scout(08:00) **앞** 07:45 스케줄 — 산출이 그날 스캔의 입력이 되게(정관 §4 «래퍼 선실행» 계열: `source_watch.py` 와 같은 자리).

**INPUTS** `departments/marketing/config.md` 소스 표(정본, 읽기) · `handoff_schema.py` `FIELDS`·`MIN_URLS`(정본) · 외부 소스.

**PROCESS** 1. 소스 표에서 content-scout 가 `UNSUPPORTED`/승인 거부로 못 본 항목만 고른다 2. 후보를 `---8<--- #id` 레코드로 쓴다(모르는 값은 `미기입`) 3. `py handoff_schema.py <파일>` 통과 블록만 `logs/scout-data/assist_<날짜>.md` 에 남긴다 4. `STATUS:`.

**OUTPUT** `logs/scout-data/assist_<날짜>.md` — content-scout 가 읽는 **입력**이지 제안이 아니다. **스캔로그·대기함·리포트 직접 쓰기 금지.**

**RULES — 금지 자리** 판정(제안/보류/기각) 금지 — 판정은 content-scout·JJ · 조문 제안 금지 · 발행 금지 · 정본 직접 쓰기 금지 · **레코드 값 지어내기 금지**(`미기입`).

**GATE** `handoff_schema.py` 검사(이미 있음 — 구현 실물 참조). 역검증: 검사기 자체 역검증 9케이스(#70).

**성공지표** keep rate = content-scout 리포트에 «제안» 으로 올라간 후보 ÷ 낸 후보 ≥ 50% · 부수: `미기입` 비율(낮을수록 좋음, 단 지어내면 안 된다).

**FAIL CONDITION** 소스 표 못 읽음 · 파일 못 씀. 소스 «확인 불가» 는 부분 표기.

**6질문 답** ① 소스 표·스키마(정본) + 외부 ② assist 파일 유일 작성자, 대기함은 content-scout 만 ③ content-scout 정의 §제안 (a)·SKILL §5.5 1~2단계 ④ 메모리 · 스캔로그(판정을 보면 편향) · 발행로그 ⑤ 레코드 필드 교정 반복 → R6(스키마 `FIELDS`) ⑥ 새 필드 필요 3회 → 스키마 개정 PR(정의는 참조라 자동 추종).

**하네스 판정** 봇 메모리 = **부채**(중복 제안 방지는 대기함·스캔로그 dedup 이 맡는다). **채점** 반복 2 · 시간 1 · 검증 2(스키마) · 실패 비용 2 · 오염 1(logs 쓰기) = **8/10**.
