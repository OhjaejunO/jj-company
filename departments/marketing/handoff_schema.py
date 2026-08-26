# -*- coding: utf-8 -*-
"""스카우트 → 소재큐 인계 노드 계약 (본선 · 2026-08-25).

킷 체인 세션에서 검증된 패턴 그대로다 — **FACTS 의 `KIT_MUST` + 결정적 규칙 검증기**.
여기서는 «인계 레코드»가 FACTS 이고, 검증기는 필드 존재·형식·URL 만 본다. LLM 판정은 없다.

왜 필요한가 (실측 2026-08-25). `content-scout.md` 241~247 행이 이미 5필드 계약을 규정하지만
**기계 검증이 없어** 리포트마다 형식이 흔들린다 — 「## 제안 — N건」 헤더는 7회차 중 1회차만 있고,
받는 쪽 `인수인계_대기함.md` 는 「소재 / 확보된 것 / 비고」 3열이라 보내는 쪽 5필드와 맞물리지 않는다.
그 사이에서 값이 자유 텍스트 벽으로 뭉개진다. 대기함 #11~15 는 이미 정의에 없는 필드
(노출·형상·주체 공식 계정 여부·축 후보·편성 판단)를 쓰고 있다 — 스키마가 정의보다 앞서 진화했다.

레코드는 **한 소재 = 한 마크다운 블록**이고 `key: value` 줄로 적는다. 자유 텍스트 벽은 스키마 위반이다.
`#` 로 시작하는 줄은 주석이라 검사 대상이 아니다 — 편성 판단·축 후보 같은 사람 몫의 메모는 거기 둔다.

판정 3건 확정 (2026-08-25 본선 적용):
  ① 출처URL 은 **층위 조건부** — `출처층위: 공식` 이면 1건 이상, `X`·`서드파티` 면 **2건 이상**.
     공식 계정 원 포스트는 그 자체가 1차 소스라 교차 확인이 필요 없고, 반응 포스트·2차 요약은
     한 건으로는 사실의 근거가 못 된다(content-scout.md 243 행 «2개 이상»의 취지를 층위로 푼 것).
  ② 신선도마감은 **필수 유지**. 마감이 없는 소재는 열거값 `상시` 로 적는다 — 비워 두면 «안 본 것»과
     «봤는데 없음»이 구분되지 않는다.
  ③ 값을 모르면 `미기입` 이라고 쓴다 — 필수 필드의 `미기입` 은 «부재»로 판정되고 목록으로 보고된다.
     지어 넣지 않게 하려고 둔 자리이지 통과시키려고 둔 자리가 아니다.

이 파일이 정본이고 `content-scout.md` 의 제안 형식 조항은 이 파일을 **참조**한다.

사용:  py handoff_schema.py                 → 역검증 (자체 테스트)
       py handoff_schema.py <파일.md> [--today YYYY-MM-DD]
                                            → `---8<--- #id` 로 나뉜 블록을 전부 검사하고 미기입 목록을 낸다
"""
import re
import sys
from dataclasses import dataclass, field

# ── 필드 정의 ─────────────────────────────────────────────────────────────
#: (키, 필수, 형식 규칙 이름). 형식 규칙은 아래 RULES 에.
FIELDS = [
    ("소재",        True,  "nonempty"),       # 고유명사 포함 1줄
    ("출처URL",     True,  "url_list"),       # 형식만 본다. **개수는 층위 조건부** — validate() 의 MIN_URLS
    ("출처층위",    True,  "tier"),           # 공식 | X | 서드파티
    ("발견일",      True,  "date"),           # YYYY-MM-DD
    ("훅각도",      True,  "oneline"),        # 1줄, 40자 이내 권장 (형식 규칙은 줄바꿈 금지만)
    ("채널충돌",    True,  "conflict"),       # 없음 | 광고성 | 페이월 | IP | 개발자니치 (복수는 ·)
    ("신선도마감",  True,  "date_or_na"),     # YYYY-MM-DD | 상시  (마감 없음 = 상시. 비우지 않는다)
    ("공식영상",    True,  "video"),          # 무 | <URL> <길이> — 주체 공식 채널의 데모 영상. **수집 시점에 스카우트가 확인해 적는다**
                                             #   (2026-08-26 신설 · SKILL §7 «공식 영상 — 있으면 싣는다» · 게이트 [1-2]). 길이는 92s / 1m32s / 1:32.
                                             #   없으면 «무» — 비우면 «안 본 것»과 «봤는데 없음»이 안 갈린다(신선도마감과 같은 취지).
    ("밝힐처리",    False, "oneline"),        # 힉스필드 MCP 처럼 «제작 툴 관계» 등 독자에게 밝힐 것. 없으면 생략
    ("지표",        False, "oneline"),        # «N만 (YYYY-MM-DD 조회)» — 시점 없는 수치는 규칙 위반
    ("형상",        False, "oneline"),        # 영상 | 이미지 | 없음 확인
    ("메모",        False, "oneline"),        # 스키마 밖 자유 서술 **한 줄**. 검사는 «한 줄»만 본다 — 벽으로 새지 않게 하는 배출구.
                                             #   여러 줄 메모는 `#` 주석으로. (본트리판 체리픽 2026-08-25)
]
REQUIRED = [k for k, req, _ in FIELDS if req]
KNOWN = {k for k, _, _ in FIELDS}

