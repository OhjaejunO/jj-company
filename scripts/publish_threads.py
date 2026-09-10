# -*- coding: utf-8 -*-
r"""Threads 발행 워커 — 게이트를 통과한 편 1건의 텍스트 스레드를 체인 순서대로 올린다.

정본 명세: `docs\workers\publish-threads.md`. **그 문서가 규칙이고 이 파일은 그 실행체다.**

    py scripts\publish_threads.py --ep ep39                     ← 드라이런 (기본값)
    py scripts\publish_threads.py --ep ep39 --publish           ← 실제 게시
    py scripts\publish_threads.py --self-test                   ← 검사기 자체 시험

## 🔴 발행 자격 (2026-09-10 개정 — 승인 파일 장치는 폐기했다)

종전에는 `publish_approval\<ep>.json` 이 트리거였고 JJ 가 그 파일을 옮기는 것이 서명이었다.
JJ 지시로 그 자리를 없앴다. 남은 자격은 **둘 다 기계가 재는 것**이다:

    ① **복붙 세트가 실재할 것** — `dist_transform.pack()` 은 게이트 FAIL 이 하나라도 있으면
       파일을 **쓰지 않는다.** 그래서 `reports\<날짜>_dist_<ep>.md` 의 존재 자체가 «게이트 통과» 다.
    ② **그 원고가 게이트를 돈 그 바이트일 것** — 사이드카 `<원고>.meta.json` 의 `body_sha256` 이
       지금 원고 파일의 sha256 과 같아야 한다. 게이트 뒤에 한 글자라도 손대면 여기서 선다.

사이드카가 없거나·해시가 갈리거나·`gate_failed` 가 0이 아니면 **게시하지 않는다.**

## 왜 에이전트가 아니라 스크립트인가

원고가 정해지면 **남은 일에 판단이 없다** — 해시를 맞추고, 컨테이너를 만들고,
`FINISHED` 를 기다리고, 순서대로 올린다. 정답이 있는 자리에 모델을 넣지 않는다
(정관 §0 · `skill-drift-audit` 과 같은 성격). 모델이 끼면 «원고를 조금 고쳐서 올리는» 길이 생긴다.

## 🔴 기본값이 드라이런이다 (§0 4층 ①)

`--publish` 를 **명시하지 않으면 어떤 경우에도 게시하지 않는다.** 금지를 규율이 아니라
기본값으로 옮긴 것이다 — 실수로 돌려도 바깥으로 나가지 않는다.

## 🔴 이 스크립트가 증명하지 *못* 하는 것 (§0 4층 ④)

- **원고가 «좋은 글인가» 는 재지 않는다.** 재는 것은 게이트 축 목록뿐이고, 그 밖의 것은
  발행 뒤 사람이 본다. 승인 장치를 뺀 대가가 정확히 이것이다 — 되돌림 비용이 낮아서
  치를 수 있는 대가라고 §0 으로 판정했다(텍스트 포스트는 삭제로 되돌아간다).
- **컨테이너가 실제로 만료돼 사라지는지 확인할 수 없다** — API 가 만료 시각을 내주지 않는다.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://graph.threads.net"
API = "/v1.0"

#: 🔴 **HQ 는 절대경로로 박는다 (2026-08-28 · 상대 계산 폐기).**
#:
#: 종전에는 `os.path.dirname(os.path.dirname(__file__))` 로 잡았다. 그러면 **같은 코드가
#: 어디 놓이느냐에 따라 다른 폴더를 본다** — 운영 서버 사본과 작업장 사본이 각각 제 옆의
#: `reports\` 를 봤다. 둘 다 실재하는 사본이고, 원고가 어느 쪽에 있는지가 갈렸다.
#: 워커가 읽는 원고 자리는 **운영 서버 하나**여야 한다 (`dist_transform` 도 거기에 쓴다).
HQ = r"C:\Users\ojaej\jj-company"
REPORTS_DIR = os.path.join(HQ, "reports")

#: 🔴 publish 는 **경로의 마지막 세그먼트 일치**로만 판정한다 (C-8 2026-08-28 사례).
#: «문자열 포함» 으로 짰다가 `threads_publishing_limit`(쿼터 조회)까지 막혀 조사 한 항목이
#: «확인 불가» 로 끝날 뻔했다. 넓게 잡힌 금지는 조사를 막고, 막힌 자리가 «불가능» 으로 오독된다.
PUBLISH_SEGMENTS = {"threads_publish"}

#: `FINISHED` 대기 상한 — **잠정값이다.** 조사 회차 표본이 2건뿐이라 «정상값» 을 모른다.
#: 실제 회차 로그가 쌓이면 그것으로 조인다(명세 «status 대기» 절).
RECEIPT_DIR = os.path.join(HQ, "logs", "publish-receipts")
#: 무기록 종료를 바깥에서 보게 하는 스탬프. `run_audit.py` 의 STARTED_RESIDUAL 과 같은 꼴이다.
STAMP_PATH = os.path.join(HQ, "logs", "publish-threads.started")
#: 실물 조회 창. 체인이 5포스트라 넉넉하다 — 창이 꽉 차면 «덮는지» 를 따로 본다.
LIVE_FETCH_LIMIT = 25

WAIT_TIMEOUT_S = 180
WAIT_INTERVAL_S = 3

POST_HEAD = re.compile(r"^###\s+P(\d+)\s+—", re.M)

#: 원고의 첨부 선언 줄. `dist_transform.pack()` 이 **코드펜스 밖**에 이 꼴로 쓴다.
#: 🔴 `parse_posts` 는 펜스 안만 읽으므로 이 줄은 발행 경로에 **한 번도 닿지 않았다** —
#:    ep39(2026-08-30)에서 영상 2건이 아무 소리 없이 사라진 것이 그 결과다.
ATTACH_HEAD = re.compile(r"^\s*\*\*첨부\*\*\s*(.*)$", re.M)


# ---------------------------------------------------------------- 토큰·전송
def load_token():
    """환경변수 우선, 없으면 HKCU\\Environment. **값은 어디에도 찍지 않는다.**"""
    t = os.environ.get("THREADS_TOKEN")
    if not t:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            t = winreg.QueryValueEx(k, "THREADS_TOKEN")[0]
    t = (t or "").strip()
    if not t:
        raise SystemExit("🔴 THREADS_TOKEN 이 없다")
    if t.startswith("<") and t.endswith(">"):
        raise SystemExit("🔴 THREADS_TOKEN 이 자리표시자다 — 실제 토큰으로 채울 것")
    return t


def last_segment(path):
    return urllib.parse.urlparse(path).path.rstrip("/").rsplit("/", 1)[-1]


def is_publish_path(path):
    return last_segment(path) in PUBLISH_SEGMENTS


class Api(object):
    def __init__(self, token, allow_publish):
        self.token = token
        self.allow_publish = allow_publish
        self.calls = []

    def scrub(self, s):
        s = str(s)
        if self.token and self.token in s:
            s = s.replace(self.token, "<TOKEN>")
        return s

    def call(self, method, path, params=None):
        if is_publish_path(path) and not self.allow_publish:
            raise Blocked("드라이런: publish 를 부르지 않는다 (%s)" % path)
        url, data = BASE + path, None
        if method == "POST":
            data = urllib.parse.urlencode(params or {}).encode("utf-8")
        elif params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token)
        self.calls.append("%s %s" % (method, path))
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                b = r.read().decode("utf-8", "replace")
                return r.status, (json.loads(b) if b.strip().startswith(("{", "[")) else b)
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(b)
            except ValueError:
                return e.code, {"raw": b}
        except Exception as e:  # noqa: BLE001
            return -1, {"transport_error": str(e)}


class Blocked(Exception):
    """드라이런에서 publish 를 막았을 때. 실패가 아니라 «여기까지» 라는 뜻이다."""


# ---------------------------------------------------------------- 원고·승인
def sha256_file(path):
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()


def sha256_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def parse_posts(md_path):
    """원고에서 포스트 본문을 뽑는다 — `### P<n> — …` 다음의 첫 코드펜스.

    `dist_transform.pack()` 이 그 꼴로 쓴다. 형식이 어긋나면 **조용히 건너뛰지 않고 죽는다** —
    포스트 하나를 놓친 채 스레드를 올리면 바깥에 반쪽이 남는다(§0).
    """
    text = io.open(md_path, encoding="utf-8").read()
    heads = list(POST_HEAD.finditer(text))
    if not heads:
        raise SystemExit("🔴 원고에서 `### P<n>` 블록을 못 찾았다 — %s" % md_path)
    out = {}
    for i, m in enumerate(heads):
        seq = int(m.group(1))
        seg = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        fence = re.search(r"```\s*\n(.*?)\n```", seg, re.S)
        if not fence:
            raise SystemExit("🔴 P%d 본문 코드펜스가 없다 — %s" % (seq, md_path))
        if seq in out:
            raise SystemExit("🔴 P%d 가 두 번 나온다 — %s" % (seq, md_path))
        out[seq] = fence.group(1).strip()
    return out


def media_support_state(src=None):
    """이 워커가 **실제로** 미디어를 실을 수 있는가 — 소스를 읽어 판정한다.

    컨테이너 파라미터의 ``media_type`` 값이 전부 리터럴 ``"TEXT"`` 면 실을 길이 없다.
    돌려주는 값은 셋이다. `None` 을 «못 싣는다» 로 뭉개지 않는다 — «못 싣는다» 와
    «모르겠다» 는 다른 사실이고, 둘을 합치면 리팩터로 배정 자리가 사라진 날 가드가
    «확실히 못 싣는다» 고 거짓 보고한다(§0).

      · ``False`` — 배정이 전부 리터럴 ``TEXT``. **미디어를 실을 길이 없다.**
      · ``True``  — 리터럴 ``TEXT`` 가 아닌 값이 섞였다. 미디어 경로가 생겼다.
      · ``None``  — 배정을 못 찾았다. **판정 불가.**

    🔴 **`ast` 로 읽는다. 정규식이 아니다.** 정규식 판은 이 파일 안의 **시험 픽스처
       문자열**까지 세어 «지원한다» 로 읽었다(자체 검사가 잡았다). `ast` 는 주석·
       독스트링·문자열 리터럴을 안 보므로 **가짜가 표를 던질 수 없다.**
    """
    import ast as _ast
    if src is None:
        src = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    try:
        tree = _ast.parse(src)
    except SyntaxError:
        return None
    vals = set()
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if not (isinstance(k, _ast.Constant) and k.value == "media_type"):
                continue
            vals.add(v.value if isinstance(v, _ast.Constant) else "<비리터럴>")
    if not vals:
        return None
    return vals != {"TEXT"}


#: 첨부 줄의 발행 메타 (2026-09-02 미디어 지원). `dist_transform.pack()` 이
#: `· URL <공개주소> · sha256 <64hex>` 를 덧붙인다 — URL 은 Threads 가 받아갈 곳이고
#: sha256 은 **게이트가 검증한 로컬 파일**의 지문이다. 발행 직전 URL 을 다시 받아 대조한다.
ATTACH_META = re.compile(r"·\s*URL\s+(\S+)\s+·\s*sha256\s+([0-9a-f]{64})")
#: 형상 낱말 → Threads media_type. 이 둘 밖(«알 수 없음» 등)은 지원 안 함으로 막는다.
ATTACH_KIND = {"영상": "VIDEO", "이미지": "IMAGE"}


def parse_attachments(md_path):
    """seq → 첨부 발행 명세 {kind, url, sha256} · 못 읽는 선언은 값이 None.

    None 을 조용히 버리지 않는다 — «첨부가 없다» 와 «첨부를 못 읽었다» 는 다른 사실이고,
    뒤쪽은 `attachment_block` 이 발행을 멈추는 근거가 된다(§0).
    한 포스트에 첨부가 둘 이상이면 역시 None — 이 워커는 포스트당 1건만 싣는다.
    """
    out = {}
    for seq, line in attachment_decls(md_path):
        if seq is None:
            continue
        if seq in out:                      # 둘째 선언 — 포스트당 1건 규격 밖
            out[seq] = None
            continue
        m = ATTACH_META.search(line)
        kind = next((v for k, v in ATTACH_KIND.items() if ("— " + k) in line), None)
        out[seq] = ({"kind": kind, "url": m.group(1), "sha256": m.group(2)}
                    if (m and kind) else None)
    return out


def fetch_sha256(url, timeout=120):
    """URL 바이트의 sha256. 못 받으면 (None, 사유) — 확인 불가는 통과가 아니다."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return hashlib.sha256(r.read()).hexdigest(), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:120]


