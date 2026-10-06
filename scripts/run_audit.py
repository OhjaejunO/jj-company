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

사용:  py run_audit.py [--date YYYY-MM-DD] [--log-dir DIR] [--stamp-dir DIR] [--tasks a,b,c] [--self-test]
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
#: 회차 표식 — cross-verify.ps1 은 2026-10-06 부터 모든 줄의 시각 칸에 자기 pid 를 적는다
#: (`[yyyy-MM-dd HH:mm:ss pid N] …`). 두 회차가 겹치면(A start → B start → A OK → B OK) 줄의
#: 위치로는 STATUS 의 주인을 모른다 — 위치로 짝지으면 둘 다 B 에 붙고 A 가 무기록 종료로 읽힌다.
_LINE_PID = re.compile(r"^\[[^\]]* pid (\d+)\]")
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


def decode_log(raw):
    """로그 바이트 → 본문. **BOM 을 뗀다** — cross-verify.ps1 은 PS 5.1 `Add-Content -Encoding UTF8` 로
    써서 파일 첫 바이트가 BOM 이고, 그러면 첫 줄(= 첫 start 줄)이 `^\\[` 에 안 걸려 그 회차가 통째로
    안 보인다(2026-10-05 실측: 운영 서버 `cross-verify_20261005.log` 의 FAIL 이 NONE 으로 읽혔다).
    바이트를 받는 함수로 뗀 것은 자체 검사가 **파일을 만들지 않고** 이 축을 재게 하려는 것이다."""
    return raw.decode("utf-8-sig", errors="replace")


def read_log(path):
    with open(path, "rb") as f:
        return decode_log(f.read())


def audit_log(path, task):
    """classify 의 파일판. (starts, status_after_last_start, fail_reason)"""
    return classify(read_log(path), task)


