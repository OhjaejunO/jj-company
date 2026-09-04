# -*- coding: utf-8 -*-
r"""세션 대시보드 — «지금 어느 에이전트가 무슨 일을 하고 있나» 를 한 페이지로 (2026-09-04 · JJ 지시).

    py tools\session-dashboard\dashboard.py            → http://127.0.0.1:8765
    py tools\session-dashboard\dashboard.py --once     → JSON 한 번 찍고 끝 (검사용)
    py tools\session-dashboard\dashboard.py --probe <작업폴더>   → 그 폴더로 네 읽기 함수가 무엇을 돌려주는지 (실물 검증)
    py tools\session-dashboard\dashboard.py --self-test

데이터 출처는 전부 **읽기**다 (정관 §0 A등급 자리) — 쓰기는 사람이 입력창에서 보낼 때 한 번뿐.
  ① `orca terminal list --json`  — 살아 있는 터미널 (핸들·워크트리·브랜치·마지막 출력·미리보기·agentIdentity·agentWait)
  ② 에이전트별 세션 기록 (2판 · 2026-09-04 JJ «헤르메스·코덱스·그록·클로드 전부»)
       claude  `~\.claude\projects\<프로젝트>\<세션>.jsonl`        — ai-title · last-prompt · pr-link · user/assistant
       codex   `~\.codex\sessions\<연>\<월>\<일>\rollout-*.jsonl`  — session_meta.cwd · turn_context.model · message user/assistant
       grok    `~\.grok\sessions\<작업폴더 URL 인코딩>\<세션>\`      — summary.json · prompt_history.jsonl · chat_history.jsonl
       hermes  `%LOCALAPPDATA%\hermes\state.db`                    — sessions · messages (작업 폴더 개념이 없어 최근 활동으로만 짝)
  ③ `C:\Users\ojaej\jj-company\logs\scheduled\*_<오늘>.log` — 터미널이 없는 스케줄 에이전트의 STATUS
클릭 이동은 `orca terminal switch`, 지시 전송은 `orca terminal send --enter`. tmux 없는 Windows 에서 Orca 가 그 자리다.

🔴 세션 ↔ 터미널 짝은 **agentIdentity + 작업 디렉토리**로 맞춘다. identity 를 모르면 네 읽기 함수를 다 돌려 가장 최근 것을 고르고
   카드에 `짝 추정` 을 남긴다 — 모르는 것을 아는 척하지 않는다. 헤르메스는 폴더 개념이 없어 항상 «추정» 이다.
🔴 127.0.0.1 에만 묶는다. 폰에서 보려면 Tailscale 같은 사설망으로 이 PC 에 붙는다(README).
"""
import argparse
import glob
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, quote

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
CODEX_SESSIONS = os.path.join(HOME, ".codex", "sessions")
GROK_SESSIONS = os.path.join(HOME, ".grok", "sessions")
HERMES_DB = os.path.join(os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local")), "hermes", "state.db")
HQ_LOGS = os.path.join(r"C:\Users\ojaej\jj-company", "logs", "scheduled")
KST = timezone(timedelta(hours=9))
TAIL_BYTES = 3 * 1024 * 1024        # 세션 기록은 수십 MB 라 꼬리만 읽는다
RUNNING_WINDOW_S = 6                # 마지막 터미널 출력이 이 안이면 «작업 중»
RECENT_S = 3600                     # 이 안에 쓰인 기록만 «살아 있는 후보» 로 본다
ORCA = os.environ.get("ORCA_CLI_COMMAND", "orca")
AGENTS = ("claude", "codex", "grok", "hermes")


def _norm(path):
    return (path or "").replace("/", "\\").rstrip("\\").lower()


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and b.get("type") in ("text", "input_text", "output_text"):
                out.append(b.get("text", ""))
        return "\n".join(out)
    return ""


def _clean_prompt(txt):
    """시스템이 끼운 문장(<system-reminder>·AGENTS.md 주입)은 사람의 지시가 아니다."""
    t = (txt or "").strip()
    if not t or t.startswith("<") or t.startswith("# AGENTS.md"):
        return None
    return t


def _blank(agent):
    return {"agent": agent, "session": None, "title": None, "last_prompt": None, "last_reply": None,
            "model": None, "effort": None, "context_tokens": None, "pr": None, "last_ts": None,
            "tools_recent": [], "mtime": None, "guess": False}


# ── ① Orca 터미널 ────────────────────────────────────────────────────────────
def orca_json(*args, timeout=20):
    r = subprocess.run([ORCA, *args, "--json"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"ok": False, "error": (r.stdout + r.stderr)[:300]}


def terminals():
    j = orca_json("terminal", "list")
    if not j.get("ok"):
        return [], j.get("error") or "orca terminal list 실패"
    return j.get("result", {}).get("terminals", []), None


# ── ② claude ─────────────────────────────────────────────────────────────────
def claude_project_dir(path):
    return os.path.join(CLAUDE_PROJECTS, re.sub(r"[\\:]", "-", path.replace("/", "\\")))


def read_claude_file(jsonl):
    size = os.path.getsize(jsonl)
    with io.open(jsonl, "rb") as fh:
        if size > TAIL_BYTES:
            fh.seek(size - TAIL_BYTES)
            fh.readline()
        raw = fh.read().decode("utf-8", errors="replace")
    out = _blank("claude")
    out["session"] = os.path.splitext(os.path.basename(jsonl))[0]
    for line in raw.splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        t = j.get("type")
        if t == "ai-title":
            out["title"] = j.get("aiTitle")
        elif t == "last-prompt":
            out["last_prompt"] = j.get("lastPrompt")
        elif t == "pr-link":
            out["pr"] = {"url": j.get("prUrl"), "n": j.get("prNumber")}
        elif t == "user":
            if j.get("isMeta") or j.get("isSidechain"):
                continue
            c = (j.get("message") or {}).get("content")
            if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                continue
            p = _clean_prompt(_text_of(c))
            if p:
                out["last_prompt"] = p
            out["last_ts"] = j.get("timestamp") or out["last_ts"]
        elif t == "assistant":
            if j.get("isSidechain"):
                continue
            m = j.get("message") or {}
            out["model"] = m.get("model") or out["model"]
            out["effort"] = j.get("effort") or out["effort"]
            u = m.get("usage") or {}
            if u:
                out["context_tokens"] = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                                         + u.get("cache_creation_input_tokens", 0))
            txt = _text_of(m.get("content")).strip()
            if txt:
                out["last_reply"] = txt
            for b in (m.get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    out["tools_recent"].append(b.get("name"))
            out["last_ts"] = j.get("timestamp") or out["last_ts"]
    out["tools_recent"] = out["tools_recent"][-6:]
    out["mtime"] = os.path.getmtime(jsonl)
    return out


def read_claude(cwd):
    files = sorted(glob.glob(os.path.join(claude_project_dir(cwd), "*.jsonl")), key=os.path.getmtime, reverse=True)
    if not files:
        return None
    s = read_claude_file(files[0])
    s["guess"] = sum(1 for f in files if time.time() - os.path.getmtime(f) < RECENT_S) > 1
    return s


# ── ② codex ──────────────────────────────────────────────────────────────────
def _codex_meta_cwd(path):
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        first = fh.readline()
    try:
        j = json.loads(first)
        return (j.get("payload") or {}).get("cwd") if j.get("type") == "session_meta" else None
    except Exception:
        return None


def read_codex_file(path):
    out = _blank("codex")
    out["session"] = os.path.basename(path)
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                j = json.loads(line)
            except Exception:
                continue
            t, p = j.get("type"), j.get("payload") or {}
            if t == "turn_context":
                out["model"] = p.get("model") or out["model"]
                out["effort"] = (p.get("collaboration_mode") or {}).get("reasoning_effort") if isinstance(p.get("collaboration_mode"), dict) else out["effort"]
            elif t == "response_item" and p.get("type") == "message":
                txt = _text_of(p.get("content")).strip()
                if p.get("role") == "user":
                    c = _clean_prompt(txt)
                    if c:
                        out["last_prompt"] = c
                        out["last_ts"] = j.get("timestamp")
                elif p.get("role") == "assistant" and txt:
                    out["last_reply"] = txt
                    out["last_ts"] = j.get("timestamp")
            elif t == "response_item" and p.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
                out["tools_recent"].append(p.get("name") or p.get("type"))
            elif t == "event_msg" and p.get("type") == "token_count":
                info = p.get("info") or {}
                tot = (info.get("total_token_usage") or {})
                if tot.get("input_tokens") is not None:
                    out["context_tokens"] = tot.get("input_tokens")
    out["tools_recent"] = out["tools_recent"][-6:]
    out["mtime"] = os.path.getmtime(path)
    out["title"] = (out["last_prompt"] or "")[:60] or None
    return out


def read_codex(cwd):
    """최근 파일 60개 안에서 session_meta.cwd 가 같은 롤아웃 중 가장 최근."""
    files = sorted(glob.glob(os.path.join(CODEX_SESSIONS, "*", "*", "*", "rollout-*.jsonl")),
                   key=os.path.getmtime, reverse=True)[:60]
    mine = [f for f in files if _norm(_codex_meta_cwd(f)) == _norm(cwd)]
    if not mine:
        return None
    s = read_codex_file(mine[0])
    s["guess"] = sum(1 for f in mine if time.time() - os.path.getmtime(f) < RECENT_S) > 1
    return s


# ── ② grok ───────────────────────────────────────────────────────────────────
def grok_session_dir(cwd):
    return os.path.join(GROK_SESSIONS, quote(cwd.replace("/", "\\"), safe=""))


def read_grok_dir(d):
    out = _blank("grok")
    out["session"] = os.path.basename(d)
    try:
        summ = json.load(io.open(os.path.join(d, "summary.json"), encoding="utf-8"))
    except Exception:
        summ = {}
    out["model"] = summ.get("current_model_id")
    out["effort"] = summ.get("reasoning_effort")
    out["title"] = summ.get("session_summary") or summ.get("agent_name") or None
    out["last_ts"] = summ.get("last_active_at") or summ.get("updated_at")
    ch = os.path.join(d, "chat_history.jsonl")
    if os.path.exists(ch):
        for line in io.open(ch, encoding="utf-8", errors="replace"):
            try:
                j = json.loads(line)
            except Exception:
                continue
            if j.get("synthetic_reason"):
                continue
            txt = _text_of(j.get("content")).strip()
            if j.get("type") == "user":
                c = _clean_prompt(txt)
                if c:
                    out["last_prompt"] = c
            elif j.get("type") == "assistant" and txt:
                out["last_reply"] = txt
            elif j.get("type") in ("tool_use", "tool_call") and j.get("name"):
                out["tools_recent"].append(j.get("name"))
    ph = os.path.join(os.path.dirname(d), "prompt_history.jsonl")
    if not out["last_prompt"] and os.path.exists(ph):
        for line in io.open(ph, encoding="utf-8", errors="replace"):
            try:
                j = json.loads(line)
            except Exception:
                continue
            if j.get("session_id") == out["session"] and j.get("prompt"):
                out["last_prompt"] = j["prompt"].strip()
    out["tools_recent"] = out["tools_recent"][-6:]
    out["mtime"] = max((os.path.getmtime(os.path.join(d, f)) for f in os.listdir(d)), default=os.path.getmtime(d))
    return out


def read_grok(cwd):
    base = grok_session_dir(cwd)
    if not os.path.isdir(base):
        return None
    dirs = [os.path.join(base, x) for x in os.listdir(base) if os.path.isdir(os.path.join(base, x))]
    if not dirs:
        return None
    dirs.sort(key=lambda d: os.path.getmtime(os.path.join(d, "summary.json")) if os.path.exists(os.path.join(d, "summary.json")) else os.path.getmtime(d), reverse=True)
    s = read_grok_dir(dirs[0])
    s["guess"] = sum(1 for d in dirs if time.time() - os.path.getmtime(d) < RECENT_S) > 1
    return s


# ── ② hermes ─────────────────────────────────────────────────────────────────
def read_hermes(db=None):
    """가장 최근 메시지가 있는 세션 하나. 헤르메스는 작업 폴더 개념이 없어 짝은 늘 추정이다."""
    db = db or HERMES_DB
    if not os.path.exists(db):
        return None
    try:
        c = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
        row = c.execute("select session_id, max(timestamp) from messages group by session_id order by 2 desc limit 1").fetchone()
        if not row:
            return None
        sid, ts = row
        sess = c.execute("select display_name, model, source from sessions where id=?", (sid,)).fetchone() or (None, None, None)
        msgs = c.execute("select role, content, tool_name, timestamp from messages where session_id=? order by timestamp", (sid,)).fetchall()
    except sqlite3.Error as e:
        s = _blank("hermes"); s["title"] = "state.db 읽기 실패: %s" % e
        return s
    out = _blank("hermes")
    out["session"], out["title"], out["model"] = str(sid), sess[0] or ("hermes · %s" % (sess[2] or "")), sess[1]
    for role, content, tool, t in msgs:
        txt = _text_of(content) if not isinstance(content, str) or not content.startswith("[") else content
        if role == "user":
            p = _clean_prompt(txt)
            if p:
                out["last_prompt"] = p
        elif role == "assistant" and txt and txt.strip():
            out["last_reply"] = txt.strip()
        elif role == "tool" and tool:
            out["tools_recent"].append(tool)
        out["last_ts"] = t
    out["tools_recent"] = out["tools_recent"][-6:]
    try:
        out["mtime"] = float(ts) if ts and float(ts) < 1e12 else (float(ts) / 1000 if ts else None)
    except (TypeError, ValueError):
        out["mtime"] = None
    out["guess"] = True
    return out


READERS = {"claude": lambda cwd: read_claude(cwd), "codex": lambda cwd: read_codex(cwd),
           "grok": lambda cwd: read_grok(cwd), "hermes": lambda cwd: read_hermes()}


def session_for(cwd, identity):
    """identity 를 알면 그 읽기 함수, 모르면 넷을 다 돌려 가장 최근 것 (+ 짝 추정)."""
    if identity in READERS:
        return READERS[identity](cwd) if cwd or identity == "hermes" else None
    cands = [s for s in (r(cwd) for r in READERS.values()) if s and s.get("mtime")]
    if not cands:
        return None
    cands.sort(key=lambda s: s["mtime"], reverse=True)
    s = cands[0]
    s["guess"] = True
    return s


# ── ③ 스케줄 에이전트 로그 ───────────────────────────────────────────────────
def scheduled_today():
    today = datetime.now(KST).strftime("%Y%m%d")
    cards = []
    for f in sorted(glob.glob(os.path.join(HQ_LOGS, "*_%s.log" % today))):
        name = os.path.basename(f).rsplit("_", 1)[0]
        try:
            lines = io.open(f, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        status = next((l for l in reversed(lines) if "STATUS:" in l), None)
        cards.append({"kind": "scheduled", "name": name, "status": status, "last_line": (lines[-1] if lines else "")[-160:],
                      "mtime": os.path.getmtime(f), "log": f,
                      # 정관 §1 조직도 — cross-verify 는 codex 감리, hermes-event-watch 는 헤르메스 sagun, 결정적 작업(백업·드리프트·발행 래퍼)은 에이전트 없음
                      "agent": ("hermes" if "hermes" in name else "codex" if "cross-verify" in name
                                else "script" if name in ("workshop-backup", "skill-drift-audit", "publish-threads") else "claude"),
                      "running": status is None and (time.time() - os.path.getmtime(f)) < 120})
    return cards


# ── 조립 ─────────────────────────────────────────────────────────────────────
def snapshot():
    terms, err = terminals()
    now_ms = int(time.time() * 1000)
    cards = []
    for t in terms:
        wt = t.get("worktreePath") or ""
        ident = (t.get("agentIdentity") or "").lower() or None
        s = session_for(wt, ident)
        age_s = (now_ms - (t.get("lastOutputAt") or 0)) / 1000.0
        wait = t.get("agentWait")
        cards.append({
            "kind": "terminal", "handle": t.get("handle"), "title": t.get("title"),
            "repo": os.path.basename(wt.rstrip("/\\")) or wt, "path": wt,
            "branch": (t.get("branch") or "").replace("refs/heads/", ""),
            "agent": ident or (s or {}).get("agent") or "unknown",
            "writable": t.get("writable"), "connected": t.get("connected"),
            "preview": t.get("preview"), "last_output_age_s": round(age_s, 1),
            "waiting": bool(wait), "wait": wait,
            "running": age_s < RUNNING_WINDOW_S and not wait, "session": s,
        })
    cards.sort(key=lambda c: (not c["waiting"], not c["running"], c["last_output_age_s"]))
    return {"ok": err is None, "error": err, "at": datetime.now(KST).isoformat(timespec="seconds"),
            "terminals": cards, "scheduled": scheduled_today()}


# ── 오피스 명부 — «JJ 가 쓰는 에이전트 전부» 가 항상 자기 책상을 갖는다 (2026-09-04 JJ 지시) ──────────
#: 근거는 정관 §1 조직도 + §4 스케줄 현황판. 상태 출처는 셋 — 스케줄 로그(오늘) · Orca 터미널 · 헤르메스 state.db.
#: 🔴 명부에 없는 살아 있는 터미널은 «방문 세션» 으로 개발팀 구역에 임시 책상을 받는다 — 빠뜨리지 않는다.
ROSTER = [
    {"id": "dev-claude", "name": "클로드", "dept": "개발팀", "role": "구현·검증 (대화 세션)", "agent": "claude", "src": {"identity": "claude"}},
    {"id": "dev-codex", "name": "코덱스", "dept": "개발팀", "role": "구현 (대화 세션)", "agent": "codex", "src": {"identity": "codex"}},
    {"id": "dev-grok", "name": "그록", "dept": "개발팀", "role": "실험 (대화 세션)", "agent": "grok", "src": {"identity": "grok"}},
    {"id": "ops-auditor", "name": "ops-auditor", "dept": "운영팀", "role": "vault 건강 감사 · 평일 12:30", "agent": "claude", "src": {"scheduled": "morning-vault-health"}},
    {"id": "content-scout", "name": "content-scout", "dept": "마케팅팀", "role": "토망치랩 아침 스캔 · 08:00", "agent": "claude", "src": {"scheduled": "tomangchi-scout"}},
    {"id": "job-scout", "name": "job-scout", "dept": "영업팀", "role": "채용 공고 발굴 · 08:30", "agent": "claude", "src": {"scheduled": "job-scout"}},
    {"id": "cross-verify", "name": "교차검증", "dept": "감리", "role": "타모델 감리 (codex)", "agent": "codex", "src": {"scheduled": "cross-verify"}},
    {"id": "sagun", "name": "사건 (sagun)", "dept": "헤르메스", "role": "사건 감시 · 07:40", "agent": "hermes", "src": {"scheduled": "hermes-event-watch"}},
    {"id": "gumsu", "name": "검수 (gumsu)", "dept": "헤르메스", "role": "크로스 모델 검수 (xreview)", "agent": "hermes", "src": {"hermes": True}},
]
MACHINES = [  # 에이전트 없는 결정적 작업 — 서버실 램프
    ("workshop-backup", "워크숍 백업 · 일 13:00 + 발행 직후"), ("skill-drift-audit", "스킬 드리프트 감사 · 12:30"),
    ("publish-threads", "Threads 발행 래퍼"),
]
DEPT_ORDER = ["개발팀", "운영팀", "마케팅팀", "영업팀", "감리", "헤르메스"]


def _sched_state(card):
    """스케줄 로그 → (state, note). 오늘 로그 없음 = sleep(출근 전) · STATUS 없음+최근 = running · FAIL = waiting · OK = idle."""
    if card is None:
        return "sleep", "오늘 아직 안 돌았어요"
    if card["running"]:
        return "running", "실행 중"
    st = card["status"] or ""
    t = datetime.fromtimestamp(card["mtime"], KST).strftime("%H:%M")
    if "FAIL" in st:
        return "waiting", "FAIL · " + st.split("STATUS:")[-1].strip()[:40]
    if "STATUS:" in st:
        return "idle", "완료 " + t + " · " + st.split("STATUS:")[-1].strip()[:30]
    return "idle", "로그만 있음 · " + t


def office():
    snap = snapshot()
    sched = {c["name"]: c for c in snap["scheduled"]}
    terms = list(snap["terminals"])
    desks = []
    for r in ROSTER:
        src = r["src"]
        d = {"id": r["id"], "name": r["name"], "dept": r["dept"], "role": r["role"], "agent": r["agent"],
             "state": "sleep", "note": "", "handle": None, "title": None, "prompt": None, "repo": None}
        if "identity" in src:
            mine = [t for t in terms if t["agent"] == src["identity"]]
            if mine:
                t = mine.pop(0); terms.remove(t)
                s = t.get("session") or {}
                d.update({"state": "waiting" if t["waiting"] else "running" if t["running"] else "idle",
                          "handle": t["handle"], "title": s.get("title") or t.get("title"), "prompt": s.get("last_prompt"),
                          "repo": t["repo"] + " · " + (t["branch"] or ""),
                          "note": "확인 필요" if t["waiting"] else ("작업 중" if t["running"] else "대기 · %d분 전" % (t["last_output_age_s"] // 60))})
                # 같은 종류의 터미널이 더 있으면 옆자리에 하나씩
                for extra in list(mine):
                    terms.remove(extra)
                    s2 = extra.get("session") or {}
                    desks.append(dict(d, id=r["id"] + "-" + extra["handle"][-6:], name=r["name"] + " (" + extra["repo"] + ")",
                                      state="waiting" if extra["waiting"] else "running" if extra["running"] else "idle",
                                      handle=extra["handle"], title=s2.get("title") or extra.get("title"), prompt=s2.get("last_prompt"),
                                      repo=extra["repo"] + " · " + (extra["branch"] or ""), note="작업 중" if extra["running"] else "대기"))
            else:
                d["note"] = "자리 비움 — Orca 탭 없음"
        elif "scheduled" in src:
            c = sched.get(src["scheduled"])
            d["state"], d["note"] = _sched_state(c)
            if c and c["running"]:
                d["title"] = c["last_line"][:80]
        elif src.get("hermes"):
            # gumsu 는 스케줄이 아니라 편 제작 때 xreview 로 불린다 — 오늘 리포트가 있으면 «오늘 N회 검수»
            today = datetime.now(KST).strftime("%Y-%m-%d")
            xr = sorted(glob.glob(os.path.join(os.path.dirname(HQ_LOGS), "..", "reports", today + "_xreview_*.md")), key=os.path.getmtime)
            if xr:
                d.update({"state": "idle", "note": "오늘 검수 %d회 · 마지막 %s" % (len(xr), datetime.fromtimestamp(os.path.getmtime(xr[-1]), KST).strftime("%H:%M")),
                          "title": os.path.basename(xr[-1]).replace(today + "_xreview_", "").replace(".md", "") + " 검수"})
            else:
                d["note"] = "호출 대기 (xreview 는 편 제작 때만)"
        desks.append(d)
    # 명부 밖 방문 세션 — 빠뜨리지 않는다
    for t in terms:
        s = t.get("session") or {}
        desks.append({"id": "visit-" + (t["handle"] or "")[-6:], "name": "방문 세션 (" + (t["agent"] or "?") + ")", "dept": "개발팀",
                      "role": t["repo"], "agent": t["agent"] if t["agent"] in AGENTS else "claude",
                      "state": "waiting" if t["waiting"] else "running" if t["running"] else "idle", "note": "명부 밖",
                      "handle": t["handle"], "title": s.get("title") or t.get("title"), "prompt": s.get("last_prompt"), "repo": t["repo"]})
    machines = []
    for name, label in MACHINES:
        c = sched.get(name)
        st, note = _sched_state(c)
        machines.append({"name": name, "label": label, "state": st, "note": note})
    return {"ok": snap["ok"], "error": snap["error"], "at": snap["at"], "dept_order": DEPT_ORDER, "desks": desks, "machines": machines}


#: 리포트 파일명 → (만든 에이전트, 받는 사람). 오늘 `reports\` 에 생기는 파일이 곧 «전달» 이벤트다 — 캐릭터가 걸어가 건네준다.
REPORT_ROUTES = [
    (r"_vault-health", "ops-auditor", "jj"), (r"_tomangchi-scout", "content-scout", "jj"), (r"_job-scout", "job-scout", "jj"),
    (r"_cross-verify", "cross-verify", "jj"), (r"_xreview_", "gumsu", "dev-claude"), (r"hermes-event|_event-watch", "sagun", "jj"),
    (r"_dist_|_publish_|_oss-|_workshop-backup", "dev-claude", "jj"),
]
HQ_REPORTS = os.path.join(os.path.dirname(HQ_LOGS), "..", "reports")


def events_today():
    """오늘 생긴 리포트를 시각순으로 — 프런트가 «걸어가서 건네주기» 로 재생한다. 파일 존재가 근거다(추측 없음)."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    out = []
    for f in glob.glob(os.path.join(HQ_REPORTS, today + "*")):
        name = os.path.basename(f)
        for pat, frm, to in REPORT_ROUTES:
            if re.search(pat, name):
                out.append({"id": name, "ts": os.path.getmtime(f), "from": frm, "to": to,
                            "label": name.replace(today + "_", "").rsplit(".", 1)[0][:40]})
                break
    out.sort(key=lambda e: e["ts"])
    return out


def send_text(handle, text):
    return orca_json("terminal", "send", "--terminal", handle, "--text", text, "--enter")


def switch_to(handle):
    return orca_json("terminal", "switch", "--terminal", handle)


# ── HTTP ─────────────────────────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _file(self, path, ctype):
        b = io.open(path, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "max-age=3600" if ctype.startswith("image/") else "no-cache")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            self._file(os.path.join(HERE, "index.html"), "text/html; charset=utf-8")
        elif p == "/office":
            self._file(os.path.join(HERE, "office.html"), "text/html; charset=utf-8")
        elif p.startswith("/assets/"):
            # 오피스 뷰 컷아웃 — 이름은 <agent>_<pose>.png 꼴만. 경로 탈출 차단.
            name = p[len("/assets/"):]
            if not re.fullmatch(r"(claude|codex|grok|hermes)_(typing|idle|hand|stand)\.png|office_bg\.(png|jpg)", name):
                return self._json({"ok": False, "error": "not found"}, 404)
            fp = os.path.join(HERE, "assets", name)
            if not os.path.exists(fp):
                return self._json({"ok": False, "error": "asset missing: " + name}, 404)
            self._file(fp, "image/png")
        elif p == "/api/snapshot":
            try:
                self._json(snapshot())
            except Exception as e:  # noqa: BLE001 — 실패를 화면에 보인다 (조용히 빈 판을 내지 않는다)
                self._json({"ok": False, "error": repr(e), "terminals": [], "scheduled": []}, 500)
        elif p == "/api/events":
            try:
                self._json({"ok": True, "events": events_today()})
            except Exception as e:  # noqa: BLE001
                self._json({"ok": False, "error": repr(e), "events": []}, 500)
        elif p == "/api/office":
            try:
                self._json(office())
            except Exception as e:  # noqa: BLE001
                self._json({"ok": False, "error": repr(e), "desks": [], "machines": [], "dept_order": DEPT_ORDER}, 500)
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        handle = body.get("handle") or ""
        if not re.fullmatch(r"term_[A-Za-z0-9-]+", handle):
            return self._json({"ok": False, "error": "bad handle"}, 400)
        if p == "/api/send":
            text = (body.get("text") or "").strip()
            if not text:
                return self._json({"ok": False, "error": "empty"}, 400)
            return self._json(send_text(handle, text))
        if p == "/api/switch":
            return self._json(switch_to(handle))
        self._json({"ok": False, "error": "not found"}, 404)

    def log_message(self, fmt, *args):
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


# ── 역검증 ───────────────────────────────────────────────────────────────────
def _self_test():
    """네 읽기 함수가 **실제 값을 담는가** · 빈 기록은 빈 값인가 · 없는 폴더는 None 인가 · 나쁜 핸들은 거부되는가."""
    import tempfile
    d = tempfile.mkdtemp()
    # claude
    f = os.path.join(d, "s.jsonl")
    rows = [{"type": "ai-title", "aiTitle": "테스트 제목"},
            {"type": "user", "message": {"content": "표지 고쳐줘"}, "timestamp": "2026-09-04T10:00:00Z"},
            {"type": "assistant", "effort": "high", "message": {"model": "claude-fable-5-1",
             "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "cache_creation_input_tokens": 0},
             "content": [{"type": "text", "text": "고쳤습니다."}, {"type": "tool_use", "name": "Bash"}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}]
    io.open(f, "w", encoding="utf-8").write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    s = read_claude_file(f)
    assert s["title"] == "테스트 제목" and s["last_prompt"] == "표지 고쳐줘" and s["last_reply"] == "고쳤습니다."
    assert s["context_tokens"] == 100 and s["tools_recent"] == ["Bash"] and s["model"] == "claude-fable-5-1"
    io.open(f, "w", encoding="utf-8").write("")
    e = read_claude_file(f)
    assert e["title"] is None and e["last_prompt"] is None and e["context_tokens"] is None
    # codex
    f = os.path.join(d, "rollout-x.jsonl")
    rows = [{"type": "session_meta", "payload": {"cwd": "C:\\w\\proj"}},
            {"type": "turn_context", "payload": {"model": "gpt-5.5"}},
            {"type": "response_item", "timestamp": "2026-09-04T10:00:00Z", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "# AGENTS.md instructions ..."}]}},
            {"type": "response_item", "timestamp": "2026-09-04T10:00:01Z", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "게임 만들어"}]}},
            {"type": "response_item", "timestamp": "2026-09-04T10:00:02Z", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "만들었습니다."}]}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 1234}}}}]
    io.open(f, "w", encoding="utf-8").write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    c = read_codex_file(f)
    assert c["model"] == "gpt-5.5" and c["last_prompt"] == "게임 만들어" and c["last_reply"] == "만들었습니다." and c["context_tokens"] == 1234
    assert _norm(_codex_meta_cwd(f)) == _norm("C:/w/proj")   # 슬래시·대소문자 무시로 짝이 맞는다
    # grok
    gd = os.path.join(d, "019-sess"); os.makedirs(gd)
    json.dump({"session_summary": "슈팅 게임", "current_model_id": "grok-4.5", "reasoning_effort": "high", "last_active_at": "2026-07-14T07:27:34Z"},
              io.open(os.path.join(gd, "summary.json"), "w", encoding="utf-8"))
    io.open(os.path.join(gd, "chat_history.jsonl"), "w", encoding="utf-8").write(
        json.dumps({"type": "user", "content": [{"type": "text", "text": "<system-reminder>x"}], "synthetic_reason": "system_reminder"}) + "\n"
        + json.dumps({"type": "user", "content": [{"type": "text", "text": "슈팅 게임 만들어줘"}]}, ensure_ascii=False) + "\n"
        + json.dumps({"type": "assistant", "content": [{"type": "text", "text": "index.html 을 만들었어요."}]}, ensure_ascii=False) + "\n")
    g = read_grok_dir(gd)
    assert g["model"] == "grok-4.5" and g["title"] == "슈팅 게임" and g["last_prompt"] == "슈팅 게임 만들어줘" and g["last_reply"].startswith("index.html")
    assert read_grok(os.path.join(d, "no-such-cwd")) is None
    # hermes
    db = os.path.join(d, "state.db")
    c2 = sqlite3.connect(db)
    c2.executescript("create table sessions(id text, display_name text, model text, source text);"
                     "create table messages(session_id text, role text, content text, tool_name text, timestamp real);")
    c2.execute("insert into sessions values('s1','검수 gumsu','nemotron','cli')")
    c2.execute("insert into messages values('s1','user','캡션 검수해','',1788500000)")
    c2.execute("insert into messages values('s1','assistant','지적 0건','',1788500001)")
    c2.commit(); c2.close()
    h = read_hermes(db)
    assert h["title"] == "검수 gumsu" and h["model"] == "nemotron" and h["last_prompt"] == "캡션 검수해" and h["last_reply"] == "지적 0건" and h["guess"]
    assert read_hermes(os.path.join(d, "none.db")) is None
    # 공통
    assert read_claude(os.path.join(d, "no-such-dir-zz")) is None
    assert not re.fullmatch(r"term_[A-Za-z0-9-]+", "term_x; rm -rf")
    print("self-test OK — claude·codex·grok·hermes 파서 값 담김 · 빈 기록은 빈 값 · 없는 폴더/DB None · 나쁜 핸들 거부")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--probe", metavar="CWD", help="그 작업 폴더로 네 읽기 함수를 다 돌려 본다")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return _self_test()
    if a.probe:
        for name, r in READERS.items():
            s = r(a.probe)
            print("==", name, "→", "없음" if s is None else json.dumps({k: (v[:80] if isinstance(v, str) else v) for k, v in s.items()}, ensure_ascii=False, default=str))
        return
    if a.once:
        print(json.dumps(snapshot(), ensure_ascii=False, indent=1, default=str))
        return
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print("session dashboard → http://127.0.0.1:%d  (Ctrl+C 로 종료)" % a.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
