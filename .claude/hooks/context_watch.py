# -*- coding: utf-8 -*-
r"""JJ Company OS - context-watch (UserPromptSubmit + SessionStart hooks).

WHY (study notes, JJ 2026-09-06: "40% 넘으면 새 세션으로")
  Claude Code cannot open a new session by itself, and hooks get no token
  count. What a hook DOES get is transcript_path, and every assistant line in
  that JSONL carries message.usage (input + cache_read + cache_creation =
  the context the last call actually used - measured 2026-09-06: 519,818 of
  1,000,000 on this very session). So the number is there; nobody was reading it.

WHAT IT DOES
  py context_watch.py prompt   (UserPromptSubmit)
      read the tail of the transcript, compute pct = last usage / window.
      pct >= threshold -> print additionalContext telling the model to write a
      handoff memo at the END of this turn and tell the user to open a new
      session. Repeats every NAG_EVERY prompts while still above, not every
      prompt (state file logs\context_watch\<session_id>.json).
  py context_watch.py start    (SessionStart)
      newest unconsumed reports\handoff\*.md (<= 48h old) -> print it as the
      session's first context, mark it consumed (rename to *.consumed.md).
      ALSO scripts\session_brief.py: unread RED (open intents, failed runs of
      the last two days). 2026-09-12: run_audit shipped RUNS_VERDICT=RED three
      days running and four intent drafts piled up unread - the reports existed,
      the reading seat did not. This hook is the seat every session passes.
      It rides on THIS hook because SessionStart is already registered: a new
      entry would need settings.json, which is a human seat (see below).
  py context_watch.py --self-test   7 cases      py context_watch.py --check

WHAT IT CANNOT DO (charter section 0, layer 4)
  - open the new session. That is one human keystroke and stays so.
  - know the window size for sure: JJ_CONTEXT_WINDOW (default 1,000,000).
    A 200k model reads as 5x too optimistic - set the env var in that case.
  - see the very latest call: the number is from the LAST assistant message,
    i.e. one turn behind. Threshold 40% leaves room for that.
  - registration: the model may not edit settings.json (classifier, 2026-09-05).
    JJ applies docs\hooks\context-watch-settings.patch; `--check` verifies.
"""
import glob
import io
import json
import os
import re
import sys
import time

HQ = os.environ.get("JJ_HQ", r"C:\Users\ojaej\jj-company")
HANDOFF_DIR = os.path.join(HQ, "reports", "handoff")
STATE_DIR = os.path.join(HQ, "logs", "context_watch")
WINDOW = int(os.environ.get("JJ_CONTEXT_WINDOW", "1000000"))
THRESHOLD = float(os.environ.get("JJ_CONTEXT_HANDOFF_PCT", "40"))
NAG_EVERY = 8
TAIL_BYTES = 600000
MAX_AGE_H = 48


def _out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def last_usage(transcript_path, tail_bytes=TAIL_BYTES):
    """(tokens, iso_ts) of the last assistant message that carries usage; (None, None) if none."""
    try:
        size = os.path.getsize(transcript_path)
        with io.open(transcript_path, "rb") as f:
            f.seek(max(0, size - tail_bytes))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None, None
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        u = (d.get("message") or {}).get("usage") or {}
        if "input_tokens" in u:
            tok = int(u.get("input_tokens", 0)) + int(u.get("cache_read_input_tokens", 0)) + int(u.get("cache_creation_input_tokens", 0))
            return tok, d.get("timestamp")
    return None, None


def _state(sid):
    p = os.path.join(STATE_DIR, re.sub(r"[^\w.-]", "_", sid or "nosession") + ".json")
    try:
        return p, json.loads(io.open(p, encoding="utf-8").read())
    except (OSError, ValueError):
        return p, {"prompts": 0, "last_nag": -100}