def attachment_decls(md_path):
    """원고가 선언한 첨부 — ``[(seq, 줄), …]``. 없으면 빈 목록.

    포스트 머리(``### P<n>``)로 구간을 갈라 **어느 포스트의 첨부인지**까지 남긴다.
    개수만 세면 «몇 건 빠졌다» 는 알아도 «어디가» 를 못 적는다.
    """
    text = io.open(md_path, encoding="utf-8").read()
    heads = list(POST_HEAD.finditer(text))
    out = []
    for m in ATTACH_HEAD.finditer(text):
        seq = None
        for h in heads:
            if h.start() < m.start():
                seq = int(h.group(1))
            else:
                break
        out.append((seq, m.group(0).strip()))
    return out


#: `attachment_block(support=...)` 의 «안 줬음» 표시. `None` 을 기본값으로 두면
#: **«판정 불가»(None) 를 시험에서 넣을 방법이 없어진다** — 두 뜻이 한 값에 겹친다.
_AUTO = object()


def attachment_block(md_path, support=_AUTO):
    """발행을 멈춰야 하면 사유 줄 목록, 아니면 빈 목록.

    판정은 **양쪽이 다 있어야** 선다 — 첨부 선언이 있고, 그것을 실을 길이 없을 때.
    선언이 0건이면 지원 여부와 무관하게 통과다(옛 편이 새로 걸리지 않는다).

    `support` 를 안 주면 소스에서 읽는다. `None` 은 **«판정 불가»** 라는 값이고,
    판정 불가는 통과가 아니다 — **모르면 멈춘다.**
    """
    decls = attachment_decls(md_path)
    if not decls:
        return []
    if support is _AUTO:
        support = media_support_state()
    if support is not True:
        why = ("이 워커는 미디어를 싣지 못한다 (컨테이너 `media_type` 이 리터럴 TEXT 뿐)"
               if support is False else
               "미디어 지원 여부를 **판정하지 못했다** (`media_type` 배정을 소스에서 못 찾았다)")
        lines = ["원고가 첨부 %d건을 선언했는데 %s" % (len(decls), why)]
        for seq, ln in decls:
            lines.append("  P%s — %s" % (seq if seq is not None else "?", ln))
        return lines
    # 지원해도 **명세가 온전해야** 간다 (2026-09-02) — URL·sha256·형상(영상/이미지)이
    # 다 있고 포스트당 1건일 것. 하나라도 비면 «조용히 텍스트만 올리는» 옛 사고(ep39
    # 영상 소실)로 돌아가므로 발행을 멈춘다.
    atts = parse_attachments(md_path)
    bad = ["P%s — 첨부 명세를 못 읽었다 (URL·sha256·형상 확인)" % s
           for s, v in sorted(atts.items()) if v is None]
    return (["첨부 %d건 중 명세 불완전 %d건:" % (len(decls), len(bad))] + ["  " + b for b in bad]) if bad else []


def build_plan(ep, ms_path, posts):
    """발행 계획을 **원고에서** 만든다 (2026-09-10 · 종전 `build_draft` 의 자리).

    종전에는 이것이 «승인 초안» 이었고 JJ 가 옮겨 서명했다. 승인 장치를 폐기했으므로
    같은 값을 **회차 시작 시점의 스냅샷**으로만 쓴다 — 체인 순서·포스트별 해시·첨부 서명.
    `run_chain` 이 묶음마다 원고를 다시 읽어 이 스냅샷과 견주므로, **도는 도중에 원고가
    바뀌면 거기서 선다.** 그 축은 승인이 사라져도 값을 잃지 않는다(오히려 유일하게 남는다).
    """
    # 🔴 판본은 **메타 필드**다 — 해시 대상이 아니다 (C-32 ①). 기록은 남기되 무결성
    #    판정에는 넣지 않는다. 사이드카가 없으면 «미상» 으로 적는다(조용히 빼지 않는다).
    _rev = (read_sidecar(ms_path) or {}).get("gate_skill_revision") or "미상 (사이드카 없음)"
    return {
        "ep": ep,
        "gate_skill_revision": _rev,
        "body_sha256": sha256_file(ms_path),
        "posts": [{"seq": s, "sha256": sha256_text(posts[s])} for s in sorted(posts)],
        # 미디어도 스냅샷에 넣는다 (2026-09-02). URL 과 그 바이트의 sha256 이 여기 박히고,
        # 워커는 발행 직전 URL 을 다시 받아 이 값과 대조한다 — 회차 도중 CDN 내용이
        # 갈리면 발행이 서지 않는다. 첨부 없는 편은 빈 목록이다.
        "attachments": [dict(seq=s, media_type=v["kind"], url=v["url"], sha256=v["sha256"])
                        for s, v in sorted(parse_attachments(ms_path).items()) if v],
        "chain": sorted(posts),
        "planned_by": "publish_threads.py",
        "planned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "manuscript": os.path.basename(ms_path),
    }


