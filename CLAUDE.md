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

- 개발팀 에이전트는 글로벌 정의를 상속한다. 이 레포에 중복 정의하지 않는다.
- 부서별 상세 규약은 departments/<부서>/ 에 둔다. 에이전트는 자기 부서 규약을 먼저 읽고 시작한다.

## 2. 작업 디렉토리 (출장지)

| 대상 | 경로 | 권한 |
|---|---|---|
| 본사 | C:\Users\ojaej\jj-company | 읽기/쓰기 |
| 세컨드브레인 | C:\Obsidian.JJ\JJ-Brain | **읽기 전용** |
| 토망치랩 제작 | C:\토망치 | 읽기 전용 (제안만) |
| 토망치랩 전달함 | OneDrive\토망치_전달함 | 읽기 전용 |
| 블로그 | OhjaejunO.github.io 로컬 클론 | 읽기 전용 (초안은 reports/에) |

- 출장지 파일을 직접 수정하는 에이전트는 없다. 모든 산출물은 본사 reports/ 에 쓴다.
- vault 경로는 settings.json deny rules로 쓰기 차단되어 있다. 우회 금지.
  - **(Edit 규칙만 유효 — Write 규칙은 파일 권한 검사에 안 걸림)** 경로 차단은 반드시 `Edit(경로)` 로 적는다. `Write(경로)` 는 무시된다.
  - settings.json 은 BOM 없는 UTF-8 로 저장한다. BOM 이 있으면 파일 전체가 파싱 실패해 deny rule 이 전부 무력화된다. (`.claude/agents/*.md` 프론트매터도 동일)

## 3. Git 규칙

- main 직접 커밋 금지. OJJ 브랜치에서 작업 → PR → `--assignee OhjaejunO --merge --admin`
- 커밋 메시지: conventional prefix(영어) + 한국어 설명. 100바이트 이내.
- 스케줄 작업의 리포트 커밋 prefix: `report:`
- logs/ 는 커밋하지 않는다 (.gitignore).

## 4. 스케줄링 규약

- 헤드리스 실행: `claude -p "<프롬프트>"`. claude 바이너리는 전체 경로로 지정 (스케줄러는 PATH 최소 상태).
- CWD는 항상 `C:\Users\ojaej\jj-company`.
- stdout/stderr를 `logs\scheduled\<작업명>_<yyyyMMdd>.log` 로 리다이렉트.
- 리포트는 `reports\<yyyy-MM-dd>_<작업명>.md`.
- 실행 결과 마지막 줄에 `STATUS: OK` 또는 `STATUS: FAIL <사유>`.
- A/B등급만 스케줄 가능. C등급 스케줄 등록 금지.
- lock 파일 `logs\<작업명>.lock` 존재 시 즉시 종료.

### 등록된 스케줄 (현황판)

| 작업 | 에이전트 | 주기 | 상태 |
|---|---|---|---|
| morning-vault-health | ops-auditor | 평일 07:30 | 준비 중 |
| tomangchi-scout | content-scout | 미정 | 대기 |
| job-scout-daily | job-scout | 미정 | 대기 |

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
