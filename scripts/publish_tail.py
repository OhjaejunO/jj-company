# -*- coding: utf-8 -*-
r"""publish_tail.py — 편이 인스타에 올라간 뒤의 꼬리를 그래프로 돈다.

    detect ──► record ──► move ──► backup ──► END
    (API 감지)  (발행로그 행)  (해시 검증 이동)  (workshop-backup)

정관 §2 예외 5(행 추가 · 본 표 끝에만) · 6(이동 · 해시 전후 동일 · «발행» 행 선재) · 3(백업 push) 을
**순서로 못박은 것**이다 — 4층의 ①(구조). 종전에는 세션이 셋을 손으로 차례로 불렀다(ep43·ep44).

- `detect` 는 `ig_watch` 로 우리 계정 게시물을 읽어 **캡션 첫 줄이 편 폴더 `caption.txt` 첫 줄과 같은** 게시물을 찾는다.
  없으면 `Wait` — 아직 안 올라간 것이다. 둘 이상이면 FAIL(애매함은 사람 자리).
- `record` 는 발행로그 **본 표의 마지막 행 뒤**에 한 행을 붙인다. 값은 API timestamp(KST 환산)·permalink.
  이미 그 편의 «발행» 행이 있으면 건너뛴다(재실행 안전).
- `move` 는 `02_제작중\<ep>` → `01_발행완료\<ep>`. 전후 파일 해시 전수 대조, 다르면 되돌리고 FAIL.
- `backup` 은 `scripts\workshop-backup.ps1 publish` 를 부르고 종료코드 0 이어야 한다(래퍼는 STATUS 를 자기 로그에 쓴다).

    py scripts\publish_tail.py --ep ep45_주간2호          # 돈다 / 안 올라갔으면 STATUS: WAIT
    py scripts\publish_tail.py --ep ep45_주간2호 --detect  # 감지만 (쓰기 없음)
    py scripts\publish_tail.py --dump                     # 그래프를 찍는다 — 문서 표 대신 이것
    py scripts\publish_tail.py --self-test

🔴 못 잡는 것: 캡션 첫 줄이 편과 다르게 올라갔으면(JJ 가 손으로 고쳐 올린 경우) 감지가 못 찾고 WAIT 에 머문다 —
그때는 `--shortcode <code>` 로 사람이 값을 준다(§2 예외 5 종전 경로).
"""
import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import graph_runner as gr  # noqa: E402
import ig_watch  # noqa: E402
import publog_check  # noqa: E402
import publish_threads  # noqa: E402

