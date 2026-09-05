# -*- coding: utf-8 -*-
r"""blogcheck — 네이버 블로그 초안(reports\blog\<날짜>_<이름>.md) 게이트.

WHY (2026-09-05 · 네이버 벤치마크 리포트 §5-1 규격을 기계로)
  잘 되는 글의 꼴(요약 3문장 → Q. 소제목 → 표 → FAQ → 한마디 → 관련글 → 태그 5~15)과
  지는 글의 신호(자동 생성 문체 · 이미지 0~1 · 해시태그 30+ · 캡션 복붙 · 자기 서술)를
  발행 전에 잰다. 사람이 읽기 전에 기계가 먼저 거른다 (정관 §0 4층 ③).

USAGE
  py scripts\blogcheck.py <md> [--publish] [--caption <caption.txt>]
     기본은 draft 모드: 「[[JJ 한마디]]」 자리가 **비어 있어야** 통과 (기계가 채우면 FAIL).
     --publish: 자리가 **채워져 있어야** 통과 (사람이 2문장을 넣었는가).
     --caption: 인스타 캡션과 20자 이상 같은 문장이 있으면 FAIL (복붙 금지).
  py scripts\blogcheck.py --self-test      역검증 (통과본 1 + 걸려야 하는 입력 8)

OUTPUT  마지막 줄 STATUS: OK | STATUS: FAIL <n>건
LIMITS (정관 §0 4층 ④ — 못 잡는 것)
  - 사실이 검증로그와 맞는지 (그건 편 게이트 [5-1] 몫 — 여기서는 «출처: 도메인 · 날짜» 꼴만 본다)
  - 한마디가 «판단»인지 (사람 자리)
  - 네이버가 실제로 어떻게 판정하는지 (비공개)
"""
import io
import os
import re
import sys
import tempfile

BANNED = [
    "저희가 검증", "우리가 검증", "검증했어요", "검증을 마쳤", "AI가 작성", "AI로 작성", "본 글은 AI",
    "발표했어요", "공개했어요", "출시했어요", "밝혔어요",          # 발표 행위 서술 (SKILL v3.60)
    "드디어", "혁신", "역대급", "압도적", "완벽하게", "곧 출시",       # 과장 (편 BANNED 와 같은 결)
    "이번 주 링크 묶음을 DM 으로",                                   # 캡션 CTA 문장 되풀이
]
EP_NUM = re.compile(r"\bep\d{1,3}\b")
SRC = re.compile(r"\(출처: [a-z0-9.-]+\.[a-z]{2,}(?: [^)]*)? · 20\d\d-\d\d-\d\d\)")
PLACEHOLDER = "[[JJ 한마디]]"


def _section(md, name):
    m = re.search(r"^## %s\s*$(.*?)(?=^## |\Z)" % re.escape(name), md, re.S | re.M)
    return m.group(1) if m else None


def _text_len(s):
    return len(re.sub(r"\s+", "", s))


