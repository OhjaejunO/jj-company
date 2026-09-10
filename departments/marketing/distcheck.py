# -*- coding: utf-8 -*-
"""유통 변환 게이트 — 발행 완료 편 → Threads 텍스트 스레드 초안 검수 (2026-08-27).

설계 정본은 `docs/workers/distribution-transform.md` GATE ⓐ~ⓔ 다. 이 파일은 그 명세의 구현이고,
**출력 형태가 캐러셀 20장에서 텍스트 3~5포스트로 바뀐 것**(JJ 지시 2026-08-27)에 맞춰
ⓒ(장수·길이)만 «포스트 수·포스트당 글자 수»로 대체했다. 나머지 ⓐⓑⓓⓔ 는 명세 그대로다.

**어미·자기언급·부정톤 판정은 사본을 두지 않는다.** 라이브 스킬 `epcheck.py` 의 정규식을
**런타임에 원문에서 추출**해 쓴다 — 사본이면 스킬이 규격을 고칠 때 조용히 갈린다
(정관 §0 «실물을 조회할 수 있는 것은 실물이 정본»). 추출에 실패하면 **예외를 던진다**;
못 찾았는데 통과시키면 검사가 헛도는 것을 아무도 모른다(정관 §0 «조용히 실패하는 코드»).

사용:
    py distcheck.py --selftest                       역검증 (검사마다 «그 검사만» 걸리는지)
    py distcheck.py --ep 34 --draft <초안.md>         편 폴더를 읽어 초안을 검수

초안 형식은 `dist_transform.py` 의 모듈 독스트링에 있다.
"""
import argparse
import io
import json as _json
import os
import re
import sys

# 두 모듈이 서로를 import 하므로 한 번만 감싼다 - 겹쳐 감싸면 앞 래퍼가 버퍼를 닫는다.
if hasattr(sys.stdout, "buffer") and not getattr(sys.stdout, "_dist_wrapped", False):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stdout._dist_wrapped = True

# ── 채널 제약 ────────────────────────────────────────────────────────────
#: Threads 포스트당 글자 상한. **공표값이고 우리 실측이 아니다**
#: (`04_운영/유통확장_설계안.md` §3). 플랫폼이 거부하는 상한이라 초과는 FAIL 이다.
THREADS_CHAR_MAX = 500
#: 스레드 길이 상한. JJ 지시 2026-08-27 «3~5개 포스트» 중 **상한만 남았다.**
#: 🔴 **하한 3 은 2026-09-10 에 1 로 내렸다 (JJ 지시 «바꿔서 해보자»).**
#: 종전 하한은 «한 편을 3~5 토막으로 나눠라» 를 뜻했는데, 그 분할이 도달을 깎는다는 것이
#: 실측으로 나왔다 — `reports/2026-09-10_threads-benchmark.md`. 같은 계정 같은 편에서
#: 부모 포스트 67♥ 에 이어 붙인 체인이 `1/` 5♥ · `2/` 4♥ · `3/` 3♥ 로 **13배 떨어졌고**,
#: 팔로워 29.1만 계정의 상위 포스트는 **전부 단일 포스트 179~264자**였다.
#: 즉 **레퍼런스가 쓰는 꼴이 이 하한에 걸려 통과할 수 없었다** — 정관 §0
#: «검사가 틀린 것을 요구하고 있으면 산출물보다 검사부터 고친다»(ep28 게이트 선례) 자리다.
#: 하한을 없앤 것이 아니라 1 로 내린 것이고, 상한 5 는 그대로다 — 체인은
#: «본문의 나머지» 가 아니라 «더 볼 사람만 가는 심화» 로 쓰면 된다.
POSTS_MIN, POSTS_MAX = 1, 5

#: v3.56 — «공식» 빈도. **편 합산**이다(원고 포스트 + 카드 문안), 카드당이 아니다.
#: 🔴 단위가 판정을 뒤집는다 — ep39 실측으로 카드 합계 8회·카드별 최대 2회라,
#:    «카드당» 으로 읽으면 통과하고 «편 합산» 으로 읽으면 크게 걸린다. JJ 확정은 **편 합산**.
OFFICIAL_WORD = "공식"
OFFICIAL_WORD_MAX = 2
#: 이 검사가 도는 최소 편 판본. 편 게이트의 `since=` 와 같은 뜻이고, 값도 같이 움직인다.
OFFICIAL_WORD_SINCE = (3, 56)

#: 벤치마크 수치를 실은 포스트가 달아야 하는 라벨 (JJ 지시 · 캡션·킷 관례 그대로).
#: 카드 게이트 `[5-4]` SELF_REF 는 «공식 발표» 를 금지하지만 **그건 카드 층 규칙**이고,
#: 캡션 층은 ep34 캡션 «점수는 공식 발표 수치입니다» 처럼 이 라벨을 쓴다. Threads 본문은 캡션 층이다.
OFFICIAL_LABEL = "공식 발표 수치"

#: v3.60 — 발표 행위 서술 상한 (지시서 1-6 · JJ 문안 2026-08-29).
#: 카드 층 상한은 `epcheck.ATTRIB_MAX` 이고 값이 같다. **지면이 다르므로 각각 1회**다 —
#: 카드에서 한 번 쓰고 포스트에서 또 한 번 쓰는 것은 중복이 아니라 각 지면의 리드다.
ATTRIB_MAX = 1
#: 이 검사가 도는 최소 편 판본.
ATTRIB_SINCE = (3, 60)

#: 캡션 복붙 판정 — 한글만 남긴 뒤 이 길이의 연속 일치가 있으면 «다시 쓰지 않은 것»으로 본다.
#: 고유명사·숫자·영문은 어차피 같아야 하므로 판정에서 뺀다.
CAPTION_SHINGLE = 12

URL_RE = re.compile(r"https?://\S+")
#: 한글이 한 자라도 있는가 — «우리 산문인가» 의 바닥선 (어미 검사 대상 판정).
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_TAGLINE_RE = re.compile(r"^[#@][^\s]+(\s+[#@][^\s]+)*$")

# ── 첨부 미디어 ─────────────────────────────────────────────────────────
#: 첨부를 허용하는 편 폴더 하위 경로. **화이트리스트다** — 금지 목록이 아니다.
#: 편 폴더 루트의 `01_cover.png`·`02_banner.png` 는 **우리가 조립한 카드**이고
#: `shots/02_banner.png` 는 **공식 원본**이다. 파일명이 겹치므로 디렉토리가 유일한 구분이며,
#: 금지 목록으로 짜면 새 산출물 이름이 생길 때마다 조용히 새는 쪽으로 기운다.
#: 첨부를 허용하는 폴더. 편 폴더 루트의 덱 산출물(우리가 조립한 카드)을 막는 화이트리스트다.
#: 🔴 **`_official/` 은 2026-08-29 에 더했다.** 그 전에는 `[10-6]` 이 «공식 영상 선언이 있으면
#:    첨부에 영상 1건 이상» 을 요구하면서, 정작 **공식 원본이 사는 유일한 폴더를 막고 있었다** —
#:    `_official\` 은 C-22 가 «미채택 공식 원본을 여기 보존한다» 로 정한 자리다. 두 규칙이
#:    정면으로 부딪혀 ep39 는 **통과할 수 있는 조합이 없었다.** 정관 §0 «검사가 틀린 것을
#:    요구하고 있으면 산출물보다 검사부터 고친다» 그대로다(ep28 게이트 선례와 같은 꼴).
MEDIA_DIRS = ("shots/", "_assets/", "_official/")
#: 편 폴더 루트의 덱 산출물 꼴 — 걸렸을 때 «인스타 카드를 붙였다» 고 짚어 주기 위한 것.
_DECK_RE = re.compile(r"^\d\d_[^/]+\.(png|jpg|jpeg|mp4)$", re.I)
#: 본문에 넣는 출처 줄. 카드에서는 하단 크레딧 라벨이 하던 일을 **본문이 대신한다** —
#: 공식 원본을 그대로 붙이므로 크레딧이 그림 안에 박혀 있지 않다(SKILL §6 크레딧 형식).
CREDIT_LINE_RE = re.compile(r"^(이미지|영상)\s*출처:\s*(?P<v>.+?)\s*$")
#: 서드파티 자작 시연 영상 4조건 ⓓ — 발행팩에 있어야 하는 절 (SKILL v3.55 §6).
THIRDPARTY_SECTION = "## 서드파티 영상 승인"


# ── 라이브 스킬에서 규격을 빌려온다 ──────────────────────────────────────
def skill_dir():
    p = os.environ.get("TOMANGCHI_SKILL")
    if p:
        return p
    return os.path.join(os.path.expanduser("~"), ".claude", "skills", "tomangchi")


_RX_CACHE = {}


def skill_regex(name):
    """라이브 `epcheck.py` 원문에서 `NAME = re.compile(r"...")` 을 찾아 컴파일한다.

    사본을 두지 않는 이유는 모듈 독스트링에 있다. 못 찾으면 던진다 — 조용히 통과시키지 않는다."""
    if name in _RX_CACHE:
        return _RX_CACHE[name]
    path = os.path.join(skill_dir(), "epcheck.py")
    if not os.path.exists(path):
        raise RuntimeError("라이브 스킬 epcheck.py 를 못 찾았다: %s (TOMANGCHI_SKILL 확인)" % path)
    src = io.open(path, encoding="utf-8").read()
    m = re.search(r"^\s*%s\s*=\s*re\.compile\(\s*r\"(?P<p>.*?)\"\s*\)" % re.escape(name), src, re.M)
    if not m:
        raise RuntimeError("epcheck.py 에서 %s 정규식을 못 찾았다 — 스킬이 규격을 옮겼는지 확인" % name)
    rx = re.compile(m.group("p"))
    _RX_CACHE[name] = rx
    return rx


def skill_revision():
    """어느 판본의 규격으로 검사했는지. 근거는 라이브의 `.deployed` 스탬프다 (정관 §4)."""
    path = os.path.join(skill_dir(), ".deployed")
    if not os.path.exists(path):
        return "미상 (.deployed 없음)"
    for ln in io.open(path, encoding="utf-8").read().splitlines():
        if ln.startswith("short:"):
            return ln.split(":", 1)[1].strip()
    return "미상"


# ── 초안 파싱 ────────────────────────────────────────────────────────────
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")


def sentences(text):
    """문장 단위. 문장 종결부호 뒤 공백, 또는 줄바꿈으로 가른다.

    «1.0» «3.8» 처럼 숫자 사이의 점은 뒤가 공백이 아니라 갈리지 않는다 (역검증에 케이스 있음)."""
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]


def _table_cells(ln):
    """마크다운 표의 한 줄에서 칸들을 뽑는다. 구분선·헤더면 None."""
    if not ln.strip().startswith("|"):
        return None
    cells = [c.strip() for c in ln.strip().strip("|").split("|")]
    if not cells or set(cells[0]) <= set("-: "):
        return None
    if not re.match(r"^[Pp](\d+)$", cells[0]):
        return None                             # 헤더 줄
    return cells


