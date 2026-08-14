# JJ Company OS — 회사 정관

> 이 레포는 JJ의 개인 자동화 본사다. 모든 스케줄 작업과 부서 에이전트는 이 디렉토리를 CWD로 실행된다.
> 이 파일은 500줄을 넘길 수 없다. 넘기면 분리하지 말고 줄여라.

## 0. 대원칙 (대표실)

- 방향/목표/전략/최종 결정은 JJ가 내린다. 에이전트는 위임받은 범위만 실행한다.
- 자동화 등급 3단계를 절대 넘지 않는다:
  - **A등급 (완전 자동)**: read-only 감사, 리포트 생성. 파일 수정 없음.
  - **B등급 (제안까지 자동)**: 콘텐츠 초안, 카드 제안, 커밋 준비. 산출물은 reports/ 로만. 발행/승격은 JJ 승인.
  - **C등급 (사람 필수)**: 발행, 머지, 배포, 외부 발송(DM/이메일), 결제. 에이전트 직접 실행 금지.
- 추측 금지. 로그/데이터 기반으로 진단한다. 확인 안 되면 "확인 불가"로 보고한다.

## 1. 조직도

| 부서 | 에이전트 | 등급 | 담당 |
|---|---|---|---|
| 운영팀 | ops-auditor | A | JJ-Brain vault 건강 감사, 백업 검증 |
| 마케팅팀 | content-scout | B | 토망치랩 소재 조사 → 카드 제안 |
| 영업팀 | job-scout | B | AX/AI 엔지니어 채용 공고 발굴 → 요약 |
| 개발팀 | implementer / verifier (글로벌 상속) | B | 구현/검증 분리, adversarial cross-validation |
| 감리 | 교차검증 codex | A | 타모델 감리. 리포트 vs 에이전트 정의 대조 — read-only, 본문 미수정 append 전용 |

- 개발팀 에이전트는 글로벌 정의를 상속한다. 이 레포에 중복 정의하지 않는다.
- 부서별 상세 규약은 departments/<부서>/ 에 둔다. 에이전트는 자기 부서 규약을 먼저 읽고 시작한다.

## 1.5 자회사

자회사는 본사와 정본이 분리된다. 본사 에이전트는 자회사 정본을 **읽되 수정하지 않는다.**

| 자회사 | 정본 | 본사 관할 | 상태 |
|---|---|---|---|
| 토망치랩 | `~\.claude\skills\tomangchi\SKILL.md` | §5.5 아침 스캔 **1~3-1단계**(수집·검증·판정·스캔로그·제안) | 가동 |

- **정본 수정 금지.** 충돌·모순을 발견하면 고치지 말고 리포트에 "확인 필요"로 보고한다.
- 컨펌·제작·발행은 본사 관할 밖 — 자회사 트랙에서 JJ가 진행한다.

## 2. 작업 디렉토리 (출장지)