def judge_per_run(text, task, is_today, alive=None):
    """PER_RUN 작업의 판정 — `(running, incomplete, [실패 사유])`. 회차마다 따로 본다.

    STATUS 줄은 **회차 표식(pid)으로 짝짓는다.** 표식이 없는 줄(2026-10-06 이전 로그)만 바로 앞 start
    의 회차에 붙인다 — 그 로그들은 겹친 회차를 못 가른다(⚪ 이틀 창이 지나면 사라진다).
    STATUS 없는 회차는 **오늘 회차이고 그 pid 가 살아 있다고 확인될 때만** «진행 중» 이다 — 회차가
    겹칠 수 있으니 «마지막 회차» 로 좁히지 않는다. 그 밖은 무기록 종료다. 생존을 모르면(None)
    진행 중으로 치지 않는다 — 스탬프 쪽(main)과 같은 규칙이다. 🔴 못 잡는 것: 죽은 회차의 pid 를
    같은 날 다른 프로세스가 물려받으면 «진행 중» 으로 읽힌다.
    `alive` 는 자체 검사가 pid 판정을 바꿔 끼우는 자리다.
    """
    alive = alive or pid_alive
    start_re = re.compile(r"^\[[^\]]+\] === %s start(?: \(pid (\d+)\))?" % re.escape(task))
    runs, current = [], None                    # [pid 문자열 | None, [STATUS 본문…]]
    for line in text.splitlines():
        m = start_re.match(line)
        if m:
            current = [m.group(1), []]
            runs.append(current)
            continue
        s = _STATUS_LINE.match(line)
        if not s or current is None:
            continue
        tag = _LINE_PID.match(line)
        owner = next((r for r in reversed(runs) if tag and r[0] == tag.group(1)), current)
        owner[1].append(s.group(1).strip())
    running, incomplete, reasons = False, False, []
    for pid, sts in runs:
        if sts:
            f = re.match(r"STATUS:\s*FAIL\s*(.*)$", sts[-1])
            why = (f.group(1).strip() or "(사유 없음)") if f else ""
            if why and why not in reasons:
                reasons.append(why)
            continue
        if is_today and pid and alive(int(pid)) is True:
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
    # 겹친 두 회차 (Codex 감리 2026-10-06 지적). STATUS 줄에 회차 표식이 있다 — 새 로그 꼴.
    # 대조군은 같은 순서에서 표식만 뺀 옛 꼴: 위치로 짝지으면 두 STATUS 가 B 에 붙고 A 가 무기록이
    # 된다 — 그래야 «표식으로 짝짓기» 가 이 케이스를 잡은 것이 증명된다. 대조군은 어제 로그로 둔다:
    # «진행 중» 판정(pid 생존)이 끼면 생존 축의 변이가 이 대조군까지 흔든다.
    tagged = lambda p, h, s: "[2026-10-05 %s pid %d] %s\n" % (h, p, s)
    ab = st(11, "08:40:00") + st(12, "08:40:05")
    overlap_ok = ab + tagged(11, "08:41:00", "STATUS: OK") + tagged(12, "08:41:30", "STATUS: OK")
    overlap_old = ab + "[2026-10-05 08:41:00] STATUS: OK\n[2026-10-05 08:41:30] STATUS: OK\n"
    overlap_fail = ab + tagged(12, "08:41:00", "STATUS: FAIL codex-exit-1") + tagged(11, "08:41:30", "STATUS: OK")
    overlap_run = ab + tagged(12, "08:41:00", "STATUS: OK")
    pr_cases = [
        (judge_per_run(overlap_old, X, False, alive_no), (False, True, []),
         "대조군: 표식 없는 겹친 회차가 위치로 짝지어지지 않았다 - 겹침 축이 재는 것이 없다"),
        (judge_per_run(overlap_ok, X, True, alive_no), (False, False, []),
         "겹친 두 회차의 OK 를 한 회차에 몰아 A 를 무기록 종료로 읽었다"),
        (judge_per_run(overlap_fail, X, True, alive_no), (False, False, ["codex-exit-1"]),
         "겹친 회차에서 B 의 FAIL 을 A 의 OK 가 덮었다"),
        (judge_per_run(overlap_run, X, True, lambda pid: pid == 11), (True, False, []),
         "B 가 끝났을 때 아직 도는 A 를 무기록 종료로 읽었다"),
        (classify(masked, X)[2], "", "대조군: 마지막 start 만 보면 앞 회차 실패가 안 보여야 한다"),
        (judge_per_run(masked, X, True, alive_no), (False, False, ["codex-exit-1"]),
         "뒤 회차 성공이 앞 회차 실패를 덮었다"),
        (judge_per_run(both_ok, X, True, alive_no), (False, False, []), "성공만 있는 날을 실패로 읽었다"),
        (judge_per_run(open_tail, X, True, alive_yes), (True, False, []), "돌고 있는 감리를 무기록 종료로 읽었다"),
        (judge_per_run(open_tail, X, True, alive_no), (False, True, []), "죽은 감리를 진행 중으로 읽었다"),
        (judge_per_run(open_tail, X, False, alive_yes), (False, True, []), "어제 회차를 진행 중으로 읽었다"),
    ]
    # 첫 실패에서 멈추지 않고 다 모은다 — 변이 검사에서 «어느 케이스가 걸렸나» 가 다 보여야
    # 케이스끼리 축이 겹치는지 잴 수 있다.
    bad = ["%s (기대 %r, 실제 %r)" % (msg, want, got) for got, want, msg in pr_cases if got != want]
    if bad:
        raise AssertionError("run_audit 자체 검사 실패: " + " / ".join(bad))

    # 바이트 축 — BOM 으로 시작하는 실제 꼴의 로그. 문자열 케이스만으로는 이것을 못 본다(위 케이스는
    # 다 통과하는데 실물 로그는 NONE 이었다). 대조군: BOM 을 안 떼고 풀면 사유가 비어야 한다.
    # **파일을 만들지 않는다** — 이 함수는 매 조회마다 돈다. 쓰기가 막힌 자리에서 조회가 로그를 읽기도
    # 전에 죽으면 session_brief 는 판정 줄 없는 출력을 받는다(Codex 감리 2026-10-06 지적 1).
    bom = b"\xef\xbb\xbf" + masked.encode("utf-8")
    file_cases = [
        (judge_per_run(bom.decode("utf-8"), X, True, alive_no)[2], [],
         "대조군: BOM 을 안 떼도 첫 회차가 보였다 - 이 축이 재는 것이 없다"),
        (judge_per_run(decode_log(bom), X, True, alive_no)[2], ["codex-exit-1"], "BOM 로그의 첫 회차 실패를 놓쳤다"),
    ]
    for got, want, msg in file_cases:
        if got != want:
            raise AssertionError("run_audit 자체 검사 실패: %s (기대 %r, 실제 %r)" % (msg, want, got))
    _SELFTESTED.append(True)