TIERS = {"공식", "X", "서드파티"}
#: 층위별 출처URL 최소 건수 (판정 ①)
MIN_URLS = {"공식": 1, "X": 2, "서드파티": 2}
CONFLICTS = {"없음", "광고성", "페이월", "IP", "개발자니치"}
#: 값을 모를 때 쓰는 자리표시 (판정 ③). 필수 필드에 있으면 «부재»로 판정.
UNFILLED = "미기입"

_URL = re.compile(r"^https?://[^\s<>\"']+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_METRIC = re.compile(r"\(\s*\d{4}-\d{2}-\d{2}[^)]*\)")   # 지표엔 «(YYYY-MM-DD …)» 조회 시점
_VIDEO_LEN = re.compile(r"^(\d+s|\d+m\d{1,2}s|\d{1,2}:\d{2}(:\d{2})?)$")   # 92s · 1m32s · 1:32 · 1:01:05

RULES = {
    "nonempty":   lambda v: bool(v.strip()),
    "oneline":    lambda v: bool(v.strip()) and "\n" not in v,
    "url_list":   lambda v: len(v.split()) >= 1 and all(_URL.match(u) for u in v.split()),
    "tier":       lambda v: v.strip() in TIERS,
    "date":       lambda v: bool(_DATE.match(v.strip())),
    "date_or_na": lambda v: v.strip() == "상시" or bool(_DATE.match(v.strip())),
    "conflict":   lambda v: all(x.strip() in CONFLICTS for x in v.split("·")),
    # 공식영상 — «무» 이거나 «URL 길이» 두 토큰. URL 만 있고 길이가 없으면 위반(구간 컷 견적은 길이가 있어야 선다).
    "video":      lambda v: v.strip() == "무" or (len(v.split()) == 2 and bool(_URL.match(v.split()[0])) and bool(_VIDEO_LEN.match(v.split()[1]))),
}
#: 자유 텍스트 벽 판정 — `key: value` 가 아닌 연속 줄이 이 수 이상이면 위반
WALL_LINES = 3


@dataclass
class Verdict:
    ok: bool
    missing: list = field(default_factory=list)     # 필수 필드 부재 (미기입 포함)
    invalid: list = field(default_factory=list)     # (필드, 사유)
    unknown: list = field(default_factory=list)     # 스키마 밖 키
    wall: int = 0                                   # 자유 텍스트 벽 줄 수
    expired: str = ""                               # 신선도마감 경과 (check_file --today 에서만)

    def line(self):
        parts = []
        if self.missing:  parts.append("필수 부재 %s" % self.missing)
        if self.invalid:  parts.append("형식 위반 %s" % ["%s(%s)" % x for x in self.invalid])
        if self.unknown:  parts.append("스키마 밖 키 %s" % self.unknown)
        if self.wall:     parts.append("자유 텍스트 벽 %d줄" % self.wall)
        if self.expired:  parts.append("마감 경과 %s" % self.expired)
        if self.ok and not parts:
            return "🟢 통과"
        return ("🟡 " if self.ok else "🔴 ") + " · ".join(parts)


# ── 파서 ──────────────────────────────────────────────────────────────────
_KV = re.compile(r"^([^\s:：][^:：]{0,20})\s*[:：]\s*(.*)$")

def parse(block):
    """`key: value` 줄을 dict 로. 그 외 줄은 «벽»으로 센다. 같은 키가 여러 줄이면 공백으로 잇는다(URL 목록용)."""
    rec, wall, last = {}, 0, None
    for raw in block.strip().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            last = None; continue
        m = _KV.match(line)
        if m and m.group(1).strip() in KNOWN:
            k, v = m.group(1).strip(), m.group(2).strip()
            rec[k] = (rec[k] + " " + v) if k in rec else v
            last = k
        elif m:
            rec.setdefault("__unknown__", []).append(m.group(1).strip()); last = None
        elif last == "출처URL" and _URL.match(line):
            rec[last] += " " + line                       # URL 이어 적기 허용
        else:
            wall += 1; last = None
    return rec, wall


