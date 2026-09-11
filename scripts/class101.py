# -*- coding: utf-8 -*-
r"""class101 — 「그 강의가 구독(플러스)에 들어 있나」를 기계로 잰다 (2026-09-11 신설).

🔴 **왜 있나.** 클래스101 파트너스 편의 전제가 «고른 강의를 14일 이용권으로 실제로
들을 수 있는가» 인데, 그것은 **구독 포함 여부**에 달려 있다. 종전에는 그 답이
«JJ 가 로그인해서 눈으로 본다» 뿐이었고, 그러면 강의를 바꿀 때마다 사람이 불려 나온다.

**사이트 화면으로는 못 읽는다** — 제품 페이지는 클라이언트 렌더라 HTML 에 제목조차 없다.
대신 공개 GraphQL 게이트웨이가 **로그인 없이** 열려 있고, 검색 필터에 그 축이 있다:

    ProductSearchFilterV2.isIncludedInPlusPlan: Boolean

읽기 전용(A등급)이다. 로그인하지 않고, 쿠키를 쓰지 않고, 공개 카탈로그만 조회한다.

    py scripts\class101.py search "AI 영상" --plus
    py scripts\class101.py search "클로드" --all --n 20
    py scripts\class101.py plus <productId> --hint "제목 일부"
    py scripts\class101.py --self-test

🔴 **못 잡는 것 (정관 §0 4층 ④)**
- **«지금» 값이다.** `plusAddedAt` 이 있듯 강의는 구독에 들어오고 나간다 — 편을 만드는
  날 다시 잰다. 오늘 참이었다는 것이 업로드 날 참이라는 뜻이 아니다.
- **가격·할인은 못 읽는다.** 그쪽은 인증이 필요하다(`classProduct` 가 `UNAUTHENTICATED`).
  구독가·특가는 **JJ 가 본 화면**이 정본이고, 우리가 본 값만 글에 적는다.
- **커리큘럼(강 수·재생시간)도 인증 자리**라 사람이 본다.
- **검색 순위**는 개인화·시점에 따라 갈린다 — 표본이지 순위표가 아니다.
"""
import argparse
import gzip
import io
import json
import sys
import urllib.request

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

EP = "https://cdn-production-gateway.class101.net/graphql"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

SEARCH_Q = """query S($q: String, $filter: ProductSearchFilterV2, $first: Int, $after: String) {
  searchProductsV5(query: $q, filter: $filter) {
    totalCount
    products(first: $first, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges { node {
        _id title klassId isIncludedInPlusPlan plusAddedAt
        likedCount score difficulty state
        author { nickName }
      } }
    }
  }
}"""


def gq(query, variables=None, timeout=40, _post=None):
    """GraphQL 한 번. 🔴 `errors` 가 오면 **던진다** — 조용히 빈 결과로 넘기지 않는다."""
    body = {"query": query}
    if variables:
        body["variables"] = variables
    raw = (_post or _http)(json.dumps(body).encode("utf-8"), timeout)
    d = json.loads(raw)
    if d.get("errors"):
        raise RuntimeError("GraphQL 오류: %s" % json.dumps(d["errors"], ensure_ascii=False)[:400])
    if "data" not in d:
        raise RuntimeError("응답에 data 가 없다: %s" % raw[:200])
    return d["data"]


