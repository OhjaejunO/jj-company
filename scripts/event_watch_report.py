# -*- coding: utf-8 -*-
r"""사건형 트리거 감시 — 리포트·알림 작성 + pin 검사 (래퍼 `hermes-event-watch.ps1` 의 뒷단).

    py scripts\event_watch_report.py --date D --state DIR --out OUT_TXT --usage USAGE_JSON --report REPORT --alerts ALERTS
                                     [--pin nemotron-3.5-lightning-free] [--profile sagun] [--hermes-exit N]

왜 파이썬인가 — 래퍼(.ps1)는 ASCII 전용이다(PS 5.1 이 BOM 없는 UTF-8 을 ANSI 로 읽어 한글이 깨진다, 정관 §6).
리포트 문안은 한글이라 여기서 쓴다. **stdout 은 ASCII 로만 적는다** — 래퍼가 그 줄을 로그에 옮기는데
PS 5.1 은 네이티브 출력을 콘솔 코드페이지로 디코드해서 한글이 깨진다.

## 🔴 알림은 모델에 매달려 있지 않다 (2026-09-12 개정)

종전에는 프로바이더가 실패하면 `STATUS: FAIL provider` 로 끝났고 **알림 파일을 아예 안 썼다.**
그런데 감지는 `event_watch.py` 가 결정적으로 끝내 놓은 상태다 — 데이터는 다 있는데 알림만 사라졌다.
실측: 2026-09-08~12 **닷새 연속** 그렇게 끝났고(무료 프로바이더가 외부 호출을 막았다) 그 닷새의
감시처 폴링은 **40/40 성공**이었다. 모델이 하던 일은 «문안 정리»인데 그것이 없다고 **알림 자체를
버리는** 구조였다(정관 §0 4층 — ① 로 닫을 수 있는 것을 모델에 맡긴 자리).

이제 판정이 미수행이면 **결정적 후보로 알림을 쓰고** `STATUS: OK (부분: 헤르메스 판정 문안 없음)` 로
적는다 — §4 «STATUS 는 작업을 끝까지 수행했는가»이고 부분 완주는 `OK (부분: …)` 이다.
🔴 **조용한 전환이 아니다**: 리포트 제목과 STATUS 에 «판정 미수행»이 그대로 남고 프로바이더 오류
원문도 그대로 싣는다.

## 🔴 헤르메스 판정 층은 종결됐다 (2026-09-13 JJ 판정 · `--no-judge`)

시범 2주를 넘기도록 **본 성공지표가 한 번도 측정되지 않았다**(14회차 전부 「JJ 기입 ___」 공란).
판정 자료는 `reports\2026-09-13_hermes-trial.md` 이고, 남긴 것은 **결정적 감지기**다 — 폴링
120/120 · 모델 호출 0 · 비용 0. `--no-judge` 면 모델을 아예 부르지 않고 결정적 후보로 알림을 쓰며
**STATUS 는 «부분» 이 아니라 `OK`** 다: 판정 층이 «실패한» 것이 아니라 «없어진» 것이라, 매 회차
부분 완주로 적으면 그 표시가 진짜 부분 완주를 가린다(정관 §0 «거짓 경보가 감시를 무디게 한다»).

종료 코드: 0 = 리포트·알림을 다 썼다(판정 수행 여부는 STATUS 문자열이 말한다) · 1 = 감지 데이터가
없어 알림을 낼 수 없다(그때는 정말 실패다).
"""
import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import event_watch as ew          # candidate()·evidence() 정본 — 두 벌 두지 않는다


def det_alerts(data, date):
    """결정적 후보로 만든 알림 줄. 헤르메스 출력과 **같은 꼴**이라 뒷단이 갈리지 않는다."""
    out = []
    for rec in data.get("items", []):
        kind = ew.candidate(rec)
        if not kind:
            continue
        out.append("트리거명: %s %s | 구분: %s | 근거 URL: %s | 확인일: %s | 근거 줄: %s"
                   % (rec.get("id"), rec.get("name"), kind, rec.get("url"), date,
                      ew.evidence(rec) or "(근거 줄 없음)"))
    return out


