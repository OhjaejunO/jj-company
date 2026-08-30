# -*- coding: utf-8 -*-
r"""발행로그 «기록 시각» 칸 검사 (A등급 · 읽기 전용).

설계도 §2-3 ③ 「발행로그에 «기록 시각» 칸 — 즉시 기록 규칙의 검사 짝」의 그 검사다.

**왜 칸이 하나 더 필요한가.** 발행로그에는 `발행일` 이 있지만 그것은 «언제 나갔나»이고,
«언제 적었나»가 아니다. 둘이 같은 칸에 있으면 **사흘 뒤에 기억으로 적은 행과 발행 직후에
적은 행이 구별되지 않는다** — 그리고 기억으로 적은 값은 틀린다(2026-08-24 포트폴리오
28 vs 29 사고의 뿌리가 그것이다). 규칙은 이미 「발행 직후 즉시 기록」인데 **그 규칙을 재는
자가 없었다.** 정관 §0 «조문마다 검사 짝».

🔴 **이 검사기는 칸을 만들지 않는다.** 표 머리를 고치는 것은 «기존 행 수정»이라
**정관 §2 예외 5번이 열어 주지 않는다**(예외 5는 `append` 만이다). 칸 설치는 사람 손이고,
이 검사기는 **칸이 없으면 그 사실을 보고**한다 — 없는 것을 FAIL 로 적으면 진짜 실패가 묻힌다.

돌리기:  py scripts\publog_check.py
역검증:  py scripts\publog_check.py --self-test
"""
import datetime as dt
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PUBLOG = os.environ.get(
    "TOMANGCHI_PUBLOG",
    "C:\\Users\\ojaej\\orca\\tomangchi-lab.github.io\\workshop\\\ubc1c\ud589\ub85c\uadf8.md")

COL = "\uae30\ub85d \uc2dc\uac01"          # 「기록 시각」
STATE_PUB = "\ubc1c\ud589"                  # 「발행」

# 「2026-08-30 16:55 KST」 · 「2026-08-30T16:55+09:00」 둘 다 받는다.
TS = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?\s*"
    r"(KST|UTC|[+-]\d{2}:?\d{2})?")

WARN_HOURS = 2.0     # 이보다 늦으면 🟡 — 「즉시」가 아니다
FAIL_HOURS = 24.0    # 이보다 늦으면 🔴 — 기억으로 적은 것이다


def parse_ts(text):
    """표 칸 하나에서 시각을 꺼낸다. 돌려주는 것은 `(datetime|None, 사유)`."""
    m = TS.search(text or "")
    if not m:
        return None, "시각 꼴이 아니다"
    y, mo, d, h, mi, s, zone = m.groups()
    if not zone:
        # 🔴 시간대 무표기는 통과시키지 않는다. Threads API 는 UTC 로 주고 우리는 KST 로
        #    적는다 — 오프셋이 없으면 아홉 시간이 조용히 어긋난다(2026-08-30 실측).
        return None, "\uc2dc\uac04\ub300 \ubb34\ud45c\uae30"
    off = dt.timedelta(hours=9) if zone == "KST" else (
        dt.timedelta(0) if zone == "UTC" else None)
    if off is None:
        sign = -1 if zone[0] == "-" else 1
        z = zone[1:].replace(":", "")
        off = sign * dt.timedelta(hours=int(z[:2]), minutes=int(z[2:]))
    return dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0),
                       tzinfo=dt.timezone(off)), ""


def split_rows(text):
    """표의 «| … |» 줄만 칸 리스트로. 구분선(`|---|`)은 뺀다."""
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = [c.strip() for c in s[1:-1].split("|")]
        if cells and all(set(c) <= set("-: ") and c for c in cells):
            continue
        out.append(cells)
    return out


