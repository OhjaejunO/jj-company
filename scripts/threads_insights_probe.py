# -*- coding: utf-8 -*-
r"""Threads 인사이트 **조회 가능 여부**를 재는 프로브 (A등급 · 읽기 전용).

설계도 §2 「계기를 먼저 심는다」의 선행 조사다. 성과 수집 워커를 만들지 말지 정하려면
**기존 토큰으로 무엇이 읽히는지**를 먼저 알아야 하고, 그것은 문서를 읽어서가 아니라
**호출해서** 안다 (정관 §0 «추측 금지 · 확인 안 되면 확인 불가»).

🔴 **발행을 못 하는 근거는 «안 부른다»가 아니라 «GET 밖에 못 한다»다.** Threads 발행은
`POST /me/threads` → `POST /me/threads_publish` 두 단계이고 **둘 다 POST** 다. 이 프로브는
`send()` 가 메서드를 `GET` 으로 못박고 `assert_get()` 이 매 호출 전에 확인한다 —
경로 이름으로 거르면 `GET /me/threads`(게시물 **목록 조회**)까지 같이 막혀 «막힌 것»을
«없는 것»으로 오독하게 된다. 정관 §0 4층 ①(구조로 닫기) 자리다.

🔴 **토큰 값은 어디에도 찍지 않는다.** 출력·예외 문자열에서 지운다(`scrub`).

돌리기:  py scripts\threads_insights_probe.py
역검증:  py scripts\threads_insights_probe.py --self-test
"""
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "https://graph.threads.net/v1.0"


class NotAGet(Exception):
    pass


def assert_get(method):
    """GET 이 아니면 거부한다.

    🔴 «부르지 않는다»는 주석이 아니라 **판정**이어야 한다. 주석은 다음 사람이 한 줄
    더할 때 아무 저항도 하지 않는다.
    """
    if method != "GET":
        raise NotAGet("이 프로브는 GET 만 한다 — 요청 메서드: %s" % method)
    return True


def load_token():
    """`publish_threads.load_token` 과 **같은 자리**에서 읽는다 (환경변수 → HKCU)."""
    t = os.environ.get("THREADS_TOKEN")
    if not t:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                t = winreg.QueryValueEx(k, "THREADS_TOKEN")[0]
        except Exception:                                      # noqa: BLE001
            t = None
    t = (t or "").strip()
    if not t or (t.startswith("<") and t.endswith(">")):
        return None
    return t


def scrub(s, token):
    s = str(s)
    if token:
        s = s.replace(token, "<TOKEN>")
    return s


def send(path, token, method="GET", **params):
    """요청 하나. 돌려주는 것은 `(HTTP코드, 본문dict 또는 원문)` 이다."""
    assert_get(method)
    params["access_token"] = token
    url = "%s/%s?%s" % (BASE, path.lstrip("/"), urllib.parse.urlencode(params))
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body
    except Exception as e:                                     # noqa: BLE001
        return 0, {"error": {"message": scrub(e, token)}}


def metric_value(payload):
    """인사이트 응답에서 값을 꺼낸다. **모양이 둘**이라 둘 다 본다.

    🔴 값을 못 꺼내면 «?» 로 넘기지 않고 **본 키를 그대로 돌려준다.** 200 인데 값이 안
    보이는 상태를 「?」로 적으면 «장치가 값을 담는지» 를 영영 알 수 없다 (정관 §0).
    """
    data = (payload.get("data") or []) if isinstance(payload, dict) else []
    if not data:
        return None, "🔴 200 인데 data 가 비었다"
    d = data[0]
    if isinstance(d.get("total_value"), dict) and "value" in d["total_value"]:
        return d["total_value"]["value"], ""
    vals = d.get("values")
    if isinstance(vals, list) and vals and isinstance(vals[0], dict) and "value" in vals[0]:
        return vals[0]["value"], "(values[] 꼴)"
    return None, "🔴 값 키를 못 찾음 — 키: %s" % ",".join(sorted(d.keys()))


def err(payload):
    if isinstance(payload, dict) and "error" in payload:
        e = payload["error"]
        return "%s / %s" % (e.get("code", "?"), (e.get("message") or "")[:110])
    return ""


def line(label, code, payload, token, extra=""):
    mark = "OK  " if code == 200 else "FAIL"
    print("  %s %-44s HTTP %-4s %s" % (mark, label, code, scrub(extra or err(payload), token)))
    return code == 200