_WRITES_BLOCKED = []
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND


def _block_writes(event, args):
    # 감사 훅의 "open" 은 open()·os.open()·tempfile 전부를 지난다 — 쓰기 비트가 있으면 거부한다.
    if _WRITES_BLOCKED and event == "open" and isinstance(args[2], int) and args[2] & _WRITE_FLAGS:
        raise PermissionError("run_audit self-test: writes are blocked")


def _no_write_selftest():
    """`--self-test` — 쓰기가 막힌 자리에서도 일반 조회가 끝까지 돌아 판정 줄을 낸다.

    매 조회마다 도는 `_selftest()` 와 갈라 둔 이유: 이 시험은 합성 로그를 **파일로** 깔아야 한다.
    깔고 나서 프로세스 전체의 쓰기를 막고(감사 훅) `main()` 을 처음부터 — 매 조회 자체 검사까지 —
    다시 돌린다. 대조군: 막힌 상태에서 `tempfile.mkstemp()`(종전 매 조회 자체 검사가 부르던 것)는
    실제로 거부되어야 한다. 그래야 «통과» 가 막힘이 헛돈 덕이 아니다.
    """
    import io
    import tempfile
    sys.addaudithook(_block_writes)
    res = []
    with tempfile.TemporaryDirectory(prefix="run_audit_nw_") as d:
        day = datetime.date.today()
        with open(os.path.join(d, "cross-verify_%s.log" % day.strftime("%Y%m%d")), "wb") as f:
            f.write(b"\xef\xbb\xbf" + (
                "[%s 08:40:00 pid 11] === cross-verify start (pid 11) ===\n"
                "[%s 08:41:00 pid 11] STATUS: FAIL codex-exit-1\n" % (day, day)).encode("utf-8"))
        _WRITES_BLOCKED.append(True)
        _SELFTESTED.clear()                     # 매 조회 자체 검사도 막힌 채로 다시 돌게
        buf, old = io.StringIO(), sys.stdout
        try:
            try:
                tempfile.mkstemp(dir=d)
                res.append(("대조군: 쓰기 막힘이 tempfile 을 실제로 거부한다", False))
            except PermissionError:
                res.append(("대조군: 쓰기 막힘이 tempfile 을 실제로 거부한다", True))
            sys.stdout = buf
            try:
                main(["--log-dir", d, "--stamp-dir", d, "--tasks", "cross-verify", "--date", day.isoformat()])
                crashed = ""
            except Exception as e:              # noqa: BLE001 — 죽은 것 자체가 이 시험의 FAIL 이다
                crashed = type(e).__name__
        finally:
            sys.stdout = old
            _WRITES_BLOCKED.clear()
    out = buf.getvalue()
    res.append(("쓰기가 막혀도 일반 조회가 죽지 않는다" + (" (%s)" % crashed if crashed else ""), not crashed))
    res.append(("쓰기가 막혀도 실패 회차를 RED 로 낸다",
                "RUNS_FAILED=cross-verify@%s:codex-exit-1" % day.isoformat() in out and "RUNS_VERDICT=RED" in out))
    fails = 0
    for name, ok in res:
        fails += not ok
        print(("ok   " if ok else "FAIL ") + name)
    print("STATUS: %s" % ("OK" if not fails else "FAIL %d" % fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--log-dir", default=r"C:\Users\ojaej\jj-company\logs\scheduled")
    ap.add_argument("--stamp-dir", default=r"C:\Users\ojaej\jj-company\logs")
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    _selftest()
    if a.self_test:
        return _no_write_selftest()
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
