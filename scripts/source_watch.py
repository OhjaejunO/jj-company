#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
릴스 원작자 소스 목록 관찰 — 래퍼 선실행 데이터 수집 (2026-08-19 신설)

content-scout 실행 순서 1-1(소스 목록 신작 확인)의 데이터 수집부.
스케줄 실행에서 에이전트에게 yt-dlp 를 열어 주지 않고, 래퍼가 이 스크립트로
조회 결과를 파일에 떨군 뒤 에이전트는 Read 만 한다 (ops-auditor 와 같은
«래퍼 선실행» 패턴 — docs/ops-grade-boundary.md).

근거: 2026-08-19 스케줄분에서 에이전트가 소스 목록 단계를 통째로 건너뛰었다
(리포트에 «소스 목록 신작 없음» 문구조차 없음, codex 감리 FINDING #2). 스케줄
allowlist 에 yt-dlp 가 원래 없었으므로 구조적으로 불가능한 단계였고, 그 사이
스풉(@spoop-v7v) 8/17 신작이 관찰되지 않은 채 지나갔다.

입력: departments/marketing/config.md 의 「릴스 원작자 소스 목록」 표.
      실행 시점에 표를 파싱하므로 목록이 자라도 코드는 그대로다.
출력(stdout, UTF-8): 소스마다 한 블록.
    --- <원작자> | <플랫폼> @<핸들>
    STATUS=OK | FAIL <사유> | UNSUPPORTED <사유>
    <upload_date>|<view_count>|<duration_s>|<title>|<url>   (OK 일 때, 최신순 최대 N건)
맨 위에 SOURCE_LIST_FILE= / SOURCE_COUNT= / YOUTUBE_COUNT= 헤더.

조회는 YouTube 만 한다 — yt-dlp 가 Threads 를 지원하지 않고 Instagram 은 로그인
장벽이라 실측(2026-08-19)에서 둘 다 실패했다. 그 계정들은 UNSUPPORTED 로 남겨
에이전트가 WebFetch 로 보거나 «미확인»으로 적게 한다. 0건으로 적지 않는다.

종료 코드: 0 = 파일을 만들 수 있는 상태(소스별 실패는 STATUS 줄로 표현).
          2 = 소스 표를 못 찾음(설정 문제 — 래퍼가 FAIL 로 올린다).
"""

import re
import subprocess
import sys
from pathlib import Path

CONFIG = Path(r"C:\Users\ojaej\jj-company\departments\marketing\config.md")
SECTION_MARK = "릴스 원작자 소스 목록"
PER_SOURCE = 5
YT_TIMEOUT_S = 90
HANDLE_RE = re.compile(r"(YouTube|Threads|Instagram|TikTok|X)\s*`@([\w.\-]+)`")


def load_sources(config_path):
    text = config_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and SECTION_MARK in line:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    sources = []
    seen_rows = False
    for line in lines[start:end]:
        # The section holds sub-tables that are NOT sources (e.g. "### 툴 공식 데모"
        # = vendor showreels, treated as ads). The source table is the first one;
        # stop at the first sub-heading after it.
        if seen_rows and line.startswith("### "):
            break
        if not line.startswith("| **"):
            continue
        seen_rows = True
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        name = cells[0].strip("*").strip()
        for platform, handle in HANDLE_RE.findall(cells[1]):
            sources.append((name, platform, handle))
    return sources


def probe_youtube(handle):
    url = f"https://www.youtube.com/@{handle}/videos"
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--skip-download", "--no-warnings",
        "--playlist-end", str(PER_SOURCE),
        "--socket-timeout", "30", "--retries", "2", "--extractor-retries", "1",
        "--print", "%(upload_date)s|%(view_count)s|%(duration)s|%(title).80s|%(webpage_url)s",
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=YT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return "FAIL timeout after %ss" % YT_TIMEOUT_S, []
    except FileNotFoundError as e:
        return "FAIL yt-dlp not runnable: %s" % e, []
    rows = [l for l in r.stdout.splitlines() if l.count("|") >= 4]
    if r.returncode != 0 or not rows:
        err = " ".join(r.stderr.strip().splitlines()[-1:]) or "no rows"
        return "FAIL exit %s: %s" % (r.returncode, err[:200]), []
    return "OK", rows


def main():
    if not CONFIG.exists():
        print("SOURCE_LIST_FILE=MISSING " + str(CONFIG))
        return 2
    sources = load_sources(CONFIG)
    if sources is None:
        print("SOURCE_LIST_FILE=" + str(CONFIG))
        print("SOURCE_COUNT=SECTION_NOT_FOUND")
        return 2
    yt = [s for s in sources if s[1] == "YouTube"]
    print("SOURCE_LIST_FILE=" + str(CONFIG))
    print("SOURCE_COUNT=%d" % len(sources))
    print("YOUTUBE_COUNT=%d" % len(yt))
    print("NOTE=YouTube only is probed by the wrapper; other platforms are UNSUPPORTED here (WebFetch or mark unverified)")
    for name, platform, handle in sources:
        print("--- %s | %s @%s" % (name, platform, handle))
        if platform != "YouTube":
            print("STATUS=UNSUPPORTED %s is not probed by the wrapper" % platform)
            continue
        status, rows = probe_youtube(handle)
        print("STATUS=" + status)
        for row in rows:
            print(row)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
