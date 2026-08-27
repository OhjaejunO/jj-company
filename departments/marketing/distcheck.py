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

#: 벤치마크 수치를 실은 포스트가 달아야 하는 라벨 (JJ 지시 · 캡션·킷 관례 그대로).
#: 카드 게이트 `[5-4]` SELF_REF 는 «공식 발표» 를 금지하지만 **그건 카드 층 규칙**이고,
#: 캡션 층은 ep34 캡션 «점수는 공식 발표 수치입니다» 처럼 이 라벨을 쓴다. Threads 본문은 캡션 층이다.
OFFICIAL_LABEL = "공식 발표 수치"

#: 캡션 복붙 판정 — 한글만 남긴 뒤 이 길이의 연속 일치가 있으면 «다시 쓰지 않은 것»으로 본다.
#: 고유명사·숫자·영문은 어차피 같아야 하므로 판정에서 뺀다.
CAPTION_SHINGLE = 12

URL_RE = re.compile(r"https?://\S+")
_TAGLINE_RE = re.compile(r"^[#@][^\s]+(\s+[#@][^\s]+)*$")


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


def parse_draft(text):
    """`## P1` 블록들과 `## 소스 맵` 표를 읽는다. 반환 (posts, rows).

    posts = [본문 문자열, ...] · rows = [(포스트번호, 문장번호, 근거문자열), ...]"""
    posts, rows = [], []
    cur, buf, in_map = None, [], False
    for ln in (text or "").splitlines():
        m = re.match(r"^##\s*P(\d+)\s*$", ln.strip())
        if m:
            if cur is not None:
                posts.append("\n".join(buf).strip())
            cur, buf, in_map = int(m.group(1)), [], False
            continue
        if re.match(r"^##\s*소스\s*맵", ln.strip()):
            if cur is not None:
                posts.append("\n".join(buf).strip())
                cur, buf = None, []
            in_map = True
            continue
        if ln.strip().startswith("##"):        # 그 밖의 헤더는 블록을 닫는다
            if cur is not None:
                posts.append("\n".join(buf).strip())
                cur, buf = None, []
            in_map = False
            continue
        if in_map:
            if not ln.strip().startswith("|"):
                continue
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) < 3 or set(cells[0]) <= set("-: "):
                continue                        # 구분선
            pm = re.match(r"^[Pp](\d+)$", cells[0])
            if not pm:
                continue                        # 헤더 줄
            try:
                rows.append((int(pm.group(1)), int(cells[1]), cells[2]))
            except ValueError:
                rows.append((int(pm.group(1)), -1, cells[2]))
        elif cur is not None:
            buf.append(ln)
    if cur is not None:
        posts.append("\n".join(buf).strip())
    return posts, rows


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


def _tone_target(s):
    """어미 검사 대상 문자열. 검사에서 빼는 것 — URL 만 있는 줄 · 해시태그/멘션 줄 · 시그니처 이모지."""
    s = s.strip()
    if URL_RE.fullmatch(s) or _TAGLINE_RE.match(s):
        return ""
    s = URL_RE.sub(" ", s)
    s = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", s)
    return s.strip()


def check(posts, rows, facts, kit_url, caption, cardcheck):
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
    posts, rows = parse_draft(io.open(a.draft, encoding="utf-8").read())
    r = check(posts, rows, ep["facts"], ep["kit_url"], ep["caption"], load_cardcheck())
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
    return check(posts, rows, _Facts(), _BASE_KIT, cap, load_cardcheck())


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


def selftest():
    cc = load_cardcheck()
    print("유통 변환 게이트 역검증 — 규격 출처: 라이브 스킬 %s" % skill_revision())
    base = check(_BASE_POSTS, _BASE_ROWS, _Facts(), _BASE_KIT, _BASE_CAPTION, cc)
    bad = 0
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
