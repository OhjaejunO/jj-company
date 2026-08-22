#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기록 일관성 감사 (A등급 · read-only)

**문서가 주장하는 것과 실제로 있는 것을 대조한다.** 세 감사가 한 파일에 있는 이유는
셋이 같은 모양이기 때문이다 — 문서에서 토큰을 뽑아 다른 곳에 실재하는지 본다.
결정적 비교라 정답이 있고, 그래서 §0 대로 **모델을 넣지 않는다.**

    publish   발행로그 × content-ops DB × 실제 폴더        (정비 항목 4)
    watch     소재 문서의 «조건» × 그 문서의 «감시처» 선언   (정비 항목 6)
    symbol    SKILL.md 의 코드 식별자 × 레포 실재            (정비 항목 5)

## 왜 감사부터인가

셋 다 **쓰기가 없다.** 자동화(`publish-done` 등)가 붙기 전까지 새로 새는 것을
잡아 주는 보험이고, 자동화를 설계할 때 «무엇이 어긋나는가»를 이미 말해 준다.

## 2026-08-22 하루에 드러난 것들이 이 감사의 근거다

  - ep25·ep26  발행로그 행 자체가 없었다
  - ep21·ep22  행은 있는데 상태가 `제작완료` 로 남아 실물과 어긋났다 → 대기함 보고가 오판
  - ep15~17    발행로그는 `발행` 인데 DB 레코드가 아예 없었다
  - 히기        「Seedance 2.5 출시되면」이 감시표 어디에도 없어 출시를 16일간 못 봤다
  - save_scene  SKILL.md 가 부르는 함수가 레포 어디에도 없다

## 위치 대조는 폴더명이 아니라 «위치» 칸을 읽는다

1차 전수에서 `epNN_` 패턴으로 폴더를 훑었더니 ep6·ep7·ep17 이 **거짓 경보**로 걸렸다.
셋 다 폴더명이 규칙 밖일 뿐 정상이다. 발행로그 갱신 규칙 4가 이미 「못 옮기는 편은
«위치» 칸에 실제 경로를 적는다」로 정해 뒀고, **26편 전부 그 칸의 경로가 실재했다.**
예외 목록을 두는 것이 아니라 **칸을 읽는 것**이 답이다 — 거짓 경보를 남기면
사람이 경보 자체를 안 보게 된다.

## 역검증 (§0)

`--selftest` 는 **일부러 걸려야 하는 입력**을 세 감사에 각각 넣어 실제로 걸리는지,
그리고 정상 입력은 통과하는지 **양쪽**을 본다. 한 유형만 시험하면 나머지 둘은
헛돌아도 모른다 — 2026-08-22 에 세 유형이 각각 다른 방식으로 샜기 때문에
**세 개를 따로** 시험한다.

정상 종료 시 마지막 줄에 `STATUS: OK` 또는 `STATUS: FAIL <사유>` 를 찍는다.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime

