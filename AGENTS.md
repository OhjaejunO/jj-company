# JJ Company OS — 코덱스용 진입점

정본은 `CLAUDE.md` 하나다. **작업 전에 `CLAUDE.md` 전문을 읽고 그대로 따른다.** 이 파일에 규칙을 적지 않는다 — 정본이 둘이면 갈린다.

코덱스에서 다른 것만 적는다 (2026-09-08 실측).

- **쓰기 차단**은 `settings.json` deny 규칙이 아니라 sandbox 다. `workspace-write` 에서 CWD 밖은 기본 차단이고, §2 출장지 예외는 `--add-dir` 로만 연다(전역 허용 금지). 예외를 열면 §4 프로브처럼 **밖은 거부·안은 성공** 양방향을 그 회차에 실증한다.
- **훅은 하나만 있다 (2026-09-08 이식).** `.codex/hooks.json` 의 PreToolUse 가 `.codex/hooks/pretooluse.ps1` 을 거쳐 셸 재해석 가드(`.claude/hooks/bash-escape-guard.ps1`)를 부른다 — 코덱스는 세션 cwd 에서 돌리므로 상대 경로다. 켜지려면 `.codex/config.toml` 의 `[features] hooks = true`(`codex_hooks` 는 deprecated), **이 프로젝트의 trust**, 그리고 **훅 자체의 trust**(`/hooks` 에서 승인 · 해시가 바뀌면 재승인)가 필요하다. 래퍼는 호출마다 `logs\hooks\codex-pretooluse.jsonl` 에 한 줄(tool_name·command·verdict·exit)을 남긴다 — «Hook failed» 가 뜨면 그 줄이 진단이다(2026-09-08 exit 1 사고 뒤 신설). 🔴 **차단은 exit 2 가 아니라 stdout JSON `permissionDecision: deny` + exit 0 이다** — 코덱스 소스(`hooks/src/events/pre_tool_use.rs`)가 exit 2 는 stderr 가 비면 무시하고 stdout 을 안 보는데, 2026-09-09 00:21 실측에서 exit 2 가 로그엔 block 으로 남고도 명령이 실행됐다(stderr 가 빈 채 도착 · 원인은 확인 불가 — 중첩 PowerShell 추정). 🟢 **Stop 게이트는 2026-09-13 에 섰다.** 종전 문안은 «이식하지 않았다 — 클로드 트랜스크립트를 읽는 스크립트라서» 였는데, 실측해 보니 **막은 것은 문이 아니라 입력 방식**이었다: 코덱스에도 `Stop`·`SessionStart` 이벤트가 있다(Orca 런타임 `hooks.json` 실값). 그래서 편을 고르는 축만 바꿨다 — `SessionStart` 가 스탬프를 찍고(`.codex\hooks\sessionstart.ps1`), `Stop` 이 **그 이후 바뀐 `workshop\02_제작중\<편>`** 의 `verify.py` 를 돌린다(`.codex\hooks\stop.ps1` → `.claude\hooks\gate_on_stop.py --codex`). 게이트 본체는 클로드판과 **한 파일**이다. 🔴 **차단은 stdout JSON 이고 exit 가 아니다**(PreToolUse 와 같은 자리). 🔴 **Stop 페이로드·응답 꼴은 문서가 없어, 차단이 실제로 세션을 멈추는지는 첫 실세션까지 확인 불가**다 — 그때까지 보장되는 것은 `logs\hooks\codex-stop-gate.jsonl` 에 리포트와 `payload_keys` 가 남는 것까지다. `context_watch` 는 여전히 미이식(트랜스크립트 꼴 의존 · ④).
- **`.codex/agents/*.toml` 의 도구 제한은 문구다.** 마이그레이터가 `tools:` 를 `developer_instructions` 산문으로만 옮겼다(코덱스 커스텀 에이전트에 도구 경계가 없다). ops-auditor 의 «Bash 없음» 이 코덱스에서는 지켜지지 않는다 — ④ 못잡음.
- **부서 정의·스킬·메모리가 «자동으로» 오지 않는다 — 읽을 수 없는 것과 다르다 (2026-09-13 정밀화).** `.claude/agents/*.md`·클로드 메모리는 코덱스 밖이고 대체물도 없다. 그런데 **스킬은 파일이라 읽힌다**: sandbox 가 드라이브 루트를 `read` 로 주고, 편 `verify.py`·빌더는 `~\.claude\skills\tomangchi` 를 `sys.path` 에 스스로 꽂는다(`EPCHECK_DIR` 로 덮을 수 있다). 즉 **검사기·게이트는 클라이언트를 안 가리고**, 코덱스에 없는 것은 «SKILL.md 자동 주입» 하나다 — 그래서 아래 «편 제작 회차» 절이 그것을 손으로 연다. 원장·백로그·발행로그는 종전대로 파일 공유 상태다.

