# -*- coding: utf-8 -*-
r"""발행로그 «기록 시각» 칸 검사 (A등급 · 읽기 전용).

설계도 §2-3 ③ 「발행로그에 «기록 시각» 칸 — 즉시 기록 규칙의 검사 짝」의 그 검사다.

**왜 칸이 하나 더 필요한가.** 발행로그에는 `발행일` 이 있지만 그것은 «언제 나갔나»이고,
«언제 적었나»가 아니다. 둘이 같은 칸에 있으면 **사흘 뒤에 기억으로 적은 행과 발행 직후에
적은 행이 구별되지 않는다** — 그리고 기억으로 적은 값은 틀린다(2026-08-24 포트폴리오
28 vs 29 사고의 뿌리가 그것이다). 규칙은 이미 「발행 직후 즉시 기록」인데 **그 규칙을 재는
자가 없었다.** 정관 §0 «조문마다 검사 짝».

**칸 설치도 이 검사기가 뒷받침한다 (2026-08-31 §2 예외 5 개정).** 종전에는 표 머리를 고치는
것이 «기존 행 수정»이라 예외가 열어 주지 않았고 이 파일도 그렇게 적혀 있었다. 개정으로
**표 구조 변경이 열렸고, 그 «부여 조건»이 곧 `verify_structure`** 다 — 값 무손실을 기계로
증명해야 구조를 바꿀 수 있다. 칸이 아직 없으면 이 검사기는 **그 사실을 보고**한다(FAIL 이
아니다 — 없는 것을 실패로 적으면 진짜 실패가 묻힌다).

돌리기:  py scripts\publog_check.py
역검증:  py scripts\publog_check.py --self-test
구조검증: py scripts\publog_check.py --verify-structure <바꾸기 전> <바꾼 뒤>
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


def main_table(text):
    """**본 표만** 잘라 낸다 — `| ep | 제목 |` 머리글이 있는 표 하나.

    🔴 **발행로그에는 표가 넷 있다** (본 표 · 편수/게시물 수 · 규칙 변경 이력 · ep14 처리).
    전체 파이프 줄을 한 표로 읽으면 다른 표의 행이 본 표 행인 척 섞인다 — 지금은 그 셋이
    2~3칸이라 길이 가드에 걸려 우연히 빠지지만, **누가 4칸짜리 표를 하나 더 넣으면 조용히
    새어 든다.** 우연에 기대는 것은 검사가 아니다 (2026-08-31 실측으로 발견).

    🔴 **«파이프 줄이 끊기면 표 끝» 으로 자르면 안 된다 (2026-08-31 실측).** 이 표의 행은
    **줄바꿈을 품는다** — ep15 행의 비고가 네 줄에 걸쳐 있고 행 사이에 빈 줄도 있다.
    끊기는 자리에서 자르니 **63행 중 14행만** 읽혔고, 검사기는 그것을 «전부 봤다»는 얼굴로
    `STATUS: OK` 를 냈다. 덜 보는 검사가 통과를 내는 것이 가장 나쁜 꼴이다.

    그래서 **«다음 표가 시작될 때까지»** 로 자른다 — 경계는 **다음 구분선(`|---`)**이다.
    사이의 빈 줄·산문은 그냥 지나친다(파이프 줄이 아니라 어차피 안 걸린다).
    """
    lines = text.split("\n")
    start = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("| ep |") and "제목" in s:
            start = i
            break
    if start is None:
        return text
    end = len(lines) - 1
    for j in range(start + 2, len(lines)):        # 자기 구분선(start+1)은 건너뛴다
        if lines[j].strip().startswith("|---"):
            # 🔴 구분선 바로 위는 **다음 표의 머리글**이다 — 그것도 뺀다.
            #    안 빼면 `| 층 | 값 | 세는 법 |` 이 본 표의 행으로 들어와 상태 칸이
            #    「세는 법」으로 읽힌다(2026-08-31 실측: 38행 중 1행이 그것이었다).
            end = j - 2 if lines[j - 1].strip().startswith("|") else j - 1
            break
    return "\n".join(lines[start:end + 1])


def audit(text):
    """돌려주는 것은 `(설치됨, 결과행목록, 요약dict)`."""
    rows = split_rows(main_table(text))
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


# ── 표 구조 변경 검증 (정관 §2 예외 5 · 2026-08-31) ──────────────────────────
#
# 🔴 **이 함수가 예외 5의 «부여 조건» 자체다.** 조문이 「값 무손실을 기계로 증명해야
#    구조를 바꿀 수 있다」고 적었으므로, 증명이 없으면 그 동작은 예외 밖이다.
#    말로 «안 건드렸다» 고 적는 것은 증명이 아니다 (§0 «감지 장치가 값을 담는지»).
#
# **무엇을 재는가.** 「기존 모든 행의 모든 값이 그대로 있는가」다. 칸이 늘면 옛 행은
# 짧아진 채로 남는데(마크다운은 빈 칸으로 렌더한다), 그때도 **원래 있던 값들은 순서까지
# 같아야** 한다. 값의 «자리»가 아니라 «존재와 순서»를 보는 이유는, 칸을 중간에 끼워도
# 자리는 바뀌지만 값은 하나도 안 사라지기 때문이다.

def row_values(cells):
    """행에서 **값이 있는 칸**만 순서대로. 빈 칸은 «없는 것»이라 비교에서 뺀다."""
    return [c for c in cells if c.strip()]


def outside_rows(text):
    """**본 표 밖**에 있는 편 행(`| ep… |` 또는 `| **ep… |`)을 돌려준다.

    🔴 **이 함수가 축 ⑤ 다 (2026-08-31 신설).** 2026-08-30 에 ep39 두 행을 «append» 했는데
    그것이 **파일 끝**이었다 — 발행로그에는 표가 넷 있고 본 표는 앞쪽이라, 붙은 자리는
    마지막 표 **다음**이었다. 갱신 규칙 6이 「발행 여부 판정은 이 표로만 한다」인데
    **그 표에 ep39 가 없었고**, 검사기도 못 봤다(`발행 행 33`).

    그때 검증은 「두 행 실재 · 기존 본문 무변경 · 추가는 끝에만」 셋 다 참을 냈다 —
    **셋 다 참이었고 셋 다 엉뚱한 것을 쟀다.** 「파일 끝에 붙인다」와 「표에 붙인다」가
    다른 일인데 그것을 가르는 축이 없었다.
    """
    inside = set()
    for cells in split_rows(main_table(text))[1:]:
        if cells:
            inside.add(tuple(cells))
    out = []
    for cells in split_rows(text)[1:]:
        first = re.sub(r"[*` ]", "", cells[0]) if cells else ""
        if re.match(r"ep\d+", first) and tuple(cells) not in inside:
            out.append(cells)
    return out


def verify_structure(before, after, allow_move=False):
    """돌려주는 것은 `(무손실인가, 결과행목록)`.

    검사 축 다섯 — ① 머리글의 기존 칸이 하나도 사라지지 않았다 ②·②-1 칸은 늘기만 했고
    새 칸은 맨 뒤에만 ③ 행 수가 줄지 않았다 ④ 기존 행마다 값이 **전수 보존**됐다
    ⑤ **모든 편 행이 본 표 안에 있다**.

    🔴 **`allow_move=True` 는 «자리 정정» 회차 전용이다** (정관 §2 예외 5 조건 ④).
    행이 옮겨지면 ④ 의 «자리별 앞부분 일치» 가 성립할 수 없다 — 그래서 그때는
    **값 «집합» 보존**으로 바꿔 재고, 대신 **⑤ 가 나빠지지 않았는지**를 같이 본다.
    🔴 **집합 비교는 자리를 못 본다** — 그래서 ⑤ 없이 `allow_move` 를 쓰면
    «값은 다 있는데 여전히 표 밖» 인 상태가 통과한다. **둘은 짝이다.**
    """
    rb, ra = split_rows(before), split_rows(after)
    if not rb or not ra:
        return False, [("표", "FAIL", "표를 못 찾았다")]

    out = []
    okall = True
    hb, ha = rb[0], ra[0]

    lost = [c for c in hb if c not in ha]
    out.append(("① 머리글 칸 보존", "OK" if not lost else "FAIL",
                "%d칸 → %d칸" % (len(hb), len(ha))
                + ("" if not lost else " · 사라짐: %s" % lost)))
    okall &= not lost

    grew = len(ha) >= len(hb)
    out.append(("② 칸은 늘기만 했다", "OK" if grew else "FAIL",
                "%+d" % (len(ha) - len(hb))))
    okall &= grew

    # 🔴 **②-1 이 이 검사의 핵심이고, 처음엔 없어서 사고가 났다 (2026-08-31).**
    #    값이 하나도 안 사라져도 **칸을 가운데 끼우면 옛 행의 «뜻»이 밀린다.** 옛 행은
    #    물리적으로 8칸이라 5번째 칸이 새 머리글 5번(「기록 시각」) 아래로 렌더되는데
    #    그 값은 실제로 「트리거」다. 실측으로 잡혔다 — 가운데 끼워 설치한 뒤 검사기를
    #    돌리니 33행이 「기록 시각 시각 꼴이 아니다: **any word**(키워드 없음…)」로 FAIL
    #    했다. **값 보존은 참인데 뜻 보존이 거짓인 상태**였다.
    #
    #    §0 «감지 장치가 값을 담는지» 의 한 겹 안쪽이다 — 장치는 값을 담았고 그 값이
    #    참이었는데, **재는 대상이 틀렸다.** 그래서 축을 하나 더 둔다:
    #    **새 칸은 «맨 뒤에만» 붙인다.** 그러면 옛 행의 1~N번 칸이 그대로 1~N번 머리글에
    #    붙고, 없는 칸만 빈 칸으로 렌더된다.
    prefix = ha[:len(hb)] == hb
    out.append(("②-1 새 칸은 맨 뒤에만 (뜻 보존)", "OK" if prefix else "FAIL",
                "옛 머리글이 새 머리글의 앞부분이다" if prefix
                else "🔴 가운데 끼웠다 — 옛 행의 칸이 다른 머리글 아래로 밀린다: %s"
                     % (ha[:len(hb)])))
    okall &= prefix

    nb, na = len(rb) - 1, len(ra) - 1
    keep = na >= nb
    out.append(("③ 행 수가 줄지 않았다", "OK" if keep else "FAIL", "%d → %d" % (nb, na)))
    okall &= keep

    bad = []
    if allow_move:
        # 🔴 자리 정정 회차 — **값 «집합»** 으로 본다(자리가 바뀌므로 자리별 비교 불가).
        #    다중집합이라 «같은 값이 둘 있다가 하나로 줄었다» 도 잡힌다.
        import collections
        cb = collections.Counter(v for cells in rb[1:] for v in row_values(cells))
        ca = collections.Counter(v for cells in ra[1:] for v in row_values(cells))
        lost_v = cb - ca
        out.append(("④ 값 집합 보존 (이동 허용 모드)", "OK" if not lost_v else "FAIL",
                    "값 %d개 전부 남음" % sum(cb.values()) if not lost_v
                    else "사라진 값 %d개 · 예: %s"
                         % (sum(lost_v.values()), list(lost_v)[0][:40])))
        okall &= not lost_v
    else:
        for i, cells in enumerate(rb[1:]):
            want = row_values(cells)
            got = row_values(ra[1 + i]) if 1 + i < len(ra) else []
            # 🔴 «부분집합» 이 아니라 «앞부분 일치» 로 본다. 부분집합이면 값을 하나 지우고
            #    다른 값을 더해도 통과할 수 있다 — 그것은 무손실이 아니라 교체다.
            if got[:len(want)] != want:
                bad.append((i + 1, want, got))
        out.append(("④ 기존 행 값 전수 보존", "OK" if not bad else "FAIL",
                    "%d행 전부 일치" % nb if not bad
                    else "어긋난 행 %d개 · 첫 번째=%d행" % (len(bad), bad[0][0])))
        okall &= not bad
        for i, want, got in bad[:3]:
            out.append(("   · %d행" % i, "FAIL", "전 %s → 후 %s" % (want[:4], got[:4])))

    ob, oa = outside_rows(before), outside_rows(after)
    better = len(oa) <= len(ob) and (len(oa) == 0 or not allow_move)
    out.append(("⑤ 편 행이 본 표 안에 있다", "OK" if better else "FAIL",
                "표 밖 %d → %d" % (len(ob), len(oa))
                + ("" if better else " · 🔴 자리 정정 회차인데 표 밖이 남았다")))
    okall &= better
    for cells in oa[:3]:
        out.append(("   · 표 밖", "FAIL", re.sub(r"[*` ]", "", cells[0])[:20]))
    return okall, out


def _selftest_structure():
    """역검증 — 🔴 **걸려야 하는 넷과 통과해야 하는 셋을 분리한다.**

    한쪽만 보면 «전부 FAIL 하는 검사»도 정상으로 보인다 (정관 §0).
    """
    H = "| ep | 제목 | 상태 | 발행일 |"
    S = "|---|---|---|---|"
    R1 = "| ep1 | 가 | 발행 | 2026-08-01 10:00 KST |"
    R2 = "| ep2 | 나 | 발행 | 2026-08-02 10:00 KST |"
    BEFORE = "\n".join([H, S, R1, R2])

    H2 = "| ep | 제목 | 상태 | 발행일 | 기록 시각 |"
    S2 = "|---|---|---|---|---|"
    NEWROW = "| ep3 | 다 | 발행 | 2026-08-03 10:00 KST | 2026-08-03 11:00 KST |"

    cases = [
        ("맨 뒤에 칸을 붙였다 (정당한 구조 변경)", "\n".join([H2, S2, R1, R2]), True),
        ("칸 늘리고 새 행도 붙였다", "\n".join([H2, S2, R1, R2, NEWROW]), True),
        # 🔴 **이 케이스는 종전에 `True` 로 적혀 있었고 그것이 사고였다 (2026-08-31).**
        #    값은 하나도 안 사라지므로 «무손실» 은 참인데, 옛 행의 칸이 다른 머리글 아래로
        #    밀려 **뜻이 바뀐다.** 실측으로 33행이 오판정됐다. 기대값을 False 로 뒤집는다.
        ("🔴 칸을 가운데 끼웠다 (값은 남지만 뜻이 밀린다)",
         "\n".join(["| ep | 기록 시각 | 제목 | 상태 | 발행일 |", S2, R1, R2]), False),
        ("맨 뒤 칸 둘을 한 번에 붙였다 (반대쪽 — 여러 칸도 통과)",
         "\n".join(["| ep | 제목 | 상태 | 발행일 | 기록 시각 | 메모 |",
                    "|---|---|---|---|---|---|", R1, R2]), True),
        ("🔴 칸 이름을 바꿨다 (개명은 값이 사라지는 것과 같다)",
         "\n".join(["| ep | 제목 | 상황 | 발행일 | 기록 시각 |", S2, R1, R2]), False),
        ("🔴 행을 하나 지웠다", "\n".join([H2, S2, R1]), False),
        ("🔴 값을 하나 고쳤다",
         "\n".join([H2, S2, R1, "| ep2 | 다른제목 | 발행 | 2026-08-02 10:00 KST |"]), False),
        ("🔴 칸을 하나 지웠다",
         "\n".join(["| ep | 제목 | 상태 |", "|---|---|---|",
                    "| ep1 | 가 | 발행 |", "| ep2 | 나 | 발행 |"]), False),
        ("🔴 값을 지우고 다른 값을 더했다 (교체)",
         "\n".join([H2, S2, R1, "| ep2 | 발행 | 2026-08-02 10:00 KST | 새값 |"]), False),
    ]
    bad = 0

    # ── 축 ⑤ · 이동 모드 역검증 (2026-08-31 신설) ──────────────────────────
    # 🔴 **걸려야 하는 쪽부터 만든다.** 표 밖에 붙은 행이 실제로 걸리는지 먼저 보고,
    #    그 다음에 «정정하면 통과한다» 를 붙인다 (L-009).
    OTHER = "\n".join(["", "## 다른 표", "",
                       "| 층 | 값 | 세는 법 |", "|---|---|---|",
                       "| 편수 | 35편 | 발행 인 행 |"])
    BASE5 = "\n".join([H2, S2, R1, R2]) + OTHER
    R3 = "| ep3 | 다 | 발행 | 2026-08-03 10:00 KST | 2026-08-03 11:00 KST |"
    STRAY = BASE5 + "\n" + R3
    FIXED = "\n".join([H2, S2, R1, R2, R3]) + OTHER

    def case5(label, cond, detail=""):
        nonlocal_bad[0] += 0 if cond else 1
        print("  %s %-52s %s" % ("OK  " if cond else "FAIL", label, detail))

    nonlocal_bad = [0]
    print("[R] 역검증 — 축 ⑤ 표 밖 행 (걸려야 하는 쪽 먼저)")
    n_stray = len(outside_rows(STRAY))
    case5("🔴 표 밖에 붙은 편 행이 잡힌다 (2026-08-30 사고 재현)",
          n_stray == 1, "표 밖 %d행" % n_stray)
    case5("본 표 안의 행은 표 밖으로 세지 않는다 (반대쪽)",
          len(outside_rows(FIXED)) == 0, "표 밖 %d행" % len(outside_rows(FIXED)))
    case5("다른 표의 행은 «편 행» 이 아니라 세지 않는다",
          len(outside_rows(BASE5)) == 0, "표 밖 %d행" % len(outside_rows(BASE5)))
    case5("🔴 표 밖에 붙이면 구조 검사가 FAIL 한다",
          verify_structure(BASE5, STRAY)[0] is False)
    case5("표 밖 행을 본 표로 옮기면 통과한다 (이동 모드)",
          verify_structure(STRAY, FIXED, allow_move=True)[0] is True)
    case5("🔴 옮기지 않고 이동 모드만 켜면 통과하지 않는다",
          verify_structure(STRAY, STRAY, allow_move=True)[0] is False,
          "집합 보존만으로는 부족 — 축 ⑤ 가 짝이다")
    case5("🔴 이동 모드에서도 값이 사라지면 FAIL 한다",
          verify_structure(STRAY, "\n".join([H2, S2, R1]) + OTHER,
                           allow_move=True)[0] is False)
    case5("이동 모드는 순서만 바뀐 것을 통과시킨다 (값 집합이 같다)",
          verify_structure(BASE5, "\n".join([H2, S2, R2, R1]) + OTHER,
                           allow_move=True)[0] is True)
    bad += nonlocal_bad[0]
    print("[R] 역검증 — 구조 변경 값 무손실")
    for label, after, want in cases:
        got, _ = verify_structure(BEFORE, after)
        ok = got == want
        bad += 0 if ok else 1
        print("  %s %-40s 무손실=%-5s (기대 %s)"
              % ("OK  " if ok else "FAIL", label, got, want))
    return bad


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

    print("[R] \uc5ed\uac80\uc99d \u2014 \ubcf8 \ud45c\ub9cc \uc77d\ub294\uac00 (\ud45c\uac00 \uc5ec\ub7ec\uac1c\uc778 \ud30c\uc77c)")
    MULTI = "\n".join([
        "# \uba38\ub9ac\ub9d0", "",
        H_NEW, SEP, row("ep40", "\ubc1c\ud589", "2026-08-30 10:00 KST",
                        "2026-08-30 10:30 KST"), "",
        "## \ub2e4\ub978 \ud45c", "",
        "| \uce35 | \uac12 | \uc138\ub294 \ubc95 | \ub137\uc9f8 | \ub2e4\uc12f\uc9f8 | \uc5ec\uc12f\uc9f8 |",
        "|---|---|---|---|---|---|",
        "| \ud3b8\uc218 | 35\ud3b8 | \ubc1c\ud589 \uc778 \ud589 | \ubc1c\ud589 | \uc544\ubb34\uac70\ub098 | \ub610 |"])
    _, res, _ = audit(MULTI)
    case("\ub2e4\ub978 \ud45c\uc758 \ud589\uc774 \uc11e\uc774\uc9c0 \uc54a\ub294\ub2e4 (\ubcf8 \ud45c 1\ud589\ub9cc)",
         len(res) == 1 and res[0][0] == "ep40", "\ub300\uc0c1 %d\uac74" % len(res))
    _, res2, _ = audit("\n".join([H_NEW, SEP,
                                  row("ep40", "\ubc1c\ud589", "2026-08-30 10:00 KST",
                                      "2026-08-30 10:30 KST")]))
    case("\ud45c\uac00 \ud558\ub098\ubfd0\uc774\uc5b4\ub3c4 \uadf8\ub300\ub85c \uc77d\ub294\ub2e4 (\ubc18\ub300\ucabd)",
         len(res2) == 1)
    LEAK = "\n".join([
        H_NEW, SEP, row("ep40", "\ubc1c\ud589", "2026-08-30 10:00 KST",
                        "2026-08-30 10:30 KST"), "",
        "| \uce35 | \uac12 | \ubc1c\ud589 | \ub137\uc9f8 | \ub2e4\uc12f\uc9f8 |",
        "|---|---|---|---|---|",
        "| \ud3b8\uc218 | 35 | \ubc1c\ud589 | x | y |"])
    _, res3, _ = audit(LEAK)
    case("\ub2e4\uc74c \ud45c\uc758 \uba38\ub9ac\uae00\uc774 \uc0c8\uc9c0 \uc54a\ub294\ub2e4 (3\ubc88\uc9f8 \uce78\uc774 \u00ab\ubc1c\ud589\u00bb \uc778 \ud45c)",
         len(res3) == 1 and res3[0][0] == "ep40",
         "\ub300\uc0c1 %d\uac74 %s" % (len(res3), [r[0] for r in res3]))


    print("[R] \uc5ed\uac80\uc99d — \uc2dc\uac04\ub300 \ud658\uc0b0")
    a, _ = parse_ts("2026-08-30 01:38 KST")
    b, _ = parse_ts("2026-08-29T16:38+00:00")
    case("KST 01:38 = UTC 16:38 (ep39 \ub8e8\ud2b8 \uc2e4\uce21)", a == b, "%s == %s" % (a, b))

    bad += _selftest_structure()

    print()
    print("STATUS: %s" % ("OK" if not bad else "FAIL self-test %d\uac74" % bad))
    return 0 if not bad else 1


def _run_verify_structure(argv):
    """`--verify-structure <\uc804> <\ud6c4>` \u2014 \uc815\uad00 \u00a72 \uc608\uc678 5 \uc758 \u00ab\uac12 \ubb34\uc190\uc2e4 \uae30\uacc4 \uc99d\uba85\u00bb."""
    try:
        i = argv.index("--verify-structure")
        b_path, a_path = argv[i + 1], argv[i + 2]
    except (ValueError, IndexError):
        print("  FAIL \uc4f0\ub294 \ubc95: --verify-structure <\ubc14\uafb8\uae30 \uc804 \ud30c\uc77c> <\ubc14\uafbc \ub4a4 \ud30c\uc77c>")
        print("\nSTATUS: FAIL usage")
        return 1
    before = io.open(b_path, encoding="utf-8").read()
    after = io.open(a_path, encoding="utf-8").read()
    print("# \ud45c \uad6c\uc870 \ubcc0\uacbd \u2014 \uac12 \ubb34\uc190\uc2e4 \uac80\uc99d (\uc815\uad00 \u00a72 \uc608\uc678 5)")
    print("  \uc804: %s" % b_path)
    print("  \ud6c4: %s" % a_path)
    print()
    mv = "--allow-move" in argv
    if mv:
        print("  🔴 이동 허용 모드 — ④ 를 «값 집합 보존» 으로 재고, ⑤ 가 0 이어야 한다")
        print()
    okall, rows = verify_structure(before, after, allow_move=mv)
    for label, verdict, why in rows:
        print("  %-4s %-24s %s" % (verdict, label, why))
    print()
    # \ud83d\udd34 \ud310\uc815\ub9cc \ub0b4\uace0 \ub05d\ub0b4\uc9c0 \uc54a\ub294\ub2e4 \u2014 \uc774 \uac80\uc0ac\uae30 \uc790\uc2e0\uc774 \ud5db\ub3c4\ub294\uc9c0 \uac19\uc774 \ubcf8\ub2e4.
    #    \u00ab\uc804\ubd80 OK \ub97c \ub0b4\ub294 \uac80\uc0ac\u00bb \ub3c4 \uc5ec\uae30\uc11c\ub294 \uc815\uc0c1\uc73c\ub85c \ubcf4\uc774\uae30 \ub54c\ubb38\uc774\ub2e4 (\uc815\uad00 \u00a70).
    rbad = _selftest_structure()
    print()
    if okall and not rbad:
        print("STATUS: OK")
        return 0
    print("STATUS: FAIL %s" % ("\uac12 \uc190\uc2e4" if not okall else "\uc5ed\uac80\uc99d %d\uac74" % rbad))
    return 1


def main():
    if "--self-test" in sys.argv:
        return _self_test()
    if "--verify-structure" in sys.argv:
        return _run_verify_structure(sys.argv)
    if not os.path.exists(PUBLOG):
        print("  FAIL \ubc1c\ud589\ub85c\uadf8\ub97c \ubabb \ucc3e\uc558\ub2e4: %s" % PUBLOG)
        print("\nSTATUS: FAIL no-publog")
        return 1
    text = io.open(PUBLOG, encoding="utf-8").read()
    print("# \ubc1c\ud589\ub85c\uadf8 «\uae30\ub85d \uc2dc\uac01» \uac80\uc0ac")
    print("  %s" % PUBLOG)
    print()
    # 🔴 **축 ⑤ 를 본 검사에도 건다 (2026-08-31).** 구조 검증 때만 보면, 평소 실행은
    #    «표 안의 행» 만 세면서 `STATUS: OK` 를 낸다 — 표 밖에 행이 있어도 조용하다.
    #    실제로 2026-08-30~31 사이 이 검사기는 ep39 두 행을 못 본 채 OK 를 냈다.
    stray = outside_rows(text)
    if stray:
        print("  FAIL ⑤ 본 표 밖에 편 행이 있다 — %d개: %s"
              % (len(stray), ", ".join(re.sub(r"[*` ]", "", c[0])[:16] for c in stray[:4])))
        print("       갱신 규칙 6 은 «발행 여부 판정은 이 표로만» 이다 — 표 밖 행은 "
              "판정에 안 들어간다. 정정: --verify-structure … --allow-move (정관 §2 예외 5 ④)")
        print()
    else:
        print("  OK   ⑤ 편 행이 전부 본 표 안에 있다")
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
    # \ud83d\udd34 **\ucd95 \u2464 \ub97c STATUS \uc5d0 \ubc18\uc601\ud55c\ub2e4.** \ud654\uba74\uc5d0 FAIL \uc744 \ucc0d\uc5b4 \ub193\uace0 `STATUS: OK` \ub97c \ub0b4\uba74
    #    \uae30\uacc4\ub85c \uc77d\ub294 \ucabd\uc740 \ud1b5\uacfc\ub85c \ubc1b\ub294\ub2e4 \u2014 \uac80\uc0ac\uac00 \uc7a1\uc740 \uac83\uc744 \uc885\uacb0\ubd80\uac00 \ubc84\ub9ac\ub294 \uad6c\uc870\ub2e4
    #    (\uac8c\uc774\ud2b8\uac00 `[P]` \uc5d0\uc11c \uacaa\uc740 \uac83\uacfc \uac19\uc740 \uaf34).
    why = []
    if n["FAIL"]:
        why.append("\uae30\ub85d\uc2dc\uac01 %d\uac74" % n["FAIL"])
    if stray:
        why.append("\ud45c\ubc16\ud589 %d\uac74" % len(stray))
    if not why:
        print("STATUS: OK")
        return 0
    print("STATUS: FAIL publog %s" % " \u00b7 ".join(why))
    return 1


if __name__ == "__main__":
    sys.exit(main())
