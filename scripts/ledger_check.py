# -*- coding: utf-8 -*-
r"""ledger_check.py — 지적 원장(docs\correction-ledger.md) 검사기.

정관 §0 «JJ 의 «고쳐라»는 그 회차 안에 자리를 얻는다» 의 장치.
원장의 각 행이 ① 처리 값이 4층 안에 있고 ② 자리(`경로#표식`)의 파일과 표식이 실재하며
③ 재발 칸이 앞선 행을 가리키는지 잰다. 재는 값은 «재발 행 수» — 0 으로 가야 한다.

    py scripts\ledger_check.py              # 원장 검사 → STATUS 줄
    py scripts\ledger_check.py --self-test  # 역검증 4건 + 정상 1건

🔴 못 잡는 것: 지적이 원장에 «적혔는가». 검사기는 적힌 행만 본다(정관 §0 4층 ④).
"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "correction-ledger.md"
LAYERS = ("기본값", "생성", "검사", "백로그", "못잡음")
NCOL = 7  # | # | 날짜 | 편 | 지적 | 처리 | 자리 | 재발 |


def parse(text):
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != NCOL or not cells[0].isdigit():
            continue  # 머리글·구분선·다른 표
        rows.append(dict(zip(("no", "date", "ep", "note", "layer", "place", "repeat"), cells)))
    return rows


def resolve(place):
    path, _, anchor = place.partition("#")
    p = Path(os.path.expanduser(path.replace("\\", "/")))
    if not p.is_absolute():
        p = ROOT / p
    return p, anchor


def check(rows):
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
            if "#" not in r["place"]:
                fails.append(f"{tag}: 자리는 `경로#표식` 꼴이어야 한다 `{r['place']}`")
            else:
                p, anchor = resolve(r["place"])
                if not p.is_file():
                    fails.append(f"{tag}: 자리 파일 없음 {p}")
                elif anchor not in p.read_text("utf-8", errors="replace"):
                    fails.append(f"{tag}: 표식 `{anchor}` 이 {p.name} 에 없다")
        if r["repeat"] != "—":
            m = re.fullmatch(r"#(\d+)", r["repeat"])
            if not m or m.group(1) not in seen:
                fails.append(f"{tag}: 재발 `{r['repeat']}` 는 앞선 행 번호(#n)여야 한다")
        seen.add(r["no"])
    return fails


def run(text):
    rows = parse(text)
    fails = check(rows)
    repeats = sum(1 for r in rows if r["repeat"] != "—")
    for f in fails:
        print("FAIL", f)
    print(f"rows={len(rows)} 재발={repeats} " + " ".join(f"{l}={sum(1 for r in rows if r['layer']==l)}" for l in LAYERS))
    return fails


HEAD = "| # | 날짜 | 편 | 지적 | 처리 | 자리 | 재발 |\n|---|---|---|---|---|---|---|\n"


def self_test():
    me = Path(__file__).resolve()
    good = HEAD + f"| 1 | 2026-09-06 | ep0 | 정상 | 검사 | {me}#def check | — |\n| 2 | 2026-09-06 | ep0 | 정상2 | 못잡음 | 취향이라 기계로 못 잰다 | #1 |\n"
    assert not check(parse(good)), "정상 행이 걸렸다"
    # 가짜 표식은 실행 시 조립한다 — 글자 그대로 적으면 이 소스 안에 있어서 «있음»으로 읽힌다(첫 실행에서 실제로 그랬다)
    ghost = "zz".join(["없는", "표식"])
    bad = {
        "4층 밖 처리": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 메모리 | {me}#def check | — |\n",
        "표식 없음": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 검사 | {me}#{ghost} | — |\n",
        "파일 없음": HEAD + "| 1 | 2026-09-06 | ep0 | x | 생성 | docs/없는파일.md#a | — |\n",
        "재발 앞 참조": HEAD + f"| 1 | 2026-09-06 | ep0 | x | 검사 | {me}#def check | #2 |\n",
        "못잡음 사유 없음": HEAD + "| 1 | 2026-09-06 | ep0 | x | 못잡음 | — | — |\n",
    }
    for name, text in bad.items():
        fails = check(parse(text))
        assert len(fails) == 1, f"{name}: 걸려야 하는데 {fails}"
        print("ok  ", name, "→", fails[0])
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
