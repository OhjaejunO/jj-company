# -*- coding: utf-8 -*-
r"""세션 대시보드 1판 — «지금 어느 에이전트가 무슨 일을 하고 있나» 를 한 페이지로 (2026-09-04 · JJ 지시).

    py tools\session-dashboard\dashboard.py            → http://127.0.0.1:8765
    py tools\session-dashboard\dashboard.py --once     → JSON 한 번 찍고 끝 (검사용)
    py tools\session-dashboard\dashboard.py --self-test

데이터 출처는 셋이고 전부 **읽기**다 (정관 §0 A등급 자리) — 쓰기는 사람이 입력창에서 보낼 때 한 번뿐.
  ① `orca terminal list --json`  — 살아 있는 터미널 (핸들·워크트리·브랜치·마지막 출력 시각·미리보기)
  ② `~\.claude\projects\<프로젝트>\<세션>.jsonl` — Claude Code 세션 기록(AI 제목·마지막 지시·마지막 답·모델·컨텍스트)
  ③ `C:\Users\ojaej\jj-company\logs\scheduled\*_<오늘>.log` — 터미널이 없는 스케줄 에이전트의 STATUS
클릭 이동은 `orca terminal switch`, 지시 전송은 `orca terminal send --enter` 다. tmux 없는 Windows 에서 Orca 가 그 자리다.

🔴 세션 ↔ 터미널 짝은 **작업 디렉토리**로 맞춘다. 같은 폴더에 세션이 둘이면 «가장 최근에 쓰인 기록»을 고르고
   카드에 `짝 추정` 표시를 남긴다 — 모르는 것을 아는 척하지 않는다.
🔴 127.0.0.1 에만 묶는다. 폰에서 보려면 Tailscale 같은 사설망으로 이 PC 에 붙는다(설계 메모 README).
"""
import argparse
import glob
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, ".claude", "projects")
HQ_LOGS = os.path.join(r"C:\Users\ojaej\jj-company", "logs", "scheduled")
KST = timezone(timedelta(hours=9))
TAIL_BYTES = 3 * 1024 * 1024        # 세션 기록은 수십 MB 라 꼬리만 읽는다
RUNNING_WINDOW_S = 6                # 마지막 터미널 출력이 이 안이면 «작업 중»
ORCA = os.environ.get("ORCA_CLI_COMMAND", "orca")


