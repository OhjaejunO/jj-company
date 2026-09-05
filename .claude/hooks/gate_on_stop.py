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
  2. for each such folder that has a verify.py: run `py verify.py` there,
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
  - 🔴 registration: the model may not edit .claude\settings.json (auto-mode
    classifier, 2026-09-05). JJ applies docs\hooks\gate-on-stop-settings.patch;
    `--check` says whether it happened.

SELF-TEST (charter section 0: a detector must be proven to hold a value)
  py gate_on_stop.py --self-test   -> 5 cases, exit 1 on any miss
  py gate_on_stop.py --check       -> hook registered in .claude\settings.json
                                      and this file exists
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile

PAT = re.compile(r"02_제작중[\\/]+(ep[0-9]+[^\\/\"'\s,]*)")  # 02_제작중\epNN...
TAIL_LINES = 14
GATE_TIMEOUT = 240


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


def main(payload):
    transcript = payload.get("transcript_path")
    active = bool(payload.get("stop_hook_active"))
    sid = payload.get("session_id", "")
    sp = _state_path(sid)
    start = 0
    if os.path.exists(sp):
        try:
            start = int(json.load(io.open(sp, encoding="utf-8")).get("line", 0))
        except Exception:
            start = 0
    eps, last = touched_eps(transcript, start)
    if last:
        json.dump({"line": last}, io.open(sp, "w", encoding="utf-8"))
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
        fh.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
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
    ok = all(v for _, v in cases)
    for name, v in cases:
        print(("PASS " if v else "FAIL ") + name)
    print("STATUS: " + ("OK" if ok else "FAIL selftest"))
    return 0 if ok else 1


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
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    raise SystemExit(main(payload))
