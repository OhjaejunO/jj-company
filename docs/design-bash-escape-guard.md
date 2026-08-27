# 셸 재해석 사고를 실행 시점에 막는 장치 — 설계안 (2026-08-27)

> **성격**: 조사·설계. **구현은 별건 JJ 승인** 후. 이 문서는 «무엇이 실제 실패 모드인가»와 «훅으로 막을 수 있는가·그 훅이 조용히 죽지 않는가»까지 확인한 결과다.

## 1. 왜 — 조항만 있고 실행 시점 검사가 없다

정관 §6 과 `docs/design-correction-routing.md` §2 의 **L-001**(«이스케이프 문자가 든 코드는 heredoc 으로 보내지 마라»)은 **문서에만 있다.** 세션이 그것을 읽고도 같은 함정에 반복해 걸린다.

| 날짜 | 무슨 일 | 대가 |
|---|---|---|
| 2026-08-23 | heredoc 안의 `I'm` 작은따옴표·em dash 가 셸과 cp949 콘솔을 깨뜨림 | 재시도 |
| 2026-08-25 | 파이썬 정규식 `\1` 이 `\x01` 로 풀림 | **재시도 2회 포함 3회 헛돎** — `cat -A` 로 바이트를 찍고서야 원인 확인 |
| **2026-08-27** | 파이썬 코드를 **큰따옴표 `-c "…"`** 로 넘겼는데 그 안의 백틱을 셸이 **명령으로 실행** | `gh auth login` 이 재실행돼 device 코드가 뜨고 2분 타임아웃(exit 143) · 메모리 갱신 실패 |

세 번 다 **조항을 쓴 쪽이 조항을 어겼다.** 규율로 안 되는 것을 규율로 두는 것이 정관 §0 4층이 금하는 자리(③으로 갈 것을 ④에 둠)다.

## 2. 실패 모드를 다시 정의한다 — «heredoc» 이 아니라 «셸이 한 번 더 해석하는 자리»

§6 은 heredoc 을 지목하지만 **8/27 사고는 heredoc 이 아니었다.** 정확한 축은 이것이다.

| 형태 | 셸이 내용을 다시 해석하나 | 판정 |
|---|---|---|
| `py - <<'EOF' … EOF` (**따옴표 delimiter**) | 아니오 | 🟢 안전 |
| `py - <<EOF … EOF` (따옴표 없음) | **예** — `$VAR`·`` `cmd` ``·`\` 전개 | 🔴 위험 |
| `py -c "…"` · `powershell -Command "…"` (**큰따옴표**) | **예** — `` `cmd` ``·`$VAR` 전개 | 🔴 위험 (8/27 사고) |
| `py -c '…'` (작은따옴표) | 아니오 | 🟢 안전 (단 내용에 `'` 를 못 넣는다) |
| Write/Edit 도구로 파일을 쓰고 `py file.py` | 셸을 안 거침 | 🟢 **권장 기본값** |

→ 조문도 이 축으로 고쳐야 한다(§6 문안 개정은 별건). 장치는 **위 🔴 두 줄만** 겨냥한다.

## 3. 장치안 — Claude Code `PreToolUse` 훅

