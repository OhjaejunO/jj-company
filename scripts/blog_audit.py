# -*- coding: utf-8 -*-
r"""블로그 재고 감사 — **썼는데 안 나간 글**을 센다 (2026-09-12 신설).

    py scripts\blog_audit.py                ← 초안 전수 대조
    py scripts\blog_audit.py --self-test    ← 역검증

## 🔴 이 자리가 없어서 한 편을 두 번 셌다

2026-09-12 에 JJ 가 「아스트라는 아마 발행했을껄?」 이라고 물었고 **맞았다** — `GPT-6 Astra` 는
9/6 에 이미 나가 있었는데 **우리 기록 어디에도 없었다.** 사람이 손으로 올린 글은 발행 로그에
안 남고, 초안의 `status:` 는 `ready`/`draft` 뿐이라 «나갔다» 를 담지 못한다. 그래서 큐를 셀 때마다
사람의 기억에 기대게 됐다.

**정본은 블로그 실물이다** (정관 §0 «실물을 조회할 수 있는 것은 실물이 정본이고 문서는 조회
결과다»). 이 감사기는 실물(RSS)을 떠서 초안 목록과 맞춰 본다 — 어느 쪽 문서도 정본으로 삼지 않는다.
`redist_audit.py` 가 Threads 재유통에 대해 하는 일과 같은 꼴이고, 계기도 같다: **«안 나간 것»은
실패가 아니라 시작이 없어서 로그가 없다.**

## 🔴 못 잡는 것 (정관 §0 4층 ④)

- **RSS 는 최근 N건만 준다.** 창 밖으로 밀려난 글은 «없다» 가 아니라 **«확인 불가»** 다 —
  그 둘을 한 칸에 두면 오래된 초안이 전부 «안 나감» 으로 뜬다. 판정 경계는 **RSS 에서 가장
  오래된 글의 날짜**이고, 그보다 이른 초안은 세지 않고 사유와 함께 따로 낸다.
- **제목이 같으면 나간 것으로 본다.** 본문이 초안과 같은지는 안 본다 — 발행 뒤 사람이 고칠 수
  있고, 에디터가 본문을 재구성하므로 바이트 대조가 애초에 성립하지 않는다(`publish_naver.py` 주석).
- 임시저장만 된 글은 RSS 에 없으므로 **«안 나감»** 으로 뜬다. 그게 맞다 — 독자에게는 없는 글이다.
"""
import argparse
import io
import os
import re
import sys
import urllib.request

HQ = r"C:\Users\ojaej\jj-company"          # reports\blog 는 운영 서버에만 있다(커밋 안 됨)
BLOG_ID = os.environ.get("NAVER_BLOG_ID") or "ai-tomangchi-lab"
RSS = "https://rss.blog.naver.com/%s.xml"

