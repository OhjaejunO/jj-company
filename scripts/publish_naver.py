# -*- coding: utf-8 -*-
r"""네이버 블로그 발행 워커 (2단계) — 임시글을 불러와 발행 창에서 카테고리·공개·태그·시각을 넣고 «발행»을 누른다.

    py scripts\publish_naver.py --post 2026-09-07_Fable_Mythos5_1 --draft-approval      ← 승인 «초안» 을 reports\ 에
    py scripts\publish_naver.py --post 2026-09-07_Fable_Mythos5_1                       ← 드라이런: 발행 창까지 채우고 «발행» 은 안 누른다
    py scripts\publish_naver.py --post 2026-09-07_Fable_Mythos5_1 --publish             ← 실제 발행 (publish_approval\ 승인 필수)
    py scripts\publish_naver.py --self-test

## 승인 (정관 §0 «승인은 채팅 문장이 아니라 파일이다» — Threads 장치 그대로)
① 에이전트: `--draft-approval` → `reports\blog-<stem>.approval.json` 초안 (원고 해시·제목·태그·카테고리·시각)
② JJ: `scripts\move-approval.bat` 으로 `publish_approval\blog-<stem>.json` 으로 옮긴다. **이동이 곧 서명이다.**
③ 워커: 발행 직전 셋을 본다 — 승인 해시 = 지금 원고 파일 해시 · 대상 stem 일치 · 승인 파일이 `publish_approval\` 에 있을 것.
   하나라도 어긋나면 «발행» 을 누르지 않고 `STATUS: FAIL approval-…` 로 멈춘다. 승인 폴더가 에이전트 손에 닿지 않는다는
   증명은 래퍼 `publish-naver.ps1` 의 프로브가 매 회차 한다.

## 실측으로 정한 경로 (2026-09-06 · ai-tomangchi-lab)
- 임시글 목록: 헤더 `save_count_btn__` → `.layer_popup__WjlfW` 의 `li` · 불러오기는 `article_button__` (삭제는 `delete_button__`, 안 누른다).
- 발행 창: 헤더 `publish_btn__` → `.layer_content_set_publish__…`. 카테고리 `selectbox_button__` → `.option_list_layer__ li`.
  공개 `#open_public` · 태그 `#tag-input`(placeholder «태그 입력 (최대 30개)», 글자 상한 100 — JJ 실측) · 시각 `#radio_time1`(현재)
  `#radio_time2`(예약: `.hour_option__`·`.minute_option__` select, 분은 10분 단위) · 최종 `.confirm_btn__`.
- 예약은 **오늘 날짜만** 다룬다 — 날짜 입력은 datepicker 라 손대지 않는다. 내일 예약이 필요하면 내일 아침에 돌린다.
- 🔴 `orca type/keypress` 금지(활성 창에 키가 간다). 전부 페이지 안 JS 이벤트다.

## 🔴 못 재는 것 (§0 4층 ④)
- 발행 뒤 글이 «검색 허용»으로 실제 노출되는지, 예약이 그 시각에 실제로 나가는지는 네이버 쪽이라 사람이 본다.
- 임시글 본문이 원고 md 와 같은지는 **제목 일치**로만 본다 — 본문은 에디터가 재구성하므로 해시 대조가 안 된다.
"""
import argparse
import base64
import datetime
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naver_draft as nd  # noqa: E402

HQ = nd.HQ
APPROVAL_DIR = os.path.join(HQ, "publish_approval")
DRAFT_DIR = os.path.join(HQ, "reports")
SHOT_DIR = os.path.join(HQ, "logs", "naver-publish")
BLOGCHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blogcheck.py")
TAG_CHARS = 100          # 네이버 태그 칸 글자 상한 (# 포함, JJ 실측 2026-09-06)
TAG_MAX = 30
P = "const p=d.querySelector('[class*=layer_content_set_publish]'); if(!p) return 'nopanel';"