# ── 경로 (환경변수로 덮어쓸 수 있다 — skill_drift_audit.py 와 같은 방식) ──────
WORKSHOP = os.environ.get(
    "TOMANGCHI_WORKSHOP",
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop")
SKILL_MD = os.environ.get(
    "TOMANGCHI_SKILL_MD",
    r"C:\Users\ojaej\.claude\skills\tomangchi\SKILL.md")
CONTENT_OPS = os.environ.get("CONTENT_OPS", r"C:\Users\ojaej\orca\content-ops")
CONFIG_MD = os.environ.get(
    "JJ_SCOUT_CONFIG",
    r"C:\Users\ojaej\jj-company\departments\marketing\config.md")
#: 식별자 실재 여부를 찾을 곳. 없는 경로는 조용히 건너뛰지 않고 🟡 로 보고한다.
#: **편 폴더를 넣는 이유**: `verify.py`·`build_kitcard.py` 는 브랜드에셋이 아니라
#: **편마다 하나씩** 있다. 1차 실행에서 둘 다 «레포에 없다»로 걸렸는데 거짓 경보였다.
SYMBOL_ROOTS = [
    os.environ.get("TOMANGCHI_SKILL_DIR",
                   r"C:\Users\ojaej\.claude\skills\tomangchi"),
    os.path.join(WORKSHOP, "00_브랜드에셋"),
    os.path.join(WORKSHOP, "01_발행완료"),
    CONTENT_OPS,
]

#: 발행로그 상태 → DB status
STATUS_MAP = {
    "발행": "published",
    "발행취소": "canceled",
    "제작완료": "produced",
    "제작중": "producing",
}


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _strip_md(cell: str) -> str:
    """표 셀에서 굵게·백틱 표시를 걷어낸다."""
    return cell.replace("**", "").replace("`", "").strip()


# ════════════════════════════════════════════════════════════════════
#  A. publish — 발행로그 × DB × 폴더
# ════════════════════════════════════════════════════════════════════
def parse_publish_log(text: str) -> dict:
    """`| **epNN** | …` 행만 뽑는다. «번호 미배정» 행은 대조 대상이 아니다
    (DB 는 번호가 있어야 레코드를 만든다) — 다만 개수는 세어 보고한다."""
    rows, unnumbered = {}, 0
    for line in text.split("\n"):
        if not line.startswith("|"):
            continue
        cells = line.strip().strip("|").split("|")
        if len(cells) < 7:
            continue
        head = _strip_md(cells[0])
        m = re.fullmatch(r"ep(\d+)", head)
        if not m:
            if "번호 미배정" in head:
                unnumbered += 1
            continue
        rows[int(m.group(1))] = {
            "상태": _strip_md(cells[2]),
            "발행일": _strip_md(cells[3]),
            "위치": _strip_md(cells[6]),
        }
    return {"rows": rows, "unnumbered": unnumbered}


def audit_publish(log_text: str, db_path: str, workshop: str) -> list:
    parsed = parse_publish_log(log_text)
    rows = parsed["rows"]
    findings = []

    if not rows:
        return [("🔴", "발행로그에서 ep 행을 하나도 못 읽었다 — 표 형식이 바뀌었나")]

    db_status = {}
    if os.path.exists(db_path):
        con = sqlite3.connect(db_path)
        try:
            db_status = {n: s for n, s in con.execute(
                "select number,status from episodes_episode")}
        finally:
            con.close()
    else:
        findings.append(("🔴", f"content-ops DB 를 못 찾았다: {db_path}"))

    for ep in sorted(rows):
        r = rows[ep]
        want = STATUS_MAP.get(r["상태"])

        # ① DB 레코드 존재 — ep15~17·ep25·ep26 이 여기서 걸렸어야 했다
        if db_status and ep not in db_status:
            findings.append(("🔴", f"ep{ep} DB 레코드 없음 (발행로그 상태: {r['상태']})"))
        # ② 상태 일치 — ep21·ep22 가 여기서 걸렸어야 했다
        elif want and ep in db_status and db_status[ep] != want:
            findings.append((
                "🔴",
                f"ep{ep} 상태 불일치 — 발행로그 «{r['상태']}» ≠ DB «{db_status[ep]}»"))

        # ③ 위치 칸의 경로가 실재하는가 (폴더명 추측 금지)
        loc = r["위치"]
        if loc and loc != "—":
            if not os.path.exists(os.path.join(workshop, loc.replace("/", os.sep))):
                findings.append(("🔴", f"ep{ep} «위치» 칸 경로가 없다: {loc}"))
            elif r["상태"] == "발행" and loc.startswith("02_제작중"):
                findings.append(("🟡", f"ep{ep} 발행인데 위치가 02_제작중이다: {loc}"))

        # ④ 발행인데 날짜가 없다
        if r["상태"] == "발행" and re.search(r"미확인|미상|^—?$", r["발행일"]):
            findings.append(("🟡", f"ep{ep} 발행인데 발행일이 «{r['발행일']}»"))

    if db_status:
        extra = sorted(set(db_status) - set(rows))
        for ep in extra:
            findings.append(("🔴", f"ep{ep} DB 에만 있고 발행로그 행이 없다"))

    findings.append(("⚪", f"대조 {len(rows)}편 · DB {len(db_status)}건 · "
                           f"번호 미배정 행 {parsed['unnumbered']}건(대조 밖)"))
    return findings


# ════════════════════════════════════════════════════════════════════
#  B. watch — 조건을 적었으면 감시처도 적었는가 (양식 검사)
# ════════════════════════════════════════════════════════════════════
#: «~되면 낸다» 류 조건 문형. 소재 문서에서 이게 보이면 감시처 선언을 요구한다.
COND_RE = re.compile(r"(출시되면|공개되면|열리면|나오면|되면\s|충족\s*시|재개 조건|성립 조건)")
#: 감시처를 선언한 것으로 인정하는 표지. 「어디서 보는가」가 적혀 있어야 한다.
WATCH_RE = re.compile(r"(감시처|감시표|감시 대상|걸리는 명단|제품 출시 감시|"
                      r"가격·정책 변경 감시|config\.md|감시 안 됨)")


def audit_watch(workshop: str, config_md: str) -> list:
    findings = []
    if not os.path.exists(config_md):
        findings.append(("🟡", f"감시표 정본을 못 찾았다: {config_md}"))

    targets = []
    for sub in ("03_소재큐", "03_보류", "02_제작중"):
        base = os.path.join(workshop, sub)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            # 폐기된 것은 조건이 이미 해제됐으므로 대조 대상이 아니다
            dirs[:] = [d for d in dirs if not d.startswith("_폐기")]
            if os.sep + "_폐기" in root:
                continue
            for f in files:
                if f.endswith(".md") and not f.startswith("_폐기"):
                    targets.append(os.path.join(root, f))

    if not targets:
        findings.append(("🟡", "조건을 볼 소재 문서를 하나도 못 찾았다"))
        return findings

    for path in sorted(targets):
        try:
            text = _read(path)
        except UnicodeDecodeError:
            findings.append(("🔴", f"UTF-8 로 안 읽힌다: {path}"))
            continue
        # 인용(>)·표 구분선은 조건 문형 판정에서 뺀다 — 규칙 설명문이 걸린다
        body = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith(">"))
        if COND_RE.search(body) and not WATCH_RE.search(body):
            rel = os.path.relpath(path, workshop)
            findings.append((
                "🔴",
                f"조건은 있는데 «감시처» 선언이 없다: {rel} "
                f"— 감시표에 등록했는지, 아니면 «감시 안 됨»인지 문서에 적어라"))

    findings.append(("⚪", f"소재 문서 {len(targets)}건 검사 (폐기분 제외)"))
    return findings


