# -*- coding: utf-8 -*-
r"""JJ Company OS - gate-on-stop (Stop hook).

WHY (study-notes proposal A, JJ approved 2026-09-05)
  ep44 needed 21 gate runs and every one was started by hand. Nothing stops a
  session from saying "done" while the deck fails the gate. This hook closes
  that at layer 2 of charter section 0 ("block it at the generation step"):
  when a session touched an episode folder, its verify.py runs before the
  session is allowed to stop, and a FAIL blocks the stop once.

WHAT IT DOES
  stdin  : Stop hook JSON  {transcript_path, stop_hook_active, session_id}
  1. scan the transcript (only lines after the last checked one, state file
     under logs\gate_on_stop\<session_id>.json) for tool_use blocks that
     mention  workshop\02_제작중\<ep...>  (Edit/Write/Bash alike - the path
     string is what is matched, not the tool)
  2. keep only folders with a file newer than the previous Stop checkpoint,
     or the first transcript timestamp on the first Stop (newest_mtime is
     shared with --codex). A path in a report/script is only a candidate.
     For each changed folder that has a verify.py: run `py verify.py` there,
     read the last ^STATUS: line
  3. all OK        -> exit 0, systemMessage "게이트 OK ..."
     any FAIL      -> decision:block with the tail of the gate output, so the
                      model must fix and report. Only once: when
                      stop_hook_active is true we never block again (loop guard)
     nothing touched -> exit 0, silent

WHAT IT CANNOT CATCH (charter section 0, layer 4 - written down on purpose)
  - sessions whose CWD is another project (hook is registered per project)
  - edits made by a script whose command text does not contain the folder
    path (e.g. `cd <ep>` in one call and `py patch.py` in the next), or that
    reaches it through a shell variable (`$W/ep44...` - measured 7 times in
    the 2026-09-05 session against 44 literal mentions)
  - a folder without verify.py (reel folders): reported as "게이트 없음",
    never blocked - there is nothing to run
  - a verify.py that itself lies. The gate is trusted as-is.
  - mtime is not a content diff or writer identity: preserved/restored mtimes,
    deletion-only changes, and writes at/before the timestamp resolution
    boundary can be missed. A concurrent writer can make a mentioned folder
    look changed by this session. Writes during verification can be consumed
    by the post-gate checkpoint. Cache files are deliberately excluded.
  - missing/invalid transcript timestamps cannot establish the first baseline:
    report "cannot measure" without blocking. A truncated/resumed transcript
    or legacy line-only state cannot reconstruct a lost Stop checkpoint.
  - 🔴 registration: the model may not edit .claude\settings.json (auto-mode
    classifier, 2026-09-05). JJ applies docs\hooks\gate-on-stop-settings.patch;
    `--check` says whether it happened.

SELF-TEST (charter section 0: a detector must be proven to hold a value)
  py gate_on_stop.py --self-test   -> original 13 axes + Claude mtime cases,
                                    exit 1 on any miss
  py gate_on_stop.py --check       -> hook registered in .claude\settings.json
                                      and this file exists
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

PAT = re.compile(r"02_제작중[\\/]+(ep[0-9]+[^\\/\"'\s,]*)")  # 02_제작중\epNN...
TAIL_LINES = 14
GATE_TIMEOUT = 240

# 코덱스 모드(--codex)에서만 쓴다. 하드코딩하면 그 줄이 또 사본이 되므로 환경변수로 덮는다
# (편 verify.py 의 EPCHECK_DIR 과 같은 꼴).
WORKSHOP = os.environ.get(
    "WORKSHOP_DIR",
    os.path.join(os.path.expanduser("~"), "orca", "tomangchi-lab.github.io", "workshop"))
SKIP_DIRS = ("__pycache__", ".git")  # 게이트 자신이 남기는 것을 «건드렸다»로 읽지 않는다


def _out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=True))
    sys.stdout.flush()


def _state_path(session_id):
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    d = os.path.join(root, "logs", "gate_on_stop")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "%s.json" % re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession"))


def touched_eps(transcript_path, start_line=0):
    """Return ({ep_folder_abs: name}, lines_read). Only tool_use blocks count."""
    eps = {}
    n = 0
    if not transcript_path or not os.path.exists(transcript_path):
        return eps, 0
    with io.open(transcript_path, "r", encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            if n <= start_line or '"tool_use"' not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            content = ((obj.get("message") or {}).get("content")) or []
            if not isinstance(content, list):
                continue
            for blk in content:
                if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                    continue
                s = json.dumps(blk.get("input", {}), ensure_ascii=False)
                for m in PAT.finditer(s):
                    # rebuild the absolute folder from the matched string's prefix
                    pre = s[: m.start()]
                    # walk back to the start of the path token (quote or whitespace)
                    k = max(pre.rfind('"'), pre.rfind("'"), pre.rfind(" "), pre.rfind("\t")) + 1
                    path = s[k : m.end()].replace("\\\\", "\\")
                    path = path.replace("/", os.sep).replace("\\", os.sep)
                    if os.path.isdir(path):
                        eps[os.path.normcase(os.path.abspath(path))] = m.group(1)
    return eps, n


def run_gate(folder):
    vp = os.path.join(folder, "verify.py")
    if not os.path.exists(vp):
        return "NOVERIFY", "verify.py not found"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run([sys.executable, "verify.py"], cwd=folder, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, timeout=GATE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "FAIL", "gate timeout %ss" % GATE_TIMEOUT
    text = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
    status = "FAIL"
    for ln in reversed(text.splitlines()):
        if ln.startswith("STATUS:"):
            status = "OK" if ln.strip() == "STATUS: OK" else "FAIL"
            break
    tail = "\n".join(text.strip().splitlines()[-TAIL_LINES:])
    return status, tail


def transcript_started_at(transcript_path):
    """First timestamp-bearing JSONL record, in epoch seconds (not file mtime).

    Claude records use a top-level ISO timestamp, also read by context_watch.
    Metadata without one is skipped; a conversation record with a missing or
    malformed timestamp is not replaced with a later one, which could hide
    an earlier real write.
    """
    with io.open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            if "timestamp" not in obj:
                if obj.get("type") in ("user", "assistant"):
                    raise ValueError("transcript timestamp missing")
                continue
            try:
                stamp = datetime.fromisoformat(obj["timestamp"].replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError("timezone missing")
                since = stamp.timestamp()
                if not 0 < since <= time.time():
                    raise ValueError("timestamp outside elapsed session")
                return since
            except (AttributeError, TypeError, ValueError, OverflowError) as exc:
                raise ValueError("invalid transcript timestamp: %s" % exc) from exc
    raise ValueError("transcript timestamp missing")


def newest_mtime(folder):
    """이 폴더에서 가장 최근에 바뀐 파일의 시각. 없으면 0."""
    newest = 0.0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith(".pyc"):
                continue
            try:
                m = os.path.getmtime(os.path.join(root, fn))
            except OSError:
                continue
            if m > newest:
                newest = m
    return newest


def touched_eps_since(workshop, since):
    """«이 세션이 건드린 편» 을 트랜스크립트가 아니라 mtime 으로 고른다.

    코덱스는 클로드의 트랜스크립트 JSONL 을 남기지 않는다. 그런데 게이트가 재려는 것은
    «무엇을 적었는가» 가 아니라 «어느 편이 바뀌었는가» 이므로, 파일 시각이 더 곧은 자다 —
    셸 변수 경로($W/ep44...)나 `cd` 뒤의 별도 호출처럼 클로드판이 놓치던 자리도 같이 잡힌다.
    """
    eps = {}
    base = os.path.join(workshop, "02_제작중")
    if not os.path.isdir(base):
        return eps
    for name in sorted(os.listdir(base)):
        folder = os.path.join(base, name)
        if not os.path.isdir(folder):
            continue
        if newest_mtime(folder) > since:
            eps[os.path.normcase(os.path.abspath(folder))] = name
    return eps


def main_codex(stamp_path):
    """코덱스 Stop 훅용. 리포트를 stdout 에 «글»로 내고 종료 코드로만 말한다.

    0 = 막을 것 없음 / 3 = 게이트 미통과. 코덱스가 요구하는 JSON 꼴은 래퍼(.codex\\hooks\\stop.ps1)가
    안다 — 그 지식을 한 곳에만 둔다(PreToolUse 에서 exit 2 가 무시되고 JSON deny + exit 0 이어야
    했던 것과 같은 자리).
    """
    if not stamp_path or not os.path.exists(stamp_path):
        # 조용히 통과시키지 않는다(§0). 잴 기준이 없었다는 사실 자체를 남긴다.
        print("gate-codex: 세션 스탬프가 없다(%s) — 아무것도 재지 못했다." % stamp_path)
        return 0
    since = os.path.getmtime(stamp_path)
    eps = touched_eps_since(WORKSHOP, since)
    if not eps:
        return 0
    results = {name: run_gate(folder) for folder, name in eps.items()}
    fails = {k: v for k, v in results.items() if v[0] == "FAIL"}
    oks = sorted(k for k, v in results.items() if v[0] == "OK")
    nogate = sorted(k for k, v in results.items() if v[0] == "NOVERIFY")
    head = []
    if oks:
        head.append("게이트 OK - " + ", ".join(oks))
    if nogate:
        head.append("게이트 없음(verify.py 없음, 못 잰다) - " + ", ".join(nogate))
    if not fails:
        if head:
            print("gate-codex: " + " / ".join(head))
        return 0
    body = "\n\n".join("[%s] %s\n%s" % (name, st, tail) for name, (st, tail) in sorted(fails.items()))
    if head:
        body = " / ".join(head) + "\n\n" + body
    print("gate-codex: 게이트 미통과. 고치고 verify.py 를 다시 돌린 뒤 결과를 보고하라.\n" + body)
    return 3


def main(payload):
    transcript = payload.get("transcript_path")
    active = bool(payload.get("stop_hook_active"))
    sid = payload.get("session_id", "")
    sp = _state_path(sid)
    start = 0
    state = {}
    if os.path.exists(sp):
        try:
            with io.open(sp, encoding="utf-8") as fh:
                state = json.load(fh)
            start = int(state.get("line", 0))
        except Exception:
            state = {}
            start = 0
    eps, last = touched_eps(transcript, start)
    if eps:
        try:
            # Old state files contain only `line`; use the session baseline
            # once, rather than treating a missing checkpoint as epoch zero.
            since = state.get("checked_at")
            if since is None:
                since = transcript_started_at(transcript)
            if isinstance(since, bool) or not isinstance(since, (int, float)) or not 0 < since <= time.time():
                raise ValueError("invalid Stop checkpoint")
        except (OSError, UnicodeError, ValueError) as exc:
            _out({"systemMessage": "gate-on-stop: 변경 시각 기준을 확인할 수 없어 못 쟀다: %s" % exc})
            return 0
        eps = {folder: name for folder, name in eps.items() if newest_mtime(folder) > since}
    results = {name: run_gate(folder) for folder, name in eps.items()}
    if last:
        # After gates: their own output must not turn a later report-only turn
        # into a fresh edit. This cannot attribute concurrent writes (see above).
        with io.open(sp, "w", encoding="utf-8") as fh:
            json.dump({"line": last, "checked_at": time.time()}, fh)
    if not eps:
        return 0
    fails = {k: v for k, v in results.items() if v[0] == "FAIL"}
    oks = sorted(k for k, v in results.items() if v[0] == "OK")
    nogate = sorted(k for k, v in results.items() if v[0] == "NOVERIFY")
    head = []
    if oks:
        head.append("게이트 OK - " + ", ".join(oks))
    if nogate:
        head.append("게이트 없음(verify.py 없음, 못 잰다) - " + ", ".join(nogate))
    if not fails:
        _out({"systemMessage": "gate-on-stop: " + " / ".join(head)})
        return 0
    msg = []
    for name, (st, tail) in sorted(fails.items()):
        msg.append("[%s] %s\n%s" % (name, st, tail))
    body = "\n\n".join(msg)
    if head:
        body = " / ".join(head) + "\n\n" + body
    if active:
        _out({"systemMessage": "gate-on-stop: 게이트 미통과 (재차단 안 함)\n" + body})
        return 0
    _out({"decision": "block",
          "reason": "gate-on-stop: 게이트 미통과. 고치고 verify.py 를 다시 돌린 뒤 결과를 보고하라. "
                    "이 차단은 한 번뿐이다.\n" + body})
    return 0


# ---------------------------------------------------------------- self-test
def _mk_ep(root, name, ok):
    ep = os.path.join(root, "workshop", "02_제작중", name)
    os.makedirs(ep, exist_ok=True)
    with io.open(os.path.join(ep, "verify.py"), "w", encoding="utf-8") as fh:
        fh.write("print('x')\nprint('STATUS: %s')\n" % ("OK" if ok else "FAIL selftest"))
    return ep


def _mk_transcript(root, paths):
    tp = os.path.join(root, "t.jsonl")
    with io.open(tp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "timestamp": "2000-01-01T00:00:00Z",
                             "message": {"content": "hi"}}) + "\n")
        for p in paths:
            blk = {"type": "tool_use", "name": "Edit", "input": {"file_path": os.path.join(p, "build_ep99.py")}}
            fh.write(json.dumps({"type": "assistant", "message": {"content": [blk]}}, ensure_ascii=False) + "\n")
    return tp


def _run_case(root, paths, active, sid):
    tp = _mk_transcript(root, paths)
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        main({"transcript_path": tp, "stop_hook_active": active, "session_id": sid})
    finally:
        sys.stdout = old
    s = buf.getvalue()
    return json.loads(s) if s.strip() else {}


def self_test():
    root = tempfile.mkdtemp(prefix="gate_on_stop_")
    os.environ["CLAUDE_PROJECT_DIR"] = root
    bad = _mk_ep(root, "ep98_bad", False)
    good = _mk_ep(root, "ep99_good", True)
    cases = []
    r = _run_case(root, [bad], False, "s1")
    cases.append(("FAIL blocks once", r.get("decision") == "block" and "ep98_bad" in r.get("reason", "")))
    r = _run_case(root, [good], False, "s2")
    cases.append(("OK does not block", "decision" not in r and "OK" in r.get("systemMessage", "")))
    r = _run_case(root, [bad], True, "s3")
    cases.append(("FAIL + stop_hook_active -> no second block", "decision" not in r and "systemMessage" in r))
    r = _run_case(root, [], False, "s4")
    cases.append(("nothing touched -> silent", r == {}))
    nog = os.path.join(root, "workshop", "02_제작중", "ep97_reel")
    os.makedirs(nog, exist_ok=True)
    with io.open(os.path.join(nog, "note.txt"), "w") as fh:
        fh.write("changed reel without a gate")
    r = _run_case(root, [nog], False, "s6")
    cases.append(("no verify.py -> report, never block", "decision" not in r and "ep97_reel" in r.get("systemMessage", "")))
    r = _run_case(root, [nog, bad], False, "s7")
    cases.append(("no verify.py + FAIL -> block names both", r.get("decision") == "block" and "ep97_reel" in r.get("reason", "") and "ep98_bad" in r.get("reason", "")))
    # state file: same transcript, second stop with no new lines -> silent
    _run_case(root, [bad], False, "s5")
    tp = os.path.join(root, "t.jsonl")
    buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
    try:
        main({"transcript_path": tp, "stop_hook_active": False, "session_id": "s5"})
    finally:
        sys.stdout = old
    cases.append(("no new transcript lines -> silent (state file)", buf.getvalue().strip() == ""))
    cases += _codex_cases()
    cases += _claude_mtime_cases()
    ok = all(v for _, v in cases)
    for name, v in cases:
        print(("PASS " if v else "FAIL ") + name)
    print("STATUS: " + ("OK" if ok else "FAIL selftest"))
    return 0 if ok else 1


# ------------------------------------------------- self-test (codex mode)
def _touch(path, when):
    os.utime(path, (when, when))


def _codex_run(stamp):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main_codex(stamp)
    finally:
        sys.stdout = old
    return code, buf.getvalue()


def _codex_cases():
    """축마다 폴더를 따로 둔다 — 한 폴더로 겹치면 «그 축이 없었어도 잡혔을 입력» 이 된다(§0)."""
    root = tempfile.mkdtemp(prefix="gate_codex_")
    globals()["WORKSHOP"] = root
    base = os.path.join(root, "02_제작중")
    stamp = os.path.join(root, "s.stamp")
    io.open(stamp, "w").write("x")
    t0 = os.path.getmtime(stamp)

    def ep(name, ok=True, verify=True, mtime=t0 + 10):
        d = os.path.join(base, name)
        os.makedirs(d, exist_ok=True)
        if verify:
            p = os.path.join(d, "verify.py")
            with io.open(p, "w", encoding="utf-8") as fh:
                fh.write("print('STATUS: %s')\n" % ("OK" if ok else "FAIL selftest"))
            _touch(p, mtime)
        else:
            p = os.path.join(d, "note.txt")
            io.open(p, "w").write("x")
            _touch(p, mtime)
        return d

    out = []

    # 1. 바뀐 편이 FAIL 이면 막는다
    ep("ep91_fail", ok=False)
    c, s = _codex_run(stamp)
    out.append(("codex: 바뀐 편 FAIL -> 차단", c == 3 and "ep91_fail" in s))
    shutil.rmtree(base)

    # 2. 바뀐 편이 OK 면 안 막는다 (전부 막는 게이트가 아님을 증명)
    ep("ep92_ok", ok=True)
    c, s = _codex_run(stamp)
    out.append(("codex: 바뀐 편 OK -> 통과", c == 0 and "ep92_ok" in s))
    shutil.rmtree(base)

    # 3. 스탬프보다 «오래된» FAIL 편은 재지 않는다 — mtime 축이 실제로 거른다(헛돎 점검)
    ep("ep93_old_fail", ok=False, mtime=t0 - 60)
    c, s = _codex_run(stamp)
    out.append(("codex: 안 건드린 FAIL 편 -> 조용", c == 0 and s.strip() == ""))
    shutil.rmtree(base)

    # 4. __pycache__ 만 새것이면 «건드린 것» 이 아니다 (게이트가 자기 흔적에 스스로 걸리지 않는다)
    d = ep("ep94_cache_only", ok=False, mtime=t0 - 60)
    pc = os.path.join(d, "__pycache__")
    os.makedirs(pc, exist_ok=True)
    f = os.path.join(pc, "x.cpython-313.pyc")
    io.open(f, "w").write("x")
    _touch(f, t0 + 10)
    c, s = _codex_run(stamp)
    out.append(("codex: __pycache__ 만 새것 -> 조용", c == 0 and s.strip() == ""))
    shutil.rmtree(base)

    # 5. 스탬프가 없으면 조용히 통과하지 않고 «못 쟀다» 를 남긴다
    c, s = _codex_run(os.path.join(root, "nope.stamp"))
    out.append(("codex: 스탬프 없음 -> 통과하되 말한다", c == 0 and "스탬프" in s))

    # 6. verify.py 없는 폴더는 보고만 하고 절대 안 막는다
    ep("ep95_reel", verify=False)
    c, s = _codex_run(stamp)
    out.append(("codex: verify.py 없음 -> 보고만", c == 0 and "ep95_reel" in s))
    shutil.rmtree(base)
    return out


def _claude_mtime_cases():
    """Each case gets its own FAIL folder; only the named axis varies.

    Quiet cases still have NEW tool_use lines and a working FAIL verifier.
    Thus the existing cursor/OK/loop guards cannot hide a broken mtime filter.
    """
    out = []
    t0 = 1000000000.0

    def fixture(name, mtime=t0 - 60, kind="report", timestamp="2001-09-09T01:46:40Z"):
        root = tempfile.mkdtemp(prefix="gate_claude_" + name + "_")
        os.environ["CLAUDE_PROJECT_DIR"] = root
        ep = _mk_ep(root, "ep96_" + name, False)
        _touch(os.path.join(ep, "verify.py"), mtime)
        tp = os.path.join(root, "t.jsonl")
        record = {"type": "user", "message": {"content": "start"}}
        if timestamp is not None:
            record["timestamp"] = timestamp
        with io.open(tp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        append(tp, ep, kind)
        return root, ep, tp

    def append(tp, ep, kind="report"):
        path = os.path.join(ep, "build_ep96.py")
        if kind == "script":
            inp = {"command": "python -c \"path = " + repr(path) + "\""}
            tool = "Bash"
        elif kind == "edit":
            inp = {"file_path": path, "old_string": "before", "new_string": "after"}
            tool = "Edit"
        else:
            inp = {"file_path": "reports/result.md", "content": "Mentioned episode: " + path}
            tool = "Write"
        # Later than t0+10: comparing file mtime to this tool timestamp would
        # miss the earlier-in-session edit (the session timestamp must win).
        record = {"type": "assistant", "timestamp": "2001-09-09T01:47:10Z",
                  "message": {"content": [{"type": "tool_use", "name": tool, "input": inp}]}}
        with io.open(tp, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run(tp):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            main({"transcript_path": tp, "session_id": "mtime", "stop_hook_active": False})
        finally:
            sys.stdout = old
        return json.loads(buf.getvalue()) if buf.getvalue() else {}

    for kind in ("report", "script"):
        _, ep, tp = fixture(kind + "_old", kind=kind)
        out.append(("claude: %s path only + old FAIL -> silent" % kind, run(tp) == {}))
        _, ep, tp = fixture(kind + "_changed", mtime=t0 + 10, kind=kind)
        out.append(("claude: %s path + earlier session edit FAIL -> block" % kind,
                    run(tp).get("decision") == "block"))

    _, ep, tp = fixture("equal_boundary", mtime=t0, kind="edit")
    out.append(("claude: file mtime equals baseline -> silent", run(tp) == {}))

    _, ep, tp = fixture("nested_change", kind="edit")
    nested = os.path.join(ep, "assets")
    os.makedirs(nested)
    source = os.path.join(nested, "source.txt")
    with io.open(source, "w") as fh:
        fh.write("changed nested source")
    _touch(source, t0 + 10)
    out.append(("claude: nested source changed, verifier old -> block", run(tp).get("decision") == "block"))

    # Independent cache exclusions: each contains only one otherwise-new file.
    for label, relative in (("cache directory", ("__pycache__", "note.txt")),
                            ("git directory", (".git", "index")),
                            ("pyc extension", ("loose.pyc",))):
        _, ep, tp = fixture(label.replace(" ", "_"), kind="edit")
        source = os.path.join(ep, *relative)
        os.makedirs(os.path.dirname(source), exist_ok=True)
        with io.open(source, "w") as fh:
            fh.write("ignored artifact")
        _touch(source, t0 + 10)
        out.append(("claude: only %s changed -> silent" % label, run(tp) == {}))

    for changed in (False, True):
        root, ep, tp = fixture("checkpoint_" + str(changed), mtime=t0 + 10, kind="edit")
        # The gate itself writes an artifact. The post-gate checkpoint must
        # cover it, yet a genuine later source write must still be measured.
        with io.open(os.path.join(ep, "verify.py"), "a", encoding="utf-8") as fh:
            fh.write("from pathlib import Path\nPath('gate-result.txt').write_text('checked')\n")
        first = run(tp)
        append(tp, ep)
        if changed:
            with io.open(_state_path("mtime"), encoding="utf-8") as fh:
                checkpoint = json.load(fh)["checked_at"]
            _touch(os.path.join(ep, "verify.py"), checkpoint + 1)
        second = run(tp)
        expected = second.get("decision") == "block" if changed else second == {}
        out.append(("claude: new mention + %s -> %s" %
                    ("post-checkpoint edit" if changed else "only gate output", "block" if changed else "silent"),
                    first.get("decision") == "block" and expected))

    for label, stamp in (("missing", None), ("invalid", "not-a-timestamp"),
                         ("no timezone", "2001-09-09T01:46:40")):
        _, ep, tp = fixture("timestamp_" + label.replace(" ", "_"), mtime=t0 + 10, timestamp=stamp)
        r = run(tp)
        out.append(("claude: %s timestamp -> diagnostic, cursor not consumed" % label,
                    "decision" not in r and "못 쟀다" in r.get("systemMessage", "")
                    and not os.path.exists(_state_path("mtime"))))
    return out


def check():
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sp = os.path.join(root, ".claude", "settings.json")
    try:
        cfg = json.load(io.open(sp, encoding="utf-8-sig"))
    except Exception as e:
        print("FAIL settings.json unreadable: %s" % e); return 1
    hooks = (cfg.get("hooks") or {}).get("Stop") or []
    found = any("gate_on_stop.py" in h.get("command", "") for grp in hooks for h in grp.get("hooks", []))
    here = os.path.abspath(__file__)
    print(("PASS " if found else "FAIL ") + "Stop hook registered in .claude\\settings.json")
    print(("PASS " if os.path.exists(here) else "FAIL ") + "script exists: " + here)
    return 0 if found else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    if "--check" in sys.argv:
        raise SystemExit(check())
    if "--codex" in sys.argv:
        # 코덱스 Stop 훅. 페이로드는 래퍼가 로그에 남기고, 여기는 스탬프만 받는다.
        i = sys.argv.index("--stamp") + 1 if "--stamp" in sys.argv else 0
        raise SystemExit(main_codex(sys.argv[i] if i else ""))
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    raise SystemExit(main(payload))