def check(md, publish=False, caption=None, kind=None):
    fails = []
    notes = []
    fm = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    meta = dict(re.findall(r"^(\w+):\s*(.+)$", fm.group(1), re.M)) if fm else {}
    kind = kind or meta.get("kind", "daily")
    lo, hi = (2000, 5500) if kind == "weekly" else (2500, 3500)

    if not re.search(r"^# .{10,}$", md, re.M):
        fails.append("제목 없음 (# 한 줄)")
    else:
        title = re.search(r"^# (.+)$", md, re.M).group(1)
        if not re.search(r"20\d\d년|\d+주차|\d+월 \d+일|총정리|정리|브리핑|소식", title):
            fails.append("제목에 연월·주차·총정리/브리핑 낱말 없음")

    summ = _section(md, "요약")
    if summ is None:
        fails.append("## 요약 없음")
    else:
        n_sent = len(re.findall(r"[.!?요]\s", summ + " "))
        if n_sent < 2 or n_sent > 5:
            fails.append("요약 문장 수 %d (2~5)" % n_sent)

    body = _section(md, "본문")
    if body is None:
        fails.append("## 본문 없음")
        body = ""
    qs = re.findall(r"^### Q\. .+$", body, re.M)
    if len(qs) < 2:
        fails.append("Q. 소제목 %d개 (≥2)" % len(qs))
    if "|---" not in body:
        fails.append("표 없음")
    srcs = SRC.findall(body)
    items = re.findall(r"^\*\*.+?\*\*", body, re.M)
    if len(srcs) < 3:
        fails.append("«(출처: 도메인 · YYYY-MM-DD)» %d개 (≥3)" % len(srcs))
    if items and len(srcs) < len(items):
        fails.append("굵은 소식 %d개 중 출처 %d개 — 소식마다 출처" % (len(items), len(srcs)))
    L = _text_len(summ or "") + _text_len(body)
    if not (lo <= L <= hi):
        fails.append("본문 길이 %d자 (%s %d~%d)" % (L, kind, lo, hi))

    faq = _section(md, "FAQ")
    if faq is None or len(re.findall(r"\*\*Q\.", faq)) < 3:
        fails.append("FAQ 3문답 미만")

    one = _section(md, "토망치랩 한마디")
    if one is None:
        fails.append("## 토망치랩 한마디 없음")
    else:
        has_ph = PLACEHOLDER in one
        filled = _text_len(one.replace(PLACEHOLDER, "")) >= 20
        if publish and (has_ph or not filled):
            fails.append("발행 모드: 한마디가 비어 있음 (사람이 2문장을 채운다)")
        if not publish and (not has_ph or filled):
            fails.append("초안 모드: 한마디 자리는 «%s» 로 비워 둔다 (기계가 채우지 않는다)" % PLACEHOLDER)
        if filled:
            n = len(re.findall(r"[.!?요]\s", one.replace(PLACEHOLDER, "") + " "))
            if n > 3:
                fails.append("한마디 %d문장 (≤3)" % n)

    if _section(md, "관련글") is None:
        fails.append("## 관련글 없음")

    imgs = _section(md, "이미지") or ""
    n_img = len(re.findall(r"^\d+\. ", imgs, re.M))
    if not (3 <= n_img <= 6):
        fails.append("이미지 %d장 (3~6)" % n_img)
    elif len(re.findall(r"\(출처: ", imgs)) < n_img:
        fails.append("이미지 캡션에 (출처: …) 누락")

    tags = _section(md, "태그") or ""
    tl = re.findall(r"#\S+", tags)
    if not (5 <= len(tl) <= 15):
        fails.append("해시태그 %d개 (5~15)" % len(tl))

    prose = (summ or "") + body + (faq or "") + (one or "")
    for b in BANNED:
        if b in prose:
            fails.append("금지 문형 «%s»" % b)
    if EP_NUM.search(prose):
        fails.append("편 번호 노출 (ep\\d+)")

    if caption:
        norm = lambda t: re.sub(r"[*`_]", "", t)          # 굵은 글씨 표식을 벗겨야 같은 문장이 같게 보인다
        cs = set(s.strip() for s in re.split(r"[.\n]", norm(caption)) if len(s.strip()) >= 20)
        ps = set(s.strip() for s in re.split(r"[.\n]", norm(prose)) if len(s.strip()) >= 20)
        dup = cs & ps
        if dup:
            fails.append("캡션과 같은 문장 %d개: %s" % (len(dup), list(dup)[0][:40]))

    notes.append("길이 %d자 · Q %d · 출처 %d · FAQ %d · 이미지 %d · 태그 %d · 모드 %s/%s"
                 % (L, len(qs), len(srcs), len(re.findall(r"\*\*Q\.", faq or "")), n_img, len(tl), kind, "publish" if publish else "draft"))
    return fails, notes


def run(path, publish=False, caption_path=None):
    md = io.open(path, encoding="utf-8").read()
    cap = io.open(caption_path, encoding="utf-8").read() if caption_path else None
    fails, notes = check(md, publish, cap)
    for n in notes:
        print("  " + n)
    for f in fails:
        print("  FAIL " + f)
    print("STATUS: " + ("OK" if not fails else "FAIL %d건" % len(fails)))
    return 0 if not fails else 1


