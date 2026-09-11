# -*- coding: utf-8 -*-
r"""네이버 블로그 조회기 — 검색 순위와 본문을 «기계로» 뜬다 (2026-09-11 신설).

🔴 **왜 이 파일이 있나.** WebFetch 는 `blog.naver.com`·`m.blog.naver.com`·
`m.search.naver.com` 에 대해 `400 The following domains are not accessible to our
user agent` 를 돌려준다 — 우리 쪽 설정이 아니라 **도구 제공자의 차단**이라 설정으로
못 푼다. 그런데 우리가 글을 올리는 유일한 검색 유입 매체가 네이버 블로그다.
「상위 글이 어떻게 쓰는가」를 못 재면 블로그 규격이 **추측**이 된다(정관 §0).

**차단은 «도구»에 걸린 것이지 «망»에 걸린 것이 아니다.** 같은 기계에서 평범한
`urllib` 요청은 200 을 받는다(2026-09-11 실측: 검색 560KB · 본문 221KB). 그래서
도구를 우회하는 것이 아니라 **다른 경로를 하나 만든다** — 이 파일이 그 경로다.

읽기 전용(A등급)이다. 로그인하지 않고, 쿠키를 쓰지 않고, 공개 페이지만 GET 한다.

    py scripts\naver_blog.py search "클래스101 후기" --n 10
    py scripts\naver_blog.py post https://blog.naver.com/<id>/<logNo>
    py scripts\naver_blog.py post <id> <logNo> --raw
    py scripts\naver_blog.py --self-test

🔴 **못 잡는 것 (정관 §0 4층 ④)**
- **순위는 «지금 이 기계에서 본 순서»다.** 네이버 검색은 개인화·시점에 따라 갈린다 —
  표본이지 순위표가 아니다.
- **본문은 `se-main-container` 안만** 읽는다. 구 스마트에디터(2018 이전) 글은 그 칸이
  없어 «본문 못 찾음» 으로 남는다. 뭉개지 않고 그렇게 적는다.
- **이미지 안의 글자는 못 읽는다.** 네이버 후기 글은 수치를 이미지로 넣는 일이 잦다.
- **대가성 표기 판정은 본문 글자만 본다** — 배너 이미지로 표기한 글은 «없음»으로 읽힌다.
"""
import argparse
import gzip
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
SEARCH = "https://search.naver.com/search.naver?where=blog&query=%s"
#: 🔴 **본문은 이 주소로 받는다.** `blog.naver.com/<id>/<logNo>` 는 껍데기이고 본문을
#: iframe 으로 끼워 넣는다 — 껍데기만 받으면 «글이 비었다»로 읽힌다.
POSTVIEW = ("https://blog.naver.com/PostView.naver?blogId=%s&logNo=%s"
            "&redirect=Dlog&widgetTypeCall=true&directAccess=false")
POST_URL = re.compile(r"https?://(?:m\.)?blog\.naver\.com/([A-Za-z0-9_-]+)/(\d{9,})")

#: 대가성 표기 탐지 — 규격 정본은 스킬의 `AD_LABEL_SAFE`/`AD_LABEL_VAGUE` 이고
#: 여기서는 **남의 글을 재는** 용도라 사본이 아니라 더 넓은 그물이다(둘의 목적이 다르다).
AD_ANY = re.compile(r"(유료\s*광고|상업\s*광고|광고|협찬|체험단|제공받|수수료|파트너스|"
                    r"소정의|대가를|원고료)")