ROOT = HERE.parent
#: 🔴 영수증은 **운영 서버**에 쌓인다 — 워커(`publish_threads`)가 쓰는 그 자리를 그대로 쓴다.
#:    `ROOT/logs` 로 잡으면 워크트리에서 «0편» 이 조용히 나온다(`logs\` 는 gitignore).
#:    「적을 것이 없다」와 「볼 곳을 잘못 봤다」가 구별되지 않는 꼴이라 상수를 빌려 온다.
RECEIPTS = Path(publish_threads.RECEIPT_DIR)
WORKSHOP = Path(os.environ.get("TOMANGCHI_WORKSHOP", r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop"))
PUBLOG = Path(os.environ.get("TOMANGCHI_PUBLOG", str(WORKSHOP / "발행로그.md")))
KST = dt.timezone(dt.timedelta(hours=9))
BACKUP_PS1 = HERE / "workshop-backup.ps1"


# ---------------------------------------------------------------- 도우미
def first_line(p):
    return p.read_text("utf-8").split("\n")[0].strip()


def read_decl(build, name):
    """`NAME = 값` 선언을 읽는다. 없으면 None — 조용히 넘기지 않고 호출한 쪽이 «없음»으로 적는다.

    값이 `{`·`[`·`(` 로 열리고 그 줄에서 안 닫히면 **닫힐 때까지 다음 줄을 잇는다.** 종전엔 첫 줄만 잘라
    ep49 킷 칸에 `{"file": "08_kit.mp4",` 가 그대로 적혔다(2026-09-07 실측). 딕셔너리면 `html` → `file` 순으로 값 하나를 돌려준다.
    """
    lines = build.read_text("utf-8").split("\n")
    for i, ln in enumerate(lines):
        m = re.match(rf"^{name}\s*=\s*(.+)$", ln)
        if not m:
            continue
        val = m.group(1)
        opens, closes = "{[(", "}])"
        depth = lambda s: sum(s.count(o) for o in opens) - sum(s.count(c) for c in closes)  # noqa: E731
        j = i
        while depth(val) > 0 and j + 1 < len(lines):
            j += 1
            val += "\n" + lines[j]
        if val.lstrip()[:1] in opens:
            try:
                import ast
                lit = ast.literal_eval(val)
            except (ValueError, SyntaxError):
                # 주석·계산식이 섞이면 literal_eval 이 죽는다 — 주석을 떼고 한 번 더
                stripped = "\n".join(re.sub(r"\s+#.*$", "", l) for l in val.split("\n"))
                try:
                    lit = ast.literal_eval(stripped)
                except (ValueError, SyntaxError):
                    return None
            if isinstance(lit, dict):
                v = lit.get("html") or lit.get("file")
                return f'"{v}"' if v else None
            return str(lit)
        return re.sub(r"\s+#.*$", "", val).strip()
    return None


def tree_hashes(folder):
    out = {}
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(folder))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def ep_rows(text, ep):
    return [ln for ln in publog_check.main_table(text).split("\n") if re.match(rf"\|\s*\**{re.escape(ep)}\**\s*\|", ln)]


def append_main_table_row(text, row):
    """본 표의 **마지막 행 뒤**에 붙인다(§2 예외 5 ④). 행은 줄바꿈을 품을 수 있어 «`|` 로 끝나는 마지막 줄» 뒤다."""
    lines = text.split("\n")
    table = publog_check.main_table(text).split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("| ep |") and "제목" in ln)
    seg = lines[start:start + len(table)]
    last = max(i for i, ln in enumerate(seg) if ln.rstrip().endswith("|"))
    lines.insert(start + last + 1, row)
    return "\n".join(lines)


# ---------------------------------------------------------------- 노드
def detect(s):
    ep_dir = WORKSHOP / "02_제작중" / s["ep"]
    if not ep_dir.is_dir():
        if (WORKSHOP / "01_발행완료" / s["ep"]).is_dir():
            ep_dir = WORKSHOP / "01_발행완료" / s["ep"]  # 이미 옮겨진 편 — 감지는 되게 둔다
        else:
            raise RuntimeError(f"편 폴더 없음: {ep_dir}")
    hook = first_line(ep_dir / "caption.txt")
    if s.get("shortcode"):  # 사람이 값을 준 경로
        media = [m for m in s["media"] if m["shortcode"] == s["shortcode"]]
    else:
        media = [m for m in s["media"] if (m.get("caption") or "").split("\n")[0].strip() == hook]
    if not media:
        raise gr.Wait(f"캡션 첫 줄 «{hook}» 인 게시물이 계정에 없다 — 아직 안 올라감")
    if len(media) > 1:
        raise RuntimeError(f"같은 첫 줄 게시물이 {len(media)}건 — 사람이 --shortcode 로 고른다")
    m = media[0]
    ts = dt.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")).astimezone(KST)
    n_cards = len([p for p in ep_dir.iterdir() if re.match(r"\d\d_.*\.(png|mp4)$", p.name)])
    m_type = {"CAROUSEL_ALBUM": "캐러셀", "VIDEO": "릴스", "IMAGE": "단장"}.get(m["media_type"], m["media_type"])
    # 릴스 단독 편은 build_ep*.py 가 없고 assemble_reel.py 가 선언을 든다 (2026-09-07 ep45 실측 — 없으면 킷이 «없음» 으로 잘못 적힌다)
    build = next(ep_dir.glob("build_ep*.py"), None) or next(ep_dir.glob("assemble_reel.py"), None)
    corner = (read_decl(build, "CORNER") or '"AI 소식"').strip('"\'') if build else "AI 소식"
    kit = read_decl(build, "KIT") if build else None
    return {"shortcode": m["shortcode"], "permalink": m["permalink"], "published_kst": ts.strftime("%Y-%m-%d %H:%M KST"),
            "title": f"[{corner}] {hook}", "cards": n_cards, "media_type": m_type,
            "kit": "없음" if kit in (None, "None") else kit.strip('"\'')}


