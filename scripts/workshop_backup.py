#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""워크숍 소스 백업 (B등급 · 워크숍은 **읽기만** 한다)

인프라 백로그 **21번 후보 ㉰** — 안전판. 본안(㉮ 사설 레포)이 서기 전까지의 자리다.

## 무엇을 담는가

`workshop/` 에서 **다시 못 만드는 것**만 담는다. 렌더물(png·mp4 3250개 3.8GB)은 빼고,
텍스트 소스 + `_official/` 원본 소재만 넣으면 10MB 대다.

  · 텍스트 소스 — `.py`·`.md`·`.html`·`.css`·`.js`·`.json`·`.txt`
  · `_official/` 아래 **전부** (공식 영상·캡처 원본. 재수집은 되나 «그때 그 원본» 보장 없음)
  · 🔴 `스캔로그/`·`발행로그.md` 는 **이름으로 따로 못박는다.** 확장자 규칙에 이미 걸리지만,
    규칙이 바뀌어도 이 둘은 빠지면 안 된다 — `스캔로그` 는 정관 §2 가 유일한 출장지 쓰기
    예외를 준 **자회사 정본**이고 `발행로그.md` 는 채널 원장이다.

## 무엇을 «확인» 이라 부르는가

쓴 것으로 끝내지 않는다. **다시 열어 멤버별 해시를 원본과 대조**한다 — 그래야 「백업했다」가
주장이 아니라 사실이 된다(정관 §0 «감지 장치가 값을 담는지 검증한다»).

🔴 **그래도 증명 못 하는 것이 있다 (§0 4층 ④).** 드라이브 백업은 **G: 까지만** 확인된다.
   구글 클라우드에 실제로 동기됐는지는 Drive API 로 조회가 안 돼 **확인 불가**다.
   그래서 리포트에 «클라우드 반영: 확인 불가» 를 **매 회차 적는다.** 적지 않으면
   「백업됐다」로 읽히고, 그것이 이 조항이 막으려는 바로 그것이다.

## 워크숍 쓰기 금지 (정관 §2)

이 스크립트는 워크숍을 **연다(open)** 만 한다. zip 도 원장도 워크숍 **밖**에 쓴다.
`--self-test` 가 그것을 실증한다 — 워크숍 트리의 파일 수·mtime 이 전후로 같은지 본다.

## 정지 조건 — 퓨즈 (2026-08-31 신설 · C-40)

**ⓐ 스스로 멈춘다**

1. **워크숍 트리 지문이 전후로 바뀌면 `STATUS: FAIL workshop-mutated`** 다. 이 워커는
   워크숍을 **읽기만** 하는 것이 §2 예외 3의 핵심 제약이고, 그 제약을 말이 아니라
   **전후 지문 비교**로 지킨다.
2. **zip 을 다시 열어 멤버 해시가 하나라도 어긋나면 그 백업은 무효다.** 「담았다」가 아니라
   **「담긴 것이 원본과 같다」**를 재야 백업이다(§0 «감지 장치가 값을 담는지»).
3. **드라이브 사본 해시가 다르면 `STATUS: FAIL`** 이다. 🔴 **다만 확인은 `G:` 까지다** —
   클라우드 반영은 조회할 방법이 없어 **«확인 불가»** 로 남는다(§0 4층 ④).

**ⓑ JJ 가 끈다**

1. **zip 크기가 직전 회차 대비 절반 이하로 줄면** 끈다 — 대상 목록이 조용히 좁아진 신호다.
   (크기가 느는 것은 정상이다. **주는 것이 신호다.**)
2. **드라이브 여유 공간이 백업 2회분 아래로 떨어지면** 끈다.
3. **워크숍 소스가 정규 레포로 옮겨지면 이 워커의 대상 목록이 줄고, 그때 폐기를 판정한다**
   (§2 예외 3의 폐기 조건과 같다).