# ════════════════════════════════════════════════════════════════════
#  C. symbol — SKILL.md 가 부르는 코드가 실재하는가
# ════════════════════════════════════════════════════════════════════
#: 백틱 안에서 «코드 식별자»로 볼 것만 좁게 잡는다. 넓히면 거짓 경보가 쏟아지고,
#: 그러면 사람이 경보를 안 본다 — 위치 대조에서 배운 것과 같은 이유다.
CALL_RE = re.compile(r"`([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\(")   # mod.func(
FUNC_RE = re.compile(r"`([a-z_][a-z0-9_]{3,})\(\)`")                 # bare_func()
PYFILE_RE = re.compile(r"`([a-z_][a-z0-9_]*\.py)`")                  # some_file.py

#: 우리 코드가 아닌 것. 1차 실행에서 `imageio_ffmpeg.get_ffmpeg_exe()` 가 걸렸다 —
#: 남의 패키지 함수를 «레포에 없다»고 하면 그건 경보가 아니라 소음이다.
EXTERNAL_MODULES = {
    "imageio_ffmpeg", "os", "sys", "re", "json", "subprocess", "shutil",
    "pathlib", "datetime", "hashlib", "sqlite3", "yt_dlp", "requests",
    "PIL", "numpy", "np", "cv2",
}
#: «이건 실재하지 않는다»고 적은 문장에 등장한 이름은 부재가 곧 조문의 내용이다.
#: 1차 실행에서 `manychat_std.py` 가 걸렸는데, 그 줄은 v3.36.1 이 **없다고 기록한** 줄이었다.
ABSENT_MARK_RE = re.compile(r"(실재하지 않|존재하지 않|전수 0건|레포에 없|삭제|폐기|철회)")


