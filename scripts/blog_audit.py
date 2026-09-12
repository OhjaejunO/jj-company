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

## 🔴 «제목을 고쳐 발행한 글» 을 영수증으로 잡는다 (2026-09-12 보강)

첫 판은 **제목 하나로만** 대조해서, 발행하며 제목을 다듬은 글이 «안 나감» 으로 떴다 — 그리고
«안 나감» 은 곧 «다시 올려라» 로 읽히므로 **같은 글을 두 번 올리게** 된다. 고친 자리는 검사가
아니라 **한 단계 앞**이다(정관 §0 4층 ①): 워커가 발행할 때 `logs\publish-receipts\blog\<원고>.json`
에 **글 번호(logNo)** 를 남기고, 여기서는 그 번호로 먼저 맞춘다. 제목은 바뀌어도 번호는 안 바뀐다.

- **RSS 가 여전히 정본이다.** 영수증은 «어느 글인가» 를 가리킬 뿐이고, «나갔는가» 는 그 번호가
  RSS 에 있는지로 판정한다. 영수증만 믿으면 **지운 글도 «나감» 으로 남는다.**
- 영수증이 있는데 RSS 창 **안**에 그 번호가 없으면 «안 나감» 이 아니라 **«지웠거나 비공개»** 로
  적는다 — 둘은 사람이 할 일이 다르다.
- **손으로 발행한 글에는 영수증이 없다.** `--seal` 이 RSS 로 확인된 짝을 영수증으로 굳힌다 —
  창이 지나가도 판정이 유지된다. 🔴 굳히는 값은 **RSS 실물에서 읽은 번호**이지 우리 기억이 아니다.
