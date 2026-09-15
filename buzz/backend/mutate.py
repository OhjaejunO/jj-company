"""돌연변이 시험 — 구현을 일부러 깨뜨리고 «그 축이 잡는가» 를 본다.

정관 §0: 통과하는 검사는 헛돌 수 있다. 변이가 의도한 결함을 못 만들면
그 시험은 축을 증명하지 않으므로, 「아무 축도 안 걸림」도 결과로 적는다.
"""
import subprocess
import sys

SRC = "/root/build/jjvps/src/main.rs"
BUILD = ["bash", "-lc", "cd /root/build/jjvps && PATH=$HOME/.cargo/bin:$PATH cargo build --release 2>&1 | tail -5"]
TEST = ["bash", "-lc", "/root/build/jjvps/target/release/buzz-backend-jjvps --self-test"]

MUTATIONS = [
    (
        "3층 순서를 뒤집는다 (policy_env 가 env 를 이기게)",
        'for layer in ["policy_env", "env"]',
        'for layer in ["env", "policy_env"]',
    ),
    (
        "presence 끄기를 «지움» 이 아니라 «덮음» 으로 낮춘다",
        '    "BUZZ_ACP_NO_PRESENCE",\n',
        "",
    ),
    (
        "지문에 세대 토큰을 포함시킨다",
        'if k == "BUZZ_MANAGED_AGENT_START_NONCE" {',
        "if false {",
    ),
    (
        "정착 시간을 0 으로 (뜨자마자 «떴다» 로 읽는다)",
        "const SETTLE_SECONDS: f64 = 8.0;",
        "const SETTLE_SECONDS: f64 = 0.0;",
    ),
    (
        "내려가는 중을 먼저 보지 않는다",
        'if obs.active_state == "deactivating" {',
        "if false {",
    ),
    (
        "살아 있어도 의도가 갈리면 손댄다",
        "if obs.started() {",
        "if obs.started() && obs.meta_intent == desired_intent {",
    ),
    (
        "셸 인용에서 홑따옴표 이스케이프를 뺀다",
        'out.push_str("\'\\\\\'\'");',
        'out.push(ch);',
    ),
    (
        "관리 표식을 안 본다 (신원만 맞으면 수리한다)",
        "if obs.managed_by != MANAGED_BY {",
        "if false {",
    ),
    (
        "같은 호출 안에서 다시 만들 수 있게 한다",
        "if created_this_call {",
        "if false {",
    ),
    (
        "가동 시간 단위를 틀리게 (us -> ms)",
        "obs.uptime_secs = (now_us - enter_us) / 1_000_000.0;",
        "obs.uptime_secs = (now_us - enter_us) / 1000.0;",
    ),
    (
        "관측 파서가 기동 시각 키를 못 알아보게",
        '"ActiveEnterTimestampMonotonic" => enter_us',
        '"ActiveEnterTimestamp" => enter_us',
    ),
    (
        "mkdir 쪽에서 %i 를 안 푼다 (없는 폴더에서 봇이 뜬다)",
        'workspace_resolved: cfg.workspace.replace("%i", &instance),',
        "workspace_resolved: cfg.workspace.clone(),",
    ),
    (
        "작업 자리 거부 목록이 «그 아래» 를 안 본다",
        'trimmed == *root || trimmed.starts_with(&format!("{root}/"))',
        "trimmed == *root",
    ),
    (
        "설정을 읽는 쪽이 작업 자리 검사를 안 부른다",
        "    validate_workspace(&workspace)?;\n",
        "",
    ),
]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def fails():
    out = run(TEST)
    return [l for l in out.splitlines() if l.startswith("FAIL")]


original = open(SRC, encoding="utf-8").read()
print("=== 기준선 ===")
run(BUILD)
base = fails()
print("기준선 FAIL: " + str(len(base)))
if base:
    print("\n".join(base))
    sys.exit(1)

results = []
for name, old, new in MUTATIONS:
    if old not in original:
        results.append((name, "변이 실패 - 대상 문자열 없음", []))
        continue
    open(SRC, "w", encoding="utf-8").write(original.replace(old, new, 1))
    build_out = run(BUILD)
    if "error" in build_out:
        results.append((name, "컴파일 실패", []))
    else:
        f = fails()
        results.append((name, str(len(f)) + "축이 잡았다" if f else "🔴 아무 축도 안 잡았다", f))
    open(SRC, "w", encoding="utf-8").write(original)

run(BUILD)
print("\n=== 결과 ===")
missed = 0
for name, verdict, f in results:
    print("- " + name + " -> " + verdict)
    for line in f[:3]:
        print("    " + line)
    if "안 잡았다" in verdict or "변이 실패" in verdict or "컴파일 실패" in verdict:
        missed += 1
print("\nSTATUS: " + ("OK" if missed == 0 else "FAIL " + str(missed) + "건"))