def read_sidecar(ms_path):
    """`<원고>.meta.json` 을 읽는다. 없거나 못 읽으면 `None` — «비었다» 와 구별한다."""
    p = ms_path + ".meta.json"
    if not os.path.exists(p):
        return None
    try:
        d = json.loads(io.open(p, encoding="utf-8").read())
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def check_gate(ms_path):
    """🔴 **발행 자격** — 승인 파일을 대신한 자리다 (2026-09-10).

    어긋난 사유 목록을 돌려준다(빈 목록이면 통과). 재는 것은 셋이다:
      ① 사이드카가 있는가 — `pack()` 이 원고와 **같이** 쓰므로 없으면 게이트를 안 돈 원고다
      ② `gate_failed` 가 0인가 — 사이드카가 그 회차의 판정을 싣는다
      ③ `body_sha256` 이 지금 원고 파일과 같은가 — 게이트 뒤에 손댄 원고를 막는다

    🔴 ③ 이 이 장치의 중심이다. ①·② 만 보면 «게이트를 통과한 적 있는 원고» 까지만 알고,
       **지금 올릴 바이트가 그것인지**는 모른다 — 승인 파일이 하던 일이 정확히 그 대조였다.
    """
    bad = []
    meta = read_sidecar(ms_path)
    if meta is None:
        bad.append("gate-evidence-missing: 사이드카가 없거나 못 읽었다 (%s)"
                   % os.path.basename(ms_path + ".meta.json"))
        return bad
    nf = meta.get("gate_failed")
    if nf is None:
        bad.append("gate-unknown: 사이드카에 `gate_failed` 가 없다 — 옛 판 `pack()` 이 쓴 것이다")
    elif nf:
        bad.append("gate-failed: 게이트 FAIL %s건" % nf)
    want = meta.get("body_sha256")
    got = sha256_file(ms_path)
    if not want:
        bad.append("gate-unknown: 사이드카에 `body_sha256` 이 없다 — 옛 판 `pack()` 이 쓴 것이다")
    elif want != got:
        bad.append("manuscript-changed: 게이트 이후 원고가 바뀌었다 (사이드카 %s… / 실물 %s…)"
                   % (str(want)[:12], got[:12]))
    return bad


# ---------------------------------------------------------------- 영수증·재기동 조정
#
# 🔴 **왜 필요한가.** 체인은 5포스트가 몇 십 초에 걸쳐 나간다. 3번까지 나가고 죽으면
#    그 사실이 **아무 데도 남지 않았다** — `done` 은 메모리 목록이고, 파일 쓰기는 회차
#    맨 끝의 리포트 한 번뿐이었다. 그 상태로 다시 켜면 `run_chain` 이 `chain[0]` 부터
#    `parent=None` 으로 시작하므로 **1번을 다시 올리고 새 스레드를 하나 더 만든다.**
#    바깥에 반쪽짜리 스레드가 둘 남는다(§0 «조용히 실패하는 코드»).
#
# 남기는 방식은 **2단계**다. 발행 «전» 에 선점(claim)을, 발행 «후» 에 영수증(receipt)을 적는다.
# 한 줄로 하면 어느 쪽이든 창이 열린다 — 발행 전에만 적으면 «적었는데 안 나간» 경우를,
# 발행 후에만 적으면 «나갔는데 못 적은» 경우를 구별할 수 없다. 두 줄이면 그 사이에서 죽어도
# **«나갔는지 모르겠다»는 상태로 정확히 남고**, 그때는 실물을 조회해 가린다.


def receipt_path(ep, base=None):
    return os.path.join(base or RECEIPT_DIR, ep + ".jsonl")