| 대상 | 경로 | 권한 |
|---|---|---|
| 작업장 | C:\Users\ojaej\orca\jj-company | 읽기/쓰기. JJ가 개발하는 곳. OJJ 브랜치에서 작업 |
| 운영 서버 | C:\Users\ojaej\jj-company | 스케줄러 CWD. **main 전용 · 사람 직접 수정 금지** (git pull 로만 갱신) |
| 세컨드브레인 | C:\Obsidian.JJ\JJ-Brain | **읽기 전용** — 읽기는 해당 스케줄 스크립트의 `--add-dir` 로만 부여 (전역 허용 금지) |
| 토망치랩 작업 폴더 | C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop | 읽기 전용 — **단, `workshop\스캔로그\` 는 content-scout 쓰기 허용** (아래 예외 조항) |
| 블로그 | OhjaejunO.github.io 로컬 클론 | 읽기 전용 (초안은 reports/에) |

- 출장지 파일을 직접 수정하는 에이전트는 없다. 모든 산출물은 운영 서버 reports/ 에 쓴다.
- **출장지 쓰기 예외 1건 (content-scout 한정)**: `...\tomangchi-lab.github.io\workshop\스캔로그\` 에만 쓴다. 토망치랩 SKILL.md §5.5-3-1 아침 스캔 로그가 그 폴더 정본이라 우회 산출이 불가능하기 때문이다. 조건 — ① 해당 스케줄 스크립트의 `--add-dir` 로만 부여(전역 허용 금지) ② 기존 내용 수정·삭제 금지, 맨 아래 append 만 ③ 그 외 workshop 하위 폴더와 다른 출장지 쓰기는 계속 금지.
- **등급 경계 (content-scout)**: 토망치랩 SKILL.md §5.5의 1~3-1단계(수집·검증·판정·스캔로그·제안)까지만 자동화한다. 컨펌·캡처·카드 제작·발행은 사람이 한다. SKILL.md 는 에이전트가 수정하지 않는다 (개정은 토망치랩 트랙에서 JJ가 진행).
- 코드/정관 변경은 작업장에서만 한다. 운영 서버에서 직접 편집하면 다음 pull 에서 충돌로 스케줄이 멈춘다.
- vault 경로는 settings.json deny rules로 쓰기 차단되어 있다. 우회 금지.
  - **(Edit 규칙만 유효 — Write 규칙은 파일 권한 검사에 안 걸림)** 경로 차단은 반드시 `Edit(경로)` 로 적는다. `Write(경로)` 는 무시된다.
  - settings.json 은 BOM 없는 UTF-8 로 저장한다. BOM 이 있으면 파일 전체가 파싱 실패해 deny rule 이 전부 무력화된다. (`.claude/agents/*.md` 프론트매터도 동일)

## 3. Git 규칙

- main 직접 커밋 금지. OJJ 브랜치에서 작업 → PR → `--assignee OhjaejunO --merge --admin`
- 커밋 메시지: conventional prefix(영어) + 한국어 설명. 100바이트 이내.
- 리포트(reports/)는 로컬 전용 — 민감 정보 포함 가능성으로 커밋 금지 (.gitignore 유지).
- logs/ 는 커밋하지 않는다 (.gitignore).

## 4. 스케줄링 규약

- 헤드리스 실행: `claude -p "<프롬프트>"`. claude 바이너리는 전체 경로로 지정 (스케줄러는 PATH 최소 상태).
- CWD는 항상 `C:\Users\ojaej\jj-company`.
- stdout/stderr를 `logs\scheduled\<작업명>_<yyyyMMdd>.log` 로 리다이렉트.
- 리포트는 `reports\<yyyy-MM-dd>_<작업명>.md`.
- 실행 결과 마지막 줄에 `STATUS: OK` 또는 `STATUS: FAIL <사유>`.
  - **예외**: 교차검증(codex) 섹션은 `STATUS` 줄 **뒤에 append** 된다. STATUS 판정은 감리 섹션을 제외한 본문의 마지막 `^STATUS:` 줄을 기준으로 한다. (스케줄 스크립트의 판정 로직이 이미 파일의 마지막 `^STATUS:` 줄을 읽으므로 감리 섹션이 뒤에 붙어도 판정은 정상 동작한다 — 실증 완료)
- A/B등급만 스케줄 가능. C등급 스케줄 등록 금지.
- lock 파일 `logs\<작업명>.lock` 존재 시 즉시 종료.
- 모든 스케줄 작업은 실행 시작 시 **두 가지를 최신 main과 동기화**한 뒤 진행한다. 어느 쪽이든 실패하면 즉시 종료한다.
  1. **운영 서버** — `git pull origin main`. 실패 시 `STATUS: FAIL git-sync`.
  2. **스킬 라이브 정본** — `scripts\deploy-skill.ps1` (라이브 ← `origin/main`). 실패 시 `STATUS: FAIL skill-sync`.
  - `~\.claude\skills\tomangchi` 는 **레포로 향하는 링크가 아니라 `origin/main` 의 사본**이다 (2026-08-15 개편). 링크였을 때는 체크아웃된 브랜치가 곧 라이브 정본이라, 한 세션이 feature 브랜치에 두고 나오면 다른 세션·스케줄이 **미승인 규칙으로 조용히 돌았다.** 사본이므로 **아무도 밀어 넣지 않으면 갱신되지 않는다** — 그래서 동기화를 스케줄 선행 단계로 못박는다.
  - 실행에 쓰인 리비전은 `scripts\skill-version.ps1` 이 로그에 남긴다. 근거는 라이브의 `.deployed` 스탬프이며 소스 레포 HEAD가 아니다.

### 등록된 스케줄 (현황판)

| 작업 | 에이전트 | 주기 | 상태 |
|---|---|---|---|
| morning-vault-health | ops-auditor | 평일 07:30 | 가동 |
| tomangchi-scout | content-scout | 매일 08:00 | 가동 |
| job-scout | job-scout | 매일 08:30 | 가동 |

## 5. 리포트 형식

공통 헤더: 부서/작업명/날짜, 실행 시각·소요, 등급, 결론 요약 3줄 이내.
- 결론 먼저, 근거는 뒤에.
- B등급 제안은 "제안 → 근거 → JJ가 할 일" 3단 구성.
- 문제 심각도: 🔴 즉시 / 🟡 이번 주 / ⚪ 참고.

## 6. 금지 사항

- vault, C:\토망치, 블로그 레포 등 출장지 직접 수정
- 외부 발송 (이메일, DM, SNS 게시, 댓글)
- main 커밋, force push
- 시크릿/토큰을 리포트나 로그에 기록
- deny rules 우회 시도
- 확인되지 않은 정보를 사실처럼 보고
- **한글 포함 파일을 PS 5.1 리다이렉트(`>`, `>>`)로 생성·추가** — PS 5.1 기본 인코딩이 UTF-8이 아니라 파일이 깨진다. 한글 파일 쓰기는 **UTF-8(BOM 없음) 명시 필수**: `Set-Content -Encoding utf8` 또는 `[IO.File]::WriteAllText($p, $t, (New-Object Text.UTF8Encoding $false))`. Bash 툴 heredoc(`cat > f <<'EOF'`)과 Write/Edit 툴은 UTF-8 그대로 쓰므로 안전하다.
  - 인코딩 점검은 `iconv` 로 하지 마라 — 이 환경에 없어서 **전 파일이 "디코딩 실패"로 오탐**된다. `py -c "open(f,'rb').read().decode('utf-8')"` 로 확인한다.
  - **콘솔에 한글이 깨져 보이는 것과 파일이 깨진 것은 다르다.** 터미널 코드페이지 문제일 수 있으니 파일을 직접 열어 확인한 뒤 판단한다.