_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_MON = {m: i + 1 for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


def norm(t):
    """제목 비교용 정규화 — 네이버는 공백을 `\\xa0` 로 바꿔 저장한다(실측)."""
    return re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip()


def _tag(chunk, name):
    m = re.search(r"<%s>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</%s>" % (name, name), chunk, re.S)
    return (m.group(1).strip() if m else "")


def rss_date(s):
    """`Sat, 12 Sep 2026 21:44:00 +0900` → `2026-09-12`. 못 읽으면 빈 문자열."""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", s or "")
    if not m or m.group(2) not in _MON:
        return ""
    return "%s-%02d-%02d" % (m.group(3), _MON[m.group(2)], int(m.group(1)))


def fetch_live(blog=BLOG_ID, _text=None):
    """블로그 실물 — `[(제목, 날짜, 주소), ...]`. `_text` 는 역검증용 주입구."""
    if _text is None:
        req = urllib.request.Request(RSS % blog, headers={"User-Agent": "Mozilla/5.0"})
        _text = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    return [(norm(_tag(c, "title")), rss_date(_tag(c, "pubDate")),
             _tag(c, "link").split("?")[0]) for c in _ITEM.findall(_text)]


def drafts(blog_dir=None):
    """초안 — `[(파일이름, 제목, 날짜)]`. 제목은 H1, 날짜는 프론트매터 `date:`."""
    d = blog_dir or os.path.join(HQ, "reports", "blog")
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.endswith(".md"):
            continue
        md = io.open(os.path.join(d, name), encoding="utf-8").read()
        h1 = re.search(r"^#\s+(.+)$", md, re.M)
        dt = re.search(r"^date:\s*(\S+)", md, re.M)
        out.append((name, norm(h1.group(1)) if h1 else "", dt.group(1) if dt else ""))
    return out


def audit(live, mine):
    """(나간 편, 안 나간 편, 확인 불가) — 각각 `[(파일, 제목[, 사유])]`.

    🔴 **«없다» 와 «못 봤다» 를 가른다.** RSS 창(가장 오래된 글의 날짜) 밖의 초안은
       안 나갔다고 말할 근거가 없다 — 세지 않고 사유를 달아 따로 낸다.
    """
    titles = {t for t, _, _ in live}
    floor = min([d for _, d, _ in live if d] or [""])
    out, missing, unknown = [], [], []
    for name, title, date in mine:
        # 🔴 여기서도 접는다 — 부르는 쪽이 접었는지에 판정이 달리면 안 된다.
        if title and norm(title) in titles:
            out.append((name, title))
        elif floor and date and date < floor:
            unknown.append((name, title, "RSS 창(%s~) 밖 — 나갔는지 못 봤다" % floor))
        else:
            missing.append((name, title))
    return out, missing, unknown


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--blog", default=BLOG_ID)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return selftest()

    live = fetch_live(a.blog)
    mine = drafts()
    done, missing, unknown = audit(live, mine)
    print("블로그 재고 감사 — 초안 %d편 · 실물(RSS) %d건" % (len(mine), len(live)))
    for name, title in missing:
        print("  🔴 안 나감 %-44s %s" % (name, title[:48]))
    for name, title, why in unknown:
        print("  확인 불가 %-42s %s" % (name, why))
    print("  나감 %d편" % len(done))
    if missing:
        print("STATUS: FAIL 안 나간 글 %d편" % len(missing))
        return 1
    print("STATUS: OK%s" % (" (확인 불가 %d편)" % len(unknown) if unknown else ""))
    return 0


# ── 역검증 ──────────────────────────────────────────────────────────────────
_FEED = u"""<rss><channel>
<item><title>나간 글</title><pubDate>Sat, 12 Sep 2026 21:44:00 +0900</pubDate>
<link>https://blog.naver.com/x/2?fromRss=true</link></item>
<item><title>오래된 글</title><pubDate>Mon, 07 Sep 2026 09:31:00 +0900</pubDate>
<link>https://blog.naver.com/x/1</link></item>
</channel></rss>"""


def selftest():
    live = fetch_live(_text=_FEED)
    cases = [
        ("RSS 를 읽는다 (2건 · 제목·날짜·주소)",
         live == [("나간 글", "2026-09-12", "https://blog.naver.com/x/2"),
                  ("오래된 글", "2026-09-07", "https://blog.naver.com/x/1")]),
        # 🔴 «있는 것을 있다고» 와 «없는 것을 없다고» 를 **따로** 본다 —
        #    한쪽만 보면 전부 통과시키는 검사도 정상으로 보인다(정관 §0 역검증).
        ("실물에 있는 제목은 «나감»",
         audit(live, [("a.md", "나간 글", "2026-09-12")])[0] == [("a.md", "나간 글")]),
        ("실물에 없는 제목은 «안 나감»",
         audit(live, [("b.md", "안 쓴 글", "2026-09-12")])[1] == [("b.md", "안 쓴 글")]),
        # 🔴 이 축이 이 감사기의 절반이다 — 없으면 오래된 초안이 전부 «안 나감» 으로 뜬다.
        ("RSS 창보다 이른 초안은 «확인 불가» (없다고 말하지 않는다)",
         [x[:2] for x in audit(live, [("c.md", "옛 글", "2026-09-01")])[2]] == [("c.md", "옛 글")]
         and audit(live, [("c.md", "옛 글", "2026-09-01")])[1] == []),
        ("창 안(같은 날)이면 «확인 불가» 가 아니라 «안 나감»",
         audit(live, [("d.md", "옛 글", "2026-09-07")])[1] == [("d.md", "옛 글")]),
        # 네이버가 제목 공백을 \xa0 로 바꿔 저장한다 — 접지 않으면 전부 «안 나감» 이 된다.
        ("공백 꼴이 달라도 같은 제목으로 본다",
         audit(live, [("e.md", "나간\xa0 글", "2026-09-12")])[0] == [("e.md", "나간\xa0 글")]),
        # 🔴 헛돌지 않는가 — 실물이 비면 모든 초안이 걸려야 한다.
        ("실물 0건이면 전부 «안 나감» (전부 통과시키는 검사가 아니다)",
         len(audit([], [("f.md", "아무 글", "2026-09-12")])[1]) == 1),
        ("제목 없는 초안은 «안 나감» — 조용히 넘기지 않는다",
         audit(live, [("g.md", "", "2026-09-12")])[1] == [("g.md", "")]),
    ]
    bad = 0
    for why, ok in cases:
        print("%s %s" % ("PASS" if ok else "FAIL", why))
        bad += 0 if ok else 1
    print("STATUS: " + ("OK" if not bad else "FAIL %d건" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