def prompt(payload):
    tok, ts = last_usage(payload.get("transcript_path") or "")
    if tok is None:
        return None                      # first prompt of a session, or unreadable - silent
    pct = 100.0 * tok / WINDOW
    p, st = _state(payload.get("session_id"))
    st["prompts"] = st.get("prompts", 0) + 1
    st["pct"] = round(pct, 1)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8").write(json.dumps(st))
    if pct < THRESHOLD or st["prompts"] - st.get("last_nag", -100) < NAG_EVERY:
        return None
    st["last_nag"] = st["prompts"]
    io.open(p, "w", encoding="utf-8").write(json.dumps(st))
    memo = os.path.join(HANDOFF_DIR, "%s_%s.md" % (time.strftime("%Y-%m-%d_%H%M"), (payload.get("session_id") or "session")[:8]))
    msg = (
        "[context-watch] 컨텍스트 사용 %.0f%% (%s 토큰 / %s · 문턱 %.0f%%). 공부 노트 원칙: 쌓인 채로 이어가지 않는다.\n"
        "이 턴의 작업을 끝낸 뒤 마지막에 두 가지를 한다.\n"
        "1. 인계 메모를 `%s` 에 쓴다 (UTF-8). 내용: ① 지금 목표 한 줄 ② 끝난 것 / 남은 것 ③ JJ 판정·지시 원문(따옴표) "
        "④ 열린 PR·worktree·claim ⑤ 다음 세션이 첫 행동으로 할 것 한 줄 ⑥ 못 잡는 것. 파일 경로·커밋 해시는 글자 그대로.\n"
        "2. 사용자에게 «컨텍스트 %.0f%% — 새 세션을 열어 주세요. 인계 메모는 새 세션이 자동으로 읽습니다» 라고 한 줄 알린다.\n"
        "새 세션을 여는 것은 사람 자리다. 이 지시는 %d 프롬프트마다 한 번만 온다."
    ) % (pct, "{:,}".format(tok), "{:,}".format(WINDOW), THRESHOLD, memo, pct, NAG_EVERY)
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}}


def newest_handoff(now=None):
    now = now or time.time()
    cands = [f for f in glob.glob(os.path.join(HANDOFF_DIR, "*.md")) if not f.endswith(".consumed.md")]
    cands = [f for f in cands if now - os.path.getmtime(f) <= MAX_AGE_H * 3600]
    return max(cands, key=os.path.getmtime) if cands else None


def _load_brief():
    d = os.path.join(HQ, "scripts")
    if d not in sys.path:
        sys.path.insert(0, d)
    import session_brief
    return session_brief


def ops_brief(load=None):
    r"""scripts\session_brief.py 의 🔴 브리핑. 깨끗하면 빈 문자열.

    실패를 삼키지 않는다 — 조회가 죽으면 그 사실을 한 줄로 띄운다. 조용히 빈 문자열을
    돌려주면 «읽을 것이 없다»와 «읽지 못했다»가 같아 보인다(정관 §0). `load` 는
    역검증이 «죽는 조회»를 넣는 자리다 — 예외 처리를 두 벌 두지 않으려고 뚫었다.
    """
    try:
        return (load or _load_brief)().brief()
    except Exception as e:                      # noqa: BLE001
        return ("[session-brief] 🔴 조회 실패: %s: %s — `py %s` 를 손으로 돌려 본다"
                % (type(e).__name__, e, os.path.join(HQ, "scripts", "session_brief.py")))


def start(payload, brief_fn=None):
    parts = []
    f = newest_handoff()
    if f:
        body = io.open(f, encoding="utf-8").read().strip()
        dst = f[:-3] + ".consumed.md"
        os.replace(f, dst)
        parts.append("[context-watch] 이전 세션 인계 메모 (%s · 읽은 뒤 %s 로 이름을 바꿨다):\n\n%s"
                     % (os.path.basename(f), os.path.basename(dst), body))
    parts.append((brief_fn or ops_brief)())
    ctx = "\n\n".join(p for p in parts if p)
    if not ctx:
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}


# ---------------------------------------------------------------- self-test / check
def _fake_transcript(root, tokens):
    p = os.path.join(root, "t.jsonl")
    lines = ['{"type":"user","message":{"content":"hi"}}']
    if tokens is not None:
        lines.append(json.dumps({"type": "assistant", "timestamp": "2026-09-06T00:00:00Z",
                                 "message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": tokens - 20, "cache_creation_input_tokens": 10}}}))
        lines.append('{"type":"user","message":{"content":"next"}}')
    io.open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return p