def _parse_ver(v):
    """«v3.56» → (3, 56). 못 읽으면 None — **모름을 «통과» 로 읽지 않는다.**"""
    m = re.match(r"^v?(\d+)\.(\d+)", str(v or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_draft(text):
    """`## P1` 블록 · `## 소스 맵` 표 · `## 첨부 미디어` 표를 읽는다.

    반환 (posts, rows, media).
    posts  = [본문 문자열, ...]
    rows   = [(포스트번호, 문장번호, 근거문자열), ...]
    media  = [{post, path, src_key, credit, tier, shape}, ...]"""
    posts, rows, media = [], [], []
    cur, buf, sect = None, [], None
    for ln in (text or "").splitlines():
        m = re.match(r"^##\s*P(\d+)\s*$", ln.strip())
        if m:
            if cur is not None:
                posts.append("\n".join(buf).strip())
            cur, buf, sect = int(m.group(1)), [], None
            continue
        head = ln.strip()
        if head.startswith("##"):
            if cur is not None:
                posts.append("\n".join(buf).strip())
                cur, buf = None, []
            if re.match(r"^##\s*소스\s*맵", head):
                sect = "map"
            elif re.match(r"^##\s*첨부\s*미디어", head):
                sect = "media"
            else:
                sect = None
            continue
        if sect == "map":
            cells = _table_cells(ln)
            if not cells or len(cells) < 3:
                continue
            pi = int(re.match(r"^[Pp](\d+)$", cells[0]).group(1))
            try:
                rows.append((pi, int(cells[1]), cells[2]))
            except ValueError:
                rows.append((pi, -1, cells[2]))
        elif sect == "media":
            cells = _table_cells(ln)
            if not cells or len(cells) < 6:
                continue
            media.append({"post": int(re.match(r"^[Pp](\d+)$", cells[0]).group(1)),
                          "path": cells[1].strip("`"), "src_key": cells[2],
                          "credit": cells[3], "tier": cells[4], "shape": cells[5],
                          # 7번째 열(선택) — 발행용 공개 URL. 워커가 파일 업로드가 아니라
                          # «URL 을 주면 Threads 가 받아가는» 방식이라 필요하다 (2026-09-02).
                          "url": (cells[6] if len(cells) > 6 else "").strip()})
        elif cur is not None:
            buf.append(ln)
    if cur is not None:
        posts.append("\n".join(buf).strip())
    return posts, rows, media


# ── 검사 ────────────────────────────────────────────────────────────────
class Result(object):
    def __init__(self):
        self.items = []          # (라벨, 판정 'OK'|'FAIL'|'NA', 상세)

    def ok(self, label, cond, detail=""):
        self.items.append((label, "OK" if cond else "FAIL", "" if cond else str(detail)[:220]))

    def na(self, label, why):
        self.items.append((label, "NA", why))

    @property
    def failed(self):
        return [i for i in self.items if i[1] == "FAIL"]

    def labels_failed(self):
        return {i[0].split("]")[0] + "]" for i in self.failed}


def _strip_urls(t):
    return URL_RE.sub(" ", t)


def _hangul(t):
    return re.sub(r"\s+", " ", re.sub(r"[^가-힣\s]+", " ", t or "")).strip()


def declared_text(facts):
    """편이 `_facts.py` 에 **선언한 문자열 값**을 전부 이어 붙인다. [1] 의 보조 어휘용."""
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, (list, tuple, set, frozenset)):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(k)
                walk(x)

    for name in dir(facts):
        if name.startswith("_") or callable(getattr(facts, name, None)):
            continue
        walk(getattr(facts, name))
    return "\n".join(out)


def probe_media(path):
    """실물을 재서 («이미지»|«영상», 폭, 높이, 초) 를 돌려준다. 못 재면 초를 None 으로.

    선언한 형상이 맞는지는 **파일이 정한다** — 표에 적은 값을 믿지 않는다(정관 §0 «실물이 정본»)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        from PIL import Image
        with Image.open(path) as im:
            return "이미지", im.size[0], im.size[1], None
    if ext in (".mp4", ".mov", ".webm", ".m4v"):
        import subprocess
        try:
            out = subprocess.check_output(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height:format=duration", "-of", "default=nw=1:nk=1", path],
                stderr=subprocess.STDOUT).decode("utf-8", "replace").split()
            return "영상", int(out[0]), int(out[1]), round(float(out[2]), 2)
        except Exception:                        # noqa: BLE001 — ffprobe 부재/실패는 «확인 불가»
            return "영상", None, None, None
    return "알 수 없음", None, None, None


#: 같은 URL 을 `[10-8]` 과 `pack()` 이 각각 받는다 — 한 회차에 두 번 내려받지 않는다.
#: (ep51 실측 21MB · 영상 편은 이 캐시가 없으면 회차마다 수십MB 를 두 번 받는다.)
_URL_CACHE = {}


def fetch_url_bytes(url, timeout=120):
    """URL 바이트를 받아 돌려준다 — `(bytes, None)` 또는 `(None, 사유)`.

    🔴 **못 받은 것은 «빈 것» 이 아니다.** 사유를 같이 돌려주고, 부르는 쪽은 그것을
    FAIL 로 적는다 — 조용히 통과시키면 워커가 발행 직전에야 알게 된다(정관 §0).
    """
    if url in _URL_CACHE:
        return _URL_CACHE[url]
    import urllib.request as _ur
    try:
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        got = (_ur.urlopen(req, timeout=timeout).read(), None)
    except Exception as e:                       # noqa: BLE001 — 확인 불가는 통과가 아니다
        got = (None, str(e)[:80])
    _URL_CACHE[url] = got
    return got


def probe_bytes(blob, name_hint):
    """`probe_media` 를 **바이트에** 대고 돈다 — URL 로 받은 것을 잴 때 쓴다.

    ffprobe·PIL 이 둘 다 «파일» 을 받으므로 임시 파일로 한 번 내렸다 지운다.
    확장자는 URL 에서 따온다 — `probe_media` 가 확장자로 갈래를 가르기 때문이다.
    """
    import tempfile
    ext = os.path.splitext(name_hint.split("?")[0])[1].lower() or ".bin"
    fd, tmp = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        return probe_media(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def shape_mismatch(declared, kind, w, h, dur):
    """선언 형상과 실측이 어긋난 사유 한 줄. 맞으면 `None`.

    `[10-5]`(로컬 파일)와 `[10-8]`(URL 바이트)이 **같은 함수로** 잰다 — 두 벌로 두면
    한쪽만 고쳐지고 그때부터 두 축이 다른 것을 재게 된다.
    """
    if not declared.startswith(kind):
        return "선언«%s» 실물«%s»" % (declared, kind)
    if w and ("%dx%d" % (w, h)) not in declared.replace("×", "x"):
        return "해상도 선언«%s» 실물 %dx%d" % (declared, w, h)
    if kind == "영상" and dur is not None and ("%gs" % dur) not in declared:
        return "길이 선언«%s» 실측 %gs" % (declared, dur)
    return None


def check_media(media, posts, facts, ep, r):
    """`[10-*]` 첨부 미디어 — 공식 원본만, 크레딧은 본문에, 우리 카드는 금지.

    설계 근거: SKILL §6 소스 실물 위계·크레딧 형식 · v3.30 공식 프로모 자산(크레딧 = 회사명) ·
    v3.55 §6 서드파티 자작 시연 영상 4조건 · v3.54 §7 공식 영상 우선."""
    ep_dir = ep["dir"]

    # [10-0] 🔴 **P1 에 공식 미디어 1건 필수** (2026-09-10 신설 · JJ 지시 · 레퍼런스 실측).
    #
    #   근거는 `reports\2026-09-10_threads-benchmark.md` 재조회다 — 팔로워 29.1만
    #   `@choi.openai` 의 최근 10건 중 미디어가 붙은 8건이 **전부 이미지 1장**이었고
    #   (영상 0건), 성격은 공식 발표 자료 캡처였다. 호스트는 전부 메타 자기 CDN 이라
    #   **앱에서 직접 올린 것**이고, 그 자리를 우리는 공개 URL 로 대신한다.
    #
    #   🔴 **«무조건» 이 아니라 «P1 에» 다.** 같은 조회에서 우리 크기 계정
    #   (`@ai.vibe.code` 661)은 **미디어 0건으로 51♥·56♥** 가 나왔다 — 미디어가
    #   보편 법칙이라는 증거는 없다. 잰 것은 «소식 편의 첫 포스트» 뿐이라 거기까지만 건다.
    #   P2(링크 포스트)는 대상이 아니다 — Threads 가 링크 썸네일을 스스로 붙인다(실측).
    p1 = [m for m in media if m["post"] == 1]
    p1_official = [m for m in p1 if "공식" in (m.get("tier") or "")]
    r.ok("[10-0] P1 에 공식 미디어 1건 이상", bool(p1_official),
         "P1 첨부 %d건 (공식 %d건)" % (len(p1), len(p1_official)))

    if not media:
        r.na("[10] 첨부 미디어", "선언 0건 — 텍스트 전용 스레드")
    else:
        # [10-1] 실재 · [10-2] 우리 카드 금지 (화이트리스트)
        missing, ours = [], []
        for m in media:
            p = m["path"].replace("\\", "/")
            if not any(p.startswith(d) for d in MEDIA_DIRS):
                ours.append("P%d %s%s" % (m["post"], p,
                                          " ← 편 폴더 루트의 덱 산출물(우리가 조립한 카드)"
                                          if _DECK_RE.match(p) else ""))
                continue
            if not os.path.exists(os.path.join(ep_dir, p)):
                missing.append("P%d %s" % (m["post"], p))
        r.ok("[10-1] 첨부 파일이 편 폴더에 실재", not missing, " / ".join(missing))
        r.ok("[10-2] 우리 제작 카드 금지 — 첨부는 %s 아래만" % "·".join(MEDIA_DIRS),
             not ours, " / ".join(ours))

        # [10-3] 첨부의 출처가 **편에 등록돼 있는가**. 정본으로 인정하는 자리가 셋이다 —
        #   ⓐ `_facts.py` 의 URL 변수 (기본)
        #   ⓑ 편 선언 `OFFICIAL_VIDEO = {url, dur}` (2026-09-02 · ep42)
        #   ⓒ 편 **검증로그**에 그 첨부 파일이 등재 (2026-09-10 · ep50/ep54)
        bad_src = []
        for m in media:
            k = m["src_key"]
            # 🔴 `VERIFY_LOG` 특례 (2026-09-10 · ep50·ep54 실측). **공식 이미지에는 ⓐ·ⓑ 어느
            # 쪽도 열려 있지 않았다** — `OFFICIAL_VIDEO` 는 영상 전용이고, 두 편의 `_facts.py`
            # 에는 URL 변수가 **0개**다(ep54 는 아티클 주소가 docstring 에만, ep50 은 아예 없다).
            # 두 편 다 `_official/shots/` 에 공식 도표를 갖고 있는데(ep54 Figure 1~7 + 배너,
            # ep50 공식 삽화 2장 포함 7장) **붙일 수 있는 조합이 없었다** — 같은 날 신설한
            # `[10-0]`(P1 에 공식 미디어 필수)과 정면으로 부딪혀 두 편은 어떤 원고로도 통과할 수
            # 없다. 편 폴더가 `01_발행완료` 라 선언을 더할 수도 없다(§2 예외 4 는 `02_제작중` 한정).
            # 정관 §0 «검사가 틀린 것을 요구하고 있으면 산출물보다 검사부터 고친다» — ep28·ep39·
            # `[10-8]` 과 같은 꼴이다.
            #
            # 🔴 **느슨해지지 않는다.** 재는 것은 «출처가 편에 «적혀» 있는가» 그대로이고, 자리만
            # 검증로그로 넓혔다 — 검증로그는 **그 편의 출처 정본 문서**이고 이미 `[10-7ⓒ]` 가 읽는
            # 게이트 입력이다. 파일 이름이 거기 없으면 종전대로 걸린다. 검증로그는 편 폴더에 있어
            # 우리가 못 고친다(§2) — 즉 **자기 서명으로 만들 수 없는 근거**다.
            if k == "VERIFY_LOG":
                vlog = ep.get("verify_log") or ""
                base = os.path.basename(m["path"] or "")
                if base and base in vlog:
                    continue
            # `OFFICIAL_VIDEO` 특례 (2026-09-02 · ep42 실측). 공식 영상의 URL 정본은
            # _facts 가 아니라 **편 선언** `OFFICIAL_VIDEO = {url, dur}` 다(SKILL v3.54 §7 이
            # 거기 두라고 정했다). ep42 는 _facts 에 URL 변수가 하나도 없어 종전 규칙으로는
            # 공식 영상을 붙일 길이 없었다 — `[5-2]` 의 KIT_URL 특례(편 선언 KIT["url"] 이
            # 정본)와 같은 꼴로 연다. 선언이 없거나 url 이 없으면 종전대로 걸린다.
            if k == "OFFICIAL_VIDEO":
                ov = ep.get("OFFICIAL_VIDEO")
                if (isinstance(ov, dict) and isinstance(ov.get("url"), str)
                        and URL_RE.match(ov["url"])):
                    continue
            v = getattr(facts, k, None) if k and not k.startswith("_") else None
            if not isinstance(v, str) or not URL_RE.match(v):
                bad_src.append("P%d %s" % (m["post"], k or "(빈칸)"))
        r.ok("[10-3] 출처키가 편에 등록돼 실재 (_facts URL · OFFICIAL_VIDEO · VERIFY_LOG)",
             not bad_src, " / ".join(bad_src))

        # [10-4] 크레딧 문구가 그 포스트 본문에 있는가 (카드 하단 라벨 역할을 본문이 대신한다)
        no_credit = []
        for m in media:
            i = m["post"]
            body = posts[i - 1] if 1 <= i <= len(posts) else ""
            vals = [cm.group("v") for cm in
                    (CREDIT_LINE_RE.match(l.strip()) for l in body.splitlines()) if cm]
            if m["credit"] not in vals:
                no_credit.append("P%d «%s» 없음 (본문 출처 줄 %s)" % (i, m["credit"], vals or "0건"))
        r.ok("[10-4] 크레딧이 해당 포스트 본문 출처 줄에", not no_credit, " / ".join(no_credit))

        # [10-5] 선언한 형상이 실물과 맞는가 — 길이·해상도는 실측으로 대조한다
        shape_bad, shape_na = [], []
        for m in media:
            p = os.path.join(ep_dir, m["path"].replace("\\", "/"))
            if not os.path.exists(p):
                continue
            kind, w, h, dur = probe_media(p)
            why = shape_mismatch(m["shape"], kind, w, h, dur)
            if why:
                shape_bad.append("P%d %s" % (m["post"], why))
            elif w is None:
                shape_na.append("P%d %s" % (m["post"], os.path.basename(p)))
        r.ok("[10-5] 선언 형상 = 실물 (해상도·영상 길이 실측 대조)", not shape_bad, " / ".join(shape_bad))
        if shape_na:
            r.na("[10-5] 실측 불가 항목", "ffprobe 로 못 잰 파일: %s" % " / ".join(shape_na))

    # [10-6] 공식 영상 우선 (SKILL v3.54 §7 — Threads 는 영상 도달이 가장 높다)
    ov = ep.get("OFFICIAL_VIDEO")
    if not ov:
        r.na("[10-6] 공식 영상 우선", "편 선언 OFFICIAL_VIDEO = 무 — 공식 이미지로 간다")
    else:
        has_v = [m for m in media if m["shape"].startswith("영상")]
        r.ok("[10-6] 공식 영상이 있으면 첨부에 영상 1건 이상", bool(has_v),
             "OFFICIAL_VIDEO 선언 있음 / 첨부 영상 0건")

    # [10-7] 서드파티 자작 시연 영상 4조건 (SKILL v3.55 §6) — 넷 중 하나라도 비면 쓰지 않는다
    tp = [m for m in media if m["tier"] == "서드파티" and m["shape"].startswith("영상")]
    if not tp:
        r.na("[10-7] 서드파티 자작 영상 4조건", "해당 첨부 0건")
    else:
        log, pack = ep.get("verify_log", ""), ep.get("pack", "")
        no_log = ["P%d %s" % (m["post"], m["src_key"]) for m in tp
                  if str(getattr(facts, m["src_key"], "")) not in log]
        r.ok("[10-7ⓒ] 서드파티 영상 출처가 검증로그에 있음", not no_log, " / ".join(no_log))
        r.ok("[10-7ⓓ] 발행팩에 «%s» 절" % THIRDPARTY_SECTION, THIRDPARTY_SECTION in pack,
             "절이 없다 — 승인을 «안 받은 것»과 «받고 안 적은 것»을 가르지 않는다")
        # ⓐ 크레딧은 [10-4] 가 이미 본다.
        r.na("[10-7ⓑ] 공식 UI 실물 여부",
             "육안 판정 — 기계가 **못 잡는다**. JJ 가 발행 전에 본다 (SKILL v3.55 §6)")

    # [10-8] 발행 URL 실측 (2026-09-02 신설 · **2026-09-10 기준 개정**).
    #
    #   🔴 **종전 축은 틀린 것을 재고 있었다.** 「URL 바이트 == 편 폴더 로컬 검증본 바이트」
    #   를 요구했는데, **나가는 것은 URL 바이트지 로컬 바이트가 아니다.** 실측(2026-09-10 ·
    #   ep51): 같은 X 포스트의 1080p 원본이 원격 20,965,746 바이트인데 우리 로컬본은
    #   20,959,125 바이트였다 — yt-dlp 가 HLS 로 받아 재먹싱한 판본이라 6,621 바이트가 다르다.
    #   즉 **정상인 상태가 FAIL 로 잡혔고, 통과할 수 있는 조합이 사실상 없었다**
    #   (`clause-backlog` C-26 «통과 조합이 없는 검사» 계열).
    #   정관 §0 «검사가 틀린 것을 요구하고 있으면 산출물보다 검사부터 고친다» — ep28 선례.
    #
    #   **고친 기준: URL 바이트가 정본이다.** URL 이 있으면 그것이 올라갈 것이므로
    #   ⓐ 열리는가 ⓑ **그 바이트의 형상이 선언과 맞는가** 를 잰다. 로컬 파일은 여전히
    #   `[10-1]`(편 폴더 실재)·`[10-2]`(우리 카드 아님)에서 **출처 층위 판정**에 쓰인다 —
    #   역할이 «올라갈 바이트의 기준» 에서 «출처가 무엇인가의 근거» 로 좁아졌을 뿐이다.
    #   해시 대조는 사라지지 않는다 — `pack()` 이 여기서 받은 바이트의 sha256 을 박고,
    #   워커가 발행 직전 다시 받아 그 값과 대조한다(회차 도중 CDN 이 갈리면 선다).
    withurl = [m for m in media if m.get("url")]
    if not withurl:
        r.na("[10-8] 발행 URL 실측", "URL 열 없음 — 워커가 못 올린다(사람 자리)")
    else:
        bad_url, url_na = [], []
        for m in withurl:
            blob, err = fetch_url_bytes(m["url"])
            if blob is None:
                bad_url.append("P%d 조회 실패: %s" % (m["post"], err))
                continue
            kind, w, h, dur = probe_bytes(blob, m["url"])
            if kind == "알 수 없음":
                url_na.append("P%d 형상 실측 불가 (ffprobe 부재?)" % m["post"])
                continue
            why = shape_mismatch(m["shape"], kind, w, h, dur)
            if why:
                bad_url.append("P%d URL 바이트 형상 불일치 — %s" % (m["post"], why))
        r.ok("[10-8] 발행 URL 이 열리고 그 바이트 형상 = 선언", not bad_url, " / ".join(bad_url))
        if url_na:
            r.na("[10-8] URL 형상 실측 불가", " / ".join(url_na))


def _tone_target(s):
    """어미 검사 대상 문자열. 검사에서 빼는 것 — URL 만 있는 줄 · 해시태그/멘션 줄 · 시그니처 이모지."""
    s = s.strip()
    if URL_RE.fullmatch(s) or _TAGLINE_RE.match(s) or CREDIT_LINE_RE.match(s):
        return ""   # 출처 줄은 크레딧 라벨이지 산문이 아니다 - 어미 규정 밖(SKILL 4.1 해시태그 제외와 같은 취지)
    # 🔴 **한글이 없는 줄은 우리 산문이 아니다** (2026-08-29 · 지시서 5-1 개정).
    #    뉴스형 편은 복붙 세트 자리를 «공식 발표 원문 인용» 으로 대신한다 — 영문 인용 줄이
    #    «…해요» 로 끝날 수는 없으므로, 빼지 않으면 **통과할 수 있는 원고가 없다**
    #    (`clause-backlog` C-26 «통과 조합이 없는 검사» 계열). URL·해시태그·크레딧 줄을
    #    같은 이유로 이미 빼고 있었고, 이것은 그 판정의 한 갈래다.
    if not HANGUL_RE.search(s):
        return ""
    s = URL_RE.sub(" ", s)
    s = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", s)
    return s.strip()


def check(posts, rows, facts, kit_url, caption, cardcheck, media=None, ep=None):
    """게이트 본체 — 순수 함수. 파일 접근은 호출자가 한다(역검증이 합성 입력을 넣을 수 있게)."""
    r = Result()
    HAEYO = skill_regex("HAEYO")
    HAPSYO = skill_regex("HAPSYO")
    PROCESS = skill_regex("PROCESS")
    VERIFY_MENTION = skill_regex("VERIFY_MENTION")
    ABSENCE = skill_regex("ABSENCE")
    body = "\n".join(posts)

    # [1] FACTS 대조 — 설계 ⓐ. 초안에 «적힌» 수치가 전부 편 어휘 안에 있는가.
    #     URL 은 사실 주장이 아니라 뺀다 (킷 주소의 «qwen38» 이 수치로 새던 결함).
    #     어휘에 더해 **편이 선언한 문자열 값에 실제로 적힌 수치**도 통과시킨다. `numeral_vocab()` 은
    #     킷 HTML 표기(«20,000,000»)를 기준으로 짜여 있어 산문 표기(«2천만 달러» → 토큰 «2»)가 새기 때문이다
    #     — 편이 선언하지 않은 수는 여전히 못 쓴다(새 수치 금지는 그대로).
    # 구세대 facts(ep40 이전)에는 numeral_vocab() 이 없다 — 없으면 빈 집합으로 간다.
    # 느슨해지는 쪽이 아니다: 허용 어휘가 줄어들 뿐이고, 편이 선언한 문자열 속 수치는
    # 아래에서 그대로 합산되므로 선언된 사실 수치는 여전히 통과한다.
    vocab = (set(facts.numeral_vocab()) if hasattr(facts, "numeral_vocab") else set()) \
        | set(getattr(facts, "NOISE", set()))
    _decl = _strip_urls(declared_text(facts))
    # 선언 문자열이 숫자 뒤 마침표로 끝나면(«…became OpenClaw 2.0.») 추출기 ② 의 경계
    # 규칙에 걸려 그 수치가 어휘에서 빠진다 — ep40 실측(선언에 «2.0» 이 실재하는데
    # [1] 이 «어휘 밖 2.0» 을 냈다). **수집 쪽에서만** 숫자 뒤 문장 끝 마침표를 공백으로
    # 바꾼다. 원고 검사 쪽(found)은 그대로라 판정이 느슨해지지 않는다 — 선언에 없는
    # 수는 여전히 걸린다(역검증 «7천만» 케이스가 그것을 지킨다).
    _decl = re.sub(r"(?<=\d)\.(?=\s|$)", " ", _decl)
    vocab |= cardcheck.kit_numerals(_decl)
    found = cardcheck.kit_numerals(_strip_urls(body))
    bad = sorted(found - vocab, key=lambda x: (len(x), x))
    r.ok("[1] FACTS 대조 — 초안 수치가 전부 numeral_vocab() 안", not bad, "어휘 밖 %s" % bad)

    # [2] 어미 해요체 — 설계 ⓑ. 판정은 라이브 epcheck 정규식 그대로.
    off = []
    for i, p in enumerate(posts, 1):
        for j, s in enumerate(sentences(p), 1):
            t = _tone_target(s)
            if not t:
                continue
            last = re.split(r"[.!?]\s+", t)[-1]
            if not (HAEYO.search(last) and not HAPSYO.search(last)):
                off.append("P%d-%d «%s»" % (i, j, s[:28]))
    r.ok("[2] 어미 해요체 (epcheck HAEYO/HAPSYO)", not off, " / ".join(off[:3]))

    # [3-1] 포스트 수 · [3-2] 포스트당 글자 수 — 설계 ⓒ 의 텍스트 스레드 판.
    r.ok("[3-1] 포스트 수 %d~%d" % (POSTS_MIN, POSTS_MAX),
         POSTS_MIN <= len(posts) <= POSTS_MAX, "%d개" % len(posts))
    lng = ["P%d %d자" % (i, len(p)) for i, p in enumerate(posts, 1) if len(p) > THREADS_CHAR_MAX]
    r.ok("[3-2] 포스트당 %d자 이하 (Threads 공표값)" % THREADS_CHAR_MAX, not lng, " / ".join(lng))

    # [4] 킷 URL 위치 — 설계 ⓓ. 마지막 포스트에만 1건, 값은 편 선언과 일치.
    urls = [(i, u) for i, p in enumerate(posts, 1) for u in URL_RE.findall(p)]
    early = ["P%d %s" % (i, u) for i, u in urls if i != len(posts)]
    last_urls = [u.rstrip(".,)»") for i, u in urls if i == len(posts)]
    r.ok("[4-1] 마지막 포스트 앞에는 URL 0건", not early, " / ".join(early))
    if kit_url:
        r.ok("[4-2] 마지막 포스트에 킷 URL 1건 · 편 선언과 일치",
             last_urls == [kit_url], "발견 %s / 선언 %s" % (last_urls, kit_url))
    else:
        # 킷 없는 편 규격 (2026-09-02 JJ 확정 · ep40 계기) — 마지막 포스트는 **원류 안내**다:
        # 본편 인스타 게시물 URL 1건, 값의 정본은 발행로그(load_ep 이 읽어 ep["post_url"] 로
        # 넘긴다). 로그에 없으면 post_url 이 아예 안 만들어져 여기까지 오지도 않는다.
        pu = (ep or {}).get("post_url") or ""
        r.ok("[4-2b] 킷 없는 편 — 마지막 포스트에 본편 인스타 URL 1건 (정본: 발행로그)",
             bool(pu) and [u.rstrip("/") for u in last_urls] == [pu.rstrip("/")],
             "발견 %s / 발행로그 %s" % (last_urls, pu or "(없음)"))

    # [5] 소스 맵 완결 — 설계 ⓔ. 문장 수 = 행 수 · 키 실재 · 무주장 행에는 수치 0개.
    cnt_s = {i: len(sentences(p)) for i, p in enumerate(posts, 1)}
    cnt_r = {}
    for pi, _, _ in rows:
        cnt_r[pi] = cnt_r.get(pi, 0) + 1
    mism = ["P%d 문장 %d ≠ 행 %d" % (i, n, cnt_r.get(i, 0)) for i, n in cnt_s.items() if cnt_r.get(i, 0) != n]
    mism += ["P%d 행만 있음" % i for i in cnt_r if i not in cnt_s]
    r.ok("[5-1] 문장 수 = 소스 맵 행 수", not mism, " / ".join(mism))
    unknown, numbered = [], []
    for pi, si, key in rows:
        for k in [x.strip() for x in key.split(",") if x.strip()]:
            if k == "-":
                sents = sentences(posts[pi - 1]) if 1 <= pi <= len(posts) else []
                s = sents[si - 1] if 1 <= si <= len(sents) else ""
                if cardcheck.kit_numerals(_strip_urls(s)):
                    numbered.append("P%d-%d «%s»" % (pi, si, s[:28]))
            elif k == "KIT_URL":
                continue
            elif k == "POST_URL" and (ep or {}).get("post_url"):
                # 킷 없는 편의 원류 URL — 정본은 발행로그, load_ep 이 실재를 이미 확인했다
                continue
            elif k == "OFFICIAL_VIDEO" and isinstance(ep.get("OFFICIAL_VIDEO"), dict):
                # 편 선언이 정본 — [10-3] 특례와 같은 근거 (2026-09-02 · ep42 실측)
                continue
            elif k == "VERIFY_LOG" and any(m.get("src_key") == "VERIFY_LOG"
                                           for m in (media or [])):
                # 🔴 `[10-3]` VERIFY_LOG 특례의 **짝** (2026-09-10 · 같은 날 뒤늦게 붙였다).
                # 첨부 출처 줄(«이미지 출처: …»)의 근거 키다. 종전에 `[10-3]` 만 열고 이쪽을
                # 안 열어서 **ep54 가 `[5-2]` 하나로 FAIL** 났다 — 특례를 열 때는 그 키가
                # 지나가는 자리를 **전부** 훑어야 한다는 실측이다.
                # 근거 자체는 `[10-3]` 이 이미 쟀다(그 첨부 파일이 검증로그에 실재). 여기서는
                # **그 첨부가 실재하는지**만 본다 — 첨부 없이 이 키만 적으면 종전대로 걸린다.
                continue
            elif not hasattr(facts, k):
                unknown.append("P%d-%d %s" % (pi, si, k))
    r.ok("[5-2] 근거 키가 _facts.py 에 실재", not unknown, " / ".join(unknown[:4]))
    r.ok("[5-3] 무주장 행(-)에는 수치 0개", not numbered, " / ".join(numbered[:3]))

    # [6] 자기 언급 · 제작/검증 과정 서사 — 캡션 층 검사 재사용 (epcheck [6] PROCESS · [7] VERIFY_MENTION).
    #     카드 층의 SELF_REF 는 쓰지 않는다 — 그쪽은 «공식 발표» 를 금지해 [8] 라벨과 정면으로 부딪힌다.
    hit = PROCESS.findall(body) + VERIFY_MENTION.findall(body)
    r.ok("[6] 자기 언급·과정 서사 0건", not hit, str(hit[:5]))

    # [7] 부정 톤 — epcheck ABSENCE 재사용 (§5.8-1 «없음을 보고하지 않는다»).
    ab = ABSENCE.findall(body)
    r.ok("[7] 부정 톤 0건", not ab, str(ab[:5]))

    # [8] «공식 발표 수치» 라벨 — 신설 1건 (JJ 지시). 벤치 값을 실은 포스트가 라벨을 다는가.
    bench = getattr(facts, "BENCH", None)
    if not bench:
        r.na("[8] «%s» 라벨" % OFFICIAL_LABEL, "이 편에 BENCH 선언이 없다 — 검사 대상 아님")
    else:
        vals = set()
        for v in bench.values():
            vals |= set(v) if isinstance(v, (tuple, list)) else {v}
        miss = []
        for i, p in enumerate(posts, 1):
            toks = cardcheck.kit_numerals(_strip_urls(p))
            if (toks & {x.replace(",", "") for x in vals}) and OFFICIAL_LABEL not in p:
                miss.append("P%d" % i)
        r.ok("[8] 벤치 수치를 실은 포스트에 «%s» 라벨" % OFFICIAL_LABEL, not miss, " / ".join(miss))

    # [9] 캡션 복붙 아님 — 신설 1건 (JJ 지시 «인스타 캡션 복붙 금지»).
    if not caption:
        r.na("[9] 캡션 복붙 아님", "캡션을 못 읽었다")
    else:
        # 라벨은 [8] 이 **강제하는** 고정 문구다. 캡션에도 있다고 복붙으로 세면 두 검사가
        # 동시에 만족될 수 없다 — 판정에서 뺀다 (정관 §0 «검사가 틀린 것을 요구하면 검사부터 고친다»).
        cap_h, body_h = _hangul(caption.replace(OFFICIAL_LABEL, " ")), _hangul(body)
        runs, i = [], 0
        while i <= len(cap_h) - CAPTION_SHINGLE:
            if cap_h[i:i + CAPTION_SHINGLE] in body_h:
                j = i + CAPTION_SHINGLE                  # 겹치는 구간은 하나로 이어 붙여 보고한다
                while j < len(cap_h) and cap_h[i:j + 1] in body_h:
                    j += 1
                runs.append(cap_h[i:j])
                i = j
            else:
                i += 1
        r.ok("[9] 캡션과 한글 %d자 연속 일치 0건" % CAPTION_SHINGLE, not runs,
             " / ".join("«%s»" % x for x in runs[:6]))

    # [12] 발표 행위 서술 (v3.60 · 지시서 1-6) — 포스트 층. 카드 층은 epcheck [1-6].
    #      규격 사본을 두지 않는다: 문형·주체·전언 어미를 라이브 epcheck 에서 뽑아 쓴다.
    _av = _parse_ver(ep.get("SKILL_VER")) if ep else None
    if ep is None or _av is None:
        r.na("[12] 발표 행위 서술", "편 선언(SKILL_VER)을 못 읽었다")
    elif _av < ATTRIB_SINCE:
        r.na("[12] 발표 행위 서술",
             "편 규격 v%d.%d — 신설 v%d.%d 이전이라 대상 아님" % (_av + ATTRIB_SINCE))
    else:
        AV = skill_regex("ATTRIB_VERB")
        AS_ = skill_regex("ATTRIB_SUBJ")
        HT = skill_regex("HEARSAY_TAIL")
        _nouns = [n for n in (ep.get("COVER_NOUNS") or []) if n]
        def _has_subj(t):
            return bool(AS_.search(t)) or any(n in t for n in _nouns)
        _hit = []
        for i, p in enumerate(posts, 1):
            for j, sn in enumerate(sentences(p), 1):
                t = sn.strip()
                if not _tone_target(t):
                    continue          # URL·해시태그·크레딧 줄·영문 인용은 우리 산문이 아니다
                if AV.search(t) and _has_subj(t) and not HT.search(t):
                    _hit.append("P%d-%d «%s»" % (i, j, t[:26]))
        r.ok("[12] 발표 행위 서술 %d회 이하 (전언 어미·인용·크레딧 줄 제외)" % ATTRIB_MAX,
             len(_hit) <= ATTRIB_MAX, " / ".join(_hit) or "0회")

    # [11] «공식» 빈도 (v3.56) — 편 합산. 예외 선언 카드는 뺀다.
    #
    # 예외를 **편 선언의 명시 필드**로 둔 이유: 검사 쪽에 카드 번호를 적으면 그 줄이
    # 편마다 늘어나 검사 본문이 편을 알게 된다(epcheck 의 «검사 본문에 편 이름이 들어가면
    # 그것은 선언이어야 한다» 와 같은 규칙). 편이 자기 사유와 함께 적는다:
    #     OFFICIAL_WORD_EXEMPT = ("03",)   # 검증 경계 소재 — 귀속을 카드마다 밝혀야 한다
    _ver = _parse_ver(ep.get("SKILL_VER")) if ep else None
    if ep is None or _ver is None:
        r.na("[11] «%s» 빈도" % OFFICIAL_WORD, "편 선언(SKILL_VER)을 못 읽었다")
    elif _ver < OFFICIAL_WORD_SINCE:
        r.na("[11] «%s» 빈도" % OFFICIAL_WORD,
             "편 규격 v%d.%d — 신설 v%d.%d 이전이라 대상 아님"
             % (_ver + OFFICIAL_WORD_SINCE))
    else:
        _ex = {str(x) for x in (ep.get("OFFICIAL_WORD_EXEMPT") or ())}
        _card_t = [t for _no, _c in (ep.get("CARDS") or {}).items() if str(_no) not in _ex
                   for t in [_c.get("headline", ""), _c.get("key", "")] + list(_c.get("body") or [])]
        _n_card = sum(t.count(OFFICIAL_WORD) for t in _card_t)
        _n_post = sum(p.count(OFFICIAL_WORD) for p in posts)
        # 🔴 **재는 것은 «원고 몫» 이다 (2026-09-10 개정 · ep55 실측).**
        #
        # 종전에는 `카드 + 원고 <= 2` 를 그대로 쟀는데, **카드는 이 워커가 못 고친다** —
        # 인스타로 이미 나간 면이고 편 폴더는 `01_발행완료` 라 §2 예외 밖이다. ep55 는 카드
        # 셋이 「공식 화면은 …」 을 쓰고 원고는 **0회**인데, 그 상태로 «합계 3회» FAIL 이
        # 났다. **원고를 어떻게 고쳐 써도 통과할 수 있는 조합이 없다** — ep28·ep39·`[10-8]`·
        # `[10-0]` 과 같은 꼴이고, 정관 §0 «검사가 틀린 것을 요구하고 있으면 산출물보다
        # 검사부터 고친다» 자리다.
        #
        # 그래서 상한을 **남은 몫**으로 건다: `원고 <= max(0, 상한 - 카드)`.
        #   · 카드가 상한 안이면 **종전과 값이 같다** (`카드+원고 <= 상한` 과 동치).
        #   · 카드가 이미 상한을 넘었으면 **원고는 0이어야 한다** — 유통이 상태를 더
        #     나쁘게 만드는 것만 막는다. 못 고치는 것을 못 고쳤다고 FAIL 내지 않는다.
        # 즉 «원고 1 + 카드 3» 은 종전대로 걸리고, «원고 0 + 카드 3» 만 열렸다.
        #
        # 🔴 **못 잡는 것 (§0 4층 ④).** 카드 쪽 초과는 이 게이트가 **못 고친다** — 그것을
        # 잡을 자리는 **편 제작 게이트**(`epcheck`)이고, 그쪽은 자회사 정본이라 본사가
        # 수정하지 않는다(§1.5). 그래서 **지우지 않고 상세에 실어 출력에 남긴다** — 빼면
        # 게이트가 «편 합산을 본다» 는 척을 하게 된다.
        _room = max(0, OFFICIAL_WORD_MAX - _n_card)
        _over = "" if _n_card <= OFFICIAL_WORD_MAX else (
            " · 🔴 카드가 이미 상한 초과 — 발행된 면이라 유통이 못 고친다(편 제작 게이트 자리)")
        r.ok("[11] «%s» 원고 몫 %d회 이하 (상한 %d − 카드 %d · 예외 %d장 제외)"
             % (OFFICIAL_WORD, _room, OFFICIAL_WORD_MAX, _n_card, len(_ex)),
             _n_post <= _room,
             "원고 %d회 (허용 %d) · 카드 %d회%s" % (_n_post, _room, _n_card, _over))
        if _n_card > OFFICIAL_WORD_MAX:
            r.na("[11-c] 카드 쪽 «%s» 초과" % OFFICIAL_WORD,
                 "카드 %d회 (상한 %d) — 이미 발행돼 못 고친다. 잡을 자리는 편 제작 게이트다"
                 % (_n_card, OFFICIAL_WORD_MAX))

    if ep is not None:
        check_media(media or [], posts, facts, ep, r)
    return r


# ── 편 로딩 ─────────────────────────────────────────────────────────────
def load_cardcheck():
    d = skill_dir()
    if d not in sys.path:
        sys.path.insert(0, d)
    import cardcheck
    return cardcheck


def load_facts(ep_dir):
    import importlib.util
    p = os.path.join(ep_dir, "_facts.py")
    if not os.path.exists(p):
        raise RuntimeError("편 FACTS 가 없다: %s — 소스 맵을 만들 수 없다(설계 FAIL CONDITION)" % p)
    spec = importlib.util.spec_from_file_location("_dist_facts", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: 회귀 검사가 «통과했던 것» 을 알아보는 자리. 사이드카가 곧 그 증적이다.
_SIDECAR_SUFFIX = ".md.meta.json"


def regress(corpus_dirs, verbose=True):
    """🔴 **이미 통과한 편들이 지금도 통과하는가** (2026-09-10 신설 · JJ 지시 «다신 일어나지 않도록»).

    **무엇을 막는가.** 2026-09-10 하루에 «검사가 못 고치는 것을 요구» 가 **네 번** 났다 —
    `[10-8]`(로컬 대조 · 통과 조합 0) · `[10-0]`(P1 공식 미디어 · ep50·ep54 통과 불가) ·
    `[10-3]`(출처키 · 같은 두 편) · `[11]`(«공식» 편 합산 · ep55 통과 불가). 그중 둘은 **그날
    내가 넣은 축**이다. 한 뿌리다 — **새 축을 넣을 때 «지금 있는 산출물이 그것을 충족할 수
    있는가» 를 재는 절차가 없었다.** 넷 다 «사람이 다음 편을 돌려 보다가» 발견됐다.

    **어떻게 재는가.** `pack()` 은 게이트 FAIL 이 하나라도 있으면 **아무것도 쓰지 않는다** —
    그래서 **사이드카의 존재 + `gate_failed 0` 이 곧 «그때 통과했다» 는 증적**이다. 그 원고를
    지금 게이트로 다시 돌려 FAIL 이 나면 **산출물이 아니라 검사가 바뀐 것**이고, 그것이 회귀다.

    🔴 **원고가 그 뒤에 바뀐 편은 판정하지 않는다.** 사이드카의 `body_sha256` 과 지금 원고
    해시가 다르면 «검사가 바뀐 탓» 인지 «원고가 바뀐 탓» 인지 **가를 수 없다**. 모르는 것을
    통과로도 회귀로도 적지 않고 `SKIP` 으로 세어 출력에 남긴다(§0 4층 ④).

    🔴 **코퍼스가 0건이면 FAIL 이다.** 잴 것이 없는데 `OK` 를 내면 이 장치는 **있는데 안 도는
    검사**가 된다 — 그 상태가 정확히 이 조항이 막으려는 것이다(§0 «감지 장치가 값을 담는지»).

    반환 (회귀 건수, 검사한 편 수, 건너뛴 편 수).
    """
    import hashlib
    import dist_transform
    seen, n_ok, n_skip, regressions = set(), 0, 0, []
    for d in corpus_dirs:
        if not d or not os.path.isdir(d):
            continue
        # 🔴 **최신 사이드카가 이긴다** — 이름이 날짜로 시작하므로 내림차순이 곧 최신순이다.
        #    같은 원고를 두 번 팩하면 사이드카가 둘 남는데(재팩), 오름차순이면 **옛 사이드카가
        #    새것을 가려** 기준선이 영영 안 선다(ep49 실측: 09-10 판이 09-11 판을 덮었다).
        for name in sorted(os.listdir(d), reverse=True):
            if not name.endswith(_SIDECAR_SUFFIX):
                continue
            try:
                side = _json.loads(io.open(os.path.join(d, name), encoding="utf-8").read())
            except Exception as e:
                n_skip += 1
                if verbose:
                    print("[ SKIP ] %s — 사이드카를 못 읽었다 (%s)" % (name, str(e)[:40]))
                continue
            # 🔴 원고 이름을 사이드카 이름에서 **유추하지 않는다.** 재팩하면 팩 파일에는 그날
            #    날짜가 붙고 원고는 처음 쓴 날짜를 그대로 두므로 둘이 갈린다(ep49 실측:
            #    사이드카 `2026-09-11_…`, 원고 `2026-09-10_…`). 사이드카가 이름을 싣는다.
            draft = os.path.join(d, side.get("draft_path")
                                 or (name[:-len(_SIDECAR_SUFFIX)] + ".draft.md"))
            if not os.path.exists(draft):
                continue
            key = os.path.basename(draft)
            if key in seen:          # 작업장과 운영 서버에 같은 편이 있으면 한 번만 잰다
                continue
            seen.add(key)
            if side.get("gate_failed") != 0:
                n_skip += 1        # 그때도 통과하지 않은 편 — 기준선이 아니다
                continue
            base = side.get("draft_sha256")
            if not base:
                # 2026-09-10 이전 사이드카 — 기준선 필드가 없다. **없는 것을 통과로 세지 않는다.**
                n_skip += 1
                if verbose:
                    print("[ SKIP ] %s — 옛 사이드카에 draft_sha256 이 없다 (재팩하면 기준선이 선다)"
                          % key)
                continue
            body = io.open(draft, "rb").read()
            if hashlib.sha256(body).hexdigest() != base:
                n_skip += 1
                if verbose:
                    print("[ SKIP ] %s — 원고가 팩 이후 바뀌었다 (검사 탓인지 원고 탓인지 못 가른다)"
                          % key)
                continue
            m = re.search(r"_dist_ep(\d+)\.draft\.md$", key)
            if not m:
                n_skip += 1
                continue
            try:
                ep = dist_transform.load_ep(dist_transform.find_ep_dir(int(m.group(1))))
                posts, rows, media = parse_draft(body.decode("utf-8"))
                r = check(posts, rows, ep["facts"], ep["kit_url"], ep["caption"],
                          load_cardcheck(), media=media, ep=ep)
            except Exception as e:
                n_skip += 1
                if verbose:
                    print("[ SKIP ] %s — 편을 못 읽었다 (%s)" % (key, str(e)[:60]))
                continue
            if r.failed:
                regressions.append((key, [i[0] for i in r.failed]))
                if verbose:
                    print("[ 회귀 ] %s — 통과했던 원고가 지금 FAIL: %s"
                          % (key, ", ".join(i[0] for i in r.failed)))
            else:
                n_ok += 1
                if verbose:
                    print("[  OK  ] %s" % key)
    return len(regressions), n_ok, n_skip


def regress_cli(corpus_dirs):
    n_reg, n_ok, n_skip = regress(corpus_dirs)
    if n_ok == 0 and n_reg == 0:
        # 🔴 잴 것이 0건인데 OK 를 내면 «있는데 안 도는 검사» 가 된다 (§0).
        print("STATUS: FAIL 회귀 코퍼스가 0건이다 — 잴 것이 없다 (건너뜀 %d) · 찾은 자리: %s"
              % (n_skip, ", ".join(corpus_dirs) or "(없음)"))
        return 1
    print("STATUS: %s — 기준선 %d편 · 건너뜀 %d편"
          % ("OK" if not n_reg else "FAIL 회귀 %d편" % n_reg, n_ok, n_skip))
    return 0 if not n_reg else 1


def run_cli(argv=None):
    ap = argparse.ArgumentParser(description="유통 변환 게이트 (Threads 텍스트 스레드)")
    ap.add_argument("--ep", type=int)
    ap.add_argument("--ep-dir")
    ap.add_argument("--draft")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--regress", action="store_true",
                    help="이미 통과한 편들이 지금도 통과하는지 (게이트를 고쳤을 때 돌린다)")
    ap.add_argument("--corpus", action="append", default=[],
                    help="회귀 기준선이 있는 reports 폴더. 여러 번 줄 수 있다")
    a = ap.parse_args(argv)
    if a.regress:
        return regress_cli(a.corpus or [os.path.join(os.getcwd(), "reports")])
    if a.selftest:
        return selftest()
        return selftest()
    if not a.draft:
        ap.error("--draft 가 필요하다 (또는 --selftest)")
    import dist_transform
    ep_dir = a.ep_dir or dist_transform.find_ep_dir(a.ep)
    ep = dist_transform.load_ep(ep_dir)
    posts, rows, media = parse_draft(io.open(a.draft, encoding="utf-8").read())
    r = check(posts, rows, ep["facts"], ep["kit_url"], ep["caption"], load_cardcheck(),
              media=media, ep=ep)
    print("유통 변환 게이트 — ep%s · 초안 %s" % (ep["EP"], os.path.basename(a.draft)))
    print("규격 출처: 라이브 스킬 %s (%s)" % (skill_revision(), skill_dir()))
    report(r)
    return 0 if not r.failed else 1


def report(r):
    for label, verdict, detail in r.items:
        mark = {"OK": "  OK  ", "FAIL": " FAIL ", "NA": "  --  "}[verdict]
        print("[%s] %s%s" % (mark, label, ("  — " + detail) if detail else ""))
    n_fail = len(r.failed)
    print("STATUS: %s" % ("OK" if not n_fail else "FAIL %d건" % n_fail))


# ── 역검증 ──────────────────────────────────────────────────────────────
# 정관 §0 — 케이스마다 «그 검사만» 걸려야 한다. 다른 검사가 같이 걸리면
# 그 검사가 없었어도 잡혔을 입력이라 새 검사의 값어치가 증명되지 않는다.
_BASE_POSTS = [
    "큐원이 새 모델을 열었어요.\n본체는 125B 예요.",
    "점수는 공식 발표 수치예요.\n코딩 점수는 62.5 이고 전작은 55.8 이에요.",
    "표는 아래 한 장에 묶어 뒀어요.\nhttps://example.invalid/kits/demo-kit.html",
]
_BASE_ROWS = [(1, 1, "-"), (1, 2, "PARAMS_MAIN"),
              (2, 1, "-"), (2, 2, "BENCH"),
              (3, 1, "-"), (3, 2, "KIT_URL")]
#: 라벨 «공식 발표 수치» 를 일부러 넣어 뒀다 — [8] 이 강제하는 문구가 [9] 에 걸리면
#: 두 검사를 동시에 만족시킬 수 없다. 기준 초안이 통과하는 것으로 그 자리를 지킨다.
_BASE_CAPTION = "지난 화요일 저녁에 알려 드린 소식입니다. 점수는 공식 발표 수치입니다."
_BASE_KIT = "https://example.invalid/kits/demo-kit.html"


class _Facts(object):
    NOISE = {"2026"}
    BENCH = {"코딩": ("62.5", "55.8")}
    PARAMS_MAIN = "125"
    #: 어휘에는 «20» 으로만 있고 산문 표기는 «2천만» 인 값 — [1] 보조 어휘의 역검증 대상.
    LICENSE_REV = "2천만 달러"

    def numeral_vocab(self):
        return {"125", "62.5", "55.8", "20"}


def _mutate(fn):
    posts = list(_BASE_POSTS)
    rows = list(_BASE_ROWS)
    cap = _BASE_CAPTION
    posts, rows, cap = fn(posts, rows, cap)
    return check(posts, rows, _Facts(), _BASE_KIT, cap, load_cardcheck())   # 미디어 없는 기준선


def _m_facts(p, r, c):
    p[0] = p[0].replace("125B", "999B")
    return p, r, c


def _m_haeyo(p, r, c):
    p[0] = p[0].replace("큐원이 새 모델을 열었어요.", "큐원이 새 모델을 열었습니다.")
    return p, r, c


def _m_count(p, r, c):
    extra = "표지는 어제 걸어 뒀어요."
    p = [p[0], p[1], extra, extra, extra, p[2]]     # 킷 포스트 앞에 끼운다 — [4] 를 건드리지 않게
    r = [(1, 1, "-"), (1, 2, "PARAMS_MAIN"), (2, 1, "-"), (2, 2, "BENCH"),
         (3, 1, "-"), (4, 1, "-"), (5, 1, "-"), (6, 1, "-"), (6, 2, "KIT_URL")]
    return p, r, c


def _m_length(p, r, c):
    p[0] = p[0].replace("큐원이 새 모델을 열었어요.", "큐원이 " + "아주 " * 170 + "새 모델을 열었어요.")
    return p, r, c


def _m_url(p, r, c):
    p[2] = p[2].replace(_BASE_KIT, "https://example.invalid/kits/wrong-kit.html")
    return p, r, c


def _m_urlearly(p, r, c):
    p[0] = p[0] + "\n" + _BASE_KIT
    return p, r + [(1, 3, "KIT_URL")], c


def _m_nofact(p, r, c):
    return p, [(1, 2, "-") if x == (1, 2, "PARAMS_MAIN") else x for x in r], c


def _m_srcmap(p, r, c):
    return p, [x for x in r if x != (1, 2, "PARAMS_MAIN")], c


def _m_key(p, r, c):
    return p, [(1, 2, "PARAMS_NOPE") if x == (1, 2, "PARAMS_MAIN") else x for x in r], c


def _m_selfref(p, r, c):
    p[0] = p[0].replace("큐원이 새 모델을 열었어요.", "큐원이 새 모델을 열었는지 확인했어요.")
    return p, r, c


def _m_absence(p, r, c):
    p[0] = p[0].replace("큐원이 새 모델을 열었어요.", "큐원 말고는 새 모델이 없어요.")
    return p, r, c


def _m_label2(p, r, c):
    p[1] = "코딩 점수는 62.5 이고 전작은 55.8 이에요."
    return p, [(2, 1, "BENCH") if x[0] == 2 and x[1] == 2 else x for x in r if not (x[0] == 2 and x[1] == 1)], c


def _m_caption(p, r, c):
    c = "큐원이 새 모델을 열었어요 라고 어제 캡션에 적어 두었습니다."
    return p, r, c


_CASES = [
    ("[1]", "수치를 어휘 밖 값으로 바꾼다", _m_facts),
    ("[2]", "한 문장을 합쇼체로 바꾼다", _m_haeyo),
    ("[3-1]", "포스트를 6개로 늘린다", _m_count),
    ("[3-2]", "한 포스트를 500자 넘게 늘린다", _m_length),
    ("[4-1]", "킷 URL 을 첫 포스트에도 넣는다", _m_urlearly),
    ("[4-2]", "마지막 URL 을 다른 주소로 바꾼다", _m_url),
    ("[5-1]", "소스 맵 행 하나를 지운다", _m_srcmap),
    ("[5-2]", "없는 FACTS 키를 적는다", _m_key),
    ("[5-3]", "수치가 든 문장을 무주장(-)으로 적는다", _m_nofact),
    ("[6]", "«확인했» 을 심는다", _m_selfref),
    ("[7]", "«없어요» 를 심는다", _m_absence),
    ("[8]", "벤치 포스트에서 라벨 문장을 뺀다", _m_label2),
    ("[9]", "캡션 문장을 그대로 옮긴다", _m_caption),
]


def _quote_tone_selftest():
    """`[2]` 무한글 줄 제외 — 넣는 쪽과 빼는 쪽을 **따로** 본다 (정관 §0 역검증).

    ⓐ 영문 인용 줄은 어미 검사를 **안 받는다** (그래야 5-1 개정 원고가 통과한다)
    ⓑ 한글이 섞인 줄은 **계속 받는다** (검사가 통째로 죽지 않았다)
    """
    cases = [
        ('"You approve every spend request, and Grok Bot receives a card."', "", "영문 인용"),
        ("https://example.invalid/kit", "", "URL"),
        ("#ai #토망치랩", "", "해시태그"),
        ("영상 출처: X / @bot", "", "크레딧 줄"),
        ("지출 요청마다 사람이 승인해야 넘어가요.", "지출 요청마다 사람이 승인해야 넘어가요.",
         "한국어 산문"),
        ("Link 를 연결하면 돼요.", "Link 를 연결하면 돼요.", "영문 낱말이 섞인 산문"),
    ]
    bad = 0
    for src, want, why in cases:
        got = _tone_target(src)
        okc = (got == want) if want else (got == "")
        bad += 0 if okc else 1
        print("[%s] [2] 무한글 제외 — %s%s"
              % ("  OK  " if okc else " FAIL ", why,
                 "" if okc else "  기대 %r 실제 %r" % (want, got)))
    return bad


# ── 역검증: 첨부 미디어 ─────────────────────────────────────────────────
# 별도 기준선을 쓴다 — 미디어 검사는 편 폴더 실물을 읽으므로 합성 폴더를 만들어 붙인다.
_MEDIA_POSTS = [_BASE_POSTS[0] + "\n이미지 출처: Qwen"] + _BASE_POSTS[1:]
_MEDIA_ROWS = _BASE_ROWS + [(1, 3, "BLOG")]
_MEDIA_BASE = [{"post": 1, "path": "shots/demo.png", "src_key": "BLOG", "credit": "Qwen",
                "tier": "공식", "shape": "이미지 20x10"}]


class _MediaFacts(_Facts):
    BLOG = "https://example.invalid/blog"
    TPV = "https://example.invalid/thirdparty-demo"


def _media_ep(tmp, **kw):
    ep = {"dir": tmp, "OFFICIAL_VIDEO": None,
          "verify_log": "출처 " + _MediaFacts.TPV + " 를 확인했다",
          "pack": THIRDPARTY_SECTION + "\nJJ 육안 확인함"}
    ep.update(kw)
    return ep


def _media_selftest(cc):
    import shutil
    import tempfile
    from PIL import Image
    tmp = tempfile.mkdtemp(prefix="distcheck_")
    bad = 0
    try:
        os.makedirs(os.path.join(tmp, "shots"))
        Image.new("RGB", (20, 10), (200, 200, 200)).save(os.path.join(tmp, "shots", "demo.png"))
        Image.new("RGB", (20, 10), (200, 200, 200)).save(os.path.join(tmp, "02_banner.png"))

        def run(media, posts=None, rows=None, **epkw):
            return check(posts or _MEDIA_POSTS, rows or _MEDIA_ROWS, _MediaFacts(), _BASE_KIT,
                         _BASE_CAPTION, cc, media=media, ep=_media_ep(tmp, **epkw))

        base = run(_MEDIA_BASE)
        if base.failed:
            bad += 1
            print("[ FAIL ] 미디어 기준선이 전부 통과해야 한다 — %s" % [i[0] for i in base.failed])
        else:
            print("[  OK  ] 미디어 기준선 전 항목 통과 (검사 %d건)" % len(base.items))
        base_fail = base.labels_failed()

        def one(m, **kw):
            return dict(_MEDIA_BASE[0], **m), kw

        cases = [
            ("[10-1]", "shots/ 아래지만 없는 파일", {"path": "shots/nope.png"}, {}),
            ("[10-2]", "편 폴더 루트의 우리 카드를 붙인다", {"path": "02_banner.png"}, {}),
            ("[10-3]", "FACTS 에 없는 출처키", {"src_key": "NOPE"}, {}),
            ("[10-4]", "본문에 없는 크레딧을 적는다", {"credit": "누군가"}, {}),
            ("[10-5]", "해상도를 틀리게 적는다", {"shape": "이미지 99x99"}, {}),
            ("[10-6]", "공식 영상이 있는데 첨부는 이미지뿐", {}, {"OFFICIAL_VIDEO": {"url": "u", "dur": "9s"}}),
        ]
        for tag, why, mut, epkw in cases:
            got = run([dict(_MEDIA_BASE[0], **mut)], **epkw).labels_failed() - base_fail
            hit = any(g.startswith(tag) for g in got)
            extra = sorted(g for g in got if not g.startswith(tag))
            if hit and not extra:
                print("[  OK  ] %-8s %s → 그 검사만 걸린다" % (tag, why))
            else:
                bad += 1
                print("[ FAIL ] %-8s %s → 걸린 검사 %s" % (tag, why, sorted(got) or "없음"))

        # 서드파티 영상 4조건 — mp4 를 만들 수 없으니 «영상» 선언만으로 조건 발동을 본다.
        tpv = {"post": 1, "path": "shots/tp.mp4", "src_key": "TPV", "credit": "Qwen",
               "tier": "서드파티", "shape": "영상 20x10"}
        for tag, why, epkw in [("[10-7ⓒ]", "출처가 검증로그에 없다", {"verify_log": "관련 없는 내용"}),
                               ("[10-7ⓓ]", "발행팩에 승인 절이 없다", {"pack": "## 다른 절"})]:
            got = run([tpv], **epkw).labels_failed()
            ref = run([tpv]).labels_failed()
            diff = got - ref
            if diff == {tag}:
                print("[  OK  ] %-8s %s → 그 검사만 걸린다" % (tag, why))
            else:
                bad += 1
                print("[ FAIL ] %-8s %s → 걸린 검사 %s" % (tag, why, sorted(diff) or "없음"))
        # [10-0] 🔴 **P1 공식 미디어 필수** 의 역검증 — 세 면을 따로 본다 (2026-09-10 신설).
        #   `[10-1]`~`[10-6]` 케이스는 전부 «P1 에 공식 첨부가 있는» 기준선을 변형한 것이라
        #   **이 축이 없어도 그대로 통과한다** — 즉 위 목록만으로는 이 축이 실재하는지 모른다.
        #   ⓐ 첨부 0건이 걸린다 (닫힌 쪽) ⓑ P2 에만 있으면 걸린다 ⓒ 층위가 «공식» 이 아니면 걸린다.
        #   그리고 기준선(P1 공식 1건)이 통과하는 것은 위 `base` 가 이미 본다 — 열린 쪽이다.
        p1_cases = [
            ("첨부 0건", []),
            ("P2 에만 첨부", [dict(_MEDIA_BASE[0], post=2)]),
            ("P1 첨부가 서드파티", [dict(_MEDIA_BASE[0], tier="서드파티")]),
        ]
        for why, mm in p1_cases:
            got = run(mm).labels_failed()
            if any(g.startswith("[10-0]") for g in got):
                print("[  OK  ] [10-0]   %s → 걸린다" % why)
            else:
                bad += 1
                print("[ FAIL ] [10-0]   %s → 안 걸린다 (걸린 검사 %s)" % (why, sorted(got) or "없음"))

        # `VERIFY_LOG` 특례 (2026-09-10 신설) — **양방향으로 본다.** 한쪽만 보면 «파일 이름을
        #   안 보고 그냥 통과시키는» 상태와 구별되지 않는다(정관 §0 역검증).
        #   ⓐ 검증로그에 그 파일이 실려 있으면 통과 ⓑ 없으면 종전대로 `[10-3]` 이 걸린다.
        _vl = dict(_MEDIA_BASE[0], src_key="VERIFY_LOG")
        _vl_cases = [
            ("검증로그에 파일이 실려 있으면 통과", "판 03 | `demo.png` 1508x1102 | 공식 삽화", False),
            ("검증로그에 그 파일이 없으면 걸린다", "판 03 | `other.png` 1508x1102 | 공식 삽화", True),
        ]
        for why, vlog, want_fail in _vl_cases:
            got = run([_vl], verify_log=vlog).labels_failed() - base_fail
            hit = any(g.startswith("[10-3]") for g in got)
            if hit == want_fail and not [g for g in got if not g.startswith("[10-3]")]:
                print("[  OK  ] [10-3]   %s" % why)
            else:
                bad += 1
                print("[ FAIL ] [10-3]   %s → 걸린 검사 %s" % (why, sorted(got) or "없음"))

        # `[5-2]` 쪽 VERIFY_LOG 짝 — **양방향.** 소스 맵의 출처 줄 근거 키가 통과하려면
        #   그 키를 쓰는 첨부가 실재해야 한다. 첨부 없이 키만 적으면 걸린다.
        _vl_posts = [_MEDIA_POSTS[0]] + _MEDIA_POSTS[1:]
        _vl_rows = _BASE_ROWS + [(1, 3, "VERIFY_LOG")]
        _vlog = "판 03 | `demo.png` 1508x1102 | 공식 삽화"
        for why, mm, want_fail in [
                ("[5-2] 출처 줄 근거 — 그 첨부가 있으면 통과", [_vl], False),
                ("[5-2] 출처 줄 근거 — 첨부가 없으면 걸린다", [], True)]:
            got = run(mm, posts=_vl_posts, rows=_vl_rows, verify_log=_vlog).labels_failed()
            hit = "[5-2]" in got
            if hit == want_fail:
                print("[  OK  ] %s" % why)
            else:
                bad += 1
                print("[ FAIL ] %s → 걸린 검사 %s" % (why, sorted(got) or "없음"))

        # `shape_mismatch` — `[10-5]`(로컬)와 `[10-8]`(URL 바이트)이 쓰는 한 함수.
        #   양방향으로 본다: 맞으면 None, 축마다 하나씩 걸린다.
        _sm = [("맞는 선언은 통과", ("이미지 20x10", "이미지", 20, 10, None), None),
               ("갈래가 다르면 걸림", ("이미지 20x10", "영상", 20, 10, 3.0), "실물"),
               ("해상도가 다르면 걸림", ("이미지 20x10", "이미지", 99, 99, None), "해상도"),
               ("영상 길이가 다르면 걸림", ("영상 20x10 3s", "영상", 20, 10, 9.0), "길이")]
        for why, args, want in _sm:
            got = shape_mismatch(*args)
            okk = (got is None) if want is None else (got is not None and want in got)
            print("[%s] shape_mismatch — %s" % ("  OK  " if okk else " FAIL ", why))
            bad += not okk

        # ⓑ 는 기계가 못 잡는다 — «못 잡는다» 고 출력에 남는지를 본다(정관 §0 4층 ④).
        na = [i for i in run([tpv]).items if i[0].startswith("[10-7ⓑ]") and i[1] == "NA"]
        if na and "못 잡는다" in na[0][2]:
            print("[  OK  ] [10-7ⓑ] 육안 항목이 «못 잡는다» 로 출력에 남는다")
        else:
            bad += 1
            print("[ FAIL ] [10-7ⓑ] 육안 항목이 출력에 안 남는다 — 검사가 완전한 척한다")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad



def _regress_selftest():
    """`--regress` 자신의 역검증 — 🔴 **이 장치가 헛돌면 아무도 모른다.**

    회귀 검사는 «아무 일도 없음» 이 정상 출력이라 고장 나도 `STATUS: OK` 로 보인다.
    그래서 **일부러 회귀를 만들어 넣고 잡히는지** 본다(정관 §0 «감지 장치가 값을 담는지»).

    네 면 — ⓐ 통과하는 기준선은 OK ⓑ **통과했던 원고가 지금 FAIL 이면 회귀로 잡힌다**
    ⓒ 원고가 팩 이후 바뀌면 SKIP(모르는 것을 통과로도 회귀로도 세지 않는다) ⓓ 코퍼스 0건은 FAIL.
    """
    import hashlib
    import shutil
    import tempfile
    import dist_transform
    tmp = tempfile.mkdtemp(prefix="distregress_")
    bad = 0
    # 실물 편을 읽지 않는다 — 합성 코퍼스를 만들고 **게이트 호출을 갈아 끼워** 이 장치의
    # «판정 부분» 만 잰다. 실물을 쓰면 편 내용이 바뀔 때마다 이 역검증이 같이 흔들린다.
    _real_check = check
    _real_find, _real_load = dist_transform.find_ep_dir, dist_transform.load_ep
    _fail = {"on": False}

    class _R(object):
        @property
        def failed(self):
            return [("[가짜] 일부러 낸 FAIL", "FAIL", "")] if _fail["on"] else []

    try:
        draft = os.path.join(tmp, "2026-01-01_dist_ep99.draft.md")
        io.open(draft, "w", encoding="utf-8", newline="").write("## P1\n한 줄이에요.\n")
        side = os.path.join(tmp, "2026-01-01_dist_ep99" + _SIDECAR_SUFFIX)

        def write_side(sha):
            io.open(side, "w", encoding="utf-8", newline="").write(_json.dumps(
                {"gate_failed": 0, "draft_sha256": sha,
                 "draft_path": os.path.basename(draft)}, ensure_ascii=False))

        good = hashlib.sha256(io.open(draft, "rb").read()).hexdigest()
        globals()["check"] = lambda *a, **k: _R()
        dist_transform.find_ep_dir = lambda ep: tmp
        dist_transform.load_ep = lambda d: {"facts": None, "kit_url": "", "caption": "", "EP": "99"}

        write_side(good)
        for why, want_reg in [("ⓐ 통과하는 기준선은 OK", False),
                              ("ⓑ 통과했던 원고가 지금 FAIL → 회귀로 잡힌다", True)]:
            _fail["on"] = want_reg
            n_reg, n_ok, _ = regress([tmp], False)
            if (n_reg > 0) == want_reg and (want_reg or n_ok == 1):
                print("[  OK  ] --regress %s" % why)
            else:
                bad += 1
                print("[ FAIL ] --regress %s → 회귀 %d · 기준선 %d" % (why, n_reg, n_ok))

        _fail["on"] = False
        write_side("0" * 64)          # 기준선 해시를 어긋나게 둔다 = «원고가 바뀌었다»
        if regress([tmp], False) == (0, 0, 1):
            print("[  OK  ] --regress ⓒ 원고가 팩 이후 바뀌면 SKIP (통과로 세지 않는다)")
        else:
            bad += 1
            print("[ FAIL ] --regress ⓒ 바뀐 원고를 SKIP 으로 안 센다 — %s" % (regress([tmp], False),))

        empty = os.path.join(tmp, "비어있음")
        os.makedirs(empty)
        if regress_cli([empty]) == 1:
            print("[  OK  ] --regress ⓓ 코퍼스 0건은 FAIL (있는데 안 도는 검사 금지)")
        else:
            bad += 1
            print("[ FAIL ] --regress ⓓ 코퍼스 0건인데 통과했다 — 장치가 헛돈다")
    finally:
        globals()["check"] = _real_check
        dist_transform.find_ep_dir, dist_transform.load_ep = _real_find, _real_load
        shutil.rmtree(tmp, ignore_errors=True)
    return bad


def _officialword_selftest(cc):
    """`[11]` — «공식» 원고 몫. 🔴 **네 면을 다 본다** (2026-09-10 개정).

    카드가 상한 안일 때는 값이 종전(`카드+원고 <= 상한`)과 같아야 하고, 카드가 넘었을 때만
    «원고 0 이면 통과» 가 열린다. 한쪽만 보면 «카드를 아예 안 세는» 상태와 구별되지 않는다."""
    kit = "https://tomangchi-lab.github.io/kits/x.html"
    rows = [(1, 1, "-"), (1, 2, "-"), (2, 1, "-"), (2, 2, "KIT_URL")]

    def run(n_card, n_post):
        #: 카드 한 장에 «공식» 을 한 번씩 넣어 개수를 만든다.
        cards = {"%02d" % (i + 1): {"headline": "공식 화면은 이렇게 돼요.",
                                    "key": "", "body": []} for i in range(n_card)}
        tail = "".join("\n공식 문서에 그렇게 적혀 있어요." for _ in range(n_post))
        posts = ["새 기능이 열렸어요.\n버튼 하나로 켜져요." + tail,
                 "정리해 뒀어요.\n" + kit]
        ep = {"SKILL_VER": "v3.60", "CARDS": cards, "OFFICIAL_WORD_EXEMPT": (), "dir": "."}
        r = check(posts, rows, _Facts(), kit, _BASE_CAPTION, cc, ep=ep)
        return [i[0] for i in r.failed if i[0].startswith("[11]")], r

    bad = 0
    cases = [
        ("카드 1 · 원고 1 → 합계 2 로 통과 (종전과 같다)", 1, 1, False),
        ("카드 1 · 원고 2 → 합계 3 으로 걸린다 (종전과 같다)", 1, 2, True),
        ("🔴 카드 3 · 원고 0 → 통과한다 (카드는 발행돼 못 고친다)", 3, 0, False),
        ("🔴 카드 3 · 원고 1 → 걸린다 (유통이 더 나쁘게 만들었다)", 3, 1, True),
    ]
    for why, nc, np_, want_fail in cases:
        got, _r = run(nc, np_)
        if bool(got) == want_fail:
            print("[  OK  ] [11]     %s" % why)
        else:
            bad += 1
            print("[ FAIL ] [11]     %s → 걸린 검사 %s" % (why, got or "없음"))

    # 🔴 카드 초과가 **출력에 남는지** — 지우면 게이트가 «편 합산을 본다» 는 척을 한다(§0 4층 ④).
    _got, _r = run(3, 0)
    _na = [i for i in _r.items if i[0].startswith("[11-c]")]
    if _na and "못 고친다" in _na[0][2]:
        print("[  OK  ] [11-c]   카드 초과가 «못 고친다» 로 출력에 남는다")
    else:
        bad += 1
        print("[ FAIL ] [11-c]   카드 초과가 출력에 안 남는다 — 검사가 완전한 척한다")
    return bad


def _attrib_selftest():
    """`[12]` — 발표 행위 서술 상한. 넣는 쪽·빼는 쪽·예외를 각각 본다."""
    # `dir` 은 첨부 검사가 먼저 읽는다 — 첨부 0건이어도 키가 없으면 죽는다.
    ep = {"SKILL_VER": "v3.60", "CARDS": {}, "OFFICIAL_WORD_EXEMPT": (), "dir": ".",
          "COVER_NOUNS": ["xAI", "Grok Bot", "@bot"]}
    kit = "https://tomangchi-lab.github.io/kits/x.html"
    base = ["xAI 가 8월 28일에 봇 공유를 열었어요.\n링크를 만들어 보내면 돼요.",
            "받는 쪽 계정에 사본이 하나 생겨요.\n대화 이력은 안 따라가요.",
            "지출 요청마다 사람이 승인해야 넘어가요.\n" + kit]
    rows = [(1, 1, "-"), (1, 2, "-"), (2, 1, "-"), (2, 2, "-"), (3, 1, "-"), (3, 2, "KIT_URL")]
    cc = load_cardcheck()
    try:
        skill_regex("ATTRIB_VERB")
    except RuntimeError as e:
        # 스킬 v3.60 배포 전이다. **건너뛴 사실을 찍는다** — 조용히 0 을 돌려주면
        # 이 역검증은 «있는데 안 도는» 검사가 된다(L-011 이웃 · selftest-coverage 규칙 2).
        print("[  --  ] [12] 역검증 — 라이브 스킬에 ATTRIB_VERB 가 없다 "
              "(v3.60 배포 전). 배포 뒤 이 줄이 5건으로 바뀐다. %s" % str(e)[:40])
        return 0

    def hit(posts):
        r = check(posts, rows, _Facts(), kit, _BASE_CAPTION, cc, ep=ep)
        return [i[0] for i in r.failed if i[0].startswith("[12]")]

    cases = [
        ("리드 1회는 통과한다", base, False),
        ("두 번째 발표 행위 서술이 걸린다",
         [base[0], base[1] + "\n@bot 계정이 결제 기능을 올렸어요.", base[2]], True),
        ("전언 어미 문장은 안 센다 (1-5 도구)",
         [base[0], base[1] + "\n휴대폰은 곧 열린대요.", base[2]], False),
        ("주체 없는 화면 서술은 안 센다",
         [base[0], base[1] + "\n결제 직전이라고 화면에 적혀 있어요.", base[2]], False),
        ("영문 인용 줄은 안 센다",
         [base[0], base[1] + '\n"xAI posted that Grok Bot can now buy things."', base[2]], False),
    ]
    bad = 0
    for why, posts, want_fail in cases:
        got = bool(hit(posts))
        okc = got == want_fail
        bad += 0 if okc else 1
        print("[%s] [12] %s%s" % ("  OK  " if okc else " FAIL ", why,
                                  "" if okc else "  (기대 %s / 실제 %s)" % (want_fail, got)))
    return bad


def _nokit_selftest(cc):
    """킷 없는 편 규격 `[4-2b]` 의 역검증 — 세 면을 따로 본다 (2026-09-02 신설).

    ⓐ 원류 URL 일치 → 통과 (전부 막는 검사가 아니다)
    ⓑ 마지막 URL 이 발행로그 값과 다르면 걸린다
    ⓒ 정본(post_url)이 안 넘어오면 걸린다 — «모르면 통과» 가 아니다
    """
    pu = "https://www.instagram.com/p/TESTPOST123/"
    posts = [p.replace(_BASE_KIT, pu) for p in _BASE_POSTS]
    rows = [(a, b, "POST_URL" if k == "KIT_URL" else k) for a, b, k in _BASE_ROWS]
    wrong = [p.replace(pu, "https://www.instagram.com/p/WRONGPOST/") for p in posts]
    bad = 0
    for why, ps, ep, want_ok in [
            ("원류 URL 일치는 통과한다", posts, {"post_url": pu, "dir": "."}, True),
            ("마지막 URL 이 다르면 걸린다", wrong, {"post_url": pu, "dir": "."}, False),
            ("정본(post_url) 부재는 걸린다", posts, {"dir": "."}, False)]:
        r = check(ps, rows, _Facts(), None, _BASE_CAPTION, cc, ep=ep)
        got_ok = not any(i[0].startswith(("[4-2b]", "[5-2]")) for i in r.failed)
        if got_ok == want_ok:
            print("[  OK  ] [4-2b] 킷 없는 편 — %s" % why)
        else:
            bad += 1
            print("[ FAIL ] [4-2b] 킷 없는 편 — %s (실제 %s)" % (why, "통과" if got_ok else "걸림"))
    return bad


def _postsmin_selftest(cc):
    """`[3-1]` 하한 개정의 역검증 — 세 면을 따로 본다 (2026-09-10 신설).

    `_m_count` 는 «6개로 늘리면 그 검사만 걸린다» 를 보지만 그것만으로는
    **하한이 실제로 열렸는지** 를 모른다 — 하한을 안 고쳤어도 그 케이스는 통과한다.
    ⓐ 단일 포스트가 통과한다 (열린 쪽)  ⓑ 0개는 걸린다 (하한이 사라진 것이 아니다)
    ⓒ 6개는 걸린다 (상한은 살아 있다)
    """
    one = ["\n".join(_BASE_POSTS)]
    six = _BASE_POSTS + _BASE_POSTS[:3]
    bad = 0
    for why, ps, want_ok in [("단일 포스트는 통과한다", one, True),
                             ("포스트 0개는 걸린다", [], False),
                             ("포스트 6개는 걸린다", six, False)]:
        r = check(ps, _BASE_ROWS, _Facts(), _BASE_KIT, _BASE_CAPTION, cc)
        got_ok = not any(i[0].startswith("[3-1]") for i in r.failed)
        if got_ok == want_ok:
            print("[  OK  ] [3-1] 포스트 수 하한 — %s" % why)
        else:
            bad += 1
            print("[ FAIL ] [3-1] 포스트 수 하한 — %s (실제 %s)" % (why, "통과" if got_ok else "걸림"))
    return bad


def selftest():
    cc = load_cardcheck()
    quote_bad = _quote_tone_selftest()
    quote_bad += _attrib_selftest()
    print("유통 변환 게이트 역검증 — 규격 출처: 라이브 스킬 %s" % skill_revision())
    base = check(_BASE_POSTS, _BASE_ROWS, _Facts(), _BASE_KIT, _BASE_CAPTION, cc)
    bad = 0
    bad += quote_bad
    if base.failed:
        print("[ FAIL ] 기준 초안이 전부 통과해야 한다 — %s" % [i[0] for i in base.failed])
        bad += 1
    else:
        print("[  OK  ] 기준 초안은 전 항목 통과 (검사 %d건)" % len(base.items))
    base_fail = base.labels_failed()
    for tag, why, fn in _CASES:
        got = _mutate(fn).labels_failed() - base_fail
        hit = any(g.startswith(tag) for g in got)
        extra = sorted(g for g in got if not g.startswith(tag))
        if hit and not extra:
            print("[  OK  ] %-6s %s → 그 검사만 걸린다" % (tag, why))
        else:
            bad += 1
            print("[ FAIL ] %-6s %s → 걸린 검사 %s (기대 %s 단독)" % (tag, why, sorted(got) or "없음", tag))
    # [1] 보조 어휘의 역검증 — 선언된 값의 산문 표기는 통과하고, 선언 안 된 수는 여전히 걸려야 한다.
    #     한쪽만 보면 «전부 통과시키는 어휘»도 정상으로 보인다.
    for repl, want_ok, why in [("월매출 2천만 달러를 넘어요.", True, "선언된 «2천만 달러» 의 «2» 는 통과한다"),
                               ("월매출 7천만 달러를 넘어요.", False, "선언 안 된 «7» 은 걸린다")]:
        posts = [_BASE_POSTS[0].replace("본체는 125B 예요.", repl)] + _BASE_POSTS[1:]
        rows = [(1, 2, "LICENSE_REV") if x == (1, 2, "PARAMS_MAIN") else x for x in _BASE_ROWS]
        got = not any(i[0].startswith("[1]") for i in check(posts, rows, _Facts(), _BASE_KIT,
                                                           _BASE_CAPTION, cc).failed)
        if got == want_ok:
            print("[  OK  ] [1] 보조 어휘 — %s" % why)
        else:
            bad += 1
            print("[ FAIL ] [1] 보조 어휘 — %s (실제 %s)" % (why, "통과" if got else "걸림"))
    # 파서 자체의 역검증 — 소수점이 문장을 가르면 [5] 가 통째로 헛돈다.
    for txt, n, why in [("License 1.0 이라 조건이 붙어요.", 1, "소수점은 문장을 가르지 않는다"),
                        ("먼저예요. 다음이에요.", 2, "종결부호 뒤 공백은 가른다"),
                        ("한 줄이에요\n두 줄이에요", 2, "줄바꿈은 가른다")]:
        got = len(sentences(txt))
        if got == n:
            print("[  OK  ] 문장 분할 — %s" % why)
        else:
            bad += 1
            print("[ FAIL ] 문장 분할 — %s (%d개로 갈렸다)" % (why, got))
    bad += _regress_selftest()
    bad += _officialword_selftest(cc)
    bad += _media_selftest(cc)
    bad += _nokit_selftest(cc)
    bad += _postsmin_selftest(cc)
    # 규격 추출 자체의 역검증 — 못 찾으면 던져야 한다.
    try:
        skill_regex("__NOT_A_REAL_REGEX__")
        bad += 1
        print("[ FAIL ] 없는 규격 이름이 예외 없이 통과했다 — 조용한 실패")
    except RuntimeError:
        print("[  OK  ] 없는 규격 이름은 예외를 던진다")
    print("STATUS: %s" % ("OK" if not bad else "FAIL %d건" % bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(run_cli())
