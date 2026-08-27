# -*- coding: utf-8 -*-
"""텍스트 파일에 박힌 **보이지 않는 제어문자**를 찾는다 (2026-08-28).

**1차 진단이 틀렸다.** 「경로 이름이 뭉쳤다」가 아니라 **역슬래시 이스케이프가 실제 제어 바이트로
바뀌어 박혔다** — `scripts\\auth_check.py` 의 `\\a` 가 **BEL(0x07)** 이 됐다. 화면에는 안 보이니
`grep` 출력은 «scriptsuth_check.py» 처럼 뭉쳐 보이고, 파일에서 그 문자열을 찾으면 **안 나온다.**
이름으로 찾는 검사는 이걸 영원히 못 잡는다 — **바이트로 본다.**

§6 「백슬래시가 든 코드는 heredoc 으로 쓰지 않는다」가 가리키는 그 결함이고, 이번엔 정관 본문에서 났다.

    py scan_ctrl.py [레포경로]
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\ojaej\orca\jj-company"
EXTS = {".md", ".py", ".ps1", ".txt", ".json", ".jsonl", ".yml", ".yaml", ".html", ".css", ".js"}
SKIP = {".git", "node_modules", "__pycache__", "logs", "reports", ".venv"}
#: 줄바꿈·탭·캐리지리턴은 정상
OK_CTRL = {0x09, 0x0A, 0x0D}
NAME = {0x07: "BEL(\\a)", 0x08: "BS(\\b)", 0x0B: "VT(\\v)", 0x0C: "FF(\\f)", 0x00: "NUL(\\0)"}


def bad_chars(text):
    out = []
    for i, ch in enumerate(text):
        o = ord(ch)
        if o < 32 and o not in OK_CTRL:
            out.append((i, o))
    return out


# ── 역검증 — 일부러 넣은 제어문자가 잡히고, 정상 텍스트는 안 잡히는가 ──────
CASES = [
    ("scripts\x07uth_check.py", True,  "BEL 이 박힌 실제 사고 꼴"),
    ("logs\x07udit-data", True,  "같은 계열"),
    ("scripts\\auth_check.py", False, "온전한 역슬래시 경로 (반대쪽)"),
    ("줄바꿈\n탭\t는 정상", False, "정상 공백문자 (반대쪽)"),
    ("CRLF\r\n도 정상", False, "윈도 줄끝 (반대쪽)"),
]
fails = 0
print("── 역검증 ──")
for s, want, why in CASES:
    got = bool(bad_chars(s))
    mark = "OK  " if got == want else "FAIL"
    if got != want:
        fails += 1
    print("  %s 기대=%-5s 실제=%-5s  %s" % (mark, want, got, why))
if fails:
    raise SystemExit("역검증 실패 %d건 — 검사가 헛돈다" % fails)

print("\n── %s 훑기 ──" % ROOT)
hits = 0
for dirpath, dirnames, files in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP]
    for fn in files:
        if os.path.splitext(fn)[1].lower() not in EXTS:
            continue
        p = os.path.join(dirpath, fn)
        try:
            t = io.open(p, encoding="utf-8").read()
        except Exception:
            continue
        bad = bad_chars(t)
        if not bad:
            continue
        rel = os.path.relpath(p, ROOT)
        for i, o in bad:
            hits += 1
            line = t.count("\n", 0, i) + 1
            ctx = t[max(0, i - 18):i + 18].replace("\n", "\\n")
            print("  %s:%d  %s  …%s…" % (rel, line, NAME.get(o, hex(o)), ctx))
print("\n제어문자 %d건" % hits)
raise SystemExit(1 if hits else 0)
