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

ROOT = HERE.parent
WORKSHOP = Path(os.environ.get("TOMANGCHI_WORKSHOP", r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop"))
PUBLOG = Path(os.environ.get("TOMANGCHI_PUBLOG", str(WORKSHOP / "발행로그.md")))
KST = dt.timezone(dt.timedelta(hours=9))
BACKUP_PS1 = HERE / "workshop-backup.ps1"


# ---------------------------------------------------------------- 도우미
def first_line(p):
    return p.read_text("utf-8").split("\n")[0].strip()


def read_decl(build, name):
    """`NAME = 값` 한 줄을 읽는다. 없으면 None — 조용히 넘기지 않고 호출한 쪽이 «없음»으로 적는다."""
    m = re.search(rf"^{name}\s*=\s*(.+?)\s*(#.*)?$", build.read_text("utf-8"), re.M)
    return m.group(1).strip() if m else None


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
    print("ok   WAIT→재개→행(본 표 끝·값 정확)→해시 이동→재실행 안전 · 역검증: 행 선재 없이 이동 FAIL · 애매 감지 FAIL · 해시 불일치 롤백")
    print("STATUS: OK")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
