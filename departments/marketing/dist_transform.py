# -*- coding: utf-8 -*-
"""유통 변환 워커 — 발행 완료 편 → Threads 텍스트 스레드 (2026-08-27).

설계 정본은 `docs/workers/distribution-transform.md`. 이 파일은 그 PROCESS 중
**결정적인 부분만** 맡는다 — 1(주장 목록)·2(소스 맵 재료)·5(복붙 세트 조립)·6(게이트 호출).
3~4(압축·배치)는 판단이 필요해 사람 또는 헤르메스 ⑥ 이 «초안 원고» 로 쓴다.
정관 §0 이 추측을 금하는 자리에는 코드를, 판단이 필요한 자리에는 사람을 둔다.

    py dist_transform.py brief --ep 34
        편을 읽어 «작업 지시서» 를 낸다 — 주장 목록 · FACTS 키 후보 · 킷 URL · 제약 · 규칙.
    py dist_transform.py pack --ep 34 --draft <초안.md>
        게이트를 먼저 돌리고, 통과하면 발행 복붙 세트를 쓴다.
        **검사가 쓰기보다 앞이다** (정관 §0 — 반쪽 상태를 남기지 않는다).

초안 원고 형식 (사람이 쓰는 파일):

    ## P1
    첫 줄이 훅이에요.
    이어지는 문장이에요.

    ## P2
    ...

    ## 소스 맵
    | 포스트 | 문장 | 근거 |
    |---|---|---|
    | P1 | 1 | - |
    | P1 | 2 | PARAMS_MAIN, PARAMS_ACTIVE |

    ## 첨부 미디어
    | 포스트 | 파일 | 출처키 | 크레딧 | 층위 | 형상 |
    |---|---|---|---|---|---|
    | P1 | shots/02_banner.png | BLOG | Qwen | 공식 | 이미지 1920x1080 |

근거는 셋 중 하나다 — `_facts.py` 의 **변수 이름** · `KIT_URL` · `-`(사실 주장 없는 문장).
`-` 인 줄에 수치가 있으면 게이트 `[5-3]` 이 막는다. 소스 맵에 없는 문장은 존재할 수 없다.

첨부는 **공식 원본만**이고 `shots/`·`_assets/` 아래여야 한다 — 편 폴더 루트의 `01_`~`09_` 는
**우리가 조립한 카드**라 붙이면 인스타 재탕이 된다(파일명이 겹치므로 디렉토리가 유일한 구분이다).
크레딧은 그림에 박혀 있지 않으니 **본문에 `이미지 출처: <크레딧>` 줄**을 두고 소스 맵에도 한 행 넣는다.

읽기만 한다. 편 폴더(출장지)에는 쓰지 않는다 — 정관 §2.
"""
import argparse
import ast
import datetime
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import distcheck

# 두 모듈이 서로를 import 하므로 한 번만 감싼다 - 겹쳐 감싸면 앞 래퍼가 버퍼를 닫는다.
if hasattr(sys.stdout, "buffer") and not getattr(sys.stdout, "_dist_wrapped", False):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stdout._dist_wrapped = True