def _self_test():
    """역검증 — «막는 검사가 실제로 막는가»와 «통과해야 하는 것은 통과하는가» 양쪽.

    한쪽만 보면 **전부 거부하는 프로브**도 정상으로 보인다 (정관 §0).
    """
    print("[R] 역검증 — 메서드 게이트")
    bad = 0
    for method, should_pass, why in [
            ("GET", True, "조회는 통과해야 한다"),
            ("POST", False, "🔴 발행 1단계가 POST 다 — 막혀야 한다"),
            ("DELETE", False, "🔴 삭제도 막혀야 한다"),
            ("PUT", False, "🔴 수정도 막혀야 한다")]:
        try:
            assert_get(method)
            got = True
        except NotAGet:
            got = False
        ok = got == should_pass
        bad += 0 if ok else 1
        print("  %s %-7s 통과=%-5s  %s" % ("OK  " if ok else "FAIL", method, got, why))

    print("[R] 역검증 — 토큰 가리기")
    fake = "TOKENVALUE123"
    hid = scrub("error: access_token=%s expired" % fake, fake)
    ok = fake not in hid and "<TOKEN>" in hid
    bad += 0 if ok else 1
    print("  %s 출력에서 토큰이 지워진다  %s" % ("OK  " if ok else "FAIL", hid))
    ok2 = scrub("아무 일 없는 문장", fake) == "아무 일 없는 문장"
    bad += 0 if ok2 else 1
    print("  %s 토큰이 없는 문장은 그대로 둔다 (반대쪽 — 전부 지우는 함수가 아님)"
          % ("OK  " if ok2 else "FAIL"))

    print()
    print("STATUS: %s" % ("OK" if not bad else "FAIL self-test %d건" % bad))
    return 0 if not bad else 1


def main():
    if "--self-test" in sys.argv:
        return _self_test()

    token = load_token()
    print("# Threads 인사이트 조회 가능성 프로브 (읽기 전용 · GET 만)")
    print()
    if not token:
        print("  FAIL THREADS_TOKEN 없음 — 이 기계에서는 잴 수 없다")
        print()
        print("STATUS: FAIL no-token")
        return 1
    print("  토큰 있음 (길이 %d · 값은 찍지 않는다)" % len(token))
    print()

    print("[1] 신원")
    code, me = send("me", token, fields="id,username")
    line("GET /me", code, me, token,
         "@%s" % me.get("username", "?") if code == 200 else "")

    print("[2] 사용자 인사이트 — 채널 층 (스코어카드 상단)")
    got_user = {}
    for m in ["views", "likes", "replies", "reposts", "quotes",
              "followers_count", "follower_demographics"]:
        code, p = send("me/threads_insights", token, metric=m)
        if code == 200:
            v, note = metric_value(p)
            got_user[m] = v
            line("metric=%s" % m, code, p, token,
                 ("값 %s %s" % (v, note)).strip() if v is not None else note)
        else:
            line("metric=%s" % m, code, p, token)

    print("[3] 게시물 목록 (GET — 발행은 POST 라 이 경로로 못 나간다)")
    code, ml = send("me/threads", token,
                    fields="id,permalink,timestamp,media_type", limit=5)
    posts = (ml.get("data") or []) if code == 200 else []
    line("GET /me/threads", code, ml, token, "%d건" % len(posts) if code == 200 else "")
    for p in posts[:5]:
        print("       - %s  %s  %s" % (p.get("timestamp", "?")[:19],
                                       p.get("media_type", "?"), p.get("id")))

    print("[4] 게시물별 인사이트 — 편별 층")
    if posts:
        pid = posts[0]["id"]
        for m in ["views", "likes", "replies", "reposts", "quotes", "shares"]:
            code, p = send("%s/insights" % pid, token, metric=m)
            if code != 200:
                line("metric=%s" % m, code, p, token)
                continue
            v, note = metric_value(p)
            line("metric=%s" % m, code, p, token,
                 ("값 %s %s" % (v, note)).strip() if v is not None else note)
    else:
        print("  SKIP 게시물 목록을 못 얻어 대상 0건 — «값이 0» 이 아니라 «못 쟀다»")

    print()
    print("[요약]")
    live = [m for m, v in got_user.items() if v is not None]
    empty = [m for m, v in got_user.items() if v is None]
    print("  사용자 지표 — 값이 온 것: %s" % (", ".join(live) if live else "없음"))
    print("  사용자 지표 — 200 인데 빈 것: %s" % (", ".join(empty) if empty else "없음"))
    print("  게시물 목록: %d건" % len(posts))
    print()
    print("STATUS: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