# ── ① Orca 터미널 ────────────────────────────────────────────────────────────
def orca_json(*args, timeout=20):
    r = subprocess.run([ORCA, *args, "--json"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    try:
        j = json.loads(r.stdout)
    except Exception:
        return {"ok": False, "error": (r.stdout + r.stderr)[:300]}
    return j


def terminals():
    j = orca_json("terminal", "list")
    if not j.get("ok"):
        return [], j.get("error") or "orca terminal list 실패"
    return j.get("result", {}).get("terminals", []), None


# ── ② 세션 기록 ──────────────────────────────────────────────────────────────
def project_dir_for(path):
    """Claude Code 가 쓰는 프로젝트 폴더 이름 — 경로의 구분자·콜론을 «-» 로 바꾼 것."""
    p = path.replace("/", "\\")
    return os.path.join(PROJECTS, re.sub(r"[\\:]", "-", p))


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def read_session(jsonl):
    """꼬리 3MB 만 읽어 카드에 필요한 것만 뽑는다."""
    size = os.path.getsize(jsonl)
    with io.open(jsonl, "rb") as fh:
        if size > TAIL_BYTES:
            fh.seek(size - TAIL_BYTES)
            fh.readline()               # 잘린 첫 줄 버림
        raw = fh.read().decode("utf-8", errors="replace")
    out = {"session": os.path.splitext(os.path.basename(jsonl))[0], "title": None, "last_prompt": None,
           "last_reply": None, "model": None, "effort": None, "context_tokens": None, "pr": None,
           "last_ts": None, "tools_recent": [], "turns_tail": 0}
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
            txt = _text_of(c).strip()
            if txt and not txt.startswith("<"):
                out["last_prompt"] = txt
            out["last_ts"] = j.get("timestamp") or out["last_ts"]
            out["turns_tail"] += 1
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
    return out


def session_for(worktree_path):
    """작업 디렉토리로 세션 기록을 찾는다. 후보가 여럿이면 가장 최근에 쓰인 것 + «짝 추정»."""
    d = project_dir_for(worktree_path)
    files = sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getmtime, reverse=True)
    if not files:
        return None
    # 최근 1시간 안에 쓰인 것이 둘 이상이면 짝을 확신할 수 없다
    now = time.time()
    live = [f for f in files if now - os.path.getmtime(f) < 3600]
    s = read_session(files[0])
    s["guess"] = len(live) > 1
    s["mtime"] = os.path.getmtime(files[0])
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
        last = lines[-1] if lines else ""
        cards.append({"kind": "scheduled", "name": name, "status": status, "last_line": last[-160:],
                      "mtime": os.path.getmtime(f), "log": f,
                      "running": status is None and (time.time() - os.path.getmtime(f)) < 120})
    return cards


# ── 조립 ─────────────────────────────────────────────────────────────────────
def snapshot():
    terms, err = terminals()
    now_ms = int(time.time() * 1000)
    cards = []
    for t in terms:
        wt = t.get("worktreePath") or ""
        s = session_for(wt) if wt else None
        age_s = (now_ms - (t.get("lastOutputAt") or 0)) / 1000.0
        cards.append({
            "kind": "terminal", "handle": t.get("handle"), "title": t.get("title"),
            "repo": os.path.basename(wt.rstrip("/\\")) or wt, "path": wt,
            "branch": (t.get("branch") or "").replace("refs/heads/", ""),
            "agent": t.get("agentIdentity"), "writable": t.get("writable"), "connected": t.get("connected"),
            "preview": t.get("preview"), "last_output_age_s": round(age_s, 1),
            "running": age_s < RUNNING_WINDOW_S, "session": s,
        })
    cards.sort(key=lambda c: c["last_output_age_s"])
    return {"ok": err is None, "error": err, "at": datetime.now(KST).isoformat(timespec="seconds"),
            "terminals": cards, "scheduled": scheduled_today()}


def send_text(handle, text):
    return orca_json("terminal", "send", "--terminal", handle, "--text", text, "--enter")


def switch_to(handle):
    return orca_json("terminal", "switch", "--terminal", handle)


# ── HTTP ─────────────────────────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            b = io.open(os.path.join(HERE, "index.html"), "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif p == "/api/snapshot":
            try:
                self._json(snapshot())
            except Exception as e:  # noqa: BLE001 — 실패를 화면에 보인다 (조용히 빈 판을 내지 않는다)
                self._json({"ok": False, "error": repr(e), "terminals": [], "scheduled": []}, 500)
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

    def log_message(self, fmt, *args):   # 콘솔 소음 줄임 — 오류만
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def _self_test():
    """역검증 — ① 세션 파서가 실제 값을 담는가 ② 없는 폴더는 None 인가 ③ 나쁜 핸들은 거부되는가."""
    import tempfile
    d = tempfile.mkdtemp()
    f = os.path.join(d, "s.jsonl")
    rows = [{"type": "ai-title", "aiTitle": "테스트 제목"},
            {"type": "user", "message": {"content": "표지 고쳐줘"}, "timestamp": "2026-09-04T10:00:00Z"},
            {"type": "assistant", "effort": "high", "message": {"model": "claude-fable-5-1",
             "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "cache_creation_input_tokens": 0},
             "content": [{"type": "text", "text": "고쳤습니다."}, {"type": "tool_use", "name": "Bash"}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}]
    io.open(f, "w", encoding="utf-8").write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    s = read_session(f)
    assert s["title"] == "테스트 제목" and s["last_prompt"] == "표지 고쳐줘" and s["last_reply"] == "고쳤습니다."
    assert s["context_tokens"] == 100 and s["tools_recent"] == ["Bash"] and s["model"] == "claude-fable-5-1"
    assert session_for(os.path.join(d, "no-such-dir-zz")) is None
    assert not re.fullmatch(r"term_[A-Za-z0-9-]+", "term_x; rm -rf")
    # 반대쪽 — 빈 기록은 값이 비어야 한다 (파서가 헛값을 지어내지 않는다)
    io.open(f, "w", encoding="utf-8").write("")
    e = read_session(f)
    assert e["title"] is None and e["last_prompt"] is None and e["context_tokens"] is None
    print("self-test OK — 파서 값 담김 · 없는 폴더 None · 나쁜 핸들 거부 · 빈 기록은 빈 값")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return _self_test()
    if a.once:
        print(json.dumps(snapshot(), ensure_ascii=False, indent=1))
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
