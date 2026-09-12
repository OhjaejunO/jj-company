# -*- coding: utf-8 -*-
r"""네이버 블로그 초안 넣기 (1단계) — 승인된 초안 md 를 Orca 내장 브라우저로 스마트에디터에 채우고 «저장(임시저장)»한다.

    py scripts\naver_draft.py --post 2026-09-07_주간1호 --blog ai-tomangchi-lab   ← 제목·본문·사진 채우고 저장, 화면 캡처
    py scripts\naver_draft.py --probe --blog ai-tomangchi-lab                     ← 에디터 화면 상태 덤프
    py scripts\naver_draft.py --self-test

## 이 스크립트는 발행하지 않는다 (JJ 판정 2026-09-05 «1단계만 먼저»)
«발행» 버튼·공개 설정·태그 입력은 **코드에 없다.** 제목 넣기, 본문 붙여넣기, 사진 올리기까지 하고 «저장»(임시글)을
누른다. 발행은 JJ 가 에디터에서 태그를 달고 «발행»을 누른다. 정관 §0 C등급(발행)은 그대로다.

## 실측으로 정한 경로 (2026-09-05 · ai-tomangchi-lab 실계정)
- 에디터는 `#mainFrame` iframe 안(같은 출처)이다. 모든 DOM 작업은 그 frame 의 document 로 한다.
- 🔴 **`orca type`·`keypress` 는 쓰지 않는다.** 브라우저 탭이 아니라 **활성 창**에 키를 보낸다 — 실측에서 JJ 채팅창에
  «테스트 제목» 이 찍혔다. 여기 남은 입력 경로는 전부 페이지 안 JS 이벤트다.
- 제목: 제목 span 에 합성 마우스 이벤트(mousedown·mouseup·click)로 에디터 내부 커서를 옮긴 뒤 text/plain 붙여넣기.
  (선택 영역만 바꾸면 에디터는 무시하고 본문 커서 자리에 넣는다 — 실측.)
- 본문: contenteditable 루트에 `ClipboardEvent('paste')` + text/html → 소제목·굵게·표(`se-table`)·문단이 그대로 컴포넌트가 된다.
- 사진: 파일 바이트를 base64 청크로 `window.__jj` 에 넣고 `File` 을 만들어 같은 붙여넣기 경로로 준다 → 에디터가
  `blogfiles.pstatic.net` 에 직접 올린다(`se-image`). CLI 인자 상한 때문에 24,000자 청크다. JPEG 88 로 줄여 보낸다.
- 새 글 화면을 열면 «작성 중이던 글 불러오기» 팝업이 뜰 수 있다 → «취소» 를 누른다(복구하지 않는다).
- 저장: 스냅샷에서 이름이 «저장» 인 버튼 ref 를 찾아 `orca click --element` (페이지 안 클릭).

## 🔴 이 스크립트가 증명하지 못하는 것 (§0 4층 ④)
- 붙여넣은 표·소제목이 발행본에서 어떻게 보이는지는 캡처·육안. 네이버의 «자동화 계정» 판정 기준은 비공개.
"""
import argparse
import base64
import hashlib
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
WRITE_URL = "https://blog.naver.com/{blog}?Redirect=Write&"
STEP_PAUSE = 1.5
CHUNK = 24000
IMG_MAX_W = 1080
JPEG_Q = 88

#: 붙여넣은 **그 장**이 실제 주소를 얻었는가. 에디터는 우리가 준 파일 이름을 `alt` 에 넣는다(실측).
#:
#: 🔴 **종전에는 «pstatic 인 img 개수가 늘었는가» 를 봤고 그것이 틀린 자다 (2026-09-12 실측).**
#:    그 개수는 **줄어들 수 있는 값**이다 — 세 회차 전부에서 **네 번째 자리**의 img 가
#:    자리표(`data:image/svg+xml`)로 되돌아갔고(파일은 매번 달랐다: fig4·fig4·fig3 — 파일 탓이 아니다),
#:    그러면 새로 올라온 장이 그 자리를 메워 **셈이 안 는다.** 그래서 이미 올라가 있는 장을 두고
#:    90초(대기를 270초로 늘려도 마찬가지)를 기다리다 **엉뚱한 파일 이름으로** 실패를 적었다.
#:    실측: `alt` 로 보니 «실패했다»던 `fig7_bench.jpg` 는 `blogfiles.pstatic.net` 주소를 갖고 있었다.
#:    정관 §0 «장치가 재는 대상이 틀렸다».
#: 같은 이름을 두 번 붙이는 편이 있을 수 있어 **마지막 것**을 본다.
UPLOADED_JS = ("const m=[...d.querySelectorAll('.se-component.se-image img')]"
               ".filter(i=>i.getAttribute('alt')===%s); if(!m.length) return 'none';"
               "return /pstatic|blogfiles/.test(m[m.length-1].src) ? 'ok' : 'placeholder';")

#: 본문 차례 검증이 찾는 표시.
#:
#: 🔴 **«토망치랩 한마디» 를 뺐다 (2026-09-12).** 그 절은 `docs\blog-format.md` 5번이
#:    **2026-09-10 에 폐기**했는데 이 검사만 계속 요구하고 있었다 — 폐기 뒤에 쓴 초안 셋
#:    (`클로드비용절감`·`코덱스이사`·`메타뮤즈`)은 **어느 것도 통과할 수 없었다.**
#:    정관 §0 «검사가 틀린 것을 요구하고 있으면 산출물보다 검사부터 고친다»(ep28 선례).
#:    한마디가 남아 있는 옛 초안은 그대로 통과한다 — 있는지 없는지를 안 보기 때문이다.
BODY_MARKS = ["FAQ", "관련글"]
MIN_SOURCE_LINES = 3

#: 역검증용 기준 본문 — 한마디 절이 **없는** 새 규격 글이다.
_ORDER_OK = "요약\n(출처: a)\n(출처: b)\n(출처: c)\n## FAQ\n답이에요.\n## 관련글\n☞ 카드"

F = "const d=document.querySelector('#mainFrame').contentDocument; const root=d.querySelector('[contenteditable]');"


