# -*- coding: utf-8 -*-
r"""blog_brief — blog-writer 의 재료(브리프)를 결정적으로 모은다. 모델 없음.

WHAT (2026-09-05 · 네이버 벤치마크 §5-2)
  전날(과 그제) 스캔로그의 «제안» 소재 + 최근 발행편 N개의 검증로그 §1·§2 + 카드 문안 + 캡션 경로
  + 덱 이미지 경로 + 인스타 URL(발행로그) 을 한 파일에 붙인다.
  → logs\blog-data\brief_<날짜>.md
  집필원은 이 파일만 읽는다. 여기 없는 사실은 글에 못 들어간다.

USAGE
  py scripts\blog_brief.py [--date YYYY-MM-DD] [--eps 2] [--out <path>]
  py scripts\blog_brief.py --self-test

STATUS 줄: 마지막 줄. 소재가 0건이면 «STATUS: OK (소재 0건)» — 실패가 아니다(§4).
"""
import argparse
import datetime as dt
import io
import os
import re
import sys

WORKSHOP = r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop"
SCANLOG = os.path.join(WORKSHOP, "스캔로그")
PUBLISHED = os.path.join(WORKSHOP, "01_발행완료")
INPROG = os.path.join(WORKSHOP, "02_제작중")
PUBLOG = os.path.join(WORKSHOP, "발행로그.md")


def read(p):
    return io.open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else ""


def proposals(day):
    """스캔로그 <day>.md 의 «후보 전체» 표에서 판정이 «제안» 인 행."""
    md = read(os.path.join(SCANLOG, day + ".md"))
    rows = []
    for ln in md.splitlines():
        if ln.startswith("|") and "**제안" in ln:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) >= 5:
                rows.append({"후보": cells[0], "축": cells[1], "확인": cells[2], "사유": cells[4]})
    return md, rows


def recent_eps(n):
    """01_발행완료 + 02_제작중 에서 mtime 최신 ep 폴더 n개(검증로그가 있는 것만)."""
    cands = []
    for root in (PUBLISHED,):          # 2026-09-05: 블로그 소재는 «발행된 편»만 — 제작 중인 편은 아직 바깥에 안 나간 것이라 쓰지 않는다
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            p = os.path.join(root, name)
            if name.startswith("ep") and os.path.isdir(p) and os.path.exists(os.path.join(p, "검증로그.md")):
                cands.append((os.path.getmtime(p), p))
    return [p for _, p in sorted(cands, reverse=True)[:n]]


def ep_block(folder):
    name = os.path.basename(folder)
    log = read(os.path.join(folder, "검증로그.md"))
    sec = re.findall(r"^## [12]\..*?(?=^## |\Z)", log, re.S | re.M)
    imgs = sorted(f for f in os.listdir(folder) if re.match(r"\d\d_.*\.(png|jpg)$", f))
    urls = [ln for ln in read(PUBLOG).splitlines() if name.split("_")[0] in ln and "instagram.com" in ln]
    out = ["### 편 %s" % name, "- 폴더: `%s`" % folder,
           "- 캡션: `%s`" % os.path.join(folder, "caption.txt"),
           "- 이미지: " + ", ".join("`%s`" % os.path.join(folder, f) for f in imgs[:16]),
           "- 인스타: " + (" / ".join(u.strip() for u in urls[:2]) or "발행로그에 없음 — «확인 못 했어요»")]
    out += ["", "#### 검증로그 §1·§2 (사실 원장 — 여기 있는 값만 쓴다)", ""] + sec
    return "\n".join(out)


def build(day, n_eps):
    d = dt.date.fromisoformat(day)
    days = [(d - dt.timedelta(days=k)).isoformat() for k in (1, 2)]
    parts = ["# 블로그 브리프 %s (%s)" % (day, "weekly" if d.weekday() == 6 else "daily"), ""]
    total = 0
    for k in days:
        md, rows = proposals(k)
        parts.append("## 스캔로그 %s — 제안 %d건" % (k, len(rows)))
        if not md:
            parts.append("- 스캔로그 없음")
        for r in rows:
            parts.append("- **%s** [%s] · 확인: %s · 사유: %s" % (r["후보"], r["축"], r["확인"], r["사유"]))
        total += len(rows)
        if rows:
            # 원문 조각·URL 은 로그 본문에 있다 — 통째로 붙인다(집필원이 URL 을 지어내지 않게)
            parts += ["", "<details><summary>스캔로그 %s 전문</summary>" % k, "", md, "", "</details>", ""]
    eps = recent_eps(n_eps)
    parts.append("## 최근 발행편 %d" % len(eps))
    for f in eps:
        parts += ["", ep_block(f)]
    total += len(eps)
    parts += ["", "## 소재 합계: %d건" % total,
              "STATUS: OK" + (" (소재 0건)" if total == 0 else "")]
    return "\n".join(parts), total


def self_test():
    import tempfile
    global SCANLOG, PUBLISHED, INPROG, PUBLOG
    root = tempfile.mkdtemp(prefix="blog_brief_")
    SCANLOG = os.path.join(root, "s"); PUBLISHED = os.path.join(root, "p"); INPROG = os.path.join(root, "i")
    PUBLOG = os.path.join(root, "pub.md")
    os.makedirs(SCANLOG); os.makedirs(PUBLISHED); os.makedirs(INPROG)
    io.open(os.path.join(SCANLOG, "2026-09-06.md"), "w", encoding="utf-8").write(
        "| 후보 | 축 | 1차 확인 | 판정 | 사유 |\n|---|---|---|---|---|\n| A | AI 소식 | x.com | **제안** | 좋다 |\n| B | 기회 | y | 반려 | 니치 |\n")
    ep = os.path.join(PUBLISHED, "ep50_test"); os.makedirs(ep)
    io.open(os.path.join(ep, "검증로그.md"), "w", encoding="utf-8").write("## 1. 사실\n- 값 1\n## 2. 원문\n- \"quote\"\n## 3. 못 연 것\n- z\n")
    io.open(os.path.join(ep, "01_cover.png"), "wb").write(b"x")
    io.open(PUBLOG, "w", encoding="utf-8").write("| ep50 | instagram.com/p/abc |\n")
    txt, total = build("2026-09-07", 1)
    ok1 = total == 2 and "**A**" in txt and "B" not in txt.split("<details>")[0].split("## 최근")[0].replace("| B |", "") and "값 1" in txt and "못 연 것" not in txt and "instagram.com/p/abc" in txt
    txt2, total2 = build("2026-09-09", 0)
    ok2 = total2 == 0 and txt2.rstrip().endswith("STATUS: OK (소재 0건)")
    for name, v in (("제안만 · §1§2만 · 인스타 URL", ok1), ("소재 0건 → OK (소재 0건)", ok2)):
        print(("PASS " if v else "FAIL ") + name)
    print("STATUS: " + ("OK" if ok1 and ok2 else "FAIL selftest"))
    return 0 if ok1 and ok2 else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--eps", type=int, default=2)
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    txt, total = build(a.date, a.eps)
    out = a.out or os.path.join("logs", "blog-data", "brief_%s.md" % a.date)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    io.open(out, "w", encoding="utf-8").write(txt)
    print("brief -> %s (%d bytes, 소재 %d건)" % (out, len(txt.encode("utf-8")), total))
    print(txt.splitlines()[-1])
