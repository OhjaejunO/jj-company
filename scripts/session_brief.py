# -*- coding: utf-8 -*-
r"""세션 시작 브리핑 — «아무도 안 읽는 🔴» 을 세션 첫 줄로 올린다 (A등급 · read-only).

## 왜

2026-09-12 실측: `run_audit` 이 `RUNS_VERDICT=RED` 를 **사흘 연속** 아침 리포트에
실었고, `reports\intents\` 에 진단 초안이 **나흘치** 쌓여 있었다. 아무도 안 읽었다 —
`skill-drift-audit` 은 나흘째 🔴, `blog-writer` 는 사흘째 `report-missing` 이었다.

**리포트를 더 쓰는 것으로는 이 결함이 안 닫힌다.** 읽는 자리가 리포트 밖에 없어서
생긴 일이라, 사람과 세션이 **반드시 지나가는 자리**(세션 시작)에 올린다.
정관 §0 4층에서 ③(검사)이 아니라 **①(구조)** 에 앉히는 자리다.

## 재는 것

  1. **미처리 intent** — `reports\intents\*.md` 중 «JJ 판정» 칸의 `- [x]` 가 0개인 것.
     그 체크박스는 `intent_from_audit.py` 가 이미 만들어 두고 아무도 쓰지 않던 자리다.
     **새 표식을 만들지 않는다** — 만들면 그것도 아무도 안 적는다.
  2. **오늘·어제 스케줄 회차** — `run_audit.py` 를 그대로 부른다(KEY=value 계약).
     같은 판정을 두 벌 구현하면 갈린다(정관 §0 «두 벌이면 갈린다»).

## 🔴 못 잡는 것 (§0 4층 ④)

  - **intent 가 안 만들어진 실패**는 못 본다 — 그것은 아침 래퍼가 돌았을 때만 생긴다.
    그래서 2번(회차 직접 조회)을 같이 둔다. 둘이 겹치는 것은 결함이 아니라 대조군이다.
  - **«복구함» 에 체크만 하고 안 고친 경우**는 못 잡는다. 사람 자리다.
  - 지난 이틀 밖의 회차는 안 본다 — 오래된 실패는 intent 쪽이 든다(기본 14일).

사용: `py scripts\session_brief.py` · 역검증 `--self-test`
"""
import argparse
import datetime
import glob
import io
import os
import re
import subprocess
import sys

HQ = os.environ.get("JJ_HQ", r"C:\Users\ojaej\jj-company")
INTENT_DIR = os.path.join(HQ, "reports", "intents")
RUN_AUDIT = os.path.join(HQ, "scripts", "run_audit.py")
INTENT_DAYS = 14
MAX_LINES = 12          # 브리핑이 길면 그것도 안 읽힌다

_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def intent_open(path):
    """그 intent 가 아직 «미처리»인가 — «JJ 판정» 칸에 `- [x]` 가 하나도 없으면."""
    try:
        text = io.open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    return "- [x]" not in text.lower()


def intent_what(path):
    """«무엇이» 표의 첫 칸들을 짧게 — `FAIL skill-drift-audit · FAIL blog-writer`."""
    try:
        text = io.open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""
    seen = []
    for ln in text.splitlines():
        cols = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cols) >= 4 and cols[0].isdigit():
            tag = "%s %s" % (cols[1], cols[2])
            if tag not in seen:
                seen.append(tag)
    return " · ".join(seen[:4]) + (" …" if len(seen) > 4 else "")


def open_intents(dirpath=None, days=INTENT_DAYS, today=None):
    """[(파일명, 요약)] — 최근 `days` 일 안의 미처리 intent, 새것부터."""
    dirpath = dirpath or INTENT_DIR
    today = today or datetime.date.today()
    out = []
    for p in sorted(glob.glob(os.path.join(dirpath, "*.md")), reverse=True):
        m = _DATE.search(os.path.basename(p))
        if not m:
            continue
        try:
            d = datetime.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if (today - d).days > days or (today - d).days < 0:
            continue
        if intent_open(p):
            out.append((os.path.basename(p), intent_what(p)))
    return out


