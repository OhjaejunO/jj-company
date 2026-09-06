# -*- coding: utf-8 -*-
r"""ig_watch.py — 우리 인스타 계정의 게시물 목록을 읽는다 (A등급 · 읽기 전용).

정관 §0 «C등급 갚기» ②: 에이전트가 «발행 사실»을 스스로 읽는 경로. 쓰기 호출은 없다.
토큰은 `IG_TOKEN`(환경변수 → HKCU\Environment) — publish_threads.load_token 과 같은 자리이고
**값은 어디에도 찍지 않는다.**

    py scripts\ig_watch.py            # 계정 + 최근 게시물 → logs\ig-data\media_<날짜>.json + 요약
    py scripts\ig_watch.py --new      # 발행로그에 없는 shortcode 만 골라 «발행 감지» 로 찍는다
    py scripts\ig_watch.py --self-test

🔴 못 잡는 것: 인사이트(좋아요 외 저장·도달)는 이 토큰 종류(Instagram 로그인)로 안 열릴 수 있다 — 실측으로 판정.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs" / "ig-data"
PUBLOG = Path(r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop\발행로그.md")
API = "https://graph.instagram.com/v21.0"
FIELDS = "id,shortcode,media_type,permalink,timestamp,caption,like_count,comments_count"
KST = dt.timezone(dt.timedelta(hours=9))


def load_token():
    t = os.environ.get("IG_TOKEN")
    if not t:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            t = winreg.QueryValueEx(k, "IG_TOKEN")[0]
    t = (t or "").strip()
    if not t or (t.startswith("<") and t.endswith(">")):
        raise SystemExit("🔴 IG_TOKEN 이 없다 — setx IG_TOKEN 으로 넣는다")
    return t


def get(token, path, **params):
    params["access_token"] = token
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace").replace(token, "<TOKEN>")
        raise SystemExit(f"🔴 API {e.code} {path}: {body[:300]}")


def fetch(token, limit=50):
    me = get(token, "me", fields="id,username,media_count")
    media = get(token, "me/media", fields=FIELDS, limit=limit).get("data", [])
    for m in media:
        m["shortcode"] = m.get("shortcode") or m.get("permalink", "").rstrip("/").rsplit("/", 1)[-1]
        m["kst"] = dt.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")).astimezone(KST).strftime("%Y-%m-%d %H:%M")
    return me, media


def publog_shortcodes(text):
    """발행로그 본문에 적힌 instagram.com/p/<code> 또는 /reel/<code> 를 전부 모은다."""
    return set(re.findall(r"instagram\.com/(?:p|reel)/([A-Za-z0-9_-]{8,})", text))


def new_posts(media, known):
    return [m for m in media if m["shortcode"] not in known]


def main(argv):
    if "--self-test" in argv:
        return self_test()
    token = load_token()
    me, media = fetch(token)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(KST).strftime("%Y%m%d")
    (OUT / f"media_{stamp}.json").write_text(json.dumps({"me": me, "media": media}, ensure_ascii=False, indent=1), "utf-8")
    print(f"account @{me['username']} media_count={me['media_count']} fetched={len(media)}")
    for m in media[:5]:
        cap = (m.get("caption") or "").split("\n")[0][:40]
        print(f"  {m['shortcode']}  {m['kst']}  {m['media_type']:<9} like={m.get('like_count')} cm={m.get('comments_count')}  {cap}")
    if "--new" in argv:
        # ① 지난 조회 스냅샷 대비 — «발행 감지»는 이 축이다
        prev = sorted(p for p in OUT.glob("media_*.json") if p.name != f"media_{stamp}.json")
        if prev:
            seen = {m["shortcode"] for m in json.loads(prev[-1].read_text("utf-8"))["media"]}
            fresh = new_posts(media, seen)
            print(f"지난 조회({prev[-1].name}) 대비 새 게시물 {len(fresh)}건")
            for m in fresh:
                print(f"  NEW {m['shortcode']}  {m['kst']}  {m['permalink']}")
        else:
            print("지난 조회 스냅샷 없음 — 이번 회차가 기준선")
        # ② 발행로그 URL 대조 — URL 칸이 있는 행만 잡히므로 «미기록»이 아니라 «URL 미기재»로 읽는다
        if PUBLOG.is_file():
            known = publog_shortcodes(PUBLOG.read_text("utf-8"))
            miss = new_posts(media, known)
            print(f"발행로그에 URL 로 적힌 게시물 {len(known)}건 · API 에는 있는데 URL 로 안 적힌 것 {len(miss)}건")
        else:
            print(f"🟡 발행로그 없음 {PUBLOG} — URL 대조 생략")
    print("STATUS: OK")
    return 0


def self_test():
    text = "…(https://www.instagram.com/p/Dc8faxakrTb/) … instagram.com/reel/ABCdef12345/ …"
    known = publog_shortcodes(text)
    assert known == {"Dc8faxakrTb", "ABCdef12345"}, known
    media = [{"shortcode": "Dc8faxakrTb"}, {"shortcode": "NEWNEW12345"}]
    assert [m["shortcode"] for m in new_posts(media, known)] == ["NEWNEW12345"]
    assert new_posts([{"shortcode": "Dc8faxakrTb"}], known) == [], "이미 있는 것이 새것으로 읽혔다"
    print("ok   발행로그 shortcode 추출 2건 · 새 게시물 판별 · 기존 게시물 제외")
    print("STATUS: OK")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
