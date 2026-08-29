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
#: 스레드 길이. JJ 지시 2026-08-27 «3~5개 포스트».
POSTS_MIN, POSTS_MAX = 3, 5

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
                          "credit": cells[3], "tier": cells[4], "shape": cells[5]})
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


def check_media(media, posts, facts, ep, r):
    """`[10-*]` 첨부 미디어 — 공식 원본만, 크레딧은 본문에, 우리 카드는 금지.

    설계 근거: SKILL §6 소스 실물 위계·크레딧 형식 · v3.30 공식 프로모 자산(크레딧 = 회사명) ·
    v3.55 §6 서드파티 자작 시연 영상 4조건 · v3.54 §7 공식 영상 우선."""
    ep_dir = ep["dir"]
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

        # [10-3] 출처가 편 FACTS 에 등록된 URL 인가
        bad_src = []
        for m in media:
            k = m["src_key"]
            v = getattr(facts, k, None) if k and not k.startswith("_") else None
            if not isinstance(v, str) or not URL_RE.match(v):
                bad_src.append("P%d %s" % (m["post"], k or "(빈칸)"))
        r.ok("[10-3] 출처키가 _facts.py 의 URL 로 실재", not bad_src, " / ".join(bad_src))

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
            if not m["shape"].startswith(kind):
                shape_bad.append("P%d 선언«%s» 실물«%s»" % (m["post"], m["shape"], kind))
                continue
            if w and ("%dx%d" % (w, h)) not in m["shape"].replace("×", "x"):
                shape_bad.append("P%d 해상도 선언«%s» 실물 %dx%d" % (m["post"], m["shape"], w, h))
            elif w is None:
                shape_na.append("P%d %s" % (m["post"], os.path.basename(p)))
            if kind == "영상" and dur is not None and ("%gs" % dur) not in m["shape"]:
                shape_bad.append("P%d 길이 선언«%s» 실측 %gs" % (m["post"], m["shape"], dur))
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
    vocab = set(facts.numeral_vocab()) | set(getattr(facts, "NOISE", set()))
    vocab |= cardcheck.kit_numerals(_strip_urls(declared_text(facts)))
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
    r.ok("[4-2] 마지막 포스트에 킷 URL 1건 · 편 선언과 일치",
         last_urls == [kit_url], "발견 %s / 선언 %s" % (last_urls, kit_url))

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
        r.ok("[11] «%s» 편 합산 %d회 이하 (원고+카드 · 예외 %d장 제외)"
             % (OFFICIAL_WORD, OFFICIAL_WORD_MAX, len(_ex)),
             _n_card + _n_post <= OFFICIAL_WORD_MAX,
             "합계 %d회 (원고 %d · 카드 %d)" % (_n_card + _n_post, _n_post, _n_card))

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


def run_cli(argv=None):
    ap = argparse.ArgumentParser(description="유통 변환 게이트 (Threads 텍스트 스레드)")
    ap.add_argument("--ep", type=int)
    ap.add_argument("--ep-dir")
    ap.add_argument("--draft")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
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


def selftest():
    cc = load_cardcheck()
    quote_bad = _quote_tone_selftest()
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
    bad += _media_selftest(cc)
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
