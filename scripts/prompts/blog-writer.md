blog-writer 서브에이전트로 네이버 블로그 초안을 1편 써라.

오늘은 {{DATE}} ({{WEEKDAY}}) 이다. 요일과 무관하게 **한 소재(kind: topic)** 한 편이다 — 브리프의 «최근 발행편» 중 블로그 글(`reports\blog\*_*.md` 의 `source:`)이 아직 없는 가장 최근 편 하나. 전부 이미 썼으면 초안을 만들지 말고 리포트에 «쓸 편 없음» 으로 적어라.

## 정본
- 에이전트 정의: `.claude/agents/blog-writer.md` — 그대로 따른다
- 형식: `docs/blog-format.md`
- 게이트: `scripts/blogcheck.py`

## 재료 (래퍼가 만들었다 — 네가 웹을 새로 조사하지 않는다)
- 브리프: `{{BRIEF}}`
  브리프에 «소재 0건» 이면 초안을 만들지 말고 리포트에 그렇게 적어라.

## 산출
1. `reports\blog\{{DATE}}_<한글 짧은 이름>.md` — 프런트매터 `kind`·`date`·`source`·`status: draft`, 한마디 자리는 `[[JJ 한마디]]`.
2. 게이트 실행 → FAIL 이면 고치고 재실행(최대 3회).
3. `reports\{{DATE}}_blog-writer.md` — 결론 3줄, 게이트 마지막 줄 인용, «JJ 가 할 일»(한마디 2문장 · 복붙 · 이미지 파일 경로).

## 쓰기 제한
위 두 파일 외에는 아무것도 만들거나 고치지 마라.

리포트 마지막 줄에 `STATUS: OK` 또는 `STATUS: FAIL <사유>` 를 넣어라. 끝나면 무엇을 어디에 썼는지 3줄로 출력하라.