# ---------------------------------------------------------------- 원고 → 블록
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
    """초안 md → (title, chunks, tags, images).
    chunks = 붙여넣기 단위 HTML 목록. 이미지는 «요약 뒤 표지, 그 다음은 Q. 절마다 하나» 순으로 끼운다.
    """
    title = re.search(r"^# (.+)$", body, re.M).group(1).strip()
    # 조각 = 붙여넣기 단위. 본문 안의 `[[이미지 N]]` 줄이 있으면 그 자리에 N번 그림을 끼운다 — 2026-09-05 JJ 지적
    # (Astra 도표가 엉뚱한 절 뒤에 붙었다). 조각 목록의 원소는 HTML 문자열이거나 ("img", N) 이다.
    chunks = [md_to_html(_section(body, "요약"))]
    main = _section(body, "본문")
    qs = re.split(r"(?m)^(?=### )", main)
    for q in qs:
        if not q.strip():
            continue
        buf = []
        for ln in q.splitlines():
            m = re.match(r"^\[\[(이미지|영상) (\d+)\]\]\s*$", ln.strip())
            if m:
                if "\n".join(buf).strip():
                    chunks.append(md_to_html("\n".join(buf)))
                buf = []
                chunks.append(("img" if m.group(1) == "이미지" else "vid", int(m.group(2))))
            else:
                buf.append(ln)
        if "\n".join(buf).strip():
            chunks.append(md_to_html("\n".join(buf)))
    for name in ("FAQ", "토망치랩 한마디", "관련글"):
        sec = _section(body, name)
        if sec:
            chunks.append("<h2>%s</h2>\n%s" % (html.escape(name), md_to_html(sec)))
    tags = re.findall(r"#(\S+)", _section(body, "태그"))
    images = []
    for ln in _section(body, "이미지").splitlines():
        m = re.match(r"^\d+\.\s+`([^`]+)`\s+—\s+(.*)$", ln.strip())
        if m:
            images.append({"path": m.group(1), "caption": m.group(2)})
    return title, chunks, tags, images


#: `## 영상` 절 한 줄. 경로만 있으면 통째로, `· 12~20` 이면 그 구간, `· <주소>` 면 원본 링크 카드도 붙인다.
VIDEO_LINE = re.compile(r"^\d+\.\s+`([^`]+)`\s*"
                        r"(?:·\s*([\d.]+)~([\d.]+)\s*)?"
                        r"(?:·\s*(https?://\S+)\s*)?"
                        r"—\s+(.*)$")


def parse_videos(body):
    """`## 영상` 절 → `[{path, start, end, url, caption}, …]`. 절이 없으면 빈 목록.

    🔴 **왜 영상 자리가 필요한가 (2026-09-12 JJ 지적).** 블로그 규격에는 영상 축이
       **0건**이었다 — 조문·게이트·채우기 셋 다. 그래서 `2026-09-11_챗지피티이미지2_5`
       글이 「소개 필름 한 편에 … **한 영상에서 차례로 볼 수 있어요**」라고 적어 놓고
       **정지 캡처 한 장**만 실었다. 독자에게는 없는 것을 가리키는 문장이다.
       인스타·릴스·Threads 에는 «영상 소스는 영상으로»(SKILL v3.24·v3.83)가 서 있는데
       블로그만 비어 있었다.
    """
    out = []
    for ln in _section(body, "영상").splitlines():
        m = VIDEO_LINE.match(ln.strip())
        if m:
            out.append({"path": m.group(1),
                        "start": float(m.group(2)) if m.group(2) else None,
                        "end": float(m.group(3)) if m.group(3) else None,
                        "url": m.group(4), "caption": m.group(5)})
    return out


def resolve_image(path):
    r"""상대 경로는 «있는 쪽»으로 푼다 — `workshop\…` 은 워크숍 루트, `reports\…` 는 운영 서버(HQ).
    2026-09-06 실측: 영상 프레임을 `reports\blog\img\` 에 뽑아 두고 워크숍 루트로만 풀어 image-missing 이 났다."""
    if os.path.isabs(path):
        return path
    for root in (WORKSHOP_ROOT, HQ):
        p = os.path.join(root, path)
        if os.path.exists(p):
            return p
    return os.path.join(WORKSHOP_ROOT, path)      # 없으면 종전 경로 그대로 돌려줘 image-missing 메시지가 그 경로를 가리킨다


def jpeg_b64(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if im.width > IMG_MAX_W:
        im = im.resize((IMG_MAX_W, round(im.height * IMG_MAX_W / im.width)))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=JPEG_Q)
    return base64.b64encode(buf.getvalue()).decode()


#: GIF 규격 — 붙여넣기로 올릴 수 있는 크기 안에서 «움직임이 보이는» 최소값 (2026-09-12 실측).
GIF_W, GIF_FPS, GIF_MAX_S, GIF_MAX_BYTES = 560, 8, 12.0, 8 * 1024 * 1024
GIF_DIR = os.path.join(HQ, "logs", "naver-draft", "gif")


