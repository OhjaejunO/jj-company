# -*- coding: utf-8 -*-
r"""intent_from_audit — 아침 감사 데이터가 🔴 이면 intent 파일을 만든다 (공부 반영 제안 E · A등급).

WHY (SDLC 플레이북 «유지보수: 로그·알림이 사람 없이 intent.md 를 낳는다» · JJ 승인 2026-09-05)
  8/27 세 작업이 같은 인증 만료로 죽었는데 다음 날 리포트를 «읽고서야» 알았다. 리포트는 사실을
  나열하고 사람이 진단을 시작한다. 이 스크립트는 그 첫 걸음(무엇이·언제·로그 어디·복구 명령 후보)을
  파일로 만들어 둔다 — 사람이 열면 진단이 되어 있는 상태로.

WHAT
  입력: logs\audit-data\runs_<날짜>.txt (run_audit.py) · auth_<날짜>.txt (auth_check.py) — KEY=value
  판정: RUNS_VERDICT=RED 또는 AUTH_ALL_OK=no 이면 항목을 모아
  출력: reports\intents\<날짜>_<사유>.md  (정관 §2 — 산출물은 reports\ 에)
        이미 있으면 덮어쓰지 않는다(같은 날 재실행 = 같은 파일). stdout 마지막 줄 INTENT=<경로> | NONE
  A등급이다 — 파일을 만들 뿐 복구 명령은 실행하지 않는다.

USAGE
  py scripts\intent_from_audit.py [--date YYYY-MM-DD] [--data-dir …] [--log-dir …] [--out-dir …]
  py scripts\intent_from_audit.py --self-test

LIMITS (정관 §0 4층 ④)
  진단은 «사유 문자열 → 규칙표» 다. 표에 없는 사유는 «진단 없음 — 로그를 봐라» 로 남는다.
"""
import argparse
import datetime as dt
import io
import os
import re
import sys

HQ = r"C:\Users\ojaej\jj-company"
RULES = [  # (사유 정규식, 진단 한 줄, 복구 명령 후보)
    (r"skill-sync-auth|credentials", "gh 토큰 만료 — deploy-skill 의 git fetch 가 인증에서 죽었다(8/27 과 같은 꼴)",
     "gh auth login --hostname github.com --git-protocol https --web"),
    (r"skill-sync", "스킬 정본 동기화 실패(인증 아님) — origin/main fetch 또는 사본 검증 실패",
     r"powershell -NoProfile -File C:\Users\ojaej\jj-company\scripts\deploy-skill.ps1"),
    (r"drift-detected", "스킬 라이브 사본(~\\.claude\\skills\\tomangchi)이 origin/main 과 다르다 — 누군가 사본을 직접 고쳤거나 배포가 빠졌다",
     r"py C:\Users\ojaej\jj-company\scripts\skill_drift_audit.py  (차이 목록 확인)  →  powershell -NoProfile -File C:\Users\ojaej\jj-company\scripts\deploy-skill.ps1"),
    (r"git-sync", "운영 서버 git pull 실패 — 동시 기동 경쟁 또는 로컬 변경 충돌",
     r"git -C C:\Users\ojaej\jj-company status --short ; git -C C:\Users\ojaej\jj-company pull --ff-only origin main"),
    (r"probe", "권한 프로브 실패 — 승인 게이트가 열린 채라 에이전트를 띄우지 않고 중단",
     r"py C:\Users\ojaej\jj-company\scripts\permission_probe.py --self-test"),
    (r"lock-exists", "이전 회차 lock 잔존 — 앞 회차가 죽으면서 lock 을 못 지웠다",
     r"dir C:\Users\ojaej\jj-company\logs\*.lock  (죽은 회차 확인 뒤 삭제)"),
    (r"report-missing|agent-status-not-ok|claude-exit", "에이전트 회차가 리포트 없이/실패로 끝났다 — cc| 줄을 본다", ""),
]


def kv(path):
    d = {}
    if not os.path.exists(path):
        return d
    txt = io.open(path, encoding="utf-8", errors="replace").read()
    if txt.strip().startswith("UNAVAILABLE"):
        return {"_UNAVAILABLE": txt.strip()}
    for ln in txt.splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def log_tail(log_dir, task, day, n=12):
    p = os.path.join(log_dir, "%s_%s.log" % (task, day.replace("-", "")))
    if not os.path.exists(p):
        return p, "(로그 파일 없음)"
    lines = io.open(p, encoding="utf-8", errors="replace").read().splitlines()
    return p, "\n".join(lines[-n:])


