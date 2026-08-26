# 사건형 트리거 감시 목록 (헤르메스 ② 입력 · 공개 정보만)

> **정본 규칙**: 이 표에는 **공개 정보만** 둔다 — 트리거명·조건 문자열·감시처 URL. 소재명·훅각도·편성 판단·밝힐처리 같은 내부 필드는 여기 적지 않는다(설계 §6 공통 원칙 «입력은 공개 예정 텍스트만»).
> `scripts\event_watch.py` 가 이 표를 읽어 감시처를 열고, 헤르메스 `sagun` 이 결과를 판정·알림으로 바꾼다. 표를 고치는 것은 사람(JJ)이다.
>
> **2026-08-26 실측 — 대기함(`인수인계_대기함.md`) 레코드 전수에서 «X 되면 낸다» 형 사건형 조건은 0건이다.** 히기/Seedance 2.5 데뷔 트리거는 2026-08-22 편 폐기로 **해제**됐고(`_폐기/히기_Higgsfield_캐릭터_데뷔.md`), 스풉 «신작 나오면»은 릴스 원작자 소스 목록이 이미 감시처다. 그래서 첫 목록은 ⓐ JJ 가 시범 대상으로 지목한 Seedance 2.5(재등재 여부는 JJ 판단 — 시범 동안은 감시) ⓑ `config.md` 감시표의 공식 changelog·RSS 를 «신규 항목 발생» 트리거로 둔다.

| id | 트리거명 | 조건 문자열 (하나라도 나타나면 후보) | 감시처 URL | 유형 | 출처 |
|---|---|---|---|---|---|
| E1 | Seedance 2.5 출시 | `Seedance 2.5` · `Seedance2.5` | https://higgsfield.ai/creator-hub/changelog | 조건 문자열 | 대기함 규칙 4 예시(해제 이력 있음 · 시범 재감시) |
| E2 | Seedance 2.5 출시 (2차 감시처) | `Seedance 2.5` · `Seedance2.5` | https://runwayml.com/changelog | 조건 문자열 | 히기 킵 문서 «Higgsfield·Runway 양쪽 coming soon» |
| E3 | OpenAI 뉴스 신규 항목 | (신규 줄) | https://openai.com/news/rss.xml | 신규 항목 | config 제품 출시 감시 |
| E4 | OpenAI API changelog 신규 항목 | (신규 줄) | https://developers.openai.com/api/docs/changelog | 신규 항목 | config 제품 출시 감시 |
| E5 | Higgsfield changelog 신규 항목 | (신규 줄) | https://higgsfield.ai/creator-hub/changelog | 신규 항목 | config 제품 출시 감시 |
| E6 | Anthropic 뉴스 신규 항목 | (신규 줄) | https://www.anthropic.com/news | 신규 항목 | config 제품 출시 감시 |
| E7 | Claude Code 릴리스 노트 신규 항목 | (신규 줄) | https://docs.claude.com/en/release-notes/claude-code | 신규 항목 | config 제품 출시 감시 (본문 파싱 미검증) |
| E8 | Cursor changelog 신규 항목 | (신규 줄) | https://cursor.com/changelog | 신규 항목 | config 제품 출시 감시 (본문 파싱 미검증) |

- **«신규 항목» 유형**은 전날 베이스라인(`logs\event-watch\baseline.json`)과의 줄 차이로 잡는다 — 첫 실행은 베이스라인만 만들고 «신규 없음(베이스라인 생성)» 으로 적는다.
- 감시처가 막히면(403·타임아웃) 그 항목은 «확인 불가» 다. 미성립이 아니다(정관 §0).