def _grep_roots(needle: str, roots: list) -> bool:
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs
                       if d not in ("__pycache__", ".git", "venv", "node_modules")]
            for f in files:
                if not f.endswith(".py"):
                    continue
                try:
                    with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                        if needle in fh.read():
                            return True
                except (UnicodeDecodeError, OSError):
                    continue
    return False


def _file_exists(name: str, roots: list) -> bool:
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, _ in os.walk(root):
            dirs[:] = [d for d in dirs
                       if d not in ("__pycache__", ".git", "venv", "node_modules")]
            if os.path.exists(os.path.join(dirpath, name)):
                return True
    return False


def audit_symbol(skill_md: str, roots: list) -> list:
    findings = []
    missing_roots = [r for r in roots if not os.path.isdir(r)]
    for r in missing_roots:
        findings.append(("🟡", f"탐색 경로가 없다 (대조가 반쪽이 된다): {r}"))
    if not os.path.exists(skill_md):
        return findings + [("🔴", f"SKILL.md 를 못 찾았다: {skill_md}")]

    text = _read(skill_md)
    #: 이름별로 «부재를 적은 줄에서만 나왔는가»를 함께 본다.
    funcs, files = {}, {}

    def note(bag, name, line):
        bag.setdefault(name, []).append(line)

    lines = text.split("\n")
    # 부재 표시가 «다음 줄»에 있는 경우가 있다 — SKILL.md 757행이 여러 줄로 이어진
    # HTML 주석이고 이름은 첫 줄, 부재 문구는 뒷줄에 있었다.
    # ⚠️ 단순히 ±1 줄로 넓히면 **이웃 줄이 오염시킨다** — 부재 기록 바로 아래의 정상
    # 문장까지 «부재»로 읽혀 역검증이 깨졌다(실측). 그래서 창이 아니라
    # **주석 블록 단위**로 묶는다. 블록 밖은 그 줄 하나만 본다.
    ctx_of = list(lines)
    i = 0
    while i < len(lines):
        if "<!--" in lines[i] and "-->" not in lines[i]:
            j = i
            while j < len(lines) and "-->" not in lines[j]:
                j += 1
            block = "\n".join(lines[i:min(j + 1, len(lines))])
            for k in range(i, min(j + 1, len(lines))):
                ctx_of[k] = block
            i = j + 1
        else:
            i += 1

    for i, line in enumerate(lines):
        ctx = ctx_of[i]
        for mod, fn in CALL_RE.findall(line):
            if mod in EXTERNAL_MODULES:
                continue
            note(funcs, fn, ctx)
        for fn in FUNC_RE.findall(line):
            note(funcs, fn, ctx)
        for f in PYFILE_RE.findall(line):
            note(files, f, ctx)

    # 등장한 줄이 «전부» 부재 기록이면 대조 대상이 아니다
    funcs = {k: v for k, v in funcs.items()
             if not all(ABSENT_MARK_RE.search(l) for l in v)}
    files = {k: v for k, v in files.items()
             if not all(ABSENT_MARK_RE.search(l) for l in v)}

    for fn in sorted(funcs):
        if not _grep_roots(f"def {fn}", roots):
            findings.append(("🔴", f"조문이 부르는 함수가 레포에 없다: {fn}()"))
    for f in sorted(files):
        if not _file_exists(f, roots):
            findings.append(("🔴", f"조문이 가리키는 파일이 레포에 없다: {f}"))

    findings.append(("⚪", f"함수 {len(funcs)}개 · 파일 {len(files)}개 대조"))
    return findings


