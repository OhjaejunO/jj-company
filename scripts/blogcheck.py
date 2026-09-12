# -*- coding: utf-8 -*-
r"""blogcheck — 네이버 블로그 초안(reports\blog\<날짜>_<이름>.md) 게이트.

WHY (2026-09-05 · 네이버 벤치마크 리포트 §5-1 규격을 기계로)
  잘 되는 글의 꼴(요약 3문장 → Q. 소제목 → 표 → FAQ → 관련글 → 태그 5~15)과
  지는 글의 신호(자동 생성 문체 · 이미지 0~1 · 해시태그 30+ · 캡션 복붙 · 자기 서술)를
  발행 전에 잰다. 사람이 읽기 전에 기계가 먼저 거른다 (정관 §0 4층 ③).

USAGE
  py scripts\blogcheck.py <md> [--publish] [--caption <caption.txt>]
     --publish: 발행 직전 회차라는 표시. 🔴 2026-09-10 에 «한마디» 축을 폐기해
       **지금은 draft 와 판정이 같다** — 모드로 갈리는 축이 하나도 남지 않았다.
     --caption: 인스타 캡션과 20자 이상 같은 문장이 있으면 FAIL (복붙 금지).
  py scripts\blogcheck.py --self-test      역검증 (통과본 1 + 걸려야 하는 입력 8)

OUTPUT  마지막 줄 STATUS: OK | STATUS: FAIL <n>건
LIMITS (정관 §0 4층 ④ — 못 잡는 것)
  - 사실이 검증로그와 맞는지 (그건 편 게이트 [5-1] 몫 — 여기서는 «출처: 도메인 · 날짜» 꼴만 본다)
  - 네이버가 실제로 어떻게 판정하는지 (비공개)
"""
import io
import os
import re
import sys
import shutil
import tempfile

BANNED = [
    "저희가 검증", "우리가 검증", "검증했어요", "검증을 마쳤", "AI가 작성", "AI로 작성", "본 글은 AI",
    "발표했어요", "공개했어요", "출시했어요", "밝혔어요",          # 발표 행위 서술 (SKILL v3.60)
    "드디어", "혁신", "역대급", "압도적", "완벽하게", "곧 출시",       # 과장 (편 BANNED 와 같은 결)
    "이번 주 링크 묶음을 DM 으로",                                   # 캡션 CTA 문장 되풀이
    "확인 못 했", "확인 못 한", "재현한 게", "저희가 돌려",             # 지면 자기 유보 (2026-09-05 JJ «빼자» · 카드 BANNED 와 같은 계열)
]
EP_NUM = re.compile(r"\bep\d{1,3}\b")


def skill_epcheck():
    """라이브 스킬 `epcheck.py` 를 모듈로 — 광고 표기 규격의 정본 (v3.80).

    🔴 **여기에 사본을 두지 않는다.** 「광고·유료광고·상업광고」 목록과 표기 줄을 떼는
    절차는 캡션·Threads·블로그 셋이 같이 쓰는 하나의 규격이고, 채널마다 목록을 두면
    **다음에 또 갈린다**(C-48 · C-26 이 그 자리다). 못 읽으면 던진다 — 부르는 쪽이
    «못 쟀다»가 아니라 **FAIL** 로 받는다(아래 주석).
    """
    p = os.environ.get("TOMANGCHI_SKILL") or os.path.join(
        os.path.expanduser("~"), ".claude", "skills", "tomangchi")
    path = os.path.join(p, "epcheck.py")
    if not os.path.exists(path):
        raise RuntimeError("라이브 스킬 epcheck.py 를 못 찾았다: %s" % path)
    import importlib.util
    spec = importlib.util.spec_from_file_location("_live_epcheck_blog", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "ad_label_ok"):
        raise RuntimeError("라이브 스킬에 광고 표기 규격(v3.80)이 없다 — deploy-skill 먼저")
    return mod


SRC = re.compile(r"\(출처: (?:[a-z0-9.-]+\.[a-z]{2,}|X / @[A-Za-z0-9_]+)(?: [^)]*)? · 20\d\d-\d\d-\d\d\)")   # 도메인 또는 X 계정


#: 영상 축이 도는 하한. 🔴 **소급하지 않는다** — 이미 올라간 일곱 편과 그 전 초안은
#  영상 절 자체가 규격에 없던 때에 쓰였고, 고칠 수 없는 것을 막는 검사는
#  통과 조합이 없는 검사다(C-26 계열 · ep28 선례).
VIDEO_AXIS_SINCE = "2026-09-12"
#: «토망치랩 한마디» 절을 되살린 날 (JJ 지시 2026-09-12). 그 전 초안은 절이 없어도 통과한다.
COMMENT_AXIS_SINCE = "2026-09-12"
#: 이미지 경로 실재 축이 서는 날. 이전 글은 이미 나갔으므로 소급하지 않는다.
IMG_PATH_AXIS_SINCE = "2026-09-12"

#: `## 이미지` 한 줄 — «1. `<경로>` — <설명> (출처: …)». `naver_draft.parse_blocks` 와 **같은 꼴**이다.
IMG_LINE = re.compile(r"^\d+\.\s+`([^`]+)`\s+\u2014\s+(.*)$")