def sha256_file(path):
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()


def tags_problem(tags):
    if not tags:
        return "태그 0개"
    if len(tags) > TAG_MAX:
        return "태그 %d개 (최대 %d)" % (len(tags), TAG_MAX)
    n = sum(len("#" + t) for t in tags) + (len(tags) - 1)
    if n > TAG_CHARS:
        return "태그 글자 %d (최대 %d, # 과 띄어쓰기 포함)" % (n, TAG_CHARS)
    return None


def time_problem(when):
    if when == "now":
        return None
    m = re.match(r"^(\d{2}):(\d{2})$", when or "")
    if not m or int(m.group(1)) > 23 or m.group(2) not in ("00", "10", "20", "30", "40", "50"):
        return "시각 %r (now 또는 HH:MM, 분은 10분 단위)" % when
    return None


def load_post(stem):
    p, meta, body = nd.read_post(stem)
    title, _chunks, tags, _images = nd.parse_blocks(body)
    return p, meta, title, tags


def build_draft(stem, md_path, title, tags, category, when):
    return {
        "ep": "blog-" + stem,
        "body_sha256": sha256_file(md_path),
        "title": title,
        "tags": tags,
        "category": category,
        "open": "public",
        "publish_time": when,
        "drafted_by": "publish_naver.py --draft-approval",
        "drafted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "manuscript": os.path.basename(md_path),
        "_승인_방법": ("이 파일을 scripts\\move-approval.bat 으로 publish_approval\\ 로 옮기면 "
                   "그것이 승인이다. reports\\ 에 있는 동안은 승인이 아니다."),
    }


def check_approval(appr, stem, md_path, title, tags):
    bad = []
    if appr.get("ep") != "blog-" + stem:
        bad.append("ep-mismatch: 승인 %r ≠ 대상 %r" % (appr.get("ep"), "blog-" + stem))
    got = sha256_file(md_path)
    if appr.get("body_sha256") != got:
        bad.append("approval-stale: 원고 해시 불일치 (승인 %s… / 실물 %s…)" % (str(appr.get("body_sha256"))[:12], got[:12]))
    if appr.get("title") != title:
        bad.append("title-mismatch")
    if list(appr.get("tags") or []) != list(tags):
        bad.append("tags-mismatch")
    if not appr.get("category"):
        bad.append("category-empty")
    tp = tags_problem(appr.get("tags") or [])
    if tp:
        bad.append("tags: " + tp)
    tm = time_problem(appr.get("publish_time"))
    if tm:
        bad.append("time: " + tm)
    return bad