def diagnose(reason):
    for pat, diag, fix in RULES:
        if re.search(pat, reason):
            return diag, fix
    return "진단 없음 — 로그를 봐라", ""


def collect(runs, auth):
    items = []
    for ent in [x for x in runs.get("RUNS_FAILED", "NONE").split(";") if x and x != "NONE"]:
        m = re.match(r"([^@]+)@(\d{4}-\d{2}-\d{2}):(.*)", ent)
        if m:
            items.append({"kind": "FAIL", "task": m.group(1), "day": m.group(2), "reason": m.group(3)})
    for ent in [x for x in runs.get("RUNS_INCOMPLETE", "NONE").split(";") if x and x != "NONE"]:
        m = re.match(r"([^@]+)@(\d{4}-\d{2}-\d{2})", ent)
        if m:
            items.append({"kind": "INCOMPLETE", "task": m.group(1), "day": m.group(2), "reason": "무기록 종료(start 뒤 STATUS 없음)"})
    for ent in [x for x in runs.get("STARTED_RESIDUAL", "NONE").split(";") if x and x != "NONE"]:
        m = re.match(r"([^(]+)\((.*)\)", ent)
        if m:
            items.append({"kind": "RESIDUAL", "task": m.group(1), "day": "", "reason": ".started 잔존 " + m.group(2)})
    if auth.get("AUTH_ALL_OK", "yes") == "no":
        if auth.get("GH_AUTH", "OK") != "OK":
            items.append({"kind": "AUTH", "task": "gh", "day": "", "reason": "GH_AUTH=" + auth.get("GH_AUTH", "?"),
                          "fix": auth.get("GH_AUTH_FIX", "gh auth login --hostname github.com --git-protocol https --web")})
        if auth.get("DRIVE", "OK") != "OK":
            items.append({"kind": "AUTH", "task": "drive", "day": "", "reason": "DRIVE=" + auth.get("DRIVE", "?"),
                          "fix": auth.get("DRIVE_FIX", "구글 드라이브 데스크톱 실행 → «내 드라이브» 마운트 확인")})
    return items


def render(date, items, log_dir, sources):
    out = ["# intent — %s 아침 감사 🔴" % date, "",
           "> 기계가 만든 진단 초안이다(A등급 · `scripts\\intent_from_audit.py`). 복구는 사람이 한다.",
           "> 근거 파일: " + " · ".join("`%s`" % s for s in sources), "",
           "## 무엇이", "", "| # | 종류 | 작업 | 날짜 | 사유 |", "|---|---|---|---|---|"]
    for i, it in enumerate(items, 1):
        out.append("| %d | %s | %s | %s | %s |" % (i, it["kind"], it["task"], it["day"] or "-", it["reason"]))
    out += ["", "## 진단 · 복구 명령 후보 (실행은 JJ)", ""]
    for i, it in enumerate(items, 1):
        if it["kind"] == "AUTH":
            diag, fix = "인증·마운트 만료(auth_check)", it.get("fix", "")
        else:
            diag, fix = diagnose(it["reason"])
        out.append("### %d. %s — %s" % (i, it["task"], it["kind"]))
        out.append("- 진단: " + diag)
        if fix:
            out += ["- 복구 후보:", "", "```", fix, "```", ""]
        if it["day"]:
            p, tail = log_tail(log_dir, it["task"], it["day"])
            out += ["- 로그: `%s` (마지막 12줄)" % p, "", "```", tail, "```", ""]
    out += ["## JJ 판정", "", "- [ ] 복구함 (명령 · 시각)", "- [ ] 무시 (사유)", "- [ ] 안건으로 (`docs\\infra-backlog.md` 번호)", ""]
    return "\n".join(out)


def run(date, data_dir, log_dir, out_dir):
    runs_p = os.path.join(data_dir, "runs_%s.txt" % date)
    auth_p = os.path.join(data_dir, "auth_%s.txt" % date)
    runs, auth = kv(runs_p), kv(auth_p)
    red = runs.get("RUNS_VERDICT") == "RED" or auth.get("AUTH_ALL_OK") == "no"
    items = collect(runs, auth) if red else []
    if not items:
        print("INTENT=NONE")
        return 0
    slug = "+".join(sorted(set(re.sub(r"[^A-Za-z0-9가-힣-]", "", it["task"]) for it in items)))[:60]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s_%s.md" % (date, slug))
    if os.path.exists(path):
        print("INTENT=%s (exists, not overwritten)" % path)
        return 0
    io.open(path, "w", encoding="utf-8").write(render(date, items, log_dir, [runs_p, auth_p]))
    print("INTENT=%s" % path)
    return 0