def audit(text):
    """돌려주는 것은 `(설치됨, 결과행목록, 요약dict)`."""
    rows = split_rows(text)
    if not rows:
        return False, [], {"reason": "\ud45c\uac00 \uc5c6\ub2e4"}
    head = rows[0]
    if COL not in head:
        return False, [], {"reason": "\uce78 \ubbf8\uc124\uce58", "head": head}

    i_col = head.index(COL)
    i_ep = 0
    i_state = head.index("\uc0c1\ud0dc") if "\uc0c1\ud0dc" in head else 2
    i_date = head.index("\ubc1c\ud589\uc77c") if "\ubc1c\ud589\uc77c" in head else 3

    results = []
    for cells in rows[1:]:
        if len(cells) <= max(i_state, i_date):
            continue
        state = re.sub(r"[*` ]", "", cells[i_state])
        if state != STATE_PUB:
            continue
        ep = re.sub(r"[*` ]", "", cells[i_ep])
        rec_raw = cells[i_col] if len(cells) > i_col else ""
        if not rec_raw.strip():
            results.append((ep, "NA", "\uce78\uc774 \ube44\uc5c8\ub2e4 (\uce78 \uc124\uce58 \uc774\uc804 \ud589)"))
            continue
        pub, why_p = parse_ts(cells[i_date])
        rec, why_r = parse_ts(rec_raw)
        if rec is None:
            results.append((ep, "FAIL", "\uae30\ub85d \uc2dc\uac01 %s: %s" % (why_r, rec_raw[:30])))
            continue
        if pub is None:
            results.append((ep, "WARN", "\ubc1c\ud589\uc77c\uc744 \ubabb \uc77d\uc5b4 \uc9c0\uc5f0\uc744 \ubabb \uc7ac\ub2e4: %s" % why_p))
            continue
        gap = (rec - pub).total_seconds() / 3600.0
        if gap < 0:
            results.append((ep, "FAIL", "\uae30\ub85d\uc774 \ubc1c\ud589\ubcf4\ub2e4 \uc55e\uc120\ub2e4 (%.1f\uc2dc\uac04)" % gap))
        elif gap > FAIL_HOURS:
            results.append((ep, "FAIL", "\uc9c0\uc5f0 %.1f\uc2dc\uac04 — \uae30\uc5b5\uc73c\ub85c \uc801\uc740 \uac12\uc774\ub2e4" % gap))
        elif gap > WARN_HOURS:
            results.append((ep, "WARN", "\uc9c0\uc5f0 %.1f\uc2dc\uac04 — «\uc989\uc2dc»\uac00 \uc544\ub2c8\ub2e4" % gap))
        else:
            results.append((ep, "OK", "\uc9c0\uc5f0 %.1f\uc2dc\uac04" % gap))
    return True, results, {"rows": len(rows) - 1}


PROPOSAL = """\
## 「기록 시각」 칸 설치 문안 (사람 손 · 2줄)

표 머리 두 줄을 아래로 바꾼다. **기존 행은 건드리지 않는다** — 칸이 하나 는 옛 행은
빈 칸으로 렌더되고, 그것이 맞다(설치 이전은 «못 잰 것»이다 · 소급 불가).

  | ep | 제목 | 상태 | 발행일 | 기록 시각 | 트리거 | 키트 | 위치 | 비고 |
  |---|---|---|---|---|---|---|---|---|

갱신 규칙에 한 줄을 더한다:

  8. **`발행`으로 바꾼 그 자리에서 「기록 시각」에 지금 시각을 적는다** (오프셋 필수 —
     `2026-08-30 17:40 KST`). 🔴 발행일은 «언제 나갔나»이고 기록 시각은 «언제 적었나»다.
     둘이 벌어진 폭이 곧 이 표를 믿을 수 있는 정도다. 검사: `scripts\\publog_check.py`

🔴 **왜 사람 손인가**: 표 머리 수정은 «기존 내용 수정»이라 정관 §2 예외 5번(append 전용)이
열어 주지 않는다. 에이전트가 못 하는 것을 못 한다고 적는 자리다(§0 4층 ④).
"""


