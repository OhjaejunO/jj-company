#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스킬 사본 드리프트 감사 (A등급 · read-only)

토망치랩 브랜드 스크립트는 **두 곳에 있다.**

    스킬 레포   tomangchi-skill `origin/main:skills/tomangchi` → 라이브 스킬로 배포된다
    워크숍 폴더  tomangchi-lab.github.io/workshop/00_브랜드에셋  (gitignore)

드리프트는 조용히 쌓인다 — 정관 §0 «조용히 실패하는 코드»와 같은 계열이다.
실제로 `brand.py` 가 한쪽에 통째로 없었는데 몇 주간 아무 신호가 없었다(2026-08-15).

막을 수 없다면 **소리를 내게** 한다. 이 감사가 그 소리다.

## 🔴 방향이 뒤집혔다 — 이 파일의 이름은 옛 사실이다 (2026-09-12)

이 감사는 2026-08-15 에 «워크숍 폴더가 실행 정본이고 스킬 레포가 그 사본» 이라는
전제로 쓰였다. **그 전제는 그 뒤 뒤집혔고, 이름만 안 따라갔다.** 실물 근거 둘:

  1. `build_ep57.py` 의 `sys.path` 마지막 순서가 «편 폴더 → **라이브 스킬** →
     `02_제작중` → `00_브랜드에셋`» 이다. 주석도 「🔴 라이브 스킬이 먼저다 —
     워크숍 `00_브랜드에셋` 사본이 낡았다(ep56 실측)」 이라고 적혀 있다.
  2. 자회사 PR #119(v3.85) 제목이 「fix(gate): 워크숍 사본이 라이브 스킬을
     가리지 않게」 다. **자회사는 뒤집힘을 인정하고 고쳤는데 본사 감사만 안 따라갔다.**

그래서 «워크숍이 뒤처짐» 은 **정상**이고(제작은 라이브 스킬을 먼저 읽는다),
«워크숍이 앞섬» 이 **결함**이다(스킬 레포로 승계되지 않은 수정이 거기 갇혀 있다).
등급을 그 방향으로 가른다 — 종전에는 둘 다 🔴 라서, **정상 상태가 나흘 연속 🔴 4건**
으로 떠 있었고 그 빨간 줄이 진짜 🔴 를 묻었다(2026-09-12 실측).

🔴 **코드 안의 `LIVE`·`COPY` 는 옛 이름 그대로 남겨 뒀다** — 560줄을 개명하는 것이
이 회차의 위험을 늘린다. `LIVE` = 워크숍 폴더, `COPY` = 스킬 레포(`origin/main`)다.

## 비교 대상은 «클론의 워킹 트리»가 아니라 `origin/main` 이다 (2026-08-15 개정)

종전에는 `tomangchi-skill` 클론의 워킹 트리를 읽었다. 그런데 **배포되는 것은
`origin/main`** 이고(§4 «라이브 ← origin/main», `deploy-skill.ps1`), 워킹 트리는
누가 언제 당겼는지에 따라 달라지는 **공유 가변 자원**이다. 실제로 그날 사고가 났다 —
PR 이 머지된 직후 클론이 아직 뒤처져 있었을 뿐인데 감사는 `🔴 내용이 다르다:
cardcheck.py` 를 냈다. **경보는 떴는데 원인이 틀렸다.** 읽는 사람은 «사본이 갈라졌다»로
읽고 엉뚱한 곳을 고치러 간다. 있으나 마나가 아니라 **잘못된 방향을 가리키는** 감사는
없는 것보다 나쁘다.

그래서 `origin/main` 을 임시 폴더로 꺼내 그것과 비교하고, 그 폴더의 자립 검증을 돌린다.
**클론 상태(브랜치·뒤처짐·더러움)는 없애지 않고 🟡 로 따로 보고한다** — 정보를 버리는
게 아니라 «드리프트»와 «클론이 뒤처짐»을 **다른 이름으로** 부르는 것이 요점이다.

덤으로 CRLF 잡음도 대부분 사라진다. git 블롭은 LF 로 저장되고 실행 정본도 LF 라
바이트가 그대로 맞는다(워킹 트리는 체크아웃 때 CRLF 가 된다). 다만 **실행 정본은
gitignore 라 git 이 손댈 수 없으므로** 개행 정규화는 그대로 둔다 — 실제로 실행 정본의
`webshot.py` 한 개가 CRLF 다. `.gitattributes` 로는 이 쪽을 고칠 수 없다.

## 무엇을 보나

  1. 사본에 없는 파일        — 특히 코드(.py)와 코드가 실행 중에 여는 자산
  2. 사본에만 있는 파일
  3. 양쪽에 다 있는데 다른 파일 — 내용 비교(개행만 다르면 ⚪ 로 내린다)
  4. 사본이 실제로 도는가     — 사본의 `_selftest.py` 를 돌린다
  5. 클론 상태               — main 인가, origin/main 을 따라잡았는가, 깨끗한가
  6. **배포가 실물인가**      — 라이브 스킬이 **자기 `.deployed` 스탬프가 가리키는
     리비전**과 바이트가 같은가 (2026-09-12 신설)

6번을 새로 넣은 이유: 제작이 **라이브 스킬을 먼저 읽는데** 그 폴더의 실물을 재는 자가
어디에도 없었다. `skill-version.ps1` 은 `.deployed` 스탬프를 읽는데 그것은 **배포기가
스스로 적은 주장**이지 대조가 아니다 — 배포가 반쯤 되거나 레포에서 지운 옛 모듈이
라이브에 남으면 스탬프는 그대로 «최신»이라고 말하고, 제작은 그 남은 파일을 import
한다(정관 §0 «감지 장치가 값을 담는지 검증한다»).

