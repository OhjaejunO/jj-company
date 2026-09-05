# -*- coding: utf-8 -*-
r"""study_watch — C:\공부 의 새 노트·바뀐 노트를 결정적으로 잡는다 (study-scout 의 래퍼 선실행).

WHAT
  *.md 를 재귀로 훑어 sha1·크기를 logs\study-data\seen.json 과 대조 →
  logs\study-data\new_<날짜>.txt 에 «NEW|경로|바이트» / «CHANGED|경로|바이트» 한 줄씩. 마지막 줄 STUDY_NEW=<n>.
  --mark : 지금 상태를 seen.json 에 적는다 — 래퍼가 **에이전트 회차가 성공한 뒤에만** 부른다.
           (실패한 회차의 노트는 다음 주에 다시 «새것» 으로 보인다 — 조용히 넘어가지 않는다)
USAGE
  py scripts\study_watch.py [--root C:\공부] [--date …] [--out …] [--seen …] [--mark] [--self-test]
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import sys

ROOT = r"C:\공부"
HQ = r"C:\Users\ojaej\jj-company"


def scan(root):
    files = {}
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith(".md"):
                continue
            p = os.path.join(dp, f)
            try:
                b = io.open(p, "rb").read()
            except OSError:
                continue
            files[p] = {"sha": hashlib.sha1(b).hexdigest(), "bytes": len(b)}
    return files


def diff(now, seen):
    rows = []
    for p, v in sorted(now.items()):
        old = seen.get(p)
        if old is None:
            rows.append("NEW|%s|%d" % (p, v["bytes"]))
        elif old.get("sha") != v["sha"]:
            rows.append("CHANGED|%s|%d" % (p, v["bytes"]))
    return rows


def main(a):
    seen = json.load(io.open(a.seen, encoding="utf-8")) if os.path.exists(a.seen) else {}
    now = scan(a.root)
    if a.mark:
        os.makedirs(os.path.dirname(a.seen), exist_ok=True)
        json.dump(now, io.open(a.seen, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        print("MARKED=%d" % len(now))
        return 0
    rows = diff(now, seen)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    io.open(a.out, "w", encoding="utf-8").write("\n".join(rows + ["STUDY_NEW=%d" % len(rows)]) + "\n")
    for r in rows:
        print(r)
    print("STUDY_NEW=%d" % len(rows))
    return 0


def self_test():
    import tempfile
    root = tempfile.mkdtemp(prefix="study_")
    notes = os.path.join(root, "notes"); os.makedirs(os.path.join(notes, "sub"))
    io.open(os.path.join(notes, "a.md"), "w", encoding="utf-8").write("a")
    io.open(os.path.join(notes, "sub", "b.md"), "w", encoding="utf-8").write("b")
    io.open(os.path.join(notes, "x.base"), "w", encoding="utf-8").write("ignored")
    seen = os.path.join(root, "seen.json"); out = os.path.join(root, "new.txt")
    A = argparse.Namespace(root=notes, seen=seen, out=out, mark=False)
    buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
    try:
        main(A); first = buf.getvalue()
        main(argparse.Namespace(root=notes, seen=seen, out=out, mark=True))
        buf.truncate(0); buf.seek(0); main(A); second = buf.getvalue()
        io.open(os.path.join(notes, "a.md"), "w", encoding="utf-8").write("a2")
        io.open(os.path.join(notes, "c.md"), "w", encoding="utf-8").write("c")
        buf.truncate(0); buf.seek(0); main(A); third = buf.getvalue()
    finally:
        sys.stdout = old
    c1 = "STUDY_NEW=2" in first and "NEW|" in first and ".base" not in first
    c2 = "STUDY_NEW=0" in second
    c3 = "STUDY_NEW=2" in third and "CHANGED|" in third and "c.md" in third
    for n, v in (("첫 스캔: md 2건 NEW, .base 제외", c1), ("mark 뒤 재스캔 0건", c2), ("수정 1 + 신규 1 → CHANGED·NEW", c3)):
        print(("PASS " if v else "FAIL ") + n)
    ok = c1 and c2 and c3
    print("STATUS: " + ("OK" if ok else "FAIL selftest"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--out")
    ap.add_argument("--seen", default=os.path.join(HQ, "logs", "study-data", "seen.json"))
    ap.add_argument("--mark", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    a.out = a.out or os.path.join(HQ, "logs", "study-data", "new_%s.txt" % a.date)
    raise SystemExit(main(a))
