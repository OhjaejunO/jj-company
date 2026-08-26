# -*- coding: utf-8 -*-
r"""사건형 트리거 감시 — 리포트·알림 작성 + pin 검사 (래퍼 `hermes-event-watch.ps1` 의 뒷단).

    py scripts\event_watch_report.py --date D --state DIR --out OUT_TXT --usage USAGE_JSON --report REPORT --alerts ALERTS
                                     [--pin nemotron-3.5-lightning-free] [--profile sagun] [--hermes-exit N]

왜 파이썬인가 — 래퍼(.ps1)는 ASCII 전용이다(PS 5.1 이 BOM 없는 UTF-8 을 ANSI 로 읽어 한글이 깨진다, 정관 §6).
리포트 문안은 한글이라 여기서 쓴다. 종료 코드: 0 = 판정 수행 · 1 = 프로바이더/모델 pin 실패(판정 미수행, 조용한 전환 금지).
"""
import argparse
import io
import json
import os
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True, help="hermes stdout 을 담은 UTF-8 파일")
    ap.add_argument("--usage", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--alerts", required=True)
    ap.add_argument("--pin", default="nemotron-3.5-lightning-free")
    ap.add_argument("--profile", default="sagun")
    ap.add_argument("--hermes-exit", type=int, default=0)
    a = ap.parse_args()

    out = io.open(a.out, encoding="utf-8", errors="replace").read().strip() if os.path.exists(a.out) else ""
    usage = {}
    if os.path.exists(a.usage):
        try:
            usage = json.load(io.open(a.usage, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            usage = {"parse_error": str(e)}
    model = usage.get("model") or ""
    provider = usage.get("provider") or ""
    failed = bool(usage.get("failed")) or not usage.get("completed")
    pin_ok = bool(model) and model.startswith(a.pin)
    performed = a.hermes_exit == 0 and not failed and pin_ok

    js = os.path.join(a.state, a.date + ".json")
    data = json.load(io.open(js, encoding="utf-8")) if os.path.exists(js) else {"items": []}
    blocked = [i["id"] for i in data.get("items", []) if i.get("status") == "blocked"]
    cond_hits = [(i["id"], len(i.get("cond_hits", []))) for i in data.get("items", []) if i.get("cond_hits")]

    head = ["# 사건형 트리거 감시 — %s" % a.date, "",
            "- **모델 pin: %s** (provider %s · in %s · out %s)" % (model or "(없음 — FAIL)", provider or "?", usage.get("input_tokens"), usage.get("output_tokens")),
            "- 프로필 `%s` · 메모리 on(베이스라인) · 입력 = 감시 목록의 공개 정보만 · 감지는 `scripts/event_watch.py`(결정적)" % a.profile,
            "- 감시 데이터: `%s` · 감시처 %d건 (열기 실패 %d: %s) · 조건 문자열 적중: %s" % (
                js, len(data.get("items", [])), len(blocked), ", ".join(blocked) or "없음",
                ", ".join("%s×%d" % (i, n) for i, n in cond_hits) or "없음"),
            ""]
    if data.get("baseline_first_run"):
        head.append("- ⚠️ 첫 실행 — «신규 항목» 유형은 베이스라인 생성. 조건 문자열 적중이 있으면 **이미 발생한 사건일 수 있다**(미탐 후보 — JJ 확인).")
        head.append("")

    if not performed:
        why = ("hermes exit %d" % a.hermes_exit) if a.hermes_exit != 0 else (
            "모델 %r ≠ pin %r" % (model, a.pin) if not pin_ok else "usage failed=%s completed=%s" % (usage.get("failed"), usage.get("completed")))
        body = head + ["## 판정 미수행 — %s" % why, "",
                       "프로바이더 실패 또는 모델명 변경 감지. **조용한 전환 금지** — 이 회차 판정은 «미수행». 감지 데이터(json)는 남아 있다. 플랜 B(Ollama)는 JJ 결정.",
                       "", "```", out[-1500:], "```", "", "STATUS: FAIL provider (판정 미수행 — %s)" % why]
        io.open(a.report, "w", encoding="utf-8").write("\n".join(body) + "\n")
        print("STATUS: FAIL provider")
        return 1

    judge = re.findall(r"^\s*-\s*(E\d+.*)$", out, re.M)
    alerts = [l.strip("- ").strip() for l in out.splitlines() if "트리거명:" in l]
    hit = [j for j in judge if re.search(r"(?<!미)성립", j)]
    unk = [j for j in judge if "확인 불가" in j]
    io.open(a.alerts, "w", encoding="utf-8").write("# 알림 %s (%d건)\n\n%s\n" % (a.date, len(alerts), "\n".join("- " + x for x in alerts)))
    body = head + ["## 헤르메스 출력 (원문 그대로)", "", "```", out, "```", "",
                   "## 관찰 기록 (사흘 시범)", "",
                   "- 판정 %d건 · 성립 %d · 확인 불가 %d · 알림 %d건" % (len(judge), len(hit), len(unk), len(alerts)),
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