🔴 **대조 상대는 `origin/main` 이 아니라 «스탬프가 가리키는 리비전»이다.** 배포는
스케줄 회차 시작 때 일어나므로 **머지 직후 라이브가 뒤처져 있는 것은 정상**이고, 거기에
🔴 를 달면 지금 이 파일이 고치고 있는 결함(거짓 경보가 진짜 경보를 묻는다)을 새로
만드는 꼴이다. 스탬프와 `origin/main` 의 차이는 ⚪ 참고로만 적는다.

**두 정본 폴더 어디에도 쓰지 않는다.** 쓰는 곳은 임시 폴더와 운영 서버 reports/ 뿐이다.

## 역검증 (§0)

`self_test()` 가 합성 폴더 쌍으로 판정기 자신을 시험하고, `main()` 이 시작할 때 돈다.
**사유 코드까지 대조한다** — 통과/실패만 보면 엉뚱한 사유로 걸려도 «잡았다»로 읽힌다.
특히 `one_char` 케이스는 개행 정규화가 **진짜 차이를 삼키지 않는지**를 본다. 정규화를
넣은 검사는 이 케이스가 없으면 «전부 통과»와 «전부 눈감음»이 구분되지 않는다.

## 정지 조건 — 퓨즈 (2026-08-31 신설 · C-40)

**ⓐ 스스로 멈춘다**

1. **두 폴더 중 하나라도 못 읽으면 `STATUS: FAIL`** 이다. 한쪽만 보고 «드리프트 없음» 을
   내는 것이 이 감사에서 가장 나쁜 실패다 — 비교 대상이 없으면 판정도 없다.
2. **`origin/main` 을 못 당기면 그 회차는 중단한다.** 낡은 사본과 비교하면 «어긋났다» 도
   «같다» 도 근거가 없다(2026-08-30 실측: 스크래치 클론 작업 트리와 비교해 **7종 어긋남**
   으로 오판했는데 실제로는 전부 CRLF 차이였다).
3. **줄 끝(CRLF/LF) 차이는 드리프트가 아니다.** 정규화 후 비교한다 — 이것도 «멈추지 않는»
   조건이라 같이 적는다.

**ⓑ JJ 가 끈다**

1. **드리프트가 0 이 아닌 상태로 2주가 지나면** 끈다 — 감사가 값을 내는데 아무도 안 고치면
   그 감사는 소음이다.
2. **브랜드 정본 단일화(`docs\\plan-brand-assets-move.md`)가 끝나면 이 워커를 폐기한다.**
   🔴 이것은 «끄는 조건» 이 아니라 **«없어지는 조건»** 이다 — 비교 대상이 사라진다.
   감사가 필요 없어지는 것이 그 이전 작업의 목적이다.
