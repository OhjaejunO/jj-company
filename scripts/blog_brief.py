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

STATUS 줄: 마지막 줄. 소재 = «쓸 편»(블로그 글이 아직 없는 최근 발행편). 0건이면 «STATUS: OK (소재 0건)» — 실패가 아니다(§4).
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
# 이미 쓴 블로그 글 — 프런트매터 `source: epNN…` 로 편을 가린다. 래퍼 CWD 가 아니라 이 스크립트의 레포 기준.
BLOGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "blog")


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


def blog_for(name):
    """편 폴더 이름(epNN_…)에 대한 기존 블로그 글 파일명. 없으면 None. 편 번호로 가른다(릴스 폴더도 같은 편)."""
    m = re.match(r"ep\d+", name)
    if not m or not os.path.isdir(BLOGDIR):
        return None
    for f in sorted(os.listdir(BLOGDIR)):
        if f.endswith(".md"):
            s = re.search(r"^source:\s*(ep\d+)", read(os.path.join(BLOGDIR, f)), re.M)
            if s and s.group(1) == m.group(0):
                return f
    return None


def ep_block(folder, done=None):
    name = os.path.basename(folder)
    log = read(os.path.join(folder, "검증로그.md"))
    # 🔴 전 절을 싣는다 (2026-09-06). 종전엔 §1·§2 만 실어 «나머지는 에이전트가 알아서 열게» 뒀는데, 첫 자동 회차가 ep42
    # 검증로그의 §3 금성 지도·§4 한계를 통째로 빼고 추측 문장으로 채웠다. 프롬프트로 «다 읽어라»가 아니라 브리프가 다 싣는다
    # (정관 §0 4층 ① 구조로 닫기). 사실이 아닌 절(게이트 사고·조판 경위)도 같이 가지만 «브리프에 없는 사실은 쓰지 않는다»가
    # 그대로 지켜지므로 해가 없다 — 없는 것보다 있는 것이 싸다.
    # 🔴 절을 골라내지 않고 파일 통째로 싣는다 (2026-09-19). 종전 `^## \d+\.` 추출은 ep60 부터 쓰인 `## §0` 꼴 제목을
    # 하나도 못 잡아 «전 절» 칸이 조용히 비었고(ep59~67 전부), `## 2-1.` 같은 하위 절도 빠뜨렸다. 고를 것이 없으면 틀릴 것도 없다.
    sec = [log.strip() or "(검증로그가 비어 있다 — 이 편은 쓸 재료가 없다)"]
    imgs = sorted(f for f in os.listdir(folder) if re.match(r"\d\d_.*\.(png|jpg)$", f))
    urls = [ln for ln in read(PUBLOG).splitlines() if name.split("_")[0] in ln and "instagram.com" in ln]
    out = ["### 편 %s" % name, "- 폴더: `%s`" % folder,
           "- 캡션: `%s`" % os.path.join(folder, "caption.txt"),
           "- 이미지: " + ", ".join("`%s`" % os.path.join(folder, f) for f in imgs[:16]),
           "- 인스타: " + (" / ".join(u.strip() for u in urls[:2]) or "발행로그에 없음 — «확인 못 했어요»"),
           "- 우리 블로그 글: " + ("이미 씀 → `reports\\blog\\%s` (쓸 편 아님)" % done if done else "아직 없음 — 쓸 편")]
    out += ["", "#### 검증로그 전 절 (사실 원장 — 여기 있는 값만 쓴다 · 과학·한계·데모 절도 소재다, 빼지 않는다)", ""] + sec
    return "\n".join(out)


def build(day, n_eps):
    d = dt.date.fromisoformat(day)
    days = [(d - dt.timedelta(days=k)).isoformat() for k in (1, 2)]
    parts = ["# 블로그 브리프 %s (%s)" % (day, "weekly" if d.weekday() == 6 else "daily"), ""]
    n_prop = 0
    for k in days:
        md, rows = proposals(k)
        parts.append("## 스캔로그 %s — 제안 %d건" % (k, len(rows)))
        if not md:
            parts.append("- 스캔로그 없음")
        for r in rows:
            parts.append("- **%s** [%s] · 확인: %s · 사유: %s" % (r["후보"], r["축"], r["확인"], r["사유"]))
        n_prop += len(rows)
        if rows:
            # 원문 조각·URL 은 로그 본문에 있다 — 통째로 붙인다(집필원이 URL 을 지어내지 않게)
            parts += ["", "<details><summary>스캔로그 %s 전문</summary>" % k, "", md, "", "</details>", ""]
    eps = recent_eps(n_eps)
    parts.append("## 최근 발행편 %d" % len(eps))
    # 🔴 합계 = «쓸 편» 수 (2026-09-19). 종전 합계는 이미 블로그 글이 있는 편과 스캔로그 제안까지 셌는데, 규격상 초안은
    # «블로그 글이 아직 없는 발행편» 에서만 나오고 제안은 관련글 재료일 뿐이다. 그래서 쓸 편이 0인 날에도 합계가 2라
    # 래퍼가 에이전트의 정당한 «쓸 편 없음» 을 FAIL draft-missing 으로 찍었다(9/15~9/19 닷새). 래퍼는 이 줄만 본다.
    total = 0
    for f in eps:
        done = blog_for(os.path.basename(f))
        total += done is None
        parts += ["", ep_block(f, done)]
    if not os.path.isdir(BLOGDIR):
        parts.append("- ⚠ 블로그 폴더 없음(`%s`) — 이미 쓴 편을 가리지 못해 전부 «쓸 편» 으로 셌다" % BLOGDIR)
    parts += ["", "## 소재 합계: %d건 (쓸 편 — 블로그 글이 아직 없는 발행편 · 스캔로그 제안 %d건은 관련글 재료라 세지 않는다)" % (total, n_prop),
              "STATUS: OK" + (" (소재 0건)" if total == 0 else "")]
    return "\n".join(parts), total