# ════════════════════════════════════════════════════════════════════
#  역검증 — 세 감사를 각각 따로 시험한다 (§0)
# ════════════════════════════════════════════════════════════════════
def selftest() -> int:
    import shutil
    import tempfile

    ok, fail = 0, 0

    def check(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  OK   {name}")
        else:
            fail += 1
            print(f"  FAIL {name}  {detail}")

    tmp = tempfile.mkdtemp(prefix="cons_audit_")
    try:
        # ── A. publish ────────────────────────────────────────────────
        ws = os.path.join(tmp, "ws")
        os.makedirs(os.path.join(ws, "01_발행완료", "ep1_정상"))
        db = os.path.join(tmp, "t.sqlite3")
        con = sqlite3.connect(db)
        con.execute("create table episodes_episode (number int, status text)")
        con.execute("insert into episodes_episode values (1,'published')")
        con.commit()
        con.close()

        head = ("| ep | 제목 | 상태 | 발행일 | 트리거 | 키트 | 위치 | 비고 |\n"
                "|---|---|---|---|---|---|---|---|\n")
        good = head + ("| **ep1** | 정상편 | **발행** | **2026-08-01** | — | — "
                       "| `01_발행완료/ep1_정상` | — |\n")
        res = audit_publish(good, db, ws)
        check("publish 정상 입력은 통과", not [f for f in res if f[0] != "⚪"],
              str([f for f in res if f[0] != "⚪"]))

        # ① DB 레코드 없음
        bad1 = good + ("| **ep9** | 레코드없음 | **발행** | **2026-08-02** | — | — "
                       "| `01_발행완료/ep1_정상` | — |\n")
        r1 = [f for f in audit_publish(bad1, db, ws) if f[0] == "🔴"]
        check("publish ① DB 레코드 없음이 걸린다",
              any("DB 레코드 없음" in m for _, m in r1), str(r1))

        # ② 상태 불일치 — 다른 검사가 같이 걸리지 않게 ep1 만 바꾼다
        bad2 = head + ("| **ep1** | 정상편 | **제작완료** | — | — | — "
                       "| `01_발행완료/ep1_정상` | — |\n")
        r2 = [f for f in audit_publish(bad2, db, ws) if f[0] == "🔴"]
        check("publish ② 상태 불일치가 «그것만» 걸린다",
              len(r2) == 1 and "상태 불일치" in r2[0][1], str(r2))

        # ③ 위치 칸 경로 없음
        bad3 = head + ("| **ep1** | 정상편 | **발행** | **2026-08-01** | — | — "
                       "| `01_발행완료/없는폴더` | — |\n")
        r3 = [f for f in audit_publish(bad3, db, ws) if f[0] == "🔴"]
        check("publish ③ 위치 칸 경로 없음이 «그것만» 걸린다",
              len(r3) == 1 and "경로가 없다" in r3[0][1], str(r3))

        # ── B. watch ──────────────────────────────────────────────────
        ws2 = os.path.join(tmp, "ws2", "03_소재큐")
        os.makedirs(ws2)
        cfg = os.path.join(tmp, "config.md")
        open(cfg, "w", encoding="utf-8").write("# 감시표\n")

        open(os.path.join(ws2, "감시처있음.md"), "w", encoding="utf-8").write(
            "출시되면 낸다.\n감시처: 제품 출시 감시 표에 등록했다.\n")
        r4 = [f for f in audit_watch(os.path.join(tmp, "ws2"), cfg) if f[0] == "🔴"]
        check("watch 감시처를 적은 문서는 통과", not r4, str(r4))

        open(os.path.join(ws2, "감시처없음.md"), "w", encoding="utf-8").write(
            "Seedance 2.5 가 출시되면 두드려봄으로 낸다.\n")
        r5 = [f for f in audit_watch(os.path.join(tmp, "ws2"), cfg) if f[0] == "🔴"]
        check("watch 조건만 있고 감시처 없으면 걸린다 (히기 재현)",
              len(r5) == 1 and "감시처" in r5[0][1], str(r5))

        # 폐기분은 대조 대상이 아니다
        dead = os.path.join(ws2, "_폐기")
        os.makedirs(dead)
        open(os.path.join(dead, "폐기건.md"), "w", encoding="utf-8").write(
            "출시되면 낸다.\n")
        r6 = [f for f in audit_watch(os.path.join(tmp, "ws2"), cfg) if f[0] == "🔴"]
        check("watch 폐기분은 대조에서 빠진다", len(r6) == 1, str(r6))

        # ── C. symbol ─────────────────────────────────────────────────
        root = os.path.join(tmp, "code")
        os.makedirs(root)
        open(os.path.join(root, "mod.py"), "w", encoding="utf-8").write(
            "def real_one():\n    pass\n")
        md_ok = os.path.join(tmp, "ok.md")
        open(md_ok, "w", encoding="utf-8").write("호출은 `mod.real_one(` 이다.\n")
        r7 = [f for f in audit_symbol(md_ok, [root]) if f[0] == "🔴"]
        check("symbol 실재하는 함수는 통과", not r7, str(r7))

        md_bad = os.path.join(tmp, "bad.md")
        open(md_bad, "w", encoding="utf-8").write("조회는 `scenes.find_scene(` 이다.\n")
        r8 = [f for f in audit_symbol(md_bad, [root]) if f[0] == "🔴"]
        check("symbol 없는 함수가 걸린다 (find_scene 재현)",
              len(r8) == 1 and "find_scene" in r8[0][1], str(r8))

        md_f = os.path.join(tmp, "f.md")
        open(md_f, "w", encoding="utf-8").write("스크립트는 `manychat_std.py` 다.\n")
        r9 = [f for f in audit_symbol(md_f, [root]) if f[0] == "🔴"]
        check("symbol 없는 파일이 걸린다 (manychat_std 재현)",
              len(r9) == 1 and "manychat_std.py" in r9[0][1], str(r9))

        # ── 1차 실물 실행에서 나온 거짓 경보 3종을 규칙으로 막았다. 그 규칙도 시험한다.
        md_x = os.path.join(tmp, "x.md")
        open(md_x, "w", encoding="utf-8").write(
            "ffmpeg 은 `imageio_ffmpeg.get_ffmpeg_exe()` 번들을 쓴다.\n")
        rA = [f for f in audit_symbol(md_x, [root]) if f[0] == "🔴"]
        check("symbol 외부 패키지 함수는 대조하지 않는다", not rA, str(rA))

        md_y = os.path.join(tmp, "y.md")
        open(md_y, "w", encoding="utf-8").write(
            "PR 원문의 `manychat_std.py` 는 워크숍·레포 어디에도 실재하지 않는다.\n")
        rB = [f for f in audit_symbol(md_y, [root]) if f[0] == "🔴"]
        check("symbol «실재하지 않는다»고 적은 줄은 대조하지 않는다", not rB, str(rB))

        # 역의 역검증 — 부재 기록이 «아닌» 줄이 하나라도 있으면 다시 걸려야 한다
        md_z = os.path.join(tmp, "z.md")
        open(md_z, "w", encoding="utf-8").write(
            "PR 원문의 `manychat_std.py` 는 실재하지 않는다.\n"
            "생성은 `manychat_std.py` 가 맡는다.\n")
        rC = [f for f in audit_symbol(md_z, [root]) if f[0] == "🔴"]
        check("symbol 부재 기록이 아닌 줄이 섞이면 다시 걸린다",
              len(rC) == 1 and "manychat_std.py" in rC[0][1], str(rC))

        # 주석 블록 — 이름은 첫 줄, 부재 문구는 뒷줄 (SKILL.md 757행 재현)
        md_c = os.path.join(tmp, "c.md")
        open(md_c, "w", encoding="utf-8").write(
            "<!-- PR 원문에는 `manychat_std.py`(정본 이전 예정)\n"
            "라고 적혀 있었으나 실재하지 않는다 -->\n")
        rD = [f for f in audit_symbol(md_c, [root]) if f[0] == "🔴"]
        check("symbol 여러 줄 주석의 부재 기록도 대조하지 않는다", not rD, str(rD))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n역검증 {ok} 통과 / {fail} 실패")
    return 0 if fail == 0 else 1


# ════════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(description="기록 일관성 감사 (read-only)")
    ap.add_argument("--only", choices=["publish", "watch", "symbol"],
                    help="한 감사만 돌린다")
    ap.add_argument("--selftest", action="store_true", help="역검증만 돌린다")
    ap.add_argument("--report", help="리포트를 쓸 경로 (없으면 표준출력만)")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    log_path = os.path.join(WORKSHOP, "발행로그.md")
    db_path = os.path.join(CONTENT_OPS, "db.sqlite3")

    sections = []
    if args.only in (None, "publish"):
        try:
            sections.append(("publish — 발행로그 × DB × 폴더",
                             audit_publish(_read(log_path), db_path, WORKSHOP)))
        except FileNotFoundError:
            sections.append(("publish — 발행로그 × DB × 폴더",
                             [("🔴", f"발행로그를 못 찾았다: {log_path}")]))
    if args.only in (None, "watch"):
        sections.append(("watch — 조건 × 감시처 선언", audit_watch(WORKSHOP, CONFIG_MD)))
    if args.only in (None, "symbol"):
        sections.append(("symbol — 조문 × 코드 실재", audit_symbol(SKILL_MD, SYMBOL_ROOTS)))

    red = sum(1 for _, fs in sections for lvl, _ in fs if lvl == "🔴")
    yellow = sum(1 for _, fs in sections for lvl, _ in fs if lvl == "🟡")

    lines = [f"# 기록 일관성 감사 — {datetime.now():%Y-%m-%d}", ""]
    lines += ["- 부서: 운영팀 / 등급: **A (read-only)**",
              f"- 실행: {datetime.now():%Y-%m-%d %H:%M}", ""]
    lines += ["## 결론", ""]
    if red:
        lines.append(f"**🔴 어긋남 {red}건.** 🟡 {yellow}건.")
    elif yellow:
        lines.append(f"**🟡 확인 필요 {yellow}건. 어긋남은 없다.**")
    else:
        lines.append("**⚪ 어긋남 없음. 세 축이 전부 일치한다.**")
    lines.append("")

    for title, fs in sections:
        lines += [f"## {title}", ""]
        for lvl, msg in fs:
            lines.append(f"- {lvl} {msg}")
        lines.append("")

    lines += ["## 이 감사가 못 보는 것", "",
              "- **인스타 실제 게시 여부.** 세 축은 전부 «우리 기록»끼리 맞춘다. "
              "셋이 다 «발행»으로 일치해도 실제로 안 올라갔으면 못 잡는다.",
              "- **감시처가 «맞는» 곳인지.** watch 는 선언이 있는지만 본다 — "
              "적힌 감시표에 실제로 등록됐는지까지는 안 본다.", ""]

    status = f"STATUS: FAIL 어긋남 {red}건" if red else "STATUS: OK"
    lines.append(status)
    out = "\n".join(lines)

    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8", newline="") as fh:
            fh.write(out)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
