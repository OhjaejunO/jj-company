# -*- coding: utf-8 -*-
r"""재유통 감사 — **발행됐는데 스레드가 안 나간 편**을 센다 (2026-09-12 신설 · JJ 지시).

    py scripts\redist_audit.py              목록을 내고 STATUS 를 찍는다
    py scripts\redist_audit.py --self-test  역검증

## 왜 이 자리가 필요한가

2026-09-12 에 JJ 가 「스레드 발행 안 된 거 얼마나 있어?」라고 물어서야 **ep44·ep46·ep53 셋**이
드러났다. 그때까지 **아무도 세지 않았다** — 영수증(`logs\publish-receipts\`)과 발행로그는 «나간
편»만 알고, «나갔어야 하는데 안 나간 편»은 어느 쪽에도 안 적힌다. 정관 §0 «조용히 실패하는 코드를
남기지 않는다» 의 한 겹 바깥이다: 실패한 것이 아니라 **아예 시작되지 않은 것**이라 로그조차 없다.

같은 계열이 이미 두 번 났다 — 2026-09-11 에 발행로그의 `-Threads` 행이 8편 통째로 빠져 있었고
(그건 «적히지 않은 것»이라 `publish_tail.py --redist` 로 메웠다), 이번은 «나가지 않은 것»이다.

## 재는 법

`01_발행완료` 의 편 중 **ep39 이상**(정관 §0 «적용은 ep39 부터 · ep35~38 소급 없음»)에 대해
셋 중 하나가 있어야 한다.

1. 유통팩 `reports\<날짜>_dist_<ep>.md` — `dist_transform.pack()` 은 게이트 FAIL 이 하나라도
   있으면 **파일을 안 쓰므로** 그 존재가 곧 «게이트를 통과했다» 이다.
2. 발행 영수증 `logs\publish-receipts\<ep>.jsonl` 에 `media_id` 를 가진 줄 — 실제로 나갔다.
3. **보류 선언** `departments\marketing\redist\<ep>.py` 의 `SKIP` — JJ 가 «안 낸다» 고 정한 편.
   사유를 같이 적는다. 🔴 보류는 **자동으로 생기지 않는다** — 사람이 적어야 한다.

🔴 **못 잡는 것 (§0 4층 ④)**: 유통팩이 있는데 **발행만 안 한** 편은 «했다» 로 읽는다 — 팩까지
   갔으면 나머지는 워커 한 번이라 병목이 아니고, 여기서 재려면 영수증과 팩의 짝을 맞춰야 하는데
   그 짝은 편마다 날짜가 달라 기계로 잇기 어렵다. 그 자리는 `publish_tail.py --redist` 몫이다.
"""
import io
import os
import re
import sys

#: 🔴 **산출물은 운영 서버에 있다.** `reports\`·`logs\` 는 커밋되지 않으므로(정관 §3)
#:    worktree 에서 이 파일을 돌리면 **한 건도 안 보여 전편이 «빠짐» 으로 읽힌다**
#:    — 2026-09-12 첫 실행에서 실제로 그렇게 나왔다(17편 전부). `naver_draft.py` 가
#:    HQ 를 못박아 두는 것과 같은 이유다.
HQ = r"C:\Users\ojaej\jj-company"
PUBLISHED = os.environ.get("TOMANGCHI_PUBLISHED") or \
    r"C:\Users\ojaej\orca\tomangchi-lab.github.io\workshop\01_발행완료"
REPORTS = os.path.join(HQ, "reports")
RECEIPTS = os.path.join(HQ, "logs", "publish-receipts")
#: 보류 선언만은 **이 파일 옆**에서 읽는다 — worktree 에서 고친 선언이 그 자리에서 먹어야 한다.
DECL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "departments", "marketing", "redist")
SINCE_EP = 39          # 정관 §0 — 재유통 적용은 ep39 부터


def episodes(published=None):
    """`01_발행완료` 의 편 번호 → 폴더 이름. ep 로 시작하지 않는 폴더는 편이 아니다."""
    out = {}
    for d in sorted(os.listdir(published or PUBLISHED)):
        m = re.match(r"^ep(\d+)_", d)
        if m:
            out.setdefault(int(m.group(1)), d)
    return out


def has_pack(ep, reports=None):
    d = reports or REPORTS
    if not os.path.isdir(d):
        return False
    return any(re.search(r"_dist_ep%d\.md$" % ep, f) for f in os.listdir(d))