def _self_test():
    """역검증 — 케이스마다 조건을 **하나씩만** 바꾼다 (정관 §0).

    한쪽만 보면 «전부 FAIL 하는 검사»도 정상으로 보이므로 **통과해야 하는 쪽**을 같이 둔다.
    """
    H_NEW = "| ep | \uc81c\ubaa9 | \uc0c1\ud0dc | \ubc1c\ud589\uc77c | \uae30\ub85d \uc2dc\uac01 | \ube44\uace0 |"
    SEP = "|---|---|---|---|---|---|"
    H_OLD = "| ep | \uc81c\ubaa9 | \uc0c1\ud0dc | \ubc1c\ud589\uc77c | \ube44\uace0 |"
    SEP5 = "|---|---|---|---|---|"

    def tbl(head, sep, *rows):
        return "\n".join([head, sep] + list(rows))

    def row(ep, state, pub, rec):
        return "| %s | \uc81c\ubaa9 | %s | %s | %s | — |" % (ep, state, pub, rec)

    bad = 0

    def case(label, cond, detail=""):
        nonlocal bad
        bad += 0 if cond else 1
        print("  %s %-52s %s" % ("OK  " if cond else "FAIL", label, detail))

    print("[R] \uc5ed\uac80\uc99d — \uce78 \uc124\uce58 \uac10\uc9c0")
    inst, _, meta = audit(tbl(H_OLD, SEP5, "| ep1 | \uc81c\ubaa9 | \ubc1c\ud589 | 2026-08-01 10:00 KST | — |"))
    case("\uce78\uc774 \uc5c6\ub294 \ud45c\ub97c «\ubbf8\uc124\uce58»\ub85c \ubcf4\uace0\ud55c\ub2e4 (FAIL \uc544\ub2c8\ub2e4)",
         inst is False and meta.get("reason") == "\uce78 \ubbf8\uc124\uce58")
    inst, _, _ = audit(tbl(H_NEW, SEP, row("ep40", "\ubc1c\ud589", "2026-08-30 10:00 KST",
                                           "2026-08-30 10:30 KST")))
    case("\uce78\uc774 \uc788\ub294 \ud45c\ub294 \uc124\uce58\ub85c \ubcf8\ub2e4 (\ubc18\ub300\ucabd)", inst is True)

    print("[R] \uc5ed\uac80\uc99d — \uc9c0\uc5f0 \ud310\uc815 (\uc870\uac74 \ud558\ub098\uc529\ub9cc \ubc14\uafc8)")
    for rec, want, why in [
            ("2026-08-30 10:30 KST", "OK", "30\ubd84 — \uc989\uc2dc"),
            ("2026-08-30 13:30 KST", "WARN", "3.5\uc2dc\uac04 — \uc989\uc2dc \uc544\ub2c8\ub2e4"),
            ("2026-09-02 10:00 KST", "FAIL", "\uc0ac\ud758 \ub4a4 — \uae30\uc5b5\uc73c\ub85c \uc801\uc740 \uac12"),
            ("2026-08-30 09:00 KST", "FAIL", "\ubc1c\ud589\ubcf4\ub2e4 \uc55e\uc120\ub2e4"),
            ("2026-08-30 10:30", "FAIL", "\uc2dc\uac04\ub300 \ubb34\ud45c\uae30"),
            ("\uc801\uc74c", "FAIL", "\uc2dc\uac01 \uaf34\uc774 \uc544\ub2c8\ub2e4")]:
        _, res, _ = audit(tbl(H_NEW, SEP, row("ep40", "\ubc1c\ud589", "2026-08-30 10:00 KST", rec)))
        got = res[0][1] if res else "(\ud589 \uc5c6\uc74c)"
        case("«%s» → %s" % (rec, want), got == want, "%s · %s" % (got, why))

    print("[R] \uc5ed\uac80\uc99d — \ubc94\uc704")
    _, res, _ = audit(tbl(H_NEW, SEP, row("ep40", "\uc81c\uc791\uc911", "—", "")))
    case("\ubbf8\ubc1c\ud589 \ud589\uc740 \ub300\uc0c1\uc774 \uc544\ub2c8\ub2e4 (\uc804\ubd80 \uac78\ub9ac\ub294 \uac80\uc0ac\uac00 \uc544\ub2d8)",
         res == [], "\ub300\uc0c1 %d\uac74" % len(res))
    _, res, _ = audit(tbl(H_NEW, SEP, row("ep1", "\ubc1c\ud589", "2026-08-01 10:00 KST", "")))
    case("\uce78 \uc124\uce58 \uc774\uc804 \ud589\uc740 NA \ub2e4 (\uc18c\uae09 FAIL \uc544\ub2c8\ub2e4)",
         res and res[0][1] == "NA", res[0][1] if res else "")
    _, res, _ = audit(tbl(H_NEW, SEP,
                          row("ep40", "\ubc1c\ud589", "2026-08-30 10:00 KST", "2026-08-30 10:30 KST"),
                          row("ep41", "\ubc1c\ud589", "2026-08-30 11:00 KST", "2026-09-05 11:00 KST")))
    case("\ud589\uc774 \uc5ec\ub7ec\uac1c\uba74 \uc804\ubd80 \ubcf8\ub2e4", len(res) == 2 and res[1][1] == "FAIL",
         "%d\uac74" % len(res))

    print("[R] \uc5ed\uac80\uc99d — \uc2dc\uac04\ub300 \ud658\uc0b0")
    a, _ = parse_ts("2026-08-30 01:38 KST")
    b, _ = parse_ts("2026-08-29T16:38+00:00")
    case("KST 01:38 = UTC 16:38 (ep39 \ub8e8\ud2b8 \uc2e4\uce21)", a == b, "%s == %s" % (a, b))

    print()
    print("STATUS: %s" % ("OK" if not bad else "FAIL self-test %d\uac74" % bad))
    return 0 if not bad else 1


