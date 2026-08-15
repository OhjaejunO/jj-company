#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스킬 사본 드리프트 감사 (A등급 · read-only)

토망치랩 브랜드 스크립트는 **두 곳에 있다.**

    실행 정본  tomangchi-lab.github.io/workshop/00_브랜드에셋   (gitignore, 제작이 여기를 import)
    버전관리 사본  tomangchi-skill/skills/tomangchi              (git, 스킬이 배포하는 것)

제작은 전부 실행 정본으로 돌아가므로 **사본이 낡거나 깨져도 아무도 죽지 않는다.**
그래서 드리프트가 조용히 쌓인다 — 정관 §0 «조용히 실패하는 코드»와 같은 계열이다.
실제로 `brand.py` 가 사본에 통째로 없었는데 몇 주간 아무 신호가 없었다(2026-08-15).

막을 수 없다면 **소리를 내게** 한다. 이 감사가 그 소리다.

세 가지를 본다.
  1. 사본에 없는 파일        — 특히 코드(.py)와 코드가 실행 중에 여는 자산
  2. 양쪽에 다 있는데 다른 파일 — 해시 비교
  3. 사본이 실제로 도는가     — 사본의 `_selftest.py` 를 돌린다

**읽기만 한다.** 두 폴더 어디에도 쓰지 않는다. 산출은 운영 서버 reports/ 한 곳뿐이다.
"""
import hashlib
import io
import os
import subprocess
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

#: 경로는 환경변수로 덮을 수 있다. 스케줄은 기본값으로 돌고, **역검증**(§0)은
#: 동기화된 worktree 를 사본으로 지정해 «드리프트 없음»이 실제로 나오는지 본다.
#: 통과만 확인하는 검사는 헛돌아도 통과처럼 보인다 — 양쪽을 다 본다.
LIVE = os.environ.get(
    "TOMANGCHI_LIVE",
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop\00_브랜드에셋")
COPY = os.environ.get(
    "TOMANGCHI_COPY",
    r"C:\Users\ojaej\orca\tomangchi-skill\skills\tomangchi")
REPORTS = os.environ.get("JJ_REPORTS", r"C:\Users\ojaej\jj-company\reports")

#: 사본에 **일부러 넣지 않은** 것. 런타임에 열리지 않는 원본·참고 자산이라 약 9MB 를
#: 레포에 넣지 않기로 했다(2026-08-15). 목록에 있으면 ⚪ 참고로만 보고한다.
#: 새 파일이 생기면 이 목록 밖이라 🟡 로 떠서 사람이 판단하게 된다 — 그게 목적이다.
EXCLUDED = {
    "avatar_1024.png", "post_sample_8.png", "endcard_v2.png", "_endcard_prev.png",
    "토망치 커버1.png", "토망치 커버2.png", "토망치 커버3.png", "토망치 프로필.png",
}
#: 사본에만 있어야 정상인 것.
COPY_ONLY = {"SKILL.md", "_selftest.py"}


def sha(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def listing(d):
    return {f: os.path.join(d, f) for f in sorted(os.listdir(d))
            if os.path.isfile(os.path.join(d, f))}


def run_selftest():
    """사본의 자립 검증을 돌린다. 없으면 그 사실 자체가 결함이다."""
    st = os.path.join(COPY, "_selftest.py")
    if not os.path.exists(st):
        return None, "사본에 _selftest.py 가 없다"
    try:
        p = subprocess.run([sys.executable, st], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300, cwd=COPY)
        return p.returncode == 0, (p.stdout or "").strip().splitlines()[-1:]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    for d in (LIVE, COPY):
        if not os.path.isdir(d):
            print(f"경로가 없다: {d}")
            print("STATUS: FAIL path-missing")
            return 2

    live, copy = listing(LIVE), listing(COPY)
    red, yellow, white = [], [], []

    # 1) 사본에 없는 것
    for f in sorted(set(live) - set(copy)):
        if f in EXCLUDED:
            white.append(f"사본 미포함(의도): {f}")
        elif f.endswith(".py"):
            red.append(f"사본에 코드가 없다: {f}")
        else:
            yellow.append(f"사본에 자산이 없다: {f}")

    # 2) 사본에만 있는 것
    for f in sorted(set(copy) - set(live)):
        if f not in COPY_ONLY:
            yellow.append(f"실행 정본에 없는데 사본에만 있다: {f}")

    # 3) 내용이 다른 것
    #
    # 줄바꿈(CRLF/LF)만 다른 것을 🔴 로 올리면 **매번 뜨는 거짓 경보**가 된다.
    # 리포트에 항상 빨간 줄이 있으면 사람이 리포트를 안 보게 되고, 그러면 이 감사가
    # 있으나 마나가 된다. git 이 체크아웃 때 줄바꿈을 바꾸므로 실제로 늘 생긴다.
    # 그래서 텍스트는 줄바꿈을 지운 내용으로 비교하고, 그것만 다르면 ⚪ 로 내린다.
    for f in sorted(set(live) & set(copy)):
        if sha(live[f]) == sha(copy[f]):
            continue
        a, b = os.path.getsize(live[f]), os.path.getsize(copy[f])
        if f.endswith((".py", ".md", ".txt", ".json")):
            try:
                ta = open(live[f], "rb").read().replace(b"\r\n", b"\n")
                tb = open(copy[f], "rb").read().replace(b"\r\n", b"\n")
                if ta == tb:
                    white.append(f"줄바꿈만 다름(내용 동일): {f}")
                    continue
            except Exception:
                pass
        red.append(f"내용이 다르다: {f} (정본 {a:,}B / 사본 {b:,}B)")

    # 4) 사본이 실제로 도는가
    ok, detail = run_selftest()
    if ok is None:
        red.append(f"자립 검증 불가 — {detail}")
    elif not ok:
        red.append(f"사본 자립 검증 실패 — {detail}")

    os.makedirs(REPORTS, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    out = os.path.join(REPORTS, f"{day}_skill-drift.md")
    lines = [
        f"# 스킬 사본 드리프트 감사 — {day}",
        "",
        "- 부서: 운영팀 / 등급: **A (read-only)**",
        f"- 실행 정본: `{LIVE}`",
        f"- 버전관리 사본: `{COPY}`",
        "",
        "## 결론",
        "",
    ]
    if red:
        lines += [f"**🔴 {len(red)}건 — 사본이 정본과 갈라졌거나 돌지 않는다.**", ""]
    elif yellow:
        lines += [f"**🟡 {len(yellow)}건 — 코드는 일치하나 자산 차이가 있다.**", ""]
    else:
        lines += ["**⚪ 드리프트 없음. 사본이 정본과 일치하고 단독으로 돈다.**", ""]
    for label, items in (("🔴 즉시", red), ("🟡 이번 주", yellow), ("⚪ 참고", white)):
        if items:
            lines += [f"## {label}", ""] + [f"- {t}" for t in items] + [""]
    lines += ["## 조치", "",
              "`py scripts\\skill_drift_audit.py` 가 낸 결과다. 사본을 맞추려면 실행 정본에서",
              "복사한 뒤 `py skills\\tomangchi\\_selftest.py` 로 자립을 다시 확인한다.",
              "", "> 근본 해결은 정본 단일화다 — `docs/plan-brand-assets-move.md` 참조.", ""]
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    print(f"리포트: {out}")
    print(f"🔴 {len(red)}  🟡 {len(yellow)}  ⚪ {len(white)}")
    for t in red:
        print("  🔴 " + t)
    for t in yellow:
        print("  🟡 " + t)
    if red:
        print(f"STATUS: FAIL drift-{len(red)}")
        return 1
    print("STATUS: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