def has_receipt(ep, receipts=None):
    p = os.path.join(receipts or RECEIPTS, "ep%d.jsonl" % ep)
    if not os.path.exists(p):
        return False
    # 🔴 «선점»(post.claim)은 나간 것이 아니다 — `media_id` 를 가진 줄만 센다(정관 §2 5번).
    return '"media_id"' in io.open(p, encoding="utf-8", errors="replace").read()


def skip_reason(ep, decl=None):
    p = os.path.join(decl or DECL, "ep%d.py" % ep)
    if not os.path.exists(p):
        return None
    m = re.search(r"^SKIP\s*=\s*(['\"])(.*?)\1", io.open(p, encoding="utf-8").read(), re.M)
    return m.group(2) if m else None


def audit(published=None, reports=None, receipts=None, decl=None):
    """(빠진 편, 보류 편) — 빠진 편은 `[(번호, 폴더)]`, 보류는 `[(번호, 사유)]`."""
    missing, skipped = [], []
    for n, name in sorted(episodes(published).items()):
        if n < SINCE_EP:
            continue
        why = skip_reason(n, decl)
        if why:
            skipped.append((n, why)); continue
        if has_pack(n, reports) or has_receipt(n, receipts):
            continue
        missing.append((n, name))
    return missing, skipped


def main():
    missing, skipped = audit()
    print("재유통 감사 — `01_발행완료` ep%d 이상" % SINCE_EP)
    for n, why in skipped:
        print("  보류 ep%-3d %s" % (n, why))
    for n, name in missing:
        print("  🔴 빠짐 ep%-3d %s" % (n, name))
    if missing:
        print("STATUS: FAIL 재유통 %d편 (%s)"
              % (len(missing), "·".join("ep%d" % n for n, _ in missing)))
        return 1
    print("STATUS: OK (보류 %d편)" % len(skipped))
    return 0


def _self_test():
    """역검증 — 빠진 편을 잡는가 · 세 자격이 각각 통과시키는가 · 보류는 사유가 있어야 하는가."""
    import shutil
    import tempfile
    t = tempfile.mkdtemp(prefix="redist_audit_")
    pub, rep, rec, dcl = (os.path.join(t, x) for x in ("pub", "rep", "rec", "dcl"))
    for d in (pub, rep, rec, dcl):
        os.makedirs(d)
    for name in ("ep38_옛편", "ep40_팩있음", "ep41_영수증있음", "ep42_보류", "ep43_빠짐"):
        os.makedirs(os.path.join(pub, name))
    io.open(os.path.join(rep, "2026-09-01_dist_ep40.md"), "w", encoding="utf-8").write("x")
    io.open(os.path.join(rec, "ep41.jsonl"), "w", encoding="utf-8").write('{"media_id": "1"}\n')
    io.open(os.path.join(dcl, "ep42.py"), "w", encoding="utf-8").write('SKIP = "지난 주간판이라 낸다"\n')
    # 🔴 선점만 있는 편은 «나갔다» 가 아니다 — 따로 둔다(다른 편이 같이 안 걸리게).
    os.makedirs(os.path.join(pub, "ep44_선점만"))
    io.open(os.path.join(rec, "ep44.jsonl"), "w", encoding="utf-8").write('{"kind": "post.claim"}\n')

    missing, skipped = audit(pub, rep, rec, dcl)
    got = [n for n, _ in missing]
    cases = [
        ("빠진 편을 잡는다 (ep43)", 43 in got),
        ("🔴 선점만 있는 편은 «나갔다» 가 아니다 (ep44)", 44 in got),
        ("유통팩이 있으면 통과 (ep40)", 40 not in got),
        ("영수증에 media_id 가 있으면 통과 (ep41)", 41 not in got),
        ("보류 선언이 있으면 통과하고 사유가 남는다 (ep42)",
         42 not in got and skipped == [(42, "지난 주간판이라 낸다")]),
        ("🔴 ep%d 미만은 안 본다 (소급 없음)" % SINCE_EP, 38 not in got),
        ("🔴 헛돌지 않는다 — 전부 통과시키는 검사가 아니다", bool(got)),
    ]
    shutil.rmtree(t, ignore_errors=True)
    bad = 0
    for why, ok in cases:
        bad += 0 if ok else 1
        print("%s %s" % ("PASS" if ok else "FAIL", why))
    print("STATUS: %s" % ("OK" if not bad else "FAIL %d건" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(_self_test() if "--self-test" in sys.argv else main())