def validate(block):
    rec, wall = parse(block)
    v = Verdict(ok=True)
    v.unknown = rec.pop("__unknown__", [])
    # 판정 ③ — 필수 필드의 «미기입»·빈 값은 부재. 값은 지우지 않고 남겨 둔다(보고용).
    v.missing = [k for k in REQUIRED if k not in rec or rec[k].strip() in ("", UNFILLED)]
    for k, _, rule in FIELDS:
        if k in rec and k not in v.missing and rec[k].strip() != UNFILLED and not RULES[rule](rec[k]):
            v.invalid.append((k, rule))
    # 판정 ① — 층위별 최소 URL 건수. 층위가 유효할 때만 (층위 자체가 틀리면 tier 위반이 이미 잡는다)
    tier = rec.get("출처층위", "").strip()
    if tier in MIN_URLS and "출처URL" not in v.missing and ("출처URL", "url_list") not in v.invalid:
        n = len(rec["출처URL"].split())
        if n < MIN_URLS[tier]:
            v.invalid.append(("출처URL", "%s층위 %d건 필요, %d건" % (tier, MIN_URLS[tier], n)))
    if "지표" in rec and rec["지표"].strip() != UNFILLED and not _METRIC.search(rec["지표"]):
        v.invalid.append(("지표", "조회시점없음"))            # content-scout.md 58 행
    v.wall = wall if wall >= WALL_LINES else 0
    v.ok = not (v.missing or v.invalid or v.unknown or v.wall)
    return v, rec


# ── retry 래퍼 ────────────────────────────────────────────────────────────
MAX_RETRY = 2   # 최초 1회 + 재시도 2회 = 최대 3회. 넘으면 «인계 실패»로 사람에게 올린다.

def submit(block, revise=None, max_retry=MAX_RETRY, log=print):
    """검증 → 실패 시 위반 필드를 넘겨 `revise(block, verdict)` 로 고친 블록을 받아 재검증.

    `revise` 는 스카우트(에이전트)가 맡는 자리다. 여기서는 콜백이라 LLM 이든 사람이든 상관없다.
    상한을 넘기면 마지막 verdict 를 들고 `HandoffRejected` 를 낸다 — 조용히 통과시키지 않는다."""
    attempts = 0
    while True:
        v, rec = validate(block)
        attempts += 1
        log("  [handoff] 시도 %d/%d — %s" % (attempts, max_retry + 1, v.line()))
        if v.ok:
            return rec, attempts
        if revise is None or attempts > max_retry:
            raise HandoffRejected(v, attempts)
        block = revise(block, v)


class HandoffRejected(Exception):
    def __init__(self, verdict, attempts):
        self.verdict, self.attempts = verdict, attempts
        super().__init__("인계 거부 (%d회) — %s" % (attempts, verdict.line()))


# ── 파일 검사 (대기함·샘플) ───────────────────────────────────────────────
_SEP = re.compile(r"^---8<---\s*(\S+)\s*$", re.M)

def split_blocks(text):
    """`---8<--- #id` 구분자로 나눈 [(id, block)]. 첫 구분자 앞은 머리글이라 버린다.
    `---8<--- end` 는 종료 표시 — 그 뒤 다음 구분자까지의 산문은 블록이 아니다(없으면 뒤 산문이 «벽»으로 잡힌다)."""
    parts = _SEP.split(text)
    out = []
    for i in range(1, len(parts) - 1, 2):
        if parts[i].lower() != "end":
            out.append((parts[i], parts[i + 1]))
    return out


def check_file(path, today=None, log=print):
    """파일의 모든 블록을 검사해 (통과 수, 전체 수, 미기입 목록) 을 돌려준다.
    `today` 를 주면 신선도마감 경과를 🟡 로 표시한다 — 대기함 규칙 4(«아무도 안 본다»)를 기계가 보는 자리."""
    with open(path, encoding="utf-8") as f:
        blocks = split_blocks(f.read())
    if not blocks:
        raise SystemExit("구분자 `---8<--- #id` 가 없다 — 검사할 블록 0건 (조용히 통과시키지 않는다)")
    passed, unfilled = 0, []
    for bid, block in blocks:
        v, rec = validate(block)
        due = rec.get("신선도마감", "").strip()
        if today and _DATE.match(due) and due < today:
            v.expired = due
        log("  %-5s %s" % (bid, v.line()))
        passed += v.ok
        for k in v.missing:
            unfilled.append((bid, k))
    log("  — %d/%d 통과" % (passed, len(blocks)))
    if unfilled:
        log("  — 미기입(필수) %d건:" % len(unfilled))
        for bid, k in unfilled:
            log("      %s %s" % (bid, k))
    return passed, len(blocks), unfilled