"""
import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.request

HQ = r"C:\Users\ojaej\jj-company"          # reports\blog 는 운영 서버에만 있다(커밋 안 됨)
BLOG_ID = os.environ.get("NAVER_BLOG_ID") or "ai-tomangchi-lab"
RSS = "https://rss.blog.naver.com/%s.xml"

#: 발행 영수증 자리. `publish_naver.py` 가 쓰고 여기서 읽는다 — **한 벌**이라 둘이 갈리지 않는다.
RECEIPTS = os.path.join(HQ, "logs", "publish-receipts", "blog")

_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_LOGNO = re.compile(r"/(\d{9,})(?:[?#]|$)")
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


def log_no(url):
    """주소에서 글 번호. 못 읽으면 빈 문자열 — 없는 번호를 지어내지 않는다."""
    m = _LOGNO.search((url or "").split("?")[0].rstrip("/"))
    return m.group(1) if m else ""


def write_receipt(post, data, root=None):
    r"""발행 영수증 한 장. 🔴 **번호가 없으면 쓰지 않는다** — 가리키는 것이 없는 영수증은
    «나갔다» 를 주장만 하고 확인은 못 하게 만든다(정관 §0 «조용히 실패하는 코드를 남기지 않는다»).
    """
    if not (data or {}).get("log_no"):
        raise ValueError("영수증에 글 번호가 없다: %r" % (data or {}).get("url"))
    d = root or RECEIPTS
    os.makedirs(d, exist_ok=True)
    q = os.path.join(d, post + ".json")
    io.open(q, "w", encoding="utf-8").write(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    return q


def receipts(root=None):
    """`{원고이름: 영수증}`. 읽다 깨진 것은 조용히 버리지 않고 사유와 함께 뺀다."""
    d = root or RECEIPTS
    out, broken = {}, []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.endswith(".json"):
            continue
        try:
            out[name[:-5]] = json.loads(io.open(os.path.join(d, name), encoding="utf-8").read())
        except (ValueError, OSError) as e:
            broken.append("%s (%s)" % (name, e))
    return out, broken


def drafts(blog_dir=None):
    r"""초안 — `[(원고이름, 제목, 날짜)]`. 제목은 H1, 날짜는 프론트매터 `date:`.

    🔴 **이름은 `.md` 를 뗀 꼴이다** — 발행 워커가 영수증을 `--post` 인자(확장자 없음)로
       적기 때문이다. 처음에는 여기서만 `.md` 를 붙여 놔서 **영수증 키가 갈렸고**, 워커가
       남긴 영수증을 이 감사기가 한 장도 못 찾았다(2026-09-12 실물 실행에서 드러났다).
       열쇠를 두 꼴로 두면 양쪽 다 «제대로 도는 것처럼» 보인다.
    """
    d = blog_dir or os.path.join(HQ, "reports", "blog")
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.endswith(".md"):
            continue
        md = io.open(os.path.join(d, name), encoding="utf-8").read()
        h1 = re.search(r"^#\s+(.+)$", md, re.M)
        dt = re.search(r"^date:\s*(\S+)", md, re.M)
        out.append((name[:-3], norm(h1.group(1)) if h1 else "", dt.group(1) if dt else ""))
    return out


def verdict(title, date, live, rec, floor):
    """한 초안의 판정 — `("나감"|"안 나감"|"못 봤다", 근거)`.

    🔴 **순서가 곧 이 함수다.**
      ① **영수증 글 번호가 RSS 에 있으면 나감** — 제목을 다듬어 발행해도 번호는 안 바뀐다.
      ② 제목이 RSS 에 있으면 나감 — 손으로 올린 글은 영수증이 없다.
      ③ RSS 창 밖이면, 영수증이 있으면 «나감»(그 번호로 나간 것을 그때 확인했다),
         없으면 **«못 봤다»** — «없다» 가 아니다.
      ④ 창 안인데 둘 다 아니면 «안 나감». 🔴 단 **영수증이 있는데 창 안에 없으면** 그것은
         «안 나감» 이 아니라 **«지웠거나 비공개»** 다 — 사람이 할 일이 다르다.
    """
    titles = {t for t, _, _ in live}
    nums = {log_no(u) for _, _, u in live}
    mine_no = (rec or {}).get("log_no") or ""
    if mine_no and mine_no in nums:
        return "나감", "글 번호 %s (영수증)" % mine_no
    if title and norm(title) in titles:
        return "나감", "제목 일치"
    if floor and date and date < floor:
        if mine_no:
            return "나감", "글 번호 %s — RSS 창(%s~) 밖이라 실물로는 못 봤다" % (mine_no, floor)
        return "못 봤다", "RSS 창(%s~) 밖 — 나갔는지 못 봤다" % floor
    if mine_no:
        return "안 나감", "🔴 영수증(%s)은 있는데 RSS 에 없다 — 지웠거나 비공개다" % mine_no
    return "안 나감", ""


def audit(live, mine, rec=None):
    """(나간 편, 안 나간 편, 확인 불가) — 각각 `[(파일, 제목, 근거)]`."""
    rec = rec or {}
    floor = min([d for _, d, _ in live if d] or [""])
    box = {"나감": [], "안 나감": [], "못 봤다": []}
    for name, title, date in mine:
        # 🔴 여기서도 접는다 — 부르는 쪽이 접었는지에 판정이 달리면 안 된다.
        v, why = verdict(title, date, live, rec.get(name), floor)
        box[v].append((name, title, why))
    return box["나감"], box["안 나감"], box["못 봤다"]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--blog", default=BLOG_ID)
    ap.add_argument("--receipts", default=None,
                    help="영수증 폴더 (기본: logs\\publish-receipts\\blog) — 굳히기를 실물에 쓰기 전에 재 볼 때")
    ap.add_argument("--seal", action="store_true",
                    help="RSS 로 «나감» 이 확인된 편 중 영수증 없는 것을 영수증으로 굳힌다")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return selftest()

    live = fetch_live(a.blog)
    mine = drafts()
    rec, broken = receipts(a.receipts)
    for b in broken:                       # 🔴 못 읽은 영수증을 조용히 버리지 않는다
        print("  🔴 영수증을 못 읽었다: %s" % b)
    done, missing, unknown = audit(live, mine, rec)
    print("블로그 재고 감사 — 초안 %d편 · 실물(RSS) %d건 · 영수증 %d장"
          % (len(mine), len(live), len(rec)))
    for name, title, why in missing:
        print("  🔴 안 나감 %-44s %s" % (name, why or title[:48]))
    for name, title, why in unknown:
        print("  확인 불가 %-42s %s" % (name, why))
    print("  나감 %d편" % len(done))

    if a.seal:
        # 🔴 굳히는 값은 **RSS 실물에서 읽은 번호**다 — 우리 기억이 아니다.
        by_title = {t: u for t, _, u in live}
        n = 0
        for name, title, _why in done:
            if name in rec or norm(title) not in by_title:
                continue
            url = by_title[norm(title)]
            if not log_no(url):
                print("  🔴 굳히지 못했다 — 주소에 글 번호가 없다: %s" % url)
                continue
            write_receipt(name, {"post": name, "title": title, "url": url,
                                 "log_no": log_no(url), "source": "rss",
                                 "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                          a.receipts)
            n += 1
        print("  영수증으로 굳힘 %d장 (근거: RSS 실물)" % n)

    if missing:
        print("STATUS: FAIL 안 나간 글 %d편" % len(missing))
        return 1
    print("STATUS: OK%s" % (" (확인 불가 %d편)" % len(unknown) if unknown else ""))
    return 0


# ── 역검증 ──────────────────────────────────────────────────────────────────
_FEED = u"""<rss><channel>
<item><title>나간 글</title><pubDate>Sat, 12 Sep 2026 21:44:00 +0900</pubDate>
<link>https://blog.naver.com/x/224409605344?fromRss=true</link></item>
<item><title>오래된 글</title><pubDate>Mon, 07 Sep 2026 09:31:00 +0900</pubDate>
<link>https://blog.naver.com/x/224400000001</link></item>
</channel></rss>"""

#: 나간 글의 영수증. 실물 RSS 에 그 번호가 있다.
_REC = {"a.md": {"log_no": "224409605344", "url": "https://blog.naver.com/x/224409605344"}}


def selftest():
    live = fetch_live(_text=_FEED)
    first = lambda box: [x[:2] for x in box]
    cases = [
        ("RSS 를 읽는다 (2건 · 제목·날짜·주소)",
         live == [("나간 글", "2026-09-12", "https://blog.naver.com/x/224409605344"),
                  ("오래된 글", "2026-09-07", "https://blog.naver.com/x/224400000001")]),
        ("주소에서 글 번호를 읽는다 — 못 읽으면 빈 값이지 지어내지 않는다",
         (log_no("https://blog.naver.com/x/224409605344?fromRss=true"),
          log_no("https://blog.naver.com/x/2"), log_no("")) == ("224409605344", "", "")),
        # 🔴 «있는 것을 있다고» 와 «없는 것을 없다고» 를 **따로** 본다 —
        #    한쪽만 보면 전부 통과시키는 검사도 정상으로 보인다(정관 §0 역검증).
        ("실물에 있는 제목은 «나감»",
         first(audit(live, [("a.md", "나간 글", "2026-09-12")])[0]) == [("a.md", "나간 글")]),
        ("실물에 없는 제목은 «안 나감»",
         first(audit(live, [("b.md", "안 쓴 글", "2026-09-12")])[1]) == [("b.md", "안 쓴 글")]),
        # ── 영수증 축 (2026-09-12) ────────────────────────────────────────────
        # 🔴 이 회차의 핵심이다 — 발행하며 제목을 다듬은 글이 종전에는 «안 나감» 으로 떴고,
        #    «안 나감» 은 곧 «다시 올려라» 로 읽혀 **같은 글을 두 번 올리게** 만들었다.
        ("🔴 제목을 고쳐 발행해도 영수증 글 번호로 «나감»",
         first(audit(live, [("a.md", "제목을 다듬었다", "2026-09-12")], _REC)[0])
         == [("a.md", "제목을 다듬었다")]),
        # 🔴 반대쪽 — 영수증만 믿으면 **지운 글도 «나감»** 으로 남는다. RSS 가 정본이다.
        ("🔴 영수증이 있어도 RSS 에 번호가 없으면 «나감» 이 아니다 (지웠거나 비공개)",
         audit(live, [("a.md", "제목을 다듬었다", "2026-09-12")],
               {"a.md": {"log_no": "224499999999"}})[1][0][2].startswith("🔴 영수증")),
        ("영수증 + RSS 창 밖 → «나감» («못 봤다» 로 남기지 않는다)",
         first(audit(live, [("a.md", "옛 글", "2026-09-01")], _REC)[0]) == [("a.md", "옛 글")]),
        ("🔴 번호 없는 영수증은 쓰지 않는다 (가리키는 것이 없는 영수증)",
         _raises(lambda: write_receipt("x", {"url": "https://blog.naver.com/x/"}))),
        # 🔴 이 축이 이 감사기의 절반이다 — 없으면 오래된 초안이 전부 «안 나감» 으로 뜬다.
        ("RSS 창보다 이른 초안은 «확인 불가» (없다고 말하지 않는다)",
         first(audit(live, [("c.md", "옛 글", "2026-09-01")])[2]) == [("c.md", "옛 글")]
         and audit(live, [("c.md", "옛 글", "2026-09-01")])[1] == []),
        ("창 안(같은 날)이면 «확인 불가» 가 아니라 «안 나감»",
         first(audit(live, [("d.md", "옛 글", "2026-09-07")])[1]) == [("d.md", "옛 글")]),
        # 네이버가 제목 공백을 \xa0 로 바꿔 저장한다 — 접지 않으면 전부 «안 나감» 이 된다.
        ("공백 꼴이 달라도 같은 제목으로 본다",
         first(audit(live, [("e.md", "나간\xa0 글", "2026-09-12")])[0])
         == [("e.md", "나간\xa0 글")]),
        # 🔴 헛돌지 않는가 — 실물이 비면 모든 초안이 걸려야 한다.
        ("실물 0건이면 전부 «안 나감» (전부 통과시키는 검사가 아니다)",
         len(audit([], [("f.md", "아무 글", "2026-09-12")])[1]) == 1),
        ("제목 없는 초안은 «안 나감» — 조용히 넘기지 않는다",
         first(audit(live, [("g.md", "", "2026-09-12")])[1]) == [("g.md", "")]),
        # 🔴 **열쇠 꼴** — 이 축이 없어서 실물 실행에서야 드러났다(2026-09-12). `drafts()` 가
        #    `.md` 를 붙여 돌려주는데 발행 워커는 `--post`(확장자 없음)로 영수증을 적어,
        #    **영수증이 한 장도 안 맞았다.** 양쪽 다 «도는 것처럼» 보이는 결함이다.
        ("🔴 초안 이름이 워커의 `--post` 와 같은 꼴이다 (`.md` 를 안 붙인다)",
         _draft_names() == ["2026-09-12_열쇠꼴"]),
    ]
    bad = 0
    for why, ok in cases:
        print("%s %s" % ("PASS" if ok else "FAIL", why))
        bad += 0 if ok else 1
    print("STATUS: " + ("OK" if not bad else "FAIL %d건" % bad))
    return 1 if bad else 0


def _draft_names():
    """가짜 초안 폴더 하나로 `drafts()` 가 돌려주는 **이름 꼴**만 잰다."""
    d = tempfile.mkdtemp(prefix="blogkey_")
    try:
        io.open(os.path.join(d, "2026-09-12_열쇠꼴.md"), "w", encoding="utf-8").write(
            "---\ndate: 2026-09-12\n---\n\n# 제목\n")
        return [n for n, _, _ in drafts(d)]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
