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


#: 원고가 나가는 자리. **절대경로다** — `__file__` 에서 거슬러 올라가지 않는다.
#:
#: 🔴 **여기가 갈렸던 자리다 (2026-08-29).** 종전에는 `repo_root()` 가 이 파일 위치에서
#:    레포 뿌리를 거슬러 올라가 `reports\` 를 만들었다. 그래서 **어느 클론에서 돌렸느냐로
#:    산출 위치가 갈렸다** — 작업장에서 돌리면 작업장 `reports\`, 운영 서버에서 돌리면
#:    운영 서버 `reports\`. 그런데 이 원고를 **소비하는** `publish_threads.py` 는
#:    `HQ = C:\Users\ojaej\jj-company` 로 못박혀 있어 운영 서버만 본다.
#:    `reports\` 는 `.gitignore` 라 `git pull` 로도 안 넘어간다 — **전달 경로가 아예 없었다.**
#:    실제로 ep35~38 원고 4건이 전부 작업장에만 있었고, 워커는 «원고를 못 찾았다» 로 끝났을 것이다.
#:
#: **왜 «복사 단계를 스킬에 박기» 가 아니라 이쪽인가.** 복사 단계는 사람이나 세션이 건너뛸 수
#: 있고, 건너뛰면 **조용히** 어긋난다(파일은 만들어졌고 게이트도 통과하므로 아무도 모른다).
#: 여기를 상수로 못박으면 **어디서 돌리든 한 자리에 떨어져** 건너뛸 단계 자체가 없어진다.
#: 정관 §0 4층 ① 이고, 위 `PUBLISHED` 와 같은 꼴이다. 백로그 15번 «상대 경로» 계열.
REPORTS_DIR = os.environ.get("JJ_REPORTS_DIR", r"C:\Users\ojaej\jj-company\reports")


def find_ep_dir(ep):
    if ep is None:
        raise RuntimeError("--ep 또는 --ep-dir 가 필요하다")
    hits = [d for d in os.listdir(PUBLISHED) if re.match(r"^ep%d(_|$)" % ep, d)]
    if not hits:
        raise RuntimeError("ep%s 폴더를 못 찾았다: %s" % (ep, PUBLISHED))
    return os.path.join(PUBLISHED, sorted(hits)[0])


