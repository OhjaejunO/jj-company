# -*- coding: utf-8 -*-
r"""오피스 뷰 녹화 — «전달 다시 보기» 를 눌러 캐릭터가 걸어가는 장면을 mp4 로 (포트폴리오용 · 2026-09-05).

    py tools\session-dashboard\record_office.py                → office_<날짜>.mp4 (20초 · 1600x900)
    py tools\session-dashboard\record_office.py --date yesterday --seconds 25 --out C:\path\office.mp4

서버(`dashboard.py`)가 127.0.0.1:8765 에 떠 있어야 한다. Playwright 가 webm 으로 녹화하고 imageio-ffmpeg 로 mp4 변환.
🔴 실제 세션 프롬프트가 말풍선에 찍힌다 — 밖에 낼 영상이면 찍기 전에 화면을 보고 민감한 문장이 없는지 확인한다.
"""
import argparse
import glob
import io
import os
import subprocess
import sys
import time
from datetime import datetime


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="today(기본) · yesterday · YYYY-MM-DD")
    ap.add_argument("--seconds", type=int, default=20)
    ap.add_argument("--out", default="")
    ap.add_argument("--url", default="http://127.0.0.1:8765/office")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    import imageio_ffmpeg
    out = a.out or os.path.join(os.getcwd(), "office_%s.mp4" % datetime.now().strftime("%Y%m%d_%H%M"))
    tmp = os.path.join(os.path.dirname(os.path.abspath(out)), "_office_rec")
    os.makedirs(tmp, exist_ok=True)
    url = a.url + ("?date=" + a.date if a.date else "")
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1600, "height": 900}, record_video_dir=tmp, record_video_size={"width": 1600, "height": 900})
        pg = ctx.new_page()
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(2500)
        n = pg.locator(".unit").count()
        ev = pg.evaluate("fetch('/api/events%s').then(r => r.json()).then(j => j.events.length)" % ("?date=" + a.date if a.date else ""))
        print("책상", n, "· 전달 이벤트", ev, "· url", url)
        pg.click("#replay")
        pg.wait_for_timeout(a.seconds * 1000)
        ctx.close()
        b.close()
    webm = max(glob.glob(os.path.join(tmp, "*.webm")), key=os.path.getmtime)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-v", "error", "-i", webm, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", out], check=True)
    os.remove(webm)
    print("wrote", out, round(os.path.getsize(out) / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