def record(s):
    text = PUBLOG.read_text("utf-8")
    if any("발행" in r for r in ep_rows(text, s["ep"].split("_")[0])):
        return {"recorded": "already"}
    ep = s["ep"].split("_")[0]
    now = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    row = (f"| **{ep}** | {s['title']} | **발행** | **{s['published_kst']}** | — | {s['kit']} | "
           f"`01_발행완료/{s['ep']}` | **인스타 {s['media_type']} {s['cards']}장** · `{s['permalink']}` — "
           f"자동 기록(`publish_tail` · `ig_watch` 감지 · API timestamp 환산) | {now} |")
    new = append_main_table_row(text, row)
    # 쓰기 전에 검사(§0): 기존 행 전부 그대로 + 새 행이 본 표 안에 있는가
    before, after = publog_check.main_table(text), publog_check.main_table(new)
    assert after.count("\n") == before.count("\n") + 1 and before.split("\n") == [l for l in after.split("\n") if l != row], "기존 행이 바뀌었다"
    assert ep_rows(new, ep), "새 행이 본 표 밖에 붙었다"
    PUBLOG.write_text(new, "utf-8")
    return {"recorded": row}


# ---------------------------------------------------------------- 재유통 (Threads)
#
# 🔴 **왜 여기 붙는가 (2026-09-11).** Threads 재유통 13편 중 **8편이 발행로그에 없었다**
#    (ep45·47·49·50·51·52·54·55 · 마지막 `-Threads` 행이 ep43 · 9/4). 정관 §2 예외 5 는
#    행 추가를 «JJ 가 준 값» 또는 «`publish_tail` 이 API 에서 읽은 값» 으로만 여는데,
#    Threads 를 읽는 코드가 이 파일에 **없었다** — 그래서 아무도 못 적었다. 조문이 막은
#    것이 아니라 **도구가 그 문장을 따라오지 못한 것**이다.
#
# 🔴 **값의 정본은 영수증이 아니라 API 다.** 영수증은 «어느 media 가 나갔는가» 를 알고,
#    **시각과 permalink 는 Threads 에서 되읽는다**(§0 «실물을 조회할 수 있는 것은 실물이
#    정본»). 되읽지 못하면 **적지 않는다** — 추측한 값을 정본 표에 넣지 않는다.
#
# 인스타 꼬리 그래프에 노드로 넣지 않은 이유: 재유통은 인스타 발행과 **다른 회차**에
# 일어난다. 같은 회차에 묶으면 매번 «아직 안 나갔다» 로 서서 그래프가 안 끝난다.
def threads_posted(ep):
    """영수증에서 **실제로 나간** 포스트만 (seq, media_id) 로. `post.claim` 은 선점이라 뺀다."""
    import json
    p = RECEIPTS / ("%s.jsonl" % ep)
    if not p.exists():
        return []
    out = {}
    for ln in p.read_text("utf-8", errors="replace").split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            e = json.loads(ln)
        except ValueError:
            continue                      # 깨진 줄은 «없음» 과 구별해 세지 않는다
        if e.get("stage") == "post.receipt" and e.get("media_id"):
            out[e.get("seq")] = e["media_id"]
    return sorted(out.items())


def threads_media(media_id, token):
    """Threads media 단건 조회 — 읽기만 한다(A등급)."""
    import json
    import urllib.request
    url = ("https://graph.threads.net/v1.0/%s?fields=id,media_type,permalink,timestamp"
           % media_id)
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token)
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))