#: 발행 완료 편들이 있는 곳. 출장지 — **읽기 전용** (정관 §2).
PUBLISHED = os.environ.get(
    "TOMANGCHI_PUBLISHED",
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop\01_발행완료")


def repo_root():
    """departments/marketing/<이 파일> → 레포 뿌리. 리포트는 정관 §4 대로 `reports\\` 에 쓴다."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_ep_dir(ep):
    if ep is None:
        raise RuntimeError("--ep 또는 --ep-dir 가 필요하다")
    hits = [d for d in os.listdir(PUBLISHED) if re.match(r"^ep%d(_|$)" % ep, d)]
    if not hits:
        raise RuntimeError("ep%s 폴더를 못 찾았다: %s" % (ep, PUBLISHED))
    return os.path.join(PUBLISHED, sorted(hits)[0])


# ── 편 선언 읽기 ─────────────────────────────────────────────────────────
def _module_literals(path):
    """`build_epNN.py` 를 **실행하지 않고** 최상위 리터럴 대입만 뽑는다.

    빌더는 스킬 모듈을 import 하고 경로를 만지므로 import 하면 부작용이 있다.
    `COVER = COVER_A` 처럼 같은 파일 안의 이름을 가리키는 대입은 한 번 더 풀어 준다."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out, alias = {}, {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        t = node.targets[0]
        if not isinstance(t, ast.Name):
            continue
        try:
            out[t.id] = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            if isinstance(node.value, ast.Name):
                alias[t.id] = node.value.id
    for k, v in alias.items():
        if v in out:
            out[k] = out[v]
    return out


def load_ep(ep_dir):
    builds = [f for f in os.listdir(ep_dir) if re.match(r"^build_ep\d+\.py$", f)]
    if not builds:
        raise RuntimeError("빌더 선언 파일이 없다: %s" % ep_dir)
    decl = _module_literals(os.path.join(ep_dir, sorted(builds)[0]))
    kit = decl.get("KIT") or {}
    if not kit.get("url"):
        raise RuntimeError("편 선언에 KIT['url'] 이 없다 — 마지막 포스트에 무엇을 넣을지 정할 수 없다")

    def _read(name):
        p = os.path.join(ep_dir, name)
        return io.open(p, encoding="utf-8").read().strip() if os.path.exists(p) else ""

    return {
        "dir": ep_dir,
        "EP": decl.get("EP"),
        "CARDS": decl.get("CARDS") or {},
        "COVER": decl.get("COVER") or (),
        # None = 공식 영상 «무» · {url, dur} = 유 (SKILL v3.54 §7). 첨부 미디어 `[10-6]` 이 본다.
        "OFFICIAL_VIDEO": decl.get("OFFICIAL_VIDEO"),
        # 편이 첨부용 공식 원본을 지목했으면 그것이 정본이다 — `shots/` 추측보다 우선한다.
        "ATTACH_OFFICIAL": decl.get("ATTACH_OFFICIAL"),
        "kit_url": kit["url"],
        "caption": _read("caption.txt"),
        "pinned": _read("pinned_comment.txt"),
        "verify_log": _read("검증로그.md"),      # 서드파티 영상 4조건 ⓒ 대조용
        "pack": _read("발행팩.md"),               # 4조건 ⓓ «## 서드파티 영상 승인» 절 확인용
        "facts": distcheck.load_facts(ep_dir),
    }


#: 카드 상단 판의 실크기. `_beforeafter.py`·자체 도해가 내는 값이라 **이 크기면 우리 합성 판**이다.
#: 공식 캡처가 우연히 딱 이 크기로 나오는 일은 없다(webshot·CDN 원본은 임의 크기).
PLATE_SIZE = (1080, 776)


def official_sources(ep):
    """편이 실제로 쓴 **공식 원본 캡처** 목록 — 첨부 후보다.

    카드 선언의 `shot`/`credit` 이 정본이다. 같은 파일명이 편 폴더 루트에도 있지만 그쪽은
    **우리가 조립한 카드**이므로 후보가 아니다 — `shots/` 아래만 낸다.

    🔴 **`shots/` 아래가 곧 «공식 원본»은 아니다 (2026-08-28 개정).** ep38 2차 교정에서
    `shots/02_anchor.png`·`03_official.png`·`04_ours.png` 가 **전/후를 합치고 우리 라벨을 얹은
    합성 판**으로 바뀌었다. 그걸 그대로 첨부하면 «공식 원본만» 규칙을 어긴 채 **규칙을 지킨 것처럼**
    보인다 — 정관 §0 «조용히 실패하는 코드».

    그래서 둘을 본다.
      ① **편 선언 `ATTACH_OFFICIAL`** 이 있으면 그것이 정본이다(편 폴더 기준 상대 경로 목록).
      ② 없으면 `shots/` 를 훑되, **판 실크기(1080x776)인 파일은 «우리 합성 판»으로 표시**해
         후보에서 빼고 사유를 같이 낸다. 조용히 넣지 않는다.
    """
    declared = ep.get("ATTACH_OFFICIAL")
    if declared:
        out = []
        for rel in declared:
            p = os.path.join(ep["dir"], rel.replace("/", os.sep))
            if not os.path.exists(p):
                out.append({"card": "-", "path": rel, "credit": "", "shape": "🔴 파일 없음",
                            "headline": "편 선언 ATTACH_OFFICIAL 에 있으나 실물이 없다"})
                continue
            kind, w, h, dur = distcheck.probe_media(p)
            shape = kind + (" %dx%d" % (w, h) if w else "") + (" %gs" % dur if dur is not None else "")
            out.append({"card": "선언", "path": rel, "credit": "", "shape": shape,
                        "headline": "편이 ATTACH_OFFICIAL 로 지목한 공식 원본"})
        return out

    out = []
    for no in sorted(ep["CARDS"]):
        c = ep["CARDS"][no]
        shot = c.get("shot")
        if not shot:
            continue
        rel = "shots/" + shot
        p = os.path.join(ep["dir"], "shots", shot)
        if not os.path.exists(p):
            continue
        kind, w, h, dur = distcheck.probe_media(p)
        shape = kind + (" %dx%d" % (w, h) if w else "")
        if dur is not None:
            shape += " %gs" % dur
        composite = (w, h) == PLATE_SIZE
        out.append({"card": no, "path": rel, "credit": c.get("credit", ""),
                    "shape": ("🔴 우리 합성 판 — " if composite else "") + shape,
                    "composite": composite,
                    "headline": c.get("headline", "")})
    return out


# ── PROCESS 1~2: 주장 목록 · FACTS 키 후보 ───────────────────────────────
def claims(ep):
    """카드 선언을 «주장» 단위로 편다. 헤드라인·핵심줄·본문 각 줄이 한 주장이다 (설계 PROCESS 1)."""
    out = []
    for no in sorted(ep["CARDS"]):
        c = ep["CARDS"][no]
        out.append((no, "헤드라인", c.get("headline", "")))
        out.append((no, "핵심줄", c.get("key", "")))
        for i, ln in enumerate(c.get("body") or [], 1):
            out.append((no, "본문%d" % i, ln))
    return [(a, b, t) for a, b, t in out if t]


def fact_index(facts):
    """`_facts.py` 의 «값 → 변수 이름» 색인. 소스 맵을 사람이 손으로 찾지 않게 한다 (설계 PROCESS 2)."""
    #: 파생 집합 — 다른 변수를 모아 만든 것이라 근거로 적으면 «어디서 왔는지» 가 안 갈린다.
    DERIVED = ("KIT_MUST", "KIT_EXTRA", "NOISE", "PREV")
    idx = {}
    for name in dir(facts):
        if name.startswith("_") or name in DERIVED or callable(getattr(facts, name, None)):
            continue
        v = getattr(facts, name)
        if isinstance(v, str):
            idx.setdefault(v, []).append(name)
        elif isinstance(v, (list, tuple, set)):
            for x in v:
                if isinstance(x, str):
                    idx.setdefault(x, []).append(name)
        elif isinstance(v, dict):
            for k, x in v.items():
                for y in (x if isinstance(x, (tuple, list)) else [x]):
                    if isinstance(y, str):
                        idx.setdefault(y, []).append("%s[%s]" % (name, k))
    return idx


def keys_for(text, idx):
    """문장에 실린 값들이 어느 FACTS 변수에서 왔는지 — 긴 값부터 맞춰 본다."""
    hit = []
    for val in sorted(idx, key=len, reverse=True):
        if len(val) >= 2 and val in text:
            for n in idx[val]:
                base = n.split("[")[0]
                if base not in hit:
                    hit.append(base)
    return hit


def brief(ep):
    L = []
    a = L.append
    a("# ep%s 유통 변환 작업 지시서 — Threads 텍스트 스레드" % ep["EP"])
    a("")
    a("> 이 문서는 **재료**다. 초안 원고는 사람(또는 헤르메스 ⑥)이 쓴다.")
    a("> 설계 정본 `docs/workers/distribution-transform.md` · 게이트 `distcheck.py`")
    a("")
    a("## 제약")
    a("")
    a("- 포스트 %d~%d개, 스레드로 이어 붙인다." % (distcheck.POSTS_MIN, distcheck.POSTS_MAX))
    a("- 포스트당 %d자 이하 (Threads 공표값 — 우리 실측 아님, `유통확장_설계안.md` §3)."
      % distcheck.THREADS_CHAR_MAX)
    a("- 킷 URL 은 **마지막 포스트에만** 1건: `%s`" % ep["kit_url"])
    a("- 어미는 **해요체**. 자기 언급·제작 과정 서사 0건. 부정 톤 금지.")
    a("- 벤치 수치를 실은 포스트에는 «%s» 라벨을 단다." % distcheck.OFFICIAL_LABEL)
    a("- **인스타 캡션을 복붙하지 않는다** — 같은 사실을 텍스트 매체 문법으로 다시 쓴다.")
    a("  첫 줄이 훅이고, 이미지 없이 읽혀야 한다.")
    a("- 소스 맵에 없는 문장은 존재할 수 없다. 근거가 없으면 **뺀다**(덜 싣는 건 자유).")
    a("")
    a("## 첨부 미디어 후보 (공식 원본만)")
    a("")
    ov = ep.get("OFFICIAL_VIDEO")
    if ov:
        a("- 🔴 **공식 영상이 있다** — `%s` (%s). Threads 는 영상 도달이 가장 높아 **영상이 먼저다**"
          % (ov.get("url", "?"), ov.get("dur", "?")))
    else:
        a("- 공식 영상 **무**(편 선언 `OFFICIAL_VIDEO = None`) → 공식 이미지로 간다.")
    a("- 🔴 **우리가 조립한 카드를 붙이지 않는다.** 편 폴더 루트의 `01_`~`09_` 가 그것이다.")
    a("  🔴 **`shots/` 아래도 무조건 공식 원본은 아니다** — 전/후 합성 판(`_beforeafter.py`)이 거기 앉는다.")
    a("  편이 `ATTACH_OFFICIAL` 을 선언했으면 그것이 정본이고, 아니면 판 실크기(1080x776)인 파일을")
    a("  **«우리 합성 판»으로 표시**해 후보에서 뺀다.")
    a("- 크레딧은 그림에 안 박혀 있으므로 **본문에 `이미지 출처: <크레딧>` 줄**로 적는다.")
    a("  그 줄도 소스 맵에 한 행이 필요하다(근거 = 출처키).")
    a("")
    srcs = official_sources(ep)
    if srcs:
        a("| 카드 | 파일 | 크레딧 | 형상 | 그 카드가 말하는 것 |")
        a("|---|---|---|---|---|")
        for s in srcs:
            a("| %s | `%s` | %s | %s | %s |"
              % (s["card"], s["path"], s["credit"], s["shape"], s["headline"]))
    else:
        a("- `shots/` 에 공식 원본 캡처가 없다 — 첨부 없이 텍스트로 간다.")
    if any(s.get("composite") for s in srcs):
        a("")
        a("🔴 **위 표에 «우리 합성 판»이 있다.** 그건 첨부하지 마라 — 공식 원본은 편 폴더의")
        a("`_official/` 같은 자리에 따로 있다. 편 선언에 `ATTACH_OFFICIAL = [\"_official/….png\"]` 을")
        a("적어 두면 다음 회차부터 이 표가 그것을 낸다.")
    a("")
    a("**출처키**는 `_facts.py` 의 URL 변수 이름으로 적는다. 이 편에 있는 것:")
    a("")
    for n in sorted(dir(ep["facts"])):
        v = getattr(ep["facts"], n, None)
        if not n.startswith("_") and isinstance(v, str) and v.startswith("http"):
            a("- `%s` — %s" % (n, v))
    a("")
    a("## 주장 목록 (카드 선언 · 정본)")
    a("")
    idx = fact_index(ep["facts"])
    for no, slot, text in claims(ep):
        ks = keys_for(text, idx)
        a("- `%s %s` %s" % (no, slot, text))
        a("  - 근거 후보: %s" % (", ".join("`%s`" % k for k in ks) if ks else "— (무주장 또는 수동 확인)"))
    a("")
    a("## 표지 훅 (참고 — 반말 허용 자리라 그대로 쓰지 않는다)")
    a("")
    a("- %s" % " / ".join(ep["COVER"]) if ep["COVER"] else "- 선언 없음")
    a("")
    a("## 캡션 (참고 — **복붙 금지**, 게이트 `[9]` 가 한글 %d자 연속 일치를 막는다)"
      % distcheck.CAPTION_SHINGLE)
    a("")
    a("```")
    a(ep["caption"] or "(없음)")
    a("```")
    return "\n".join(L)


# ── PROCESS 5: 발행 복붙 세트 ────────────────────────────────────────────
def pack(ep, posts, rows, gate, media=None):
    today = datetime.date.today().isoformat()
    L = []
    a = L.append
    a("# ep%s Threads 발행 복붙 세트 — %s" % (ep["EP"], today))
    a("")
    a("> **JJ 는 이 섹션만 본다.** 포스트를 위에서부터 차례로 올리고, 2번째부터는 **답글로 이어 붙인다.**")
    a("> 발행은 사람이 한다 — API 자동 게시는 범위 밖(정관 §0 C등급).")
    a("")
    a("## 발행 순서")
    a("")
    by_post = {}
    for m in (media or []):
        by_post.setdefault(m["post"], []).append(m)
    for i, p in enumerate(posts, 1):
        a("### %s%d — %d자" % ("P", i, len(p)))
        a("")
        a("```")
        a(p)
        a("```")
        a("")
        for m in by_post.get(i, []):
            a("**첨부** `%s` — %s · 크레딧 `%s` · %s"
              % (os.path.join(ep["dir"], m["path"].replace("/", os.sep)),
                 m["shape"], m["credit"], m["tier"]))
        if by_post.get(i):
            a("")
    a("## 게이트")
    a("")
    a("검사 판본: 라이브 스킬 `%s`" % distcheck.skill_revision())
    a("")
    for label, verdict, detail in gate.items:
        a("- `%s` %s%s" % ({"OK": " OK ", "FAIL": "FAIL", "NA": " -- "}[verdict], label,
                           ("  — " + detail) if detail else ""))
    a("")
    a("## 소스 맵")
    a("")
    a("| 포스트 | 문장 | 근거 | 문장 |")
    a("|---|---|---|---|")
    for pi, si, key in rows:
        sents = distcheck.sentences(posts[pi - 1]) if 1 <= pi <= len(posts) else []
        s = sents[si - 1] if 1 <= si <= len(sents) else ""
        a("| P%d | %d | `%s` | %s |" % (pi, si, key, s.replace("|", "/")))
    a("")
    a("## 발행 후 JJ 가 할 일")
    a("")
    a("- 발행로그에 **게시물** 1건 추가 (편수는 그대로 — SKILL v3.52 ⓗ 편/게시물 층 분리).")
    a("- 수정한 줄이 있으면 알려 준다 — 설계 성공지표가 «수정 없이 발행한 비율» 이다.")
    return "\n".join(L)


def write_utf8(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)


# ── CLI ─────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="유통 변환 워커 (Threads 텍스트 스레드)")
    ap.add_argument("cmd", choices=["brief", "pack"])
    ap.add_argument("--ep", type=int)
    ap.add_argument("--ep-dir")
    ap.add_argument("--draft")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    ep = load_ep(a.ep_dir or find_ep_dir(a.ep))
    today = datetime.date.today().isoformat()
    outdir = os.path.join(repo_root(), "reports")

    if a.cmd == "brief":
        out = a.out or os.path.join(outdir, "%s_dist_ep%s.brief.md" % (today, ep["EP"]))
        write_utf8(out, brief(ep))
        print("작업 지시서: %s" % out)
        return 0

    if not a.draft:
        ap.error("pack 에는 --draft 가 필요하다")
    posts, rows, media = distcheck.parse_draft(io.open(a.draft, encoding="utf-8").read())
    gate = distcheck.check(posts, rows, ep["facts"], ep["kit_url"], ep["caption"],
                           distcheck.load_cardcheck(), media=media, ep=ep)
    print("유통 변환 게이트 — ep%s" % ep["EP"])
    distcheck.report(gate)
    if gate.failed:
        # 검사가 쓰기보다 앞이다 — 반쪽 산출물을 남기지 않는다 (정관 §0).
        print("복붙 세트를 쓰지 않았다 — 게이트 FAIL %d건을 먼저 고친다." % len(gate.failed))
        return 1
    out = a.out or os.path.join(outdir, "%s_dist_ep%s.md" % (today, ep["EP"]))
    write_utf8(out, pack(ep, posts, rows, gate, media))
    print("복붙 세트: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