def write_alerts(path, date, lines):
    io.open(path, "w", encoding="utf-8").write(
        "# 알림 %s (%d건)\n\n%s\n" % (date, len(lines), "\n".join("- " + x for x in lines)))


# ── 역검증 (§0) ─────────────────────────────────────────────────────────────
# **케이스를 분리한다** — «후보를 알림으로 내는가» 와 «침묵 편입을 잡는가» 는 다른 축이라
# 한 입력에서 같이 걸리면 어느 쪽이 일했는지 증명되지 않는다.

_ITEMS = [
    {"id": "E1", "name": "조건형", "url": "http://a", "kind": "cond", "status": "fetched",
     "cond_hits": ["Seedance 2.5 출시"], "cond_verdict": "기 발생"},
    {"id": "E3", "name": "신규형", "url": "http://b", "kind": "new", "status": "fetched",
     "new_lines": ["새 줄 하나"]},
    {"id": "E6", "name": "조용한 신규형", "url": "http://c", "kind": "new", "status": "fetched",
     "new_lines": []},
    {"id": "E8", "name": "못 연 곳", "url": "http://d", "kind": "new", "status": "blocked",
     "new_lines": ["열지도 못했는데 새 줄"]},
]


def _run(td, out_text, usage, items=None, extra=()):
    """합성 입력으로 `main()` 을 한 번 돌리고 `(코드, 리포트, 알림)` 을 돌려준다."""
    import subprocess
    date = "2026-09-12"
    js = os.path.join(td, date + ".json")
    json.dump({"date": date, "baseline_first_run": False,
               "items": items if items is not None else _ITEMS},
              io.open(js, "w", encoding="utf-8"), ensure_ascii=False)
    outp = os.path.join(td, "out.txt")
    io.open(outp, "w", encoding="utf-8").write(out_text)
    up = os.path.join(td, "usage.json")
    json.dump(usage, io.open(up, "w", encoding="utf-8"))
    rp, al = os.path.join(td, "r.md"), os.path.join(td, "a.md")
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--date", date,
                        "--state", td, "--out", outp, "--usage", up,
                        "--report", rp, "--alerts", al] + list(extra),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    rd = io.open(rp, encoding="utf-8").read() if os.path.exists(rp) else ""
    ad = io.open(al, encoding="utf-8").read() if os.path.exists(al) else ""
    return p.returncode, (p.stdout or "").strip(), rd, ad


_OK_USAGE = {"model": "nemotron-3.5-lightning-free", "provider": "opencode-free", "completed": True}
_BAD_USAGE = {"failed": True}
#: 헤르메스가 정상으로 판정한 회차의 출력. E1·E3 둘 다 알림에 있다.
_JUDGED = ("판정 2건\n- E1 조건형 — 성립\n- E3 신규형 — 성립\n"
           "알림 2건\n- 트리거명: E1 조건형 | 구분: 기 발생 | 근거 URL: http://a\n"
           "- 트리거명: E3 신규형 | 구분: 신규 | 근거 URL: http://b\n")
#: 같은 회차인데 **E3 알림만 빠진** 출력 — 침묵 편입이다.
_SILENT = ("판정 2건\n- E1 조건형 — 성립\n- E3 신규형 — 성립\n"
           "알림 1건\n- 트리거명: E1 조건형 | 구분: 기 발생 | 근거 URL: http://a\n")


