#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""워크숍 소스 → 사설 레포 **단방향 push** (정관 §2 예외 3번 · 인프라 백로그 21번 ㉮).

## 🔴 단방향을 «규율» 이 아니라 «구조» 로 만든다 (§0 4층 ①)

훅으로 «워크숍으로 pull 하지 마라» 를 막는 방법도 있지만, 그것은 ③층이다. 여기서는
**워크숍을 그 레포의 작업 트리로 만들지 않는다.**

    워크숍 (읽기만)  ──복사──▶  스테이징 클론  ──push──▶  OhjaejunO/tomangchi-workshop
    C:\...\workshop              C:\...\tomangchi-workshop

워크숍에는 그 레포의 `.git` 이 **없다.** 그러므로 `git pull`·`checkout`·`reset` 이
**워크숍에 닿을 경로 자체가 없다** — 실수로도 못 덮는다. 이것이 이 설계의 요점이다.

매 회차 그것을 **실증**한다:
  · 워크숍 트리 지문(파일 수 + 경로·크기·mtime 해시)이 전후로 같은가
  · 워크숍 안에 이 레포를 가리키는 `.git` 이 생기지 않았는가

## 추적 대상 (백로그 21번 목록 · JJ 지시 2026-08-30)

텍스트 소스(`.py`·`.md`·`.txt`·`.json`·`.html`) + 편별 선언 + `_official/` +
`스캔로그/` + `발행로그.md`. **렌더 산출물은 추적하지 않는다** — 코드가 다시 만든다.

🔴 **다시 못 만드는 렌더물이 더 있다.** `_scenes/`(모델 생성)·`_assets/`(JJ 제공)·
   브랜드 이미지·옛 편 표지 시안이 그것이고, 합치면 **1.7GB** 다. 이 스크립트는 그것을
   **담지 않는다** — 담을지는 무게 때문에 사람이 정할 일이라 `--report-exceptions` 로
   목록과 크기만 낸다(정관 §0 «못 하는 것은 못 한다고 적는다»).

## 병행

zip 백업(`workshop_backup.py`)은 **끄지 않는다.** 둘은 같은 사고로 같이 죽지 않는다 —
하나는 레포(원격), 하나는 드라이브다.
"""
import argparse
import datetime
import hashlib
import io
import os
import shutil
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

WS = os.environ.get(
    "TOMANGCHI_WORKSHOP",
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop")
STAGE = os.environ.get(
    "TOMANGCHI_WS_REPO", r"C:\Users\ojaej\orca\tomangchi-workshop")
REMOTE = "https://github.com/OhjaejunO/tomangchi-workshop.git"

SRC_EXT = (".py", ".md", ".txt", ".json", ".html")
MUST_DIRS = ("_official", "\uc2a4\uce94\ub85c\uadf8")
MUST_FILES = ("\ubc1c\ud589\ub85c\uadf8.md",)
SKIP_DIRS = ("__pycache__", ".git")
#: 담지 않지만 **다시 못 만드는** 것 — 목록만 낸다(위 독스트링 참조).
EXCEPTION_DIRS = ("_scenes", "_assets")

GITIGNORE = """# 렌더 산출물은 추적하지 않는다 — 코드가 소스에서 다시 만든다.
# 🔴 다시 못 만드는 렌더물(_scenes/·_assets/·브랜드 이미지·옛 표지 시안, 합계 1.7GB)은
#    무게 때문에 여기 없다. 목록은 `workshop_repo_sync.py --report-exceptions`.
*.png
*.jpg
*.jpeg
*.webp
*.gif
*.mp4
*.mov
*.pdf
*.log
*.bak
__pycache__/