# ── 편 선언 읽기 ─────────────────────────────────────────────────────────
class _Subst(ast.NodeTransformer):
    """`F.NAME` 같은 **모듈 속성 참조**를 실제 값으로 바꿔 준다.

    🔴 왜 필요한가 (2026-08-28). 빌더가 `"shot": F.VIDEO_SRC` 처럼 `_facts.py` 값을 가리키면
    `ast.literal_eval` 이 통째로 실패한다. 종전 코드는 그 실패를 **조용히 삼켜** `CARDS` 를
    빼먹었고, `load_ep` 이 `or {}` 로 받아 **주장 0건·첨부 0건짜리 지시서**를 정상인 척 냈다
    (ep36 실측 — 영상 카드가 있는 편은 처음부터 이 상태였다). 정관 §0 «조용히 실패하는 코드».
    """

    def __init__(self, tables, local=None):
        self.tables = tables          # {"F": {이름: 값}, ...}
        #: **같은 파일 위쪽에서 이미 값이 정해진 이름**. 빌더가 `"key": "… — %s" % AAI_LABEL`
        #: 처럼 자기 상수를 쓰는 일이 흔하다(ep35 실측) — 그것도 풀어 준다.
        self.local = local if local is not None else {}

    def visit_Attribute(self, node):
        v = node.value
        if isinstance(v, ast.Name) and v.id in self.tables and node.attr in self.tables[v.id]:
            return ast.copy_location(ast.Constant(self.tables[v.id][node.attr]), node)
        return self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id in self.local:
            return ast.copy_location(ast.Constant(self.local[node.id]), node)
        return node

    # 🔴 **아래 둘은 «값을 손으로 적지 않은 편» 을 읽으려고 있다 (2026-08-29).**
    #    ep39 는 예시 개수를 `EXAMPLES_TOTAL = len(EXAMPLES_EN)` 로 **세게** 하고
    #    카드는 `"… %d가지예요." % F.EXAMPLES_TOTAL` 로 받아 썼다 — 손으로 적었다가
    #    18/19 를 틀린 자리를 구조로 닫은 것이다(§0 4층 ①). 그런데 그렇게 하면
    #    `ast.literal_eval` 이 `len(...)` 도 `%` 도 못 읽어 **편 전체를 못 읽는다.**
    #    즉 **빌더가 옳게 쓸수록 이 추출기가 막는** 꼴이었다. 그래서 둘만 접어 준다.
    #    🔴 일반 계산기를 만들지 않는다 — `len` 과 `%` 두 갈래만이다. 넓히면 이 파일이
    #    빌더를 «실행» 하기 시작하고, 실행하지 않는 것이 이 추출기의 존재 이유다.
    def visit_Call(self, node):
        node = self.generic_visit(node)
        # 첫째 갈래: **빌더가 자기 폴더를 가리키는 관용구** (2026-09-11 · ep44 실측).
        # `D = os.path.dirname(os.path.abspath(__file__))` 는 빌더 36개가 전부 쓰는 꼴이고,
        # 그 위에 `EPS = os.path.join(D, "_eps")` · `p(EPS, "x.png")` 로 카드 경로를 만든다.
        # `D` 가 리터럴이 아니라 **ep44 CARDS 가 통째로 안 읽혔다**(주간 편 유통이 여기서 막혔다).
        # 🔴 **절대경로로 풀지 않는다 — 빈 문자열로 접는다.** 이 파이프라인의 카드 경로는
        #    이미 «편 폴더 기준 상대경로»이고(`shots/x.png`), `os.path.join("", "_eps")` 는
        #    `"_eps"` 다 — 다른 편이 손으로 적는 것과 **같은 값**이 된다. 절대경로로 풀면
        #    기계마다 다른 값이 나와 게이트 `[10-1]`·`[10-2]` 의 대조가 어긋난다.
        # 🔴 **이 한 꼴만 이름으로 열거한다** — `__file__` 이 든 다른 조립은 접지 않는다.
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "dirname"
                and len(node.args) == 1 and not node.keywords
                and isinstance(node.args[0], ast.Call)
                and isinstance(node.args[0].func, ast.Attribute)
                and node.args[0].func.attr == "abspath"
                and len(node.args[0].args) == 1
                and isinstance(node.args[0].args[0], ast.Name)
                and node.args[0].args[0].id == "__file__"):
            return ast.copy_location(ast.Constant(""), node)
        if (isinstance(node.func, ast.Name) and node.func.id == "len"
                and len(node.args) == 1 and not node.keywords
                and isinstance(node.args[0], ast.Constant)):
            try:
                return ast.copy_location(ast.Constant(len(node.args[0].value)), node)
            except TypeError:
                return node
        # 셋째 갈래: 경로 조립 (2026-09-02 · ep41/42 실측). 빌더가 카드 shot 을
        # `p("_official", "og_1200.jpg")`(ep42) 나 `os.path.join("_official", …)`(ep41) 로
        # 적기 시작해 CARDS 전체가 안 읽혔다. `p(*a)` 는 빌더 공통 헬퍼로 `os.path.join` 의
        # 별칭이다 — 둘 다 **문자열 상수 인자일 때만** 접는다. len·% 와 같은 꼴로, 인자에
        # 상수 아닌 것(`p(OF, …)` 의 OF 같은 절대경로 변수)이 섞이면 접지 않고 그대로 둔다.
        is_p = isinstance(node.func, ast.Name) and node.func.id == "p"
        is_ospj = (isinstance(node.func, ast.Attribute) and node.func.attr == "join"
                   and isinstance(node.func.value, ast.Attribute)
                   and node.func.value.attr == "path"
                   and isinstance(node.func.value.value, ast.Name)
                   and node.func.value.value.id == "os")
        if ((is_p or is_ospj) and node.args and not node.keywords
                and all(isinstance(a, ast.Constant) and isinstance(a.value, str)
                        for a in node.args)):
            return ast.copy_location(
                ast.Constant(os.path.join(*[a.value for a in node.args])), node)
        # 넷째 갈래: `max`·`min` 의 **상수 인자** (2026-09-10 · ep51 실측). 빌더가 팬 길이를
        # `max(24.566667, 18.466667)` 로 적어 CARDS 전체가 안 읽혔다 — `len` 과 같은 꼴로
        # **인자가 전부 상수 숫자일 때만** 접는다. 값을 손으로 적지 않은 편을 읽으려는 것이지
        # 계산기를 만드는 것이 아니다(위 doctrine 그대로 — 갈래를 이름으로 열거한다).
        if (isinstance(node.func, ast.Name) and node.func.id in ("max", "min")
                and len(node.args) >= 2 and not node.keywords
                and all(isinstance(a, ast.Constant) and isinstance(a.value, (int, float))
                        and not isinstance(a.value, bool) for a in node.args)):
            fn = max if node.func.id == "max" else min
            return ast.copy_location(ast.Constant(fn(*[a.value for a in node.args])), node)
        return node

    def visit_Subscript(self, node):
        """이미 상수로 접힌 dict·list 에서 한 칸 꺼내기 (2026-09-10 · ep51/52/55 실측).

        빌더가 `OFFICIAL_VIDEO["file"]`·`OFFICIAL_CLIPS["03"]["file"]` 로 자기 선언을
        가리키기 시작해 **세 편의 CARDS 가 통째로 안 읽혔다.** 이름 쪽은 `visit_Name` 이
        이미 상수 dict 로 바꿔 주는데 그 다음 칸 꺼내기가 없어 거기서 멈춘 것이다.
        🔴 **계산이 아니라 «선언된 값 읽기»다** — 컨테이너와 키가 **둘 다 상수일 때만** 접고,
        키가 없거나 꼴이 안 맞으면 **그대로 둔다**(조용히 틀린 값을 만들지 않는다).
        """
        node = self.generic_visit(node)
        if not (isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, (dict, list, tuple, str))):
            return node
        sl = node.slice
        if not (isinstance(sl, ast.Constant) and isinstance(sl.value, (str, int))
                and not isinstance(sl.value, bool)):
            return node
        try:
            return ast.copy_location(ast.Constant(node.value.value[sl.value]), node)
        except (KeyError, IndexError, TypeError):
            return node

    def visit_BinOp(self, node):
        node = self.generic_visit(node)
        if not isinstance(node.op, ast.Mod):
            return node
        left = node.left
        if not (isinstance(left, ast.Constant) and isinstance(left.value, str)):
            return node
        if isinstance(node.right, ast.Constant):
            args = node.right.value
        elif (isinstance(node.right, ast.Tuple)
              and all(isinstance(e, ast.Constant) for e in node.right.elts)):
            args = tuple(e.value for e in node.right.elts)
        else:
            return node
        try:
            return ast.copy_location(ast.Constant(left.value % args), node)
        except (TypeError, ValueError):
            return node        # 접지 못하면 그대로 둔다 — 조용히 틀린 값을 만들지 않는다