def runs_verdict(argv=None):
    """`run_audit.py` 를 그대로 부른다 — `(verdict, [사유줄])`. 못 부르면 `(None, [사유])`."""
    try:
        p = subprocess.run([sys.executable, RUN_AUDIT] + list(argv or []),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
    except Exception as e:                      # noqa: BLE001
        return None, ["run_audit 실행 불가: %s" % type(e).__name__]
    kv = {}
    for ln in (p.stdout or "").splitlines():
        k, _, v = ln.partition("=")
        if _:
            kv[k.strip()] = v.strip()
    why = []
    for key, label in (("RUNS_FAILED", "실패"), ("RUNS_INCOMPLETE", "무기록 종료"),
                       ("STARTED_RESIDUAL", "잔존 스탬프")):
        val = kv.get(key, "NONE")
        if val and val != "NONE":
            why.append("%s: %s" % (label, val))
    return kv.get("RUNS_VERDICT"), why


def brief(dirpath=None, days=INTENT_DAYS, today=None, run_argv=None, want_runs=True):
    """세션 첫 줄에 올릴 글. **깨끗하면 빈 문자열** — 조용할 때 조용한 것이 조건이다."""
    lines = []
    verdict, why = (None, []) if not want_runs else runs_verdict(run_argv)
    if verdict == "RED":
        lines.append("- 🔴 **스케줄 회차 RED** (오늘·어제) — " + " / ".join(why))
    items = open_intents(dirpath, days, today)
    if items:
        lines.append("- 🔴 **미처리 intent %d건** (`reports\\intents\\`) — "
                     "«JJ 판정» 칸이 비어 있다:" % len(items))
        for name, what in items[:MAX_LINES - 2]:
            lines.append("  - `%s` — %s" % (name, what or "내용 요약 없음"))
        if len(items) > MAX_LINES - 2:
            lines.append("  - … 그 밖 %d건" % (len(items) - (MAX_LINES - 2)))
    if not lines:
        return ""
    return ("[session-brief] 🔴 아직 안 읽힌 것이 있다 (A등급 조회 · "
            "`py scripts\\session_brief.py`)\n" + "\n".join(lines) +
            "\n\n> 고쳤으면 intent 파일의 «JJ 판정» 칸에 `- [x]` 를 찍는다 — "
            "그 표식이 이 브리핑을 끄는 유일한 자리다.")


# ── 역검증 (§0) ─────────────────────────────────────────────────────────────
# **케이스를 분리한다.** 스케줄 축(`run_audit`)은 `want_runs=False` 로 꺼 두고 intent
# 축만 재고, 스케줄 축은 자기 케이스에서 따로 잰다 — 한 입력이 둘 다 걸리면 «어느 축이
# 잡았는지» 가 증명되지 않는다.
_HEAD = "# intent — 2026-09-12 아침 감사 🔴\n\n## 무엇이\n\n| # | 종류 | 작업 | 날짜 | 사유 |\n|---|---|---|---|---|\n| 1 | FAIL | blog-writer | 2026-09-12 | report-missing |\n\n## JJ 판정\n\n"
_OPEN = _HEAD + "- [ ] 복구함 (명령 · 시각)\n"
_DONE = _HEAD + "- [x] 복구함 (2026-09-12 13:00)\n"


def self_test():
    import tempfile
    today = datetime.date(2026, 9, 12)
    res = []
    with tempfile.TemporaryDirectory(prefix="brief_") as d:
        def put(name, body):
            io.open(os.path.join(d, name), "w", encoding="utf-8").write(body)

        # ① 아무것도 없으면 조용하다 — «늘 뜨는 브리핑» 은 안 읽힌다
        res.append(("빈 폴더는 조용", brief(d, today=today, want_runs=False) == ""))
        # ② 미처리 intent 는 뜬다
        put("2026-09-12_blog-writer.md", _OPEN)
        b = brief(d, today=today, want_runs=False)
        res.append(("미처리 intent 를 올린다", "2026-09-12_blog-writer.md" in b
                    and "FAIL blog-writer" in b))
        # ③ 체크한 intent 는 안 뜬다 (헛돎 점검 — 잡는 쪽만 보면 «전부 잡는» 판정기도 정상)
        put("2026-09-12_blog-writer.md", _DONE)
        res.append(("- [x] 찍힌 intent 는 조용", brief(d, today=today, want_runs=False) == ""))
        # ④ 기한 밖(15일 전)은 안 뜬다
        put("2026-08-20_old.md", _OPEN)
        res.append(("기한 밖 intent 는 조용", brief(d, today=today, want_runs=False) == ""))
        # ⑤ 날짜 없는 파일 이름은 건너뛴다 (죽지 않는다)
        put("notes.md", _OPEN)
        res.append(("날짜 없는 파일에 안 죽는다", brief(d, today=today, want_runs=False) == ""))

    # ⑥⑦ 스케줄 축 — 합성 로그로 `run_audit` 을 직접 먹인다. **양방향이다.**
    with tempfile.TemporaryDirectory(prefix="brief_runs_") as ld:
        day = datetime.date.today().strftime("%Y%m%d")
        good = os.path.join(ld, "blog-writer_%s.log" % day)
        io.open(good, "w", encoding="utf-8").write(
            "[2026-09-12 09:00:00] === blog-writer start ===\n"
            "[2026-09-12 09:10:00] STATUS: OK\n")
        argv = ["--log-dir", ld, "--stamp-dir", ld, "--tasks", "blog-writer"]
        v, _w = runs_verdict(argv)
        res.append(("정상 회차는 OK", v == "OK"))
        io.open(good, "a", encoding="utf-8").write(
            "[2026-09-12 09:20:00] === blog-writer start ===\n"
            "[2026-09-12 09:30:00] STATUS: FAIL report-missing\n")
        v, w = runs_verdict(argv)
        res.append(("실패 회차는 RED + 사유", v == "RED" and any("report-missing" in x for x in w)))

    fails = 0
    for name, ok in res:
        fails += not ok
        print(("ok   " if ok else "FAIL ") + name)
    print("STATUS: %s" % ("OK" if not fails else "FAIL %d" % fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    text = brief()
    print(text if text else "조용하다 — 미처리 intent 없음, 오늘·어제 회차 정상.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