def gif_for(v):
    r"""영상 한 줄 → 구워 둔 GIF 경로.

    🔴 **왜 GIF 인가 (2026-09-12 실측).** 네이버 스마트에디터는
       ⓐ **영상 File 붙여넣기를 받지 않는다** — `paste` 는 삼켜지는데(`defaultPrevented`)
         컴포넌트가 **0건** 생긴다(4.9MB mp4 로 실측, 40초까지 기다려도 그대로).
       ⓑ **동영상 단추는 OS 파일 대화상자**를 여는데, 이 워커에는 키 입력 경로가 **없고**
         자체 검사가 그것을 못 만들게 막고 있다(«OS 키 입력 경로 없음»).
       ⓒ **GIF 붙여넣기는 된다** — `blogfiles.pstatic.net` 주소를 받는다(실측).
       그래서 **이미 도는 이미지 경로를 그대로 쓴다.** 움직임이 보이는 것이 요점이고,
       원본 전체는 같은 줄의 주소가 **링크 카드**로 받는다(그쪽도 실측 — `se-oglink` 1건).

    🔴 **구간을 안 적으면 앞에서부터 %.0f초**다 — 통째로 굽지 않는다. GIF 는 코덱이 없어
       길이가 곧 크기이고, 붙여넣기로 보낼 수 있는 한도를 넘으면 아무것도 못 싣는다.
    """ % GIF_MAX_S
    src = resolve_image(v["path"])
    if not os.path.exists(src):
        raise Missing("영상 파일이 없다: %s" % src)
    start = v["start"] or 0.0
    end = v["end"] if v["end"] is not None else start + GIF_MAX_S
    dur = min(end - start, GIF_MAX_S)
    if dur <= 0:
        raise Missing("영상 구간이 비었다: %s~%s" % (v["start"], v["end"]))
    key = hashlib.sha1(("%s|%.2f|%.2f|%d|%d" % (src, start, dur, GIF_W, GIF_FPS)).encode("utf-8")).hexdigest()[:16]
    out = os.path.join(GIF_DIR, key + ".gif")
    if not os.path.exists(out):
        os.makedirs(GIF_DIR, exist_ok=True)
        vf = ("fps=%d,scale=%d:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];"
              "[b][p]paletteuse=dither=bayer" % (GIF_FPS, GIF_W))
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % start, "-t", "%.2f" % dur,
                            "-i", src, "-vf", vf, "-loop", "0", out],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or not os.path.exists(out):
            raise Missing("GIF 굽기 실패: %s" % (r.stderr or "")[-200:])
    n = os.path.getsize(out)
    if n > GIF_MAX_BYTES:
        raise Missing("GIF 가 너무 크다 (%.1fMB > %.0fMB) — 구간을 줄여라: %s"
                      % (n / 1048576.0, GIF_MAX_BYTES / 1048576.0, os.path.basename(src)))
    return out


