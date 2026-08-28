# -*- coding: utf-8 -*-
"""드라이브에 남은 **옛 판본 덱 파일**을 찾아 제거 명령을 낸다 (2026-08-28 신설).

## 왜 있나

덱 파일명이 `01_cover.png` 처럼 **자리 번호**라, 카드를 하나 넣거나 빼면 뒤가 전부 밀려
이름이 통째로 바뀐다. 드라이브는 같은 이름만 덮어쓰므로 **옛 번호 파일이 남고** 폰에서 덱이 섞인다.
근본 해결은 이름을 내용 기반으로 바꾸는 것이다(`docs/infra-backlog.md` **10번** ①).
이 파일은 그 전까지의 ③층 도구다.

🔴 **지우지 않는다.** 드라이브 삭제는 되돌리기 어렵고 정관상 사람 자리다 —
이 스크립트는 **무엇을 지울지 보여 주고 명령을 만들어 줄 뿐**이다.

🔴 **목록은 덱이 바뀔 때마다 달라진다.** 한 번 뽑아 둔 명령을 재사용하지 말고
**지우기 직전에 다시 돌린다** — 2026-08-28 에 ep35 덱이 한 세션에 두 번 움직여
먼저 뽑은 목록이 곧 낡았다.

    py scripts/stale_delivery.py
    py scripts/stale_delivery.py --drive "G:\\내 드라이브"
"""
import argparse
import os
import sys

DEFAULT_DRIVE = os.path.join("G:" + os.sep, "내 드라이브")
DEFAULT_SRC = os.path.join(
    os.path.expanduser("~"), "orca", "tomangchi-lab.github.io", "workshop", "02_제작중")
DECK_EXT = (".png", ".mp4")


def deck_files(d):
    """덱으로 나가는 파일 — 번호로 시작하는 png·mp4."""
    return sorted(f for f in os.listdir(d)
                  if f[:1].isdigit() and os.path.splitext(f)[1].lower() in DECK_EXT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive", default=DEFAULT_DRIVE)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--eps", nargs="*", default=None)
    a = ap.parse_args()

    eps = a.eps or sorted(f for f in os.listdir(a.src) if f.startswith("ep"))
    lines, cmds, total = ["드라이브 옛 판본 훑기", ""], [], 0
    for ep in eps:
        s, d = os.path.join(a.src, ep), os.path.join(a.drive, ep)
        if not os.path.isdir(s):
            continue
        if not os.path.isdir(d):
            lines.append("%-20s 드라이브 폴더 없음 — 전달 전" % ep)
            continue
        want, have = deck_files(s), deck_files(d)
        stale = [f for f in have if f not in want]
        missing = [f for f in want if f not in have]
        total += len(stale)
        lines.append("%-20s 덱 %2d · 드라이브 %2d · 잔존 %d%s"
                     % (ep, len(want), len(have), len(stale),
                        " · 🔴 누락 %d" % len(missing) if missing else ""))
        if missing:
            lines.append("%-20s   누락: %s" % ("", ", ".join(missing)))
        if stale:
            lines.append("%-20s   잔존: %s" % ("", ", ".join(stale)))
            cmds.append('powershell -NoProfile -Command "Remove-Item -LiteralPath %s -Force"'
                        % ", ".join("'%s'" % os.path.join(d, f) for f in stale))

    lines += ["", "총 잔존 %d개" % total]
    if cmds:
        lines += ["", "제거 명령 (사람이 확인하고 실행한다 — 실행 뒤 재전달):", ""]
        lines += [c + "\n" for c in cmds]
    else:
        lines += ["", "🟢 잔존 없음 — 재전달 불필요"]
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