def redist(ep_no, token, dry=False):
    """`| **epNN-Threads** | …` 행 하나를 본 표 끝에 붙인다. 이미 있으면 건너뛴다."""
    text = PUBLOG.read_text("utf-8")
    key = "%s-Threads" % ep_no
    if any("발행" in r for r in ep_rows(text, key)):
        return {"ep": ep_no, "recorded": "already"}

    posted = threads_posted(ep_no)
    if not posted:
        return {"ep": ep_no, "recorded": "skip", "why": "영수증에 나간 포스트가 없다"}

    root = threads_media(posted[0][1], token)
    if not root.get("permalink") or not root.get("timestamp"):
        raise RuntimeError("%s P1 을 Threads 에서 못 읽었다 — 값을 추측해 적지 않는다" % ep_no)
    ts = dt.datetime.fromisoformat(root["timestamp"].replace("+0000", "+00:00")).astimezone(KST)

    # 위치·제목은 그 편의 **인스타 행**에서 가져온다 — 재유통은 «같은 편» 이라 새로 짓지 않는다.
    own = ep_rows(text, ep_no)
    if not own:
        raise RuntimeError("%s 의 인스타 행이 발행로그에 없다 — 원류 없이 재유통 행을 적지 않는다" % ep_no)
    cells = [c.strip() for c in own[0].strip().strip("|").split("|")]
    where = cells[6] if len(cells) > 6 else ""

    video = "· P1 공식 영상 첨부 " if root.get("media_type") == "VIDEO" else ""
    now = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    # 🔴 킷 칸에 «위와 같음» 을 쓰지 않는다 — 행은 **본 표 끝에만** 붙으므로(§2 예외 5 ④)
    #    바로 위가 그 편의 인스타 행이라는 보장이 없다. 종전 다섯 행이 그 꼴이고
    #    ep41-Threads 는 실제로 ep42 바로 아래에 앉아 남의 킷을 가리키고 있다.
    row = ("| **%s** | 같은 편 · Threads 텍스트 체인 (재유통) | **발행** | **%s** | — | %s 본행과 같음 | %s | "
           "**%d포스트 체인** %s· 루트 `%s` · 워커 자동 발행 · 영수증 `logs\\publish-receipts\\%s.jsonl` "
           "— 자동 기록(`publish_tail --redist` · Threads API timestamp 환산) | %s |"
           % (key, ts.strftime("%Y-%m-%d %H:%M KST"), ep_no, where, len(posted), video,
              root["permalink"], ep_no, now))
    if dry:
        return {"ep": ep_no, "recorded": "dryrun", "row": row}

    new = append_main_table_row(text, row)
    before, after = publog_check.main_table(text), publog_check.main_table(new)
    assert after.count("\n") == before.count("\n") + 1 and before.split("\n") == [l for l in after.split("\n") if l != row], "기존 행이 바뀌었다"
    assert ep_rows(new, key), "새 행이 본 표 밖에 붙었다"
    PUBLOG.write_text(new, "utf-8")
    return {"ep": ep_no, "recorded": row}


def move(s):
    src, dst = WORKSHOP / "02_제작중" / s["ep"], WORKSHOP / "01_발행완료" / s["ep"]
    if not src.exists() and dst.exists():
        return {"moved": "already"}
    ep = s["ep"].split("_")[0]
    if not any("발행" in r for r in ep_rows(PUBLOG.read_text("utf-8"), ep)):
        raise RuntimeError("발행로그에 «발행» 행이 없다 — §2 예외 6 은 행 선재가 조건")
    if dst.exists():
        raise RuntimeError(f"대상이 이미 있다: {dst}")
    before = tree_hashes(src)
    shutil.move(str(src), str(dst))
    after = tree_hashes(dst)
    if before != after:
        shutil.move(str(dst), str(src))
        raise RuntimeError(f"이동 전후 해시 불일치({len(before)}→{len(after)} 파일) — 되돌렸다")
    return {"moved": str(dst), "files": len(after)}