def self_test():
    import tempfile
    global SCANLOG, PUBLISHED, INPROG, PUBLOG, BLOGDIR
    root = tempfile.mkdtemp(prefix="blog_brief_")
    SCANLOG = os.path.join(root, "s"); PUBLISHED = os.path.join(root, "p"); INPROG = os.path.join(root, "i")
    PUBLOG = os.path.join(root, "pub.md"); BLOGDIR = os.path.join(root, "blog")
    os.makedirs(SCANLOG); os.makedirs(PUBLISHED); os.makedirs(INPROG); os.makedirs(BLOGDIR)
    io.open(os.path.join(SCANLOG, "2026-09-06.md"), "w", encoding="utf-8").write(
        "| 후보 | 축 | 1차 확인 | 판정 | 사유 |\n|---|---|---|---|---|\n| A | AI 소식 | x.com | **제안** | 좋다 |\n| B | 기회 | y | 반려 | 니치 |\n")
    ep = os.path.join(PUBLISHED, "ep50_test"); os.makedirs(ep)
    io.open(os.path.join(ep, "검증로그.md"), "w", encoding="utf-8").write("## 1. 사실\n- 값 1\n## 2. 원문\n- \"quote\"\n## 3. 못 연 것\n- z\n")
    io.open(os.path.join(ep, "01_cover.png"), "wb").write(b"x")
    io.open(PUBLOG, "w", encoding="utf-8").write("| ep50 | instagram.com/p/abc |\n")
    txt, total = build("2026-09-07", 1)
    ok1 = total == 1 and "**A**" in txt and "B" not in txt.split("<details>")[0].split("## 최근")[0].replace("| B |", "") and "값 1" in txt and "instagram.com/p/abc" in txt
    # 역검증 (2026-09-06): §3 이 브리프에 실려야 한다 — 종전 «§1·§2 만» 이면 여기서 걸린다
    ok3 = "## 3. 못 연 것" in txt and "- z" in txt
    txt2, total2 = build("2026-09-09", 0)
    ok2 = total2 == 0 and txt2.rstrip().endswith("STATUS: OK (소재 0건)")
    # 역검증 (2026-09-19) ⓐ `## §N` 꼴 검증로그도 실린다 — 종전 `^## \d+\.` 추출이면 본문이 빠진다
    ep2 = os.path.join(PUBLISHED, "ep60_sec"); os.makedirs(ep2)
    io.open(os.path.join(ep2, "검증로그.md"), "w", encoding="utf-8").write("## §0 축\n- 섹션값 7\n## §2. 사실\n- 섹션값 8\n")
    os.utime(ep2, (9e9, 9e9))   # 가장 최근 편으로
    txt4, total4 = build("2026-09-09", 1)
    ok4 = "섹션값 7" in txt4 and "섹션값 8" in txt4 and total4 == 1
    # ⓑ 이미 블로그 글이 있는 편은 «쓸 편» 이 아니다 — 제안이 있어도(09-07 브리프의 전날 06 로그) 합계 0 · STATUS 0건
    io.open(os.path.join(BLOGDIR, "2026-09-10_x.md"), "w", encoding="utf-8").write("---\nkind: topic\nsource: ep60_sec 검증로그\n---\n")
    txt5, total5 = build("2026-09-07", 1)
    ok5 = total5 == 0 and txt5.rstrip().endswith("STATUS: OK (소재 0건)") and "이미 씀" in txt5 and "**A**" in txt5
    # ⓑ 반대쪽: 번호가 앞자리만 같은 편(ep6)의 글은 ep60 을 «씀» 으로 만들지 않는다
    os.remove(os.path.join(BLOGDIR, "2026-09-10_x.md"))
    io.open(os.path.join(BLOGDIR, "2026-09-10_y.md"), "w", encoding="utf-8").write("---\nsource: ep6 검증로그\n---\n")
    txt6, total6 = build("2026-09-07", 1)
    ok6 = total6 == 1 and "아직 없음" in txt6
    cases = (("제안만 · 인스타 URL", ok1), ("검증로그 전 절 실림 (§3 포함)", ok3), ("소재 0건 → OK (소재 0건)", ok2),
             ("§N 꼴 검증로그 본문 실림", ok4), ("이미 쓴 편 → 합계 0 · 제안은 세지 않음", ok5), ("ep6 글이 ep60 을 가리지 않음", ok6))
    for name, v in cases:
        print(("PASS " if v else "FAIL ") + name)
    ok = all(v for _, v in cases)
    print("STATUS: " + ("OK" if ok else "FAIL selftest"))
    return 0 if ok else 1


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