# 예외 — 내려받은 공식 원본은 만든 적이 없으므로 추적한다.
!**/_official/**
"""


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit("🔴 git %s → %s\n%s" % (" ".join(args), r.returncode, r.stderr))
    return (r.stdout or "").strip()


def tracked(root):
    """추적할 (상대경로, 절대경로) — 백로그 21번 목록."""
    out = []
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        parts = os.path.relpath(cur, root).replace("\\", "/").split("/")
        in_must = any(p in MUST_DIRS for p in parts)
        for f in files:
            rel = os.path.relpath(os.path.join(cur, f), root).replace("\\", "/")
            if in_must or f in MUST_FILES or f.lower().endswith(SRC_EXT):
                out.append((rel, os.path.join(cur, f)))
    return sorted(out)


def tree_state(root):
    """워크숍이 안 바뀌었음을 볼 지문."""
    h = hashlib.sha256()
    n = 0
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            p = os.path.join(cur, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            n += 1
            h.update(("%s|%d|%d" % (os.path.relpath(p, root), st.st_size,
                                    int(st.st_mtime))).encode("utf-8", "replace"))
    return n, h.hexdigest()


def assert_oneway(root):
    """🔴 워크숍이 이 레포의 작업 트리가 아님을 확인한다 — 단방향의 뿌리."""
    bad = []
    for cur, dirs, _ in os.walk(root):
        if ".git" in dirs:
            bad.append(os.path.relpath(cur, root) or ".")
            dirs.remove(".git")
    return bad


def report_exceptions(root):
    """담지 않지만 다시 못 만드는 것 — 목록과 크기."""
    IMG = (".png", ".jpg", ".jpeg", ".mp4", ".webp", ".gif", ".mov", ".ttf", ".otf")
    buckets = {}
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(cur, root).replace("\\", "/")
        parts = rel.split("/")
        for f in files:
            if not f.lower().endswith(IMG):
                continue
            if any(p in ("_official",) for p in parts):
                continue                                   # 이미 추적한다
            if any(p in EXCEPTION_DIRS for p in parts):
                k = "%s/ (모델 생성·제공 에셋)" % [p for p in parts if p in EXCEPTION_DIRS][0]
            elif parts and parts[0].startswith("00_"):
                k = "00_브랜드에셋 이미지"
            elif f[:1].isdigit() or "shots" in parts or f.startswith("_"):
                continue                                   # 코드가 다시 만든다
            else:
                k = "옛 편 표지 시안·릴스"
            b = buckets.setdefault(k, [0, 0])
            b[0] += 1
            try:
                b[1] += os.path.getsize(os.path.join(cur, f))
            except OSError:
                pass
    return buckets


def main(argv=None):
    ap = argparse.ArgumentParser(description="워크숍 소스 단방향 push")
    ap.add_argument("--message", default=None)
    ap.add_argument("--no-push", action="store_true", help="커밋까지만 (시험용)")
    ap.add_argument("--report-exceptions", action="store_true")
    a = ap.parse_args(argv)

    if not os.path.isdir(WS):
        print("🔴 워크숍을 못 찾았다: %s" % WS)
        print("STATUS: FAIL workshop-missing")
        return 1

    if a.report_exceptions:
        print("담지 않지만 **다시 못 만드는** 렌더물")
        tot = 0
        for k, (n, sz) in sorted(report_exceptions(WS).items(), key=lambda x: -x[1][1]):
            tot += sz
            print("  %-34s %5d개 · %8.1f MB" % (k, n, sz / 1e6))
        print("  합계 %.2f GB — 이만큼을 담을지는 **사람이 정한다**" % (tot / 1e9))
        return 0

    # ── 단방향 확인 (구조) ──────────────────────────────────────────────
    nested = assert_oneway(WS)
    if nested:
        print("🔴 워크숍 안에 `.git` 이 있다: %s" % nested[:3])
        print("   이 설계는 «워크숍이 그 레포의 작업 트리가 아니라는 것» 이 단방향의 뿌리다.")
        print("STATUS: FAIL workshop-is-a-worktree")
        return 1
    print("단방향 확인 — 워크숍에 `.git` 없음 (pull·checkout 이 닿을 경로가 없다)")

    before = tree_state(WS)

    # ── 스테이징 클론 ──────────────────────────────────────────────────
    if not os.path.isdir(os.path.join(STAGE, ".git")):
        os.makedirs(STAGE, exist_ok=True)
        git(STAGE, "init", "-q")
        git(STAGE, "remote", "add", "origin", REMOTE)
        print("스테이징 클론 생성: %s" % STAGE)
    io.open(os.path.join(STAGE, ".gitignore"), "w", encoding="utf-8",
            newline="\n").write(GITIGNORE)

    items = tracked(WS)
    print("추적 대상 %d개" % len(items))

    # 옛 판 제거 — 워크숍에서 사라진 파일이 레포에 남지 않게
    for cur, dirs, files in os.walk(STAGE):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            if f in (".gitignore", "README.md", "동기절차.md"):
                continue
            p = os.path.join(cur, f)
            rel = os.path.relpath(p, STAGE).replace("\\", "/")
            if rel not in {r for r, _ in items}:
                os.remove(p)

    total = 0
    for rel, src in items:
        dst = os.path.join(STAGE, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        total += os.path.getsize(src)
    print("복사 완료 %.2f MB" % (total / 1e6))

    # ── 워크숍 불변 (실증) ─────────────────────────────────────────────
    after = tree_state(WS)
    if after != before:
        print("🔴 워크숍 트리가 바뀌었다 — 이 작업은 읽기 전용이어야 한다 (정관 §2)")
        print("STATUS: FAIL workshop-mutated")
        return 1
    print("워크숍 불변 확인 — 파일 %d개 · 지문 %s…" % (before[0], before[1][:12]))

    git(STAGE, "add", "-A")
    if not git(STAGE, "status", "--porcelain"):
        print("바뀐 것이 없다 — 커밋하지 않는다")
        print("STATUS: OK (no-change)")
        return 0

    msg = a.message or ("chore(workshop): 소스 동기 %s"
                        % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    git(STAGE, "-c", "user.name=OhjaejunO",
        "-c", "user.email=ojaejun1995@gmail.com", "commit", "-q", "-m", msg)
    print("커밋: %s" % git(STAGE, "log", "--oneline", "-1"))

    if a.no_push:
        print("STATUS: OK (--no-push)")
        return 0
    git(STAGE, "push", "-q", "-u", "origin", "HEAD:main")
    print("push 완료 → %s" % REMOTE)
    print("STATUS: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