def main():
    if "--self-test" in sys.argv:
        return _self_test()
    if not os.path.exists(PUBLOG):
        print("  FAIL \ubc1c\ud589\ub85c\uadf8\ub97c \ubabb \ucc3e\uc558\ub2e4: %s" % PUBLOG)
        print("\nSTATUS: FAIL no-publog")
        return 1
    text = io.open(PUBLOG, encoding="utf-8").read()
    print("# \ubc1c\ud589\ub85c\uadf8 «\uae30\ub85d \uc2dc\uac01» \uac80\uc0ac")
    print("  %s" % PUBLOG)
    print()
    inst, res, meta = audit(text)
    if not inst:
        print("  N/A  \uce78\uc774 \uc5c6\ub2e4 — %s" % meta.get("reason"))
        print("       \ud604\uc7ac \uce78: %s" % " | ".join(meta.get("head", [])))
        print()
        print(PROPOSAL)
        print("STATUS: OK (\ubd80\ubd84: \uce78 \ubbf8\uc124\uce58 — \uc0ac\ub78c \uc190)")
        return 0
    n = {"OK": 0, "WARN": 0, "FAIL": 0, "NA": 0}
    for ep, verdict, why in res:
        n[verdict] += 1
        print("  %-4s %-16s %s" % (verdict, ep, why))
    print()
    print("  \ubc1c\ud589 \ud589 %d — OK %d · WARN %d · FAIL %d · NA %d"
          % (len(res), n["OK"], n["WARN"], n["FAIL"], n["NA"]))
    print()
    print("STATUS: %s" % ("OK" if not n["FAIL"] else "FAIL publog %d\uac74" % n["FAIL"]))
    return 0 if not n["FAIL"] else 1


if __name__ == "__main__":
    sys.exit(main())
