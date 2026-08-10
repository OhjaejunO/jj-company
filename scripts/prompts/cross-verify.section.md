
---

## 교차검증 (codex)

**감리 시각**: {{TIME}} | **감리자**: codex ({{MODEL}}) | **등급**: A (read-only 감리 — 본문 미수정, append 전용)
**규칙 파일**: `{{RULES}}`

{{BODY}}
<!--SPLIT-->
---

## 교차검증 (codex)

**감리 시각**: {{TIME}} | **등급**: A

**교차검증 미수행** — {{BODY}}

감리는 부가 기능이므로 이 리포트 본체의 판정에는 영향을 주지 않는다. 필요하면 아래로 수동 재실행:

```
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\ojaej\jj-company\scripts\cross-verify.ps1 -Report "{{REPORT}}"
```
