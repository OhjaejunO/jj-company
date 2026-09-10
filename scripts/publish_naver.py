# -*- coding: utf-8 -*-
r"""네이버 블로그 발행 워커 (2단계) — 임시글을 불러와 발행 창에서 카테고리·공개·태그·시각을 넣고 «발행»을 누른다.

    py scripts\publish_naver.py --post 2026-09-07_Fable_Mythos5_1                       ← 드라이런: 발행 창까지 채우고 «발행» 은 안 누른다
    py scripts\publish_naver.py --post 2026-09-07_Fable_Mythos5_1 --publish             ← 실제 발행
    py scripts\publish_naver.py --self-test

## 🔴 발행 자격 (2026-09-10 개정 — 승인 파일 장치는 폐기했다)
종전에는 `publish_approval\blog-<stem>.json` 이 트리거였다. JJ 지시로 그 자리를 없앴다 —
**게이트 통과가 곧 자격이다.** 워커는 발행 직전 `blogcheck.py --publish` 를 스스로 돌리고,
`STATUS: OK` 가 아니면 «발행» 을 누르지 않는다(`STATUS: FAIL blogcheck`).
`--publish` 를 명시하지 않으면 어떤 경우에도 누르지 않는다(기본값 드라이런).
근거는 되돌림 비용이다(정관 §0) — 네이버 글은 삭제·비공개 전환으로 되돌아가고 원고는 `reports\blog\` 에 남는다.

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
import io
import json
import os
import re
import subprocess
import sys

try:  # cp949 콘솔에서 «—» 가 든 로그 줄이 UnicodeEncodeError 로 죽었다(2026-09-07 실측 · 파일은 이미 써진 뒤)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naver_draft as nd  # noqa: E402

HQ = nd.HQ
SHOT_DIR = os.path.join(HQ, "logs", "naver-publish")
BLOGCHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blogcheck.py")
TAG_CHARS = 100          # 네이버 태그 칸 글자 상한 (# 포함, JJ 실측 2026-09-06)
TAG_MAX = 30
P = "const p=d.querySelector('[class*=layer_content_set_publish]'); if(!p) return 'nopanel';"


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


def plan_problem(tags, category, when):
    """발행 전 «형식» 확인 — 종전 `check_approval` 이 승인 파일에 대고 재던 것들이다 (2026-09-10 개정).

    승인 파일이 사라졌으므로 잴 대상이 원고·인자로 바뀌었을 뿐 축은 그대로다:
    태그 개수·글자 상한 · 카테고리 비었는가 · 예약 시각 꼴.
    (원고 해시 대조는 축이 없어졌다 — 대조할 «승인 시점의 해시» 가 없다.
     그 자리는 발행 직전 `blogcheck --publish` 가 대신한다 — 지금 파일을 지금 잰다.)
    """
    bad = []
    if not category:
        bad.append("category-empty")
    tp = tags_problem(tags)
    if tp:
        bad.append("tags: " + tp)
    tm = time_problem(when)
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
    category, when = a.category, a.at
    bad = plan_problem(tags, category, when)
    if bad:
        for b in bad:
            log("  plan| " + b)
        log("STATUS: FAIL " + bad[0].split(":")[0]); return 1
    # 🔴 게이트가 곧 발행 자격이다 (2026-09-10 · 승인 파일 폐기). 드라이런에서도 돈다 —
    #    통과 못 한 원고로 에디터를 채워 두면 사람이 «발행» 을 누를 수 있게 된다.
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
    tags = ["a", "b"]
    cases = [
        ("정상 통과", (tags, "AI 뉴스", "now"), []),
        ("카테고리 비면 걸림", (tags, "", "now"), ["category-empty"]),
        ("시각 꼴 틀리면 걸림", (tags, "AI 뉴스", "9:05"), ["time"]),
        ("태그 0개면 걸림", ([], "AI 뉴스", "now"), ["tags"]),
    ]
    fails = 0
    for name, args, expect in cases:
        got = [b.split(":")[0] for b in plan_problem(*args)]
        res = got == expect
        fails += not res
        print("%s %s: %s" % ("ok  " if res else "FAIL", name, got))
    _all = io.open(__file__, encoding="utf-8").read()
    _src = _all.split("def run(")[1]
    extra = [
        ("태그 100자 초과 걸림", tags_problem(["가나다라마바사아자차"] * 10) is not None),
        ("태그 100자 안 통과", tags_problem(["가나다라"] * 10) is None),
        ("예약 분 단위 걸림", time_problem("09:05") is not None),
        ("예약 09:00 통과", time_problem("09:00") is None),
        ("발행 클릭(o.confirm)이 코드에 한 번, --publish 분기 안에만 있다",
         _src.count("o.confirm(") == 1 and _src.index("if a.publish:") < _src.index("o.confirm(") < _src.index("_dry.png")),
        # 🔴 승인 폐기의 역검증 — 축을 «없앴다» 는 코드가 남아 있지 않다는 것으로만 증명된다.
        # 🔴 승인 폐기의 역검증 — 축을 «없앴다» 는 그 자리가 비었다는 것으로만 증명된다.
        #    문서 문장(«종전에는 …») 은 대상이 아니라 **호출 가능한 자리**만 본다.
        ("승인 장치 세 자리가 다 비었다",
         not [n for n in ("APPROVAL_DIR", "check_approval", "build_draft") if n in globals()]),
        ("--draft-approval 플래그가 없다", 'add_argument("--draft-' + 'approval"' not in _all),
        # 게이트가 «발행 클릭보다 앞»에 있는가. 순서가 뒤집히면 자격 검사가 사후 확인이 된다.
        ("gate() 가 o.confirm() 보다 앞에서 불린다", _src.index("if not gate(") < _src.index("o.confirm(")),
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
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    if not a.post:
        ap.error("--post <stem>")
    raise SystemExit(run(a, print))
