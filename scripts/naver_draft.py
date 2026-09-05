# -*- coding: utf-8 -*-
r"""네이버 블로그 초안 넣기 (1단계) — 승인된 초안 md 를 Orca 내장 브라우저로 스마트에디터에 채우고 «임시저장»한다.

    py scripts\naver_draft.py --post 2026-09-07_주간1호 --blog <블로그id>   ← 제목·본문·사진 채우고 임시저장, 화면 캡처
    py scripts\naver_draft.py --probe --blog <블로그id>                     ← 에디터 화면 요소 덤프 (선택자 손보기용)
    py scripts\naver_draft.py --self-test

## 이 스크립트는 발행하지 않는다 (JJ 판정 2026-09-05 «1단계만 먼저»)
«발행» 버튼·공개 설정·태그 입력은 **코드에 없다.** 하는 일은 사람이 복붙하던 것 — 제목 치기, 본문 붙여넣기,
사진 올리기 — 까지이고, 마지막에 «임시저장»(비공개 임시글)을 누른다. 발행은 JJ 가 에디터를 열어 태그를 달고
«발행»을 누른다. 그래서 정관 §0 의 C등급(발행)은 그대로다.

## 왜 API 가 아니라 브라우저인가
네이버 블로그에는 공식 글쓰기 API 가 없다(2026-09-05 확인). 로그인은 사람이 Orca 탭에서 한다 — 쿠키를 읽지 않는다.

## 🔴 이 스크립트가 증명하지 못하는 것 (§0 4층 ④)
- 스마트에디터가 붙여넣은 HTML(소제목·표·굵게)을 어떻게 바꾸는지는 화면 캡처로만 본다 — 사람 육안.
- 선택자(`SEL`)는 2026-09-05 추정값이다. 틀리면 «요소 못 찾음» 으로 멈추지 엉뚱한 곳을 누르지 않는다.
"""
import argparse
import html
import io
import json
import os
import re
import subprocess
import sys
import time

HQ = r"C:\Users\ojaej\jj-company"
BLOG_DIR = os.path.join(HQ, "reports", "blog")
SHOT_DIR = os.path.join(HQ, "logs", "naver-draft")
WORKSHOP_ROOT = r"C:\Users\ojaej\orca\tomangchi-lab.github.io"
STEP_PAUSE = 1.2

#: 스마트에디터 ONE 선택자 — 🔴 추정값. `--probe` 로 실물을 덤프해 맞춘다.
SEL = {
    "editor_ready": ".se-main-container",
    "title": ".se-title-text [contenteditable], .se-title-text",
    "body": ".se-main-container .se-component.se-text [contenteditable], .se-main-container [contenteditable]",
    "file_input": "input[type=file][accept*=image], input[type=file]",
    "save_btn": "button[class*=save_btn]",
    "login_hint": "#frmNIDLogin, input#id",
}
WRITE_URL = "https://blog.naver.com/{blog}?Redirect=Write&"


# ---------------------------------------------------------------- 원고 → HTML
def read_post(stem):
    p = os.path.join(BLOG_DIR, stem + ".md")
    md = io.open(p, encoding="utf-8").read()
    fm = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    meta = dict(re.findall(r"^(\w+):\s*(.+)$", fm.group(1), re.M)) if fm else {}
    return p, meta, (md[fm.end():] if fm else md)


def _section(md, name):
    m = re.search(r"^## %s\s*$(.*?)(?=^## |\Z)" % re.escape(name), md, re.S | re.M)
    return (m.group(1) if m else "").strip()


def _inline(s):
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(s))


def md_to_html(sec):
    out, table = [], []

    def flush():
        if not table:
            return
        rows = [r for r in table if not re.match(r"^\|[-| ]+\|$", r)]
        cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
        out.append("<table>" + "".join(
            "<tr>" + "".join(("<th>%s</th>" if i == 0 else "<td>%s</td>") % _inline(c) for c in row) + "</tr>"
            for i, row in enumerate(cells)) + "</table>")
        table[:] = []

    for ln in sec.splitlines():
        s = ln.rstrip()
        if s.startswith("|"):
            table.append(s); continue
        flush()
        if not s:
            continue
        out.append("<h3>%s</h3>" % _inline(s[4:]) if s.startswith("### ") else "<p>%s</p>" % _inline(s))
    flush()
    return "\n".join(out)