def _module_literals(path, tables=None):
    """`build_epNN.py` 를 **실행하지 않고** 최상위 리터럴 대입만 뽑는다.

    빌더는 스킬 모듈을 import 하고 경로를 만지므로 import 하면 부작용이 있다.
    `COVER = COVER_A` 처럼 같은 파일 안의 이름을 가리키는 대입은 한 번 더 풀어 준다.
    `tables` 를 주면 `F.VIDEO_SRC` 같은 모듈 속성도 값으로 바꿔 읽는다.
    """
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out, alias = {}, {}
    # `out` 을 그대로 넘긴다 — 위에서 아래로 읽으므로 앞서 정해진 이름은 이미 들어 있다.
    sub = _Subst(tables or {}, out)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        t = node.targets[0]
        if not isinstance(t, ast.Name):
            continue
        try:
            out[t.id] = ast.literal_eval(sub.visit(node.value))
        except (ValueError, SyntaxError, TypeError):
            if isinstance(node.value, ast.Name):
                alias[t.id] = node.value.id
    for k, v in alias.items():
        if v in out:
            out[k] = out[v]
    return out


def publog_post_url(ep_no):
    """발행로그 본 표에서 그 편의 인스타 게시물 URL 을 읽는다 — 킷 없는 편의 마감 URL 정본.

    행 첫 칸이 정확히 `**ep<n>**`/`ep<n>` 인 행만 본다 — `**ep40-Threads**` 같은
    게시물 행이 `startswith` 로 걸려들면 안 된다. 없으면 **소리 내고 죽는다**:
    «로그에 없다» 는 «아직 인스타에 안 나갔다» 이고, 안 나간 편은 재유통할 원류가 없다.
    """
    p = os.path.join(os.path.dirname(PUBLISHED), "발행로그.md")
    key = "ep%s" % ep_no
    for ln in io.open(p, encoding="utf-8").read().split("\n"):
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if not cells or cells[0].strip("*") != key:
            continue
        # 🔴 **릴스는 `/reel/` 이다** (2026-09-11 · ep45·46·47·53 실측). 종전 정규식은 `/p/` 만
        #    봐서 **URL 이 멀쩡히 적혀 있는데 «없다» 고 죽었다** — 릴스 편 넷이 유통에서 통째로
        #    막힌 자리다(발행로그 전수: `/p/` 16건 · `/reel/` 4건). 「원류 없이 재유통하지
        #    않는다」는 조건은 **이미 만족돼 있었고** 검사기가 그 꼴을 몰랐을 뿐이다
        #    (정관 §0 «검사가 틀린 것을 요구하면 산출물보다 검사부터 고친다»).
        m = re.search(r"https://www\.instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?", ln)
        if m:
            return m.group(0)
        raise RuntimeError("발행로그 %s 행에 인스타 게시물 URL 이 없다 — 원류 없이 재유통할 수 없다" % key)
    raise RuntimeError("발행로그 본문에 %s 행이 없다 — 인스타 발행 전에는 재유통하지 않는다" % key)