def self_test():
    import tempfile
    res = []
    with tempfile.TemporaryDirectory(prefix="ewr_") as td:
        # ① 프로바이더가 죽어도 알림이 나간다 (후보 2건: E1·E3)
        code, so, rd, ad = _run(td, "HTTP 400: provider dead", _BAD_USAGE)
        res.append(("프로바이더 실패에도 알림이 나간다",
                    code == 0 and "alerts=2" in so and "E1" in ad and "E3" in ad))
        # ② 그리고 그것을 «판정 수행» 인 척하지 않는다
        res.append(("판정 미수행이 STATUS 에 남는다",
                    "부분: 헤르메스 판정 문안 없음" in rd and "판정 미수행" in rd))
        # ③ 못 연 감시처는 후보가 아니다 (E8 은 새 줄이 있어도 blocked)
        res.append(("못 연 감시처는 알림에 안 넣는다", "E8" not in ad))
        # ④ 새 줄이 없는 신규형도 후보가 아니다 (헛돎 점검 — 전부 알리면 ①도 참이 된다)
        res.append(("조용한 감시처는 알림에 안 넣는다", "E6" not in ad))
    with tempfile.TemporaryDirectory(prefix="ewr_") as td:
        # ⑤ 정상 회차에서 침묵 편입이 없으면 «0건»
        code, so, rd, ad = _run(td, _JUDGED, _OK_USAGE)
        res.append(("정상 회차는 침묵 편입 0건", code == 0 and "알림 누락 0건" in rd))
    with tempfile.TemporaryDirectory(prefix="ewr_") as td:
        # ⑥ **신규형** 알림이 빠지면 잡는다 — 종전 검사는 이 유형을 아예 안 봤다
        code, so, rd, ad = _run(td, _SILENT, _OK_USAGE)
        res.append(("신규형 침묵 편입을 잡는다", "알림 누락 E3" in rd))
    with tempfile.TemporaryDirectory(prefix="ewr_") as td:
        # ⑦ 종결 모드 — 모델 없이도 알림이 나가고, 그것을 «부분 완주» 로 적지 않는다.
        #    (out·usage 를 정상값으로 줘도 «판정» 절이 생기면 안 된다 — 끄는 것이 실제로 끄는가)
        code, so, rd, ad = _run(td, _JUDGED, _OK_USAGE, extra=["--no-judge"])
        res.append(("종결 모드에서도 알림은 나간다",
                    code == 0 and "no-judge, alerts=2" in so and "E1" in ad and "E3" in ad))
        res.append(("종결은 «부분 완주» 가 아니다",
                    rd.rstrip().endswith("STATUS: OK") and "부분" not in rd and "헤르메스 출력" not in rd))
        # ⑧ 헛돎 점검 — 종결 모드라고 «전부 알리는» 것은 아니다
        res.append(("종결 모드도 조용한 곳·못 연 곳은 안 알린다", "E6" not in ad and "E8" not in ad))
    with tempfile.TemporaryDirectory(prefix="ewr_") as td:
        # ⑨ 감지 데이터가 없으면 그때는 진짜 실패다
        io.open(os.path.join(td, "out.txt"), "w", encoding="utf-8").write("")
        import subprocess
        p = subprocess.run([sys.executable, os.path.abspath(__file__), "--date", "2026-09-12",
                            "--state", td, "--out", os.path.join(td, "out.txt"),
                            "--usage", os.path.join(td, "u.json"),
                            "--report", os.path.join(td, "r.md"),
                            "--alerts", os.path.join(td, "a.md")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        res.append(("감지 데이터가 없으면 FAIL",
                    p.returncode == 1 and "data-missing" in (p.stdout or "")))
    fails = 0
    for name, ok in res:
        fails += not ok
        print(("ok   " if ok else "FAIL ") + name)
    print("STATUS: %s" % ("OK" if not fails else "FAIL %d" % fails))
    return 1 if fails else 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", default="", help="hermes stdout 을 담은 UTF-8 파일 (종결 모드에서는 없다)")
    ap.add_argument("--usage", default="")
    ap.add_argument("--report", required=True)
    ap.add_argument("--alerts", required=True)
    ap.add_argument("--pin", default="nemotron-3.5-lightning-free")
    ap.add_argument("--profile", default="sagun")
    ap.add_argument("--hermes-exit", type=int, default=0)
    ap.add_argument("--no-judge", action="store_true",
                    help="헤르메스 판정 층 종결 — 모델을 부르지 않는다 (2026-09-13)")
    a = ap.parse_args()

    ended = a.no_judge
    out = io.open(a.out, encoding="utf-8", errors="replace").read().strip() if (
        not ended and a.out and os.path.exists(a.out)) else ""
    usage = {}
    if not ended and a.usage and os.path.exists(a.usage):
        try:
            usage = json.load(io.open(a.usage, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            usage = {"parse_error": str(e)}
    model = usage.get("model") or ""
    provider = usage.get("provider") or ""
    failed = bool(usage.get("failed")) or not usage.get("completed")
    pin_ok = bool(model) and model.startswith(a.pin)
    performed = (not ended) and a.hermes_exit == 0 and not failed and pin_ok

    js = os.path.join(a.state, a.date + ".json")
    if not os.path.exists(js):
        # 감지 데이터가 없으면 알림을 낼 근거가 없다 — 이때가 진짜 실패다.
        io.open(a.report, "w", encoding="utf-8").write(
            "# 사건형 트리거 감시 — %s\n\n감지 데이터가 없다: `%s`\n\nSTATUS: FAIL data-missing\n"
            % (a.date, js))
        print("STATUS: FAIL data-missing")
        return 1
    data = json.load(io.open(js, encoding="utf-8"))
    blocked = [i["id"] for i in data.get("items", []) if i.get("status") == "blocked"]
    cond_hits = [(i["id"], len(i.get("cond_hits", []))) for i in data.get("items", []) if i.get("cond_hits")]

    first = ("- **헤르메스 판정 층 종결 (2026-09-13 JJ 판정)** — 모델 호출 0 · 비용 0"
             if ended else
             "- **모델 pin: %s** (provider %s · in %s · out %s)" % (
                 model or "(없음 — FAIL)", provider or "?", usage.get("input_tokens"), usage.get("output_tokens")))
    second = ("- 감지·알림은 `scripts/event_watch.py`(결정적) 하나가 낸다 · 입력 = 감시 목록의 공개 정보만"
              if ended else
              "- 프로필 `%s` · 메모리 on(베이스라인) · 입력 = 감시 목록의 공개 정보만 · 감지는 `scripts/event_watch.py`(결정적)" % a.profile)
    head = ["# 사건형 트리거 감시 — %s" % a.date, "",
            first, second,
            "- 감시 데이터: `%s` · 감시처 %d건 (열기 실패 %d: %s) · 조건 문자열 적중: %s" % (
                js, len(data.get("items", [])), len(blocked), ", ".join(blocked) or "없음",
                ", ".join("%s×%d" % (i, n) for i, n in cond_hits) or "없음"),
            ""]
    if data.get("baseline_first_run"):
        head.append("- ⚠️ 첫 실행 — «신규 항목» 유형은 베이스라인 생성. 조건 문자열 적중이 있으면 **이미 발생한 사건일 수 있다**(미탐 후보 — JJ 확인).")
        head.append("")

    if ended:
        det = det_alerts(data, a.date)
        write_alerts(a.alerts, a.date, det)
        body = head + ["## 판정 층 없음 — 시범 종결 (2026-09-13)", "",
                       "헤르메스 판정 층은 시범 2주를 넘기도록 **본 성공지표가 측정되지 않아** JJ 판정으로 "
                       "종결했다(자료 `reports\\2026-09-13_hermes-trial.md`). 감지·알림은 결정적 코드가 그대로 낸다 "
                       "— 폴링 성공률은 시범 내내 120/120 이었다.",
                       "",
                       "- 알림 **%d건** → `%s`" % (len(det), a.alerts),
                       ""] + ["  - " + x for x in det] + [
                       "", "STATUS: OK"]
        io.open(a.report, "w", encoding="utf-8").write("\n".join(body) + "\n")
        # ASCII only - 래퍼가 이 줄을 로그에 옮긴다 (PS 5.1 코드페이지)
        print("STATUS: OK (no-judge, alerts=%d)" % len(det))
        return 0

    if not performed:
        why = ("hermes exit %d" % a.hermes_exit) if a.hermes_exit != 0 else (
            "모델 %r ≠ pin %r" % (model, a.pin) if not pin_ok else "usage failed=%s completed=%s" % (usage.get("failed"), usage.get("completed")))
        det = det_alerts(data, a.date)
        write_alerts(a.alerts, a.date, det)
        body = head + ["## 판정 미수행 — %s" % why, "",
                       "프로바이더 실패 또는 모델명 변경 감지. **조용한 전환 금지** — 이 회차의 «판정 문안»은 미수행이다.",
                       "",
                       "🔴 **알림은 나갔다 — 감지는 결정적 코드가 끝냈다.** 모델이 하던 일은 문안 정리이고, "
                       "그것이 없다고 알림을 버리면 데이터가 있는데도 사건을 놓친다(2026-09-08~12 닷새 실측).",
                       "",
                       "- 결정적 후보 알림 **%d건** → `%s`" % (len(det), a.alerts),
                       ""] + ["  - " + x for x in det] + [
                       "", "```", out[-1500:], "```", "",
                       "STATUS: OK (부분: 헤르메스 판정 문안 없음 — %s · 알림 %d건은 결정적 후보로 냈다)"
                       % (why, len(det))]
        io.open(a.report, "w", encoding="utf-8").write("\n".join(body) + "\n")
        # ASCII only - the wrapper copies this line into its log (PS 5.1 codepage).
        print("STATUS: OK (partial: hermes-judgement-missing, alerts=%d)" % len(det))
        return 0

    judge = re.findall(r"^\s*-\s*(E\d+.*)$", out, re.M)
    alerts = [l.strip("- ").strip() for l in out.splitlines() if "트리거명:" in l]
    hit = [j for j in judge if re.search(r"(?<!미)성립", j)]
    pre = [a_ for a_ in alerts if "기 발생" in a_]
    # 역검증 자리 — 스크립트가 «기 발생/신규» 판정 후보를 붙였는데 헤르메스가 알림을 안 냈으면 그 사실을 적는다(침묵 편입 감지)
    # 2026-09-12: `candidate()` 로 바꿨다 — 종전 `cond_verdict` 직접 조회는 «조건 문자열»
    # 유형만 봐서 감시처 8곳 중 6곳(«신규 항목» 유형)을 한 번도 검사하지 않았다.
    expected = [i["id"] for i in data.get("items", []) if ew.candidate(i)]
    missing_alert = [e for e in expected if not any(a_.startswith("트리거명: " + e) or (" " + e + " ") in a_ or a_.find(e) >= 0 for a_ in alerts)]
    unk = [j for j in judge if "확인 불가" in j]
    write_alerts(a.alerts, a.date, alerts)
    body = head + ["## 헤르메스 출력 (원문 그대로)", "", "```", out, "```", "",
                   "## 관찰 기록 (사흘 시범)", "",
                   "- 판정 %d건 · 성립 %d · 확인 불가 %d · 알림 %d건 (기 발생 %d · 신규 %d)" % (len(judge), len(hit), len(unk), len(alerts), len(pre), len(alerts) - len(pre)),
                   "- 침묵 편입 검사: 스크립트 판정 후보(기 발생/신규) %s → 알림 누락 %s" % (", ".join(expected) or "없음", ", ".join(missing_alert) or "0건"),
                   "- 조건 문자열 적중인데 판정이 미성립인 항목: %s" % (", ".join(i for i, n in cond_hits if not any(j.startswith(i) and re.search(r"(?<!미)성립", j) for j in judge)) or "없음") + " — 미탐 후보(JJ 확인)",
                   "- 오탐/미탐: JJ 기입 ___",
                   "- keep rate 근거: 호출 1 · 유효 산출 %d · 착수 수는 JJ 기입: ___" % (1 if judge else 0),
                   "", "알림 파일: `%s`" % a.alerts, "",
                   "STATUS: OK" if judge else "STATUS: OK (부분: 판정 줄 0건 — 출력 형식 확인 필요)"]
    io.open(a.report, "w", encoding="utf-8").write("\n".join(body) + "\n")
    print(body[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
