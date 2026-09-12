# -*- coding: utf-8 -*-
r"""어디 있나 — 게이트 축·검사기·표식을 한 번에 찾는다 (A등급 · read-only).

## 왜

2026-09-12 턴 감사 실측: Bash **7,353회 중 51%가 «찾기»** 다(파일 들여다보기 1,827 ·
grep 1,775). 기준선 47% 에서 오히려 올랐다. 세션이 매번 같은 것을 다시 찾는다 —
«`[7-3]` 이 어디서 도나» · «이 검사기는 누가 부르나» · «그 상수는 어느 파일인가».

🔴 **색인 문서를 하나 더 만들지 않는다.** `docs\selftest-coverage.md` 가 그 실패를
이미 보여 준다 — 2026-08-27 에 손으로 적은 행 번호(`skill_drift_audit.py 258·391행`)가
그날 이후 코드가 움직이면서 **틀린 값이 됐다.** 정관 §0: **실물이 정본이고 문서는 조회
결과다.** 그래서 이 자는 문서를 쓰지 않고 **부를 때마다 실물을 읽는다.**

## 쓰는 법

    py scripts\where.py 7-3          # 게이트 축이 정의·실행되는 자리
    py scripts\where.py CARD_BANNED  # 상수·함수·클래스가 정의된 자리
    py scripts\where.py --checks     # 자체 검사 전수 + **부르는 자리** (있는데 안 도는 검사)
    py scripts\where.py --axes       # 축 전수 (게이트별)
    py scripts\where.py --self-test

## 🔴 못 잡는 것 (§0 4층 ④)

  - **워크숍 편 폴더**(`02_제작중`)는 안 본다 — gitignore 이고 편마다 사라진다.
    라이브 스킬이 편이 실제로 읽는 정본이라 그쪽을 본다(§4 `build_epNN.py` sys.path).
  - **«무엇을 재는 축인가»는 그 줄의 글자를 그대로 옮길 뿐** 뜻을 읽지 않는다.
  - 검사가 **pre-commit 에 등록됐는지**는 훅 파일의 문자열로 본다 — 등록됐는데 그 회차에
    안 도는 경우(스테이지 목록 밖)는 «등록됨» 으로 나온다.
"""
import io
import os
import re
import sys

HQ = os.environ.get("JJ_HQ", r"C:\Users\ojaej\jj-company")
SKILL = os.environ.get("TOMANGCHI_LIVE_SKILL",
                       os.path.expanduser(os.path.join("~", ".claude", "skills", "tomangchi")))
#: (이름, 뿌리, 하위 폴더). 하위가 비면 그 뿌리의 파일만.
ROOTS = [
    ("본사", HQ, ["scripts", "departments", "docs", os.path.join(".claude", "hooks"), ""]),
    ("스킬", SKILL, [""]),
]
EXT = (".py", ".md", ".ps1")
SKIP_DIR = {"logs", "reports", ".git", "__pycache__", "node_modules"}
#: 게이트 축 꼴 — `[7-3]` · `[IMG-2]` · `[AD-1]` · `[R]`
AXIS = re.compile(r"\[([A-Z0-9][A-Z0-9가-힣-]{0,11})\]")
#: 축 전수용 — **문자열 맨 앞**의 축만. 게이트는 판정 줄을 늘 `[축] 설명` 으로 연다.
#: 앵커가 없으면 f-문자열의 `{size[0]}` 이 축 «[0]» 으로 잡힌다(2026-09-13 실측).
AXIS_HEAD = re.compile(r"^\s*\[([A-Z0-9][A-Z0-9가-힣-]{0,11})\]")
#: 그 줄이 «축이 실제로 도는 자리»로 보이는가 (판정 함수를 부른다)
RUNS = re.compile(r"\b(print|ok|fail|skip|warn|info)\s*\(")
#: 문자열 리터럴 — 축은 그 안에만 산다
QUOTED = re.compile(r"""[\"']([^\"']*)[\"']""")
DEF = re.compile(r"^\s*(?:def|class)\s+(\w+)|^\s*([A-Z_][A-Z0-9_]{2,})\s*=")
SELFTEST = re.compile(r"^\s*def\s+(self_test|_selftest|selftest|_self_test)\s*\(")
#: 그 호출이 «사람이 깃발을 줘야» 도는 자리인가 — argv 분기 안이면 자동이 아니다.
MANUAL = re.compile(r"--self[-_]?test|sys\.argv|args?\.self_test|ap\.add_argument")