def _http(payload, timeout):
    req = urllib.request.Request(EP, data=payload, headers={
        "User-Agent": UA, "Content-Type": "application/json",
        "Origin": "https://class101.net", "Referer": "https://class101.net/",
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            b = gzip.decompress(b)
        return b.decode("utf-8", "replace")


def build_filter(plus):
    """`plus` 가 None 이면 **필터를 걸지 않는다**(전체).

    🔴 `False` 와 `None` 을 같이 다루면 «단품만 보기» 가 조용히 «전체» 가 된다.
    """
    return {} if plus is None else {"isIncludedInPlusPlan": bool(plus)}


def search(query, plus=None, first=15, after=None, _post=None):
    d = gq(SEARCH_Q, {"q": query, "filter": build_filter(plus),
                      "first": first, "after": after}, _post=_post)
    res = d["searchProductsV5"]
    ps = res["products"]
    rows = []
    for e in ps["edges"]:
        n = e["node"]
        rows.append({
            "id": n["_id"], "title": n.get("title") or "",
            "plus": bool(n.get("isIncludedInPlusPlan")),
            "plus_added_at": n.get("plusAddedAt"),
            "liked": n.get("likedCount"), "score": n.get("score"),
            "difficulty": n.get("difficulty"), "state": n.get("state"),
            "author": (n.get("author") or {}).get("nickName") or "",
            "url": "https://class101.net/ko/products/%s" % n["_id"],
        })
    return {"total": ps.get("totalCount") or res.get("totalCount"),
            "has_next": (ps.get("pageInfo") or {}).get("hasNextPage"),
            "cursor": (ps.get("pageInfo") or {}).get("endCursor"),
            "rows": rows}


def plus_of(product_id, hint, _post=None):
    """그 강의가 지금 구독에 들어 있나. 🔴 못 찾으면 `None` — «아니다»가 아니다."""
    for plus in (True, False):
        r = search(hint, plus=plus, first=40, _post=_post)
        for row in r["rows"]:
            if row["id"] == product_id:
                return row
    return None


def _self_test():
    r"""역검증 — 망을 타지 않는다. 조립과 «조용히 실패» 경로만 본다.

    🔴 망 쪽(«200 이 오는가»)은 실제 실행으로 사람이 본다. 여기서 그것까지 재려 하면
    네트워크가 죽은 날 커밋이 막히고, 그러면 `--no-verify` 가 나온다.
    """
    bad = []

    def t(why, got, want):
        if got != want:
            bad.append("%s — 얻음 %r / 바람 %r" % (why, got, want))

    # ① 필터 조립 — 🔴 False 와 None 이 갈린다
    t("plus=True 면 필터가 참", build_filter(True), {"isIncludedInPlusPlan": True})
    t("🔴 plus=False 는 «단품만» 이다 (전체가 아니다)",
      build_filter(False), {"isIncludedInPlusPlan": False})
    t("🔴 plus=None 이면 필터가 비어 있다 (전체)", build_filter(None), {})

    # ② errors 가 오면 던진다 — 빈 결과로 넘어가지 않는다
    def boom(payload, timeout):
        return json.dumps({"errors": [{"message": "You need to authenticate first."}]})
    try:
        gq("{x}", _post=boom)
        bad.append("🔴 errors 를 받고도 안 던졌다")
    except RuntimeError as e:
        t("🔴 errors 면 던진다 (조용히 통과 아님)", "authenticate" in str(e), True)

    # ③ data 가 없으면 던진다
    try:
        gq("{x}", _post=lambda p, tmo: json.dumps({"extensions": {}}))
        bad.append("🔴 data 없는 응답을 통과시켰다")
    except RuntimeError as e:
        t("🔴 data 가 없으면 던진다", "data" in str(e), True)

    # ④ 결과 매핑 — 플러스 참/거짓 양쪽
    def fake(payload, timeout):
        return json.dumps({"data": {"searchProductsV5": {"totalCount": 2, "products": {
            "totalCount": 2, "pageInfo": {"hasNextPage": False, "endCursor": None},
            "edges": [
                {"node": {"_id": "a", "title": "구독 강의", "isIncludedInPlusPlan": True,
                          "plusAddedAt": "2025-11-17T00:00:00Z", "likedCount": 5,
                          "author": {"nickName": "ZOA"}}},
                {"node": {"_id": "b", "title": "단품 강의", "isIncludedInPlusPlan": False,
                          "plusAddedAt": None, "likedCount": 1, "author": None}},
            ]}}}})
    r = search("q", plus=None, _post=fake)
    t("구독 강의는 plus=True 로 읽힌다", r["rows"][0]["plus"], True)
    t("🔴 단품 강의는 plus=False 로 읽힌다 (전부 참이 아니다)", r["rows"][1]["plus"], False)
    t("author 가 없어도 죽지 않는다", r["rows"][1]["author"], "")
    t("주소를 만든다", r["rows"][0]["url"], "https://class101.net/ko/products/a")

    # ⑤ plus_of — 못 찾으면 None (🔴 «구독 아님» 이 아니다)
    t("🔴 목록에 없으면 None 이다 («구독 아님»이 아니다)",
      plus_of("zzz", "q", _post=fake), None)
    t("찾으면 그 행을 준다", (plus_of("b", "q", _post=fake) or {}).get("plus"), False)

    for line in bad:
        print("FAIL " + line)
    print("STATUS: %s" % ("OK" if not bad else "FAIL %d" % len(bad)))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="클래스101 공개 카탈로그 조회 (읽기 전용)")
    ap.add_argument("mode", nargs="?", choices=["search", "plus"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--plus", action="store_true", help="구독 포함만")
    ap.add_argument("--only-paid", action="store_true", help="구독 미포함(단품)만")
    ap.add_argument("--all", action="store_true", help="전체 (기본)")
    ap.add_argument("--hint", default=None, help="plus 모드에서 그 강의를 찾을 검색어")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return _self_test()
    if not a.mode:
        ap.print_help()
        return 2

    plus = True if a.plus else (False if a.only_paid else None)

    if a.mode == "search":
        if not a.args:
            print("STATUS: FAIL 검색어가 없다")
            return 2
        q = " ".join(a.args)
        r = search(q, plus=plus, first=a.n)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print("«%s» · 구독필터 %s · 전체 %s건 (이 페이지 %d)"
                  % (q, {True: "포함만", False: "단품만", None: "없음"}[plus],
                     r["total"], len(r["rows"])))
            for row in r["rows"]:
                print("  %-56s %s 👍%-6s %s"
                      % (row["title"][:54], "구독" if row["plus"] else "🔴단품",
                         row["liked"], row["author"]))
                print("      %s" % row["url"])
        print("STATUS: OK  («지금» 값이다 — 편을 만드는 날 다시 잰다)")
        return 0

    # plus
    if not a.args:
        print("STATUS: FAIL productId 가 없다")
        return 2
    pid = a.args[0]
    hint = a.hint or (a.args[1] if len(a.args) > 1 else None)
    if not hint:
        print("STATUS: FAIL --hint 가 필요하다 (검색으로만 찾을 수 있다)")
        return 2
    row = plus_of(pid, hint)
    if row is None:
        print("🔴 검색 결과에서 그 강의를 못 찾았다 — «구독 아님»이 아니라 «못 쟀다»다")
        print("STATUS: OK (부분: 판정 불가 — --hint 를 바꿔 본다)")
        return 0
    print("제목    %s" % row["title"])
    print("구독    %s (추가 %s)" % ("포함" if row["plus"] else "🔴 미포함", row["plus_added_at"]))
    print("찜 %s · 난이도 %s · %s" % (row["liked"], row["difficulty"], row["author"]))
    print(row["url"])
    print("STATUS: OK  («지금» 값이다 — 편을 만드는 날 다시 잰다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
