# 워크숍 소스 레포 — 동기 절차 (인프라 백로그 21번 ㉮ · 정관 §2 예외 3번)

> **레포**: `OhjaejunO/tomangchi-workshop` (**PRIVATE**)
> **도구**: `scripts\workshop_repo_sync.py`
> **상태**: 초기 동기 완료 (2026-08-30 · 710개 · 58.19 MB)
>
> 🔴 **주소가 한 번 바뀌었다 (2026-08-30).** `PU3-Lab/tomangchi-workshop` 에서 위 주소로
> 이전했다 — `PU3-Lab` 은 팀 조직이라 회사 자산을 둘 자리가 아니다(백로그 22번).
> **리다이렉트에 기대지 않는다** — 옛 주소로도 `clone`·`push` 가 계속 통과해 틀린 주소가
> 아무 신호도 내지 않고, 누가 옛 이름을 다시 만들면 그날 끊긴다. 이 문서와
> `workshop_repo_sync.py` 의 `REMOTE` 를 포함해 **전부 새 주소로 갱신**했다.

## 왜 단방향이 «구조» 인가

훅으로 「워크숍으로 pull 하지 마라」를 막을 수도 있다. 그것은 **③층**이다.
여기서는 한 겹 아래에서 닫는다(정관 §0 4층 ①) —

```
워크숍 (읽기만)  ──복사──▶  스테이징 클론  ──push──▶  OhjaejunO/tomangchi-workshop
C:\...\workshop              C:\...\tomangchi-workshop
```

**워크숍에는 그 레포의 `.git` 이 없다.** 그러므로 `git pull`·`checkout`·`reset` 이
**워크숍에 닿을 경로 자체가 없다.** 실수로도, 급해서도 못 덮는다.

매 회차 그것을 말이 아니라 값으로 확인한다 —

| 확인 | 방법 | 실패 시 |
|---|---|---|
| 워크숍이 작업 트리가 아님 | 워크숍 하위에 `.git` 이 있는지 훑는다 | `STATUS: FAIL workshop-is-a-worktree` |
| 워크숍 불변 | 트리 지문(파일 수 + 경로·크기·mtime 해시) 전후 비교 | `STATUS: FAIL workshop-mutated` |

## 추적 대상

텍스트 소스(`.py`·`.md`·`.txt`·`.json`·`.html`) · 편별 선언(`build_epNN.py`·`_facts.py`) ·
`_official/` · `스캔로그/` · `발행로그.md`. **렌더 산출물은 안 담는다** — 코드가 다시 만든다.

🔴 **다시 못 만드는데 안 담긴 것이 1.74 GB 있다.** 아래 «미결» 참조.

## 집 컴퓨터 온보딩

```powershell
# ① 세 레포 + 워크숍 레포
git clone https://github.com/OhjaejunO/jj-company.git
git clone https://github.com/OhjaejunO/tomangchi-skill.git
git clone https://github.com/tomangchi-lab/tomangchi-lab.github.io.git
git clone https://github.com/OhjaejunO/tomangchi-workshop.git

# ② 워크숍 소스를 사이트 레포 안으로 편다 (workshop/ 은 사이트 레포에서 gitignore 다)
#    🔴 복사다. 사이트 레포 안에 워크숍 레포를 «클론» 하지 않는다 — 그러면 그 폴더가
#       작업 트리가 되어 단방향이 깨진다.
robocopy tomangchi-workshop tomangchi-lab.github.io\workshop /E /XD .git
```