# ---------------------------------------------------------------- 브라우저
class Pub(nd.Orca):
    def load_draft(self, title):
        r = self.in_frame("const b=[...d.querySelectorAll('button')].find(x=>/save_count_btn/.test(x.className)); if(!b) return 'none'; b.click(); return 'opened';")
        if r != "opened":
            raise nd.Missing("임시글 목록 버튼 없음")
        time.sleep(2)
        self.eval("(()=>{const w=document.querySelector('#mainFrame').contentWindow; w.confirm=()=>true; return 1;})()")   # «작성 중인 글을 버릴까요» 류 → 예 (새 탭이라 버릴 것이 없다)
        js = ("const p=d.querySelector('[class*=layer_popup]'); if(!p) return 'nopopup';"
              "const li=[...p.querySelectorAll('li')].find(x=>(x.innerText||'').replace(/\\s+/g,' ').includes(%s)); if(!li) return 'no-entry';"
              "const b=[...li.querySelectorAll('button')].find(x=>/article_button/.test(x.className)); if(!b) return 'no-btn'; b.click(); return 'clicked';") % json.dumps(title[:40])
        r = self.in_frame(js)
        if r != "clicked":
            raise nd.Missing("임시글 «%s…» 불러오기 실패: %s" % (title[:20], r))
        for _ in range(20):
            time.sleep(1)
            got = (self.in_frame("return (d.querySelector('.se-title-text')||{}).innerText||'';") or "").replace("\xa0", " ").strip()
            if got == title:
                return
        raise nd.Missing("불러온 글 제목이 다르다: %r" % got)

    def open_panel(self):
        self.in_frame("const b=[...d.querySelectorAll('button')].find(x=>/publish_btn__/.test(x.className)); b.click(); return 1;")
        time.sleep(3)
        if self.in_frame(P + "return 'ok';") != "ok":
            raise nd.Missing("발행 창이 안 열림")

    def set_category(self, name):
        self.in_frame(P + "p.querySelector('[class*=selectbox_button]').click(); return 1;")
        time.sleep(1.5)
        r = self.in_frame(P + "const li=[...p.querySelectorAll('[class*=option_list_layer] li')].find(x=>(x.innerText||'').trim()===%s); if(!li) return 'no-cat:'+[...p.querySelectorAll('[class*=option_list_layer] li')].map(x=>x.innerText.trim()).join('|'); (li.querySelector('button,span')||li).click(); return 'ok';" % json.dumps(name))
        time.sleep(1)
        got = self.in_frame(P + "return (p.querySelector('[class*=selectbox_button]').innerText||'').trim();")
        if r != "ok" or got != name:
            raise nd.Missing("카테고리 «%s» 선택 실패: %s / 지금 %r" % (name, r, got))

    def set_public(self):
        r = self.in_frame(P + "const r=p.querySelector('#open_public'); if(!r.checked) r.click(); return r.checked;")
        if r is not True:
            raise nd.Missing("전체공개 선택 실패")

    def tag_text(self):
        return (self.in_frame(P + "const t=p.querySelector('[class*=option_tag]'); return t?t.innerText:'';") or "").replace("\xa0", " ")

    def add_tag(self, tag):
        js = (P + "const i=p.querySelector('#tag-input'); const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
              "set.call(i, %s); i.dispatchEvent(new Event('input',{bubbles:true}));"
              "for(const ty of ['keydown','keypress','keyup']) i.dispatchEvent(new KeyboardEvent(ty,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true}));"
              "return 'sent';") % json.dumps(tag)
        self.in_frame(js)
        time.sleep(0.8)
        if tag not in self.tag_text():
            raise nd.Missing("태그 «%s» 가 안 붙음 (지금: %r)" % (tag, self.tag_text()[:80]))

    def clear_tags(self):
        """드라이런 뒤 붙인 태그를 떼어 임시글에 남지 않게 한다. 칩(span.tag__)은 클릭으로 안 지워지고 입력칸 Backspace 가
        하나씩 지운다(2026-09-06 실측)."""
        cnt = P + "return p.querySelectorAll('[class*=option_tag] span[class^=tag__]').length;"
        for _ in range(TAG_MAX + 1):
            if not (self.in_frame(cnt) or 0):
                break
            self.in_frame(P + "const i=p.querySelector('#tag-input'); i.focus(); for(const ty of ['keydown','keyup']) i.dispatchEvent(new KeyboardEvent(ty,{key:'Backspace',code:'Backspace',keyCode:8,which:8,bubbles:true,cancelable:true})); return 1;")
            time.sleep(0.4)
        return self.in_frame(cnt) or 0

    def set_time(self, when):
        if when == "now":
            r = self.in_frame(P + "const r=p.querySelector('#radio_time1'); r.click(); return r.checked;")
            if r is not True:
                raise nd.Missing("«현재» 선택 실패")
            return
        hh, mm = when.split(":")
        self.in_frame(P + "p.querySelector('#radio_time2').click(); return 1;")
        time.sleep(1.5)
        js = (P + "const set=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;"
              "const h=p.querySelector('[class*=hour_option]'), m=p.querySelector('[class*=minute_option]'); if(!h||!m) return 'no-select';"
              "set.call(h, %s); h.dispatchEvent(new Event('change',{bubbles:true})); set.call(m, %s); m.dispatchEvent(new Event('change',{bubbles:true}));"
              "return h.value+':'+m.value;") % (json.dumps(hh), json.dumps(mm))
        r = self.in_frame(js)
        time.sleep(0.8)
        got = self.in_frame(P + "const h=p.querySelector('[class*=hour_option]'), m=p.querySelector('[class*=minute_option]'); return h.value+':'+m.value+'|'+p.querySelector('#radio_time2').checked;")
        if got != when + "|true":
            raise nd.Missing("예약 시각 %s 설정 실패: %s / %s" % (when, r, got))
        warn = self.in_frame(P + "const t=p.querySelector('[class*=option_time]'); return t?t.innerText:'';") or ""
        if "이후로" in warn:      # «현재 시간 이후로 설정해주세요.» — 지난 시각은 네이버가 안 받는다 (2026-09-06 실측)
            raise nd.Missing("예약 시각 %s 이 지났다: %s" % (when, " ".join(warn.split())[:60]))

    def screenshot(self, path):
        b64 = None
        for _ in range(3):        # 큰 페이지 직후 «runtime closed the connection» 이 한 번 나온다(2026-09-06 실측) — 3번까지
            d = self.run("screenshot")
            b64 = (d.get("result") or {}).get("data") if d.get("ok") else None
            if b64:
                break
            time.sleep(3)
        if not b64:
            print("screenshot failed: %s" % json.dumps(d, ensure_ascii=False)[:200])
            return None
        io.open(path, "wb").write(base64.b64decode(b64))
        return path

    def confirm(self):
        before = self.url()
        r = self.in_frame(P + "const b=p.querySelector('[class*=confirm_btn]'); if(!b||b.disabled) return 'no-confirm'; b.click(); return 'clicked';")
        if r != "clicked":
            raise nd.Missing("최종 «발행» 버튼: %s" % r)
        for _ in range(30):
            time.sleep(1)
            u = self.url() or ""
            if u != before and "Redirect=Write" not in u:
                return u
        return self.url()


