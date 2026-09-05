# -*- coding: utf-8 -*-
r"""오피스 계기판 집계 — 상단 바 · 수치 띠 · 오른쪽 패널(팀·피드·승인 대기·7일 그래프) · 아래 절(회차 표 · 발행 추이 · 리포트 표 · 게이트 요약).

    py tools\session-dashboard\hud.py            → JSON 한 번 (검사용)
    py tools\session-dashboard\hud.py --self-test

전부 **읽기**다. 유일한 쓰기는 `logs\dashboard\stats_<날짜>.json` — 수치 띠의 ▲▼ 를 위해 «어제 값» 을 남기는 스냅샷이고
`logs\` 라 커밋되지 않는다. 출처: 발행로그(편·게시물) · logs\scheduled(회차) · reports\(승인 초안·리포트) · 편 폴더 shots\(게이트) ·
`gh pr list`(열린 PR · 60초 캐시) · 스킬 사본 SKILL.md(판본). 모르는 것은 모른다고 적는다 — 값이 없으면 null, «0» 으로 뭉개지 않는다.
"""
import glob
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
HQ = r"C:\Users\ojaej\jj-company"
HQ_LOGS = os.path.join(HQ, "logs", "scheduled")
HQ_REPORTS = os.path.join(HQ, "reports")
STATS_DIR = os.path.join(HQ, "logs", "dashboard")
WORKSHOP = r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop"
PUBLOG = os.path.join(WORKSHOP, "발행로그.md")
SKILL_MD = os.path.join(os.path.expanduser("~"), ".claude", "skills", "tomangchi", "SKILL.md")
TASKS = ["hermes-event-watch", "tomangchi-scout", "job-scout", "morning-vault-health", "skill-drift-audit"]   # 아침 회차 5 (정관 §4 현황판)
REPOS = ["OhjaejunO/jj-company", "OhjaejunO/tomangchi-skill", "tomangchi-lab/tomangchi-lab.github.io", "OhjaejunO/OhjaejunO.github.io", "OhjaejunO/content-ops"]
#: 승인 대기 큐의 «되돌림 비용» — 정관 §0 의 가르는 기준 그대로. 기계가 아는 만큼만 적는다.
REVERSIBLE = {"pr": "revert 한 번", "approval": "파일 이동 취소", "publish_wait": "발행 전 — 전량 재생성", "fail": "재실행", "wait": "입력 한 줄"}

_cache = {}


def _cached(key, ttl, fn):
    now = time.time()
    v = _cache.get(key)
    if v and now - v[0] < ttl:
        return v[1]
    r = fn()
    _cache[key] = (now, r)
    return r


# ── 발행로그 ──────────────────────────────────────────────────────────────────
def publog():
    """본 표의 «발행» 행 → 편 수 · 게시물 수 · Threads 수 · 주별 발행 수 · 최근 행."""
    try:
        lines = io.open(PUBLOG, encoding="utf-8").read().split("\n")
    except OSError:
        return {"error": "발행로그 없음"}
    hdr = next((i for i, l in enumerate(lines) if l.startswith("| ep | 제목 | 상태 | 발행일")), None)
    if hdr is None:
        return {"error": "본 표 머리글 없음"}
    end = next((i for i in range(hdr, len(lines)) if lines[i].startswith("## ")), len(lines))
    rows = [l for l in lines[hdr + 2:end] if l.startswith("|") and "**발행**" in l]
    keys, dates, recent = [], [], []
    for l in rows:
        cells = [c.strip() for c in l.split("|")]
        k = re.sub(r"\*", "", cells[1]).strip()
        m = re.search(r"(\d{4}-\d{2}-\d{2})", re.sub(r"\*", "", cells[4]) if len(cells) > 4 else "")
        keys.append(k)
        if m:
            dates.append(m.group(1))
            recent.append({"ep": k, "title": re.sub(r"\*", "", cells[2])[:48], "date": m.group(1)})
    eps = [k for k in keys if re.fullmatch(r"ep\d+", k)]
    threads = [k for k in keys if "Threads" in k]
    weekly = {}
    for d in dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        wk = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
        weekly[wk] = weekly.get(wk, 0) + 1
    wks = sorted(weekly)[-10:]
    return {"episodes": len(eps), "posts": len(rows) - len(threads), "threads": len(threads), "rows": len(rows),
            "weekly": [{"week": w[5:].replace("-", "/"), "n": weekly[w]} for w in wks], "recent": sorted(recent, key=lambda r: r["date"])[-6:][::-1]}


