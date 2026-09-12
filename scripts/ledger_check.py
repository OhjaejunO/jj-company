# -*- coding: utf-8 -*-
r"""ledger_check.py — 지적 원장(docs\correction-ledger.md) 검사기.

정관 §0 «JJ 의 «고쳐라»는 그 회차 안에 자리를 얻는다» 의 장치.
원장의 각 행이 ① 처리 값이 4층 안에 있고 ② 자리(`경로#표식`)의 파일과 표식이 실재하며
③ 재발 칸이 앞선 행을 가리키고 ④ **미룬 것이 닫혔으면 «해소» 칸이 그 자리를 가리키는지** 잰다.
재는 값은 «**해소 안 된** 재발 행 수» — 0 으로 가야 한다.

    py scripts\ledger_check.py              # 원장 검사 → STATUS 줄
    py scripts\ledger_check.py --self-test  # 역검증 11건 + 정상 1건

## 🔴 «해소» 칸이 왜 생겼는가 (2026-09-12)

처리 칸은 **그 회차의 판단**이다. 그런데 미룬 것(«백로그»)이 나중에 닫혀도 **돌아와 적는 자리가
없었다** — 그래서 2026-09-12 실측에서 백로그 3항(C-25·C-48·C-54)이 **이미 닫혔는데** 원장 5행이
여전히 그것을 «백로그» 로 가리키고 있었다. C-25 는 조건을 채운 지 이틀이 지나 있었다.
재발 38 이라는 값이 **실제보다 부풀어** 있었고, 그 숫자로는 «무엇이 아직 안 고쳐졌는가» 를 알 수 없었다.

🔴 **처리 칸을 고치지 않는다** — 그러면 기록이 개작된다(정관 §2 5번과 같은 정신). 칸을 **맨 뒤에**
하나 더 두고, 닫힌 뒤 앉은 자리를 거기 적는다. 이 검사기는 **둘이 갈리는 순간**을 잡는다:
백로그 항목에 «🟢 … 닫힘» 이 섰는데 원장의 해소 칸이 비어 있으면 FAIL.

🔴 못 잡는 것 (정관 §0 4층 ④):
- 지적이 원장에 «적혔는가». 검사기는 적힌 행만 본다.
- 백로그 항목이 «실제로» 닫혔는가. 재는 것은 **닫혔다고 적혔는가**이고, 그 판정은 사람이 한다.
- 🔴 **닫는 조건이 아직 실행 가능한가.** C-45 의 조건은 «ep51·ep52 빌더를 정리한다» 였는데 두 편이
  발행되며 `01_발행완료` 로 가 정관 §2 로 **고칠 수 없게 됐다** — 조건이 죽었는데 아무도 돌아오지
  않았다. 그런 조건을 기계가 가려내지는 못한다.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "correction-ledger.md"
BACKLOG = ROOT / "docs" / "clause-backlog.md"
LAYERS = ("기본값", "생성", "검사", "백로그", "못잡음")
NCOL = 8  # | # | 날짜 | 편 | 지적 | 처리 | 자리 | 재발 | 해소 |


def parse(text):
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != NCOL or not cells[0].isdigit():
            continue  # 머리글·구분선·다른 표
        rows.append(dict(zip(
            ("no", "date", "ep", "note", "layer", "place", "repeat", "resolved"), cells)))
    return rows


def resolve(place):
    path, _, anchor = place.partition("#")
    p = Path(os.path.expanduser(path.replace("\\", "/")))
    if not p.is_absolute():
        p = ROOT / p
    return p, anchor


def closed(text):
    """백로그에서 «🟢 … 닫힘» 이 선 항목 번호. **적힌 것을 읽을 뿐 판정하지 않는다.**"""
    out, cur = set(), None
    for ln in text.splitlines():
        m = re.match(r"^#{2,4}\s+(C-[\w-]+)", ln)
        if m:
            cur = m.group(1)
        elif cur and "\U0001F7E2" in ln and "닫힘" in ln:
            out.add(cur)
    return out


def place_problem(tag, place, what):
    """`경로#표식` 이 실재하는가. 자리와 해소가 **같은 규칙**을 쓴다 — 두 벌이면 갈린다."""
    if "#" not in place:
        return f"{tag}: {what}는 `경로#표식` 꼴이어야 한다 `{place}`"
    p, anchor = resolve(place)
    if re.fullmatch(r"build_ep\d+\.py", p.name):
        return f"{tag}: 편 한정 파일은 {what}가 아니다 {p}"
    if not p.is_file():
        return f"{tag}: {what} 파일 없음 {p}"
    if anchor not in p.read_text("utf-8", errors="replace"):
        return f"{tag}: 표식 `{anchor}` 이 {p.name} 에 없다"
    return None


def check(rows, shut=None):
    shut = closed(BACKLOG.read_text("utf-8", errors="replace")) if shut is None else shut
    fails = []
    seen = set()
    for r in rows:
        tag = f"행 {r['no']}"
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"]):
            fails.append(f"{tag}: 날짜 꼴 아님 `{r['date']}`")
        if r["layer"] not in LAYERS:
            fails.append(f"{tag}: 처리 `{r['layer']}` 는 4층 밖 (허용: {' · '.join(LAYERS)})")
        if r["layer"] == "못잡음":
            if not r["place"] or r["place"] == "—":
                fails.append(f"{tag}: 못잡음이면 자리에 «왜 못 잡는지»를 적는다")
        else:
            bad = place_problem(tag, r["place"], "자리")
            if bad:
                fails.append(bad)
        # ── 해소 칸 (2026-09-12) ────────────────────────────────────────────
        # 🔴 **미룬 것이 닫혔는데 원장이 안 따라가는 자리**를 잡는다. 종전에는 그 갈림을
        #    아무도 안 봤고, 그래서 이미 닫힌 안건이 며칠씩 «백로그» 로 남아 재발 수를 부풀렸다.
        got = r.get("resolved", "—")
        if got != "—":
            if r["layer"] != "백로그":
                fails.append(f"{tag}: 해소는 «백로그» 행에만 적는다 — 처리가 `{r['layer']}` 면 자리가 이미 있다")
            else:
                bad = place_problem(tag, got, "해소")
                if bad:
                    fails.append(bad)
        elif r["layer"] == "백로그":
            m = re.search(r"clause-backlog\.md#(C-[\w-]+)", r["place"])
            if m and m.group(1) in shut:
                fails.append(f"{tag}: {m.group(1)} 는 닫혔는데 해소 칸이 비었다 — 닫힌 뒤 앉은 자리를 적는다")
        if r["repeat"] != "—":
            m = re.fullmatch(r"#(\d+)", r["repeat"])
            if not m or m.group(1) not in seen:
                fails.append(f"{tag}: 재발 `{r['repeat']}` 는 앞선 행 번호(#n)여야 한다")
        seen.add(r["no"])
    return fails


def run(text):
    rows = parse(text)
    fails = check(rows)
    # 🔴 재는 값은 «**해소 안 된** 재발» 이다 — 닫힌 뒤에도 세면 그 숫자는 실제를 안 가리킨다.
    live = [r for r in rows if r["repeat"] != "—" and r.get("resolved", "—") == "—"]
    done = sum(1 for r in rows if r.get("resolved", "—") != "—")
    for f in fails:
        print("FAIL", f)
    print(f"rows={len(rows)} 재발(미해소)={len(live)} 해소={done} "
          + " ".join(f"{l}={sum(1 for r in rows if r['layer']==l)}" for l in LAYERS))
    return fails


HEAD = ("| # | 날짜 | 편 | 지적 | 처리 | 자리 | 재발 | 해소 |\n"
        "|---|---|---|---|---|---|---|---|\n")

#: 역검증용 «닫힘» 주입. 🔴 **실재하는 항목 번호**를 쓴다 — 없는 번호를 쓰면 «자리 표식 없음» 이
#: 같이 걸려 **이 축이 제 몫을 했는지** 를 알 수 없다(정관 §0 «역검증 케이스는 분리한다»).
#: C-42 는 백로그에 실재하고 실제로는 **열려 있다** — 닫힘은 여기서만 주입한다.
SHUT = {"C-42"}


def self_test():
    me = Path(__file__).resolve()
    good = HEAD + (f"| 1 | 2026-09-06 | ep0 | 정상 | 검사 | {me}#def check | — | — |\n"
                   f"| 2 | 2026-09-06 | ep0 | 정상2 | 못잡음 | 취향이라 기계로 못 잰다 | #1 | — |\n")
    assert not check(parse(good), SHUT), "정상 행이 걸렸다"
    # 가짜 표식은 실행 시 조립한다 — 글자 그대로 적으면 이 소스 안에 있어서 «있음»으로 읽힌다(첫 실행에서 실제로 그랬다)
    ghost = "zz".join(["없는", "표식"])
    bl = "docs/clause-backlog.md"
    with tempfile.TemporaryDirectory() as tmp:
        epfile = Path(tmp) / "build_ep42.py"
        epfile.write_text("BANNED = []\n", encoding="utf-8")
        bad = {
            "4층 밖 처리": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 메모리 | {me}#def check | — | — |\n",
            "표식 없음": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 검사 | {me}#{ghost} | — | — |\n",
            "파일 없음": HEAD + "| 1 | 2026-09-06 | ep0 | x | 생성 | docs/없는파일.md#a | — | — |\n",
            "재발 앞 참조": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 검사 | {me}#def check | #2 | — |\n",
            "못잡음 사유 없음": HEAD + "| 1 | 2026-09-06 | ep0 | x | 못잡음 | — | — | — |\n",
            "편 한정 파일": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 검사 | {epfile}#BANNED = | — | — |\n",
            # ── 해소 축 (2026-09-12) ────────────────────────────────────────
            # 🔴 이 셋이 이번 회차의 자리다 — 닫힌 안건이 «백로그» 로 남아 재발 수를 부풀리던 것.
            "닫혔는데 해소 빔": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 백로그 | {bl}#C-42 | — | — |\n",
            "해소 표식 없음": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 백로그 | {bl}#C-42 | — | {me}#{ghost} |\n",
            "백로그 아닌데 해소": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 검사 | {me}#def check | — | {me}#def parse |\n",
        }
        for name, text in bad.items():
            fails = check(parse(text), SHUT)
            assert len(fails) == 1, f"{name}: 걸려야 하는데 {fails}"
            print("ok  ", name, "→", fails[0])

        # 🔴 **반대쪽** — 한쪽만 보면 «전부 요구하는 검사» 도 정상으로 보인다(정관 §0 역검증).
        ok_cases = {
            "닫힌 항목 + 해소 채움 → 통과":
                HEAD + f"| 1 | 2026-09-06 | ep0 | x | 백로그 | {bl}#C-42 | — | {me}#def check |\n",
            "열린 항목 + 해소 빔 → 통과 (아직 미룬 것을 다그치지 않는다)":
                HEAD + f"| 1 | 2026-09-06 | ep0 | x | 백로그 | {bl}#C-24 | — | — |\n",
        }
        for name, text in ok_cases.items():
            fails = check(parse(text), SHUT)
            assert not fails, f"{name}: 통과해야 하는데 {fails}"
            print("ok  ", name)

    # 🔴 «닫힘» 을 읽는 자 자신도 양방향으로 본다 — 표기가 없으면 닫혔다고 하지 않는다.
    src = ("## C-1 — 가\n- 본문\n"
           "## C-2 — 나\n- \U0001F7E2 2026-09-12 닫힘. 근거\n"
           "## C-3 — 다\n- \U0001F7E2 진행 중이라는 뜻의 초록\n")
    assert closed(src) == {"C-2"}, closed(src)
    print("ok   닫힘 표기를 읽는다 — «🟢» 만으로는 닫힘이 아니다 (C-2 만)")
    print("ok   정상 2행 통과")
    print("STATUS: OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--self-test" in sys.argv:
        self_test()
        sys.exit(0)
    fails = run(LEDGER.read_text("utf-8"))
    print("STATUS: OK" if not fails else f"STATUS: FAIL {len(fails)}건")
    sys.exit(1 if fails else 0)
