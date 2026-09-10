# -*- coding: utf-8 -*-
"""턴 감사 — 「뭐 하나 하는데 오래 걸린다」를 되풀이해서 잴 수 있게 만든 자.

2026-09-10 JJ 지시(「최적화를 한번 해야할것 같아」)로 만든 1회성 조사를 상시화한 것이다.
**고치기 전에 기준선을 박아 두고, 고친 뒤 같은 축으로 다시 재기 위해서** 있다 —
숫자 없이 «빨라진 것 같다» 고 적으면 §0 «감지 장치가 값을 담는지 검증한다» 에 걸린다.

재는 것
  ① 활성 응답시간  사람이 한마디 하고 응답이 끝나기까지. **유휴는 뺀다**
                   (인접 이벤트 간격이 IDLE 초를 넘으면 사람이 자리를 비웠거나
                    백그라운드를 기다린 것이라 «오래 걸린다» 의 원인이 아니다)
  ② 턴당 도구 호출 수 — 활성시간을 끌어올리는 실제 변수
  ③ Bash 용도 분포  — «찾고 읽기» 대 «만들기» 의 비율

🔴 **읽는 것은 타임스탬프와 도구 이름뿐이다.** 프롬프트·결과 내용은 열지 않는다(정관 §6).
   Bash 명령은 **분류 라벨로만** 세고 원문을 리포트에 남기지 않는다 — 경로·인자에 무엇이
   섞여 있을지 모르기 때문이다.

쓰는 법
    py scripts\turn_audit.py                     # 최근 12세션 요약
    py scripts\turn_audit.py --sessions 4        # 최근 4세션 (고친 뒤 재기)
    py scripts\turn_audit.py --json baseline.json
    py scripts\turn_audit.py --self-test         # 역검증

🔴 **이 자는 한 번에 못 맞혔다.** 1차는 «사람 메시지 → 다음 사람 메시지» 로 재서 사람이
   자리를 비운 42시간이 «대기» 로 들어갔고, 2차는 응답 끝까지로 고쳤는데도 백그라운드 대기가
   남았다. 3차에서 유휴를 잘라 내고서야 값이 섰다. `--self-test` 의 첫 케이스가 그 함정이다.
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
IDLE = 300.0          # 초. 이보다 긴 공백은 «작업» 이 아니다

#: Bash 명령 분류. 위에서부터 처음 맞는 것 하나로 센다.
#: «찾기» 로 표시된 것이 늘면 색인이 없다는 뜻이다.
BASH_KINDS = [
    (r"\bverify\.py",                       "게이트",           "만들기"),
    (r"\bbuild_ep\d+\.py",                  "편 빌드",          "만들기"),
    (r"kitchain\.py",                       "킷 체인",          "만들기"),
    (r"deliver\.py",                        "드라이브 전달",     "만들기"),
    (r"publish_tail\.py",                   "발행 꼬리",        "만들기"),
    (r"ledger_check\.py|publog_check\.py",  "원장·발행로그 검사", "만들기"),
    (r"patch_\w+\.py|scratchpad[\\/].*\.py", "패치 스크립트",    "고치기"),
    (r"\bgh pr\b",                          "gh pr",           "왕복"),
    (r"\bgit (commit|push|add|status|log|diff)\b", "git",       "왕복"),
    (r"\bgrep\b|\brg\b",                    "grep",            "찾기"),
    (r"\bsed -n\b|\bcat |\bhead |\btail |\bwc ", "파일 들여다보기", "찾기"),
    (r"\bls\b|\bfind \b",                   "ls·find",         "찾기"),
    (r"\bpy -c\b",                          "py -c 한 줄",      "고치기"),
]


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def is_human(rec):
    """사람이 실제로 친 메시지인가. tool_result 로 돌아온 user 턴은 사람이 아니다."""
    if rec.get("type") != "user":
        return False
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip())
    if isinstance(c, list):
        return not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)
    return False


def human_text(rec):
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    return "\n".join(b.get("text") or "" for b in (c or [])
                     if isinstance(b, dict) and b.get("type") == "text")


def is_synthetic(txt):
    """시스템이 끼워 넣은 자동 턴 — 요약 재개·리마인더는 사람 턴이 아니다."""
    t = txt.lstrip()
    return t.startswith("<") or "session is being continued" in t.lower()


def classify(cmd):
    for pat, label, group in BASH_KINDS:
        if re.search(pat, cmd):
            return label, group
    return "기타", "기타"


def scan_records(records, idle=IDLE):
    """레코드 열 → 턴 목록. 파일에서 읽든 자체 검사에서 만들든 여기로 들어온다."""
    turns = []
    cur = None
    for r in records:
        t = r.get("timestamp")
        if not t:
            continue
        try:
            now = ts(t)
        except Exception:
            continue

        if is_human(r):
            if is_synthetic(human_text(r)):
                continue
            cur = {"start": now, "last": now, "active": 0.0,
                   "tools": Counter(), "bash": Counter(), "group": Counter()}
            turns.append(cur)
            continue
        if cur is None:
            continue

        gap = (now - cur["last"]).total_seconds()
        if 0 <= gap <= idle:
            cur["active"] += gap
        cur["last"] = now

        for b in ((r.get("message") or {}).get("content") or []):
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            name = b.get("name") or "?"
            cur["tools"][name] += 1
            if name == "Bash":
                cmd = re.sub(r"\s+", " ", ((b.get("input") or {}).get("command") or ""))[:500]
                label, group = classify(cmd)
                cur["bash"][label] += 1
                cur["group"][group] += 1
    return turns


def scan_file(path, idle=IDLE):
    recs = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    return scan_records(recs, idle)


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return 0.0
    return xs[min(int(q * len(xs)), len(xs) - 1)]


def summarize(turns):
    if not turns:
        return None
    act = [t["active"] / 60 for t in turns]
    ntool = [sum(t["tools"].values()) for t in turns]
    total = sum(act)
    order = sorted(range(len(turns)), key=lambda i: -act[i])
    top12 = max(1, len(turns) // 8)

    bash = Counter()
    group = Counter()
    for t in turns:
        bash += t["bash"]
        group += t["group"]
    nbash = sum(bash.values()) or 1

    return {
        "turns": len(turns),
        "active_hours": round(total / 60, 1),
        "median_min": round(pct(act, 0.5), 1),
        "p75_min": round(pct(act, 0.75), 1),
        "p90_min": round(pct(act, 0.9), 1),
        "max_min": round(max(act), 1),
        "tools_median": pct(ntool, 0.5),
        "tools_p90": pct(ntool, 0.9),
        "tools_max": max(ntool),
        #: 긴 턴 12% 가 시간의 몇 %를 먹나 — 낮아질수록 «몰림» 이 풀린 것이다
        "top12pct_share": round(100 * sum(act[i] for i in order[:top12]) / (total or 1)),
        "bash_calls": sum(bash.values()),
        #: 🔴 핵심 축. 찾기 비중이 내려가야 색인이 값을 한 것이다
        "find_share": round(100 * group.get("찾기", 0) / nbash),
        "make_share": round(100 * group.get("만들기", 0) / nbash),
        "fix_share": round(100 * group.get("고치기", 0) / nbash),
        "bash_top": bash.most_common(10),
    }


def report(s, title="턴 감사"):
    print("== %s ==" % title)
    print("사람 턴 %d개 · 활성 작업시간 %.1f시간 (유휴 %d분↑ 제외)"
          % (s["turns"], s["active_hours"], IDLE / 60))
    print()
    print("한 번 시키면 실제로 도는 시간")
    print("  중앙 %.1f분 · 상위25%% %.1f분 · 상위10%% %.1f분 · 최장 %.1f분"
          % (s["median_min"], s["p75_min"], s["p90_min"], s["max_min"]))
    print("턴당 도구 호출")
    print("  중앙 %d회 · 상위10%% %d회 · 최다 %d회"
          % (s["tools_median"], s["tools_p90"], s["tools_max"]))
    print("  긴 턴 12%%가 활성시간의 %d%% 를 먹는다" % s["top12pct_share"])
    print()
    print("Bash %d회의 용도" % s["bash_calls"])
    print("  🔴 찾기 %d%% · 만들기 %d%% · 고치기 %d%%"
          % (s["find_share"], s["make_share"], s["fix_share"]))
    for k, v in s["bash_top"]:
        print("     %-18s %5d회" % (k, v))


# ---------------------------------------------------------------- 역검증
def _rec(kind, minutes, tool=None, cmd=None, text=None):
    base = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    r = {"type": kind, "timestamp": (base + timedelta(minutes=minutes)).isoformat()}
    if kind == "user":
        r["message"] = {"content": text if text is not None else [{"type": "tool_result"}]}
    else:
        c = []
        if tool:
            c.append({"type": "tool_use", "name": tool, "id": "x",
                      "input": {"command": cmd} if cmd else {}})
        r["message"] = {"content": c}
    return r


def self_test():
    fails = []

    def ok(name, cond, note=""):
        print("  %-4s %s  %s" % ("OK" if cond else "FAIL", name, note))
        if not cond:
            fails.append(name)

    # ① 🔴 유휴가 활성시간에 들어가면 안 된다 — 이 자가 두 번 틀렸던 자리
    t = scan_records([
        _rec("user", 0, text="해줘"),
        _rec("assistant", 1, tool="Bash", cmd="grep foo"),
        _rec("assistant", 600),                       # 10시간 뒤 재개
        _rec("assistant", 601),
    ])
    ok("유휴 10시간이 활성에서 빠진다",
       len(t) == 1 and t[0]["active"] < 130,
       "활성 %.0f초 (전체 간격은 36,060초)" % t[0]["active"])

    # ② 반대쪽 — 쉼 없이 도는 구간은 **빠지면 안 된다**
    t = scan_records([_rec("user", 0, text="해줘")] +
                     [_rec("assistant", i, tool="Bash", cmd="cat x") for i in range(1, 11)])
    ok("연속 10분은 그대로 잡힌다", 540 <= t[0]["active"] <= 600,
       "활성 %.0f초" % t[0]["active"])

    # ③ tool_result 로 돌아온 user 턴은 사람 턴이 아니다
    t = scan_records([
        _rec("user", 0, text="해줘"),
        _rec("assistant", 1, tool="Bash", cmd="ls"),
        _rec("user", 2),                              # tool_result
        _rec("assistant", 3, tool="Bash", cmd="ls"),
    ])
    ok("tool_result 는 새 턴을 열지 않는다", len(t) == 1, "턴 %d개" % len(t))

    # ④ 자동 재개 턴도 사람 턴이 아니다
    t = scan_records([
        _rec("user", 0, text="해줘"),
        _rec("user", 1, text="<system-reminder>뭐라뭐라</system-reminder>"),
        _rec("assistant", 2, tool="Bash", cmd="ls"),
    ])
    ok("system-reminder 턴은 세지 않는다", len(t) == 1, "턴 %d개" % len(t))

    # ⑤ 분류가 «찾기» 와 «만들기» 를 실제로 가르는가
    t = scan_records([
        _rec("user", 0, text="해줘"),
        _rec("assistant", 1, tool="Bash", cmd="grep -n foo bar.py"),
        _rec("assistant", 2, tool="Bash", cmd="sed -n '1,20p' x.md"),
        _rec("assistant", 3, tool="Bash", cmd="py verify.py"),
    ])
    s = summarize(t)
    ok("찾기 2 · 만들기 1 로 갈린다",
       s["find_share"] == 67 and s["make_share"] == 33,
       "찾기 %d%% 만들기 %d%%" % (s["find_share"], s["make_share"]))

    # ⑥ 🔴 반대쪽 — 분류가 전부 «찾기» 로 몰리는 자가 아닌가
    t = scan_records([_rec("user", 0, text="해줘"),
                      _rec("assistant", 1, tool="Bash", cmd="py build_ep55.py")])
    ok("만들기만 있으면 찾기 0%", summarize(t)["find_share"] == 0)

    # ⑦ 몰림 지표가 실제로 몰림을 잡는가 — 한 턴만 길게
    long_turn = [_rec("user", 0, text="a")] + [_rec("assistant", i) for i in (1, 2, 3, 4)]
    short = []
    for k in range(7):
        base = 100 + k * 10
        short += [_rec("user", base, text="b"), _rec("assistant", base + 0.2)]
    s = summarize(scan_records(long_turn + short))
    ok("긴 턴 몰림이 잡힌다", s["top12pct_share"] >= 70,
       "12%% 턴이 %d%%" % s["top12pct_share"])

    print()
    print("STATUS: %s" % ("OK" if not fails else "FAIL " + ", ".join(fails)))
    return 1 if fails else 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--project", default=None,
                    help="프로젝트 트랜스크립트 폴더 (기본: 이 레포)")
    ap.add_argument("--json", default=None, help="요약을 이 경로에 JSON 으로 남긴다")
    ap.add_argument("--label", default="턴 감사")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()

    root = a.project or os.path.join(PROJECTS, "C--Users-ojaej-orca-jj-company")
    files = sorted(glob.glob(os.path.join(root, "*.jsonl")),
                   key=os.path.getmtime, reverse=True)[:a.sessions]
    if not files:
        print("STATUS: FAIL 트랜스크립트 없음: %s" % root)
        return 1

    turns = []
    for f in files:
        turns += scan_file(f)
    s = summarize(turns)
    if not s:
        print("STATUS: FAIL 사람 턴 0개")
        return 1
    s["sessions"] = len(files)
    s["measured_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

    report(s, a.label)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(s, fh, ensure_ascii=False, indent=2)
        print()
        print("기준선 저장: %s" % a.json)
    print()
    print("STATUS: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
