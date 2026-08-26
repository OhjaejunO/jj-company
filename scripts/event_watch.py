# -*- coding: utf-8 -*-
r"""사건형 트리거 감시 — 감시처 조회·조건 적중·신규 줄 검출 (헤르메스 ② 입력 생성 · 2026-08-26 시범 신설).

    py scripts\event_watch.py [--list departments\marketing\event-watchlist.md] [--state logs\event-watch]
                              [--date YYYY-MM-DD] [--prompt-out PATH]

설계: 정관 §0 4층 — **감지는 결정적 코드가, 판정·알림 문안은 헤르메스 `sagun` 이** 한다. 이 스크립트는 LLM 을 부르지 않는다.
- 감시 목록(공개 정보만)을 읽어 감시처를 연다(urllib · 20초 · UA 명시).
- «조건 문자열» 유형: 본문에 조건 문자열이 있는가(대소문자 무시). 적중 줄을 최대 3개 남긴다.
- «신규 항목» 유형: 전날 베이스라인(`baseline.json`)의 줄 집합과 비교해 **새로 생긴 줄**을 최대 15개 남긴다.
  첫 실행은 베이스라인만 만들고 «베이스라인 생성» 으로 적는다.
- 차단·오류는 `blocked` 로 남긴다 — **미성립으로 적지 않는다**(정관 §0). 실행이 끝나면 오늘 스냅숏이 새 베이스라인이 된다.
출력: `<state>\<date>.json`(기계 판독) + 프롬프트 텍스트(헤르메스 -z 입력) — stdout 마지막 줄 `EVENT_WATCH=<json 경로>`.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import re
import sys
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jj-company event-watch/1.0"
LINE_MIN = 12          # 이보다 짧은 줄은 메뉴·잡음으로 본다
MAX_LINES = 400        # 페이지당 비교 줄 상한(앞쪽)


def parse_list(path):
    rows = []
    for ln in io.open(path, encoding="utf-8"):
        m = re.match(r"^\|\s*(E\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(https?://\S+)\s*\|\s*(.+?)\s*\|", ln)
        if not m:
            continue
        eid, name, cond, url, kind = m.groups()
        conds = [c.strip("` ") for c in re.findall(r"`([^`]+)`", cond)]
        rows.append({"id": eid, "name": name, "conds": conds, "url": url, "kind": "cond" if conds else "new"})
    return rows


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read(1_500_000)
        ctype = r.headers.get("Content-Type", "")
    txt = raw.decode("utf-8", errors="replace")
    if "xml" in ctype or txt.lstrip().startswith("<?xml") or "<rss" in txt[:500]:
        # RSS: 제목·날짜만 줄로
        items = re.findall(r"<item>(.*?)</item>", txt, re.S)
        lines = []
        for it in items:
            t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
            d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
            if t:
                lines.append(("%s | %s" % (t.group(1).strip(), d.group(1).strip() if d else "")).strip())
        return lines, "rss"
    t = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", txt)
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</tr>|</div>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&nbsp;|&#160;", " ", t)
    t = re.sub(r"&amp;", "&", t)
    lines = [re.sub(r"\s+", " ", x).strip() for x in t.split("\n")]
    lines = [x for x in lines if len(x) >= LINE_MIN]
    return lines[:MAX_LINES], "html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default=os.path.join("departments", "marketing", "event-watchlist.md"))
    ap.add_argument("--state", default=os.path.join("logs", "event-watch"))
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--prompt-out", default=None)
    a = ap.parse_args()
    os.makedirs(a.state, exist_ok=True)
    base_p = os.path.join(a.state, "baseline.json")
    baseline = json.load(io.open(base_p, encoding="utf-8")) if os.path.exists(base_p) else {}
    first = not baseline
    rows = parse_list(a.list)
    if not rows:
        raise SystemExit("🔴 event_watch: 감시 목록에 항목이 없다 — %s" % a.list)

    out = {"date": a.date, "baseline_first_run": first, "items": []}
    new_base = {}
    for r in rows:
        rec = {"id": r["id"], "name": r["name"], "url": r["url"], "kind": r["kind"], "status": "fetched"}
        try:
            lines, fmt = fetch(r["url"])
            rec["format"] = fmt
            rec["lines"] = len(lines)
            digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]
            rec["hash"] = digest
            if r["kind"] == "cond":
                hits = [ln for ln in lines if any(c.lower() in ln.lower() for c in r["conds"])]
                rec["cond_hits"] = hits[:3]
                # 2026-08-26 E1 설계 수정 — 등재 시점에 조건이 이미 성립이면 «성립(기 발생)» 으로 알린다. 침묵 편입 금지.
                # 첫 회차가 «베이스라인 생성» 이라는 이유로 적중을 삼키면 이미 난 사건이 영원히 안 보인다(E1 Seedance 2.5 실측).
                #   신규   = 적중 줄이 베이스라인의 적중 목록에 없다 (베이스라인이 있는 경우)
                #   기 발생 = 이 URL 의 적중 목록이 베이스라인에 아직 없다(등재 시점) 인데 적중이 있다
                #   기 알림 = 적중이 전부 베이스라인의 적중 목록 안 (이미 알린 것 — 재알림 안 함)
                prev_hits = baseline.get(r["url"], {}).get("cond_hits")
                if hits and prev_hits is None:
                    rec["cond_verdict"] = "기 발생"
                elif hits and any(h not in prev_hits for h in hits):
                    rec["cond_verdict"] = "신규"
                    rec["cond_new_hits"] = [h for h in hits if h not in prev_hits][:3]
                elif hits:
                    rec["cond_verdict"] = "기 알림"
                else:
                    rec["cond_verdict"] = "없음"
            prev = baseline.get(r["url"], {}).get("lines")
            if prev is None:
                rec["new_lines"] = []
                rec["new_lines_note"] = "베이스라인 생성 (비교 대상 없음)"
            else:
                prevset = set(prev)
                rec["new_lines"] = [ln for ln in lines if ln not in prevset][:15]
            entry = {"lines": lines, "hash": digest, "date": a.date}
            if r["kind"] == "cond":
                entry["cond_hits"] = sorted(set((baseline.get(r["url"], {}).get("cond_hits") or []) + [ln for ln in lines if any(c.lower() in ln.lower() for c in r["conds"])]))
            new_base[r["url"]] = entry
        except Exception as e:  # noqa: BLE001
            rec["status"] = "blocked"
            rec["error"] = str(e)[:200]
            if r["url"] in baseline:
                new_base[r["url"]] = baseline[r["url"]]      # 못 열었으면 옛 베이스라인을 유지 — 지우면 내일 «전부 신규» 가 된다
        out["items"].append(rec)

    jp = os.path.join(a.state, a.date + ".json")
    json.dump(out, io.open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(new_base, io.open(base_p, "w", encoding="utf-8"), ensure_ascii=False)

    # 헤르메스 입력 — 공개 정보(트리거명·URL·적중/신규 줄)만
    pl = ["오늘 %s 감시 결과다. 항목마다 «성립|미성립|확인 불가» 를 판정하고 성립 건만 알림으로 낸다." % a.date]
    if first:
        pl.append("주의: 오늘은 첫 실행이라 «신규 항목» 유형은 베이스라인 생성이다 — 신규 줄 판정은 «미성립(베이스라인 생성)» 으로 적는다.")
    pl.append("규칙: «조건 문자열» 유형은 스크립트가 붙인 판정 후보를 그대로 따른다 — 기 발생 → «성립(기 발생)» 알림 · 신규 → «성립(신규)» 알림 · 기 알림 → «미성립(기 알림)» · 없음 → «미성립». 등재 시점에 이미 성립인 조건을 침묵 편입하지 않는다.")
    for rec in out["items"]:
        pl.append("")
        pl.append("%s %s — %s" % (rec["id"], rec["name"], rec["url"]))
        if rec["status"] == "blocked":
            pl.append("  감시처 열기 실패: %s" % rec.get("error", ""))
            continue
        if rec["kind"] == "cond":
            pl.append("  조건 문자열 적중 %d건 · 판정 후보: %s: %s" % (
                len(rec.get("cond_hits", [])), rec.get("cond_verdict", "없음"),
                " // ".join(rec.get("cond_new_hits") or rec.get("cond_hits", [])) or "없음"))
        nl = rec.get("new_lines", [])
        note = rec.get("new_lines_note")
        pl.append("  새로 생긴 줄 %d건%s: %s" % (len(nl), (" (%s)" % note) if note else "", " // ".join(nl[:8]) or "없음"))
    prompt = "\n".join(pl)
    pp = a.prompt_out or os.path.join(a.state, a.date + ".prompt.txt")
    io.open(pp, "w", encoding="utf-8").write(prompt)
    print("items=%d fetched=%d blocked=%d first_run=%s" % (
        len(out["items"]), sum(1 for i in out["items"] if i["status"] == "fetched"),
        sum(1 for i in out["items"] if i["status"] == "blocked"), first))
    print("EVENT_WATCH=" + jp)
    print("EVENT_PROMPT=" + pp)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