# ── 스케줄 회차 ────────────────────────────────────────────────────────────────
def _status_of(logfile):
    try:
        lines = io.open(logfile, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return None
    st = next((l for l in reversed(lines) if "STATUS:" in l), None)
    if st is None:
        return {"state": "running" if time.time() - os.path.getmtime(logfile) < 120 else "nostatus", "detail": ""}
    tail = st.split("STATUS:")[-1].strip()
    return {"state": "fail" if tail.startswith("FAIL") else "ok", "detail": tail[:60]}


def runs7(days=7):
    """작업 × 날짜 격자 — 로그 파일 존재·STATUS 로만 판정한다."""
    today = datetime.now(KST).date()
    ds = [(today - timedelta(days=i)) for i in range(days - 1, -1, -1)]
    grid = []
    for t in TASKS:
        row = []
        for d in ds:
            f = os.path.join(HQ_LOGS, "%s_%s.log" % (t, d.strftime("%Y%m%d")))
            s = _status_of(f) if os.path.exists(f) else None
            row.append({"date": d.isoformat(), "state": (s or {}).get("state", "none"), "detail": (s or {}).get("detail", "")})
        grid.append({"task": t, "days": row})
    per_day = []
    for i, d in enumerate(ds):
        states = [r["days"][i]["state"] for r in grid]
        per_day.append({"date": d.strftime("%m/%d"), "ok": states.count("ok"), "fail": states.count("fail"), "none": states.count("none") + states.count("nostatus")})
    return {"dates": [d.strftime("%m/%d") for d in ds], "grid": grid, "per_day": per_day}


def headroom_today():
    """래퍼가 찍는 «headroom: saved this run N tokens» 합 — 없으면 null (0 으로 뭉개지 않는다)."""
    today = datetime.now(KST).strftime("%Y%m%d")
    tot, n = 0, 0
    for f in glob.glob(os.path.join(HQ_LOGS, "*_%s.log" % today)):
        for m in re.finditer(r"headroom: saved this run (\d+) tokens", io.open(f, encoding="utf-8", errors="replace").read()):
            tot += int(m.group(1)); n += 1
    return {"tokens": tot, "runs": n} if n else None


# ── 승인 대기 큐 ───────────────────────────────────────────────────────────────
def open_prs():
    def fetch():
        out = []
        for repo in REPOS:
            try:
                r = subprocess.run(["gh", "pr", "list", "--repo", repo, "--state", "open", "--json", "number,title,headRefName,mergeable,updatedAt", "--limit", "10"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
                for p in json.loads(r.stdout or "[]"):
                    out.append({"repo": repo.split("/")[-1], "n": p["number"], "title": p["title"][:70], "mergeable": p.get("mergeable"), "updated": p.get("updatedAt")})
            except Exception as e:  # noqa: BLE001 — 못 읽으면 «확인 불가» 한 줄
                out.append({"repo": repo.split("/")[-1], "n": None, "title": "확인 불가: " + str(e)[:60], "mergeable": None})
        return out
    return _cached("prs", 60, fetch)


def approvals(terminals=None, scheduled=None):
    q = []
    for p in open_prs():
        q.append({"kind": "pr", "what": "PR #%s · %s" % (p["n"], p["repo"]), "detail": p["title"], "who": "JJ 머지 승인", "reversible": REVERSIBLE["pr"],
                  "flag": (p.get("mergeable") or "").lower()})
    for f in glob.glob(os.path.join(HQ_REPORTS, "*.approval.json")):
        q.append({"kind": "approval", "what": "Threads 승인 초안 · " + os.path.basename(f).split(".")[0], "detail": "move-approval.bat 으로 옮기면 서명",
                  "who": "JJ 서명", "reversible": REVERSIBLE["approval"], "flag": ""})
    # 게이트 통과했는데 발행로그에 없는 편 (02_제작중)
    pl = publog(); done = set()
    try:
        lines = io.open(PUBLOG, encoding="utf-8").read()
        done = set(re.findall(r"\|\s*\*\*(ep\d+)\*\*\s*\|", lines))
    except OSError:
        pass
    for d in sorted(glob.glob(os.path.join(WORKSHOP, "02_제작중", "ep*"))):
        ep = os.path.basename(d).split("_")[0]
        runs = sorted(glob.glob(os.path.join(d, "shots", "_gate_run*.txt")), key=os.path.getmtime)
        if not runs:
            continue
        last = io.open(runs[-1], encoding="utf-8", errors="replace").read()
        ok = "STATUS: OK" in last.splitlines()[-1] if last.strip() else False
        if ok and ep not in done:
            q.append({"kind": "publish_wait", "what": "발행 대기 · " + os.path.basename(d), "detail": "게이트 OK · 드라이브 전달 뒤 JJ 업로드(C등급)",
                      "who": "JJ 발행", "reversible": REVERSIBLE["publish_wait"], "flag": ""})
    for c in (scheduled or []):
        if c.get("status") and "FAIL" in c["status"]:
            q.append({"kind": "fail", "what": "회차 FAIL · " + c["name"], "detail": c["status"].split("STATUS:")[-1].strip()[:60], "who": "JJ 판단", "reversible": REVERSIBLE["fail"], "flag": "fail"})
    for t in (terminals or []):
        if t.get("waiting"):
            q.append({"kind": "wait", "what": "입력 대기 · " + t.get("repo", ""), "detail": str(t.get("wait"))[:60], "who": "JJ 답", "reversible": REVERSIBLE["wait"], "flag": "wait"})
    return q


# ── 게이트 · 리포트 · 스킬 ────────────────────────────────────────────────────
def latest_gate():
    """가장 최근 게이트 회차(01_발행완료·02_제작중 통틀어) — OK/FAIL/SKIP 수와 절 수."""
    runs = glob.glob(os.path.join(WORKSHOP, "0[12]_*", "ep*", "shots", "_gate_run*.txt"))
    if not runs:
        return None
    f = max(runs, key=os.path.getmtime)
    t = io.open(f, encoding="utf-8", errors="replace").read()
    ep = f.split(os.sep)[-3]
    return {"ep": ep, "file": os.path.basename(f), "ok": len(re.findall(r"^  OK ", t, re.M)), "fail": len(re.findall(r"^  FAIL ", t, re.M)) - 1 if "역검증용" in t else len(re.findall(r"^  FAIL ", t, re.M)),
            "skip": len(re.findall(r"^  SKIP ", t, re.M)), "sections": len(set(re.findall(r"^\[([0-9][^\]]*)\]", t, re.M))),
            "status": (t.strip().splitlines() or [""])[-1][:40], "at": datetime.fromtimestamp(os.path.getmtime(f), KST).strftime("%m/%d %H:%M")}


def reports_today(day=None):
    d = (day or datetime.now(KST).date()).isoformat() if not isinstance(day, str) else day
    out = []
    for f in sorted(glob.glob(os.path.join(HQ_REPORTS, d + "*")), key=os.path.getmtime):
        out.append({"name": os.path.basename(f), "kb": round(os.path.getsize(f) / 1024, 1), "at": datetime.fromtimestamp(os.path.getmtime(f), KST).strftime("%H:%M")})
    return out


def skill_version():
    try:
        head = io.open(SKILL_MD, encoding="utf-8").read(120000)
        vs = re.findall(r"> v(3\.\d+)", head)
        return "v" + max(vs, key=lambda v: tuple(int(x) for x in v.split("."))) if vs else None
    except OSError:
        return None


# ── 수치 띠 + 어제 대비 ───────────────────────────────────────────────────────
def ticker(pl, r7, gate, prs_n, day=None):
    today = datetime.now(KST).date()
    ok_today = next((d["ok"] for d in r7["per_day"] if d["date"] == today.strftime("%m/%d")), 0)
    cur = {"episodes": pl.get("episodes"), "posts": pl.get("posts"), "threads": pl.get("threads"), "runs_ok": ok_today,
           "gate_sections": gate["sections"] if gate else None, "open_prs": prs_n, "reports": len(reports_today())}
    os.makedirs(STATS_DIR, exist_ok=True)
    f = os.path.join(STATS_DIR, "stats_%s.json" % today.isoformat())
    if not os.path.exists(f):
        io.open(f, "w", encoding="utf-8").write(json.dumps({"date": today.isoformat(), **cur}, ensure_ascii=False))
    prev = None
    for i in range(1, 8):
        pf = os.path.join(STATS_DIR, "stats_%s.json" % (today - timedelta(days=i)).isoformat())
        if os.path.exists(pf):
            prev = json.load(io.open(pf, encoding="utf-8")); break
    items = [("발행 편", "episodes"), ("게시물", "posts"), ("Threads", "threads"), ("오늘 회차 OK", "runs_ok"), ("게이트 절", "gate_sections"), ("열린 PR", "open_prs"), ("오늘 리포트", "reports")]
    out = []
    for label, k in items:
        v = cur.get(k); d = (v - prev[k]) if (prev and prev.get(k) is not None and v is not None) else None
        out.append({"label": label, "value": v, "delta": d, "prev_date": prev["date"] if prev else None})
    out.append({"label": "SKILL", "value": skill_version(), "delta": None})
    return out


def hud(snapshot, day=None):
    pl = publog()
    r7 = runs7()
    gate = latest_gate()
    prs = open_prs()
    q = approvals(snapshot.get("terminals"), snapshot.get("scheduled"))
    hr = headroom_today()
    return {"ok": True, "at": datetime.now(KST).isoformat(timespec="seconds"),
            "ticker": ticker(pl, r7, gate, len([p for p in prs if p.get("n")])),
            "approvals": q, "runs7": r7, "publog": pl, "gate": gate, "reports": reports_today(day), "headroom": hr, "prs": prs}


def _self_test():
    import tempfile
    d = tempfile.mkdtemp()
    global HQ_LOGS
    old = HQ_LOGS; HQ_LOGS = d
    try:
        today = datetime.now(KST).strftime("%Y%m%d")
        io.open(os.path.join(d, "job-scout_%s.log" % today), "w", encoding="utf-8").write("x\nSTATUS: OK\n")
        io.open(os.path.join(d, "tomangchi-scout_%s.log" % today), "w", encoding="utf-8").write("x\nSTATUS: FAIL git-sync\n")
        io.open(os.path.join(d, "morning-vault-health_%s.log" % today), "w", encoding="utf-8").write("headroom: saved this run 1200 tokens\nheadroom: saved this run 300 tokens\nSTATUS: OK\n")
        r = runs7()
        last = r["per_day"][-1]
        assert last["ok"] == 2 and last["fail"] == 1 and last["none"] == 2, last          # 5작업 중 OK2 · FAIL1 · 없음2
        assert headroom_today() == {"tokens": 1500, "runs": 2}
        io.open(os.path.join(d, "hermes-event-watch_%s.log" % today), "w", encoding="utf-8").write("시작만\n")
        assert runs7()["grid"][0]["days"][-1]["state"] in ("running", "nostatus")            # STATUS 없는 회차는 OK 로 읽지 않는다
    finally:
        HQ_LOGS = old
    assert headroom_today() is None or headroom_today()["runs"] >= 0
    pl = publog(); assert pl.get("episodes", 0) > 30 and pl["posts"] >= pl["episodes"], pl.get("error")
    print("self-test OK — 회차 격자 OK/FAIL/없음 · headroom 합 · STATUS 없음은 OK 아님 · 발행로그 실값 %d편/%d게시물" % (pl["episodes"], pl["posts"]))


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if "--self-test" in sys.argv:
        _self_test()
    else:
        print(json.dumps(hud({"terminals": [], "scheduled": []}), ensure_ascii=False, indent=1, default=str)[:6000])
