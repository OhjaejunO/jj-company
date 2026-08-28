# -*- coding: utf-8 -*-
"""«남의 것을 우리가 한 것처럼 적은 어미» 훑기.

주어가 **공식·문서·블로그·모델**인데 서술이 **행위형**이면 우리가 한 것처럼 읽힌다.
    ❌ 공식은 … 「…」고 같이 **적어요**      (우리가 적는 것처럼)
    ✅ 공식 문서에 「…」고 같이 **적혀 있어요**

이 검사는 **바닥선**이다 — 주어를 문법으로 완전히 가릴 수는 없으므로,
«남의 것 표지» 가 같은 줄에 있고 서술이 행위형인 줄을 **후보**로 낸다. 판정은 사람이 한다.

    py mimi_scan.py <편폴더> [편폴더 ...]
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "departments", "marketing"))
import dist_transform as DT

#: 남의 것 표지 — 이 말이 줄에 있으면 그 줄의 서술 주체는 대개 우리가 아니다.
THEIRS = ("공식", "블로그", "문서", "릴리스 노트", "README", "도움말", "모델 페이지",
          "가격 문서", "발표", "안내", "각주", "표", "카드 머리", "Z.ai", "구글", "메타",
          "Anthropic", "Meta", "Google")

#: 행위형 어미 — «우리가 한다» 로 읽히는 꼴.
ACT = re.compile(
    r"(적어요|적습니다|밝혀요|밝힙니다|말해요|말합니다|알려요|알립니다"
    r"|보여줘요|보여 줘요|보여줍니다|보여 줍니다|넣어요|넣습니다|둬요|둡니다"
    r"|해요|합니다|줘요|줍니다|써요|씁니다|만들어요|만듭니다|잡아요|잡습니다"
    r"|봐요|봅니다|골라요|고릅니다)$")

#: 이미 관찰형인 꼬리 — 후보에서 뺀다.
OBS = re.compile(r"(있어요|있습니다|돼요|됩니다|된대요|라고 해요|라고 합니다|이에요|예요|입니다"
                 r"|같아요|아니에요|아닙니다|없어요)$")

#: 우리 행위라 행위형이 맞는 줄 — 이 말이 있으면 뺀다.
OURS = ("저희", "우리", "직접 돌려", "재 봤", "시켜 봤", "돌려 봤", "물어", "넣어 봤")


def sentences(text):
    for s in re.split(r"(?<=[.!?])\s+|\n", text or ""):
        s = s.strip()
        if s:
            yield s


def scan(label, text, out):
    for s in sentences(text):
        core = s.rstrip(".!?」』\"')").strip()
        if not any(w in s for w in THEIRS):
            continue
        if any(w in s for w in OURS):
            continue
        if OBS.search(core):
            continue
        m = ACT.search(core)
        if m:
            out.append((label, m.group(0), s))


def main():
    out = []
    for d in sys.argv[1:]:
        name = os.path.basename(d.rstrip("\\/"))
        ep = DT.load_ep(d)
        for no in sorted(ep["CARDS"]):
            c = ep["CARDS"][no]
            for kind, t in ([("헤드라인", c.get("headline", "")), ("핵심", c.get("key", ""))]
                            + [("본문%d" % (i + 1), x) for i, x in enumerate(c.get("body") or [])]):
                scan("%s 카드%s %s" % (name, no, kind), t, out)
        scan("%s 캡션" % name, ep["caption"], out)
        scan("%s 고정댓글" % name, ep["pinned"], out)
        kit = os.path.join(d, [f for f in os.listdir(d) if f.endswith(".html")][0])
        html = io.open(kit, encoding="utf-8").read()
        html = re.sub(r"<[^>]+>", " ", html)
        scan("%s 킷" % name, html, out)

    lines = ["후보 %d건 (판정은 사람이 한다)" % len(out), ""]
    for label, tail, s in out:
        lines.append("  %-26s «%s»  %s" % (label, tail, s[:88]))
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