def load_ep(ep_dir):
    builds = [f for f in os.listdir(ep_dir) if re.match(r"^build_ep\d+\.py$", f)]
    # `_facts.py` 를 먼저 읽어 `F.` 참조를 풀 수 있게 한다 — 안 그러면 영상 카드가 든 편의
    # `CARDS` 가 통째로 안 읽힌다(위 `_Subst` 주석).
    _facts_p = os.path.join(ep_dir, "_facts.py")
    _facts_lit = _module_literals(_facts_p) if os.path.exists(_facts_p) else {}
    _tables = {"F": _facts_lit} if _facts_lit else {}

    # 🔴 **릴스 단독 편은 빌더가 없다** (2026-09-11 · ep45·ep47 실측 · SKILL §6.6 A).
    #    카드가 0장이고 `assemble_reel.py` 하나가 편의 전부라, 종전 코드는 첫 줄에서
    #    「빌더 선언 파일이 없다」로 죽었다 — **릴스 편 넷이 유통에서 통째로 막힌 자리**다.
    #
    #    판별 축은 «빌더 없음» 하나가 아니라 **«빌더 없음 ∧ `assemble_reel.py` 있음»** 둘이다.
    #    하나만 보면 «빌더를 아직 안 만든 제작 중인 편»까지 조용히 통과해 카드 0장짜리
    #    스레드를 내보낸다 — 그것이 종전 `CARDS` 필수 검사가 막던 것이고, 여기서 그 몫을
    #    잃지 않는다. 릴스 편에서 카드 0장은 **결함이 아니라 그 편의 꼴**이다.
    #
    #    선언은 `_facts.py` 가 진다. `assemble_reel.py` 에 적지 않는 이유는 그 파일이
    #    **이미 발행된 편의 산출물**이라서다(정관 §2 — `01_발행완료` 는 못 고친다).
    reel_only = not builds and os.path.exists(os.path.join(ep_dir, "assemble_reel.py"))
    if not builds and not reel_only:
        raise RuntimeError(
            "빌더 선언 파일이 없다: %s — 릴스 단독 편이면 `assemble_reel.py` 가 있어야 한다" % ep_dir)

    if reel_only:
        if not _facts_lit:
            raise RuntimeError(
                "릴스 편에 `_facts.py` 가 없다: %s — 빌더가 없는 편은 선언(EP·KIT·"
                "ATTACH_OFFICIAL·OFFICIAL_VIDEO)을 그 파일이 진다" % ep_dir)
        decl = _facts_lit
    else:
        decl = _module_literals(os.path.join(ep_dir, sorted(builds)[0]), _tables)
        if not decl.get("CARDS"):
            # 🔴 조용히 넘어가지 않는다. 빌더가 있는 편에서 카드 0건은 **읽기 실패**다.
            raise RuntimeError(
                "편 선언에서 CARDS 를 읽지 못했다: %s — 리터럴이 아닌 참조가 들어 있으면 "
                "`_facts.py` 에 올리거나 `_Subst` 에 그 모듈을 더해라" % ep_dir)
    kit = decl.get("KIT") or {}
    if kit and not kit.get("url"):
        raise RuntimeError("편 선언 KIT 에 url 이 없다 — 킷이 있으면 url 을 적고, 킷 없는 편이면 KIT 선언 자체를 빼라")
    post_url = None
    if not kit:
        # 킷 없는 편 규격 (2026-09-02 JJ 확정 · ep40 계기): 마지막 포스트는 킷 대신
        # **원류 안내** — 본편 인스타 게시물 URL 1건으로 닫는다. URL 의 정본은 발행로그다
        # (§0 실물 정본). 로그에 그 편 인스타 URL 이 없으면 여기서 선다 — «인스타 발행 전
        # 재유통 금지» 가 별도 검사 없이 이 정본 선택에서 공짜로 따라온다.
        post_url = publog_post_url(decl.get("EP"))

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
        # v3.56 — «공식» 빈도 검사가 읽는 둘. 선언이 없으면 각각 None·빈 집합이고,
        # `SKILL_VER` 이 없으면 그 검사는 **돌지 않는다**(편 게이트의 since 와 같은 뜻).
        "SKILL_VER": decl.get("SKILL_VER"),
        "OFFICIAL_WORD_EXEMPT": decl.get("OFFICIAL_WORD_EXEMPT") or (),
        # v3.60 `[12]` — 발표 행위 서술의 «주체» 를 편 선언 고유명사로 잡는다.
        # 이것이 없으면 «xAI 가 열었어요» 의 주체를 못 읽어 검사가 조용히 헛돈다.
        "COVER_NOUNS": list(decl.get("COVER_NOUNS") or ()),
        "kit_url": kit.get("url"),          # None = 킷 없는 편 — [4-2] 가 post_url 분기로 간다
        "post_url": post_url,
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

    # 🔴 `_official/` 도 후보로 낸다 (2026-09-10 신설 · ep50·ep54 실측).
    # 종전에는 카드 선언의 `shot` 만 훑어서 **`_official/shots/` 를 한 번도 보지 않았다** —
    # 게이트의 `MEDIA_DIRS` 는 2026-08-29 부터 `_official/` 을 허용하는데 지시서만 몰랐다.
    # 그래서 ep54 브리핑이 「`shots/` 에 공식 원본 캡처가 없다 — 첨부 없이 텍스트로 간다」 를
    # 냈고, 정작 그 편에는 앤트로픽 아티클 Figure 1~7 이 그 폴더에 다 있었다. 같은 날 신설한
    # `[10-0]`(P1 에 공식 미디어 필수)과 부딪혀 **지시서를 그대로 따르면 반드시 FAIL 난다.**
    # §0 4층 ② — 검사로 잡기 전에 생성 단계가 옳은 것을 내게 한다.
    seen = {s["path"] for s in out}
    off = os.path.join(ep["dir"], "_official", "shots")
    for name in sorted(os.listdir(off)) if os.path.isdir(off) else []:
        rel = "_official/shots/" + name
        if rel in seen:
            continue
        p = os.path.join(off, name)
        kind, w, h, dur = distcheck.probe_media(p)
        if kind == "기타":
            continue
        shape = kind + (" %dx%d" % (w, h) if w else "") + (" %gs" % dur if dur is not None else "")
        out.append({"card": "_official", "path": rel, "credit": "", "shape": shape,
                    "headline": "공식 원본 보관 자리 (C-22) — 크레딧·출처키는 검증로그에서"})
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
    a("- 포스트 %d~%d개. 🔴 **P1 하나로 끝내도 된다** — 하한이 1 이다(2026-09-10 개정)."
      % (distcheck.POSTS_MIN, distcheck.POSTS_MAX))
    a("- 포스트당 %d자 이하 (Threads 공표값 — 우리 실측 아님, `유통확장_설계안.md` §3)."
      % distcheck.THREADS_CHAR_MAX)
    if ep["kit_url"]:
        a("- 킷 URL 은 **마지막 포스트에만** 1건: `%s`" % ep["kit_url"])
    else:
        a("- 🔴 **킷 없는 편** — 마지막 포스트는 **원류 안내**로 닫는다: 본편 인스타 게시물 URL"
          " **1건만** `%s` (정본: 발행로그 · 소스 맵 근거 키는 `POST_URL`)" % ep["post_url"])
    a("- 어미는 **해요체**. 자기 언급·제작 과정 서사 0건. 부정 톤 금지.")
    a("- 벤치 수치를 실은 포스트에는 «%s» 라벨을 단다." % distcheck.OFFICIAL_LABEL)
    a("- **인스타 캡션을 복붙하지 않는다** — 같은 사실을 텍스트 매체 문법으로 다시 쓴다.")
    a("  첫 줄이 훅이고, 이미지 없이 읽혀야 한다.")
    a("")
    a("## 🔴 Threads 문법 (실측 · `reports/2026-09-10_threads-benchmark.md`)")
    a("")
    a("2026-09-10 에 잘되는 계정 5곳 15편의 본문을 그대로 옮겨 쟀다. **여섯 가지가 갈랐다.**")
    a("")
    a("1. **P1 은 그 자체로 완결이다.** 상위 포스트는 전부 단일 포스트 179~264자였고,")
    a("   같은 계정 같은 편에서 체인 자식은 **13배** 떨어졌다(부모 67♥ → `1/` 5♥ · `2/` 4♥ · `3/` 3♥).")
    a("   **P2~ 는 «본문의 나머지»가 아니라 «더 볼 사람만» 가는 심화다.** 나눌 이유가 없으면 나누지 않는다.")
    a("2. **첫 줄은 짧고(20~42자) 결론만.** 알맹이는 둘째 문단부터 내린다.")
    a("   우리 옛 원고는 첫 줄 44~84자 = 포스트 전체였다 — 첫 줄에서 끝나 스크롤할 이유가 없었다.")
    a("3. **첫 줄의 주어는 «독자가 무엇을 하게 되는가»다.** 824♥ 짜리 첫 줄에는 제품명이 없다:")
    a("   「Opus급 코딩 에이전트를 이제 무료로 돌릴 수 있습니다」 — 회사·모델명은 둘째 줄에 나온다.")
    a("   아는 것에 빗대는 것도 통한다: 「오디오계의 나노바나나가 등장했습니다」(51♥).")
    a("   🔴 «~가 나왔어요» 로 여는 소식 고지가 우리 옛 원고 4편 전부의 첫 줄이었다.")
    a("4. **수치는 단독이 아니라 «대비»로 준다.** 「출력 가격은 Opus 5의 20분의 1」·")
    a("   「구글이 7.50달러를 받는데 이 모델은 0.28달러」·「7.8%였던 것이 99.9%가 됐고」.")
    a("   비교 대상이 없는 수치는 크고 작음을 알 수 없다.")
    a("5. **마지막 줄은 소감 한 줄.** 「~가는 것 같네요」·「~줄어들 것 같습니다」.")
    a("   인스타 캡션의 «💬 토망치랩 코멘트» 와 같은 자리인데 옛 Threads 원고에는 0건이었다.")
    a("6. **해시태그·팔로우 요청 0개.** 표본 상위 포스트에 하나도 없었다.")
    a("   CTA 자리는 «예고» 가 대신한다 — 「왜 이런 물건을 공짜로 주는지부터 정리했습니다」(824♥).")
    a("")
    a("**문체는 축이 아니다** — 합니다체·반말·개조식(`-음`)이 전부 상위에 있었다. 우리 해요체는 그대로 간다.")
    a("")
    a("🔴 **게이트는 이 중 넷을 «경고» 로만 재다 (2026-09-11).** "
      "`[3-3a/b]` 1번(P1 완결) · `[2-1]` 3번(첫 줄 주어) · "
      "`[5-4]` 4번(수치 비교쌍) · `[3-3c]` 5번(마지막 줄 소감).")
    a("🔴 **경고는 발행을 막지 않는다** — `gate_failed` 에 "
      "들어가지 않으므로 경고만 있으면 팩은 그대로 나온다. "
      "판정으로 두지 않은 이유는 **예외가 실재하기 때문**이다 — "
      "표본 1위 포스트가 제품명으로 열었다.")
    a("2번(첫 줄 길이)와 6번(해시태그 0)는 이미 "
      "`[3-2]`·`[4-1]` 이 근처에서 재고 있다.")
    a("🔴 **그래도 진짜 자리는 이 지시서다**(정관 §0 4층 — "
      "② 생성이 ③ 검사보다 앞이다). 경고는 «지시서가 먹인 것이 "
      "원고에서 빠졌을 때 보이게» 하는 몫만 한다.")
    a("🔴 **여전히 못 재는 것**: 넷 다 어휘·길이 목록이라 "
      "**바닥선**이다. 새 표현으로 같은 일을 하면 못 잡고, "
      "«그래서 읽힐 글인가» 는 어느 축도 재지 않는다.")
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
    # §0 이 Threads 를 승인 장치와 함께 열었고(2026-08-28), 2026-09-10 에 JJ 지시로
    # **그 승인 장치를 폐기**했다 — 이 파일이 실재한다는 것이 곧 «게이트 통과» 다
    # (`pack()` 은 FAIL 이 하나라도 있으면 아무것도 쓰지 않는다). 워커는 첨부를 싣는다.
    a("> 발행은 게이트 통과가 자격이다 — 이 파일이 있다는 것이 그 증거다(FAIL 이면 안 써진다).")
    a("> 워커(`publish_threads.py --publish`)가 올린다. 사이드카 해시가 이 원고와 다르면 선다.")
    a("> 🔴 **첨부에 공개 URL·sha256 이 없는 편은 워커가 멈춘다** — 그 편은 사람이 올린다.")
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
            line = ("**첨부** `%s` — %s · 크레딧 `%s` · %s"
                    % (os.path.join(ep["dir"], m["path"].replace("/", os.sep)),
                       m["shape"], m["credit"], m["tier"]))
            if m.get("url"):
                # 발행용 공개 URL + **그 URL 바이트**의 sha256 — 워커가 발행 직전 URL 을
                # 다시 받아 이 값과 대조한다. 해시는 기계가 센다(사람이 옮겨 적는 값이 아니다).
                #
                # 🔴 **로컬 파일이 아니라 URL 을 잰다 (2026-09-10 개정).** 나가는 것은
                #    URL 바이트다. 종전에는 로컬 검증본을 쟀는데, 실측(ep51)에서 같은
                #    X 원본이 원격 20,965,746 · 로컬 20,959,125 로 달랐다 — 우리 로컬본은
                #    yt-dlp 재먹싱분이다. 그 기준으로는 **통과할 수 있는 조합이 없었다.**
                #    URL 이 열리는지·그 바이트 형상이 선언과 맞는지는 게이트 `[10-8]` 이
                #    이미 봤고(같은 회차·같은 캐시), 여기서는 그 바이트의 해시만 박는다.
                import hashlib as _hl
                _blob, _err = distcheck.fetch_url_bytes(m["url"])
                if _blob is None:
                    # 게이트를 통과했는데 여기서 못 받는 경우는 «그 사이에 죽었다» 뿐이다.
                    # 조용히 URL 없는 줄로 떨어뜨리지 않는다 — 그러면 워커가 텍스트만 올린다.
                    raise SystemExit("🔴 발행 URL 을 못 받았다 (P%d · %s): %s"
                                     % (m["post"], m["url"], _err))
                _sha = _hl.sha256(_blob).hexdigest()
                line += " · URL %s · sha256 %s" % (m["url"], _sha)
            a(line)
        if by_post.get(i):
            a("")
    a("## 게이트")
    a("")
    # 🔴 **검사 판본은 여기 적지 않는다** (2026-08-29 · C-32 판정 ①).
    #    원고는 승인 해시의 대상이고, 판본은 **배포할 때마다 바뀐다** — 내용이 한 글자도
    #    안 바뀌었는데 서명이 낡는다(실측: 포스트 5건 해시는 같고 본문 해시만 달랐다).
    #    같은 값을 원고 옆 사이드카에 쓰고, 승인 초안이 그것을 메타 필드로 싣는다.
    a("")
    for label, verdict, detail in gate.items:
        a("- `%s` %s%s" % ({"OK": " OK ", "FAIL": "FAIL", "NA": " -- ",
                            "WARN": "WARN"}[verdict], label,
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
def _subst_selftest():
    """`_module_literals` 추출 갈래의 역검증 — 걸리는 쪽과 **안 걸리는 쪽**을 같이 본다.

    이 추출기는 **빌더를 실행하지 않고** 최상위 리터럴만 뽑는 것이 존재 이유다. 갈래를 넓힐
    때마다 «계산기가 되는 쪽»으로 한 걸음씩 가므로, 넓힌 갈래가 **그 꼴만** 접는지 매번 잰다.
    🔴 2026-09-11 까지 이 자리에 역검증이 **0건**이었다 — len·%·`p()`·max/min·Subscript 가
    전부 실측 사고를 보고 붙었는데 «그 갈래가 제 몫만 하는지» 를 잰 적이 없다(정관 §0).
    """
    import tempfile
    bad = 0

    def measure(src, name):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "build_ep99.py")
            io.open(f, "w", encoding="utf-8").write(src)
            return _module_literals(f).get(name, "<없음>")

    cases = [
        # (이름, 소스, 기대값, 왜)
        ("D 관용구는 «빈 문자열»로 접힌다 (ep44 · 빌더 36개 공통)",
         "import os\nD = os.path.dirname(os.path.abspath(__file__))\nX = D\n", "X", ""),
        ("그 위에 쌓은 `os.path.join(D, …)` 도 상대경로로 접힌다",
         "import os\nD = os.path.dirname(os.path.abspath(__file__))\n"
         "EPS = os.path.join(D, '_eps')\n", "EPS", "_eps"),
        ("`p(EPS, '<파일>')` 이 다른 편과 **같은 상대경로**가 된다",
         "import os\nD = os.path.dirname(os.path.abspath(__file__))\n"
         "EPS = os.path.join(D, '_eps')\n"
         "def p(*a):\n    return os.path.join(*a)\nS = p(EPS, 'a.png')\n",
         "S", os.path.join("_eps", "a.png")),
        # 🔴 **반대쪽** — `__file__` 이 들었다고 다 접지 않는다. 이 케이스가 없으면
        #    «전부 접는» 추출기도 위 셋을 통과시킨다.
        ("`os.path.abspath(__file__)` 만 쓴 것은 **안 접는다** (그 꼴이 아니다)",
         "import os\nX = os.path.abspath(__file__)\n", "X", "<없음>"),
        ("`os.path.dirname(어떤 변수)` 도 **안 접는다**",
         "import os\nY = 'x'\nX = os.path.dirname(Y)\n", "X", "<없음>"),
        # 앞서 붙은 갈래들의 바닥선 — 넓히다 옛 갈래를 깨면 여기서 선다.
        ("`len(상수)` 갈래", "X = len('abcd')\n", "X", 4),
        ("`%` 갈래", "N = 3\nX = '%d개' % 3\n", "X", "3개"),
        ("`max(상수, 상수)` 갈래", "X = max(1.5, 2.5)\n", "X", 2.5),
        ("Subscript 갈래", "V = {'file': 'a.mp4'}\nX = V['file']\n", "X", "a.mp4"),
        ("키가 없으면 **안 접는다**", "V = {'file': 'a.mp4'}\nX = V['nope']\n", "X", "<없음>"),
    ]
    # 발행로그 URL 꼴 — 게시물과 **릴스** 둘 다 읽는가. 릴스 넷이 여기서 막혔었다.
    _u = re.compile(r"https://www\.instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?")
    for label, ln, want in [
        ("발행로그 URL — 게시물 `/p/`", "| **ep55** | x | https://www.instagram.com/p/Dc8faxakrTb/ |", True),
        ("발행로그 URL — **릴스 `/reel/`** (ep45~47·53 이 막혔던 자리)",
         "| **ep45** | x | https://www.instagram.com/reel/Dc-bY92o_OG |", True),
        ("남의 도메인은 **안 읽는다**", "| x | https://www.facebook.com/reel/abc |", False),
    ]:
        got = bool(_u.search(ln))
        print("[ %s ] %s" % ("  OK  " if got == want else " FAIL ", label))
        bad += 0 if got == want else 1
    for label, src, name, want in cases:
        got = measure(src, name)
        okc = got == want
        print("[ %s ] %s" % ("  OK  " if okc else " FAIL ", label),
              "" if okc else "— 기대 %r · 실제 %r" % (want, got))
        bad += 0 if okc else 1
    # --- 릴스 단독 편 판별 (2026-09-11) ------------------------------------
    #
    # 판별 축이 **둘**이라는 것이 이 묶음의 전부다. «빌더 없음» 하나만 보면
    # 「빌더를 아직 안 만든 제작 중인 편」까지 카드 0장으로 통과한다 — 종전 `CARDS`
    # 필수 검사가 막던 그것이다. 그래서 통과해야 하는 쪽과 **거부해야 하는 쪽**을
    # 같이 잰다(정관 §0 — 한쪽만 보면 전부 거부하는 코드도 정상으로 보인다).
    for label, files, want in [
        ("릴스 편(빌더 없음 + assemble_reel.py + _facts.py)은 읽힌다",
         {"assemble_reel.py": "", "_facts.py": "EP = 45\nCARDS = {}\n"}, "ok"),
        ("빌더가 있으면 종전 그대로 — CARDS 0장은 읽기 실패",
         {"build_ep99.py": "CARDS = {}\n"}, "raise"),
        ("빌더도 assemble_reel.py 도 없으면 거부",
         {"_facts.py": "EP = 99\n"}, "raise"),
        ("릴스 편인데 _facts.py 가 없으면 거부 (선언이 그 파일에 있다)",
         {"assemble_reel.py": ""}, "raise"),
    ]:
        with tempfile.TemporaryDirectory() as d:
            for n, body in files.items():
                io.open(os.path.join(d, n), "w", encoding="utf-8").write(body)
            try:
                load_ep(d)
                got = "ok"
            except RuntimeError:
                got = "raise"
            except Exception as e:                       # noqa: BLE001
                got = "other:%s" % type(e).__name__
        okc = got == want
        print("[ %s ] %s" % ("  OK  " if okc else " FAIL ", label),
              "" if okc else "— 기대 %r · 실제 %r" % (want, got))
        bad += 0 if okc else 1

    print("STATUS: %s" % ("OK" if not bad else "FAIL %d건" % bad))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description="유통 변환 워커 (Threads 텍스트 스레드)")
    ap.add_argument("cmd", choices=["brief", "pack", "selftest"])
    ap.add_argument("--ep", type=int)
    ap.add_argument("--ep-dir")
    ap.add_argument("--draft")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    if a.cmd == "selftest":
        return 1 if _subst_selftest() else 0

    ep = load_ep(a.ep_dir or find_ep_dir(a.ep))
    today = datetime.date.today().isoformat()
    outdir = REPORTS_DIR
    if not os.path.isdir(outdir):
        # 조용히 만들지 않는다 — 자리가 없다는 것은 «운영 서버가 없다» 는 뜻이고,
        # 그 상태로 원고를 쓰면 워커가 못 찾을 곳에 쓰는 것이다(§0 «조용히 실패하지 않는다»).
        raise SystemExit("🔴 원고 자리가 없다: %s — 운영 서버 경로를 확인하라" % outdir)

    if a.cmd == "brief":
        out = a.out or os.path.join(outdir, "%s_dist_ep%s.brief.md" % (today, ep["EP"]))
        write_utf8(out, brief(ep))
        print("작업 지시서: %s" % out)
        return 0

    if not a.draft:
        ap.error("pack 에는 --draft 가 필요하다")
    a_draft = a.draft
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
    # 판본 기록은 **원고 밖**에 남긴다 (C-32 ①). 없애는 것이 아니라 자리를 옮기는 것이다.
    #
    # 🔴 **사이드카가 발행 자격의 증적이다 (2026-09-10 · 승인 파일 폐기).** 종전에는 JJ 가
    #    옮긴 `publish_approval\<ep>.json` 이 트리거였고 그 파일이 원고 해시를 들고 있었다.
    #    그 자리를 없앴으므로 **여기서 지금 쓴 파일의 해시를 박는다** — 워커는 발행 직전
    #    원고를 다시 해싱해 이 값과 견주고, 다르면 «게이트 뒤에 손댄 원고» 로 보고 선다.
    #    `gate_failed` 는 0 만 나온다(FAIL 이면 위에서 이미 돌아갔다). 그래도 **적는다** —
    #    워커가 «0인지» 를 재게 해야 축이 실재하고, 옛 판 사이드카와도 구별된다.
    import hashlib as _hl
    import json as _json
    _sha = _hl.sha256(io.open(out, "rb").read()).hexdigest()
    write_utf8(out + ".meta.json", _json.dumps(
        {"gate_skill_revision": distcheck.skill_revision(),
         "gate_failed": len(gate.failed),
         "body_sha256": _sha,
         # 🔴 **회귀 기준선** (2026-09-10 신설 · JJ 지시 «다신 일어나지 않도록»).
         # `body_sha256` 은 **팩 결과물**의 해시라 «어떤 원고가 통과했는가» 를 못 가리킨다.
         # 게이트를 고쳤을 때 «이미 통과한 편이 지금도 통과하는가» 를 재려면 **그때 돈 원고
         # 바이트**가 있어야 한다 — `distcheck --regress` 가 이 값을 기준선으로 쓴다.
         "draft_sha256": _hl.sha256(io.open(a_draft, "rb").read()).hexdigest(),
         "draft_path": os.path.basename(a_draft),
         "packed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
         "_왜_여기_있나": ("발행 자격의 증적이다 — 워커가 `body_sha256` 을 지금 원고와 "
                      "대조하고 `gate_failed` 가 0인지 본다. 판본을 원고 안에 두지 "
                      "않는 이유는 clause-backlog C-32 ①. `draft_sha256` 은 그와 "
                      "다른 일을 한다 — 게이트 회귀 검사의 기준선이다.")},
        ensure_ascii=False, indent=2))
    print("복붙 세트: %s" % out)
    print("검사 판본: %s (원고 밖 · %s)"
          % (distcheck.skill_revision(), os.path.basename(out) + ".meta.json"))
    print("자격 증적: body_sha256 %s… · gate_failed %d" % (_sha[:12], len(gate.failed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