def backup(s):
    if s.get("_no_backup"):  # self-test
        return {"backup": "skipped(test)"}
    # 래퍼는 첫 위치 인자를 Reason 으로 읽고(`$args[0]`), STATUS 는 stdout 이 아니라 자기 로그 파일에만 쓴다 —
    # 판정은 종료코드, 사유는 로그 꼬리에서 가져온다.
    r = subprocess.run(["powershell", "-NoProfile", "-File", str(BACKUP_PS1), "publish"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    logs = sorted((ROOT / "logs" / "scheduled").glob("workshop-backup_*.log"))
    tail = [l for l in logs[-1].read_text("utf-8", errors="replace").splitlines() if "STATUS:" in l][-1:] if logs else []
    if r.returncode != 0:
        raise RuntimeError(f"workshop-backup exit {r.returncode}: {tail[0] if tail else r.stdout[-300:]}")
    return {"backup": tail[0].split("] ", 1)[-1] if tail else "exit 0"}


GRAPH = {
    "start": "detect",
    "nodes": {"detect": detect, "record": record, "move": move, "backup": backup},
    "edges": {"detect": [(None, "record")], "record": [(None, "move")], "move": [(None, "backup")], "backup": [(None, "END")]},
}


# ---------------------------------------------------------------- 진입
def main(argv):
    if "--self-test" in argv:
        return _self_test()
    if "--dump" in argv:
        print(gr.dump(GRAPH))
        return 0

    # --redist: Threads 재유통 행. 인스타 꼬리와 다른 회차에 도는 별개 진입점이다.
    #   --redist --ep ep45      한 편
    #   --redist --all          영수증이 있는 편 전부 (이미 적힌 편은 건너뛴다)
    #   --dry 를 붙이면 행만 찍고 쓰지 않는다.
    if "--redist" in argv:
        import publish_threads
        token = publish_threads.load_token()
        dry = "--dry" in argv
        if "--all" in argv:
            eps = sorted({p.stem for p in RECEIPTS.glob("ep*.jsonl")
                          if re.fullmatch(r"ep\d+", p.stem)},
                         key=lambda e: int(e[2:]))
        else:
            eps = [argv[argv.index("--ep") + 1].split("_")[0]]
        wrote = 0
        for e in eps:
            try:
                r = redist(e, token, dry=dry)
            except Exception as exc:                    # noqa: BLE001 — 한 편이 죽어도 나머지는 돈다
                print("  %-6s 🔴 %s" % (e, exc))
                continue
            state = r.get("recorded")
            if state in ("already", "skip"):
                print("  %-6s %s%s" % (e, state, (" — " + r["why"]) if r.get("why") else ""))
            else:
                wrote += 1
                print("  %-6s %s" % (e, "dryrun" if dry else "기록"))
                print("      %s" % r["row" if dry else "recorded"][:150])
        print("STATUS: OK (%d편 %s)" % (wrote, "적을 것" if dry else "기록"))
        return 0

    ep = argv[argv.index("--ep") + 1]
    token = ig_watch.load_token()
    _, media = ig_watch.fetch(token)
    state = {"ep": ep, "media": media}
    if "--shortcode" in argv:
        state["shortcode"] = argv[argv.index("--shortcode") + 1]
    if "--detect" in argv:
        try:
            d = detect(state)
            print("감지:", {k: d[k] for k in ("shortcode", "published_kst", "title", "cards", "media_type", "kit")})
            print("STATUS: OK")
            return 0
        except gr.Wait as w:
            print(f"STATUS: WAIT detect: {w}")
            return 3
    ckpt = ROOT / "logs" / "tail" / f"{ep}.ckpt.json"
    if "--reset" in argv and ckpt.exists():
        ckpt.unlink()
    return gr.run(GRAPH, ckpt, state)


def _self_test():
    global WORKSHOP, PUBLOG
    with tempfile.TemporaryDirectory() as d:
        WORKSHOP, PUBLOG = Path(d) / "ws", Path(d) / "ws" / "발행로그.md"
        ep = (WORKSHOP / "02_제작중" / "ep99_시험편")
        ep.mkdir(parents=True)
        (WORKSHOP / "01_발행완료").mkdir()
        (ep / "caption.txt").write_text("시험 훅? 9월 9주차 AI 소식\n\n본문", "utf-8")
        (ep / "build_ep99.py").write_text('CORNER = "주간 AI 소식"\nKIT = None\n', "utf-8")
        (ep / "01_cover.png").write_bytes(b"png1")
        (ep / "02_a.mp4").write_bytes(b"mp4")
        (ep / "shots").mkdir()
        (ep / "shots" / "x.png").write_bytes(b"s")
        PUBLOG.write_text("# 발행로그\n\n| ep | 제목 | 상태 | 발행일 | 트리거 | 키트 | 위치 | 비고 | 기록 시각 |\n|---|---|---|---|---|---|---|---|---|\n"
                          "| ep1 | 첫 편 | 발행 | 2026-08-01 | — | — | `01_발행완료/ep1` | 비고가\n두 줄 | 2026-08-01 10:00 KST |\n\n"
                          "## 편수\n\n| 층 | 값 |\n|---|---|\n| 편 | 1 |\n", "utf-8")
        old_row_count = len(publog_check.main_table(PUBLOG.read_text("utf-8")).split("\n"))
        ck = Path(d) / "ck.json"
        quiet = lambda *a: None  # noqa: E731
        media0 = [{"shortcode": "OTHER", "caption": "다른 글", "timestamp": "2026-09-14T09:00:00+0000", "media_type": "IMAGE", "permalink": "x"}]
        st = {"ep": "ep99_시험편", "media": media0, "_no_backup": True}
        assert gr.run(GRAPH, ck, st, log=quiet) == 3, "안 올라갔으면 WAIT"
        hit = {"shortcode": "ABC12345678", "caption": "시험 훅? 9월 9주차 AI 소식\n\n본문", "timestamp": "2026-09-14T09:00:00+0000",
               "media_type": "CAROUSEL_ALBUM", "permalink": "https://www.instagram.com/p/ABC12345678/"}
        c = gr.load(ck); c["state"]["media"] = media0 + [hit]; gr.save(ck, c)
        assert gr.run(GRAPH, ck, log=quiet) == 0, "재개해서 끝까지"
        text = PUBLOG.read_text("utf-8")
        rows = ep_rows(text, "ep99")
        assert len(rows) == 1 and "2026-09-14 18:00 KST" in rows[0] and "캐러셀 2장" in rows[0] and "[주간 AI 소식] 시험 훅?" in rows[0], rows
        assert len(publog_check.main_table(text).split("\n")) == old_row_count + 1, "본 표 밖에 붙었다"
        assert "| 편 | 1 |" in text and "두 줄 | 2026-08-01" in text, "다른 표·기존 행이 변했다"
        assert (WORKSHOP / "01_발행완료" / "ep99_시험편" / "shots" / "x.png").read_bytes() == b"s" and not ep.exists()
        assert gr.run(GRAPH, ck, log=quiet) == 0 and len(ep_rows(PUBLOG.read_text("utf-8"), "ep99")) == 1, "재실행에 행이 두 번 붙었다"
        # 여러 줄 KIT 딕셔너리(ep49 꼴) — 킷 칸에 html 값 하나가 적혀야 한다. 한 줄 문자열·None 도 같이 본다.
        kb = WORKSHOP / "02_제작중" / "ep96_k"; kb.mkdir()
        (kb / "build_ep96.py").write_text('CORNER = "AI 소식"\nKIT = {"file": "08_kit.mp4",\n       "html": "x-kit.html",\n'
                                          '       "dur": 22.8,   # 실측\n       "title": "킷"}\n', "utf-8")
        assert read_decl(kb / "build_ep96.py", "KIT") == '"x-kit.html"', read_decl(kb / "build_ep96.py", "KIT")
        (kb / "build_ep96.py").write_text('KIT = "y-kit.html"  # 재사용\n', "utf-8")
        assert read_decl(kb / "build_ep96.py", "KIT") == '"y-kit.html"'
        (kb / "build_ep96.py").write_text('KIT = None\n', "utf-8")
        assert read_decl(kb / "build_ep96.py", "KIT") == "None" and read_decl(kb / "build_ep96.py", "NOPE") is None
        # 역검증 ① 행 선재 없이 move → FAIL
        (WORKSHOP / "02_제작중" / "ep98_x").mkdir(); (WORKSHOP / "02_제작중" / "ep98_x" / "a.png").write_bytes(b"a")
        try:
            move({"ep": "ep98_x"}); raise AssertionError("행 없이 이동됐다")
        except RuntimeError as e:
            assert "선재" in str(e)
        # 역검증 ② 같은 첫 줄 2건 → FAIL(애매)
        try:
            detect({"ep": "ep99_시험편", "media": [hit, dict(hit, shortcode="ZZZ99999999")]}); raise AssertionError("애매한데 통과")
        except RuntimeError as e:
            assert "2건" in str(e)
        # 역검증 ③ 이동 중 해시가 달라지면 되돌리고 FAIL
        (WORKSHOP / "02_제작중" / "ep97_y").mkdir(); (WORKSHOP / "02_제작중" / "ep97_y" / "a.png").write_bytes(b"a")
        PUBLOG.write_text(PUBLOG.read_text("utf-8").replace("| **ep99** |", "| **ep97** |"), "utf-8")  # ep97 «발행» 행을 흉내
        orig = tree_hashes
        try:
            globals()["tree_hashes"] = lambda f: orig(f) if f.name != "ep97_y" or f.parent.name == "02_제작중" else {"a.png": "tampered"}
            try:
                move({"ep": "ep97_y"}); raise AssertionError("해시 불일치인데 통과")
            except RuntimeError as e:
                assert "불일치" in str(e) and (WORKSHOP / "02_제작중" / "ep97_y").exists(), "되돌리지 않았다"
        finally:
            globals()["tree_hashes"] = orig

        # ── 역검증 — 재유통 기록 (`--redist` · 2026-09-11) ────────────────────
        #
        # 🔴 **네 갈래 중 셋이 «적지 않아야 하는 쪽» 이다.** 발행로그는 「무엇이 나갔는가」의
        #    정본이라, 안 나간 것을 적는 실수가 못 적는 실수보다 비싸다.
        global RECEIPTS
        RECEIPTS = Path(d) / "receipts"
        RECEIPTS.mkdir()
        PUBLOG.write_text(
            "# 발행로그\n\n| ep | 제목 | 상태 | 발행일 | 트리거 | 키트 | 위치 | 비고 | 기록 시각 |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            "| **ep1** | 첫 편 | **발행** | 2026-08-01 | — | k.html | `01_발행완료/ep1` | — | 2026-08-01 10:00 KST |\n"
            "\n## 편수\n\n| 층 | 값 |\n|---|---|\n| 편 | 1 |\n", "utf-8")
        (RECEIPTS / "ep1.jsonl").write_text(
            '{"stage": "post.claim", "seq": 1}\n'
            '{"stage": "post.receipt", "seq": 1, "media_id": "M1"}\n'
            '{"stage": "post.receipt", "seq": 2, "media_id": "M2"}\n', "utf-8")
        (RECEIPTS / "ep2.jsonl").write_text('{"stage": "post.claim", "seq": 1}\n', "utf-8")
        orig_media = threads_media
        globals()["threads_media"] = lambda mid, tok: {
            "id": mid, "media_type": "VIDEO", "permalink": "https://www.threads.com/p/" + mid,
            "timestamp": "2026-08-01T02:00:00+0000"}
        try:
            r = redist("ep1", "TOK")
            t2 = PUBLOG.read_text("utf-8")
            assert r["recorded"].startswith("| **ep1-Threads**"), r
            assert len(ep_rows(t2, "ep1-Threads")) == 1, "행이 안 붙었다"
            assert "2026-08-01 11:00 KST" in r["recorded"], "UTC→KST 환산이 틀렸다"
            assert "2포스트 체인" in r["recorded"] and "P1 공식 영상 첨부" in r["recorded"]
            assert "`01_발행완료/ep1`" in r["recorded"], "위치를 인스타 행에서 안 가져왔다"
            assert len(publog_check.split_rows(publog_check.main_table(t2))) == 3, "본 표 밖에 붙었다"
            assert "| 편 | 1 |" in t2, "다른 표가 변했다"
            assert redist("ep1", "TOK")["recorded"] == "already", "두 번 붙었다"
            assert redist("ep2", "TOK")["recorded"] == "skip", "선점(claim)만 있는데 적었다"
            assert redist("ep9", "TOK")["recorded"] == "skip", "영수증이 없는데 적었다"
            # 🔴 원류(인스타 행)가 없으면 적지 않는다
            (RECEIPTS / "ep3.jsonl").write_text('{"stage": "post.receipt", "seq": 1, "media_id": "M3"}\n', "utf-8")
            try:
                redist("ep3", "TOK"); raise AssertionError("인스타 행이 없는데 적었다")
            except RuntimeError as e:
                assert "인스타 행이" in str(e)
            # 🔴 Threads 에서 못 읽으면 값을 추측해 적지 않는다
            globals()["threads_media"] = lambda mid, tok: {"id": mid}
            try:
                redist("ep4", "TOK")
                (RECEIPTS / "ep4.jsonl").write_text('{"stage": "post.receipt", "seq": 1, "media_id": "M4"}\n', "utf-8")
                redist("ep4", "TOK"); raise AssertionError("permalink 없이 적었다")
            except RuntimeError as e:
                assert "못 읽었다" in str(e)
        finally:
            globals()["threads_media"] = orig_media
    print("ok   WAIT→재개→행(본 표 끝·값 정확)→해시 이동→재실행 안전 · 역검증: 행 선재 없이 이동 FAIL · 애매 감지 FAIL · 해시 불일치 롤백")
    print("ok   재유통(--redist): 행 1건 기록 · 재기록·선점만·영수증없음 3건 건너뜀 · 원류없음·조회실패 2건 FAIL")
    print("STATUS: OK")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