def walk():
    """(라벨, 절대경로, 레포상대경로) 를 흘린다."""
    for name, root, subs in ROOTS:
        for sub in subs:
            base = os.path.join(root, sub) if sub else root
            if not os.path.isdir(base):
                continue
            for dirpath, dirnames, files in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIR]
                if not sub and dirpath != base:
                    continue                      # 뿌리 직속 파일만 (하위는 자기 차례에)
                for f in sorted(files):
                    if f.endswith(EXT):
                        p = os.path.join(dirpath, f)
                        yield name, p, os.path.relpath(p, root)


def lines(path):
    try:
        return io.open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return []


def find_axis(q):
    """축 하나가 나오는 모든 자리. 실행 자리를 앞에 둔다."""
    tag = "[%s]" % q.strip("[]").upper()
    runs, docs = [], []
    for name, p, rel in walk():
        for i, ln in enumerate(lines(p), 1):
            if tag in ln.upper():
                row = (name, rel, i, ln.strip()[:150])
                (runs if RUNS.search(ln) else docs).append(row)
    return runs, docs


def find_symbol(q):
    """정의 자리(def·class·상수)와 그냥 나오는 자리를 가른다."""
    defs, uses = [], []
    for name, p, rel in walk():
        for i, ln in enumerate(lines(p), 1):
            if q not in ln:
                continue
            m = DEF.match(ln)
            row = (name, rel, i, ln.strip()[:150])
            if m and q in (m.group(1) or m.group(2) or ""):
                defs.append(row)
            else:
                uses.append(row)
    return defs, uses


def enclosing_def(body, i):
    """`i` 번째 줄(1-based)을 감싸는 `def` 이름. 모듈 최상위면 `"모듈"`."""
    for j in range(i - 1, -1, -1):
        m = re.match(r"^def\s+(\w+)", body[j])
        if m:
            return m.group(1)
    return "모듈"


def checks():
    r"""[(라벨, 경로, 행, 함수명, 어떻게 도나, 자동인가)] — «있는데 안 도는 검사» 를 실물로.

    🔴 **`--self-test` argv 분기는 «도는 자리»가 아니다.** 사람이 깃발을 줘야 도는 것은
    수동이고, 이 자가 찾으려는 것이 바로 «손으로 안 돌리면 안 도는 검사»다
    (`scenes.self_test` 열흘 잠복 — `docs\selftest-coverage.md`).
    """
    # 🔴 주석 줄은 뺀다 — 훅에 «이 검사는 아직 등록 안 했다» 고 적어 두면 그 문장이
    #    등록으로 읽힌다(2026-09-13 실측: `surface_check` 가 그렇게 «자동» 이 됐다).
    hook = "\n".join(l for l in lines(os.path.join(HQ, "scripts", "githooks", "pre-commit"))
                      if not l.lstrip().startswith("#"))
    out = []
    for name, p, rel in walk():
        if not p.endswith(".py"):
            continue
        body = lines(p)
        for i, ln in enumerate(body, 1):
            m = SELFTEST.match(ln)
            if not m:
                continue
            mod = os.path.basename(p)[:-3]
            how, auto = [], False
            if re.search(r"\b%s\b" % re.escape(mod), hook):
                how.append("pre-commit")
                auto = True
            code, manual = [], 0
            for j, l2 in enumerate(body, 1):
                if j == i or not re.search(r"\b%s\s*\(" % m.group(1), l2):
                    continue
                near = "\n".join(body[max(0, j - 3):j])
                if MANUAL.search(l2) or MANUAL.search(near):
                    manual += 1
                else:
                    code.append(enclosing_def(body, j))
            if code:
                how.append("코드 " + "·".join(sorted(set(code))))
                auto = True
            if manual:
                how.append("수동 깃발 %d" % manual)
            out.append((name, rel, i, m.group(1),
                        " · ".join(how) or "호출 0", auto))
    return out