def parse_blocks(body):
    """초안 md → (title, html, tags, images). 태그는 JJ 가 발행 창에서 붙이도록 텍스트로만 돌려준다."""
    title = re.search(r"^# (.+)$", body, re.M).group(1).strip()
    parts = []
    for name in ("요약", "본문", "FAQ", "토망치랩 한마디", "관련글"):
        sec = _section(body, name)
        if sec:
            if name != "요약":
                parts.append("<h2>%s</h2>" % html.escape(name))
            parts.append(md_to_html(sec))
    tags = re.findall(r"#(\S+)", _section(body, "태그"))
    images = []
    for ln in _section(body, "이미지").splitlines():
        m = re.match(r"^\d+\.\s+`([^`]+)`\s+—\s+(.*)$", ln.strip())
        if m:
            images.append({"path": m.group(1), "caption": m.group(2)})
    return title, "\n".join(parts), tags, images


def resolve_image(path):
    return path if os.path.isabs(path) else os.path.join(WORKSHOP_ROOT, path)


# ---------------------------------------------------------------- 브라우저 (Orca CLI)
class Missing(Exception):
    pass


class Orca(object):
    def __init__(self, page):
        self.page = page

    def run(self, *args, timeout=90):
        r = subprocess.run(["orca", *args, "--page", self.page, "--json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        m = re.search(r"\{.*\}", r.stdout, re.S)
        return json.loads(m.group(0)) if m else {"ok": False, "raw": (r.stdout + r.stderr)[-400:]}

    def eval(self, js):
        # `orca eval` = Orca 내장 브라우저 탭 안에서 JS 를 돌리는 CLI 다(파이썬 eval 아님). 여기 넘기는 JS 는
        # 전부 이 파일의 고정 문자열이고, 원고 본문은 json.dumps 로 감싸 데이터로만 들어간다.
        d = self.run("eval", "--expression", js)
        res = d.get("result", {}).get("result") if d.get("ok") else None
        if isinstance(res, str):
            res = res.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
        return res

    def exists(self, css):
        return bool(self.eval("!!document.querySelector(%s)" % json.dumps(css)))

    def focus_css(self, css):
        ok = self.eval("(()=>{const e=document.querySelector(%s); if(!e) return false; e.scrollIntoView(); e.focus(); e.click(); return true;})()" % json.dumps(css))
        if not ok:
            raise Missing("요소 없음: %s" % css)
        time.sleep(STEP_PAUSE)

    def click_css(self, css):
        ok = self.eval("(()=>{const e=document.querySelector(%s); if(!e) return false; e.scrollIntoView(); e.click(); return true;})()" % json.dumps(css))
        if not ok:
            raise Missing("요소 없음: %s" % css)
        time.sleep(STEP_PAUSE)

    def type(self, text):
        d = self.run("type", "--input", text)
        if not d.get("ok"):
            raise Missing("type 실패: %s" % str(d)[:200])
        time.sleep(STEP_PAUSE)

    def paste_html(self, css, html_text):
        """붙여넣기 이벤트를 합성해 HTML 을 넣는다 — 사람이 웹에서 복사해 붙이는 것과 같은 경로."""
        js = ("(()=>{const e=document.querySelector(%s); if(!e) return 'missing'; e.focus();"
              "const dt=new DataTransfer(); dt.setData('text/html', %s); dt.setData('text/plain', %s);"
              "e.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true})); return 'ok';})()"
              ) % (json.dumps(css), json.dumps(html_text), json.dumps(re.sub(r"<[^>]+>", "", html_text)))
        r = self.eval(js)
        if r != "ok":
            raise Missing("붙여넣기 실패: %s" % r)
        time.sleep(STEP_PAUSE * 2)

    def upload(self, css, files):
        ok = self.eval("(()=>{const e=document.querySelector(%s); if(!e) return false; e.style.display='block'; e.style.opacity=1; return true;})()" % json.dumps(css))
        if not ok:
            raise Missing("파일 입력 없음: %s" % css)
        snap = json.dumps(self.run("snapshot"), ensure_ascii=False)
        m = re.search(r"(@e\d+)[^\n]{0,80}(file|파일)", snap, re.I)
        if not m:
            raise Missing("snapshot 에서 파일 입력 ref 를 못 찾음")
        d = self.run("upload", "--element", m.group(1), "--files", ",".join(files), timeout=180)
        if not d.get("ok"):
            raise Missing("upload 실패: %s" % str(d)[:200])
        time.sleep(STEP_PAUSE * 3)

    def screenshot(self, path):
        d = self.run("screenshot")
        try:
            b64 = d["result"].get("data") or d["result"].get("base64")
            if b64:
                import base64
                io.open(path, "wb").write(base64.b64decode(b64)); return path
        except Exception:
            pass
        return None

    def url(self):
        return self.eval("location.href")


def find_page(blog):
    r = subprocess.run(["orca", "tab", "list", "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    m = re.search(r"\{.*\}", r.stdout, re.S)
    for t in (json.loads(m.group(0))["result"]["tabs"] if m else []):
        if "naver.com" in t.get("url", ""):
            return t["browserPageId"]
    r = subprocess.run(["orca", "tab", "create", "--url", WRITE_URL.format(blog=blog), "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    d = json.loads(re.search(r"\{.*\}", r.stdout, re.S).group(0))["result"]
    return d.get("browserPageId") or d.get("tab", {}).get("browserPageId")


# ---------------------------------------------------------------- 실행
def run(stem, blog, log):
    p, meta, body = read_post(stem)
    if meta.get("status") != "ready":
        log("STATUS: FAIL not-ready (status=%s — 한마디를 채우고 status: ready 로)" % meta.get("status")); return 1
    g = subprocess.run([sys.executable, os.path.join(HQ, "scripts", "blogcheck.py"), p, "--publish"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if "STATUS: OK" not in (g.stdout or ""):
        log((g.stdout or "")[-600:]); log("STATUS: FAIL blogcheck"); return 1
    title, body_html, tags, images = parse_blocks(body)
    files = [resolve_image(i["path"]) for i in images]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        log("STATUS: FAIL image-missing %s" % missing[0]); return 1
    os.makedirs(SHOT_DIR, exist_ok=True)
    try:
        o = Orca(find_page(blog))
        o.run("goto", "--url", WRITE_URL.format(blog=blog)); time.sleep(6)
        if o.exists(SEL["login_hint"]) or "nid.naver.com" in (o.url() or ""):
            log("STATUS: FAIL login-required (Orca 탭에서 네이버에 로그인한 뒤 다시)"); return 1
        o.run("wait", "--selector", SEL["editor_ready"], timeout=60)
        o.focus_css(SEL["title"]); o.type(title)
        o.focus_css(SEL["body"]); o.paste_html(SEL["body"], body_html)
        if files:
            o.upload(SEL["file_input"], files)
        shot = o.screenshot(os.path.join(SHOT_DIR, "%s_filled.png" % stem))
        log("filled: title=%r html=%d자 images=%d shot=%s" % (title, len(body_html), len(files), shot))
        o.click_css(SEL["save_btn"])
        log("임시저장 클릭. 태그는 발행 창에서 JJ 가 붙인다: %s" % " ".join("#" + t for t in tags))
        log("STATUS: OK (임시저장 — 발행은 JJ)"); return 0
    except Missing as e:
        log("요소 못 찾음 — 아무것도 누르지 않고 멈춘다: %s" % e)
        log("STATUS: FAIL selector — `--probe` 로 화면을 덤프해 SEL 을 맞춘다"); return 1


def probe(blog, log):
    o = Orca(find_page(blog))
    o.run("goto", "--url", WRITE_URL.format(blog=blog)); time.sleep(6)
    log("url: %s" % o.url())
    for k, css in SEL.items():
        log("%-13s %-75s %s" % (k, css, "있음" if o.exists(css) else "없음"))
    os.makedirs(SHOT_DIR, exist_ok=True)
    out = os.path.join(SHOT_DIR, "probe_snapshot.json")
    io.open(out, "w", encoding="utf-8").write(json.dumps(o.run("snapshot"), ensure_ascii=False, indent=1))
    log("snapshot -> %s" % out)
    log("screenshot -> %s" % o.screenshot(os.path.join(SHOT_DIR, "probe.png")))
    return 0


# ---------------------------------------------------------------- self-test
def self_test():
    global BLOG_DIR
    import tempfile
    root = tempfile.mkdtemp(prefix="naverdraft_")
    BLOG_DIR = os.path.join(root, "blog"); os.makedirs(BLOG_DIR)
    md = ("---\nkind: daily\nstatus: ready\n---\n\n# 제목 하나 (2026년 9월 8일)\n\n## 요약\n\n한 문장이에요.\n\n## 본문\n\n"
          "### Q. 왜?\n\n**굵은 첫 문장이에요.** 둘째 <문장>. (출처: a.com · 2026-09-08)\n\n| 소식 | 날짜 |\n|---|---|\n| 하나 | 9/8 |\n\n"
          "## FAQ\n\n**Q. 하나?**\n답.\n\n## 토망치랩 한마디\n\n판단이에요.\n\n## 관련글\n\n☞ 카드 — x\n\n## 이미지\n\n"
          "1. `workshop\\a.png` — 표지 (출처: 토망치랩)\n\n## 태그\n\n#AI뉴스 #토망치랩\n")
    io.open(os.path.join(BLOG_DIR, "t.md"), "w", encoding="utf-8").write(md)
    p, meta, body = read_post("t")
    title, h, tags, images = parse_blocks(body)
    cases = [
        ("제목", title == "제목 하나 (2026년 9월 8일)"),
        ("소제목 h3 · 굵게 strong · 표 table · 절 제목 h2", "<h3>Q. 왜?</h3>" in h and "<strong>굵은 첫 문장이에요.</strong>" in h and "<table><tr><th>소식</th>" in h and "<h2>토망치랩 한마디</h2>" in h),
        ("HTML 이스케이프", "&lt;문장&gt;" in h and "<문장>" not in h),
        ("태그·이미지는 따로", tags == ["AI뉴스", "토망치랩"] and images[0]["path"] == "workshop\\a.png" and resolve_image(images[0]["path"]).startswith(WORKSHOP_ROOT)),
        ("이미지·태그 절은 본문 HTML 에 안 들어간다", "a.png" not in h and "#AI뉴스" not in h),
        # 클릭은 SEL 을 거쳐서만 일어난다 — 발행·확인·태그 선택자가 없으면 누를 길이 없다
        ("발행 동작이 코드에 없다 (발행·확인·태그 선택자 0건)", not any(k in SEL for k in ("publish_open", "publish_confirm", "tag_input"))
         and set(SEL) == {"editor_ready", "title", "body", "file_input", "save_btn", "login_hint"}),
    ]
    for n, v in cases:
        print(("PASS " if v else "FAIL ") + n)
    ok = all(v for _, v in cases)
    print("STATUS: " + ("OK" if ok else "FAIL selftest"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--post")
    ap.add_argument("--blog", default=os.environ.get("NAVER_BLOG_ID", ""))
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    if not a.blog:
        raise SystemExit("--blog 또는 NAVER_BLOG_ID 가 필요하다")
    if a.probe:
        raise SystemExit(probe(a.blog, print))
    if not a.post:
        raise SystemExit("--post 가 필요하다")
    raise SystemExit(run(a.post, a.blog, print))
