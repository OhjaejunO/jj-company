# -*- coding: utf-8 -*-
"""아침 회차 인증·마운트 점검 — 래퍼가 에이전트보다 **먼저** 돌린다.

**왜 있나 (2026-08-27).** 하루에 둘이 같이 만료돼 각각을 막았다.
  · `gh` 토큰 만료 → push 와 PR 생성이 막혀 킷 배포가 멈췄다.
  · 구글 드라이브 데스크톱 미실행 → `deliver.py` 가 «'내 드라이브'를 찾지 못했다» 로
    멈춰 폰 전달이 안 됐다(마운트가 C: 하나뿐이었다).
**둘 다 «발행 직전에 발견»되는 종류다** — 그때는 이미 급하다. 아침에 미리 잡는다.

**등급.** 조회만 한다(A등급). 로그인·갱신은 사람이 한다 — 이 스크립트는 **명령을 알려 줄 뿐**
실행하지 않는다.

**STATUS 를 떨어뜨리지 않는다.** 정관 §4 «STATUS 의 뜻은 작업을 끝까지 수행했는가»다.
인증이 만료됐다고 감사가 성립하지 않는 것은 아니므로, 여기서는 **KEY=value 로 사실만 남기고**
🔴 판정은 리포트에서 한다.

    py auth_check.py            # KEY=value 를 stdout 으로
    py auth_check.py --selftest # 판정 함수 역검증만
"""
import os
import string
import subprocess
import sys


def _run(cmd, timeout=30):
    """(종료코드, 출력). 실행 자체가 안 되면 (None, 사유) — 조용히 성공으로 넘기지 않는다."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except FileNotFoundError:
        return None, "명령을 찾을 수 없다: %s" % cmd[0]
    except subprocess.TimeoutExpired:
        return None, "시간 초과 %ss: %s" % (timeout, cmd[0])
    except Exception as e:                                  # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, e)


# ── 판정 함수 (순수) — 역검증이 합성 입력을 넣을 수 있게 분리한다 ────────────
def gh_verdict(code, out):
    """gh auth status 결과 → (상태, 한 줄). 상태: OK · EXPIRED · UNKNOWN"""
    if code is None:
        return "UNKNOWN", out
    low = (out or "").lower()
    if code == 0 and "logged in" in low:
        return "OK", "로그인 상태"
    if "not logged" in low or "authentication failed" in low or "token is invalid" in low:
        return "EXPIRED", "재로그인 필요"
    if code != 0:
        return "EXPIRED", "gh 종료코드 %s" % code
    return "UNKNOWN", "판정 불가 — 출력에 상태 문구가 없다"


def drive_verdict(mount_path, proc_count):
    """(마운트 경로 또는 None, 프로세스 수) → (상태, 한 줄).

    🔴 **둘 다 본다.** 프로세스가 죽어도 경로가 잠깐 남아 있을 수 있고,
    프로세스만 살아 있고 마운트가 아직 안 붙은 순간도 있다. 한쪽만 보면 둘 다 놓친다.
    """
    if mount_path and proc_count > 0:
        return "OK", mount_path
    if not mount_path and proc_count > 0:
        return "MOUNTING", "프로세스는 떠 있는데 '내 드라이브' 경로가 없다"
    if mount_path and proc_count == 0:
        return "STALE", "경로는 있는데 GoogleDriveFS 프로세스가 없다 — %s" % mount_path
    return "DOWN", "구글 드라이브 데스크톱이 실행 중이 아니다"


def find_drive():
    """deliver.py 와 같은 방식 — G: 우선, 없으면 전 드라이브 탐색."""
    for letter in ["G"] + [c for c in string.ascii_uppercase if c != "G"]:
        p = "%s:\\내 드라이브" % letter
        if os.path.isdir(p):
            return p
    return None


def drive_procs():
    code, out = _run(["powershell", "-NoProfile", "-Command",
                      "(Get-Process -Name 'GoogleDriveFS' -ErrorAction SilentlyContinue "
                      "| Measure-Object).Count"])
    if code is None:
        return -1                                          # 조회 실패는 0 과 다르다
    try:
        return int((out or "0").strip().splitlines()[-1])
    except Exception:                                       # noqa: BLE001
        return -1


def collect():
    lines = []
    gcode, gout = _run(["gh", "auth", "status"])
    gs, gmsg = gh_verdict(gcode, gout)
    lines.append("GH_AUTH=%s" % gs)
    lines.append("GH_AUTH_NOTE=%s" % gmsg)
    if gs != "OK":
        lines.append("GH_AUTH_FIX=gh auth login --hostname github.com --git-protocol https --web")

    mount = find_drive()
    procs = drive_procs()
    ds, dmsg = drive_verdict(mount, procs)
    lines.append("DRIVE=%s" % ds)
    lines.append("DRIVE_NOTE=%s" % dmsg)
    lines.append("DRIVE_MOUNT=%s" % (mount or "-"))
    lines.append("DRIVE_PROCS=%s" % procs)
    if ds != "OK":
        lines.append("DRIVE_FIX=구글 드라이브 데스크톱을 실행하고 로그인 상태를 확인한다 (사람)")

    lines.append("AUTH_ALL_OK=%s" % ("yes" if (gs == "OK" and ds == "OK") else "no"))
    return lines


def selftest():
    """역검증 — 걸려야 하는 입력이 걸리고, 통과해야 하는 입력이 통과하는지 **양쪽**."""
    cases = [
        ("gh 로그인됨", gh_verdict(0, "github.com\n  * Logged in to github.com as OhjaejunO")[0], "OK"),
        ("gh 만료", gh_verdict(1, "You are not logged into any GitHub hosts.")[0], "EXPIRED"),
        ("gh 토큰 무효", gh_verdict(1, "The token is invalid.")[0], "EXPIRED"),
        ("gh 실행 불가", gh_verdict(None, "명령을 찾을 수 없다: gh")[0], "UNKNOWN"),
        ("gh 종료 0 인데 문구 없음", gh_verdict(0, "")[0], "UNKNOWN"),
        ("드라이브 정상", drive_verdict("G:\\내 드라이브", 2)[0], "OK"),
        ("드라이브 미실행", drive_verdict(None, 0)[0], "DOWN"),
        ("프로세스만 있고 마운트 없음", drive_verdict(None, 1)[0], "MOUNTING"),
        ("마운트만 있고 프로세스 없음", drive_verdict("G:\\내 드라이브", 0)[0], "STALE"),
    ]
    bad = [(n, got, want) for n, got, want in cases if got != want]
    for n, got, want in cases:
        print("  %s %-28s %s" % ("OK  " if got == want else "FAIL", n, got))
    if bad:
        print("STATUS: FAIL auth_check-selftest (%d)" % len(bad))
        return 1
    print("STATUS: OK — 역검증 %d건" % len(cases))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    for ln in collect():
        print(ln)