"""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

#: 경로는 환경변수로 덮을 수 있다.
LIVE = os.environ.get(
    "TOMANGCHI_LIVE",
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop\00_브랜드에셋")
COPY_REPO = os.environ.get("TOMANGCHI_COPY_REPO",
                           r"C:\Users\ojaej\orca\tomangchi-skill")
COPY_SUB = os.environ.get("TOMANGCHI_COPY_SUB", "skills/tomangchi")
COPY_REV = os.environ.get("TOMANGCHI_COPY_REV", "origin/main")
#: 주면 export 대신 **이 폴더**를 사본으로 본다. 역검증·디버깅용 탈출구다.
COPY_DIR = os.environ.get("TOMANGCHI_COPY")
#: 배포본. **제작이 실제로 import 하는 것**이라 `origin/main` 과 같아야 한다 (§4).
LIVE_SKILL = os.environ.get(
    "TOMANGCHI_LIVE_SKILL",
    os.path.expanduser(os.path.join("~", ".claude", "skills", "tomangchi")))
#: 배포기가 적는 스탬프. 레포에 없는 것이 정상이라 대조에서 뺀다.
DEPLOY_IGNORE = {".deployed"}
REPORTS = os.environ.get("JJ_REPORTS", r"C:\Users\ojaej\jj-company\reports")

#: 사본에 **일부러 넣지 않은** 것. 런타임에 열리지 않는 원본·참고 자산이라 약 9MB 를
#: 레포에 넣지 않기로 했다(2026-08-15). 목록에 있으면 ⚪ 참고로만 보고한다.
#: 새 파일이 생기면 이 목록 밖이라 🟡 로 떠서 사람이 판단하게 된다 — 그게 목적이다.
EXCLUDED = {
    "avatar_1024.png", "post_sample_8.png", "endcard_v2.png", "_endcard_prev.png",
    "토망치 커버1.png", "토망치 커버2.png", "토망치 커버3.png", "토망치 프로필.png",
}
#: 사본에만 있어야 정상인 것 — **스킬로 배포되지만 제작 폴더에서는 쓰지 않는 파일.**
#:
#: 2026-08-21 추가: `epcheck.py`(편 게이트 검사기 정본)·`verify.template.py`(편 껍데기
#: 템플릿). 둘은 `00_브랜드에셋` 에 있을 이유가 없다 — 편은 스킬 경로에서 부른다.
#: 목록에 없으면 **매일 🟡 2건이 상주**하고, 늘 노란 줄이 있는 리포트는 사람이 안 보게 된다
#: (§0 — 거짓 경보가 감시를 무디게 한다). 근거: 브랜드 동기화(PR #51) 뒤 남은 유일한 🟡.
#: 2026-09-12 추가: `surface_check.py`(지면 금지 목록 공용 정본). `epcheck` 가 import
#: 하는 검사기라 `epcheck.py` 와 같은 자리이고, 없으면 **매일 🟡 1건이 상주**한다.
COPY_ONLY = {"SKILL.md", "_selftest.py", "epcheck.py", "verify.template.py",
             "surface_check.py"}

#: 개행 정규화를 적용할 확장자. **바이너리에는 쓰지 않는다** — PNG 안의 `\r\n`
#: 바이트를 지우면 진짜 차이를 가려 버린다.
TEXT_EXT = (".py", ".md", ".txt", ".json", ".ps1", ".yml", ".yaml")

#: 사유 코드 → 심각도. 리포트 색은 여기 한 곳에서만 정한다.
#:
#: «내용이 다르다» 는 **방향에 따라 등급이 갈린다** (2026-09-12) — 헤더 «방향이
#: 뒤집혔다» 절 그대로다. 워크숍이 앞선 것만 결함이고, 스킬 레포가 앞선 것은 정상이다.
SEVERITY = {
    "missing-code": "red",
    "content": "red",               # 방향 불명 — 모르는 채로 덮는 것이 사고라 🔴 로 둔다
    "content-unmerged": "red",      # 워크숍이 앞섬 — 스킬 레포로 승계되지 않은 수정
    "content-stale": "yellow",      # 스킬 레포가 앞섬 — 워크숍 사본이 뒤처진 것뿐(정상)
    "deploy": "red",                # 라이브 실물이 자기 스탬프와 어긋난다
    "deploy-behind": "white",       # 머지 뒤 아직 배포 전 — 다음 회차가 따라잡는다
    "selftest": "red",
    "missing-asset": "yellow",
    "copy-only": "yellow",
    "clone": "yellow",
    "newline": "white",
    "excluded": "white",
}


def sha(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def listing(d):
    return {f: os.path.join(d, f) for f in sorted(os.listdir(d))
            if os.path.isfile(os.path.join(d, f))}


def git(repo, *args, check=True):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           f"{p.stderr.decode('utf-8', 'replace').strip()}")
    return p


def export_rev(repo, rev, sub, dest):
    """`rev:sub` 트리를 `dest` 로 꺼낸다. 레포 워킹 트리·HEAD 는 건드리지 않는다.

    `core.autocrlf=false core.eol=lf` 를 꽂는 이유: `git archive` 는 **체크아웃과
    같은 개행 변환을 적용한다.** 안 끄면 이 머신 설정대로 CRLF 로 나와, git 이 LF 로
    보관한 것을 굳이 CRLF 로 바꿔 놓고 «개행만 다름» 13줄을 리포트에 깔게 된다.
    블롭 그대로 꺼내면 실행 정본(LF)과 바이트가 맞는다.

    이건 **잡음 제거일 뿐 판정을 바꾸지 않는다** — 개행 차이는 어차피 ⚪ 다.
    """
    data = git(repo, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
               "archive", "--format=tar", f"{rev}:{sub}").stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        try:
            t.extractall(dest, filter="data")     # py3.12+
        except TypeError:
            t.extractall(dest)
    return dest


def clone_state(repo, rev):
    """클론이 «지금 무엇을 들고 있나». 드리프트와 **다른 이름으로** 보고할 것."""
    out = []
    try:
        branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.decode().strip()
        if branch != "main":
            out.append(("clone", f"클론이 main 이 아니다 (현재 {branch})"))
        behind = git(repo, "rev-list", "--count", f"HEAD..{rev}").stdout.decode().strip()
        if behind not in ("0", ""):
            out.append(("clone", f"클론이 {rev} 보다 {behind}커밋 뒤처졌다 "
                                 f"— `git -C {repo} pull --ff-only` (드리프트가 아니다)"))
        dirty = git(repo, "status", "--porcelain").stdout.decode("utf-8", "replace").strip()
        if dirty:
            n = len(dirty.splitlines())
            out.append(("clone", f"클론 워킹 트리가 깨끗하지 않다 ({n}건) "
                                 f"— 커밋되지 않은 변경은 배포되지 않는다"))
    except Exception as e:
        out.append(("clone", f"클론 상태 확인 불가: {type(e).__name__}: {e}"))
    return out


#: 두 시각이 이만큼 이상 벌어져야 «어느 쪽이 최근»이라고 말한다. 그 안이면 «불명»이다.
#: 파일 복사·체크아웃이 mtime 을 건드리므로 근소한 차이는 근거가 못 된다.
NEWER_MARGIN_S = 300


def _newer(live_path, name, copy_age):
    """(판정, 표기) — 판정은 "live" / "copy" / None(불명).

    실행 정본 쪽 근거는 **파일 mtime**, 사본 쪽 근거는 **그 경로를 마지막으로 건드린 커밋
    시각**이다. 둘은 성질이 다르다 — mtime 은 복사·체크아웃으로 갱신되고 커밋 시각은 안
    그렇다. 그래서 이 함수는 **단정하지 않는다.** 근거를 나란히 적고, 차이가 여유(5분)를
    넘을 때만 방향을 말한다. 사람이 그 두 값을 보고 뒤집을 수 있어야 한다.
    """
    import datetime as _dt
    try:
        lm = os.path.getmtime(live_path)
    except OSError:
        return None, "정본 mtime 확인 불가"
    ls = _dt.datetime.fromtimestamp(lm).strftime("%Y-%m-%d %H:%M")
    if copy_age is None:
        return None, f"정본 mtime {ls} / 사본 시각 확인 안 함"
    cm, cs = copy_age(name)
    if cm is None:
        return None, f"정본 mtime {ls} / 사본 커밋 시각 확인 불가 ({cs})"
    if abs(lm - cm) < NEWER_MARGIN_S:
        return None, f"정본 mtime {ls} · 사본 커밋 {cs} — 차이 5분 미만이라 **방향 불명**"
    if lm > cm:
        return "live", (f"워크숍 mtime {ls} · 스킬 레포 커밋 {cs} — "
                        "🔴 **워크숍이 앞선다** (스킬 레포로 승계되지 않은 수정이다)")
    return "copy", (f"워크숍 mtime {ls} · 스킬 레포 커밋 {cs} — "
                    "**스킬 레포가 최근** (정상 — 제작은 라이브 스킬을 먼저 읽는다)")


def classify(live_dir, copy_dir, copy_age=None, newer_out=None):
    """두 폴더를 비교해 `[(사유코드, 설명), ...]` 로 돌려준다. 비어 있으면 일치다.

    `copy_age(name) -> (epoch, 표기)` 를 주면 «내용이 다르다» 줄에 **어느 쪽이 최근인지**를
    같이 적는다. 2026-08-21 신설 — 그 전에는 이 감사가 «다르다»만 말하고 방향을 몰랐고,
    그런데도 조치 문구는 늘 «실행 정본에서 복사해 커밋»이었다. `deliver.py` 는 사본 쪽이
    새것이었으므로 **그 지시를 따랐으면 2026-08-20 양방향 대조 수정이 되돌아갔다.**
    감사가 결함을 재도입하는 지시를 내는 상태였다.

    `newer_out` 리스트를 주면 파일별 판정("live"/"copy"/None)을 담아 돌려준다 —
    조치 문구가 그것을 보고 방향을 정한다.
    """
    live, copy = listing(live_dir), listing(copy_dir)
    out = []

    # 1) 사본에 없는 것
    for f in sorted(set(live) - set(copy)):
        if f in EXCLUDED:
            out.append(("excluded", f"사본 미포함(의도): {f}"))
        elif f.endswith(".py"):
            out.append(("missing-code", f"사본에 코드가 없다: {f}"))
        else:
            out.append(("missing-asset", f"사본에 자산이 없다: {f}"))

    # 2) 사본에만 있는 것
    for f in sorted(set(copy) - set(live)):
        if f not in COPY_ONLY:
            out.append(("copy-only", f"실행 정본에 없는데 사본에만 있다: {f}"))

    # 3) 내용이 다른 것
    #
    # 개행(CRLF/LF)만 다른 것을 🔴 로 올리면 **매번 뜨는 거짓 경보**가 된다. 리포트에
    # 늘 빨간 줄이 있으면 사람이 리포트를 안 보게 되고, 그러면 이 감사가 있으나 마나가
    # 된다. 실행 정본은 gitignore 라 git 이 개행을 맞춰 줄 수 없으므로 늘 생길 수 있다.
    # 그래서 텍스트는 개행을 지운 내용으로 비교하고, 그것만 다르면 ⚪ 로 내린다.
    #
    # 이 정규화가 **진짜 차이를 삼키지 않는지**는 `self_test` 의 `one_char` 가 본다.
    for f in sorted(set(live) & set(copy)):
        if sha(live[f]) == sha(copy[f]):
            continue
        a, b = os.path.getsize(live[f]), os.path.getsize(copy[f])
        if f.endswith(TEXT_EXT):
            try:
                ta = open(live[f], "rb").read().replace(b"\r\n", b"\n")
                tb = open(copy[f], "rb").read().replace(b"\r\n", b"\n")
                if ta == tb:
                    out.append(("newline", f"개행만 다름(내용 동일): {f}"))
                    continue
            except Exception:
                pass
        _who, _why = _newer(live[f], f, copy_age)
        if newer_out is not None:
            newer_out.append((f, _who))
        # 사유 코드가 방향을 진다 — 등급이 여기서 갈린다(SEVERITY).
        _code = {"live": "content-unmerged", "copy": "content-stale"}.get(_who, "content")
        out.append((_code, f"내용이 다르다: {f} (워크숍 {a:,}B / 스킬 레포 {b:,}B) — {_why}"))
    return out


def same_content(a, b, name):
    """바이트가 같은가 — 텍스트면 **개행 차이는 같은 것으로 본다.**

    🔴 라이브 스킬은 **CRLF 로 깔린다**(2026-09-12 실측: `brand.py` 라이브 3,301B /
    블롭 3,241B). git 블롭은 LF 라 정규화 없이 대조하면 **텍스트 파일 전부가 «다르다»**
    로 떠서, 이 축이 첫날부터 24건짜리 거짓 경보가 된다 — `classify` 가 같은 함정을
    이미 한 번 밟고 ⚪ 로 내려 둔 자리다.
    """
    if sha(a) == sha(b):
        return True
    if name.endswith(TEXT_EXT):
        try:
            return (open(a, "rb").read().replace(b"\r\n", b"\n")
                    == open(b, "rb").read().replace(b"\r\n", b"\n"))
        except OSError:
            return False
    return False


def read_stamp(path):
    """`.deployed` 의 `revision:` 값 — `(리비전, 사유)`. 못 읽으면 `(None, 사유)`."""
    try:
        for ln in io.open(path, encoding="utf-8", errors="replace"):
            k, _, v = ln.partition(":")
            if k.strip() == "revision" and v.strip():
                return v.strip(), ""
        return None, "revision 줄이 없다"
    except OSError as e:
        return None, f"{type(e).__name__}"


def deploy_gap(live_skill, rev_now, export_fn):
    """배포본이 **자기 스탬프가 가리키는 리비전**과 같은가. `[(사유코드, 설명), ...]`.

    양쪽을 다 본다: 라이브에 **없거나 다른** 파일(배포가 덜 됐다)과 라이브에만 **남은**
    파일(레포에서 지웠는데 안 지워졌다). 뒤엣것도 결함이다 — 제작이 라이브를 `sys.path`
    앞에 두므로 **남은 옛 모듈이 조용히 먹힌다.**
    """
    if not os.path.isdir(live_skill):
        return [("deploy", f"라이브 스킬 폴더가 없다: {live_skill}")]
    rev, err = read_stamp(os.path.join(live_skill, ".deployed"))
    if not rev:
        return [("deploy", f"배포 스탬프를 못 읽는다 ({err}) — "
                           "라이브가 무엇인지 증명할 수 없다")]
    out = []
    if rev_now and rev != rev_now:
        out.append(("deploy-behind",
                    f"라이브는 {rev[:7]} · {COPY_REV} 는 {rev_now[:7]} — "
                    "머지 뒤 아직 배포 전이다(다음 스케줄 회차가 따라잡는다)"))
    want = export_fn(rev)
    if want is None:
        out.append(("deploy", f"스탬프가 가리키는 {rev[:7]} 을 꺼낼 수 없다 — "
                              "배포본을 대조할 수 없다"))
        return out
    got = listing(live_skill)
    bad = []
    for f in sorted(listing(want)):
        if f in DEPLOY_IGNORE:
            continue
        if f not in got:
            bad.append(f"배포 안 됨: {f}")
        elif not same_content(os.path.join(want, f), got[f], f):
            bad.append(f"내용 다름: {f}")
    for f in sorted(set(got) - set(listing(want)) - DEPLOY_IGNORE):
        bad.append(f"레포에 없는데 라이브에 남음: {f}")
    if bad:
        out.append(("deploy", f"라이브 실물이 자기 스탬프 {rev[:7]} 과 다르다 "
                              f"({len(bad)}건) — " + " · ".join(bad[:8])
                              + (" …" if len(bad) > 8 else "")))
    return out


def run_selftest(copy_dir):
    """사본의 자립 검증을 돌린다. 없으면 그 사실 자체가 결함이다."""
    st = os.path.join(copy_dir, "_selftest.py")
    if not os.path.exists(st):
        return None, "사본에 _selftest.py 가 없다"
    try:
        p = subprocess.run([sys.executable, st], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600,
                           cwd=copy_dir)
        return p.returncode == 0, (p.stdout or "").strip().splitlines()[-1:]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ── 역검증 — 모듈 안에 둔다 (정관 §0) ────────────────────────────────
# 합성 폴더 쌍으로 판정기 자신을 시험한다. 밖에서 감싸 돌리면 그 래퍼를 빠뜨린 실행이
# 아무것도 증명하지 않으므로, `main()` 이 시작할 때 여기서 먼저 돈다.
#
# 케이스는 **서로 걸리지 않게 분리**한다(§0). `one_char` 가 개행까지 같이 다르면
# «정규화가 진짜 차이를 삼키는지»를 증명하지 못한다 — 개행 차이로도 걸릴 수 있으니까.

#: (이름, 기대 사유코드 집합). 빈 집합이면 «일치»가 나와야 하는 입력이다.
_CASES = (
    ("identical", frozenset()),
    # 글자는 같고 개행만 다르다 → ⚪ 로 내려가야 한다 (🔴 면 매일 뜨는 거짓 경보)
    ("newline_only", frozenset({"newline"})),
    # 개행은 **양쪽 다 LF 로 같고** 글자 하나만 다르다 → 정규화가 삼키면 안 된다
    ("one_char", frozenset({"content"})),
    ("missing_py", frozenset({"missing-code"})),
    ("extra_file", frozenset({"copy-only"})),
)

_BODY = b"# -*- coding: utf-8 -*-\nX = 1\nY = 2\n"


def _synth(kind, root):
    """합성 정본/사본 폴더 쌍을 만들어 `(live, copy)` 경로를 돌려준다."""
    live, copy = os.path.join(root, "live"), os.path.join(root, "copy")
    os.makedirs(live), os.makedirs(copy)

    def put(d, name, data):
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)

    put(live, "brand.py", _BODY)
    put(copy, "brand.py", _BODY)
    if kind == "identical":
        pass
    elif kind == "newline_only":
        put(copy, "brand.py", _BODY.replace(b"\n", b"\r\n"))
    elif kind == "one_char":
        put(copy, "brand.py", _BODY.replace(b"X = 1", b"X = 2"))
    elif kind == "missing_py":
        put(live, "inner.py", _BODY)
    elif kind == "extra_file":
        put(copy, "ghost.py", _BODY)
    return live, copy


#: 방향 판정 역검증. **케이스를 하나씩 분리한다** — 한 입력이 여러 조건에 같이 걸리면
#: «그 판정이 제 몫을 했는지»가 증명되지 않는다(§0). 여기서는 정본 mtime 과 사본 커밋
#: 시각의 **차이 하나만** 바꾼다.
_DIR_CASES = (
    ("dir_live_newer", -86400, "live"),   # 사본 커밋이 하루 전  → 정본이 최근
    ("dir_copy_newer", +86400, "copy"),   # 사본 커밋이 하루 뒤  → 사본이 최근
    ("dir_margin",        -60, None),     # 1분 차이 (여유 5분 안) → 불명
)


def _dir_self_test():
    """`_newer` 가 방향을 실제로 가르는가. `[(이름, 기대, 실제, 통과)]`."""
    out = []
    for name, delta, expected in _DIR_CASES:
        with tempfile.TemporaryDirectory(prefix="drift_dir_") as td:
            f = os.path.join(td, "x.py")
            with open(f, "wb") as fh:
                fh.write(_BODY)
            lm = os.path.getmtime(f)
            got, _why = _newer(f, "x.py", lambda _n, _c=lm + delta: (_c, "합성"))
            out.append((name, frozenset([expected or "불명"]),
                        frozenset([got or "불명"]), got == expected))
    # 사본 시각을 못 읽으면 «불명»이어야 한다 — 못 읽은 것을 «정본이 최근»으로 읽으면
    # 이력 없는 새 파일마다 «덮어라» 지시가 나간다.
    with tempfile.TemporaryDirectory(prefix="drift_dir_") as td:
        f = os.path.join(td, "x.py")
        with open(f, "wb") as fh:
            fh.write(_BODY)
        got, _why = _newer(f, "x.py", lambda _n: (None, "이력 없음"))
        out.append(("dir_no_history", frozenset(["불명"]),
                    frozenset([got or "불명"]), got is None))
    return out


#: COPY_ONLY 역검증. 목록에 든 것은 면제되고, 안 든 것은 걸려야 한다.
#: **양쪽을 본다** — 면제만 보면 «전부 면제하는 목록»도 정상으로 보인다.
_CO_CASES = (
    ("copyonly_exempt", "epcheck.py", True),
    ("copyonly_catch", "not_in_list.py", False),
)


def _copyonly_self_test():
    out = []
    for name, fn, exempt in _CO_CASES:
        got = fn in COPY_ONLY
        out.append((name, frozenset(["면제" if exempt else "적발"]),
                    frozenset(["면제" if got else "적발"]), got == exempt))
    return out


#: 등급 방향 역검증. **한 입력에서 mtime 차이 하나만 바꾼다** — 다른 조건이 같이
#: 걸리면 «방향이 등급을 갈랐는지» 가 증명되지 않는다(§0).
_GRADE_CASES = (
    ("grade_workshop_ahead", -86400, "content-unmerged"),  # 워크숍이 앞섬 → 🔴
    ("grade_repo_ahead",     +86400, "content-stale"),     # 스킬 레포가 앞섬 → 🟡
    ("grade_unknown",           -60, "content"),           # 여유 안 → 방향 불명 → 🔴
)


def _grade_self_test():
    """방향이 사유 코드를, 사유 코드가 등급을 실제로 가르는가."""
    out = []
    want = {"content-unmerged": "red", "content-stale": "yellow", "content": "red"}
    for name, delta, code in _GRADE_CASES:
        with tempfile.TemporaryDirectory(prefix="drift_grade_") as td:
            live, copy = _synth("one_char", td)
            lm = os.path.getmtime(os.path.join(live, "brand.py"))
            got = frozenset(c for c, _ in classify(
                live, copy, copy_age=lambda _n, _c=lm + delta: (_c, "합성")))
            ok = got == frozenset({code}) and SEVERITY.get(code) == want[code]
            out.append((name, frozenset({code + "/" + want[code]}),
                        frozenset(sorted(c + "/" + str(SEVERITY.get(c)) for c in got)), ok))
    return out


#: 배포 역검증. **양쪽을 본다** — 잡는 쪽만 보면 «전부 잡는» 판정기도 정상으로 보이고,
#: 통과 쪽만 보면 «전부 눈감는» 판정기도 정상으로 보인다. 그리고 **«뒤처짐»과 «어긋남»을
#: 가르는 케이스를 따로 둔다** — 이 둘이 같은 등급이면 이번 개정이 아무것도 안 한 것이다.
_DEPLOY_CASES = (
    ("deploy_same",     "same",     frozenset()),
    ("deploy_stamp",    "stamp",    frozenset()),          # `.deployed` 는 대조에서 빠진다
    ("deploy_behind",   "behind",   frozenset({"white"})),  # 뒤처짐만 — 🔴 이면 안 된다
    ("deploy_crlf",     "crlf",     frozenset()),           # 라이브는 CRLF 로 깔린다
    ("deploy_changed",  "changed",  frozenset({"red"})),
    ("deploy_missing",  "missing",  frozenset({"red"})),
    ("deploy_leftover", "extra",    frozenset({"red"})),    # 지운 옛 모듈이 라이브에 남았다
    ("deploy_nostamp",  "nostamp",  frozenset({"red"})),
)


def _deploy_self_test():
    out = []
    for name, kind, expect in _DEPLOY_CASES:
        with tempfile.TemporaryDirectory(prefix="drift_dep_") as td:
            repo, live = os.path.join(td, "repo"), os.path.join(td, "live")
            os.makedirs(repo), os.makedirs(live)

            def put(d, fn, data):
                with open(os.path.join(d, fn), "wb") as f:
                    f.write(data)

            put(repo, "brand.py", _BODY)
            if kind != "missing":
                _body = _BODY
                if kind == "changed":
                    _body = _BODY.replace(b"X = 1", b"X = 2")
                elif kind == "crlf":
                    _body = _BODY.replace(b"\n", b"\r\n")
                put(live, "brand.py", _body)
            if kind != "nostamp":
                put(live, ".deployed", b"revision: aaaa111\nshort: aaaa111\n")
            if kind == "extra":
                put(live, "old_module.py", _BODY)
            # 「뒤처짐」은 스탬프와 origin/main 이 다른 경우다 — 실물은 스탬프와 같다.
            rev_now = "bbbb222" if kind == "behind" else "aaaa111"
            got = frozenset(SEVERITY.get(c) for c, _ in
                            deploy_gap(live, rev_now, lambda _r: repo))
            out.append((name, expect or frozenset(["통과"]),
                        got or frozenset(["통과"]), got == expect))
    return out


def self_test():
    """`[(이름, 기대, 실제, 통과)]`."""
    out = []
    for name, expected in _CASES:
        with tempfile.TemporaryDirectory(prefix="drift_") as td:
            live, copy = _synth(name, td)
            got = frozenset(code for code, _ in classify(live, copy))
            out.append((name, expected, got, got == expected))
    out += _dir_self_test()
    out += _copyonly_self_test()
    out += _grade_self_test()
    out += _deploy_self_test()
    return out


def _ensure_self_test():
    bad = [r for r in self_test() if not r[3]]
    if bad:
        lines = [f"  {n}: 기대={sorted(e) or '일치'} 실제={sorted(g) or '일치'}"
                 for n, e, g, _ in bad]
        raise AssertionError(
            "드리프트 판정기 역검증 실패 — 검사기 자신이 헛돌고 있다:\n" + "\n".join(lines))


def main():
    _ensure_self_test()        # 검사기가 헛돌면 감사를 시작조차 하지 않는다 (§0)

    if not os.path.isdir(LIVE):
        print(f"경로가 없다: {LIVE}")
        print("STATUS: FAIL path-missing")
        return 2

    tmp = None
    rev_desc = COPY_DIR or f"{COPY_REV} @ {COPY_REPO}"
    reasons = []
    newer = []          # [(파일명, "live"/"copy"/None)] — 조치 문구가 방향을 정할 근거
    try:
        if COPY_DIR:
            # 폴더를 직접 지정했다 — 역검증·디버깅 경로. fetch 도 클론 상태도 보지 않는다.
            if not os.path.isdir(COPY_DIR):
                print(f"경로가 없다: {COPY_DIR}")
                print("STATUS: FAIL path-missing")
                return 2
            copy_dir = COPY_DIR
        else:
            if not os.path.isdir(COPY_REPO):
                print(f"레포가 없다: {COPY_REPO}")
                print("STATUS: FAIL path-missing")
                return 2
            # fetch 는 원격 추적 ref 만 갱신한다 — 워킹 트리·HEAD 는 그대로다.
            # 안 하면 낡은 origin/main 과 비교하고도 «일치»라고 말한다.
            try:
                git(COPY_REPO, "fetch", "--quiet", "origin")
            except Exception as e:
                print(f"git fetch 실패: {e}")
                print("STATUS: FAIL git-fetch")
                return 2
            sha_full = git(COPY_REPO, "rev-parse", COPY_REV).stdout.decode().strip()
            when = git(COPY_REPO, "log", "-1", "--format=%cI",
                       COPY_REV).stdout.decode().strip()
            rev_desc = f"`{COPY_REV}` = {sha_full[:7]} ({when})"
            tmp = tempfile.mkdtemp(prefix="drift_copy_")
            copy_dir = export_rev(COPY_REPO, COPY_REV, COPY_SUB, tmp)
            reasons += clone_state(COPY_REPO, COPY_REV)

        def _copy_age(name):
            """사본 쪽 «최근» 근거 — 그 경로를 마지막으로 건드린 커밋 시각."""
            rel = COPY_SUB.rstrip("/") + "/" + name
            try:
                r = git(COPY_REPO, "log", "-1", "--format=%ct|%cI", COPY_REV, "--", rel, check=False)
                txt = r.stdout.decode("utf-8", "replace").strip()
                if r.returncode != 0 or not txt:
                    return None, "이력 없음"
                ct, _, ci = txt.partition("|")
                return int(ct), ci[:16].replace("T", " ")
            except Exception:                      # noqa: BLE001
                return None, "git 조회 실패"

        _copy_age_fn = _copy_age if COPY_REPO and not COPY_DIR else None
        reasons += classify(LIVE, copy_dir, copy_age=_copy_age_fn, newer_out=newer)

        # 배포 축은 레포가 있을 때만 돈다. `TOMANGCHI_COPY` 로 폴더를 직접 지정한
        # 회차(역검증·디버깅)는 스탬프 리비전을 꺼낼 레포가 없다.
        if not COPY_DIR:
            _stamp_tmps = []

            def _export_stamp(rev):
                try:
                    d = tempfile.mkdtemp(prefix="drift_deployed_")
                    _stamp_tmps.append(d)
                    return export_rev(COPY_REPO, rev, COPY_SUB, d)
                except Exception:              # noqa: BLE001
                    return None

            try:
                reasons += deploy_gap(LIVE_SKILL, sha_full, _export_stamp)
            finally:
                for _d in _stamp_tmps:
                    shutil.rmtree(_d, ignore_errors=True)

        ok, detail = run_selftest(copy_dir)
        if ok is None:
            reasons.append(("selftest", f"자립 검증 불가 — {detail}"))
        elif not ok:
            reasons.append(("selftest", f"사본 자립 검증 실패 — {detail}"))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    red = [t for c, t in reasons if SEVERITY.get(c) == "red"]
    yellow = [t for c, t in reasons if SEVERITY.get(c) == "yellow"]
    white = [t for c, t in reasons if SEVERITY.get(c) == "white"]

    os.makedirs(REPORTS, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    out = os.path.join(REPORTS, f"{day}_skill-drift.md")
    lines = [
        f"# 스킬 사본 드리프트 감사 — {day}",
        "",
        "- 부서: 운영팀 / 등급: **A (read-only)**",
        f"- 실행 정본: `{LIVE}`",
        f"- 버전관리 사본: {rev_desc}",
        "",
        "## 결론",
        "",
    ]
    if red:
        lines += [f"**🔴 {len(red)}건 — 승계되지 않은 수정·배포 누락이 있거나 스킬이 돌지 않는다.**", ""]
    elif yellow:
        lines += [f"**🟡 {len(yellow)}건 — 스킬 레포는 배포됐고 돈다. 워크숍 사본·자산·클론 쪽 차이다.**", ""]
    else:
        lines += ["**⚪ 드리프트 없음. 두 폴더가 일치하고 배포본도 `origin/main` 그대로다.**", ""]
    for label, items in (("🔴 즉시", red), ("🟡 이번 주", yellow), ("⚪ 참고", white)):
        if items:
            lines += [f"## {label}", ""] + [f"- {t}" for t in items] + [""]
    # 2026-08-21: 조치 문구가 **방향을 따른다.** 종전에는 방향과 무관하게 늘
    # «실행 정본에서 복사해 커밋»이었고, 사본이 새것인 파일에 그 지시를 따르면
    # 사본의 수정이 사라진다 (`deliver.py` 실제 사례). 방향을 모르면 지시하지 않는다.
    _dirs = [w for _, w in newer]
    _live_new = [f for f, w in newer if w == "live"]
    _copy_new = [f for f, w in newer if w == "copy"]
    _unknown = [f for f, w in newer if w is None]
    lines += ["## 조치", "",
              "`py scripts\\skill_drift_audit.py` 가 낸 결과다. 비교 대상은 클론의 워킹",
              f"트리가 아니라 **{COPY_REV}** — 배포되는 것이 그것이기 때문이다(§4).",
              "",
              "🔴 **정본은 스킬 레포다** — 제작은 `sys.path` 앞자리의 라이브 스킬을 먼저 읽는다"
              "(`build_ep57.py`). 워크숍 `00_브랜드에셋` 이 뒤처진 것은 결함이 아니다.", ""]
    if newer:
        lines += ["**방향 판정** — 근거는 정본 `mtime` 과 사본 마지막 커밋 시각이다. "
                  "성질이 다른 두 값이라 **단정하지 않는다**; 차이가 5분 미만이면 «불명»으로 둔다.", ""]
        if _live_new:
            lines += [f"- 🔴 **워크숍이 앞선다 ({len(_live_new)}건)**: {', '.join('`' + x + '`' for x in _live_new)}",
                      "  → **스킬 레포로 승계되지 않은 수정이다.** 워크숍 파일을 스킬 레포로 옮겨 "
                      "PR·머지한 뒤 `py skills\\tomangchi\\_selftest.py` 로 자립을 확인한다. "
                      "그대로 두면 다음 편이 라이브 스킬을 읽으면서 그 수정을 잃는다.", ""]
        if _copy_new:
            lines += [f"- 🟡 **스킬 레포가 최근 ({len(_copy_new)}건)**: {', '.join('`' + x + '`' for x in _copy_new)}",
                      "  → **정상이다. 조치하지 않는다.** 제작은 라이브 스킬을 먼저 읽으므로 "
                      "워크숍 사본이 뒤처져도 아무것도 안 깨진다. 🔴 워크숍은 출장지라 "
                      "에이전트가 덮어쓰지 않는다(§2) — 근본 해결은 정본 단일화로 그 폴더를 없애는 것이다.", ""]
        if _unknown:
            lines += [f"- ⚪ **방향 불명 ({len(_unknown)}건)**: {', '.join('`' + x + '`' for x in _unknown)}",
                      "  → **복사 지시를 내지 않는다.** 어느 쪽이 새것인지 사람이 두 파일을 보고 정한다. "
                      "모르는 채로 덮는 것이 이 감사가 막으려는 사고다.", ""]
    lines += ["> 근본 해결은 정본 단일화다 — `docs/plan-brand-assets-move.md` 참조.", ""]

    # STATUS is the last line of the report body, same as the three agent jobs
    # (charter section 5). Until 2026-08-21 this job printed STATUS to stdout only,
    # so its report was the one artifact of record with no verdict in it. The
    # verdict is computed once here and reused for stdout - two places must not be
    # able to disagree.
    status = f"STATUS: FAIL drift-{len(red)}" if red else "STATUS: OK"
    lines += [status, ""]

    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    print(f"리포트: {out}")
    print(f"비교 대상: {rev_desc}")
    print(f"🔴 {len(red)}  🟡 {len(yellow)}  ⚪ {len(white)}")
    for t in red:
        print("  🔴 " + t)
    for t in yellow:
        print("  🟡 " + t)
    print(status)
    return 1 if red else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        print("[역검증]")
        allgood = True
        for name, expected, got, ok in self_test():
            allgood &= ok
            print(f"  {'OK  ' if ok else 'FAIL'} {name:13} "
                  f"기대={sorted(expected) or ['일치']} 실제={sorted(got) or ['일치']}")
        sys.exit(0 if allgood else 1)
    sys.exit(main())