def axes():
    """{축: [(라벨, 상대경로, 행, 줄)]} — 실행 자리만 모은다(문서 줄은 뺀다)."""
    found = {}
    for name, p, rel in walk():
        if not p.endswith(".py"):
            continue
        for i, ln in enumerate(lines(p), 1):
            if not RUNS.search(ln):
                continue
            # 축은 **문자열 맨 앞**에 있다 — `[축] 설명` 이 게이트 판정 줄의 꼴이다.
            for lit in QUOTED.findall(ln):
                m = AXIS_HEAD.match(lit)
                if m:
                    found.setdefault(m.group(1), []).append((name, rel, i, ln.strip()[:110]))
    return found


def show(title, rows, limit=12):
    print("\n== %s (%d) ==" % (title, len(rows)))
    for name, rel, i, ln in rows[:limit]:
        print("  [%s] %s:%d" % (name, rel, i))
        print("        " + ln)
    if len(rows) > limit:
        print("  … 그 밖 %d줄" % (len(rows) - limit))


# ── 역검증 (§0) ─────────────────────────────────────────────────────────────
def self_test():
    import tempfile
    global ROOTS
    saved = ROOTS
    res = []
    with tempfile.TemporaryDirectory(prefix="where_") as td:
        os.makedirs(os.path.join(td, "scripts"))
        io.open(os.path.join(td, "scripts", "fake_gate.py"), "w", encoding="utf-8").write(
            '# -*- coding: utf-8 -*-\n'
            '#: 문서 줄 — [9-9] 가짜 축 설명\n'
            'THING_BANNED = ["x"]\n'
            'def self_test():\n'
            '    return 0\n'
            'def run():\n'
            '    print("[9-9] 가짜 축 — 실행 자리")\n'
            '    print("[8-8] 다른 축")\n'
            '    print(THING_BANNED[0])\n'
            'if "--self-test" in sys.argv:\n'
            '    self_test()\n')
        # 🔴 argv 분기만 있는 파일이 «자동» 으로 읽히면 이 자는 아무것도 못 잡는다.
        #    실제로 첫 판이 그랬다 — 전 파일이 «부르는 자리 있음» 으로 통과했다.
        io.open(os.path.join(td, "scripts", "fake_auto.py"), "w", encoding="utf-8").write(
            '# -*- coding: utf-8 -*-\n'
            'def self_test():\n'
            '    return 0\n'
            'def run():\n'
            '    self_test()\n')
        ROOTS = [("시험", td, ["scripts"])]
        runs, docs = find_axis("9-9")
        # ① 실행 자리와 문서 줄을 가른다
        res.append(("축의 실행 자리를 찾는다", len(runs) == 1 and "실행 자리" in runs[0][3]))
        res.append(("문서 줄은 따로 센다", len(docs) == 1 and "설명" in docs[0][3]))
        # ② 없는 축은 0건 (헛돎 점검 — 전부 돌려주는 자가 아닌가)
        res.append(("없는 축은 0건", find_axis("7-7") == ([], [])))
        # ③ 상수 정의 자리를 가른다
        defs, uses = find_symbol("THING_BANNED")
        res.append(("상수 정의 자리를 찾는다", len(defs) == 1 and defs[0][2] == 3))
        # ④ 수동 깃발만 있는 검사를 «자동 아님» 으로 적는다 — 이 자의 존재 이유다
        c = {r[1]: r for r in checks()}
        gate = c[os.path.join("scripts", "fake_gate.py")]
        res.append(("argv 분기만 있으면 «자동» 이 아니다",
                    gate[5] is False and "수동 깃발" in gate[4]))
        # ⑤ 반대쪽 — 코드에서 부르면 «자동» 이다 (헛돎 점검: 전부 🔴 로 찍는 자가 아닌가)
        auto = c[os.path.join("scripts", "fake_auto.py")]
        res.append(("코드에서 부르면 «자동»", auto[5] is True and "코드 run" in auto[4]))
        # ⑤-1 훅 «주석» 에 이름만 적힌 것은 등록이 아니다
        global HQ
        _hq, HQ = HQ, td
        os.makedirs(os.path.join(td, "scripts", "githooks"))
        io.open(os.path.join(td, "scripts", "githooks", "pre-commit"), "w",
                encoding="utf-8").write("# fake_gate.py is not registered yet\n"
                                        "run_check \"x\" py scripts/fake_auto.py --self-test\n")
        c2 = {r[1]: r for r in checks()}
        res.append(("훅 주석은 등록이 아니다",
                    c2[os.path.join("scripts", "fake_gate.py")][5] is False
                    and "pre-commit" in c2[os.path.join("scripts", "fake_auto.py")][4]))
        HQ = _hq
        # ⑥ 축 전수는 실행 자리만 (문서 줄이 섞이면 «어디서 도나» 가 흐려진다)
        a = axes()
        # 색인(`THING_BANNED[0]`)이 축 «[0]» 으로 섞이면 `--axes` 가 쓰레기로 찬다
        res.append(("축 전수는 실행 자리만 · 색인은 안 센다",
                    sorted(a) == ["8-8", "9-9"] and len(a["9-9"]) == 1))
    ROOTS = saved
    # ⑥ 실물에서도 값을 담는가 — 빈 결과를 «통과» 로 읽지 않는다(§0)
    res.append(("실물에서 축이 잡힌다", len(axes()) >= 10))
    fails = 0
    for name, ok_ in res:
        fails += not ok_
        print(("ok   " if ok_ else "FAIL ") + name)
    print("STATUS: %s" % ("OK" if not fails else "FAIL %d" % fails))
    return 1 if fails else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    if "--checks" in argv:
        rows = checks()
        blind = [r for r in rows if not r[5]]
        print("자체 검사 %d개 · 🔴 자동으로 도는 자리가 없는 것 %d개 (손으로 안 돌리면 안 돈다)"
              % (len(rows), len(blind)))
        for name, rel, i, fn, how, auto in sorted(rows, key=lambda r: (r[5], r[1])):
            print("  %s %-4s %-42s:%-5d %-11s %s"
                  % ("  " if auto else "🔴", name, rel, i, fn, how))
        return 0
    if "--axes" in argv:
        found = axes()
        print("게이트 축 %d개 (실행 자리 기준)" % len(found))
        for a in sorted(found):
            name, rel, i, ln = found[a][0]
            print("  [%-7s] %s:%d  %s" % (a, rel, i, ln[:70]))
        return 0
    q = [x for x in argv if not x.startswith("-")]
    if not q:
        print(__doc__.split("## 쓰는 법")[1].split("## 🔴")[0].strip())
        return 2
    q = q[0]
    if re.fullmatch(r"\[?[A-Z0-9][A-Z0-9가-힣-]{0,11}\]?", q.upper()):
        runs, docs = find_axis(q)
        if runs or docs:
            show("«%s» 가 도는 자리" % q, runs)
            show("«%s» 를 적은 자리" % q, docs, limit=8)
            return 0
    defs, uses = find_symbol(q)
    show("«%s» 정의" % q, defs)
    show("«%s» 쓰이는 자리" % q, uses, limit=10)
    return 0 if (defs or uses) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