#: 상대 경로를 푸는 두 뿌리. `naver_draft` 가 쓰던 값을 여기로 옮겼다 — 두 벌로 두면 갈린다.
HQ_ROOT = r"C:\Users\ojaej\jj-company"
WORKSHOP_ROOT = r"C:\Users\ojaej\orca\tomangchi-lab.github.io"


def resolve_image(path):
    r"""상대 경로는 «있는 쪽»으로 푼다 — `workshop\\…` 은 워크숍 루트, `reports\\…` 는 운영 서버(HQ).

    2026-09-06 실측: 영상 프레임을 `reports\\blog\\img\\` 에 뽑아 두고 워크숍 루트로만 풀어
    image-missing 이 났다.

    🔴 **이 함수는 `naver_draft` 에 있었고 게이트는 그것을 몰랐다** (2026-09-12). 그래서 채우기는
       경로를 풀 수 있었고 게이트는 줄 수만 셌다 — 아래 `[IMG-2]` 가 재는 것이 바로 이 함수의 결과다.
       **부르는 자리를 하나로 둔다**: 두 벌이면 한쪽만 고쳐지고 그때부터 둘이 다른 것을 푼다.
    """
    if os.path.isabs(path):
        return path
    for root in (WORKSHOP_ROOT, HQ_ROOT):
        q = os.path.join(root, path)
        if os.path.exists(q):
            return q
    return os.path.join(WORKSHOP_ROOT, path)   # 없으면 종전 경로 그대로 — 오류 메시지가 그 경로를 가리킨다

#: 채우기가 **먹어 치우는** 자리 표시 둘 — 이건 원고에 남아도 지면에 안 나간다.
CONSUMED_MARK = re.compile(r"^\[\[(이미지|영상)\s+\d+\]\]$")
ANY_MARK = re.compile(r"\[\[[^\[\]]+\]\]")
WORKSHOP = os.environ.get("TOMANGCHI_WORKSHOP") or \
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop"
#: 선언인 줄만 본다 — `OFFICIAL_VIDEO["file"]` 처럼 **쓰는** 줄은 선언이 아니고,
#  🔴 **`= None` 도 선언이 아니다**. 편 규격은 «공식 영상이 없으면 None 을 적는다»
#  이므로 값을 안 보면 영상 없는 편이 전부 걸린다 (2026-09-12 실측 — ep54 가 그랬다).
OFFICIAL_VIDEO_DECL = re.compile(r"^OFFICIAL_VIDEO\s*=\s*(?!None\b)\S", re.M)


def video_line_re():
    """영상 줄 꼴의 정본은 `naver_draft.VIDEO_LINE` 하나다 — 여기에 사본을 두지 않는다.
    (같은 결함이 채널마다 갈리던 자리 · 백로그 C-48)"""
    d = os.path.dirname(os.path.abspath(__file__))
    if d not in sys.path:
        sys.path.insert(0, d)
    import naver_draft
    return naver_draft.VIDEO_LINE


def episode_dir(source):
    r"""초안 `source:` 가 가리키는 **편 폴더 경로**. 못 찾으면 `None`.

    블로그 초안의 `source:` 는 «ep55 검증로그 …» 또는 «ep51_메타뮤즈 검증로그(…)» 꼴이라
    편 번호를 뽑아 워크숍 폴더를 찾는다. 편 선언(`build_epNN.py`·`_facts.py`)이 정본이고
    이 함수는 조회 결과다 (정관 §0 «실물이 정본이고 문서는 조회 결과다»).

    🔴 **조회를 함수로 갈라 둔 이유** (2026-09-12): 종전에는 이 로직이 `episode_has_video()`
       안에만 있어서, 같은 편 폴더를 봐야 하는 다음 축(`[IMG-3]`)이 **같은 코드를 다시 써야**
       했다. 두 벌이 되면 한쪽만 고쳐지고 그때부터 둘이 다른 편을 본다.
    """
    # 🔴 뒤 경계를 걸지 않는다 — 초안 `source:` 는 «ep51_메타뮤즈 …» 꼴도 쓰는데
    #    밑줄이 낱말 문자라 \b 가 안 붙어 **편을 통째로 못 찾았다**(2026-09-12 실측).
    m = re.search(r"\bep(\d{1,3})", source or "")
    if not m:
        return None
    pre = "ep" + m.group(1)
    for stage in ("01_발행완료", "02_제작중", "90_자료함"):
        d = os.path.join(WORKSHOP, stage)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name == pre or name.startswith(pre + "_"):
                return os.path.join(d, name)
    return None


