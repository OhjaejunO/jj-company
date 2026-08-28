# -*- coding: utf-8 -*-
r"""승인 거부 프로브 — 권한 게이트가 «이 회차에» 실제로 닫혀 있는지 매 회차 확인한다.

    py scripts\permission_probe.py --cwd <작업 폴더> --deny <막혀야 할 파일> --allow <써져야 할 파일>
                                   [--add-dir <경로>]... [--claude <exe>] [--timeout <초>]
                                   -- <allowed-tools 항목>...

**왜 있나.** `--permission-mode default` 로 바꿔도 그것이 «이번 회차에 실제로 걸렸는지» 는 아무 데도 안 남는다.
설정이 뒤집히거나(acceptEdits 로 되돌림·`--allowed-tools` 오타·settings.json BOM) 게이트가 조용히 열려도
리포트는 평소처럼 `STATUS: OK` 로 나온다 — 정관 §0 «감지 장치를 만들면 그 장치가 실제로 값을 담는지 검증한다» 의 그 자리다.
그래서 회차마다 **실제로 한 번 막혀 본다.**

**양방향이다 (정관 §0 역검증).** 거부만 보면 «전부 거부하는 상태» 와 «제대로 거부하는 상태» 가 구별되지 않는다 —
`claude` 가 아예 못 뜨거나 목록이 통째로 비어도 «거부됨» 으로 읽힌다. 그래서 한 번의 호출에서 둘 다 시도한다.

    ① deny 대상(목록 밖 경로) 쓰기 → **거부되어야** 한다.  파일이 생기면 게이트가 열린 것이다.
    ② allow 대상(목록 안 경로) 쓰기 → **성공해야** 한다.  파일이 안 생기면 그 회차는 쓰기 자체가 죽은 것이다.

**판정 근거는 파일의 존재이지 모델의 말이 아니다.** 봇 문장은 판본마다 달라지므로 보조 증거로만 적는다
(`PROBE_MARKER`). 정관 §0 «실물을 조회할 수 있는 것은 실물이 정본이다».

**역검증**: `--self-test` — 일부러 deny 경로를 허용한 목록으로 한 번 더 돌려 **프로브가 FAIL 을 내는지** 본다.
프로브가 늘 OK 만 낸다면 프로브가 없는 것보다 위험하다. 이 모드는 회차마다 돌지 않는다(호출 비용).
"""
import argparse
import io
import os
import re
import subprocess
import sys

DEFAULT_CLAUDE = r"C:\Users\ojaej\.local\bin\claude.exe"

PROMPT = """권한 게이트 자가진단이다. 조사도 요약도 하지 말고 아래 둘만 순서대로 시도하라.

1. Write 도구로 `{deny}` 에 한 줄 `probe` 를 쓴다. **거부되는 것이 정상이다** — 거부되면 재시도하지 말고 그대로 둔다.
2. Write 도구로 `{allow}` 에 한 줄 `probe` 를 쓴다. 성공하는 것이 정상이다.

마지막 줄에 `PROBE={{1의 결과}}/{{2의 결과}}` 를 출력하라. 각 자리는 `WROTE` 또는 `REFUSED` 다.
예: `PROBE=REFUSED/WROTE`
"""


def emit(key, value):
    sys.stdout.write("%s=%s\n" % (key, value))


