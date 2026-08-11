# 마케팅팀 설정

content-ops 로컬 클론 경로: C:\Users\ojaej\orca\content-ops
미설정 시 중복 확인 스킵, "중복 미확인" 표기.

## 중복 확인 방법 (읽기 전용)

Django 프로젝트. 발행 이력은 `db.sqlite3` 에 있다. 조회만 하고 쓰지 않는다.

```
cd C:\Users\ojaej\orca\content-ops
PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe -c "import sqlite3;c=sqlite3.connect('db.sqlite3');[print(r) for r in c.execute('select number,title,category,status,published_at from episodes_episode order by number')]"
```

- `episodes_episode` — 발행/취소된 에피소드 (number, title, category, status, published_at)
- `episodes_topic` — 토픽명 (중복 판정의 1차 기준)
- `episodes_source` — 에피소드별 출처 URL
- `status='canceled'` 는 발행되지 않은 것이므로 중복으로 보지 않되, 재제안 시 취소 사유를 확인한다

소스 화이트리스트(X 계정): (추가 예정)

## 벤치마크 채널 (반응 신호 관찰용 — 내용 재사용 금지)

| 채널 | 규모(팔로워/게시물) | 성격 |
|---|---|---|
| @ai.trend.kr | 19.8만 / 702 | 뉴스·큐레이션 물량형. **소재 겹침 최다 예상** |
| @prompt_what | 17.6만 / 257 | 레시피 특화 (Kling·Higgsfield·invideo). **유형A 직접 경쟁** |
| @ai_freaks.kr | 11.5만 / 228 | 뉴스+꿀팁, 쿠폰 퍼널 |
| @trenddalkak.ai | 5.6만 / 100 | 디자인·비주얼 특화. 포스트당 효율 벤치마크 |

**관찰 항목**: 고반응 소재 유형 / 헤드라인 문법 / 발행 빈도 / (수치 확인 가능 시) 반응 지표

**금지**: 이 채널들의 카드 내용·문구·구성 재사용. 소재가 겹치면 **1차 소스로 거슬러 올라가 독립 검증** 후 우리 방식으로 제작한다. 벤치마크 채널을 출처로 표기하지 않는다 — 그들도 인용자이지 1차 소스가 아니다.

**겹침 표기**: 벤치마크가 이미 다룬 소재는 **"시장 검증됨 + 차별화 필요"** 플래그를 단다.
