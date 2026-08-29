# -*- coding: utf-8 -*-
r"""Threads 발행 워커 — 승인된 편 1건의 텍스트 스레드를 체인 순서대로 올린다.

정본 명세: `docs\workers\publish-threads.md`. **그 문서가 규칙이고 이 파일은 그 실행체다.**

    py scripts\publish_threads.py --ep ep39 --draft-approval    ← 승인 «초안» 을 reports\ 에
    py scripts\publish_threads.py --ep ep39                     ← 드라이런 (기본값)
    py scripts\publish_threads.py --ep ep39 --publish           ← 실제 게시
    py scripts\publish_threads.py --self-test                   ← 검사기 자체 시험

## 승인은 초안·서명 2단이다 (2026-08-28 개정)

    ① 에이전트: `--draft-approval` → `reports\<ep>.approval.json` **초안**
       (본문 해시 5건 + chain + 대상 편. 해시 계산은 기계가 한다 — 사람이 셀 값이 아니다)
    ② JJ: 원고 5포스트를 읽고 판정한 뒤 `scripts\move-approval.bat` 으로
       `publish_approval\<ep>.json` 으로 **옮긴다. 이동이 곧 서명이다.**
    ③ 워커: **`publish_approval\` 에 있는 것만** 승인으로 본다.

🔴 **초안 생성이 잠금을 우회하지 않는다.** 에이전트는 `reports\` 에만 쓸 수 있고
`publish_approval\` 에는 쓰지도 못하고 이동 배치를 실행하지도 못한다(프로브가 회차마다 실증).
초안은 **«승인해 달라는 서류»** 이지 승인이 아니다 — 그 서류가 어느 폴더에 있느냐가 전부다.

## 왜 에이전트가 아니라 스크립트인가

승인 파일과 원고가 정해지면 **남은 일에 판단이 없다** — 해시를 맞추고, 컨테이너를 만들고,
`FINISHED` 를 기다리고, 순서대로 올린다. 정답이 있는 자리에 모델을 넣지 않는다
(정관 §0 · `skill-drift-audit` 과 같은 성격). 모델이 끼면 «원고를 조금 고쳐서 올리는» 길이 생긴다.

## 🔴 기본값이 드라이런이다 (§0 4층 ①)

`--publish` 를 **명시하지 않으면 어떤 경우에도 게시하지 않는다.** 금지를 규율이 아니라
기본값으로 옮긴 것이다 — 실수로 돌려도 바깥으로 나가지 않는다.

## 🔴 이 스크립트가 증명하지 *못* 하는 것 (§0 4층 ④)

- **승인 파일의 암호 서명을 검증하지 않는다.** 서명은 «이동» 이고, 이동할 수 있는 것은
  `publish_approval\` 에 쓸 수 있는 자 뿐이다. 그 자리를 재는 것은 `scripts\permission_probe.py` 이고
  워커 기동 **전에** 래퍼가 돌린다. 여기서 다시 검사하는 척하지 않는다.
- 🔴 **그 프로브가 증명하는 것은 «에이전트가 만들 수 없다» 가 아니라 «이 회차에 만들지 못했다» 다.**
  권한 밖 경로로 우회하는 길(다른 세션·사람 권한 탈취)은 이 장치가 못 잡는다.
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
#: 어디 놓이느냐에 따라 다른 폴더를 본다** — 운영 서버 사본은 `jj-company\publish_approval`,
#: 작업장 사본은 `orca\jj-company\publish_approval` 이었다. 둘 다 실재하는 사본이다.
#:
#: 승인 폴더는 **잠금의 경계**다. 경계가 사본마다 다르면 «에이전트가 못 쓴다» 는 실증이
#: 어느 폴더에 대한 것인지 흐려지고, 배치가 옮겨 둔 승인을 워커가 못 보는 조합도 생긴다.
#: 배치(`move-approval.bat` DST)·래퍼(`publish-threads.ps1` $Hq)는 이미 절대경로였다 —
#: **셋 중 하나만 상대 계산이었고, 그 하나가 보안 경계를 쥐고 있었다.**
#:
#: 세 자리가 어긋나면 `_selftest()` 가 파일을 열어 **실제로 대조해** 걸러 낸다.
HQ = r"C:\Users\ojaej\jj-company"
APPROVAL_DIR = os.path.join(HQ, "publish_approval")
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


def build_draft(ep, ms_path, posts):
    """승인 «초안» 을 만든다 — 해시 계산은 기계 몫이다. **서명은 여기 없다.**

    `signed_by`·`signature` 를 미리 채우지 않는다. 채워 두면 사람이 «이미 서명됐다» 로 읽는다 —
    서명은 이 파일을 `publish_approval\\` 로 **옮기는 행위** 다.
    """
    # 🔴 판본은 **메타 필드**다 — 해시 대상이 아니다 (C-32 ①). 기록은 남기되 승인의
    #    무결성 판정에는 넣지 않는다. 사이드카가 없으면 «미상» 으로 적는다(조용히 빼지 않는다).
    _meta = ms_path + ".meta.json"
    _rev = "미상 (사이드카 없음)"
    if os.path.exists(_meta):
        try:
            _rev = json.loads(io.open(_meta, encoding="utf-8").read()).get(
                "gate_skill_revision") or _rev
        except ValueError:
            _rev = "미상 (사이드카를 못 읽었다)"
    return {
        "ep": ep,
        "gate_skill_revision": _rev,
        "body_sha256": sha256_file(ms_path),
        "posts": [{"seq": s, "sha256": sha256_text(posts[s])} for s in sorted(posts)],
        "chain": sorted(posts),
        "drafted_by": "publish_threads.py --draft-approval",
        "drafted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S KST"),
        "manuscript": os.path.basename(ms_path),
        "_승인_방법": ("이 파일을 scripts\\move-approval.bat 으로 publish_approval\\ 로 옮기면 "
                   "그것이 승인이다. reports\\ 에 있는 동안은 승인이 아니다."),
    }


def check_approval(appr, ep, ms_path, posts):
    """3확인 + 원고·승인 정합. 어긋난 사유 목록을 돌려준다(빈 목록이면 통과)."""
    bad = []
    if appr.get("ep") != ep:
        bad.append("ep-mismatch: 승인 %r ≠ 대상 %r" % (appr.get("ep"), ep))
    got = sha256_file(ms_path)
    if appr.get("body_sha256") != got:
        bad.append("approval-stale: 원고 해시 불일치 (승인 %s… / 실물 %s…)"
                   % (str(appr.get("body_sha256"))[:12], got[:12]))
    chain = appr.get("chain") or []
    declared = {int(p["seq"]): p["sha256"] for p in (appr.get("posts") or [])}
    if sorted(chain) != sorted(declared):
        bad.append("chain 과 posts 의 seq 집합이 다르다: %s ≠ %s" % (sorted(chain), sorted(declared)))
    if set(declared) != set(posts):
        bad.append("승인 seq %s ≠ 원고 seq %s" % (sorted(declared), sorted(posts)))
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
        os.makedirs(d)                      # logs\ 아래다. publish_approval\ 이 아니다.
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

        params = {"media_type": "TEXT", "text": body}
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
_NO_MKDIR_CHECKED = []


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

    # ③ 승인 대조 — 정상 통과 / 축마다 하나씩 걸림 (역검증 케이스를 섞지 않는다)
    posts = {1: "가", 2: "나"}
    base = {"ep": "ep39", "body_sha256": sha256_file(p),
            "posts": [{"seq": 1, "sha256": sha256_text("가")},
                      {"seq": 2, "sha256": sha256_text("나")}],
            "chain": [1, 2]}
    assert check_approval(dict(base), "ep39", p, posts) == [], "정상 승인을 걸렀다"
    assert check_approval(dict(base, ep="ep40"), "ep39", p, posts), "ep 불일치를 놓쳤다"
    assert check_approval(dict(base, body_sha256="x" * 64), "ep39", p, posts), "원고 해시 불일치를 놓쳤다"
    assert check_approval(dict(base, chain=[1]), "ep39", p, posts), "chain/posts 어긋남을 놓쳤다"

    # ③-b 초안은 서명 자리를 만들지 않는다 — 만들면 «이미 서명됐다» 로 읽힌다
    d = build_draft("ep39", p, posts)
    assert d["ep"] == "ep39" and d["chain"] == [1, 2], d
    assert "signature" not in d and "signed_by" not in d, "초안이 서명 자리를 갖고 있다"
    assert check_approval(d, "ep39", p, posts) == [], "제 초안이 제 검사를 통과 못 한다"

    for q in (p, p2):
        os.remove(q)

    # ③-c 승인 폴더가 **세 자리에서 같은 값인가** — 파일을 열어 실제로 대조한다.
    #     선언만 맞추면 다음 사람이 한 곳만 고치고 지나간다. 그 «한 곳» 이 하필
    #     보안 경계였던 것이 이 조항의 계기다(2026-08-28).
    #     세 파일이 같은 폴더에 있을 때만 본다 — 시험 실행에서 파일이 없다고 죽지 않는다.
    here = os.path.dirname(os.path.abspath(__file__))
    bat = os.path.join(here, "move-approval.bat")
    ps1 = os.path.join(here, "publish-threads.ps1")
    if os.path.exists(bat) and os.path.exists(ps1):
        bt = io.open(bat, encoding="utf-8", errors="replace").read()
        pt = io.open(ps1, encoding="utf-8", errors="replace").read()
        m = re.search(r'set\s+"HQ=([^"]+)"', bt)
        assert m, "move-approval.bat 에서 HQ 를 못 찾았다"
        assert os.path.normcase(m.group(1).rstrip("\\")) == os.path.normcase(HQ), \
            "승인 폴더가 어긋난다 — 배치 HQ=%r 대 워커 HQ=%r" % (m.group(1), HQ)
        m2 = re.search(r"\$Hq\s*=\s*'([^']+)'", pt)
        assert m2, "publish-threads.ps1 에서 $Hq 를 못 찾았다"
        assert os.path.normcase(m2.group(1).rstrip("\\")) == os.path.normcase(HQ), \
            "승인 폴더가 어긋난다 — 래퍼 $Hq=%r 대 워커 HQ=%r" % (m2.group(1), HQ)

    # ③-d 절대경로인가 — 상대 계산으로 되돌아가면 사본마다 다른 폴더를 본다
    assert os.path.isabs(APPROVAL_DIR), "APPROVAL_DIR 이 절대경로가 아니다"
    assert APPROVAL_DIR == os.path.join(HQ, "publish_approval"), APPROVAL_DIR

    # ③-e **이 경로를 만드는 코드는 어디에도 없어야 한다 (2026-08-28 신설).**
    #
    #     2026-08-28 21:16:29 에 빈 `publish_approval\` 이 나타났다. 조사 결과
    #     어느 세션도 그 창에 돌지 않았고 스케줄도 없었으며 코드에도 만드는 자리가 없었다 —
    #     즉 **사람이 만든 것**으로 보이고, 그렇다면 정상이다. 문제는 그때
    #     «코드가 만든 것인지 사람이 만든 것인지 가릴 방법이 없었다» 는 것이다.
    #
    #     그래서 규칙을 **예외 없이** 세운다: 이 레포의 어떤 스크립트도 그 폴더를 만들지 않는다.
    #     «사람 도구만 만들어도 된다» 는 예외는 밖에서 검증할 수 없다 —
    #     배치는 자기를 누가 눌렀는지 증명하지 못한다. 예외가 없어야 grep 한 번으로 판정된다.
    #     🔴 주석은 빼고 본다. 첫 판이 «이 폴더를 만들지 않는다» 고 **설명하는 주석**에 걸렸다 —
    #     낱말만 세면 규칙을 적어 둔 자리가 규칙 위반으로 잡힌다(C-8 계열).
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    mk = re.compile(r"(makedirs|mkdir|New-Item[^\n]*Directory)", re.I)
    offenders = []
    for fn in sorted(os.listdir(scripts_dir)):
        if not fn.lower().endswith((".py", ".ps1", ".bat", ".cmd")):
            continue
        fp = os.path.join(scripts_dir, fn)
        if os.path.samefile(fp, os.path.abspath(__file__)):
            continue                      # 이 파일의 검사 코드 자신은 대상이 아니다
        for ln in io.open(fp, encoding="utf-8", errors="replace").read().splitlines():
            bare = ln.strip()
            if bare.startswith("#") or bare.startswith("::") or bare[:4].lower() == "rem ":
                continue                  # 주석은 코드가 아니다
            if "publish_approval" in bare and mk.search(bare):
                offenders.append("%s: %s" % (fn, bare[:90]))
    assert not offenders, ("publish_approval 을 만드는 코드가 있다 — 그 폴더는 사람이 만든다:\n  "
                           + "\n  ".join(offenders))
    _NO_MKDIR_CHECKED.append(scripts_dir)

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
    ap.add_argument("--approval-dir", default=None)
    ap.add_argument("--manuscript", default=None, help="원고 경로. 생략하면 reports 에서 찾는다")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--receipt-dir", default=None,
                    help="영수증 자리. 시험용 우회 — 쓰면 리포트가 그렇게 적는다")
    ap.add_argument("--publish", action="store_true",
                    help="🔴 실제 게시. 없으면 드라이런 — 기본값은 게시하지 않는다")
    ap.add_argument("--draft-approval", action="store_true",
                    help="승인 «초안» 을 reports\\<ep>.approval.json 으로 쓴다. 승인이 아니다")
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
                        "mode": "publish" if a.publish else "dryrun",
                        "draft_only": bool(a.draft_approval)}, base=_receipt_dir_early)
    # 같은 사실을 `run_audit.py` 가 읽는 꼴로도 남긴다 — 그 스크립트는 이 JSONL 을 모른다.
    write_stamp()

    # 자리는 위 상수로 고정한다. 인자는 **시험용 우회**일 뿐이고, 쓰면 리포트가 그렇게 적는다 —
    # 그렇게 적지 않으면 fixture 회차가 실제 회차처럼 읽힌다.
    appr_dir = a.approval_dir or APPROVAL_DIR
    out_dir = a.out_dir or REPORTS_DIR
    rcpt_dir = a.receipt_dir or RECEIPT_DIR
    overridden = [n for n, v in (("--approval-dir", a.approval_dir),
                                 ("--out-dir", a.out_dir),
                                 ("--receipt-dir", a.receipt_dir)) if v]
    appr_path = os.path.join(appr_dir, a.ep + ".json")

    lines = []

    def log(m):
        print(m)
        lines.append(m)

    def find_manuscript():
        if a.manuscript:
            return a.manuscript
        cand = sorted(f for f in os.listdir(out_dir)
                      if re.match(r"\d{4}-\d\d-\d\d_dist_%s\.md$" % a.ep, f))
        return os.path.join(out_dir, cand[-1]) if cand else None

    # --- 초안 만들기 — 승인이 아니다 -------------------------------------------
    if a.draft_approval:
        ms = find_manuscript()
        if not ms:
            print("🔴 원고를 못 찾았다: reports\\<날짜>_dist_%s.md" % a.ep)
            return 1
        draft = build_draft(a.ep, ms, parse_posts(ms))
        dpath = os.path.join(out_dir, a.ep + ".approval.json")
        io.open(dpath, "w", encoding="utf-8", newline="\n").write(
            json.dumps(draft, ensure_ascii=False, indent=1) + "\n")
        print("초안: %s" % dpath)
        print("포스트 %d건 · 원고 %s" % (len(draft["posts"]), draft["manuscript"]))
        print("🔴 **이것은 승인이 아니다.** JJ 가 원고 5포스트를 읽고 "
              "`scripts\\move-approval.bat` 으로 publish_approval\\ 로 옮겨야 승인이다.")
        print("STATUS: OK (초안 생성 — 승인 아님)")
        _finish(a.ep, a.receipt_dir or RECEIPT_DIR, "draft-only")
        return 0

    log("# Threads 발행 — %s · %s" % (a.ep, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    log("모드: **%s**" % ("실제 게시" if a.publish else "드라이런 (publish 미호출)"))
    log("승인 폴더: `%s`" % appr_dir)
    # 🔴 이 회차가 시작될 때 그 폴더가 있었는가. 끝에서 다시 봐서 «없었는데 생겼다» 면
    #    코드가 만든 것이므로 그 회차를 FAIL 로 찍는다 — 승인 폴더는 사람이 만든다.
    _DIR_WATCH[:] = [appr_dir, os.path.isdir(appr_dir)]
    log("승인 폴더 존재(회차 시작 시): %s" % ("예" if _DIR_WATCH[1] else "아니오"))
    if overridden:
        log("🔴 **기본 자리가 아니다 — 시험용 우회** (%s). 실제 회차가 아니다"
            % ", ".join(overridden))

    # 트리거 — 승인 파일이 없으면 워커는 뜨지 않는다 (에러 아님).
    # 🔴 **`publish_approval\` 만 본다.** reports\ 의 초안은 승인이 아니므로 여기서 찾지 않는다 —
    #    찾는 순간 «에이전트가 자기에게 내주는 허가» 가 되고 3확인 전체가 무너진다.
    if not os.path.exists(appr_path):
        log("승인 파일 없음 — 트리거가 없다: %s" % appr_path)
        draft_path = os.path.join(out_dir, a.ep + ".approval.json")
        if os.path.exists(draft_path):
            log("🔴 초안은 있다 (`%s`) — **초안은 승인이 아니다.** "
                "JJ 가 `scripts\\move-approval.bat` 으로 옮겨야 한다" % os.path.basename(draft_path))
        log("STATUS: OK (부분: 승인 파일 없음 — 발행 대상 아님)")
        _finish(a.ep, rcpt_dir, "no-approval")
        _write_report(out_dir, a.ep, lines)
        return 0
    appr = json.load(io.open(appr_path, encoding="utf-8"))

    ms = a.manuscript
    if not ms:
        cand = sorted(f for f in os.listdir(out_dir) if re.match(r"\d{4}-\d\d-\d\d_dist_%s\.md$" % a.ep, f))
        if not cand:
            log("원고를 못 찾았다: reports\\<날짜>_dist_%s.md" % a.ep)
            log("STATUS: FAIL manuscript-missing")
            _finish(a.ep, rcpt_dir, "manuscript-missing")
            _write_report(out_dir, a.ep, lines)
            return 1
        ms = os.path.join(out_dir, cand[-1])
    log("원고: %s" % os.path.basename(ms))

    posts = parse_posts(ms)
    bad = check_approval(appr, a.ep, ms, posts)
    if bad:
        for b in bad:
            log("🔴 3확인 실패 — %s" % b)
        log("STATUS: FAIL approval (%d건)" % len(bad))
        _finish(a.ep, rcpt_dir, "approval")
        _write_report(out_dir, a.ep, lines)
        return 1
    log("3확인 통과 — ep 일치 · 원고 해시 일치 · chain↔posts↔원고 seq 일치")
    log("승인 출처: `%s` — **이동이 곧 서명이다**" % appr_path)
    log("🔴 ② 는 이 스크립트가 재지 않는다 — «승인 파일이 `publish_approval\\` 에 있고 "
        "그 폴더에 대한 에이전트 쓰기·이동배치 실행이 **이 회차에** 거부됐음» 을 "
        "래퍼의 `permission_probe.py` 가 실증한다. "
        "그것은 «만들 수 없다» 가 아니라 **«이 회차에 만들지 못했다»** 다(§0 4층 ④)")

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


#: [승인 폴더 경로, 회차 시작 시 존재 여부]. 아래 `main` 이 **모든 출구에서** 다시 본다.
_DIR_WATCH = []


def main(argv=None):
    """`_run` 을 감싸 **어느 출구로 나가든** 승인 폴더가 새로 생겼는지 확인한다.

    🔴 첫 판은 이 검사를 함수 꼬리에만 뒀다가 **조기 반환 경로(승인 파일 없음)에서 건너뛰었다** —
    역검증에서 «안 걸렸다» 로 잡혔다. 실제 회차의 대부분이 그 조기 반환 경로이므로,
    꼬리에만 두면 거의 언제나 검사가 없는 것과 같다(정관 §0 «검사가 헛도는지»).
    """
    _DIR_WATCH[:] = []
    # `finally` 안에서 `return` 하지 않는다 — 그렇게 하면 `_run` 이 던진 예외를 조용히 삼킨다
    # (파이썬이 SyntaxWarning 으로 경고하는 자리이고, 정관 §0 «조용히 실패하는 코드» 그대로다).
    # 판정만 `finally` 에서 세우고, 값은 밖에서 돌려준다.
    created = [False]
    try:
        rc = _run(argv)
    finally:
        created[0] = (len(_DIR_WATCH) == 2 and (not _DIR_WATCH[1])
                      and os.path.isdir(_DIR_WATCH[0]))
        if created[0]:
            for line in ("🔴 승인 폴더가 이 회차 도중에 생겼다: %s" % _DIR_WATCH[0],
                         "   그 폴더는 사람이 만든다 — 코드가 만들면 «이동이 곧 서명» 이 성립하지 않는다.",
                         "STATUS: FAIL approval-dir-created"):
                print(line)
    return 1 if created[0] else rc


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    raise SystemExit(main())