def _selftest():
    # 역검증 — 검사기가 헛돌지 않는지. 각 케이스는 **한 검사만** 걸리게 분리한다(CLAUDE.md §0).
    GOOD = """소재: Claude 가 약물 결합체를 설계했다
출처URL: https://x.com/AnthropicAI/status/2089842387845804246
출처층위: 공식
발견일: 2026-08-24
훅각도: AI 가 코드 말고 약을 설계했다
채널충돌: 없음
신선도마감: 2026-09-07
공식영상: 무
지표: 노출 407.9만 (2026-08-24 조회)
형상: 영상"""
    BAD_URL = GOOD.replace("https://x.com/AnthropicAI/status/2089842387845804246", "x.com/AnthropicAI")
    BAD_TIER = GOOD.replace("출처층위: 공식", "출처층위: 공식계정")
    WALL = GOOD + "\n\n이 소재는 접점이 강하고\n수치가 논지이며\n저자가 한계를 같이 적었다\n그래서 좋다"
    UNF = GOOD.replace("신선도마감: 2026-09-07", "신선도마감: 미기입")      # 판정 ③
    NA = GOOD.replace("신선도마감: 2026-09-07", "신선도마감: 상시")          # 판정 ②
    # 판정 ① — URL 1건인 GOOD 을 층위만 바꿔 재판정. 공식이면 통과, X·서드파티면 URL 부족으로 리젝.
    X1 = GOOD.replace("출처층위: 공식", "출처층위: X")
    T1 = GOOD.replace("출처층위: 공식", "출처층위: 서드파티")
    X2 = X1.replace("출처층위: X", "출처층위: X\n출처URL: https://example.com/second-source")
    # 공식영상 (2026-08-26) — 각 케이스는 이 필드만 건드린다. VID_OK 는 URL+길이, VID_NOLEN 은 URL 만, VID_MISSING 은 줄 자체 부재.
    VID_OK = GOOD.replace("공식영상: 무", "공식영상: https://www.youtube.com/watch?v=abc123 1m32s")
    VID_NOLEN = GOOD.replace("공식영상: 무", "공식영상: https://www.youtube.com/watch?v=abc123")
    VID_MISSING = GOOD.replace("공식영상: 무\n", "")
    cases = (("GOOD", GOOD, True), ("BAD_URL", BAD_URL, False), ("BAD_TIER", BAD_TIER, False),
             ("WALL", WALL, False), ("UNFILLED", UNF, False), ("NA_상시", NA, True),
             ("X_1url", X1, False), ("3RD_1url", T1, False), ("X_2url", X2, True),
             ("VID_OK", VID_OK, True), ("VID_NOLEN", VID_NOLEN, False), ("VID_MISSING", VID_MISSING, False))
    fails = 0
    for name, b, expect in cases:
        v, _ = validate(b)
        hit = v.ok == expect
        fails += not hit
        print("  %-9s %s  %s" % (name, "OK" if hit else "🔴 역검증 실패", v.line()))
    # 실측 샘플 #11·#14 (공식·URL 1건) 를 층위별로 재판정
    import os
    sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_handoff_samples_20260825.md")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            blocks = dict(split_blocks(f.read()))
        print("  — 실측 샘플 층위 재판정 (#11·#14, URL 1건):")
        # 샘플은 공식영상 신설(2026-08-26) 이전 실측이라 그 줄이 없다 — 파일 값은 지어 넣지 않고 **검사 입력에만** «무» 를 덧붙여 층위 판정을 본다.
        _FX = "\n공식영상: 무"
        for bid in ("#11", "#14"):
            for tier in ("공식", "X", "서드파티"):
                v, _ = validate(blocks[bid].replace("출처층위: 공식", "출처층위: " + tier) + _FX)
                print("    %s %-6s %s" % (bid, tier, v.line()))
        # 규칙이 «개수»를 보는지 — X 층위에 URL 을 1건 더 붙이면 통과해야 한다 (본트리판 체리픽 2026-08-25).
        # 이 케이스가 없으면 «X 는 무조건 리젝»인 검사기도 위 재판정을 통과한다.
        two = blocks["#11"].replace("출처층위: 공식", "출처층위: X").replace(
            "status/2089842387845804246", "status/2089842387845804246 https://www.anthropic.com/news") + _FX
        v, _ = validate(two)
        ok2 = v.ok
        if not ok2:
            fails += 1
        print("    #11 X+URL2건 %s  %s" % ("OK" if ok2 else "🔴 역검증 실패", v.line()))
    print("  STATUS:", "FAIL 역검증 %d건" % fails if fails else "OK")
    return fails


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    today = None
    if "--today" in sys.argv:
        today = sys.argv[sys.argv.index("--today") + 1]
    if args:
        check_file(args[0], today=today)
    else:
        sys.exit(_selftest())
