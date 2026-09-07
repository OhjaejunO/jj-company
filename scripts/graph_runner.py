# -*- coding: utf-8 -*-
r"""graph_runner.py — 그래프는 데이터, 노드마다 체크포인트, 사람 대기는 노드. stdlib 만.

브리프 `reports\2026-09-06_graph-engineering-brief.md` §2 의 그 러너다. 상한은 이 파일 크기다 —
플러그인·클래스 계층을 붙이지 않는다(§3 «과추상화»).

    graph = {"start": "a", "nodes": {"a": fa, "b": fb}, "edges": {"a": [(None, "b")], "b": [(None, "END")]}}
    run(graph, ckpt=Path("logs/x.ckpt.json"), state={...})

- 노드: `state(dict) -> 갱신분(dict)`. `Wait` 를 던지면 «사람 차례» — 저장하고 종료코드 3(`STATUS: WAIT`).
- 엣지: `(조건 또는 None, 다음)` 목록. 첫 번째로 참인 것을 탄다. 조건은 **여기에만** 적는다.
- 체크포인트: 노드 하나 끝날 때마다 `at`(다음)·`state`·`done` 을 디스크에. 다음 실행은 `at` 부터.
- 같은 명령을 다시 부르면 재개. `END` 면 «already done» 으로 재실행을 막는다(`--reset` 으로 푼다).

    py scripts\graph_runner.py --self-test
"""
import json
import sys
import tempfile
from pathlib import Path


class Wait(Exception):
    """게이트가 던진다 — 실패가 아니라 «사람 차례»."""


def load(ckpt):
    return json.loads(ckpt.read_text("utf-8")) if ckpt.exists() else None


def save(ckpt, c):
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    ckpt.write_text(json.dumps(c, ensure_ascii=False, indent=1), "utf-8")


def dump(graph):
    """문서에 표를 두지 않는다 — 실물을 찍는다(정관 §0 «실물이 정본»)."""
    out = [f"start: {graph['start']}"]
    for n, edges in graph["edges"].items():
        arrows = " | ".join(("*" if c is None else "if") + " -> " + nx for c, nx in edges)
        out.append(f"  {n:<10} {arrows}")
    return "\n".join(out)


def run(graph, ckpt, state=None, retries=1, log=print):
    c = load(ckpt) or {"at": graph["start"], "state": dict(state or {}), "done": []}
    at = c["at"]
    if at == "END":
        log("STATUS: OK (already done; --reset 으로 다시)")
        return 0
    while at != "END":
        fn = graph["nodes"][at]
        for n in range(retries + 1):
            try:
                upd = fn(c["state"]) or {}
                break
            except Wait as w:
                c["at"] = at
                save(ckpt, c)
                log(f"STATUS: WAIT {at}: {w}")
                return 3
            except Exception as e:  # noqa: BLE001 — 노드 실패는 이름 붙여 멈춘다(§0 조용한 실패 금지)
                if n == retries:
                    c["at"] = at
                    c["state"]["_error"] = f"{at}: {e}"
                    save(ckpt, c)
                    log(f"STATUS: FAIL {at}: {e}")
                    return 1
                log(f"  retry {at} ({n + 1}/{retries}): {e}")
        c["state"].update(upd)
        c["done"].append(at)
        at = next(nx for cond, nx in graph["edges"][at] if cond is None or cond(c["state"]))
        c["at"] = at
        save(ckpt, c)  # 여기서 죽어도 다음 실행은 이 노드부터
        log(f"  done {c['done'][-1]} -> {at}")
    log("STATUS: OK")
    return 0


def _self_test():
    calls = []
    gate_open = {"v": False}

    def fetch(s): calls.append("fetch"); return {"items": [1, 2]}
    def gate(s):
        calls.append("gate")
        if not gate_open["v"]:
            raise Wait("승인 없음")
        return {"ok": True}
    def publish(s): calls.append("publish"); return {"receipt": "r"}
    def boom(s): raise RuntimeError("터짐")

    g = {"start": "fetch", "nodes": {"fetch": fetch, "gate": gate, "publish": publish},
         "edges": {"fetch": [(lambda s: not s["items"], "END"), (None, "gate")],
                   "gate": [(None, "publish")], "publish": [(None, "END")]}}
    with tempfile.TemporaryDirectory() as d:
        ck = Path(d) / "t.ckpt.json"
        quiet = lambda *a: None  # noqa: E731
        assert run(g, ck, log=quiet) == 3 and load(ck)["at"] == "gate", "게이트에서 WAIT 로 서야 한다"
        gate_open["v"] = True
        assert run(g, ck, log=quiet) == 0 and calls == ["fetch", "gate", "gate", "publish"], calls
        assert run(g, ck, log=quiet) == 0 and calls[-1] == "publish", "END 뒤 재실행은 노드를 돌리면 안 된다"
        ck2 = Path(d) / "u.ckpt.json"
        g2 = {"start": "boom", "nodes": {"boom": boom}, "edges": {"boom": [(None, "END")]}}
        assert run(g2, ck2, log=quiet) == 1 and load(ck2)["state"]["_error"].startswith("boom:")
        g3 = {"start": "fetch", "nodes": {"fetch": lambda s: {"items": []}},
              "edges": {"fetch": [(lambda s: not s["items"], "END"), (None, "gate")]}}
        assert run(g3, Path(d) / "v.ckpt.json", log=quiet) == 0, "조건부 엣지 END"
    print("ok   WAIT 저장 · 재개 시 앞 노드 건너뜀 · END 재실행 차단 · 노드 예외 FAIL · 조건부 엣지")
    print("STATUS: OK")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--self-test" in sys.argv:
        _self_test()
        sys.exit(0)
    print(__doc__)