# ---------------------------------------------------------------- 브라우저 (Orca CLI · 페이지 안 JS 만)
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
        # `orca eval` = Orca 내장 브라우저 탭 안에서 JS 를 돌리는 CLI 다(파이썬 eval 아님). 넘기는 JS 는 이 파일의
        # 고정 문자열이고 원고·이미지는 json.dumps 로 감싸 데이터로만 들어간다.
        d = self.run("eval", "--expression", js)
        res = d.get("result", {}).get("result") if d.get("ok") else None
        if isinstance(res, str):
            res = res.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
            try:
                return json.loads(res)   # 'false'/'true'/JSON 문자열 — 'false' 는 참이 아니다
            except ValueError:
                return res
        return res

    def url(self):
        return self.eval("location.href")

    def in_frame(self, body_js):
        return self.eval("(()=>{%s %s})()" % (F, body_js))

    def editor_ready(self):
        return bool(self.in_frame("return !!d.querySelector('.se-title-text') && !!root;"))

    def dismiss_restore(self):
        """«작성 중이던 글 불러오기» 류 팝업 → 취소. 복구하지 않는다."""
        r = self.in_frame("const b=[...d.querySelectorAll('button')].find(x=>(x.innerText||'').trim()==='취소'); if(!b) return 'none'; b.click(); return 'cancelled';")
        time.sleep(STEP_PAUSE)
        return r

    def set_title(self, text):
        js = ("const t=d.querySelector('.se-title-text p span')||d.querySelector('.se-title-text p'); if(!t) return 'no-title';"
              "const r=t.getBoundingClientRect(); const x=r.left+10,y=r.top+r.height/2;"
              "for(const ty of ['mousedown','mouseup','click']) t.dispatchEvent(new MouseEvent(ty,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0}));"
              "const s=d.getSelection(); const rg=d.createRange(); rg.selectNodeContents(t); rg.collapse(false); s.removeAllRanges(); s.addRange(rg);"
              "const dt=new DataTransfer(); dt.setData('text/plain', %s); const ev=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}); root.dispatchEvent(ev);"
              "return ev.defaultPrevented ? 'ok' : 'not-handled';") % json.dumps(text)
        r = self.in_frame(js); time.sleep(STEP_PAUSE)
        if r != "ok":
            raise Missing("제목 붙여넣기 실패: %s" % r)
        got = (self.in_frame("return d.querySelector('.se-title-text').innerText;") or "").replace("\xa0", " ")   # 에디터가 공백을 nbsp 로 바꾼다
        if text[:10] not in got:
            raise Missing("제목이 안 들어감: %r" % got)

    _body_clicked = False

    def _cursor_to_end(self):
        """본문 첫 문단으로 내부 커서를 **한 번만** 옮긴다. 그 뒤 붙여넣기는 에디터 커서(직전 붙여넣기 끝)에 이어진다.
        매번 «마지막 문단»을 다시 누르면 커서가 그 문단 **앞**에 앉아 조각이 뒤섞였다(2026-09-05 실측 — 마지막 문단에
        요약·한마디·관련글 꼬리가 한 줄로 엉켰다)."""
        if self._body_clicked:
            return ""
        self._body_clicked = True
        return ("const ps=[...d.querySelectorAll('.se-component.se-text .se-text-paragraph')]; const p=ps[ps.length-1]; if(!p) return 'no-body';"
                "const r=p.getBoundingClientRect(); for(const ty of ['mousedown','mouseup','click']) p.dispatchEvent(new MouseEvent(ty,{bubbles:true,cancelable:true,clientX:r.left+5,clientY:r.top+r.height/2,button:0}));"
                "const s=d.getSelection(); const rg=d.createRange(); rg.selectNodeContents(p); rg.collapse(false); s.removeAllRanges(); s.addRange(rg);")

    def bold_off(self):
        """에디터의 «굵게» 상태가 켜져 있으면 끈다. 붙여넣은 <strong>·<h2> 뒤로 굵게 상태가 남아 **다음 붙여넣기 전체가
        굵게** 됐다(2026-09-05 실측 — FAQ·한마디까지 전부 굵게, 툴바 B 가 켜진 채). 버튼은 `.se-bold-toolbar-button.se-is-selected`."""
        return self.in_frame("const b=d.querySelector('.se-bold-toolbar-button.se-is-selected'); if(!b) return 'off'; b.click(); return 'turned-off';")

    def paste_html(self, html_text):
        # 조각 끝에 빈 문단 — 다음 조각의 첫 블록이 앞 문단에 합쳐지지 않게(«토망치랩 한마디» 가 «랩 한마디» 로 잘린 실측).
        # 빈 문단은 조각 **끝**에 있어야 한다 — 따로 붙이면 에디터가 버린다.
        if not html_text.rstrip().endswith("<p><br></p>"):
            html_text = html_text + "<p><br></p>"
        self.bold_off()
        js = (self._cursor_to_end() +
              "const dt=new DataTransfer(); dt.setData('text/html', %s); dt.setData('text/plain', %s);"
              "const ev=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}); root.dispatchEvent(ev); return ev.defaultPrevented?'ok':'not-handled';"
              ) % (json.dumps(html_text), json.dumps(re.sub(r"<[^>]+>", " ", html_text)))
        r = self.in_frame(js); time.sleep(STEP_PAUSE * 2)
        if r != "ok":
            raise Missing("본문 붙여넣기 실패: %s" % r)
        self.bold_off()

    def paste_image(self, path):
        b = jpeg_b64(path)
        self.eval("window.__jj=''")
        for i in range(0, len(b), CHUNK):
            self.eval("(()=>{window.__jj+=%s; return 1;})()" % json.dumps(b[i:i + CHUNK]))
        got = self.eval("window.__jj.length")
        if got != len(b):
            raise Missing("이미지 전송 길이 불일치 %s≠%d" % (got, len(b)))
        want = json.dumps(os.path.basename(path).rsplit(".", 1)[0] + ".jpg")   # 에디터가 alt 로 쓸 이름
        js = (self._cursor_to_end() +
              "const bin=atob(window.__jj); const arr=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);"
              "const file=new File([arr], %s, {type:'image/jpeg'}); const dt=new DataTransfer(); dt.items.add(file);"
              "const ev=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}); root.dispatchEvent(ev); window.__jj=''; return ev.defaultPrevented?'ok':'not-handled';"
              ) % want
        r = self.in_frame(js)
        if r != "ok":
            raise Missing("이미지 붙여넣기 실패: %s" % r)
        self.bold_off()
        last = "none"
        for _ in range(60):   # 업로드 완료 대기 (최대 90초 — 표지 PNG 는 30초를 넘겼다, 실측)
            time.sleep(1.5)
            last = self.in_frame(UPLOADED_JS % want) or "none"
            if last == "ok":
                return
        raise Missing("이미지 업로드가 90초 안에 안 끝남: %s (에디터 상태 %s)"
                      % (os.path.basename(path), last))

    def _send_bytes(self, blob):
        """바이트를 페이지 안 `window.__jj` 로 옮긴다. 길이가 다르면 붙여넣지 않는다."""
        b = base64.b64encode(blob).decode()
        self.eval("window.__jj=''")
        for i in range(0, len(b), CHUNK):
            self.eval("(()=>{window.__jj+=%s; return 1;})()" % json.dumps(b[i:i + CHUNK]))
        got = self.eval("window.__jj.length")
        if got != len(b):
            raise Missing("전송 길이 불일치 %s≠%d" % (got, len(b)))

    def paste_gif(self, path):
        """GIF 를 **다시 굽지 않고** 그대로 붙인다 — 다시 구우면 움직임이 사라진다.

        판정은 이미지와 같은 자(`UPLOADED_JS` · `alt` 로 그 장을 본다).
        """
        name = os.path.basename(path)
        self._send_bytes(open(path, "rb").read())
        js = (self._cursor_to_end() +
              "const bin=atob(window.__jj); const arr=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);"
              "const file=new File([arr], %s, {type:'image/gif'}); const dt=new DataTransfer(); dt.items.add(file);"
              "const ev=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}); root.dispatchEvent(ev); window.__jj=''; return ev.defaultPrevented?'ok':'not-handled';"
              ) % json.dumps(name)
        r = self.in_frame(js)
        if r != "ok":
            raise Missing("GIF 붙여넣기 실패: %s" % r)
        self.bold_off()
        last = "none"
        for _ in range(60):
            time.sleep(1.5)
            last = self.in_frame(UPLOADED_JS % json.dumps(name)) or "none"
            if last == "ok":
                return
        raise Missing("GIF 업로드가 90초 안에 안 끝남: %s (에디터 상태 %s)" % (name, last))

    def paste_link(self, url):
        """주소를 붙여 **링크 카드**(`se-oglink`)를 만든다. 안 생기면 글자 링크로 남는다 — 그건 실패가 아니다."""
        before = self.in_frame("return d.querySelectorAll('.se-oglink').length;") or 0
        js = (self._cursor_to_end() +
              "const dt=new DataTransfer(); dt.setData('text/plain', %s);"
              "const ev=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true});"
              "root.dispatchEvent(ev); return ev.defaultPrevented?'ok':'not-handled';" % json.dumps(url))
        if self.in_frame(js) != "ok":
            raise Missing("주소 붙여넣기 실패: %s" % url)
        for _ in range(10):
            time.sleep(1.5)
            if (self.in_frame("return d.querySelectorAll('.se-oglink').length;") or 0) > before:
                return "카드"
        return "글자"

    def clear_body(self):
        """본문을 통째로 지운다 (발행글 수정 화면 전용).

        🔴 **지워졌는지 재고, 안 지워졌으면 선다.** 안 서면 채우기가 **옛 글 위에 얹혀**
           같은 글이 두 번 실린다 — 그 상태로 «발행» 을 누르면 되돌릴 것이 실물 글이다.
        🔴 실물 글은 «발행» 을 누르기 전까지 한 글자도 안 바뀐다 — 여기서 지우는 것은
           **에디터 안의 사본**이다.
        """
        js = ("const ps=[...d.querySelectorAll('.se-component.se-text .se-text-paragraph')];"
              "const p=ps[ps.length-1]; if(p){const r=p.getBoundingClientRect();"
              "for(const ty of ['mousedown','mouseup','click']) p.dispatchEvent(new MouseEvent(ty,"
              "{bubbles:true,cancelable:true,clientX:r.left+5,clientY:r.top+r.height/2,button:0}));}"
              "d.defaultView.focus(); root.focus();"
              "const a=d.execCommand('selectAll'); const b=d.execCommand('delete');"
              "return JSON.stringify([a,b]);")
        r = self.in_frame(js)
        time.sleep(STEP_PAUSE * 2)
        st = self.state()
        st = json.loads(st) if isinstance(st, str) else (st or {})
        if len(st.get("comps", [])) > 2 or (st.get("chars") or 0) > 50:
            raise Missing("본문이 안 비워졌다 (comps=%d chars=%s · execCommand %s) — 옛 글 위에 얹지 않는다"
                          % (len(st.get("comps", [])), st.get("chars"), r))
        self._body_clicked = False
        return r

    def click_named_button(self, name):
        snap = self.run("snapshot")
        refs = (snap.get("result") or {}).get("refs") or {}
        ref = next((k for k, v in refs.items() if v.get("role") == "button" and (v.get("name") or "").strip() == name), None)
        if ref:
            d = self.run("click", "--element", "@" + ref)
            if d.get("ok"):
                time.sleep(STEP_PAUSE * 2); return
        # 스냅샷이 큰 문서에서 비어 오는 때가 있다(2026-09-05 실측 — 내용을 다 채운 뒤 «저장» ref 를 못 찾았다).
        # 프레임 안 버튼을 글자로 찾아 페이지 안에서 누른다. «발행» 은 이 경로로도 부르지 않는다(self-test).
        cls = {"저장": "save_btn__"}.get(name)   # 글자 대조가 빗나갈 때(innerText 에 숨은 글자) 클래스로 — «발행» 은 여기 없다
        js = ("const b=[...d.querySelectorAll('button')].find(x=>(x.innerText||'').trim()===%s || (%s && new RegExp(%s).test(x.className))); if(!b) return 'none'; b.click(); return 'clicked';"
              % (json.dumps(name), json.dumps(bool(cls)), json.dumps(cls or "^$")))
        last = None
        for _ in range(3):        # 큰 문서 직후 한 번 헛도는 때가 있다(2026-09-05 실측) — 3번까지
            last = self.in_frame(js)
            if last == "clicked":
                time.sleep(STEP_PAUSE * 2); return
            time.sleep(2)
        raise Missing("«%s» 버튼 없음 (스냅샷·프레임 3회, 마지막 응답 %r)" % (name, last))

    def screenshot(self, path):
        d = self.run("screenshot")
        try:
            b64 = d["result"].get("data")
            if b64:
                io.open(path, "wb").write(base64.b64decode(b64)); return path
        except Exception:
            pass
        return None

    def state(self):
        return self.in_frame("return JSON.stringify({title:(d.querySelector('.se-title-text')||{}).innerText||'', comps:[...d.querySelectorAll('.se-component')].map(e=>e.className.toString().replace('se-component ','').split(' ')[0]), chars:(d.querySelector('.se-components-wrap')||{}).innerText?d.querySelector('.se-components-wrap').innerText.length:0});")


