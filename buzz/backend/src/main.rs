//! buzz-backend-jjvps — Buzz 원격 에이전트 backend provider (JJ 회사 VPS / systemd 바인딩).
//!
//! 규격: buzz 레포 `docs/remote-agents.md`. 데스크톱이 이 바이너리를 한 번에 한 동작씩 띄우고,
//! stdin 으로 JSON 하나를 주고 stdout 에서 JSON 하나를 읽는다.
//!
//! 🔴 이 판은 **탐침이다.** `info` 만 진짜로 답하고 `deploy` 는 in-band 실패를 낸다.
//! 이유: 설치된 데스크톱이 2026-09-06 판이고, 규격의 「알려진 결함 1」이
//! 「Windows 에서 `.exe` 접미사가 provider id 에 남아 deploy 에서 id 검증에 걸린다 —
//! 드롭다운엔 뜨고, info 는 통과하고, deploy 만 깨진다」이다. 그리고 v1 provider 범위는
//! **macOS+Linux 로 선언**돼 있다(DECISION B). 그러니 deploy 를 다 짜 놓고 그 자리에서
//! 막히는 대신, **뜨는지 · id 가 뭔지부터** 이 탐침으로 잰다.
//!
//! 지키는 것 (규격 [L2]):
//! - stdin JSON 하나 -> stdout JSON 하나. 처리된 실패는 `{"ok":false,"error":...}` + exit 0.
//! - 종료 코드는 한 비트만 나른다: 0 = 출력을 믿어도 된다, 0 아님 = 실패(출력 무시).
//! - `provider_config` 로 자격증명을 받지 않는다(I2). 스키마에 그런 칸이 없다.
//! - 어떤 출력에도 시크릿을 싣지 않는다. 이 판은 nsec 을 읽지조차 않는다.

use std::io::Read;

const PROTOCOL_VERSION: u64 = 1;
const VERSION: &str = env!("CARGO_PKG_VERSION");

/// `info` 응답. `config_schema` 가 앱의 설정 폼을 만든다.
///
/// 🔴 자격증명 칸이 없다. SSH 키는 이 PC 에 이미 있고(`~/.ssh/buzz_vps`),
/// provider_config 로 받으면 규격 I2 위반이다.
fn info() -> serde_json::Value {
    serde_json::json!({
        "ok": true,
        "name": "JJ Company VPS (systemd)",
        "version": VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "description": "회사 Hostinger VPS 에 systemd 유닛으로 에이전트를 세운다. \
                        PC 가 꺼져 있어도 계속 돈다.",
        "config_schema": {
            "type": "object",
            "properties": {
                "ssh_host": {
                    "type": "string",
                    "title": "VPS 주소",
                    "default": "187.127.100.11"
                },
                "ssh_user": {
                    "type": "string",
                    "title": "SSH 사용자",
                    "default": "root"
                },
                "inactivity_seconds": {
                    "type": "number",
                    "title": "무활동 종료 (초 · 0 = 무제한)",
                    "default": 7200
                }
            },
            "required": ["ssh_host", "ssh_user"]
        }
    })
}

fn err(message: &str) -> serde_json::Value {
    serde_json::json!({ "ok": false, "error": message })
}

/// 요청 하나를 응답 하나로. 순수 함수라 자체 검사가 이 자리를 그대로 잰다.
fn handle(request: &serde_json::Value) -> serde_json::Value {
    match request.get("op").and_then(serde_json::Value::as_str) {
        Some("info") => info(),
        Some("deploy") => err(
            "probe build: deploy is not implemented yet. \
             This binary exists to measure whether Windows discovery yields a clean provider id.",
        ),
        Some(other) => err(&format!("unsupported op: {other}")),
        None => err("request has no string field 'op'"),
    }
}

/// 자체 검사. 축을 따로 둔다 — 하나가 다른 하나를 가려 주지 않게.
fn self_test() -> i32 {
    let mut failed = 0;
    let mut check = |name: &str, ok: bool| {
        println!("{} {}", if ok { "ok  " } else { "FAIL" }, name);
        if !ok {
            failed += 1;
        }
    };

    let i = handle(&serde_json::json!({"op": "info", "request_id": "x"}));
    check("info: ok=true", i["ok"] == serde_json::json!(true));
    check(
        "info: protocol_version 이 정수 1 (문자열 '1' 이면 데스크톱이 거부한다)",
        i["protocol_version"] == serde_json::json!(1),
    );
    for field in ["name", "version", "description"] {
        check(
            &format!("info: {field} 가 비지 않은 문자열"),
            i[field].as_str().is_some_and(|s| !s.is_empty()),
        );
    }
    check(
        "info: config_schema 가 객체",
        i["config_schema"].is_object(),
    );

    // I2: 스키마가 자격증명을 요구하지 않는다. 이 축은 위 축들과 겹치지 않는다 -
    // 스키마가 객체이면서도 비밀 칸을 들고 있을 수 있기 때문이다.
    let schema_text = i["config_schema"].to_string().to_lowercase();
    check(
        "I2: config_schema 에 자격증명 낱말이 없다",
        !["password", "secret", "token", "private_key", "nsec", "credential"]
            .iter()
            .any(|needle| schema_text.contains(needle)),
    );

    let d = handle(&serde_json::json!({"op": "deploy", "agent": {"private_key_nsec": "nsec1SECRET"}}));
    check("deploy: 탐침은 in-band 실패를 낸다", d["ok"] == serde_json::json!(false));
    // 「아무것도 안 했다」가 「했다」와 같은 값을 내지 않는지, 그리고 시크릿이 새지 않는지.
    check(
        "deploy: 실패 응답에 요청 속 시크릿이 안 실린다",
        !d.to_string().contains("nsec1SECRET"),
    );

    let u = handle(&serde_json::json!({"op": "launch-missiles"}));
    check("모르는 op 은 거부한다", u["ok"] == serde_json::json!(false));
    let n = handle(&serde_json::json!({"request_id": "x"}));
    check("op 이 없으면 거부한다", n["ok"] == serde_json::json!(false));

    println!("\n{}", if failed == 0 { "STATUS: OK" } else { "STATUS: FAIL" });
    i32::from(failed != 0)
}

fn main() {
    if std::env::args().any(|a| a == "--self-test") {
        std::process::exit(self_test());
    }

    let mut raw = String::new();
    if let Err(e) = std::io::stdin().read_to_string(&mut raw) {
        // 요청을 못 읽었으면 출력은 못 믿는다 -> 0 아닌 종료.
        eprintln!("failed to read request: {e}");
        std::process::exit(1);
    }

    let response = match serde_json::from_str::<serde_json::Value>(&raw) {
        Ok(request) => handle(&request),
        // 파싱 실패는 처리된 실패다 - in-band 로 알리고 0 으로 나간다.
        Err(e) => err(&format!("request is not valid JSON: {e}")),
    };

    println!("{response}");
}