## 편 제작 회차 (2026-09-13 신설)

토망치랩 편 제작을 코덱스로 돌릴 때만 읽는다. 그 외 회차는 위 항목으로 족하다.

1. **정본 둘을 먼저 읽는다** — `CLAUDE.md`, 그리고 자회사 정본 `~\.claude\skills\tomangchi\SKILL.md`. 후자는 클로드에서는 스킬로 자동 주입되지만 **코덱스에는 아무도 넣어 주지 않는다.** 안 읽고 만든 덱은 규격이 아니라 취향이 된다. 🔴 **SKILL.md 는 자회사 정본이라 수정하지 않는다**(§1.5) — 모순을 찾으면 고치지 말고 «확인 필요» 로 보고한다.
2. **워크숍을 `--add-dir` 로 연다** — `codex --add-dir C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop`. 편 폴더는 jj-company 밖이라 부여 없이는 sandbox 가 첫 쓰기에서 거부한다. 🔴 **승인 창으로 뚫지 않는다**(승인은 접두사로 저장돼 다음에 안 묻는다). 열리는 범위는 §2 예외 4번 그대로 — **JJ 가 제작을 지시한 편**의 `02_제작중\<편>` 아래뿐이고, `01_발행완료`·`03_소재큐` 는 아니다.
3. **게이트는 자동이지만 보고는 자동이 아니다** — Stop 훅이 바뀐 편의 `verify.py` 를 돌린다. 그래도 **`STATUS` 줄과 역검증 출력을 회차 보고에 그대로 붙인다**(위 «작성자 ≠ 감리자» 조항: 검증 결과를 붙이는 것까지가 작성자 몫이다). 🔴 **게이트를 통과시키려고 빈 빌더를 만들지 않는다** — 통과는 목적이 아니라 결과다.
4. **발행은 하지 않는다** — 인스타 게시·고정 댓글·DM 은 C등급 그대로다(§6). 드라이브 전달·킷 배포까지가 제작 회차의 끝이다.
- **작성자 ≠ 감리자.** 코덱스가 쓴 산출물의 감리는 클로드가 한다(§1 «타모델 감리»). 자기 승인은 승인이 아니다.
  - 🔴 **감리자는 JJ 가 띄운 세션이다. 작성자는 감리 프롬프트를 쓰지도, 감리자를 부르지도 않는다.** 작성자가 결론과 정당화를 넣어 부른 감리는 그 결론을 승인해 줄 뿐이다(근거: 2026-09-08 PR #209 — 코덱스가 Sonnet 을 `claude -p` 로 직접 불러 «REVIEW: PASS» 를 받았고, 그 프롬프트에 자기 변경의 근거가 들어 있었다). 검증 실행 결과(`STATUS` 줄·역검증 출력)를 PR 본문에 붙이는 것까지가 작성자 몫이다.
  - **2026-09-11 부터 이것은 문장이 아니라 장치다** (C-44 4단계). `scripts\cross-verify.ps1` 이 `-Author`·`-Auditor` 를 받고 **둘이 같으면 실행을 거부**한다 — 작성자를 못 알아내도 거부다(조용한 통과 없음). 코덱스가 쓴 것을 감리하려면 `-Auditor claude -Author codex -Rules CLAUDE.md`, 스케줄 리포트는 종전대로 이름에서 작성자가 풀려 `-Auditor codex` 가 기본이다. 역검증은 `-SelfTest`.
- **쓰기 경계는 sandbox 다 (2026-09-09 양방향 실증).** 작업 폴더는 `write`, 그 밖은 `read` 이고 목록 밖 쓰기는 **첫 시도에 거부**된다. 뚫는 길은 둘뿐 — `--add-dir <경로>` 로 띄우거나(정책에 `write` 항목으로 들어간다 · §2 «부여 경로» 그 자리다), 사람이 그 자리에서 승인하거나. 🔴 **승인은 «명령 접두사»로 저장돼 다음에 안 묻는다** — 저장처는 확인 불가다. 그러니 **승인으로 뚫지 말고 `--add-dir` 로 부여한다.** 작업 폴더 안이어도 `.git`·`.agents`·`.codex` 는 `read` 로 내려간다.
- git 훅(`core.hooksPath`)·`claim.ps1`·`check-repo-guard.ps1` 은 클라이언트를 안 가린다 — 그대로 든다.