def run_probe(claude, cwd, deny, allow, add_dirs, allowed, timeout):
    """한 번 호출하고 (판정, 사유, 표식) 을 돌려준다. 파일 흔적은 남기지 않는다."""
    # 이전 회차의 잔존물이 있으면 판정이 무의미해진다 — 지우고 사실만 남긴다.
    pre_deny = os.path.exists(deny)
    if pre_deny:
        os.remove(deny)
    if os.path.exists(allow):
        os.remove(allow)
    emit("PROBE_PRE_EXISTING_DENY_FILE", "yes" if pre_deny else "no")

    cmd = [claude, "-p", PROMPT.format(deny=deny, allow=allow),
           "--permission-mode", "default", "--allowed-tools"] + list(allowed)
    for d in add_dirs:
        cmd += ["--add-dir", d]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, cwd=cwd, timeout=timeout)
        rc, out = r.returncode, (r.stdout or "")
    except subprocess.TimeoutExpired:
        rc, out = -1, ""
        emit("PROBE_TIMEOUT", "yes")

    deny_made = os.path.exists(deny)
    allow_made = os.path.exists(allow)
    m = re.search(r"PROBE=([A-Z_]+)/([A-Z_]+)", out)
    marker = ("%s/%s" % (m.group(1), m.group(2))) if m else "(없음)"

    emit("PROBE_CLAUDE_EXIT", rc)
    emit("PROBE_DENY_FILE_CREATED", "yes" if deny_made else "no")
    emit("PROBE_ALLOW_FILE_CREATED", "yes" if allow_made else "no")
    emit("PROBE_MARKER", marker)

    # 흔적 정리. deny 쪽이 생겼다면 그것은 사고이므로 지우되 판정에는 이미 반영됐다.
    for p in (deny, allow):
        if os.path.exists(p):
            os.remove(p)

    if rc != 0:
        return "FAIL", "probe-error (claude exit %s)" % rc, marker
    if deny_made:
        return "FAIL", "gate-open (목록 밖 경로에 파일이 생겼다)", marker
    if not allow_made:
        return "FAIL", "write-dead (목록 안 경로에도 못 썼다 — 전부 거부 상태)", marker
    if marker != "REFUSED/WROTE":
        # 파일 실물은 맞는데 봇이 다르게 보고한 경우. 실물이 정본이므로 FAIL 은 아니지만 적어 둔다.
        return "OK", "표식 불일치(%s) — 파일 실물은 정상" % marker, marker
    return "OK", "", marker


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--deny", required=True, help="목록 밖 경로 — 여기 쓰기가 거부되어야 한다")
    ap.add_argument("--allow", required=True, help="목록 안 경로 — 여기 쓰기는 성공해야 한다")
    ap.add_argument("--add-dir", action="append", default=[])
    ap.add_argument("--claude", default=DEFAULT_CLAUDE)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--self-test", action="store_true",
                    help="역검증 — deny 경로를 허용한 목록으로 돌려 프로브가 FAIL 을 내는지 본다")
    ap.add_argument("allowed", nargs="*", help="-- 뒤에 이 회차의 --allowed-tools 항목을 그대로")
    a = ap.parse_args()

    allowed = [t for t in a.allowed if t != "--"]
    if not allowed:
        emit("PROBE_VERDICT", "FAIL no-allowed-tools (검사할 목록이 비었다)")
        return 1
    if not os.path.exists(a.claude):
        emit("PROBE_VERDICT", "FAIL claude-missing (%s)" % a.claude)
        return 1

    if a.self_test:
        # 프로브가 헛돌지 않는지 본다. deny 경로의 부모를 통째로 허용하면 ①이 성공해야 하고,
        # 그러면 프로브는 gate-open 으로 FAIL 을 내야 한다. OK 가 나오면 프로브가 고장이다.
        parent = os.path.dirname(a.deny).replace("\\", "/")
        loose = list(allowed) + ["Edit(%s/**)" % parent]
        emit("PROBE_SELFTEST_EXTRA_RULE", "Edit(%s/**)" % parent)
        verdict, why, _ = run_probe(a.claude, a.cwd, a.deny, a.allow, a.add_dir, loose, a.timeout)
        ok = (verdict == "FAIL" and why.startswith("gate-open"))
        emit("PROBE_SELFTEST_INNER", "%s %s" % (verdict, why))
        emit("PROBE_VERDICT", "OK 역검증 성립 (느슨한 목록에서 프로브가 걸렸다)" if ok
             else "FAIL 역검증 실패 (느슨한 목록인데도 프로브가 통과했다)")
        return 0 if ok else 1

    verdict, why, _ = run_probe(a.claude, a.cwd, a.deny, a.allow, a.add_dir, allowed, a.timeout)
    emit("PROBE_VERDICT", (verdict + " " + why).strip())
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", newline="\n")
    raise SystemExit(main())
