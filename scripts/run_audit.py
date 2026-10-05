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

TASKS = ["skill-drift-audit", "morning-vault-health", "tomangchi-scout", "job-scout",
         "publish-threads", "hermes-event-watch", "workshop-backup", "blog-writer", "study-scout",
         "cross-verify"]   # 2026-09-05: 래퍼가 있는 작업 전부 · 2026-10-05: cross-verify (백로그 31 ③)
#: 하루 로그 하나에 «서로 다른 회차» 가 쌓이는 작업 — cross-verify 는 리포트마다 한 번씩 돈다
#: (job-scout 아침 · study-scout 일요일 · 손으로 부른 감리). 다른 작업처럼 «마지막 start» 만 보면
#: 앞 회차의 실패가 뒤 회차의 성공에 덮인다. 그래서 회차마다 따로 본다.
#: 래퍼도 `.started` 스탬프도 없어서 «진행 중» 은 start 줄의 pid 로 가른다.
#: 근거: 2026-09-10~10-05 감리가 매일 실패했는데 이 TASKS 에 없어서 아침 리포트·세션 브리핑
#: 어디에도 안 떴다 — 흔적은 리포트 끝 «교차검증 미수행» 절뿐이었다(백로그 31).
PER_RUN = {"cross-verify"}
_START_PID = re.compile(r"\(pid (\d+)\)")
# 래퍼 로그 줄은 '[yyyy-MM-dd HH:mm:ss] STATUS: ...' — 줄머리가 아니라 타임스탬프 뒤다.
# 첫 판본이 '^STATUS:' 로 써서 정상 회차 전부를 INCOMPLETE 로 찍었다(대조군이 잡음, 2026-08-25).
_STATUS = re.compile(r"^\[[^\]]+\] STATUS:", re.M)
#: 같은 줄의 STATUS 이후를 통째로 잡는다 — 실패 사유를 리포트에 실으려면 «있다/없다» 로는 부족하다.
_STATUS_LINE = re.compile(r"^\[[^\]]+\] (STATUS:.*)$", re.M)


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


def classify(text, task):
    """로그 본문에서 (start 횟수, STATUS 유무, 마지막 STATUS 사유). 사유는 FAIL 일 때만 채운다.

    문자열을 받는다 — 파일을 열지 않으므로 자체 검사가 합성 로그로 그대로 부를 수 있다.
    """
    starts = [m.start() for m in re.finditer(r"^\[[^\]]+\] === %s start" % re.escape(task), text, re.M)]
    if not starts:
        return 0, True, ""
    tail = text[starts[-1]:]
    hits = _STATUS_LINE.findall(tail)
    if not hits:
        return len(starts), False, ""
    last = hits[-1].strip()
    # 'STATUS: FAIL skill-sync' → 'skill-sync'. 'STATUS: OK (부분: ...)' 은 FAIL 이 아니다(정관 §4).
    m = re.match(r"STATUS:\s*FAIL\s*(.*)$", last)
    return len(starts), True, (m.group(1).strip() or "(사유 없음)") if m else ""