그다음 `~\.claude\` (설정·훅·스킬)와 자격은 **레포 밖**이다 — `docs\onboarding-credentials.md`.

## 두 기계로 일할 때

**규칙 하나: 한 편은 한 기계에서.**

- 충돌 자리는 **편 폴더 단위**다(`02_제작중\epNN_*`). 한 편의 `build_epNN.py`·`_facts.py`·
  `검증로그.md`·`발행팩.md` 는 서로를 참조하며 같이 바뀌므로, **두 기계가 같은 편을 만지면
  줄 단위 병합으로는 못 푼다** — 게이트가 통과하는 상태가 파일마다 달라진다.
- **공용 파일**(`00_브랜드에셋\*.py`)은 그보다 낫지만 역시 한 기계에서 고친다.
  고친 뒤 **바로 push** 하고, 다른 기계는 **작업 시작 전에 pull** 한다.
- 🔴 **`git pull` 은 스테이징 클론에서 한다. 워크숍에서 하지 않는다** — 애초에 못 한다
  (위 «구조» 참조). 집에서 받은 것을 이 기계에 반영하려면
  `git -C tomangchi-workshop pull` 뒤 **robocopy 로 워크숍에 편다.**
- **claim 을 쓴다.** `scripts\claim.ps1 -Topic ep<N>` 이 같은 주제 중복을 거부한다.
  다만 그것은 **한 기계 안에서만** 유효하다 — 두 기계 사이는 이 규칙(한 편은 한 기계)이
  진다. 🔴 **기계 간 잠금 장치는 없다. 못 잡는다고 여기 적는다**(정관 §0 4층 ④).

## 병행 — zip 백업은 끄지 않는다

`workshop_backup.py`(㉰)는 그대로 돈다. 둘은 **같은 사고로 같이 죽지 않는다** — 하나는
원격 레포, 하나는 드라이브다. 레포는 이력이 있고 zip 은 레포 밖에 있다.

초기 동기 검증에서 **셋이 같은 것을 담고 있음**을 해시로 확인했다 —
레포 710개 ↔ zip 710개 ↔ 워크숍 원본, **불일치 0**.

## ✅ 렌더물 판정 (2026-08-30 JJ) — 미결 닫힘

**레포는 그대로 텍스트+`_official` 만 담는다**(58 MB). 나머지는 **zip 백업이 진다** —
`_scenes/`·`_assets/`·`assets/`·브랜드 이미지 + **발행 채택본 10개**.
zip 첫 회차 실측: **1,265개 · 966.34 MB · 24.6초**, 전 멤버 해시 일치.

**옛 편 시안·아카이브 506개 823.9 MB 는 «백업 제외 · 소실 감수»** 다 — 삭제하지 않고
워크숍에 그대로 둔다. 🔴 선행 실측에서 그 더미에 **발행 채택본이 섞여 있는 것**을 잡아
따로 건져 냈다(ep1 릴스·힉스필드 릴스·채널 광고·릴스 표지 프레임).

~~## 🔴 미결 — 담지 않은 «다시 못 만드는» 렌더물 1.74 GB~~ (아래는 판정 전 기록)

| 갈래 | 개수 | 크기 | 왜 못 만드나 |
|---|---|---|---|
| 옛 편 표지 시안·릴스 | 560 | 964.8 MB | 옛 편의 생성 이미지·영상. `_scenes/` 관행 이전 판 |
| `_scenes/` | 209 | 661.4 MB | **모델이 만든다** — 같은 프롬프트로도 같은 그림이 안 나온다 |
| `_assets/` | 250 | 61.9 MB | JJ 제공·외부 수집 |
| `00_브랜드에셋` 이미지 | 37 | 53.1 MB | 로고·엔드카드 원본 |

**지금은 zip 백업에도 없다** — `workshop_backup.py` 도 텍스트와 `_official/` 만 담는다.
즉 **이 1.74 GB 는 어디에도 백업이 없다.**

- **왜 안 담았나**: 담으면 레포가 **1.8 GB** 가 된다. GitHub 는 개별 파일 100 MB 를 막고
  레포 1 GB 부터 경고한다 — Git LFS 없이는 실용적이지 않다.
- **후보**: ⓐ Git LFS 로 `_scenes/` 만 ⓑ 별도 레포 ⓒ zip 백업 범위를 넓혀 드라이브로만
  ⓓ 그대로 둔다(옛 편 시안은 잃어도 된다고 판정).
- 🔴 **JJ 판정 대기.** 이 문서가 그 목록이고, `--report-exceptions` 가 매번 다시 센다.