def episode_has_video(source):
    """그 편이 «공식 영상»을 선언했는가. `True`·`False`·`None`(못 쟀다)."""
    folder = episode_dir(source)
    if not folder:
        return None
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".py"):
            continue
        try:
            txt = io.open(os.path.join(folder, f), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if OFFICIAL_VIDEO_DECL.search(txt):
            return True
    return False


def image_owner(path, folder):
    r"""그 그림이 **어디 소속인가** — `"편"`·`"블로그"`·`"남의 편"`·`"바깥"`.

    🔴 `[IMG-2]` 는 «있는가» 만 본다. 그런데 **엉뚱한 편의 그림도 «있다»** — 워크숍에는 60편이
       넘는 폴더가 나란히 있고 파일 이름은 편마다 똑같다(`01_cover.png`·`figure_0.png` …).
       2026-09-09 코덱스이사 초안이 이름만 적어 놨을 때 그 이름은 **여러 편에 다 있었다.**
       이번에는 맞는 편을 골랐지만 그것을 고른 것은 사람이지 검사가 아니었다.
    """
    q = os.path.normcase(os.path.abspath(resolve_image(path)))

    def under(root):
        return q.startswith(os.path.normcase(os.path.abspath(root)) + os.sep)

    if folder and under(folder):
        return "편"
    if under(os.path.join(HQ_ROOT, "reports", "blog")):   # 블로그가 직접 뽑은 프레임 자리
        return "블로그"
    if under(WORKSHOP):                                    # 워크숍 안인데 이 편이 아니다
        return "남의 편"
    return "바깥"


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
    kind = kind or meta.get("kind", "topic")
    if kind == "daily":
        kind = "topic"                       # 2026-09-05 JJ: 블로그는 «하루 한 소재 제대로» — daily 는 topic 의 옛 이름
    lo, hi = (2000, 5500) if kind == "weekly" else (2500, 4500)

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

    # 🔴 «토망치랩 한마디» 축은 2026-09-10 에 폐기했다 (JJ 지시 «한마디 절을 없앤다»).
    #    그 축은 «사람이 채워야 통과» 였고, 그래서 **JJ 서명 없이 발행하기로 한 뒤에는
    #    남은 유일한 사람 자리**가 됐다 — 승인 파일을 없애고 이 축을 두면 이름만 바뀐
    #    같은 잠금이 된다. 절 자체를 규격에서 뺐다(`docslog-format.md`).
    #    글은 사실 정리 + FAQ 로 닫는다. 판단을 실을 자리가 다시 필요해지면
    #    그때는 «누가 쓰는가» 를 먼저 정하고 축을 새로 세운다.

    if kind == "topic":
        # 한 소재 글의 뼈대 (테크토니형) — «핵심 정보 한눈에» 표 + «참고 자료» 목록
        if not re.search(r"^### 핵심 정보", body, re.M):
            fails.append("«### 핵심 정보 한눈에» 표 없음 (한 소재 글의 첫 절)")
        ref = _section(md, "참고 자료") or ""
        n_ref = len([ln for ln in ref.splitlines() if ln.startswith("- ") and re.search(r"[a-z0-9-]+\.[a-z]{2,}|X / @", ln)])
        if n_ref < 3:
            fails.append("«## 참고 자료» 출처 줄 %d (≥3, 도메인 또는 X / @핸들)" % n_ref)
    # 벤치마크 실측(2026-09-05 리포트 §4)에서 댓글 11~23 나오는 글이 전부 갖춘 셋 — JJ 지적으로 필수화
    if not re.search(r"^### Q\. .*(뭘 하면|해보면|하면 되나|하면 될까)", body, re.M):
        fails.append("실용 절 없음 — «### Q. 그래서 … 뭘 하면 되나요?» 꼴 소제목 1개 (이지온·이혜인 매 편)")
    rel = _section(md, "관련글")
    if rel is None:
        fails.append("## 관련글 없음")
    else:
        if "이웃추가" not in rel or "댓글" not in rel:
            fails.append("마무리 CTA 없음 — 관련글 절에 «댓글» 질문과 «이웃추가» 요청 둘 다")
        if kind == "weekly" and "다음 주" not in rel:
            fails.append("주간판에 «다음 주 지켜볼 것» 없음")
        if kind == "topic" and "지켜볼 것" not in rel:
            fails.append("«다음에 지켜볼 것» 없음 (후속 예고 한 단락)")

    # ── [CMT] 토망치랩 한마디 (2026-09-12 되살림 · JJ 「한마디 안써있는데?」) ─────────
    # 🔴 2026-09-10 에 **폐기했던 절을 되살린 것**이다. 폐기 사유는 «사람이 채워야 통과» 였고
    #    승인 파일을 없앤 뒤 남은 유일한 사람 자리라는 것이었다. 되살리며 **쓰는 사람을 바꿨다**
    #    — 에이전트가 쓴다. 그래서 사람 자리가 다시 생기지 않는다.
    if (meta.get("date") or "") >= COMMENT_AXIS_SINCE:
        if not (_section(md, "토망치랩 한마디") or "").strip():
            fails.append("[CMT-1] «## 토망치랩 한마디» 절이 없거나 비었다 — 판단 두 문장을 쓴다")

    # ── [PH] 채우다 만 자리표 (2026-09-12 신설) ─────────────────────────────────
    # 🔴 **이 축이 없어서 «[[JJ 한마디]]» 가 그대로 발행됐다** (2026-09-11 글 · JJ 지적).
    #    «[[이미지 N]]»·«[[영상 N]]» 은 채우기가 먹지만 그 밖의 자리표는 **아무도 안 먹어서**
    #    날것으로 지면에 나간다 — 정관 §0 «조용히 실패하는 코드를 남기지 않는다».
    #    날짜로 가르지 않는다: 나가면 언제 쓴 글이든 결함이다.
    left = [m for m in ANY_MARK.findall(md) if not CONSUMED_MARK.match(m)]
    if left:
        fails.append("[PH] 채우다 만 자리표가 남았다 — 그대로 지면에 나간다: %s" % left[0])

    imgs = _section(md, "이미지") or ""
    n_img = len(re.findall(r"^\d+\. ", imgs, re.M))
    if not (3 <= n_img <= 6):
        fails.append("이미지 %d장 (3~6)" % n_img)
    elif len(re.findall(r"\(출처: ", imgs)) < n_img:
        fails.append("이미지 캡션에 (출처: …) 누락")

    # ── [IMG-2] 그림이 실제로 거기 있는가 (2026-09-12 신설) ─────────────────────
    # 🔴 **종전 축은 «줄 수»만 셌다.** 2026-09-09 코덱스이사 초안은 경로를 `01_cover.png` 처럼
    #    **파일 이름만** 적어 놨는데 게이트는 내내 `STATUS: OK` 였고, 발행 워커가 에디터를 열기
    #    **직전에** `image-missing` 으로 섰다 — 재는 자리가 한 단계 늦었다(정관 §0 «검사는 쓰기 전에»).
    #    그날 다섯 편을 올리는 회차에서 그 한 편만 두 번 돌게 됐다.
    # 🔴 판정은 `resolve_image()` 의 결과다 — **채우기가 쓰는 바로 그 함수**다. 규칙을 베껴 쓰면
    #    한쪽만 고쳐지고 그때부터 게이트와 채우기가 다른 곳을 본다.
    # 🔴 **못 잡는 것**: 그림이 «맞는 그림인가» 는 못 본다. 있는가만 본다.
    if (meta.get("date") or "") >= IMG_PATH_AXIS_SINCE:
        gone = []
        for ln in imgs.splitlines():
            m = IMG_LINE.match(ln.strip())
            if m and not os.path.exists(resolve_image(m.group(1))):
                gone.append(m.group(1))
        if gone:
            fails.append("[IMG-2] 그림 파일이 없다 — 발행 때 선다: %s%s"
                         % (gone[0], (" 외 %d건" % (len(gone) - 1)) if len(gone) > 1 else ""))

        # ── [IMG-3] 그 그림이 «이 편의 것인가» (2026-09-12 신설) ─────────────
        # 🔴 `[IMG-2]` 의 못잡음을 한 겹 좁힌다. 워크숍에는 편 폴더가 60개 넘게 나란히 있고
        #    파일 이름은 편마다 같다 — `01_cover.png` 는 거의 모든 편에 있다. 그래서
        #    **다른 편의 그림을 붙여도 `[IMG-2]` 는 통과한다.** 이 축은 그림이 `source:` 가
        #    가리킨 편 폴더(또는 블로그가 직접 뽑은 `reports\blog\` 아래)에 있는지 본다.
        # 🔴 **못 쟀으면 세우지 않는다** — `source:` 에 편이 없는 초안(스캔로그 기반)은 대조
        #    대상이 없다. 「못 쟀다」를 「통과」로 적지 않고 노트로 남긴다(정관 §0).
        # 🔴 여전히 못 잡는 것: **맞는 편 안에서 엉뚱한 그림**을 고른 것. 그건 사람 자리다.
        _folder = episode_dir(meta.get("source"))
        if _folder:
            alien = [(m.group(1), image_owner(m.group(1), _folder))
                     for m in (IMG_LINE.match(l.strip()) for l in imgs.splitlines()) if m]
            alien = [(pth, who) for pth, who in alien if who in ("남의 편", "바깥")]
            if alien:
                fails.append("[IMG-3] %s 그림이다 — `source:` 는 %s: %s"
                             % (alien[0][1], os.path.basename(_folder), alien[0][0]))
        elif not (meta.get("source") or ""):
            notes.append("🔴 [IMG-3] 못 쟀다 — `source:` 가 비어 편 폴더를 모른다")
        else:
            notes.append("🔴 [IMG-3] 못 쟀다 — `source:` 에서 편 폴더를 못 찾았다: %r"
                         % ((meta.get("source") or "")[:40]))

    # ── [VID] 영상 축 (2026-09-12 신설) ──────────────────────────────────────
    # 🔴 **블로그에만 영상 자리가 없었다** — 조문·게이트·채우기 셋 다 0건이라
    #    `2026-09-11_챗지피티이미지2_5` 글이 「한 영상에서 차례로 볼 수 있어요」라고
    #    적어 놓고 **정지 캡처 한 장**만 실었다(JJ 지적). 인스타·릴스에는 «영상 소스는
    #    영상으로»(SKILL v3.24·v3.83)가 v3.24 부터 서 있다.
    if (meta.get("date") or "") >= VIDEO_AXIS_SINCE:
        vlines = [l.strip() for l in (_section(md, "영상") or "").splitlines()
                  if re.match(r"^\d+\.\s", l.strip())]
        bad = [l for l in vlines if not video_line_re().match(l)]
        if bad:
            # 꼴이 어긋난 줄은 채우기가 **조용히 버린다** — 여기서 잡는다 (정관 §0).
            fails.append("[VID-2] 영상 줄 꼴이 아니다 — «N. `경로.mp4` · 시작~끝 · 주소 — 설명»: %s" % bad[0][:50])
        has = episode_has_video(meta.get("source"))
        if has is None:
            notes.append("🔴 [VID] 못 쟀다 — source 에서 편 폴더를 못 찾았다: %r"
                         % ((meta.get("source") or "")[:40]))
        elif has and not vlines:
            fails.append("[VID-1] 이 편은 공식 영상을 인용했는데 «## 영상» 절이 비었다 "
                         "— 영상 소스는 영상으로 (정지 캡처만 실으면 독자는 못 본다)")

    tags = _section(md, "태그") or ""
    tl = re.findall(r"#\S+", tags)
    if not (5 <= len(tl) <= 15):
        fails.append("해시태그 %d개 (5~15)" % len(tl))

    # ── [AD] 광고(대가성) 표기 (v3.80 · 공정위 「추천·보증 등에 관한 표시·광고 심사지침」) ──
    # 🔴 **부재가 기본값이다** — 프런트매터에 `sponsor_label:` 이 없으면 광고 글이 아니므로
    #    축이 **안 돈다**(정관 §0 4층 ①). 「광고인데 선언을 안 한 글」은 못 잡는다(④ · 사람 자리).
    # 자리는 문자 매체 규정대로 **제목 또는 글 맨 앞**이다 — 네이버 본문의 맨 앞은
    #    `## 요약` 절이므로 그 첫 줄을 본다.
    sp_label = (meta.get("sponsor_label") or "").strip()
    if sp_label:
        try:
            _sk = skill_epcheck()
        except RuntimeError as _e:
            # 🔴 «못 쟀다» 로 넘기지 않는다. 이 게이트의 `STATUS: OK` 가 곧 발행 자격이라
            #    (정관 §0 발행 절), 재지 못한 채 통과시키면 표기 없는 광고 글이 나간다.
            fails.append("[AD] 광고 표기 규격을 못 읽었다 — %s" % _e)
        else:
            if not _sk.ad_label_ok(sp_label):
                fails.append("[AD-1] 표기 «%s» 에 «광고/유료광고/상업광고» 가 없다 "
                             "— 「협찬·체험단·파트너십」 만으로는 미표기다" % sp_label)
            _title = (re.search(r"^# (.+)$", md, re.M) or [None, ""])[1] \
                if re.search(r"^# (.+)$", md, re.M) else ""
            _head = next((l.strip() for l in (summ or "").splitlines() if l.strip()), "")
            if sp_label not in _title and not _head.startswith(sp_label):
                fails.append("[AD-2] 표기가 제목에도 글 맨 앞에도 없다 (문자 매체 규정) "
                             "— 맨 앞 «%s»" % _head[:30])
            sp_link = (meta.get("sponsor_link") or "").strip()
            # 🔴 프런트매터를 빼고 본다 — 안 빼면 **선언 그 자체가 «있다»로 읽혀**
            #    이 축이 영원히 통과한다(자체 검사에서 실제로 그랬다).
            _rendered = md[fm.end():] if fm else md
            if sp_link and sp_link not in _rendered:
                fails.append("[AD-3] 선언한 제휴 링크가 글에 없다: %s" % sp_link)

    prose = (summ or "") + body + (faq or "")
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

세 가지 소식을 골랐어요. 전부 공식 페이지에서 날짜를 확인했어요. 값과 조건은 발표 페이지 그대로예요.

## 본문

### 핵심 정보 한눈에

| 항목 | 내용 |
|---|---|
| 나온 날 | 9/7 |

### Q. 첫째 소식은 뭐예요?

**첫째 소식이에요.** 오늘 새벽 공식 페이지에 올라온 값을 그대로 옮겨 적은 문장이에요. %s (출처: openai.com · 2026-09-07)

### Q. 둘째는요?

**둘째 소식이에요.** %s (출처: blog.google · 2026-09-07)

**셋째 소식이에요.** %s (출처: claude.com · 2026-09-06)

### Q. 그래서 오늘 뭘 해보면 되나요?

**설정을 한 번 열어 보세요.** 바뀐 게 그대로 되는지 보면 돼요. (출처: blog.google · 2026-09-07)

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

## 관련글

☞ 카드 — instagram.com/p/x

다음에 지켜볼 것은 열리는 날이에요. 먼저 써 보고 싶은 게 뭔가요? 댓글로 남겨 주세요. 이웃추가도 부탁드려요.

## 이미지

1. `a.png` — 표지 (출처: 토망치랩)
2. `b.png` — 카드 (출처: openai.com)
3. `c.png` — 카드 (출처: blog.google)

## 참고 자료

- openai.com — 발표문 (2026-09-07)
- blog.google — 블로그 (2026-09-07)
- X / @OpenAI — 포스트 (2026-09-07)

## 태그

#AI뉴스 #AI소식 #Astra #제미나이 #토망치랩
"""


def self_test():
    filler = ("문장이 하나 더 있어요. " * 80).strip()   # 3곳 × 80 = 일간 하한(2,500자)을 넘긴다
    good = GOOD % (filler, filler, filler)
    cases = []
    f, _ = check(good)
    cases.append(("통과본 통과", not f, f))
    # 🔴 한마디 축이 **되살아났다 (2026-09-12)** — 양쪽을 다 본다 (정관 §0 — 한쪽만 보면
    #    «전부 통과시키는 검사» 도, «전부 거부하는 검사» 도 정상으로 보인다).
    dated = good.replace("kind: daily", "kind: daily\ndate: " + COMMENT_AXIS_SINCE)
    cases.append(("한마디 축: 되살린 날 **이전** 초안은 절이 없어도 통과 (옛 초안을 안 막는다)",
                  not any(x.startswith("[CMT") for x in check(good)[0]), check(good)[0]))
    cases.append(("🔴 한마디 축: 되살린 날 **이후** 초안에 절이 없으면 FAIL",
                  any(x.startswith("[CMT-1]") for x in check(dated)[0]), check(dated)[0]))
    cmt_ok = dated.replace("## 관련글", "## 토망치랩 한마디\n\n한 문장이에요. 두 문장이에요.\n\n## 관련글")
    cases.append(("한마디를 쓰면 통과",
                  not any(x.startswith("[CMT") for x in check(cmt_ok)[0]), check(cmt_ok)[0]))
    # ── [PH] 자리표 — 양방향. 채우기가 먹는 둘은 통과, 그 밖은 FAIL.
    ph_bad = cmt_ok.replace("한 문장이에요. 두 문장이에요.", "[[JJ 한마디]]")
    cases.append(("🔴 채우다 만 «[[JJ 한마디]]» → FAIL (나간 글에서 실제로 난 결함)",
                  any(x.startswith("[PH]") for x in check(ph_bad)[0]), check(ph_bad)[0]))
    ph_ok = cmt_ok.replace("## 관련글", "[[이미지 2]]\n[[영상 1]]\n\n## 관련글")
    cases.append(("자리표 축이 헛돌지 않는다 — 채우기가 먹는 둘은 통과",
                  not any(x.startswith("[PH]") for x in check(ph_ok)[0]), check(ph_ok)[0]))
    # ── [IMG-2] 그림 실재 — 세 면 (2026-09-12). 🔴 **있는 쪽과 없는 쪽을 따로** 본다:
    #    한쪽만 보면 «전부 통과시키는 검사» 도 «전부 막는 검사» 도 정상으로 보인다(정관 §0).
    _here = os.path.dirname(os.path.abspath(__file__))
    _real = dated
    for _n, _f in (("a.png", "blogcheck.py"), ("b.png", "blogcheck.py"), ("c.png", "blogcheck.py")):
        _real = _real.replace("`%s`" % _n, "`%s`" % os.path.join(_here, _f))
    cases.append(("🔴 [IMG-2] 없는 그림 경로 → FAIL (발행 워커가 직전에 서던 자리)",
                  any(x.startswith("[IMG-2]") for x in check(dated)[0]), check(dated)[0]))
    cases.append(("[IMG-2] 실재하는 경로는 통과 — 전부 막는 검사가 아니다",
                  not any(x.startswith("[IMG-2]") for x in check(_real)[0]), check(_real)[0]))
    cases.append(("[IMG-2] 축이 서기 전 초안은 안 본다 (기발행분 소급 없음)",
                  not any(x.startswith("[IMG-2]") for x in check(good)[0]), check(good)[0]))
    f, _ = check(good, publish=True)
    cases.append(("옛 초안은 --publish 로도 판정이 같다", not f, f))
    f, _ = check(good.replace("(출처: blog.google · 2026-09-07)", ""))
    cases.append(("출처 없는 소식 → FAIL", any("출처" in x for x in f), f))
    f, _ = check(good.replace("#AI뉴스 #AI소식 #Astra #제미나이 #토망치랩", "#AI뉴스 #AI소식"))
    cases.append(("해시태그 2개 → FAIL", any("해시태그" in x for x in f), f))
    f, _ = check(good.replace("첫째 소식이에요.", "첫째 소식을 발표했어요."))
    cases.append(("발표 행위 서술 → FAIL", any("금지 문형" in x for x in f), f))
    f, _ = check(good.replace("첫째 소식이에요.", "첫째 소식이에요. 무료 일정은 확인 못 했어요."))
    cases.append(("지면 자기 유보 «확인 못 했어요» → FAIL", any("금지 문형 «확인 못 했»" in x for x in f), f))
    f, _ = check(good.replace("첫째 소식이에요.", "ep44 에서 다룬 소식이에요."))
    cases.append(("편 번호 노출 → FAIL", any("편 번호" in x for x in f), f))
    f, _ = check(good, caption="첫째 줄 훅이에요.\n오늘 새벽 공식 페이지에 올라온 값을 그대로 옮겨 적은 문장이에요.")
    cases.append(("캡션 문장 복붙 → FAIL", any("캡션" in x for x in f), f))
    f, _ = check(good.replace("3. `c.png` — 카드 (출처: blog.google)\n", ""))
    cases.append(("이미지 2장 → FAIL", any("이미지" in x for x in f), f))
    f, _ = check(good.replace("### Q. 그래서 오늘 뭘 해보면 되나요?", "### Q. 넷째는요?"))
    cases.append(("실용 절 없음 → FAIL", any("실용 절" in x for x in f), f))
    f, _ = check(good.replace("이웃추가도 부탁드려요.", ""))
    cases.append(("이웃추가 없음 → FAIL", any("마무리 CTA" in x for x in f), f))
    f, _ = check(good.replace("kind: daily", "kind: weekly"))
    cases.append(("주간판에 다음 주 예고 없음 → FAIL", any("다음 주" in x for x in f), f))
    f, _ = check(good.replace("kind: daily", "kind: weekly").replace("이웃추가도 부탁드려요.", "이웃추가도 부탁드려요. 다음 주 지켜볼 것은 하나예요."))
    cases.append(("주간판 예고 있으면 통과", not any("다음 주" in x for x in f), f))
    f, _ = check(good.replace("### 핵심 정보 한눈에", "### 정보"))
    cases.append(("한 소재 글에 핵심 정보 표 없음 → FAIL", any("핵심 정보" in x for x in f), f))
    f, _ = check(good.replace("- blog.google — 블로그 (2026-09-07)\n", ""))
    cases.append(("참고 자료 2줄 → FAIL", any("참고 자료" in x for x in f), f))

    # ── [AD] 광고 표기 (v3.80) — 양방향. 🔴 «선언이 없으면 안 돈다» 를 맨 먼저 본다.
    LABEL = "광고 · 클래스101 파트너스 수수료 지급"
    cases.append(("🔴 sponsor_label 선언이 없으면 [AD] 축이 돌지 않는다",
                  not any(x.startswith("[AD") for x in check(good)[0]), check(good)[0]))
    ad_fm = "kind: daily\nsponsor_label: " + LABEL
    ad_good = good.replace("kind: daily", ad_fm).replace(
        "## 요약\n\n세 가지", "## 요약\n\n" + LABEL + "\n세 가지")
    f, _ = check(ad_good)
    cases.append(("표기를 글 맨 앞에 두면 통과한다", not any(x.startswith("[AD") for x in f), f))
    f, _ = check(good.replace("kind: daily", ad_fm))
    cases.append(("🔴 선언만 하고 지면에 안 적으면 [AD-2] FAIL",
                  any(x.startswith("[AD-2]") for x in f), f))
    vague = "클래스101 협찬"
    f, _ = check(good.replace("kind: daily", "kind: daily\nsponsor_label: " + vague).replace(
        "## 요약\n\n세 가지", "## 요약\n\n" + vague + "\n세 가지"))
    cases.append(("🔴 «협찬» 만으로 때우면 [AD-1] FAIL",
                  any(x.startswith("[AD-1]") for x in f) and
                  not any(x.startswith("[AD-2]") for x in f), f))
    f, _ = check(ad_good.replace(
        "sponsor_label: " + LABEL,
        "sponsor_label: " + LABEL + "\nsponsor_link: https://example.invalid/c101"))
    cases.append(("🔴 선언한 제휴 링크가 글에 없으면 [AD-3] FAIL",
                  any(x.startswith("[AD-3]") for x in f), f))
    # 🔴 라이브에 규격이 없을 때 **통과시키지 않는다.** «못 쟀다» 로 넘기면 이 게이트의
    #    `STATUS: OK` 가 곧 발행 자격이라(정관 §0) 표기 없는 광고 글이 그대로 나간다.
    _old_sk = os.environ.get("TOMANGCHI_SKILL")
    _tmp = tempfile.mkdtemp(prefix="blogad_")
    try:
        os.environ["TOMANGCHI_SKILL"] = _tmp          # epcheck.py 가 없는 디렉토리
        f, _ = check(ad_good)
        cases.append(("🔴 라이브에 규격이 없으면 [AD] FAIL (조용히 통과 아님)",
                      any(x.startswith("[AD]") for x in f), f))
    finally:
        if _old_sk is None:
            os.environ.pop("TOMANGCHI_SKILL", None)
        else:
            os.environ["TOMANGCHI_SKILL"] = _old_sk
        shutil.rmtree(_tmp, ignore_errors=True)

    # ── [VID] 영상 축 (2026-09-12) — 양방향 ─────────────────────────────────
    # 편 선언은 워크숍 실물이 정본이라, 자체 검사는 **가짜 워크숍**을 세워 잰다.
    global WORKSHOP
    _old_w, _w = WORKSHOP, tempfile.mkdtemp(prefix="blogvid_")
    try:
        _pub = os.path.join(_w, "01_발행완료")
        for ep, decl in (("ep99_영상편", 'OFFICIAL_VIDEO = {"url": "https://x.com/a/1"}\n'),
                         ("ep98_무영상편", 'src = OFFICIAL_VIDEO["file"]\n'),
                         ("ep97_None편", 'OFFICIAL_VIDEO = None\n')):
            os.makedirs(os.path.join(_pub, ep))
            io.open(os.path.join(_pub, ep, "build_%s.py" % ep.split("_")[0]), "w",
                    encoding="utf-8").write(decl)
        WORKSHOP = _w
        vfm = lambda ep, date="2026-09-12": "kind: daily\ndate: %s\nsource: %s 검증로그" % (date, ep)
        vsec = ("## 영상\n\n1. `workshop\\v.mp4` · 3~9.5 · https://x.com/a/1 — 스케치가 변하는 구간\n\n")
        base = good.replace("kind: daily", vfm("ep99"))
        f, _ = check(base)
        cases.append(("🔴 공식 영상을 선언한 편인데 «## 영상» 절이 비면 [VID-1] FAIL",
                      any(x.startswith("[VID-1]") for x in f), f))
        f, _ = check(base.replace("## 태그", vsec + "## 태그"))
        cases.append(("영상 절을 채우면 통과한다", not any(x.startswith("[VID") for x in f), f))
        f, _ = check(good.replace("kind: daily", vfm("ep98")))
        cases.append(("공식 영상을 선언하지 않은 편은 영상 절이 없어도 통과 (쓰는 줄은 선언이 아니다)",
                      not any(x.startswith("[VID") for x in f), f))
        f, _ = check(good.replace("kind: daily", vfm("ep99", "2026-09-11")))
        cases.append(("🔴 하한 날짜 전 초안은 축이 돌지 않는다 (기발행분 소급 없음)",
                      not any(x.startswith("[VID") for x in f), f))
        f, _ = check(base.replace("## 태그",
                                  "## 영상\n\n1. workshop/v.mp4 그냥 이 영상\n\n## 태그"))
        cases.append(("🔴 영상 줄 꼴이 어긋나면 [VID-2] FAIL (조용히 버려지지 않는다)",
                      any(x.startswith("[VID-2]") for x in f), f))
        f, n_ = check(good.replace("kind: daily", "kind: daily\ndate: 2026-09-12\nsource: 스캔로그"))
        cases.append(("source 에 편이 없으면 «못 쟀다» 를 적고 세우지는 않는다",
                      not any(x.startswith("[VID") for x in f)
                      and any("[VID] 못 쟀다" in x for x in n_), f))
        cases.append(("편 폴더 조회가 셋을 갈라 돌려준다 (True·False·None)",
                      (episode_has_video("ep99 검증로그"), episode_has_video("ep98 검증로그"),
                       episode_has_video("스캔로그")) == (True, False, None), []))
        cases.append(("🔴 «ep99_영상편 검증로그» 밑줄 꼴도 찾는다 (실물 source 가 그 꼴이다)",
                      episode_has_video("ep99_영상편 검증로그(2026-09-10)") is True, []))
        cases.append(("🔴 «OFFICIAL_VIDEO = None» 은 선언이 아니다 (영상 없는 편이 다 걸리던 자리)",
                      episode_has_video("ep97 검증로그") is False, []))

        # ── [IMG-3] 그림 소속 — 네 면 (2026-09-12) ──────────────────────────
        # 🔴 **«제 편»과 «남의 편»을 따로** 본다. 한쪽만 보면 전부 통과시키는 검사도,
        #    전부 막는 검사도 정상으로 보인다(정관 §0 역검증).
        _mine = os.path.join(_pub, "ep99_영상편", "01_cover.png")
        _alien = os.path.join(_pub, "ep98_무영상편", "01_cover.png")
        io.open(_mine, "w").write("x")
        io.open(_alien, "w").write("x")
        _imgs = lambda a, b, c: (
            "## 이미지\n\n1. `%s` \u2014 하나 (출처: x.com)\n"
            "2. `%s` \u2014 둘 (출처: x.com)\n3. `%s` \u2014 셋 (출처: x.com)\n\n" % (a, b, c))
        _base = good.replace("kind: daily", vfm("ep99"))
        _ok = re.sub(r"(?sm)^## 이미지\s*$.*?(?=^## )", lambda _m: _imgs(_mine, _mine, _mine), _base)
        _bad = re.sub(r"(?sm)^## 이미지\s*$.*?(?=^## )", lambda _m: _imgs(_mine, _alien, _mine), _base)
        f, _ = check(_bad)
        cases.append(("🔴 [IMG-3] 남의 편 그림이면 FAIL (이름이 같아서 [IMG-2] 는 통과한다)",
                      any(x.startswith("[IMG-3]") for x in f)
                      and not any(x.startswith("[IMG-2]") for x in f), f))
        f, _ = check(_ok)
        cases.append(("[IMG-3] 제 편 그림은 통과 — 전부 막는 검사가 아니다",
                      not any(x.startswith("[IMG-3]") for x in f), f))
        f, n_ = check(_ok.replace("source: ep99 검증로그", "source: 스캔로그"))
        cases.append(("[IMG-3] 편을 못 찾으면 «못 쟀다» 를 적고 세우지는 않는다",
                      not any(x.startswith("[IMG-3]") for x in f)
                      and any("[IMG-3] 못 쟀다" in x for x in n_), f))
        cases.append(("소속을 넷으로 가른다 (편·남의 편·블로그·바깥)",
                      (image_owner(_mine, os.path.dirname(_mine)),
                       image_owner(_alien, os.path.dirname(_mine)),
                       image_owner(os.path.join(HQ_ROOT, "reports", "blog", "img", "a.png"),
                                   os.path.dirname(_mine)),
                       image_owner(os.path.join(HQ_ROOT, "logs", "a.png"),
                                   os.path.dirname(_mine)))
                      == ("편", "남의 편", "블로그", "바깥"), []))
    finally:
        WORKSHOP = _old_w or r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop"
        shutil.rmtree(_w, ignore_errors=True)

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
