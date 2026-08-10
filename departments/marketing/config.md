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