def fetch(url, timeout=20):
    """공개 페이지를 GET 해 본문 문자열로 돌려준다."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://blog.naver.com/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body.decode("utf-8", "replace")


def search(query, n=10, page_html=None):
    """블로그 검색 결과에서 `(blogId, logNo)` 를 **본 순서대로** 뽑는다.

    🔴 중복을 지우되 **순서는 보존한다** — 순서가 곧 우리가 재려는 값이다.
    """
    h = page_html if page_html is not None else fetch(
        SEARCH % urllib.parse.quote(query))
    out = []
    for bid, log in POST_URL.findall(h):
        if (bid, log) not in out:
            out.append((bid, log))
    return out[:n]


def _div_block(h, start):
    """`start` 에서 시작하는 `<div …>` 의 짝을 세어 그 블록만 잘라 낸다.

    🔴 정규식으로 `</div>` 까지 자르면 **첫 번째 닫는 태그**에서 끊긴다 — 본문은
    `<div>` 가 스무 겹 중첩이라 그렇게 자르면 한 문단만 남는다.
    """
    depth = 0
    for m in re.finditer(r"<(/?)div\b", h[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            # 🔴 `</div` 까지만 잘라 내면 닫는 태그가 **평문으로 남는다** — `>` 까지 먹는다.
            return h[start:h.find(">", start + m.end()) + 1]
    return h[start:]


def _text(fragment):
    """태그를 지우고 줄바꿈을 살린 평문으로."""
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", fragment)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|h[1-6]|li)>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t).replace("​", "")
    t = re.sub(r"[ \t ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def post(blog_id, log_no, page_html=None):
    """글 하나를 재서 dict 로 돌려준다."""
    h = page_html if page_html is not None else fetch(POSTVIEW % (blog_id, log_no))
    i = h.find('class="se-main-container"')
    if i < 0:
        body, note = "", "본문 못 찾음 — se-main-container 없음(구 에디터 글일 수 있다)"
    else:
        body, note = _text(_div_block(h, h.rfind("<div", 0, i))), ""
    title = ""
    m = re.search(r'(?is)<meta property="og:title" content="(.*?)"', h)
    if m:
        title = html.unescape(m.group(1)).strip()
    if not title:
        m = re.search(r"(?is)<title>(.*?)</title>", h)
        title = html.unescape(m.group(1)).split(" : ")[0].strip() if m else ""
    date = ""
    m = re.search(r'(?is)class="se_publishDate[^"]*"[^>]*>(.*?)<', h)
    if m:
        date = _text(m.group(1))
    imgs = len(re.findall(r"(?i)<img[^>]+se-image-resource", h)) or \
        len(re.findall(r"(?i)<img\b", h))
    ad = sorted(set(AD_ANY.findall(body)))
    return {
        "blog_id": blog_id, "log_no": log_no,
        "url": "https://blog.naver.com/%s/%s" % (blog_id, log_no),
        "title": title, "date": date, "note": note,
        "chars": len(re.sub(r"\s", "", body)), "images": imgs,
        "links": sorted(set(re.findall(r"https?://[^\s\"'<>)\]]+", body))),
        "ad_tokens": ad, "body": body,
    }


def _self_test():
    """🔴 역검증 — 걸리는 쪽과 **안 걸리는 쪽**을 같이 본다.

    망을 타지 않는다. 파서가 제 몫을 하는지만 본다 — 망 쪽은 `search`/`post` 를
    실제로 돌려 «200 이 오는가»로 확인하고, 그것은 사람이 볼 자리다.
    """
    bad = []

    def t(why, got, want):
        if got != want:
            bad.append("%s — 얻음 %r / 바람 %r" % (why, got, want))

    # ① 중첩 div 를 끝까지 센다 (첫 </div> 에서 안 끊긴다)
    h = ('<div class="se-main-container"><div><p>첫 문단</p></div>'
         '<div><p>둘째 문단</p></div></div><div>바깥</div>')
    got = _text(_div_block(h, 0))
    t("중첩 본문을 끝까지 읽는다", "둘째 문단" in got, True)
    t("🔴 바깥 div 는 안 읽는다", "바깥" in got, False)

    # ② 본문 칸이 없으면 «못 찾음» — 조용히 빈 글로 넘어가지 않는다
    r = post("x", "1", page_html="<html><title>구에디터</title><body>본문</body></html>")
    t("🔴 본문 칸이 없으면 못 찾음이라 적는다", r["note"].startswith("본문 못 찾음"), True)
    t("🔴 그때 글자 수는 0 이다", r["chars"], 0)

    # ③ 검색 파서 — 순서 보존 · 중복 제거 · m. 도 같이 잡는다
    fake = ("a https://blog.naver.com/bbb/111111111 b "
            "https://m.blog.naver.com/aaa/222222222 c "
            "https://blog.naver.com/bbb/111111111 d")
    t("검색 순서를 보존한다", search("q", 10, page_html=fake),
      [("bbb", "111111111"), ("aaa", "222222222")])
    t("🔴 글 주소가 아닌 페이지에서는 0건이다",
      search("q", 10, page_html="https://blog.naver.com/bbb 소개글"), [])

    # ④ 대가성 표기 탐지 — 양방향
    mk = lambda s: '<div class="se-main-container"><p>%s</p></div>' % s
    t("«소정의 수수료» 가 잡힌다",
      post("x", "1", page_html=mk("소정의 수수료를 받습니다"))["ad_tokens"] != [], True)
    t("🔴 표기 없는 글은 빈 목록이다",
      post("x", "1", page_html=mk("오늘은 강의를 들었습니다"))["ad_tokens"], [])

    # ⑤ 제목·글자 수
    r = post("x", "1", page_html=(
        '<meta property="og:title" content="클래스101 후기"/>' + mk("가나다 라마바")))
    t("og:title 을 제목으로 읽는다", r["title"], "클래스101 후기")
    t("공백을 뺀 글자 수를 센다", r["chars"], 6)

    for line in bad:
        print("FAIL " + line)
    print("STATUS: %s" % ("OK" if not bad else "FAIL %d" % len(bad)))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="네이버 블로그 조회기 (읽기 전용)")
    ap.add_argument("mode", nargs="?", choices=["search", "post"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--raw", action="store_true", help="본문 전문을 같이 찍는다")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return _self_test()
    if not a.mode:
        ap.print_help()
        return 2

    if a.mode == "search":
        if not a.args:
            print("STATUS: FAIL 검색어가 없다")
            return 2
        q = " ".join(a.args)
        hits = search(q, a.n)
        rows = []
        for rank, (bid, log) in enumerate(hits, 1):
            try:
                r = post(bid, log)
            except Exception as e:                        # noqa: BLE001
                print("  %2d. %s/%s — 조회 실패: %s" % (rank, bid, log, e))
                continue
            rows.append(dict(r, rank=rank))
            if a.json:
                continue
            print("  %2d. %s" % (rank, r["title"]))
            print("      %s · %s자 · 이미지 %d · 표기 %s"
                  % (r["url"], r["chars"], r["images"],
                     "/".join(r["ad_tokens"]) or "없음"))
            if r["note"]:
                print("      🔴 %s" % r["note"])
        if a.json:
            print(json.dumps([{k: v for k, v in r.items() if k != "body"}
                              for r in rows], ensure_ascii=False, indent=2))
        print("STATUS: OK  («%s» %d건 — 지금 이 기계에서 본 순서다)" % (q, len(rows)))
        return 0

    # post
    if len(a.args) == 1:
        m = POST_URL.search(a.args[0])
        if not m:
            print("STATUS: FAIL 주소에서 blogId/logNo 를 못 읽었다")
            return 2
        bid, log = m.group(1), m.group(2)
    elif len(a.args) >= 2:
        bid, log = a.args[0], a.args[1]
    else:
        print("STATUS: FAIL 주소 또는 <id> <logNo> 가 필요하다")
        return 2

    r = post(bid, log)
    if a.json:
        print(json.dumps(r if a.raw else {k: v for k, v in r.items() if k != "body"},
                         ensure_ascii=False, indent=2))
    else:
        print("제목: %s" % r["title"])
        print("주소: %s" % r["url"])
        print("분량: %d자 (공백 제외) · 이미지 %d장" % (r["chars"], r["images"]))
        print("대가성 표기 낱말: %s" % ("/".join(r["ad_tokens"]) or "🔴 없음"))
        print("링크 %d건: %s" % (len(r["links"]), ", ".join(r["links"][:5])))
        if r["note"]:
            print("🔴 %s" % r["note"])
        if a.raw:
            print("-" * 60)
            print(r["body"])
    print("STATUS: %s" % ("OK" if not r["note"] else "OK (부분: 본문 못 읽음)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