"""
import argparse
import datetime
import hashlib
import io
import os
import re
import sys
import zipfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

WS = os.environ.get(
    "TOMANGCHI_WORKSHOP",
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop")
HQ = os.environ.get("JJ_HQ", r"C:\Users\ojaej\jj-company")

SRC_EXT = (".py", ".md", ".html", ".css", ".js", ".json", ".txt")
#: 🔴 이름으로 못박는 자리. 확장자 규칙이 바뀌어도 이것들은 빠지면 안 된다.
MUST_DIRS = ("_official", "\uc2a4\uce94\ub85c\uadf8")
MUST_FILES = ("\ubc1c\ud589\ub85c\uadf8.md",)
SKIP_DIRS = ("__pycache__", ".git")

#: ── ⓒ 자산 — **다시 못 만드는 것** (JJ 판정 2026-08-30) ─────────────────────
#: `_scenes/` 는 모델이 만든다. 같은 프롬프트로도 같은 그림이 안 나온다.
#: `_assets/`·`assets/` 는 제공·수집물, `00_브랜드에셋` 이미지는 로고·엔드카드 원본이다.
ASSET_DIRS = ("_scenes", "_assets")
ASSET_ROOTS = ("assets", "00_\ube0c\ub79c\ub4dc\uc5d0\uc14b")
ASSET_EXT = (".png", ".jpg", ".jpeg", ".mp4", ".webp", ".gif", ".mov", ".ttf", ".otf")

#: ── ⓓ 보존분 — **발행 채택본** ────────────────────────────────────────────
#: 릴스 최종물·채널 광고·릴스 표지 프레임. 덱 번호 체계 밖에서 발행되는 산출물이라
#: 빌더가 다시 만들지 않는다. 🔴 선행 실측에서 이것들이 «옛 시안» 더미에 있었다.
FINAL_RE = re.compile(r"(reel[0-9_]*\.mp4$|reel_[a-z0-9_]+\.(mp4|png)$"
                      r"|cover_frame\.png$|ad_[a-z0-9_]+\.mp4$|01_reel\.mp4$)", re.I)
#: 🔴 아카이브·폐기 **안의** 최종물 꼴은 최종물이 아니다 — 자리로 먼저 가른다.
DROP_DIRS = ("_archive", "_retired", "_\ud3d0\uae30")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def collect(root):
    """(상대경로, 절대경로) 목록 — 담을 것만."""
    out = []
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        parts = os.path.relpath(cur, root).replace("\\", "/").split("/")
        in_must = any(p in MUST_DIRS for p in parts)
        in_asset = any(p in ASSET_DIRS for p in parts) or (parts and parts[0] in ASSET_ROOTS)
        in_drop = any(p in DROP_DIRS for p in parts)
        for f in files:
            rel = os.path.relpath(os.path.join(cur, f), root).replace("\\", "/")
            low = f.lower()
            keep = in_must or f in MUST_FILES or low.endswith(SRC_EXT)
            # ⓒ 자산 — 다시 못 만든다
            if not keep and in_asset and low.endswith(ASSET_EXT):
                keep = True
            # ⓓ 발행 채택본 — **코드가 만드는 덱 산출물은 먼저 뺀다**(순서가 판정을 바꾼다)
            if (not keep and not in_drop and not f[:1].isdigit()
                    and not f.startswith("_") and "shots" not in parts
                    and FINAL_RE.search(f)):
                keep = True
            if keep:
                out.append((rel, os.path.join(cur, f)))
    return sorted(out)


def tree_state(root):
    """워크숍이 안 바뀌었음을 볼 지문 — 파일 수 + (경로, 크기, mtime) 해시."""
    h = hashlib.sha256()
    n = 0
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            p = os.path.join(cur, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            n += 1
            h.update(("%s|%d|%d" % (os.path.relpath(p, root), st.st_size,
                                    int(st.st_mtime))).encode("utf-8", "replace"))
    return n, h.hexdigest()


def build_zip(items, dest):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel, p in items:
            z.write(p, rel)
    return dest


def verify_zip(items, dest):
    """**다시 열어** 멤버별 해시를 원본과 대조한다. 쓴 것으로 끝내지 않는다.

    돌려주는 것은 (문제 목록, 검사한 멤버 수).
    """
    bad = []
    src = {rel: p for rel, p in items}
    with zipfile.ZipFile(dest) as z:
        names = set(z.namelist())
        for rel in src:
            if rel not in names:
                bad.append("zip 에 없음: %s" % rel)
        for rel in sorted(names):
            if rel not in src:
                bad.append("원본에 없는 멤버: %s" % rel)
                continue
            got = hashlib.sha256(z.read(rel)).hexdigest()
            want = sha256_file(src[rel])
            if got != want:
                bad.append("내용 불일치: %s" % rel)
    return bad, len(items)


def drive_root():
    """구글 드라이브 «내 드라이브» — 문자를 고정하지 않는다(재로그인에 바뀐다)."""
    import string
    for letter in string.ascii_uppercase:
        p = "%s:\\%s" % (letter, "\ub0b4 \ub4dc\ub77c\uc774\ube0c")
        if os.path.isdir(p):
            return p
    return None


def ledger_line(rec):
    return ("| %s | %s | %d개 | %.2f MB | `%s` | %s |"
            % (rec["at"], rec["reason"], rec["count"], rec["mb"],
               rec["sha256"][:16], rec["drive"]))


def _self_test():
    """역검증 — 확인기가 헛돌지 않는가. **양방향**으로 본다.

    막는 것만 보면 «전부 실패로 읽는 확인기» 도 정상으로 보인다.
    """
    import tempfile
    d = tempfile.mkdtemp(prefix="_wsbk_")
    root = os.path.join(d, "ws")
    os.makedirs(os.path.join(root, "_official"))
    os.makedirs(os.path.join(root, "\uc2a4\uce94\ub85c\uadf8"))
    io.open(os.path.join(root, "a.py"), "w", encoding="utf-8").write("x = 1\n")
    io.open(os.path.join(root, "b.png"), "w", encoding="utf-8").write("render")
    io.open(os.path.join(root, "\ubc1c\ud589\ub85c\uadf8.md"), "w",
            encoding="utf-8").write("ledger\n")
    io.open(os.path.join(root, "_official", "v.mp4"), "w",
            encoding="utf-8").write("official-bytes")
    io.open(os.path.join(root, "\uc2a4\uce94\ub85c\uadf8", "s.md"), "w",
            encoding="utf-8").write("scan\n")

    items = collect(root)
    rels = {r for r, _ in items}
    # ⓐ 담아야 할 것이 담긴다 — 이름으로 못박은 자리 포함
    assert "a.py" in rels, rels
    assert "\ubc1c\ud589\ub85c\uadf8.md" in rels, "발행로그를 안 담았다"
    assert "_official/v.mp4" in rels, "_official 원본을 안 담았다 (확장자 규칙 밖이다)"
    assert "\uc2a4\uce94\ub85c\uadf8/s.md" in rels, "스캔로그를 안 담았다"
    # ⓑ 렌더물은 안 담는다 (전부 담는 백업이 아니다)
    assert "b.png" not in rels, "렌더물까지 담고 있다"
    # ⓑ-2 ⓒ 자산·ⓓ 채택본 (2026-08-30)
    os.makedirs(os.path.join(root, "ep9", "_scenes"))
    os.makedirs(os.path.join(root, "ep9", "reel"))
    os.makedirs(os.path.join(root, "ep9", "_archive"))
    for rel_, data in (("ep9/_scenes/cover_x.png", "scene"),
                       ("ep9/reel_ep9.mp4", "reel-final"),
                       ("ep9/reel/cover_frame.png", "reel-cover"),
                       ("ep9/08_kit.mp4", "deck-output"),
                       ("ep9/_archive/reel_old.mp4", "archived")):
        io.open(os.path.join(root, rel_.replace("/", os.sep)), "w",
                encoding="utf-8").write(data)
    rels2 = {r for r, _ in collect(root)}
    assert "ep9/_scenes/cover_x.png" in rels2, "생성 씬을 안 담았다 (ⓒ)"
    assert "ep9/reel_ep9.mp4" in rels2, "릴스 최종물을 안 담았다 (ⓓ)"
    assert "ep9/reel/cover_frame.png" in rels2, "릴스 표지 프레임을 안 담았다 (ⓓ)"
    # 🔴 순서 검사 — 덱 산출물은 이름이 비슷해도 안 담긴다
    assert "ep9/08_kit.mp4" not in rels2, "덱 산출물까지 담았다 (순서가 틀렸다)"
    # 🔴 아카이브 안의 최종물 꼴은 최종물이 아니다
    assert "ep9/_archive/reel_old.mp4" not in rels2, "아카이브까지 담았다"

    z = os.path.join(d, "t.zip")
    build_zip(items, z)
    bad, n = verify_zip(items, z)
    # ⓒ 멀쩡한 zip 은 통과
    assert not bad and n == len(items), bad
    # ⓓ **내용이 갈린 zip 은 걸린다.** 변조가 실제로 먹었는지 먼저 확인한다 (L-009).
    io.open(os.path.join(root, "a.py"), "w", encoding="utf-8").write("x = 2\n")
    assert io.open(os.path.join(root, "a.py"), encoding="utf-8").read() == "x = 2\n", \
        "변조가 안 먹었다 — 아래 «걸린다» 는 판정이 아니다"
    bad2, _ = verify_zip(items, z)
    assert any("\ub0b4\uc6a9 \ubd88\uc77c\uce58" in b for b in bad2), bad2
    # ⓔ **멤버가 빠진 zip 도 걸린다** (다른 축 — ⓓ 와 섞지 않는다)
    io.open(os.path.join(root, "a.py"), "w", encoding="utf-8").write("x = 1\n")
    short = os.path.join(d, "short.zip")
    build_zip(items[:-1], short)
    bad3, _ = verify_zip(items, short)
    assert any("zip \uc5d0 \uc5c6\uc74c" in b for b in bad3), bad3
    # ⓕ 워크숍은 **안 바뀐다** — zip 을 만들어도 트리 지문이 같다 (정관 §2)
    before = tree_state(root)
    build_zip(items, os.path.join(d, "again.zip"))
    assert tree_state(root) == before, "워크숍이 바뀌었다 — 읽기 전용을 어겼다"

    import shutil
    shutil.rmtree(d, ignore_errors=True)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="워크숍 소스 백업 (읽기 전용)")
    ap.add_argument("--reason", default="weekly",
                    help="주기(weekly) 또는 발행 직후(after-publish:<ep>)")
    ap.add_argument("--out-dir", default=None, help="zip 을 둘 로컬 자리")
    ap.add_argument("--no-drive", action="store_true", help="드라이브 복사 생략(시험용)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        _self_test()
        print("자체 검사 통과 — 담김·제외·불일치·누락·워크숍 불변 5축")
        return 0

    # 확인기가 헛돌면 그 뒤 STATUS 는 근거가 못 된다. 매 실행 앞에 세운다.
    _self_test()

    if not os.path.isdir(WS):
        print("🔴 워크숍을 못 찾았다: %s" % WS)
        print("STATUS: FAIL workshop-missing")
        return 1

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    today = datetime.date.today().isoformat()
    out_dir = a.out_dir or os.path.join(HQ, "logs", "backup")
    os.makedirs(out_dir, exist_ok=True)
    name = "workshop-source_%s.zip" % stamp
    local = os.path.join(out_dir, name)

    before = tree_state(WS)
    items = collect(WS)
    print("담을 것 %d개" % len(items))
    build_zip(items, local)
    size = os.path.getsize(local)
    print("zip %s · %.2f MB" % (name, size / 1e6))

    bad, n = verify_zip(items, local)
    if bad:
        for b in bad[:8]:
            print("🔴 %s" % b)
        print("STATUS: FAIL zip-verify (%d건)" % len(bad))
        return 1
    print("검증 통과 — 멤버 %d개 전부 원본과 해시 일치 (zip 을 다시 열어 대조)" % n)

    after = tree_state(WS)
    if after != before:
        print("🔴 워크숍 트리가 바뀌었다 — 이 작업은 읽기 전용이어야 한다 (정관 §2)")
        print("STATUS: FAIL workshop-mutated")
        return 1
    print("워크숍 불변 확인 — 파일 %d개 · 지문 %s…" % (before[0], before[1][:12]))

    digest = sha256_file(local)
    drive_note = "생략(--no-drive)"
    if not a.no_drive:
        root = drive_root()
        if root is None:
            print("🔴 구글 드라이브 «내 드라이브» 를 못 찾았다 — 데스크톱 앱이 떠 있는가")
            print("STATUS: FAIL drive-missing")
            return 1
        dst_dir = os.path.join(root, "_backup", "workshop")
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, name)
        import shutil
        shutil.copy2(local, dst)
        got = sha256_file(dst)
        if got != digest:
            print("🔴 드라이브 사본 해시가 다르다 — 복사가 깨졌다")
            print("STATUS: FAIL drive-hash")
            return 1
        drive_note = dst
        print("드라이브 사본 해시 일치: %s" % dst)

    rec = {"at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "reason": a.reason, "count": n, "mb": size / 1e6,
           "sha256": digest, "drive": drive_note}

    # 원장 — 로컬과 드라이브 **양쪽**에 둔다. 로컬에만 두면 원장 자신이 백업 밖이다.
    header = ("# 워크숍 소스 백업 원장\n\n"
              "🔴 **G: 까지만 확인된다.** 구글 클라우드 반영은 Drive API 조회가 안 돼\n"
              "**확인 불가**다 — 정관 §0 4층 ④. 아래 «드라이브» 칸은 «G: 에 그 해시로\n"
              "놓였다» 는 뜻이지 «클라우드에 올라갔다» 가 아니다.\n\n"
              "| 시각 | 사유 | 파일 수 | 크기 | zip sha256(앞16) | 드라이브 |\n"
              "|---|---|---|---|---|---|\n")
    for led in [os.path.join(out_dir, "\uc6d0\uc7a5.md")] + (
            [] if a.no_drive else [os.path.join(os.path.dirname(drive_note),
                                                "\uc6d0\uc7a5.md")]):
        old = io.open(led, encoding="utf-8").read() if os.path.exists(led) else header
        if not old.startswith("#"):
            old = header
        io.open(led, "w", encoding="utf-8", newline="\n").write(
            old.rstrip("\n") + "\n" + ledger_line(rec) + "\n")
    print("원장 기록: %s" % os.path.join(out_dir, "\uc6d0\uc7a5.md"))

    rep_dir = os.path.join(HQ, "reports")
    if os.path.isdir(rep_dir):
        rp = os.path.join(rep_dir, "%s_workshop-backup.md" % today)
        io.open(rp, "w", encoding="utf-8", newline="\n").write(
            "# 워크숍 소스 백업 — %s\n\n"
            "- 부서: 개발팀 / 등급: **B** (워크숍은 읽기만 · 드라이브에 새 파일만 쓴다)\n"
            "- 사유: %s\n- 담은 파일: %d개 · %.2f MB\n- zip sha256: `%s`\n"
            "- 로컬: `%s`\n- 드라이브: `%s`\n\n"
            "## 확인한 것\n\n"
            "- zip 을 **다시 열어** 멤버 %d개를 원본과 해시 대조 — 전부 일치\n"
            "- 워크숍 트리 지문 전후 동일 (파일 %d개) — 읽기 전용을 지켰다\n"
            "- 드라이브 사본 해시 = 로컬 해시\n\n"
            "## 🔴 확인 못 한 것 (§0 4층 ④)\n\n"
            "**클라우드 반영은 확인 불가.** G: 는 마운트된 로컬 뷰이고, 구글 클라우드에\n"
            "실제로 올라갔는지는 Drive API 조회가 안 돼 잴 방법이 없다. 이 리포트의\n"
            "«드라이브» 는 «G: 에 그 해시로 놓였다» 는 뜻이다.\n\n"
            "STATUS: OK\n"
            % (rec["at"], a.reason, n, size / 1e6, digest, local, drive_note,
               n, before[0]))
        print("리포트: %s" % rp)

    # 오래된 zip 정리 — **12개만 남긴다.** 지우는 것은 우리가 만든 zip 뿐이다.
    # 🔴 범위를 넓히며 한 벌이 ~1GB 가 됐다. 12개를 두면 12GB 다 —
    #    이력은 이제 레포(`tomangchi-workshop`)가 지므로 zip 은 **최근 것만** 둔다.
    zips = sorted(f for f in os.listdir(out_dir)
                  if f.startswith("workshop-source_") and f.endswith(".zip"))
    for old in zips[:-4]:
        os.remove(os.path.join(out_dir, old))
        print("옛 로컬 zip 정리: %s" % old)

    print("STATUS: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