def self_test():
    global HANDOFF_DIR, STATE_DIR
    import tempfile
    root = tempfile.mkdtemp(prefix="ctxwatch_")
    HANDOFF_DIR = os.path.join(root, "handoff"); STATE_DIR = os.path.join(root, "state")
    os.makedirs(HANDOFF_DIR)
    res = []
    # 1 below threshold -> silent
    t = _fake_transcript(root, int(WINDOW * 0.30))
    res.append(("30% 는 조용", prompt({"transcript_path": t, "session_id": "s1"}) is None))
    # 2 above threshold -> nag with memo path
    t = _fake_transcript(root, int(WINDOW * 0.45))
    r = prompt({"transcript_path": t, "session_id": "s2"})
    res.append(("45% 는 인계 지시", bool(r) and "인계 메모" in r["hookSpecificOutput"]["additionalContext"] and "45%" in r["hookSpecificOutput"]["additionalContext"]))
    # 3 same session, next prompt -> silent (nag throttle)
    res.append(("연속 프롬프트엔 안 되풀이", prompt({"transcript_path": t, "session_id": "s2"}) is None))
    # 4 no usage yet -> silent, no crash
    t0 = _fake_transcript(root, None)
    res.append(("usage 없는 첫 프롬프트는 조용", prompt({"transcript_path": t0, "session_id": "s3"}) is None))
    # 5 start with no memo -> None
    #
    # 브리핑은 `brief_fn` 으로 꺼 둔다 — 이 케이스가 재는 것은 «인계 메모» 축이고,
    # 실기계의 🔴 가 섞이면 무엇이 띄웠는지 증명되지 않는다(§0 «케이스는 분리한다»).
    def _quiet():
        return ""
    res.append(("인계 메모 없으면 시작 훅 조용", start({}, _quiet) is None))
    # 6 start with memo -> injected + consumed
    m = os.path.join(HANDOFF_DIR, "2026-09-06_0100_abc.md")
    io.open(m, "w", encoding="utf-8").write("# 인계\n- 목표: X\n")
    r = start({}, _quiet)
    res.append(("인계 메모 주입 + consumed 개명", bool(r) and "- 목표: X" in r["hookSpecificOutput"]["additionalContext"] and not os.path.exists(m) and os.path.exists(m[:-3] + ".consumed.md")))
    # 7 stale memo (> 48h) ignored
    m2 = os.path.join(HANDOFF_DIR, "old.md"); io.open(m2, "w", encoding="utf-8").write("old")
    os.utime(m2, (time.time() - 3 * 86400, time.time() - 3 * 86400))
    res.append(("48시간 지난 메모는 무시", start({}, _quiet) is None))
    # 8 브리핑만 있어도 시작 훅이 뜬다 (인계 메모 0건 · 🔴 만)
    r = start({}, lambda: "[session-brief] 🔴 미처리 intent 1건")
    res.append(("브리핑만 있어도 띄운다",
                bool(r) and "미처리 intent" in r["hookSpecificOutput"]["additionalContext"]))
    # 9 브리핑 조회가 죽어도 훅은 살고, **죽었다는 사실이 보인다** (조용한 실패 금지)
    def _boom():
        raise RuntimeError("boom")
    r = start({}, lambda: ops_brief(load=_boom))
    res.append(("브리핑 조회 실패를 숨기지 않는다",
                bool(r) and "조회 실패" in r["hookSpecificOutput"]["additionalContext"]))
    fails = 0
    for name, ok in res:
        fails += not ok
        print(("ok   " if ok else "FAIL ") + name)
    print("STATUS: %s" % ("OK" if not fails else "FAIL %d" % fails))
    return 1 if fails else 0


def check():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")
    try:
        s = io.open(p, encoding="utf-8").read()
    except OSError:
        print("settings.json 없음: %s" % p); return 1
    ok = all(k in s for k in ("context_watch.py", '"UserPromptSubmit"', '"SessionStart"'))
    print("registered=%s (%s)" % (ok, p))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    if "--check" in sys.argv:
        raise SystemExit(check())
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    try:
        r = prompt(payload) if mode == "prompt" else start(payload) if mode == "start" else None
    except Exception as e:          # a hook that crashes blocks nothing but hides the failure - say it
        r = {"systemMessage": "[context-watch] 오류: %s" % e}
    if r:
        _out(r)
    raise SystemExit(0)