def read_log(path):
    """로그 본문. **BOM 을 뗀다** — cross-verify.ps1 은 PS 5.1 `Add-Content -Encoding UTF8` 로 써서
    파일 첫 바이트가 BOM 이고, 그러면 첫 줄(= 첫 start 줄)이 `^\\[` 에 안 걸려 그 회차가 통째로
    안 보인다(2026-10-05 실측: 운영 서버 `cross-verify_20261005.log` 의 FAIL 이 NONE 으로 읽혔다)."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def audit_log(path, task):
    """classify 의 파일판. (starts, status_after_last_start, fail_reason)"""
    return classify(read_log(path), task)


def judge_per_run(text, task, is_today, alive=None):
    """PER_RUN 작업의 판정 — `(running, incomplete, [실패 사유])`. 회차마다 따로 본다.

    STATUS 없는 회차는 **오늘의 마지막 회차이고 그 pid 가 살아 있다고 확인될 때만** «진행 중» 이다.
    그 밖은 무기록 종료다 — 앞 회차가 STATUS 없이 끝났다면 뒤 회차가 돌고 있어도 그것은 죽은 것이다.
    생존을 모르면(None) 진행 중으로 치지 않는다 — 스탬프 쪽(main)과 같은 규칙이다.
    `alive` 는 자체 검사가 pid 판정을 바꿔 끼우는 자리다.
    """
    alive = alive or pid_alive
    starts = list(re.finditer(r"^\[[^\]]+\] === %s start[^\n]*" % re.escape(task), text, re.M))
    running, incomplete, reasons = False, False, []
    for i, m in enumerate(starts):
        seg = text[m.start():starts[i + 1].start() if i + 1 < len(starts) else len(text)]
        hits = _STATUS_LINE.findall(seg)
        if hits:
            f = re.match(r"STATUS:\s*FAIL\s*(.*)$", hits[-1].strip())
            why = (f.group(1).strip() or "(사유 없음)") if f else ""
            if why and why not in reasons:
                reasons.append(why)
            continue
        pm = _START_PID.search(m.group(0))
        if i == len(starts) - 1 and is_today and pm and alive(int(pm.group(1))) is True:
            running = True
        else:
            incomplete = True
    return running, incomplete, reasons


_SELFTESTED = []


def _selftest():
    r"""판정기 자신을 시험한다 — 합성 로그 넷(+ PER_RUN 다섯과 대조군 하나)으로 «잡아야 할 것»과 «잡으면 안 되는 것»을 같이 본다.

    정관 §0: 역검증 케이스는 다른 검사가 같이 걸리지 않게 분리한다. 여기서는 네 입력이
    각각 하나의 축만 건드린다 — 완주 OK / 무기록 / FAIL / «OK (부분:)».
    특히 마지막이 중요하다: 정관 §4 는 부분 완주를 FAIL 이 아니라고 못박았으므로,
    이것이 RUNS_FAILED 에 들어가면 매일 거짓 🔴 가 뜬다.
    """
    if _SELFTESTED:
        return
    T = "morning-vault-health"
    ok = "[2026-08-28 12:30:00] === %s start (pid 1) ===\n[2026-08-28 12:34:00] STATUS: OK\n" % T
    dead = "[2026-08-28 12:30:00] === %s start (pid 1) ===\n[2026-08-28 12:32:00] start stagger\n" % T
    bad = "[2026-08-27 12:30:00] === %s start (pid 1) ===\n[2026-08-27 12:32:02] STATUS: FAIL skill-sync\n" % T
    part = "[2026-08-28 12:30:00] === %s start (pid 1) ===\n[2026-08-28 12:34:00] STATUS: OK (부분: 소스 미조회)\n" % T
    cases = [
        (ok, (1, True, ""), "완주 회차를 실패로 읽었다"),
        (dead, (1, False, ""), "무기록 종료를 놓쳤다"),
        (bad, (1, True, "skill-sync"), "FAIL 사유를 못 뽑았다"),
        (part, (1, True, ""), "«OK (부분:)» 을 FAIL 로 읽었다 - 정관 §4 위반"),
    ]
    for text, want, msg in cases:
        got = classify(text, T)
        if got != want:
            raise AssertionError("run_audit 자체 검사 실패: %s (기대 %r, 실제 %r)" % (msg, want, got))

    # PER_RUN (cross-verify). 축마다 입력 하나 — 실패가 덮이는 꼴 · 둘 다 성공 · 돌고 있음 · 죽음.
    # 첫 케이스는 대조군을 같이 둔다: 같은 로그를 classify(마지막 start 만)에 먹이면 사유가 비어야
    # 한다 — 그래야 «회차마다 본다» 가 그 실패를 잡은 것이지 원래 잡히던 것이 아니라는 게 증명된다.
    X = "cross-verify"
    st = lambda p, h: "[2026-10-05 %s] === %s start (pid %d) ===\n" % (h, X, p)
    masked = (st(11, "08:40:00") + "[2026-10-05 08:41:00] STATUS: FAIL codex-exit-1\n" +
              st(12, "15:10:00") + "[2026-10-05 15:12:00] STATUS: OK\n")
    both_ok = (st(11, "08:40:00") + "[2026-10-05 08:41:00] STATUS: OK\n" +
               st(12, "15:10:00") + "[2026-10-05 15:12:00] STATUS: OK\n")
    open_tail = st(11, "08:40:00") + "[2026-10-05 08:40:01] codex exec start\n"
    alive_yes, alive_no = (lambda pid: True), (lambda pid: False)
    pr_cases = [
        (classify(masked, X)[2], "", "대조군: 마지막 start 만 보면 앞 회차 실패가 안 보여야 한다"),
        (judge_per_run(masked, X, True, alive_no), (False, False, ["codex-exit-1"]),
         "뒤 회차 성공이 앞 회차 실패를 덮었다"),
        (judge_per_run(both_ok, X, True, alive_no), (False, False, []), "성공만 있는 날을 실패로 읽었다"),
        (judge_per_run(open_tail, X, True, alive_yes), (True, False, []), "돌고 있는 감리를 무기록 종료로 읽었다"),
        (judge_per_run(open_tail, X, True, alive_no), (False, True, []), "죽은 감리를 진행 중으로 읽었다"),
        (judge_per_run(open_tail, X, False, alive_yes), (False, True, []), "어제 회차를 진행 중으로 읽었다"),
    ]
    for got, want, msg in pr_cases:
        if got != want:
            raise AssertionError("run_audit 자체 검사 실패: %s (기대 %r, 실제 %r)" % (msg, want, got))

    # 파일 축 — BOM 으로 시작하는 실제 꼴의 로그. 문자열 케이스만으로는 이것을 못 본다(위 케이스는
    # 다 통과하는데 실물 로그는 NONE 이었다). 대조군: BOM 을 안 떼고 읽으면 사유가 비어야 한다.
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".log")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(b"\xef\xbb\xbf" + masked.encode("utf-8"))
        with open(tmp, encoding="utf-8") as f:
            raw = f.read()
        file_cases = [
            (judge_per_run(raw, X, True, alive_no)[2], [], "대조군: BOM 을 안 떼도 첫 회차가 보였다 - 이 축이 재는 것이 없다"),
            (judge_per_run(read_log(tmp), X, True, alive_no)[2], ["codex-exit-1"], "BOM 로그의 첫 회차 실패를 놓쳤다"),
        ]
    finally:
        os.remove(tmp)
    for got, want, msg in file_cases:
        if got != want:
            raise AssertionError("run_audit 자체 검사 실패: %s (기대 %r, 실제 %r)" % (msg, want, got))
    _SELFTESTED.append(True)


def main(argv=None):
    _selftest()
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

    checked, incomplete, running, failed = 0, [], [], []
    for d in (today - datetime.timedelta(days=1), today):
        for t in tasks:
            p = os.path.join(a.log_dir, "%s_%s.log" % (t, d.strftime("%Y%m%d")))
            if not os.path.exists(p):
                continue
            checked += 1
            if t in PER_RUN:
                run_now, dead, whys = judge_per_run(read_log(p), t, d == today)
                if run_now:
                    running.append("%s@%s" % (t, d.isoformat()))
                if dead:
                    incomplete.append("%s@%s" % (t, d.isoformat()))
                if whys:
                    failed.append("%s@%s:%s" % (t, d.isoformat(), ",".join(whys)))
                continue
            n, ok, why = audit_log(p, t)
            if n and not ok:
                if d == today and stamps.get(t) is True:
                    running.append("%s@%s" % (t, d.isoformat()))
                else:
                    incomplete.append("%s@%s" % (t, d.isoformat()))
            elif n and why:
                failed.append("%s@%s:%s" % (t, d.isoformat(), why))

    print("RUNS_CHECKED=%d" % checked)
    print("RUNS_INCOMPLETE=%s" % (";".join(incomplete) or "NONE"))
    print("RUNS_FAILED=%s" % (";".join(failed) or "NONE"))
    print("RUNS_RUNNING=%s" % (";".join(running) or "NONE"))
    print("STARTED_RESIDUAL=%s" % (";".join(residual) or "NONE"))
    print("RUNS_VERDICT=%s" % ("RED" if (incomplete or residual or failed) else "OK"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
