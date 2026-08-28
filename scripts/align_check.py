# -*- coding: utf-8 -*-
"""상단 블록 정렬 실측 — **실크기 렌더에서 좌표를 잰다** (육안 판정 폐지).

`inner.make_v3` 는 상단을 «덮기»로 채우므로 여백은 **판 안쪽**에서 생긴다
(`_plate.fit` · `_beforeafter._place` 의 가운데 정렬, `_ownart` 의 조판).
그래서 최종 카드의 상단 영역에서 **잉크가 있는 최좌·최우 열**을 찾아 좌우 여백을 잰다.

    py align_check.py <편폴더> [편폴더 ...]

판정: 좌우 여백 차이 |L-R| ≤ TOL(px). 차이가 나면 어느 쪽이 넓은지 같이 낸다.
"""
import os
import sys

from PIL import Image

sys.path.insert(0, r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop\00_브랜드에셋")
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "departments", "marketing"))
import inner
import dist_transform as DT

TOL = 2            # 가운데 정렬의 정수 나눗셈 오차 한계
BG_TOL = 10        # 배경으로 볼 밝기 여유


def top_box(card_path):
    """카드 상단 영역에서 «배경이 아닌» 화소의 좌우 끝. 배경색은 네 모서리에서 잡는다."""
    im = Image.open(card_path).convert("RGB")
    top_h = round(inner.H * inner.V3_TOP)
    top = im.crop((0, 0, inner.W, top_h))
    px = top.load()
    w, h = top.size
    corners = [px[1, 1], px[w - 2, 1], px[1, h - 2], px[w - 2, h - 2]]
    bg = corners[0]
    if not all(sum(abs(a - b) for a, b in zip(c, bg)) <= BG_TOL * 3 for c in corners):
        return None, None, w, "모서리 배경색이 서로 다르다 — 여백 판정 불가(풀블리드 판)"
    left, right = w, -1
    for x in range(w):
        for y in range(0, h, 3):
            if sum(abs(a - b) for a, b in zip(px[x, y], bg)) > BG_TOL * 3:
                left = min(left, x)
                right = max(right, x)
                break
    if right < 0:
        return None, None, w, "상단이 통짜 배경이다"
    return left, w - 1 - right, w, None


def main():
    rows = []
    for d in sys.argv[1:]:
        name = os.path.basename(d.rstrip("\\/"))
        ep = DT.load_ep(d)
        for fname, badge in ep_deck(d):
            if badge is None or not fname.endswith(".png"):
                continue
            p = os.path.join(d, fname)
            if not os.path.exists(p):
                continue
            L, R, w, note = top_box(p)
            rows.append((name, fname, badge, L, R, note))

    out = ["상단 블록 좌우 여백 실측 (허용 |L-R| ≤ %dpx)" % TOL, "",
           "%-18s %-16s %-4s %6s %6s  %-6s %s" % ("편", "파일", "뱃지", "왼쪽", "오른쪽", "판정", "비고")]
    bad = 0
    for name, fname, badge, L, R, note in rows:
        if note:
            out.append("%-18s %-16s %-4s %6s %6s  %-6s %s" % (name, fname, badge, "-", "-", "N/A", note))
            continue
        okk = abs(L - R) <= TOL
        bad += not okk
        out.append("%-18s %-16s %-4s %6d %6d  %-6s %s"
                   % (name, fname, badge, L, R, "OK" if okk else "🔴 어긋남",
                      "" if okk else "%s쪽이 %dpx 넓다" % ("왼" if L > R else "오른", abs(L - R))))
    out.append("")
    out.append("STATUS: %s" % ("OK" if not bad else "FAIL %d건" % bad))
    sys.stdout.buffer.write(("\n".join(out) + "\n").encode("utf-8"))
    return 1 if bad else 0


def ep_deck(d):
    import re
    b = [f for f in os.listdir(d) if re.match(r"^build_ep\d+\.py$", f)][0]
    tab = {"F": DT._module_literals(os.path.join(d, "_facts.py"))}
    return DT._module_literals(os.path.join(d, b), tab)["DECK"]


if __name__ == "__main__":
    sys.exit(main())
