#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스킬 사본 드리프트 감사 (A등급 · read-only)

토망치랩 브랜드 스크립트는 **두 곳에 있다.**

    실행 정본  tomangchi-lab.github.io/workshop/00_브랜드에셋   (gitignore, 제작이 여기를 import)
    버전관리 사본  tomangchi-skill  `origin/main:skills/tomangchi`  (스킬이 배포하는 것)

제작은 전부 실행 정본으로 돌아가므로 **사본이 낡거나 깨져도 아무도 죽지 않는다.**
그래서 드리프트가 조용히 쌓인다 — 정관 §0 «조용히 실패하는 코드»와 같은 계열이다.
실제로 `brand.py` 가 사본에 통째로 없었는데 몇 주간 아무 신호가 없었다(2026-08-15).

막을 수 없다면 **소리를 내게** 한다. 이 감사가 그 소리다.

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

**두 정본 폴더 어디에도 쓰지 않는다.** 쓰는 곳은 임시 폴더와 운영 서버 reports/ 뿐이다.

## 역검증 (§0)

`self_test()` 가 합성 폴더 쌍으로 판정기 자신을 시험하고, `main()` 이 시작할 때 돈다.
**사유 코드까지 대조한다** — 통과/실패만 보면 엉뚱한 사유로 걸려도 «잡았다»로 읽힌다.
특히 `one_char` 케이스는 개행 정규화가 **진짜 차이를 삼키지 않는지**를 본다. 정규화를
넣은 검사는 이 케이스가 없으면 «전부 통과»와 «전부 눈감음»이 구분되지 않는다.
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
COPY_ONLY = {"SKILL.md", "_selftest.py", "epcheck.py", "verify.template.py"}

#: 개행 정규화를 적용할 확장자. **바이너리에는 쓰지 않는다** — PNG 안의 `\r\n`
#: 바이트를 지우면 진짜 차이를 가려 버린다.
TEXT_EXT = (".py", ".md", ".txt", ".json", ".ps1", ".yml", ".yaml")

#: 사유 코드 → 심각도. 리포트 색은 여기 한 곳에서만 정한다.
SEVERITY = {
    "missing-code": "red",
    "content": "red",
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
        return "live", f"정본 mtime {ls} · 사본 커밋 {cs} — **정본이 최근**"
    return "copy", f"정본 mtime {ls} · 사본 커밋 {cs} — **사본이 최근** (정본으로 덮으면 사본 수정이 사라진다)"


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
        out.append(("content", f"내용이 다르다: {f} (정본 {a:,}B / 사본 {b:,}B) — {_why}"))
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
        lines += [f"**🔴 {len(red)}건 — 사본이 정본과 갈라졌거나 돌지 않는다.**", ""]
    elif yellow:
        lines += [f"**🟡 {len(yellow)}건 — 코드는 일치하나 자산·클론 상태에 차이가 있다.**", ""]
    else:
        lines += ["**⚪ 드리프트 없음. 사본이 정본과 일치하고 단독으로 돈다.**", ""]
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
              f"트리가 아니라 **{COPY_REV}** — 배포되는 것이 그것이기 때문이다(§4).", ""]
    if newer:
        lines += ["**방향 판정** — 근거는 정본 `mtime` 과 사본 마지막 커밋 시각이다. "
                  "성질이 다른 두 값이라 **단정하지 않는다**; 차이가 5분 미만이면 «불명»으로 둔다.", ""]
        if _live_new:
            lines += [f"- **정본이 최근 ({len(_live_new)}건)**: {', '.join('`' + x + '`' for x in _live_new)}",
                      "  → 실행 정본에서 사본으로 복사해 **커밋·머지**한 뒤 "
                      "`py skills\\tomangchi\\_selftest.py` 로 자립을 다시 확인한다.", ""]
        if _copy_new:
            lines += [f"- 🔴 **사본이 최근 ({len(_copy_new)}건)**: {', '.join('`' + x + '`' for x in _copy_new)}",
                      "  → **반대 방향이다.** 사본에서 실행 정본으로 가져온다. "
                      "정본으로 덮으면 사본에 들어간 수정이 사라진다.", ""]
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