# ---------------------------------------------------------------- self-test
GOOD = u"""---
kind: daily
---

# 오늘의 AI 소식 3가지 - Astra 무료 계정 일정과 Gemini 요금 (2026년 9월 8일)

## 요약

세 가지 소식을 골랐어요. 전부 공식 페이지에서 날짜를 확인했어요. 확인 못 한 것은 못 했다고 적었어요.

## 본문

### Q. 첫째 소식은 뭐예요?

**첫째 소식이에요.** 오늘 새벽 공식 페이지에 올라온 값을 그대로 옮겨 적은 문장이에요. %s (출처: openai.com · 2026-09-07)

### Q. 둘째는요?

**둘째 소식이에요.** %s (출처: blog.google · 2026-09-07)

**셋째 소식이에요.** %s (출처: claude.com · 2026-09-06)

| 소식 | 날짜 |
|---|---|
| 첫째 | 9/7 |

## FAQ

**Q. 하나?**
답이에요.

**Q. 둘?**
답이에요.

**Q. 셋?**
답이에요.

## 토망치랩 한마디

[[JJ 한마디]]

## 관련글

☞ 카드 — instagram.com/p/x

## 이미지

1. `a.png` — 표지 (출처: 토망치랩)
2. `b.png` — 카드 (출처: openai.com)
3. `c.png` — 카드 (출처: blog.google)

## 태그

#AI뉴스 #AI소식 #Astra #제미나이 #토망치랩
"""


def self_test():
    filler = ("문장이 하나 더 있어요. " * 80).strip()   # 3곳 × 80 = 일간 하한(2,500자)을 넘긴다
    good = GOOD % (filler, filler, filler)
    cases = []
    f, _ = check(good)
    cases.append(("통과본 통과", not f, f))
    f, _ = check(good.replace("[[JJ 한마디]]", "한마디를 기계가 채웠어요."))
    cases.append(("초안 모드에서 채워진 한마디 → FAIL", any("초안 모드" in x for x in f), f))
    f, _ = check(good, publish=True)
    cases.append(("발행 모드에서 빈 한마디 → FAIL", any("발행 모드" in x for x in f), f))
    f, _ = check(good.replace("[[JJ 한마디]]", "이번 주는 요금이 움직였어요. 지켜볼 자리예요."), publish=True)
    cases.append(("발행 모드 채워진 한마디 → 통과", not f, f))
    f, _ = check(good.replace("(출처: blog.google · 2026-09-07)", ""))
    cases.append(("출처 없는 소식 → FAIL", any("출처" in x for x in f), f))
    f, _ = check(good.replace("#AI뉴스 #AI소식 #Astra #제미나이 #토망치랩", "#AI뉴스 #AI소식"))
    cases.append(("해시태그 2개 → FAIL", any("해시태그" in x for x in f), f))
    f, _ = check(good.replace("첫째 소식이에요.", "첫째 소식을 발표했어요."))
    cases.append(("발표 행위 서술 → FAIL", any("금지 문형" in x for x in f), f))
    f, _ = check(good.replace("첫째 소식이에요.", "ep44 에서 다룬 소식이에요."))
    cases.append(("편 번호 노출 → FAIL", any("편 번호" in x for x in f), f))
    f, _ = check(good, caption="첫째 줄 훅이에요.\n오늘 새벽 공식 페이지에 올라온 값을 그대로 옮겨 적은 문장이에요.")
    cases.append(("캡션 문장 복붙 → FAIL", any("캡션" in x for x in f), f))
    f, _ = check(good.replace("3. `c.png` — 카드 (출처: blog.google)\n", ""))
    cases.append(("이미지 2장 → FAIL", any("이미지" in x for x in f), f))
    ok = all(c[1] for c in cases)
    for name, v, f in cases:
        print(("PASS " if v else "FAIL ") + name + ("" if v else "  <- " + "; ".join(f)))
    print("STATUS: " + ("OK" if ok else "FAIL selftest"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__); raise SystemExit(2)
    cap = None
    if "--caption" in sys.argv:
        cap = sys.argv[sys.argv.index("--caption") + 1]
    raise SystemExit(run(args[0], publish="--publish" in sys.argv, caption_path=cap))