def gate(md_path, log):
    r = subprocess.run([sys.executable, BLOGCHECK, "--publish", md_path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
    log("gate| " + last)
    return last.startswith("STATUS: OK")


def run(a, log):
    md_path, _meta, title, tags = load_post(a.post)
    if a.draft_approval:
        tp = tags_problem(tags) or time_problem(a.at)
        if tp:
            log("STATUS: FAIL draft " + tp); return 1
        if not gate(md_path, log):
            log("STATUS: FAIL blogcheck (승인 초안을 만들지 않는다)"); return 1
        out = os.path.join(DRAFT_DIR, "blog-" + a.post + ".approval.json")
        io.open(out, "w", encoding="utf-8").write(json.dumps(build_draft(a.post, md_path, title, tags, a.category, a.at), ensure_ascii=False, indent=1))
        log("approval draft -> " + out)
        log("STATUS: OK (초안 — 서명은 JJ 가 move-approval.bat 으로)"); return 0

    appr = None
    if a.publish:
        ap = os.path.join(APPROVAL_DIR, "blog-" + a.post + ".json")
        if not os.path.exists(ap):
            log("STATUS: FAIL approval-missing " + ap); return 1
        appr = json.loads(io.open(ap, encoding="utf-8").read())
        bad = check_approval(appr, a.post, md_path, title, tags)
        if bad:
            for b in bad:
                log("  approval| " + b)
            log("STATUS: FAIL approval-" + bad[0].split(":")[0]); return 1
        category, when = appr["category"], appr["publish_time"]
    else:
        category, when = a.category, a.at
        tp = tags_problem(tags) or time_problem(when)
        if tp:
            log("STATUS: FAIL " + tp); return 1
    if not gate(md_path, log):
        log("STATUS: FAIL blogcheck"); return 1

    os.makedirs(SHOT_DIR, exist_ok=True)
    o = Pub(nd.find_page(a.blog, fresh=True))
    if not nd.open_editor(o, a.blog, log):
        return 1
    try:
        o.load_draft(title); log("draft loaded: " + title[:40])
        o.open_panel()
        o.set_category(category); log("category: " + category)
        o.set_public(); log("open: public")
        for t in tags:
            o.add_tag(t)
        log("tags: %d" % len(tags))
        o.set_time(when); log("time: " + when)
        if a.publish:
            url = o.confirm()
            shot = o.screenshot(os.path.join(SHOT_DIR, a.post + "_published.png"))
            log("published url=%s shot=%s" % (url, shot))
            log("STATUS: OK published %s" % url); return 0
        shot = o.screenshot(os.path.join(SHOT_DIR, a.post + "_dry.png"))
        left = o.clear_tags()
        log("dry: panel filled, «발행» not clicked, tags cleared (left: %s) shot=%s" % (left, shot))
        log("STATUS: OK (dry run — 발행 안 함)"); return 0
    except nd.Missing as e:
        o.screenshot(os.path.join(SHOT_DIR, a.post + "_fail.png"))
        log("STATUS: FAIL selector %s" % e); return 1


def self_test():
    d = tempfile.mkdtemp()
    md = os.path.join(d, "x.md")
    io.open(md, "w", encoding="utf-8").write("---\nkind: topic\n---\n# 제목 (2026년 9월)\n## 태그\n#a #b\n")
    tags = ["a", "b"]
    ok = build_draft("x", md, "제목 (2026년 9월)", tags, "AI 뉴스", "now")
    cases = [
        ("정상 승인 통과", dict(ok), []),
        ("ep 불일치 걸림", dict(ok, ep="blog-y"), ["ep-mismatch"]),
        ("원고 바뀌면 걸림", dict(ok, body_sha256="0" * 64), ["approval-stale"]),
        ("태그 바뀌면 걸림", dict(ok, tags=["a"]), ["tags-mismatch"]),
        ("카테고리 비면 걸림", dict(ok, category=""), ["category-empty"]),
        ("시각 꼴 틀리면 걸림", dict(ok, publish_time="9:05"), ["time"]),
    ]
    fails = 0
    for name, appr, expect in cases:
        bad = check_approval(appr, "x", md, "제목 (2026년 9월)", tags)
        got = [b.split(":")[0] for b in bad]
        res = got == expect
        fails += not res
        print("%s %s: %s" % ("ok  " if res else "FAIL", name, got))
    _src = io.open(__file__, encoding="utf-8").read().split("def run(")[1]
    extra = [
        ("태그 100자 초과 걸림", tags_problem(["가나다라마바사아자차"] * 10) is not None),
        ("태그 100자 안 통과", tags_problem(["가나다라"] * 10) is None),
        ("예약 분 단위 걸림", time_problem("09:05") is not None),
        ("예약 09:00 통과", time_problem("09:00") is None),
        ("발행 클릭(o.confirm)이 코드에 한 번, --publish 분기 안에만 있다",
         _src.count("o.confirm(") == 1 and _src.index("if a.publish:") < _src.index("o.confirm(") < _src.index("_dry.png")),
    ]
    for name, res in extra:
        fails += not res
        print("%s %s" % ("ok  " if res else "FAIL", name))
    print("STATUS: %s" % ("OK" if not fails else "FAIL %d" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--post")
    ap.add_argument("--blog", default=os.environ.get("NAVER_BLOG_ID", "ai-tomangchi-lab"))
    ap.add_argument("--category", default="AI 뉴스")
    ap.add_argument("--at", default="now", help="now 또는 HH:MM (오늘 예약, 분은 10분 단위)")
    ap.add_argument("--draft-approval", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    if not a.post:
        ap.error("--post <stem>")
    raise SystemExit(run(a, print))