def self_test():
    import tempfile
    root = tempfile.mkdtemp(prefix="intent_")
    data, logs, out = [os.path.join(root, x) for x in ("data", "logs", "out")]
    for d in (data, logs):
        os.makedirs(d)
    io.open(os.path.join(data, "runs_2026-09-05.txt"), "w", encoding="utf-8").write(
        "RUNS_CHECKED=4\nRUNS_INCOMPLETE=job-scout@2026-09-04\nRUNS_FAILED=tomangchi-scout@2026-09-05:skill-sync-auth (gh token expired or missing)\nRUNS_RUNNING=NONE\nSTARTED_RESIDUAL=NONE\nRUNS_VERDICT=RED\n")
    io.open(os.path.join(data, "auth_2026-09-05.txt"), "w", encoding="utf-8").write("GH_AUTH=EXPIRED\nGH_AUTH_FIX=gh auth login --web\nDRIVE=OK\nAUTH_ALL_OK=no\n")
    io.open(os.path.join(logs, "tomangchi-scout_20260905.log"), "w", encoding="utf-8").write("[..] === tomangchi-scout start\n[..] STATUS: FAIL skill-sync-auth\n")
    buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
    try:
        run("2026-09-05", data, logs, out)
    finally:
        sys.stdout = old
    line = buf.getvalue().strip()
    p = line.split("=", 1)[1]
    txt = io.open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    c1 = ("FAIL" in txt and "INCOMPLETE" in txt and "gh auth login --web" in txt and "gh 토큰 만료" in txt
          and "STATUS: FAIL skill-sync-auth" in txt and "무기록 종료" in txt)
    # idempotent
    buf = io.StringIO(); sys.stdout = buf
    try:
        run("2026-09-05", data, logs, out)
    finally:
        sys.stdout = old
    c2 = "not overwritten" in buf.getvalue()
    # green day -> NONE
    io.open(os.path.join(data, "runs_2026-09-06.txt"), "w", encoding="utf-8").write("RUNS_FAILED=NONE\nRUNS_INCOMPLETE=NONE\nSTARTED_RESIDUAL=NONE\nRUNS_VERDICT=OK\n")
    io.open(os.path.join(data, "auth_2026-09-06.txt"), "w", encoding="utf-8").write("GH_AUTH=OK\nDRIVE=OK\nAUTH_ALL_OK=yes\n")
    buf = io.StringIO(); sys.stdout = buf
    try:
        run("2026-09-06", data, logs, out)
    finally:
        sys.stdout = old
    c3 = buf.getvalue().strip() == "INTENT=NONE" and len(os.listdir(out)) == 1
    # «OK (부분:)» day must stay NONE — run_audit already excludes it; here: RED with only RUNNING -> no items
    io.open(os.path.join(data, "runs_2026-09-07.txt"), "w", encoding="utf-8").write("RUNS_FAILED=NONE\nRUNS_INCOMPLETE=NONE\nSTARTED_RESIDUAL=NONE\nRUNS_VERDICT=OK\n")
    buf = io.StringIO(); sys.stdout = buf
    try:
        run("2026-09-07", data, logs, out)
    finally:
        sys.stdout = old
    c4 = buf.getvalue().strip() == "INTENT=NONE"
    for name, v in (("RED → 항목·진단·복구·로그 꼬리", c1), ("같은 날 재실행 → 덮어쓰지 않음", c2), ("OK 날 → NONE, 파일 없음", c3), ("auth 파일 없는 OK 날 → NONE", c4)):
        print(("PASS " if v else "FAIL ") + name)
    ok = c1 and c2 and c3 and c4
    print("STATUS: " + ("OK" if ok else "FAIL selftest"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--data-dir", default=os.path.join(HQ, "logs", "audit-data"))
    ap.add_argument("--log-dir", default=os.path.join(HQ, "logs", "scheduled"))
    ap.add_argument("--out-dir", default=os.path.join(HQ, "reports", "intents"))
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(self_test())
    raise SystemExit(run(a.date, a.data_dir, a.log_dir, a.out_dir))