**계약 (문서 확인)**
- `settings.json` 의 `hooks.PreToolUse[].matcher = "Bash"` 로 Bash 도구만 매칭한다.
- 훅 명령은 **stdin 으로 JSON** 을 받고, 명령 문자열은 **`tool_input.command`** 다.
- 차단은 둘 중 하나 — **exit code 2**(stderr 가 모델에게 피드백으로 감) 또는 exit 0 + JSON `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"…"}}`. **둘을 섞지 않는다.**
- Windows 에서는 exec form(`command` + `args`)으로 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <절대경로>` 를 부르는 것이 안전하다(shell form 은 PowerShell 이 한 번 더 해석한다 — 이 훅이 막으려는 것과 같은 함정).
- 경로는 `${CLAUDE_PROJECT_DIR}` 로 절대화. 훅 파일 수정은 **다음 turn 부터 반영**(세션 재시작 불필요).
- 우선순위: `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`. 이 가드는 **전 레포 공통 함정**이라 사용자 전역(`~/.claude/settings.json`)이 맞다.

**판정 규칙 초안** (거짓 차단을 줄이려 좁게 잡는다)
1. 명령에 `<<` 가 있고 delimiter 에 따옴표가 없다(`<<EOF`, `<<-EOF`) **그리고** 본문에 `` ` `` 또는 `\` 또는 `$(` 가 있다 → 차단.
2. `-c "` 또는 `-Command "` 로 시작하는 **큰따옴표 인자** 안에 `` ` `` 또는 `$(` 가 있다 → 차단.
3. 그 밖에는 통과. 특히 `<<'EOF'` · 작은따옴표 인자 · `grep '\d'` 같은 평범한 정규식은 **건드리지 않는다.**

거부 메시지에는 **대안을 같이 준다**(정관 §3 «거부 메시지에 대안을»): «Write/Edit 도구로 파일에 쓰고 그 파일을 실행하라 · 꼭 heredoc 이면 `<<'EOF'` 로 delimiter 를 따옴표로 감싸라».

## 4. 🔴 이 장치의 «조용한 실패» — 반드시 같이 만든다

문서 확인 결과 **훅이 없거나 실행에 실패하면 도구 호출은 그대로 통과한다**(non-blocking error). 스크립트를 지우거나 경로가 틀리면 **가드가 사라진 줄 모르고 계속 일한다** — 정관 §0 이 지목하는 바로 그 모양이고, `core.hooksPath` 가 없으면 pre-commit 훅이 조용히 사라지던 것과 같은 구조다.

그래서 구현할 때 **가드 자체 검사기**를 같이 만든다(`scripts/check-bash-guard.ps1`, `check-repo-guard.ps1` 형제):
- 설정에 훅이 있고 스크립트 파일이 실재하는가
- **역검증 양쪽** — 걸려야 하는 입력 2건(unquoted heredoc + 백틱 / `-c "…\`…"`)을 스크립트에 직접 먹여 **exit 2 가 나오는지**, 통과해야 하는 입력 2건(`<<'EOF'` · `grep '\d'`)이 **exit 0 인지**. 한쪽만 보면 «전부 차단하는 훅»도 정상으로 보인다.
- 세션 착수 절차(정관 §3 `check-repo-guard`)에 한 줄로 붙인다.

## 5. 한계 — 못 잡는 것 (적어 둔다)

- **PowerShell 도구·MCP 경로**는 이 훅이 안 본다(matcher 가 Bash 다). 같은 함정이 다른 도구에서 나면 그때 matcher 를 넓힌다.
- **문자열 안에 든 백틱이 정당한 경우**(예: 마크다운 코드펜스를 heredoc 으로 쓰는 것)도 차단된다 — 규칙 1 이 `<<'EOF'` 를 통과시키므로 **따옴표 delimiter 로 바꾸면 풀린다.** 거짓 차단의 탈출구가 조문 안에 있다.
- 훅은 **명령 문자열만** 본다. 파일에 쓰인 코드가 옳은지는 못 본다(그건 `py_compile`·게이트 몫).

## 6. 구현 범위 (승인 시)

1. `~/.claude/settings.json` 에 PreToolUse 훅 1건 + `.claude/hooks/bash-escape-guard.ps1`
2. `scripts/check-bash-guard.ps1` (역검증 4케이스 · STATUS 줄)
3. 정관 §6 문안을 «heredoc» → «셸이 한 번 더 해석하는 자리»로 개정 + 장치 참조 한 줄
4. `docs/design-correction-routing.md` L-001 에 «③ 검사로 이동(2026-08-27)» 표기

**구현은 이 문서 승인 후 별건 PR.**
