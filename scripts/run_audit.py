# -*- coding: utf-8 -*-
"""무기록 종료 감지 — 스케줄 로그에 «start 는 있는데 STATUS 가 없는» 회차와 잔존 .started 스탬프를 찾는다.

근거 (2026-08-25 판정): 8/25 tomangchi-scout·job-scout 가 09:10:38 기동 → 09:14:21 재부팅으로
stagger 수면 중 죽었다. 로그는 'start stagger' 한 줄에서 끝났고 STATUS 줄·리포트·완료 이벤트·lock
어디에도 흔적이 없었다 — 정관 §0 «조용한 실패». 이 스크립트가 그 자리를 본다.

구조는 vault_audit.py 와 같다: 래퍼가 에이전트보다 먼저 돌려 KEY=value 파일을 만들고, ops-auditor(A등급,
Bash 없음)는 그 파일을 읽어 판정만 한다. 이 스크립트는 파일을 수정하지 않는다 (stdout 만).

출력 (stdout, KEY=value):
  RUNS_CHECKED=<본 로그 파일 수>
  RUNS_INCOMPLETE=<task>@<yyyy-MM-dd>;...  | NONE     ← 마지막 start 뒤에 ^STATUS: 가 없고, 살아 있는 프로세스도 없음
  RUNS_RUNNING=<task>@<yyyy-MM-dd>;...     | NONE     ← STATUS 없지만 .started 의 pid 가 살아 있음 (진행 중 = 정상)
  STARTED_RESIDUAL=<task>(pid=N,started=...);... | NONE ← .started 가 있는데 pid 가 죽어 있음
  RUNS_VERDICT=OK | RED

사용:  py run_audit.py [--date YYYY-MM-DD] [--log-dir DIR] [--stamp-dir DIR] [--tasks a,b,c]
       기본은 오늘·어제 이틀치, 운영 서버 logs/scheduled 와 logs/.
"""
import os
import re
import sys
import argparse
import datetime
import subprocess

TASKS = ["skill-drift-audit", "morning-vault-health", "tomangchi-scout", "job-scout"]
# 래퍼 로그 줄은 '[yyyy-MM-dd HH:mm:ss] STATUS: ...' — 줄머리가 아니라 타임스탬프 뒤다.
# 첫 판본이 '^STATUS:' 로 써서 정상 회차 전부를 INCOMPLETE 로 찍었다(대조군이 잡음, 2026-08-25).
_STATUS = re.compile(r"^\[[^\]]+\] STATUS:", re.M)


def pid_alive(pid):
    """Windows: tasklist 로 pid 생존 확인. 실패하면 None (모름) — 모름을 «죽음»으로 읽지 않는다."""
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                             capture_output=True, text=True, timeout=15).stdout
        return (" %d " % pid) in out.replace("\t", " ")
    except Exception:
        return None


def read_stamp(path):
    """'pid=N started=YYYY-MM-DD HH:mm:ss' 한 줄. 형식이 깨졌으면 pid=None."""
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read().strip()
    except OSError:
        return None, ""
    m = re.search(r"pid=(\d+)", txt)
    return (int(m.group(1)) if m else None), txt


def audit_log(path, task):
    """마지막 '=== <task> start' 뒤에 ^STATUS: 가 있는가. (starts, status_after_last_start)"""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    starts = [m.start() for m in re.finditer(r"^\[[^\]]+\] === %s start" % re.escape(task), text, re.M)]
    if not starts:
        return 0, True
    tail = text[starts[-1]:]
    return len(starts), bool(_STATUS.search(tail))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--log-dir", default=r"C:\Users\ojaej\jj-company\logs\scheduled")
    ap.add_argument("--stamp-dir", default=r"C:\Users\ojaej\jj-company\logs")
    ap.add_argument("--tasks", default=",".join(TASKS))
    a = ap.parse_args(argv)
    today = datetime.date.fromisoformat(a.date)
    tasks = [t for t in a.tasks.split(",") if t]

    # 스탬프 먼저 — 로그 판정이 «진행 중»을 알아야 한다
    stamps = {}
    residual = []
    for t in tasks:
        p = os.path.join(a.stamp_dir, t + ".started")
        if not os.path.exists(p):
            continue
        pid, txt = read_stamp(p)
        alive = pid_alive(pid) if pid else None
        stamps[t] = alive
        if alive is False:
            residual.append("%s(%s)" % (t, txt.replace(" ", ",")))
        elif alive is None:
            residual.append("%s(%s,alive=unknown)" % (t, txt.replace(" ", ",")))

    checked, incomplete, running = 0, [], []
    for d in (today - datetime.timedelta(days=1), today):
        for t in tasks:
            p = os.path.join(a.log_dir, "%s_%s.log" % (t, d.strftime("%Y%m%d")))
            if not os.path.exists(p):
                continue
            checked += 1
            n, ok = audit_log(p, t)
            if n and not ok:
                if d == today and stamps.get(t) is True:
                    running.append("%s@%s" % (t, d.isoformat()))
                else:
                    incomplete.append("%s@%s" % (t, d.isoformat()))

    print("RUNS_CHECKED=%d" % checked)
    print("RUNS_INCOMPLETE=%s" % (";".join(incomplete) or "NONE"))
    print("RUNS_RUNNING=%s" % (";".join(running) or "NONE"))
    print("STARTED_RESIDUAL=%s" % (";".join(residual) or "NONE"))
    print("RUNS_VERDICT=%s" % ("RED" if (incomplete or residual) else "OK"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
