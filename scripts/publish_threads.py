# -*- coding: utf-8 -*-
r"""Threads 발행 워커 — 승인된 편 1건의 텍스트 스레드를 체인 순서대로 올린다.

정본 명세: `docs\workers\publish-threads.md`. **그 문서가 규칙이고 이 파일은 그 실행체다.**

    py scripts\publish_threads.py --ep ep39                     ← 드라이런 (기본값)
    py scripts\publish_threads.py --ep ep39 --publish           ← 실제 게시
    py scripts\publish_threads.py --self-test                   ← 검사기 자체 시험

## 왜 에이전트가 아니라 스크립트인가

승인 파일과 원고가 정해지면 **남은 일에 판단이 없다** — 해시를 맞추고, 컨테이너를 만들고,
`FINISHED` 를 기다리고, 순서대로 올린다. 정답이 있는 자리에 모델을 넣지 않는다
(정관 §0 · `skill-drift-audit` 과 같은 성격). 모델이 끼면 «원고를 조금 고쳐서 올리는» 길이 생긴다.

## 🔴 기본값이 드라이런이다 (§0 4층 ①)

`--publish` 를 **명시하지 않으면 어떤 경우에도 게시하지 않는다.** 금지를 규율이 아니라
기본값으로 옮긴 것이다 — 실수로 돌려도 바깥으로 나가지 않는다.

## 🔴 이 스크립트가 증명하지 *못* 하는 것 (§0 4층 ④)

- **승인 파일의 서명을 검증하지 않는다.** 3확인 ② 의 판정은 «승인 폴더에 못 쓴다» 이고
  그것을 재는 것은 `scripts\permission_probe.py` 다 — 워커 기동 **전에** 래퍼가 돌린다.
  여기서 서명을 다시 검사하는 척하지 않는다.
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

#: 🔴 publish 는 **경로의 마지막 세그먼트 일치**로만 판정한다 (C-8 2026-08-28 사례).
#: «문자열 포함» 으로 짰다가 `threads_publishing_limit`(쿼터 조회)까지 막혀 조사 한 항목이
#: «확인 불가» 로 끝날 뻔했다. 넓게 잡힌 금지는 조사를 막고, 막힌 자리가 «불가능» 으로 오독된다.
PUBLISH_SEGMENTS = {"threads_publish"}

#: `FINISHED` 대기 상한 — **잠정값이다.** 조사 회차 표본이 2건뿐이라 «정상값» 을 모른다.
#: 실제 회차 로그가 쌓이면 그것으로 조인다(명세 «status 대기» 절).
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


def run_chain(api, uid, ep, ms_path, appr, log, publish):
    """seq 마다 [해시 대조 → 컨테이너 → FINISHED 대기 → publish → id 회수] 한 묶음.

    🔴 **원고를 묶음마다 디스크에서 다시 읽는다.** 처음 한 번만 읽어 메모리에 들고 있으면
    «직전마다 대조한다» 가 **늘 같은 값끼리 견주는 장식**이 된다 — 도는 도중에 파일이 바뀌어도
    영원히 안 걸린다. 체인은 포스트마다 몇 초에서 몇 십 초가 걸리고, 그 사이가 실제로 열려 있다.
    (정관 §0 «감지 장치가 실제로 값을 담는지».)
    """
    declared = {int(p["seq"]): p["sha256"] for p in appr["posts"]}
    chain = list(appr["chain"])
    done, parent = [], None
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

        st, r = api.call("POST", "%s/%s/threads_publish" % (API, uid), {"creation_id": cid})
        if st != 200 or not isinstance(r, dict) or "id" not in r:
            return done, "FAIL publish P%d (HTTP %s · %s)" % (seq, st, api.scrub(json.dumps(r, ensure_ascii=False))[:160])
        mid = r["id"]
        done.append({"seq": seq, "container_id": cid, "media_id": mid, "published": True})
        log("    게시 media_id=%s" % mid)
        parent = mid
    return done, None


# ---------------------------------------------------------------- 자체 검사
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
    for q in (p, p2):
        os.remove(q)

    # ④ 드라이런에서 publish 가 실제로 막히는가 (토큰 없이도 되는 검사)
    api = Api("dummy", allow_publish=False)
    try:
        api.call("POST", "/v1.0/1/threads_publish", {"creation_id": "1"})
        raise AssertionError("드라이런인데 publish 가 통과했다")
    except Blocked:
        pass
    assert Api("dummy", allow_publish=True) is not None
    return True


# ---------------------------------------------------------------- main
def main(argv=None):
    _selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep", help="대상 편 (예: ep39)")
    ap.add_argument("--approval-dir", default=None)
    ap.add_argument("--manuscript", default=None, help="원고 경로. 생략하면 reports 에서 찾는다")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--publish", action="store_true",
                    help="🔴 실제 게시. 없으면 드라이런 — 기본값은 게시하지 않는다")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        print("자체 검사 통과")
        return 0
    if not a.ep:
        raise SystemExit("--ep 가 필요하다")

    hq = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    appr_dir = a.approval_dir or os.path.join(hq, "publish_approval")
    out_dir = a.out_dir or os.path.join(hq, "reports")
    appr_path = os.path.join(appr_dir, a.ep + ".json")

    lines = []

    def log(m):
        print(m)
        lines.append(m)

    log("# Threads 발행 — %s · %s" % (a.ep, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    log("모드: **%s**" % ("실제 게시" if a.publish else "드라이런 (publish 미호출)"))

    # 트리거 — 승인 파일이 없으면 워커는 뜨지 않는다 (에러 아님)
    if not os.path.exists(appr_path):
        log("승인 파일 없음 — 트리거가 없다: %s" % appr_path)
        log("STATUS: OK (부분: 승인 파일 없음 — 발행 대상 아님)")
        return 0
    appr = json.load(io.open(appr_path, encoding="utf-8"))

    ms = a.manuscript
    if not ms:
        cand = sorted(f for f in os.listdir(out_dir) if re.match(r"\d{4}-\d\d-\d\d_dist_%s\.md$" % a.ep, f))
        if not cand:
            log("원고를 못 찾았다: reports\\<날짜>_dist_%s.md" % a.ep)
            log("STATUS: FAIL manuscript-missing")
            return 1
        ms = os.path.join(out_dir, cand[-1])
    log("원고: %s" % os.path.basename(ms))

    posts = parse_posts(ms)
    bad = check_approval(appr, a.ep, ms, posts)
    if bad:
        for b in bad:
            log("🔴 3확인 실패 — %s" % b)
        log("STATUS: FAIL approval (%d건)" % len(bad))
        return 1
    log("3확인 통과 — ep 일치 · 원고 해시 일치 · chain↔posts↔원고 seq 일치")
    log("🔴 ② «에이전트가 만들지 않았을 것» 은 이 스크립트가 재지 않는다 — "
        "래퍼의 `permission_probe.py` 가 회차마다 실증한다")

    token = load_token()
    api = Api(token, allow_publish=a.publish)
    st, me = api.call("GET", API + "/me", {"fields": "id,username"})
    if st != 200:
        log("계정 조회 실패 HTTP %s" % st)
        log("STATUS: FAIL account")
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

    try:
        done, err = run_chain(api, uid, a.ep, ms, appr, log, a.publish)
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

    rep = os.path.join(out_dir, "%s_publish_%s.md" % (datetime.date.today().isoformat(), a.ep))
    io.open(rep, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("report: %s" % rep)
    return rc


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    raise SystemExit(main())