def append_event(ep, obj, base=None):
    """이벤트 한 줄을 append 하고 **디스크에 내린다.**

    🔴 `fsync` 를 빼면 이 장치의 목적이 사라진다 — 죽는 순간을 대비해 적는 기록인데
    버퍼에만 있으면 죽을 때 같이 사라진다. 적었다고 남은 것이 아니다.
    """
    d = base or RECEIPT_DIR
    if not os.path.isdir(d):
        os.makedirs(d)                      # logs\ 아래다 — 워커 산출물 자리다.
    # 🔴 **`fsync` 가 빠져도 자체 시험은 못 잡는다** (§0 4층 ④). 프로세스가 정상 종료하면
    #    `close()` 가 어차피 flush 하므로, 같은 프로세스 안에서는 fsync 유무가 보이지 않는다.
    #    이 줄이 값을 하는 자리는 **정전·강제 종료** 뿐이고 그것은 시험으로 만들 수 없다.
    #    변조 시험에서 이 줄을 지워도 통과한다 — 그러니 «시험이 지킨다» 고 믿지 말고 남겨 둔다.
    obj = dict(obj)
    obj.setdefault("at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    obj.setdefault("at_epoch", int(time.time()))
    obj.setdefault("pid", os.getpid())
    line = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    with io.open(receipt_path(ep, d), "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    return line


def read_events(ep, base=None):
    """이벤트를 순서대로 읽는다. 깨진 줄은 **버리지 않고 세어서 돌려준다.**

    조용히 건너뛰면 «영수증이 없다» 와 «영수증을 못 읽었다» 가 같아 보인다 — 앞은 재개,
    뒤는 중단이라 판정이 정반대다(§0).
    """
    p = receipt_path(ep, base)
    if not os.path.exists(p):
        return [], 0
    out, broken = [], 0
    for ln in io.open(p, encoding="utf-8", errors="replace").read().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            broken += 1
    return out, broken


def resume_state(events):
    """seq 별 마지막 상태. `receipt` 가 `claim` 을 덮는다."""
    st = {}
    for e in events:
        stage = e.get("stage")
        if stage not in ("post.claim", "post.receipt"):
            continue
        seq = e.get("seq")
        if seq is None:
            continue
        cur = st.setdefault(int(seq), {})
        if stage == "post.claim" and cur.get("stage") != "post.receipt":
            cur.update(stage="post.claim", container_id=e.get("container_id"),
                       at_epoch=e.get("at_epoch"))
        elif stage == "post.receipt":
            cur.update(stage="post.receipt", container_id=e.get("container_id"),
                       media_id=e.get("media_id"), at_epoch=e.get("at_epoch"))
    return st


def live_index(live):
    """실물 포스트를 **본문 해시 → media id** 로 뒤집는다.

    id 가 아니라 본문으로 맞추는 이유: 우리가 아는 것이 본문이기 때문이다. 선점만 남은
    seq 의 media id 는 애초에 모른다 — 그것을 알아내려고 조회하는 것이다.
    """
    return {sha256_text((p.get("text") or "").strip()): p.get("id") for p in (live or [])}


def live_covers(live, limit, since_epoch):
    """조회한 창이 그 시각을 **덮는가.** 못 덮으면 «없다» 를 «안 나갔다» 로 읽으면 안 된다.

    창이 꽉 찼으면(len == limit) 잘렸을 수 있다 — 그때는 가장 오래된 실물이 그 시각보다
    앞서야 «그 사이가 다 보인다» 고 말할 수 있다. 시각을 못 읽으면 **모른다**(None)로 돌려준다.
    """
    if live is None:
        return None
    if len(live) < limit:
        return True                          # 잘리지 않았다 — 계정 전체가 이 안에 있다
    oldest = None
    for p in live:
        ts = p.get("timestamp") or ""
        try:
            e = int(datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z").timestamp())
        except ValueError:
            return None                      # 형식을 모른다 → 덮는지 모른다
        oldest = e if oldest is None else min(oldest, e)
    if oldest is None or since_epoch is None:
        return None
    return oldest <= since_epoch


def plan_resume(chain, state, live, limit, declared):
    """어디부터 이어갈지 정한다. 돌려주는 것은 (할 일 seq, 직전 media id, 기록, 중단 사유).

    중단 사유가 있으면 **아무것도 발행하지 않는다.** 자동 재시도는 하지 않는다 —
    «나갔는지 모르는» 것을 다시 올리는 것이 바로 이 장치가 막으려는 사고다.
    """
    idx = live_index(live)
    todo, notes = [], []
    parent, stop = None, None
    for seq in chain:
        s = state.get(seq) or {}
        if s.get("stage") == "post.receipt":
            parent = s.get("media_id")
            notes.append("P%d 영수증 있음 — 이미 나갔다 (media %s)" % (seq, parent))
            if not parent:
                stop = ("reconcile-broken P%d — 영수증에 media id 가 없다" % seq)
                break
            continue
        if s.get("stage") == "post.claim":
            # 불확정 — 선점만 있고 영수증이 없다. 실물로 가린다.
            if live is None:
                stop = ("reconcile-unverifiable P%d — 선점만 있는데 계정 조회에 실패했다" % seq)
                break
            mid = idx.get(declared.get(seq))
            if mid:
                parent = mid
                notes.append("P%d 선점만 있었으나 **실물에 있다** — 나간 것으로 본다 (media %s)"
                             % (seq, mid))
                continue
            cov = live_covers(live, limit, s.get("at_epoch"))
            if cov is not True:
                stop = ("reconcile-unverifiable P%d — 실물에 없으나 조회 창이 그 시각을 "
                        "덮는지 확인할 수 없다 (덮음=%s)" % (seq, cov))
                break
            notes.append("P%d 선점만 있고 실물에도 없다 — 나가지 않은 것으로 본다" % seq)
            todo.append(seq)
            continue
        todo.append(seq)
    return todo, parent, notes, stop


def duplicate_live(todo, declared, live):
    """이제 올릴 것이 **이미 계정에 있는가.** 있으면 그 편은 이미 나간 것이다.

    승인 파일의 해시 대조는 «원고가 바뀌었는가» 를 본다 — 바깥이 바뀐 것은 못 본다.
    승인을 받아 둔 사이에 사람이 손으로 올렸을 수도 있고, 영수증 없는 회차가 돌았을 수도 있다.
    """
    idx = live_index(live)
    return [(seq, idx[declared[seq]]) for seq in todo
            if declared.get(seq) in idx]


def fetch_live(api, uid, limit=LIVE_FETCH_LIMIT):
    """계정의 최근 포스트. 실패하면 **None (모름)** — 모름을 «없음» 으로 읽지 않는다."""
    st, r = api.call("GET", "%s/%s/threads" % (API, uid),
                     {"fields": "id,text,timestamp", "limit": limit})
    if st != 200 or not isinstance(r, dict) or not isinstance(r.get("data"), list):
        return None
    return [{"id": d.get("id"), "text": d.get("text") or "",
             "timestamp": d.get("timestamp") or ""} for d in r["data"]]


def write_stamp(path=None):
    """`pid=N started=…` 한 줄. `run_audit.read_stamp` 가 읽는 바로 그 꼴이다.

    이것이 남아 있는데 pid 가 죽어 있으면 «무기록 종료» 다 — 그 판정은 `run_audit` 이 한다.
    여기서는 **남기기만** 한다.
    """
    p = path or STAMP_PATH
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(p, "w", encoding="utf-8", newline="\n").write(
        "pid=%d started=%s\n" % (os.getpid(),
                                 datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return p


def clear_stamp(path=None):
    """정상 종료에서만 지운다. 죽으면 남고, 남은 것이 곧 신호다."""
    p = path or STAMP_PATH
    try:
        if os.path.exists(p):
            os.remove(p)
    except OSError:
        pass


def _finish(ep, rcpt_dir, verdict):
    """회차 마감 — 이벤트 한 줄과 스탬프 해제. **모든 출구가 이걸 부른다.**"""
    try:
        append_event(ep, {"stage": "run.finished", "verdict": verdict}, base=rcpt_dir)
    finally:
        clear_stamp()


def _write_report(out_dir, ep, lines):
    rep = os.path.join(out_dir, "%s_publish_%s.md" % (datetime.date.today().isoformat(), ep))
    io.open(rep, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("report: %s" % rep)
    return rep


# ---------------------------------------------------------------- 체인
def wait_finished(api, cid, log, timeout=WAIT_TIMEOUT_S, interval=WAIT_INTERVAL_S):
    """`FINISHED` 까지 기다린다. **상한을 넘으면 publish 를 부르지 않고 돌아온다.**

    무한 대기를 두면 «도는 중» 과 «죽은 것» 이 구별되지 않는다(정관 §0).
    """
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        st, r = api.call("GET", "%s/%s" % (API, cid), {"fields": "status,error_message"})
        last = r.get("status") if isinstance(r, dict) else None
        log("    status=%s (%.0fs)" % (last, time.time() - t0))
        if last == "FINISHED":
            return True, last, None
        if last in ("ERROR", "EXPIRED"):
            return False, last, (r.get("error_message") if isinstance(r, dict) else None)
        time.sleep(interval)
    return False, last, "대기 상한 %ds 초과" % timeout


def run_chain(api, uid, ep, ms_path, appr, log, publish,
              todo=None, parent=None, rcpt_dir=None):
    """seq 마다 [해시 대조 → 컨테이너 → FINISHED 대기 → publish → id 회수] 한 묶음.

    🔴 **원고를 묶음마다 디스크에서 다시 읽는다.** 처음 한 번만 읽어 메모리에 들고 있으면
    «직전마다 대조한다» 가 **늘 같은 값끼리 견주는 장식**이 된다 — 도는 도중에 파일이 바뀌어도
    영원히 안 걸린다. 체인은 포스트마다 몇 초에서 몇 십 초가 걸리고, 그 사이가 실제로 열려 있다.
    (정관 §0 «감지 장치가 실제로 값을 담는지».)
    """
    declared = {int(p["seq"]): p["sha256"] for p in appr["posts"]}
    # 🔴 도는 것은 **이어갈 seq 만**이다. 종전에는 늘 `appr["chain"]` 전체를 처음부터 돌아,
    #    3번까지 나간 뒤 다시 켜면 1번을 또 올렸다. `parent` 도 밖에서 받는다 —
    #    이어가는 회차의 첫 포스트는 **이미 나간 포스트의 답글**이어야 한다.
    chain = list(todo) if todo is not None else list(appr["chain"])
    done = []
    for n, seq in enumerate(chain, 1):
        # 파일 전체 해시부터 다시 본다 — 어느 포스트가 바뀌었든 여기서 먼저 걸린다.
        now = sha256_file(ms_path)
        if now != appr["body_sha256"]:
            return done, "FAIL manuscript-changed-midrun P%d (원고 해시 %s… ≠ 승인 %s…)" % (
                seq, now[:12], str(appr["body_sha256"])[:12])
        posts = parse_posts(ms_path)
        if seq not in posts:
            return done, "FAIL post-missing-midrun P%d" % seq
        body = posts[seq]
        log("[%d/%d] P%d — %d자" % (n, len(chain), seq, len(body)))

        # ① 컨테이너를 만들기 **직전마다** 대조한다. 한 번만 하면 뒷포스트가 조용히 갈린다.
        if sha256_text(body) != declared[seq]:
            return done, "FAIL post-hash-mismatch P%d" % seq
        log("    해시 대조 OK (원고 재읽기)")

        # ② 첨부도 같은 원칙이다 (2026-09-02 미디어 지원) — 원고를 다시 읽었으니 첨부
        #    명세도 다시 읽고, 승인이 서명한 것과 대조하고, **URL 바이트를 지금 받아**
        #    승인 sha256 과 견준다. 서명 뒤 CDN 내용이 갈렸으면 여기서 선다.
        att = parse_attachments(ms_path).get(seq)
        appr_att = {int(x["seq"]): x for x in (appr.get("attachments") or [])}.get(seq)
        if (att or None) != (None if appr_att is None else
                             {"kind": appr_att["media_type"], "url": appr_att["url"],
                              "sha256": appr_att["sha256"]}):
            return done, "FAIL attachment-approval-mismatch P%d" % seq
        if att:
            got, err = fetch_sha256(att["url"])
            if got != att["sha256"]:
                return done, ("FAIL media-hash-mismatch P%d (URL 바이트 %s ≠ 승인 %s…%s)"
                              % (seq, (got or "조회 실패")[:12], att["sha256"][:12],
                                 (" · " + err) if err else ""))
            log("    첨부 대조 OK (URL 재수신 · sha256 일치 · %s)" % att["kind"])

        if att is None:
            params = {"media_type": "TEXT", "text": body}
        elif att["kind"] == "VIDEO":
            params = {"media_type": "VIDEO", "video_url": att["url"], "text": body}
        else:
            params = {"media_type": "IMAGE", "image_url": att["url"], "text": body}
        if parent:
            params["reply_to_id"] = parent
        st, r = api.call("POST", "%s/%s/threads" % (API, uid), params)
        if st != 200 or not isinstance(r, dict) or "id" not in r:
            return done, "FAIL container-create P%d (HTTP %s · %s)" % (seq, st, api.scrub(json.dumps(r, ensure_ascii=False))[:160])
        cid = r["id"]
        log("    컨테이너 %s" % cid)

        ok, status, err = wait_finished(api, cid, log)
        if not ok:
            return done, "FAIL container-timeout %d/%d (status=%s · %s)" % (n, len(chain), status, err)

        if not publish:
            done.append({"seq": seq, "container_id": cid, "status": status, "published": False})
            return done, ("DRYRUN 여기까지 — publish 를 부르지 않았다. "
                          "체인은 직전 포스트의 media id 가 있어야 이어지므로 "
                          "드라이런은 **1번에서 멈추는 것이 정상**이다")

        # 🔴 **발행 «전» 에 선점을 적는다.** 여기서 죽으면 «나갔는지 모른다» 가 남고,
        #    다음 기동이 실물을 조회해 가린다. 안 적고 죽으면 아무 흔적이 없다.
        append_event(ep, {"stage": "post.claim", "seq": seq, "container_id": cid},
                     base=rcpt_dir)
        st, r = api.call("POST", "%s/%s/threads_publish" % (API, uid), {"creation_id": cid})
        if st != 200 or not isinstance(r, dict) or "id" not in r:
            return done, "FAIL publish P%d (HTTP %s · %s)" % (seq, st, api.scrub(json.dumps(r, ensure_ascii=False))[:160])
        mid = r["id"]
        append_event(ep, {"stage": "post.receipt", "seq": seq, "container_id": cid,
                          "media_id": mid}, base=rcpt_dir)
        done.append({"seq": seq, "container_id": cid, "media_id": mid, "published": True})
        log("    게시 media_id=%s" % mid)
        parent = mid
    return done, None


# ---------------------------------------------------------------- 자체 검사
def _selftest_resume():
    r"""재기동 조정·중복 검사의 자체 시험.

    🔴 **L-009 — 변조가 실제로 먹었는지 먼저 확인하고 판정한다.** 변조를 «했다» 고 믿고
    바로 결과를 보면, 변조가 안 먹은 채로 통과한 것을 «잘 막았다» 로 읽는다. 아래 각
    역검증 케이스는 ⓐ 변조 전 상태를 재고 ⓑ 변조 후 상태가 **달라졌음을 assert** 한 뒤
    ⓒ 비로소 판정을 본다.

    케이스는 **서로 분리한다** — 한 입력에 두 결함을 넣으면 «새 검사가 없었어도 잡혔을
    입력» 이 되어 그 검사의 값어치가 증명되지 않는다(정관 §0 · `cardcheck.local_blob` 선례).
    """
    import shutil
    import tempfile

    base = tempfile.mkdtemp(prefix="_pt_rcpt_")
    try:
        ep = "epTEST"
        bodies = {n: "본문 P%d" % n for n in range(1, 6)}
        declared = {n: sha256_text(bodies[n]) for n in bodies}
        chain = [1, 2, 3, 4, 5]

        # ── ⓐ 영수증이 없다 → 처음부터, 직전 없음 ────────────────────────────
        todo, parent, _n, stop = plan_resume(chain, {}, [], LIVE_FETCH_LIMIT, declared)
        assert stop is None and todo == chain and parent is None, (todo, parent, stop)

        # ── ⓑ 1~3 영수증 → 4부터, 직전 = 3의 media id ───────────────────────
        for n in (1, 2, 3):
            append_event(ep, {"stage": "post.claim", "seq": n, "container_id": "c%d" % n}, base=base)
            append_event(ep, {"stage": "post.receipt", "seq": n, "container_id": "c%d" % n,
                              "media_id": "m%d" % n}, base=base)
        ev, broken = read_events(ep, base)
        assert broken == 0 and len(ev) == 6, (len(ev), broken)
        st = resume_state(ev)
        assert [st[n]["stage"] for n in (1, 2, 3)] == ["post.receipt"] * 3, st
        todo, parent, _n, stop = plan_resume(chain, st, [], LIVE_FETCH_LIMIT, declared)
        assert stop is None, stop
        assert todo == [4, 5], todo
        assert parent == "m3", parent

        # ── ⓒ 역검증: 3의 «영수증» 을 지워 선점만 남긴다 → 불확정 ───────────
        #    L-009 — 먼저 «지워졌는가» 를 확인한다.
        p = receipt_path(ep, base)
        before = io.open(p, encoding="utf-8").read()
        kept = [ln for ln in before.splitlines()
                if not ('"stage": "post.receipt"' in ln and '"seq": 3' in ln)]
        io.open(p, "w", encoding="utf-8", newline="\n").write("\n".join(kept) + "\n")
        after = io.open(p, encoding="utf-8").read()
        assert after != before, "변조가 안 먹었다 — 이 줄이 없으면 아래 판정은 아무 뜻이 없다"
        st2 = resume_state(read_events(ep, base)[0])
        assert st2[3]["stage"] == "post.claim", \
            "변조 후에도 3이 영수증 상태다 — 변조가 파싱에 반영되지 않았다"

        #    실물을 못 읽으면(None) → 멈춘다.
        #    🔴 **사유 문구까지 본다.** 「reconcile-unverifiable」 만 보면 아래 «창이 안 덮는다»
        #    쪽 사유와 구별되지 않아, 이 갈래를 통째로 지워도 시험이 통과한다(변조 시험에서
        #    실제로 안 걸렸다). 어느 갈래가 잡았는지까지 재야 그 갈래가 증명된다(§0).
        todo, parent, _n, stop = plan_resume(chain, st2, None, LIVE_FETCH_LIMIT, declared)
        assert stop and "계정 조회에 실패" in stop, stop

        #    실물에 3이 **있으면** → 나간 것으로 보고 4부터 이어간다
        live_has3 = [{"id": "m3", "text": bodies[3], "timestamp": "2026-08-29T01:00:00+0000"}]
        todo, parent, _n, stop = plan_resume(chain, st2, live_has3, LIVE_FETCH_LIMIT, declared)
        assert stop is None and todo == [4, 5] and parent == "m3", (todo, parent, stop)

        #    실물에 **없고** 창이 안 찼으면 → 안 나간 것으로 보고 3부터 올린다
        live_no3 = [{"id": "zz", "text": "남의 글", "timestamp": "2026-08-29T01:00:00+0000"}]
        todo, parent, _n, stop = plan_resume(chain, st2, live_no3, LIVE_FETCH_LIMIT, declared)
        assert stop is None and todo == [3, 4, 5] and parent == "m2", (todo, parent, stop)

        #    실물에 없는데 창이 **꽉 찼고** 그 시각을 못 덮으면 → 멈춘다
        full = [{"id": "x%d" % i, "text": "남의 글 %d" % i,
                 "timestamp": "2027-01-01T00:00:00+0000"} for i in range(3)]
        todo, parent, _n, stop = plan_resume(chain, st2, full, 3, declared)
        assert stop and "reconcile-unverifiable" in stop, stop

        # ── ⓓ 창 덮기 판정 자체 ─────────────────────────────────────────────
        assert live_covers([{"timestamp": "2027-01-01T00:00:00+0000"}], 5, 0) is True, \
            "창이 안 찼는데 «못 덮는다» 고 했다"
        assert live_covers(full, 3, 0) is False, "꽉 찬 창이 옛 시각을 덮는다고 했다"
        assert live_covers(None, 3, 0) is None, "모름이 «안다» 로 바뀌었다"

        # ── ⓔ 중복 게시 — 걸리는 쪽과 통과하는 쪽을 **같이** 본다 ───────────
        live_dup = [{"id": "already", "text": bodies[1], "timestamp": "2026-08-29T01:00:00+0000"}]
        assert duplicate_live([1, 2], declared, live_dup) == [(1, "already")], "중복을 놓쳤다"
        assert duplicate_live([2, 3], declared, live_dup) == [], "중복이 아닌 것을 걸렀다"
        assert duplicate_live([1, 2], declared, []) == [], "빈 계정에서 중복이 나왔다"

        # ── ⓕ 깨진 줄은 «없음» 과 구별된다 ──────────────────────────────────
        with io.open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write("{망가진 줄\n")
        ev2, broken2 = read_events(ep, base)
        assert broken2 == 1, "깨진 줄을 조용히 버렸다 — «없다» 와 구별되지 않는다"
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return True


def _selftest():
    r"""검사기 자신을 시험한다 — 통과해야 할 것과 걸려야 할 것을 **같이** 본다 (정관 §0).

    특히 «금지 판정» 은 양쪽을 봐야 한다. 막는 것만 보면 **전부 막는 가드**가 정상으로 보인다.
    """
    # ① publish 판정 — 세그먼트 일치. C-8 사례가 여기 박혀 있다.
    assert is_publish_path("/v1.0/123/threads_publish"), "publish 를 못 막는다"
    assert is_publish_path("/v1.0/123/threads_publish?x=1"), "쿼리가 붙으면 못 막는다"
    assert not is_publish_path("/v1.0/123/threads_publishing_limit"), \
        "쿼터 조회를 막는다 — «문자열 포함» 으로 판정하고 있다 (C-8)"
    assert not is_publish_path("/v1.0/123/threads"), "컨테이너 생성을 막는다"

    # ② 원고 파싱 — 정상 / 코드펜스 없음
    import tempfile
    ok_md = "# x\n\n### P1 — 10자\n\n```\n첫 줄\n```\n\n### P2 — 10자\n\n```\n둘째 줄\n```\n"
    p = os.path.join(tempfile.gettempdir(), "_pt_ok.md")
    io.open(p, "w", encoding="utf-8").write(ok_md)
    got = parse_posts(p)
    assert got == {1: "첫 줄", 2: "둘째 줄"}, got
    bad_md = "### P1 — 10자\n\n본문에 코드펜스가 없다\n"
    p2 = os.path.join(tempfile.gettempdir(), "_pt_bad.md")
    io.open(p2, "w", encoding="utf-8").write(bad_md)
    try:
        parse_posts(p2)
        raise AssertionError("코드펜스 없는 원고를 통과시켰다")
    except SystemExit:
        pass

    # ③ 발행 자격 (`check_gate`) — 정상 통과 / 축마다 하나씩 걸림 (역검증 케이스를 섞지 않는다)
    #   승인 파일을 폐기하고 그 자리에 앉힌 검사다 (2026-09-10). 사이드카를 실제로 써 놓고 잰다.
    posts = {1: "가", 2: "나"}
    _side = p + ".meta.json"

    def _put_side(obj):
        io.open(_side, "w", encoding="utf-8", newline="\n").write(
            json.dumps(obj, ensure_ascii=False))

    #   ⓐ 사이드카가 없으면 걸린다 — «게이트를 안 돈 원고» 다
    if os.path.exists(_side):
        os.remove(_side)
    assert any("gate-evidence-missing" in x for x in check_gate(p)), "사이드카 없는 원고를 통과시켰다"
    #   ⓑ 정상 사이드카는 통과한다 (전부 막는 가드가 아니다)
    _ok_side = {"gate_failed": 0, "body_sha256": sha256_file(p), "gate_skill_revision": "v0"}
    _put_side(_ok_side)
    assert check_gate(p) == [], "정상 자격을 걸렀다: %r" % (check_gate(p),)
    #   ⓒ 게이트 FAIL 이 실려 있으면 걸린다
    _put_side(dict(_ok_side, gate_failed=2))
    assert any("gate-failed" in x for x in check_gate(p)), "게이트 FAIL 을 통과시켰다"
    #   ⓓ 🔴 **게이트 뒤에 원고가 바뀌면 걸린다** — 이 축이 승인 파일의 해시 대조를 이어받았다
    _put_side(dict(_ok_side, body_sha256="x" * 64))
    assert any("manuscript-changed" in x for x in check_gate(p)), "게이트 뒤 원고 변경을 놓쳤다"
    #   ⓔ 옛 판 사이드카(축 자체가 없는 것)는 «통과» 가 아니라 **모른다** 로 걸린다
    _put_side({"gate_skill_revision": "v0"})
    assert len([x for x in check_gate(p) if "gate-unknown" in x]) == 2, \
        "옛 판 사이드카를 통과시켰다: %r" % (check_gate(p),)
    _put_side(_ok_side)

    # ③-a 첨부 안전판 — **양방향** (인프라 백로그 20번 ① · 2026-08-30)
    #      막는 것만 보면 «전부 막는 가드» 가 정상으로 보인다. 통과해야 할 것을 같이 본다.
    att_md = ok_md.replace("```\n첫 줄\n```",
                           "```\n첫 줄\n```\n\n**첨부** `_official/a.mp4` — 영상 1920x1080")
    pa = os.path.join(tempfile.gettempdir(), "_pt_attach.md")
    io.open(pa, "w", encoding="utf-8").write(att_md)
    #   ⓐ-0 **조건이 실제로 만들어졌는가.** 첨부 줄이 안 들어갔으면 아래 «막혔다» 는
    #        가드의 공이 아니라 잴 것이 없었던 것이다 (L-009).
    _d = attachment_decls(pa)
    assert len(_d) == 1 and _d[0][0] == 1, "픽스처에 첨부 선언이 안 들어갔다: %r" % (_d,)
    #   ⓐ 첨부 선언 + 미지원 → 막힌다
    assert attachment_block(pa, support=False), "첨부 선언 원고를 통과시켰다"
    #   ⓑ 첨부 0건 → 통과한다 (옛 편이 새로 걸리지 않는다)
    assert attachment_decls(p) == [], "첨부 없는 원고에서 선언을 찾았다"
    assert attachment_block(p, support=False) == [], "첨부 없는 원고를 막았다"
    #   ⓒ 첨부 선언 + 지원 + **명세 완비(URL·sha256·형상)** → 통과한다 (전부 막는 가드가 아니다)
    _sha64 = "a" * 64
    full_md = ok_md.replace(
        "```\n첫 줄\n```",
        "```\n첫 줄\n```\n\n**첨부** `_official/a.mp4` — 영상 1920x1080 · 크레딧 `c` · 공식"
        " · URL https://example.com/a.mp4 · sha256 " + _sha64)
    pf = os.path.join(tempfile.gettempdir(), "_pt_attach_full.md")
    io.open(pf, "w", encoding="utf-8").write(full_md)
    _pa = parse_attachments(pf)
    assert _pa == {1: {"kind": "VIDEO", "url": "https://example.com/a.mp4",
                       "sha256": _sha64}}, "첨부 명세 파싱이 틀렸다: %r" % (_pa,)
    assert attachment_block(pf, support=True) == [], "명세 완비 첨부를 막았다"
    #   ⓒ-2 지원해도 **명세가 비면 막는다** (2026-09-02) — URL 없는 옛 꼴은 «조용히
    #        텍스트만 올리는» ep39 사고 경로라 지원 여부와 무관하게 선다
    _nou = attachment_block(pa, support=True)
    assert _nou and any("P1" in x for x in _nou), "URL 없는 첨부를 통과시켰다: %r" % (_nou,)
    #   ⓒ-3 포스트당 2건 → 막는다 (이 워커는 1건만 싣는다)
    two_md = full_md.replace("**첨부** `_official/a.mp4`",
                             "**첨부** `_official/b.mp4` — 영상 1x1 · 크레딧 `c` · 공식"
                             " · URL https://example.com/b.mp4 · sha256 " + _sha64
                             + "\n**첨부** `_official/a.mp4`")
    _patt2 = os.path.join(tempfile.gettempdir(), "_pt_attach_two.md")
    io.open(_patt2, "w", encoding="utf-8").write(two_md)
    assert parse_attachments(_patt2) == {1: None}, "포스트당 2건을 명세로 읽었다"
    assert attachment_block(_patt2, support=True), "포스트당 2건을 통과시켰다"
    os.remove(_patt2)
    #   ⓒ-4 계획이 첨부를 **서명값으로** 싣는다 — `run_chain` 이 묶음마다 이것과 견준다
    _posts_f = parse_posts(pf)
    _plan_f = build_plan("ep39", pf, _posts_f)
    assert _plan_f["attachments"] == [{"seq": 1, "media_type": "VIDEO",
                                       "url": "https://example.com/a.mp4",
                                       "sha256": _sha64}], _plan_f["attachments"]
    os.remove(pf)
    #   ⓓ **판정 불가는 통과가 아니다** — 모르면 멈춘다
    _unk = attachment_block(pa, support=None)
    assert _unk and "판정하지" in _unk[0], "판정 불가를 통과시켰다: %r" % (_unk,)
    #   ⓔ 사유 줄이 **어느 포스트인지** 를 담는다 (개수만 세면 «어디가» 를 못 적는다)
    _why = attachment_block(pa, support=False)
    assert any("P1" in x for x in _why), "막았지만 어느 포스트인지 안 적었다: %r" % (_why,)
    os.remove(pa)

    # ③-a2 지원 여부 판정기 — 깃발이 아니라 **소스**를 읽는다
    #   ⓕ 지금 이 파일은 **미디어 지원**으로 읽혀야 한다 (깃발 ↔ 실물 대조).
    #      2026-09-02 에 VIDEO/IMAGE 리터럴 컨테이너가 실제로 붙었다 — 종전 «TEXT 전용»
    #      단정은 그날 사실이 바뀌며 같이 뒤집었다. 이 줄이 False 로 돌아가면
    #      리팩터가 미디어 경로를 지운 것이니 첨부 편 발행을 멈춰야 한다.
    assert media_support_state() is True, \
        "이 워커가 미디어를 못 싣는 것으로 읽혔다 — 미디어 경로가 지워졌거나 판정기가 틀렸다"
    #   ⓖ 변수로 바뀐 소스는 «지원» 으로 읽어야 한다 — 안 그러면 가드가 조용히 낡는다
    assert media_support_state("x = {" + repr("media_type") + ": kind}") is True, \
        "미디어 경로가 생겨도 못 알아챈다"
    #   ⓗ 배정을 못 찾으면 «못 싣는다» 가 아니라 **모른다** 다
    assert media_support_state("배정이 없는 소스") is None, \
        "배정을 못 찾았는데 «못 싣는다» 로 단정했다"
    #   ⓘ **문자열 안의 가짜 배정은 세지 않는다.** 이 파일의 시험 픽스처가 판정을 흔들면
    #      안 된다 — 정규식 판이 정확히 그래서 떨어졌고, 그게 ast 로 바꾼 계기다.
    assert media_support_state("x = " + repr('{"media_type": "VIDEO"}')) is None, \
        "문자열 안의 가짜 배정을 세고 있다 — 시험 픽스처가 판정을 흔든다"
    #   ⓙ 문법이 깨진 소스는 «못 싣는다» 가 아니라 **모른다** 다
    assert media_support_state("def (:") is None, "깨진 소스를 «못 싣는다» 로 단정했다"

    # ③-b 계획은 원고에서 나온다 — 그 값이 `run_chain` 의 대조 기준이 된다
    d = build_plan("ep39", p, posts)
    assert d["ep"] == "ep39" and d["chain"] == [1, 2], d
    assert d["body_sha256"] == sha256_file(p), "계획의 본문 해시가 원고와 다르다"
    assert [x["sha256"] for x in d["posts"]] == [sha256_text("가"), sha256_text("나")], d["posts"]

    for q in (p, p2, _side):
        if os.path.exists(q):
            os.remove(q)

    # ③-c 🔴 **승인 장치가 코드에 남아 있지 않다 (2026-09-10 신설).**
    #     축을 «없앴다» 는 것은 그 자리가 비었다는 것으로만 증명된다. 한 자리만 지우고
    #     다른 자리에 남으면 «이름만 바뀐 같은 잠금» 이 된다 — 이 워커에서 그것을 잰다.
    #     🔴 주석·문서 문장은 대상이 아니다. 낱말만 세면 «폐기했다» 고 적어 둔 자리가
    #     위반으로 잡힌다(C-8 계열).
    _mod = sys.modules[__name__]
    assert not [n for n in ("APPROVAL_DIR", "check_approval", "build_draft")
                if hasattr(_mod, n)], "승인 장치가 아직 이 모듈에 있다"
    _needle = "publish_" + "approval"     # 이 줄 자신이 검사에 걸리지 않게 쪼개 둔다
    _body = io.open(os.path.abspath(__file__), encoding="utf-8").read().split("\nimport ", 1)[1]
    _live = [ln.strip() for ln in _body.splitlines()
             if _needle in ln and not ln.strip().startswith("#")]
    assert not _live, "승인 폴더를 가리키는 코드가 남아 있다:\n  " + "\n  ".join(_live[:5])

    # ④ 드라이런에서 publish 가 실제로 막히는가 (토큰 없이도 되는 검사)
    api = Api("dummy", allow_publish=False)
    try:
        api.call("POST", "/v1.0/1/threads_publish", {"creation_id": "1"})
        raise AssertionError("드라이런인데 publish 가 통과했다")
    except Blocked:
        pass
    assert Api("dummy", allow_publish=True) is not None

    # ⑤ 재기동 조정·중복 검사 — 영수증이 있는 상태에서 이어가는지, 변조하면 멈추는지
    _selftest_resume()
    return True


# ---------------------------------------------------------------- main
def _run(argv=None):
    _selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep", help="대상 편 (예: ep39)")
    ap.add_argument("--manuscript", default=None, help="원고 경로. 생략하면 reports 에서 찾는다")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--receipt-dir", default=None,
                    help="영수증 자리. 시험용 우회 — 쓰면 리포트가 그렇게 적는다")
    ap.add_argument("--publish", action="store_true",
                    help="🔴 실제 게시. 없으면 드라이런 — 기본값은 게시하지 않는다")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        print("자체 검사 통과")
        return 0
    if not a.ep:
        raise SystemExit("--ep 가 필요하다")

    # 🔴 **여기가 첫 파일 쓰기다.** 종전에는 회차 맨 끝 리포트 한 번뿐이라, 승인 확인
    #    도중이나 체인 도중에 죽으면 **아무것도 남지 않았다** — 바깥에서 «돌았는지» 조차
    #    알 수 없었다. 승인·토큰·계정보다 **앞**에 적는다: 무엇이 실패하든 «켜졌다» 는 남는다.
    _receipt_dir_early = a.receipt_dir or RECEIPT_DIR
    append_event(a.ep, {"stage": "run.started",
                        "mode": "publish" if a.publish else "dryrun"},
                 base=_receipt_dir_early)
    # 같은 사실을 `run_audit.py` 가 읽는 꼴로도 남긴다 — 그 스크립트는 이 JSONL 을 모른다.
    write_stamp()

    # 자리는 위 상수로 고정한다. 인자는 **시험용 우회**일 뿐이고, 쓰면 리포트가 그렇게 적는다 —
    # 그렇게 적지 않으면 fixture 회차가 실제 회차처럼 읽힌다.
    out_dir = a.out_dir or REPORTS_DIR
    rcpt_dir = a.receipt_dir or RECEIPT_DIR
    overridden = [n for n, v in (("--out-dir", a.out_dir),
                                 ("--receipt-dir", a.receipt_dir)) if v]

    lines = []

    def log(m):
        print(m)
        lines.append(m)

    log("# Threads 발행 — %s · %s" % (a.ep, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    log("모드: **%s**" % ("실제 게시" if a.publish else "드라이런 (publish 미호출)"))
    if overridden:
        log("🔴 **기본 자리가 아니다 — 시험용 우회** (%s). 실제 회차가 아니다"
            % ", ".join(overridden))

    # 트리거 — 복붙 세트가 없으면 워커는 뜨지 않는다 (에러 아님).
    # 🔴 `pack()` 은 게이트 FAIL 이면 파일을 **쓰지 않는다** — 그래서 이 파일의 존재가
    #    곧 «그 회차 게이트를 통과했다» 다. 초안(`.draft.md`)은 대상이 아니다.
    ms = a.manuscript
    if not ms:
        cand = sorted(f for f in os.listdir(out_dir) if re.match(r"\d{4}-\d\d-\d\d_dist_%s\.md$" % a.ep, f))
        if not cand:
            log("복붙 세트 없음 — 트리거가 없다: reports\\<날짜>_dist_%s.md" % a.ep)
            log("STATUS: OK (부분: 원고 없음 — 발행 대상 아님)")
            _finish(a.ep, rcpt_dir, "no-manuscript")
            _write_report(out_dir, a.ep, lines)
            return 0
        ms = os.path.join(out_dir, cand[-1])
    elif not os.path.exists(ms):
        log("원고를 못 찾았다: %s" % ms)
        log("STATUS: FAIL manuscript-missing")
        _finish(a.ep, rcpt_dir, "manuscript-missing")
        _write_report(out_dir, a.ep, lines)
        return 1
    log("원고: %s" % os.path.basename(ms))

    posts = parse_posts(ms)

    # 🔴 **첨부 안전판** (인프라 백로그 20번 ① · 2026-08-30). 승인 대조보다 **앞**이고
    #    네트워크 호출보다 **앞**이다 — 못 실을 것을 들고 계정까지 갈 이유가 없다.
    #    ep39 에서 이 자리가 없어 영상 2건이 말없이 사라졌다. 구현(20번 ③)이 서면
    #    `media_support_state()` 가 소스에서 그것을 읽어 이 게이트는 **저절로 열린다** —
    #    사람이 깃발을 내리는 걸음이 없다(그 걸음이 있으면 언젠가 빠진다).
    stop = attachment_block(ms)
    if stop:
        for ln in stop:
            log("🔴 %s" % ln)
        log("🔴 **발행하지 않았다.** 첨부를 못 싣는 채로 올리면 본문의 «영상 출처:» 류 "
            "라벨이 없는 것을 가리킨다 — ep39 실사고(2026-08-30)가 그것이다.")
        log("STATUS: FAIL attachment-unsupported")
        _finish(a.ep, rcpt_dir, "attachment-unsupported")
        _write_report(out_dir, a.ep, lines)
        return 1

    # 🔴 **발행 자격** (2026-09-10 · 승인 파일 폐기). 사이드카가 재는 두 축을 여기서 본다.
    bad = check_gate(ms)
    if bad:
        for b in bad:
            log("🔴 자격 실패 — %s" % b)
        log("STATUS: FAIL gate (%d건)" % len(bad))
        _finish(a.ep, rcpt_dir, "gate")
        _write_report(out_dir, a.ep, lines)
        return 1
    _meta = read_sidecar(ms) or {}
    log("자격 통과 — 게이트 FAIL 0건 · 원고 해시 = 게이트 당시 해시 (%s…)"
        % str(_meta.get("body_sha256"))[:12])
    log("검사 판본: %s" % _meta.get("gate_skill_revision", "미상"))

    appr = build_plan(a.ep, ms, posts)
    log("발행 계획: P%s (포스트 %d건)"
        % ("·P".join(str(s) for s in appr["chain"]), len(appr["posts"])))

    token = load_token()
    api = Api(token, allow_publish=a.publish)
    st, me = api.call("GET", API + "/me", {"fields": "id,username"})
    if st != 200:
        log("계정 조회 실패 HTTP %s" % st)
        log("STATUS: FAIL account")
        _finish(a.ep, rcpt_dir, "account")
        _write_report(out_dir, a.ep, lines)
        return 1
    uid = me["id"]
    log("계정: %s (%s)" % (me.get("username"), uid))

    st, q = api.call("GET", "%s/%s/threads_publishing_limit" % (API, uid),
                     {"fields": "quota_usage,config,reply_quota_usage,reply_config"})
    if st == 200 and isinstance(q, dict) and q.get("data"):
        d = q["data"][0]
        log("쿼터 전: 게시 %s/%s · 답글 %s/%s"
            % (d.get("quota_usage"), d.get("config", {}).get("quota_total"),
               d.get("reply_quota_usage"), d.get("reply_config", {}).get("quota_total")))

    # --- 재기동 조정 — 이미 나간 것을 먼저 안다 --------------------------------
    declared = {int(p["seq"]): p["sha256"] for p in appr["posts"]}
    events, broken = read_events(a.ep, rcpt_dir)
    if broken:
        log("🔴 영수증에 못 읽은 줄이 %d 개 있다 — «없다» 와 구별해야 한다" % broken)
        log("STATUS: FAIL receipt-corrupt")
        _finish(a.ep, rcpt_dir, "receipt-corrupt")
        _write_report(out_dir, a.ep, lines)
        return 1
    state = resume_state(events)
    live = fetch_live(api, uid)
    log("실물 조회: %s" % ("%d건" % len(live) if live is not None else "🔴 실패 — 모름"))
    todo, parent, notes, stop = plan_resume(list(appr["chain"]), state, live,
                                            LIVE_FETCH_LIMIT, declared)
    for nline in notes:
        log("  조정| %s" % nline)
    if stop:
        log("🔴 %s" % stop)
        log("**보고하고 멈춘다** — 나갔는지 모르는 것을 다시 올리지 않는다. 자동 재시도 금지.")
        log("STATUS: FAIL %s" % stop.split()[0])
        _finish(a.ep, rcpt_dir, "stop")
        _write_report(out_dir, a.ep, lines)
        return 1
    if not todo:
        log("이어갈 포스트가 없다 — 이 편은 이미 다 나갔다 (영수증 기준)")
        log("STATUS: OK (부분: 이미 발행 완료 — 새로 올린 것 0건)")
        _finish(a.ep, rcpt_dir, "already-done")
        _write_report(out_dir, a.ep, lines)
        return 0
    if len(todo) != len(appr["chain"]):
        log("재기동 조정: %d/%d 는 이미 나갔다 — P%s 부터 이어간다 (직전 media %s)"
            % (len(appr["chain"]) - len(todo), len(appr["chain"]), todo[0], parent))

    # --- 신선도 — 승인 이후 «바깥» 이 바뀌었는가 -------------------------------
    # 🔴 승인 파일의 해시 대조는 **원고가 바뀌었는가**만 본다. 승인을 받아 둔 사이에
    #    사람이 손으로 올렸거나 영수증 없는 회차가 돌았으면 그것은 못 잡는다.
    if live is None:
        if a.publish:
            log("🔴 실물을 못 읽어 중복 게시를 가릴 수 없다")
            log("STATUS: FAIL live-unreadable")
            _finish(a.ep, rcpt_dir, "live-unreadable")
            _write_report(out_dir, a.ep, lines)
            return 1
        log("⚪ 드라이런이라 실물 조회 실패를 넘긴다 — 발행이 없으므로 중복도 없다")
    else:
        dup = duplicate_live(todo, declared, live)
        if dup:
            for seq, mid in dup:
                log("🔴 P%d 가 이미 계정에 있다 (media %s)" % (seq, mid))
            log("**보고하고 멈춘다** — 같은 편을 두 번 올리지 않는다.")
            log("STATUS: FAIL duplicate-live")
            _finish(a.ep, rcpt_dir, "duplicate-live")
            _write_report(out_dir, a.ep, lines)
            return 1
        log("중복 검사 통과 — 올릴 %d건이 계정에 없다" % len(todo))

    try:
        done, err = run_chain(api, uid, a.ep, ms, appr, log, a.publish,
                              todo=todo, parent=parent, rcpt_dir=rcpt_dir)
    except Blocked as e:
        done, err = [], "DRYRUN %s" % e

    log("")
    log("| seq | 컨테이너 | media id | 게시 |")
    log("|---|---|---|---|")
    for d in done:
        log("| %s | %s | %s | %s |" % (d["seq"], d["container_id"],
                                       d.get("media_id", "—"), "예" if d.get("published") else "아니오"))

    if err and err.startswith("DRYRUN"):
        log("")
        log(err)
        log("STATUS: OK (부분: 드라이런 — 발행 0건)")
        rc = 0
    elif err:
        log("")
        log("🔴 %s" % err)
        log("**보고하고 멈춘다** — 자동 이어붙임·자동 삭제 금지(명세). 재실행은 새 승인 파일을 요구한다.")
        log("STATUS: %s" % err if err.startswith("FAIL") else "STATUS: FAIL %s" % err)
        rc = 1
    else:
        log("STATUS: OK — %d/%d 포스트 게시" % (len(done), len(appr["chain"])))
        rc = 0

    _finish(a.ep, rcpt_dir, "ok" if rc == 0 else "fail")
    _write_report(out_dir, a.ep, lines)
    return rc


def main(argv=None):
    """🔴 종전에는 여기서 «승인 폴더가 회차 도중에 생겼는가» 를 봤다 (2026-08-28).

    승인 장치를 폐기(2026-09-10)하면서 그 감시도 같이 뺐다 — 볼 폴더가 없다.
    자격을 재는 자리는 `_run` 안의 `check_gate(ms)` 하나이고, 그 축의 역검증은
    `_selftest()` ③ 에 있다.
    """
    return _run(argv)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    raise SystemExit(main())