def _tabs():
    r = subprocess.run(["orca", "tab", "list", "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    m = re.search(r"\{.*\}", r.stdout, re.S)
    return json.loads(m.group(0))["result"]["tabs"] if m else []


def find_page(blog, fresh=False):
    """편집 탭. fresh=True 면 옛 네이버 탭을 닫고 새 탭으로 연다 — 열려 있던 편집 화면은 goto 로도 홈 경유로도
    새로고침이 안 됐다(2026-09-05 실측 세 번: 옛 내용 위에 제목이 겹쳤다). 로그인은 프로필 쿠키라 새 탭에도 살아 있다."""
    if fresh:
        for t in sorted([t for t in _tabs() if "naver.com" in t.get("url", "")], key=lambda t: -t["index"]):
            subprocess.run(["orca", "tab", "close", "--index", str(t["index"]), "--json"], capture_output=True, text=True, timeout=60)
    else:
        for t in _tabs():
            if "naver.com" in t.get("url", ""):
                return t["browserPageId"]
    r = subprocess.run(["orca", "tab", "create", "--url", WRITE_URL.format(blog=blog), "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    d = json.loads(re.search(r"\{.*\}", r.stdout, re.S).group(0))["result"]
    return d.get("browserPageId") or d.get("tab", {}).get("browserPageId")


#: 발행글 수정 화면. 🔴 **껍데기 주소라야 `#mainFrame` 이 생긴다** — `PostUpdateForm.naver`·
#  `/postwrite?logNo=` 도 에디터를 열긴 하지만 프레임이 없어 이 파일의 JS 가 하나도 안 닿는다(2026-09-12 실측).
UPDATE_URL = "https://blog.naver.com/{blog}?Redirect=Update&logNo={logno}"


def find_update_page(blog, logno):
    """발행글 수정 탭을 새로 연다 (옛 네이버 탭은 닫는다 — `find_page(fresh=True)` 와 같은 이유)."""
    for t in sorted([t for t in _tabs() if "naver.com" in t.get("url", "")], key=lambda t: -t["index"]):
        subprocess.run(["orca", "tab", "close", "--index", str(t["index"]), "--json"],
                       capture_output=True, text=True, timeout=60)
    r = subprocess.run(["orca", "tab", "create", "--url", UPDATE_URL.format(blog=blog, logno=logno), "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    d = json.loads(re.search(r"\{.*\}", r.stdout, re.S).group(0))["result"]
    return d.get("browserPageId") or d.get("tab", {}).get("browserPageId")


def open_update(o, title, log):
    """발행글 수정 화면을 열고 본문을 비운다. 제목이 다르면 **아무것도 안 지우고 선다.**

    🔴 **엉뚱한 글을 고치지 않는다** — 이 화면의 제목과 원고 제목이 글자 그대로 같아야
       열린다. 글 번호를 손으로 넘기는 자리라 오타 하나가 남의 글을 지우는 자리다.
    """
    time.sleep(10)
    if "nid.naver.com" in (o.url() or ""):
        log("STATUS: FAIL login-required (Orca 탭에서 네이버에 로그인한 뒤 다시)"); return False
    if not o.editor_ready():
        log("STATUS: FAIL editor-not-ready (%s)" % o.url()); return False
    log("restore popup: %s" % o.dismiss_restore())
    st = o.state()
    st = json.loads(st) if isinstance(st, str) else (st or {})
    got = (st.get("title") or "").replace("\xa0", " ").strip()
    if got != title.strip():
        log("STATUS: FAIL wrong-post (화면 제목 %r ≠ 원고 제목 %r) — 아무것도 지우지 않았다"
            % (got[:40], title[:40]))
        return False
    log("update target ok: %r (comps=%d chars=%s)" % (got[:40], len(st.get("comps", [])), st.get("chars")))
    log("cleared: %s" % o.clear_body())
    return True


def open_editor(o, blog, log):
    time.sleep(8)
    if "nid.naver.com" in (o.url() or ""):
        log("STATUS: FAIL login-required (Orca 탭에서 네이버에 로그인한 뒤 다시)"); return False
    if not o.editor_ready():
        log("STATUS: FAIL editor-not-ready (%s)" % o.url()); return False
    log("restore popup: %s" % o.dismiss_restore())
    st = o.state()
    st = json.loads(st) if isinstance(st, str) else (st or {})
    if len(st.get("comps", [])) > 2 or (st.get("title") or "").strip() not in ("", "제목"):
        log("STATUS: FAIL editor-not-empty (comps=%d title=%r) — 빈 새 글이 아니면 넣지 않는다" % (len(st.get("comps", [])), st.get("title")))
        return False
    return True


# ---------------------------------------------------------------- 실행
def body_order_problem(text):
    """본문 조각이 뒤섞였는가. 사유(문자열) 또는 None. 저장 전에 서는 자리라 **순수 함수**로 둔다.

    재는 것 셋 — ⓐ 표시가 다 있는가 ⓑ 차례대로인가 ⓒ 출처 줄이 충분한가(조각이 잘리면 준다).
    🔴 **없는 절을 요구하지 않는다** — `BODY_MARKS` 주석 참고.
    """
    pos = [text.find(m) for m in BODY_MARKS]
    missing = [m for m, p in zip(BODY_MARKS, pos) if p < 0]
    if missing:
        return "차례 표시를 못 찾았다: %s (위치 %s)" % ("·".join(missing), pos)
    if pos != sorted(pos):
        return "차례가 뒤섞였다: %s (위치 %s)" % ("→".join(BODY_MARKS), pos)
    n_src = text.count("(출처:")
    if n_src < MIN_SOURCE_LINES:
        return "출처 줄이 %d개뿐이다 (%d개 이상이어야 한다 — 조각이 잘렸다는 뜻)" % (n_src, MIN_SOURCE_LINES)
    return None


def prepare(stem, log):
    """원고 → 채울 재료. 게이트·그림 실재·GIF 굽기까지 **에디터를 열기 전에** 끝낸다.

    🔴 재료를 다 만든 뒤에 에디터를 연다 (정관 §0 «검사는 쓰기 전에») — 중간에 서면
       반쯤 채운 글이 남고, 수정 회차에서는 그것이 **실물 글을 덮을 뻔한 상태**가 된다.
    돌려주는 값은 `dict` 이거나, 못 만들었으면 `None`(사유는 log 에 찍는다).
    """
    p_, meta, body = read_post(stem)
    if meta.get("status") != "ready":
        log("STATUS: FAIL not-ready (status=%s — status: ready 로)" % meta.get("status")); return None
    # 게이트는 **이 파일 옆의** blogcheck.py — 운영 서버 사본을 고정으로 부르면 worktree 에서 고친 규칙이 안 먹는다(2026-09-05 실측)
    g = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "blogcheck.py"), p_, "--publish"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if "STATUS: OK" not in (g.stdout or ""):
        log((g.stdout or "")[-600:]); log("STATUS: FAIL blogcheck"); return None
    title, chunks, tags, images = parse_blocks(body)
    files = [resolve_image(i["path"]) for i in images]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        log("STATUS: FAIL image-missing %s" % missing[0]); return None
    videos = parse_videos(body)
    try:
        gifs = [gif_for(v) for v in videos]
    except Missing as e:
        log("STATUS: FAIL video %s" % e); return None
    for v, gp in zip(videos, gifs):
        log("video: %s -> %s (%.1fMB)" % (os.path.basename(v["path"]), os.path.basename(gp),
                                          os.path.getsize(gp) / 1048576.0))
    return {"path": p_, "title": title, "chunks": chunks, "tags": tags,
            "files": files, "videos": videos, "gifs": gifs}


def fill(o, prep, log):
    """열려 있는 에디터에 제목·본문·그림·영상을 채운다. **저장도 발행도 하지 않는다.**

    마지막에 본문 차례를 재고 어긋나면 `Missing` 을 던진다 — 부르는 쪽이 저장 전에 선다.
    """
    title, chunks, files = prep["title"], prep["chunks"], prep["files"]
    videos, gifs = prep["videos"], prep["gifs"]
    o.set_title(title); log("title ok")
    o._body_clicked = False
    # 자리 지정은 **종류마다 따로** 본다 — 영상 자리만 적은 글에서 이미지 자동 배치가 꺼지면 안 된다.
    explicit = any(isinstance(c, tuple) and c[0] == "img" for c in chunks)
    vexplicit = any(isinstance(c, tuple) and c[0] == "vid" for c in chunks)
    placed, vplaced = set(), set()
    img_i = 0

    def put_video(n_, where):
        """영상 한 편 = GIF 한 장 + (주소가 있으면) 원본 링크 카드."""
        o.paste_gif(gifs[n_ - 1]); vplaced.add(n_)
        log("video %d/%d (%s): %s" % (n_, len(gifs), where, os.path.basename(gifs[n_ - 1])))
        u = videos[n_ - 1]["url"]
        if u:
            log("  원본 링크: %s (%s)" % (u, o.paste_link(u)))

    for k, ch in enumerate(chunks):
        if isinstance(ch, tuple):                      # [[이미지 N]] · [[영상 N]] 자리
            kind, n_ = ch
            if kind == "img":
                if 1 <= n_ <= len(files) and n_ not in placed:
                    o.paste_image(files[n_ - 1]); placed.add(n_); log("image %d/%d (자리 지정): %s" % (n_, len(files), os.path.basename(files[n_ - 1])))
            elif 1 <= n_ <= len(gifs) and n_ not in vplaced:
                put_video(n_, "자리 지정")
            continue
        o.paste_html(ch)
        if not explicit and (k == 0 or (0 < k < len(chunks) - 3)) and img_i < len(files):
            o.paste_image(files[img_i]); placed.add(img_i + 1); log("image %d/%d: %s" % (img_i + 1, len(files), os.path.basename(files[img_i]))); img_i += 1
        if k == 0 and not vexplicit:                   # 자리를 안 적은 영상은 요약 바로 뒤 — 그 편의 주인공이라 위에 둔다
            for n_ in range(1, len(gifs) + 1):
                put_video(n_, "요약 뒤")
        log("chunk %d/%d ok" % (k + 1, len(chunks)))
    for n_ in range(1, len(files) + 1):               # 자리 지정이 없는 나머지는 끝에
        if n_ not in placed:
            o.paste_image(files[n_ - 1]); log("image %d/%d (끝): %s" % (n_, len(files), os.path.basename(files[n_ - 1])))
    for n_ in range(1, len(gifs) + 1):                # 🔴 자리 번호가 어긋난 영상도 **버리지 않는다** (정관 §0 «조용히 실패하는 코드를 남기지 않는다»)
        if n_ not in vplaced:
            put_video(n_, "끝")
    log("state: %s" % o.state())
    # 순서 검증 — 조각이 뒤섞였으면 부르는 쪽이 저장하지 않는다
    text = (o.in_frame("return d.querySelector('.se-components-wrap').innerText;") or "").replace("\xa0", " ")
    why = body_order_problem(text)
    if why:
        raise Missing("본문 순서가 어긋남 — %s" % why)


def run(stem, blog, log):
    prep = prepare(stem, log)
    if prep is None:
        return 1
    os.makedirs(SHOT_DIR, exist_ok=True)
    o = Orca(find_page(blog, fresh=True))
    if not open_editor(o, blog, log):
        return 1
    try:
        fill(o, prep, log)
        o.click_named_button("저장")
        time.sleep(3)
        toast = o.in_frame("return (d.body.innerText.match(/[^\\n]*저장[^\\n]*/g)||[]).slice(0,3).join(' | ');")
        snap = o.run("snapshot"); refs = (snap.get("result") or {}).get("refs") or {}
        cnt = next((v.get("name") for v in refs.values() if "임시저장된 글 보기" in (v.get("name") or "")), "?")
        shot = o.screenshot(os.path.join(SHOT_DIR, "%s_filled.png" % stem))
        log("save clicked. toast=%r drafts=%r shot=%s" % (toast, cnt, shot))
        if "0개" in str(cnt):
            log("STATUS: OK (부분: 임시글 개수가 0 — 에디터에 내용은 남아 있으니 JJ 가 화면에서 «저장» 확인)"); return 0
        log("태그는 발행 창에서 JJ 가 붙인다: %s" % " ".join("#" + t for t in prep["tags"]))
        log("STATUS: OK (임시저장 — 발행은 JJ)"); return 0
    except Missing as e:
        o.screenshot(os.path.join(SHOT_DIR, "%s_failed.png" % stem))
        log("멈춤 — 더 누르지 않는다: %s" % e)
        log("STATUS: FAIL %s" % str(e)[:40]); return 1


def probe(blog, log):
    o = Orca(find_page(blog))
    time.sleep(3)
    log("url: %s" % o.url())
    log("editor_ready: %s" % o.editor_ready())
    log("state: %s" % o.state())
    os.makedirs(SHOT_DIR, exist_ok=True)
    snap = o.run("snapshot")
    refs = (snap.get("result") or {}).get("refs") or {}
    log("buttons: %s" % ", ".join(sorted(v.get("name", "") for v in refs.values() if v.get("role") == "button")[:30]))
    log("screenshot -> %s" % o.screenshot(os.path.join(SHOT_DIR, "probe.png")))
    return 0


# ---------------------------------------------------------------- self-test
#: 영상 절 표본 — 구간·주소가 **있는** 줄과 **없는** 줄 둘 다 든다.
_VID_MD = ("## 영상\n\n"
           "1. `workshop\\v.mp4` · 3~9.5 · https://x.com/OpenAI/status/1 — 스케치가 그림이 되는 구간\n"
           "2. `workshop\\w.mp4` — 통째로\n\n## 태그\n")


def _raises_missing(fn, head):
    """그 호출이 `Missing` 을 내고, 사유가 그 말로 시작하는가."""
    try:
        fn()
    except Missing as e:
        return str(e).startswith(head)
    return False


def self_test():
    global BLOG_DIR
    import tempfile
    root = tempfile.mkdtemp(prefix="naverdraft_")
    BLOG_DIR = os.path.join(root, "blog"); os.makedirs(BLOG_DIR)
    md = ("---\nkind: daily\nstatus: ready\n---\n\n# 제목 하나 (2026년 9월 8일)\n\n## 요약\n\n한 문장이에요.\n\n## 본문\n\n"
          "### Q. 왜?\n\n**굵은 첫 문장이에요.** 둘째 <문장>. (출처: a.com · 2026-09-08)\n\n### Q. 둘?\n\n문단.\n\n| 소식 | 날짜 |\n|---|---|\n| 하나 | 9/8 |\n\n"
          "## FAQ\n\n**Q. 하나?**\n답.\n\n## 토망치랩 한마디\n\n판단이에요.\n\n## 관련글\n\n☞ 카드 — x\n\n## 이미지\n\n"
          "1. `workshop\\a.png` — 표지 (출처: 토망치랩)\n\n## 태그\n\n#AI뉴스 #토망치랩\n")
    io.open(os.path.join(BLOG_DIR, "t.md"), "w", encoding="utf-8").write(md)
    p, meta, body = read_post("t")
    title, chunks, tags, images = parse_blocks(body)
    src = io.open(__file__, encoding="utf-8").read()
    cases = [
        ("제목", title == "제목 하나 (2026년 9월 8일)"),
        ("청크 = 요약 · Q 둘 · FAQ · 한마디 · 관련글 = 6", len(chunks) == 6 and chunks[1].startswith("<h3>Q. 왜?</h3>") and chunks[2].startswith("<h3>Q. 둘?</h3>")),
        ("[[이미지 N]] 줄은 ('img', N) 조각이 된다", (lambda c: ("img", 2) in c and all("[[이미지" not in x for x in c if isinstance(x, str)))(parse_blocks(body.replace("### Q. 둘?", "[[이미지 2]]\n\n### Q. 둘?"))[1])),
        ("굵게 strong · 표 table · 이스케이프", "<strong>굵은 첫 문장이에요.</strong>" in chunks[1] and "<table><tr><th>소식</th>" in chunks[2] and "&lt;문장&gt;" in chunks[1]),
        ("절 제목 h2", chunks[3].startswith("<h2>FAQ</h2>") and chunks[4].startswith("<h2>토망치랩 한마디</h2>")),
        ("태그·이미지는 따로, 본문에 안 들어간다", tags == ["AI뉴스", "토망치랩"] and images[0]["path"] == "workshop\\a.png" and not any("a.png" in c or "#AI뉴스" in c for c in chunks)),
        ("상대 경로는 있는 쪽으로 — HQ 에만 있는 파일은 HQ, 어디에도 없으면 워크숍 루트, 절대 경로는 그대로",
            resolve_image(os.path.join("scripts", "naver_draft.py")) == os.path.join(HQ, "scripts", "naver_draft.py")
            and resolve_image(r"reports\blog\img\없는파일.png") == os.path.join(WORKSHOP_ROOT, r"reports\blog\img\없는파일.png")
            and resolve_image(os.path.join(HQ, "scripts", "naver_draft.py")) == os.path.join(HQ, "scripts", "naver_draft.py")),
        # ── 본문 차례 검증 (2026-09-12) — 폐기된 «한마디» 를 요구하던 자리 ──────────
        ("차례: 한마디 **없는** 새 초안이 통과한다 (폐기된 절을 요구하지 않는다)",
            body_order_problem(_ORDER_OK) is None),
        ("차례: 한마디 **있는** 옛 초안도 그대로 통과한다 (기발행분이 안 깨진다)",
            body_order_problem(_ORDER_OK.replace("## FAQ", "## FAQ\n\n## 토망치랩 한마디")) is None),
        # 🔴 반대쪽 — 셋 다 «걸려야 하는» 입력이다. 없으면 «전부 통과시키는 검사» 도 위를 통과한다.
        ("차례: 관련글이 없으면 걸린다",
            (body_order_problem(_ORDER_OK.replace("관련글", "딴말")) or "").startswith("차례 표시를 못 찾았다")),
        ("차례: FAQ 와 관련글 순서가 뒤집히면 걸린다",
            (body_order_problem("관련글\n(출처: a)\n(출처: b)\n(출처: c)\nFAQ") or "").startswith("차례가 뒤섞였다")),
        ("차례: 출처 줄이 모자라면 걸린다 (조각이 잘렸다는 뜻)",
            (body_order_problem(_ORDER_OK.replace("(출처: c)", "")) or "").startswith("출처 줄이")),
        # ── 이미지 업로드 판정 (2026-09-12) — «개수» 가 아니라 «그 장» ─────────────
        # 🔴 찾을 문자열을 이어 붙여 만든다 — 안 그러면 **이 줄 자체가** src 에 있어 늘 걸린다(위와 같은 함정).
        ("업로드 판정이 개수 세기가 아니다 (alt 로 그 장을 본다)",
            "getAttribute('alt')" in UPLOADED_JS
            and ("filter(i=>/pstatic|blogfiles/" + ".test(i.src)).length") not in src),
        ("업로드 판정은 자리표를 «올라갔다» 로 읽지 않는다 (세 값이 갈린다)",
            all(v in UPLOADED_JS for v in ("'none'", "'ok'", "'placeholder'"))),
        # ── 영상 절 (2026-09-12) — 블로그에 영상 축이 아예 없던 자리 ──────────────
        ("영상 절이 없으면 빈 목록이다 (영상 없는 편은 아무것도 안 바뀐다)", parse_videos(body) == []),
        ("영상 줄 파싱: 경로 · 구간 · 주소 · 설명이 갈린다",
            parse_videos(_VID_MD) == [{"path": "workshop\\v.mp4", "start": 3.0, "end": 9.5,
                                       "url": "https://x.com/OpenAI/status/1", "caption": "스케치가 그림이 되는 구간"},
                                      {"path": "workshop\\w.mp4", "start": None, "end": None,
                                       "url": None, "caption": "통째로"}]),
        ("[[영상 N]] 줄은 ('vid', N) 조각이 된다",
            ("vid", 1) in parse_blocks(body.replace("### Q. 둘?", "[[영상 1]]\n\n### Q. 둘?"))[1]),
        ("영상 자리만 적어도 이미지 자동 배치는 안 꺼진다 (종류마다 따로 본다)",
            (lambda c: not any(isinstance(x, tuple) and x[0] == "img" for x in c)
                       and any(isinstance(x, tuple) and x[0] == "vid" for x in c))(
                parse_blocks(body.replace("### Q. 둘?", "[[영상 1]]\n\n### Q. 둘?"))[1])),
        # 🔴 반대쪽 — 걸려야 하는 입력 둘. 없으면 «전부 받아들이는 파서» 도 위를 통과한다.
        ("꼴이 안 맞는 줄은 영상 목록에 안 들어간다",
            parse_videos(_VID_MD.replace("1. `workshop\\v.mp4`", "- workshop/v.mp4")) ==
            parse_videos(_VID_MD)[1:]),
        ("구간이 비면 굽지 않고 선다 (ffmpeg 까지 가지 않는다)",
            _raises_missing(lambda: gif_for({"path": __file__, "start": 5.0, "end": 5.0,
                                             "url": None, "caption": ""}), "영상 구간이 비었다")),
        # 검사 문자열은 이어 붙여 만든다 — 이 줄 자체가 검사에 걸리지 않게
        ("OS 키 입력 경로 없음 (run 에 type·keypress 호출 0건)", ("run(\"" + "type\"") not in src and ("run(\"" + "keypress\"") not in src),
        ("발행 버튼을 누르는 코드 없음", ("click_named_button(\"" + "발행\")") not in src),
    ]
    for n_, v in cases:
        print(("PASS " if v else "FAIL ") + n_)
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
