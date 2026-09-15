//! buzz-backend-jjvps — Buzz 원격 에이전트 backend provider (JJ 회사 VPS / systemd 바인딩).
//!
//! 규격: buzz 레포 `docs/remote-agents.md`. 데스크톱이 이 바이너리를 한 번에 한 동작씩 띄우고,
//! stdin 으로 JSON 하나를 주고 stdout 에서 JSON 하나를 읽는다.
//!
//! 🔴 **탐침 판은 끝났다.** 2026-09-14 에 JJ 가 데스크톱에서 재서 「Run on: jjvps」가 뜨고
//! `deploy` 가 우리 바이너리까지 도달하는 것을 확인했고(알려진 결함 1 은 이 설치본에 없다),
//! 2026-09-15 에 설치본(9/06 빌드) 문자열 표에서 `provider_deploy.rs` 옆에 `launch`·`policy_env`·
//! `BUZZ_ACP_REPLAY_FLOOR` 가 같이 박혀 있는 것을 확인했다 — **`launch` 블록을 이미 내보낸다**
//! (알려진 결함 3 이 이 판에서는 살아 있지 않다). 그래서 정식 §Launch data 경로로 짰다.
//!
//! 🔴 **`launch` 가 없으면 배포하지 않는다.** 없는 판에서 top-level 원시 필드로 대신 짜면
//! 「같은 에이전트인데 로컬과 다른 명령줄로 도는」 상태가 조용히 만들어진다(결함 3 의 (a)(b)).
//! 규격이 그 페이로드를 「semantics-preserving remote launch 에 불충분」이라고 못박았으므로
//! **닫히는 쪽으로 실패한다.**
//!
//! ## 이 바인딩이 규격의 각 항을 무엇으로 실현하는가 ([L2] 6항의 «binding documents» 의무)
//!
//! | 규격(쿠버네티스 말) | 이 바인딩(systemd 말) |
//! |---|---|
//! | 파드 | `buzz-remote@<id>.service` 인스턴스 |
//! | `agent_id` | `buzz-agent-<앞12hex>` (파드 이름과 같은 꼴) |
//! | 식별 라벨 | 상태 디렉터리 이름 `<앞12hex>` |
//! | 전체 pubkey 어노테이션 | `meta.json` 의 `agent_pubkey_full` |
//! | 관리 표식 | `meta.json` 의 `managed_by`+`binding_version` |
//! | create-intent 어노테이션 | `meta.json` 의 `create_intent` (sha256) |
//! | Secret + 세대 토큰 | `env`(0600) + `meta.json` 의 `generation` |
//! | UID+resourceVersion 펜스 | 파괴 직전 `meta.json` 의 sha256 재대조 |
//! | `state.running` | `ActiveState=active` ∧ `SubState=running` ∧ **정착 시간 경과** |
//! | `terminationGracePeriodSeconds: 60` | `TimeoutStopSec=60` |
//! | `restartPolicy` | **항상 `Restart=no`** (아래) |
//!
//! 🔴 **`Restart=no` 는 선택이 아니라 규격이 시킨 것이다.** 알려진 결함 6: 하네스의
//! 「의도적 종료 ⇒ 0」 계약이 **고정·시험된 적이 없어**, 그것이 서기 전에는 어떤 supervisor
//! 재시작 정책도(`OnFailure`·`Restart=on-failure` 포함) 하네스에 걸면 안 된다. 되살아나야 할
//! 자리는 재시작기가 아니라 **사람의 Start 재발행**이고, `deploy` 가 화해 루프라 그 경로가 이미 있다.
//!
//! 지키는 것 (규격 [L2]):
//! - stdin JSON 하나 -> stdout JSON 하나. 처리된 실패는 `{"ok":false,"error":...}` + exit 0.
//! - 종료 코드는 한 비트만 나른다: 0 = 출력을 믿어도 된다, 0 아님 = 실패(출력 무시).
//! - `provider_config` 로 자격증명을 받지 않는다(I2). 받는 것은 **경로**뿐이다.
//! - 어떤 출력에도 시크릿을 싣지 않는다.

use k256::elliptic_curve::sec1::ToEncodedPoint;
use std::collections::BTreeMap;
use std::io::{Read, Write};

const PROTOCOL_VERSION: u64 = 1;
const VERSION: &str = env!("CARGO_PKG_VERSION");
const MANAGED_BY: &str = "buzz-backend-jjvps";
const BINDING_VERSION: u64 = 1;

const HARNESS_PATH: &str = "/usr/local/bin/buzz-acp";
const MCP_COMMAND: &str = "buzz-dev-mcp";
const STATE_ROOT: &str = "/etc/buzz-remote";
const WORK_ROOT: &str = "/srv/work/remote";

/// 하네스가 «정말 떴다» 로 인정받기까지 연속으로 `active(running)` 이어야 하는 시간.
/// 이보다 짧으면 「떴다가 곧 죽는」 것을 «떴다» 로 읽는다.
const SETTLE_SECONDS: f64 = 8.0;
const POLL_SECONDS: u64 = 3;
/// 규격 §Deploy 의 600s 동작 기한. 「한 번의 Start 가 동기적으로 얼마나 기다리는가」일 뿐이고,
/// 기한이 지났다고 무엇을 지우지 않는다.
const DEADLINE_SECONDS: u64 = 600;

/// 사용자 층(`launch.env`·`launch.policy_env`)에서 **지워야** 하는 키.
/// 덮어쓰는 것으로 충분하지 않은 것들이다 — 아예 없어야 하거나(L1 2항), 호스트 경로라
/// 원격에서 반드시 다시 풀어야 한다(§Launch data «Host-resolved values»).
const DROP_FROM_USER_LAYERS: &[&str] = &[
    // L1 2항: 원격 에이전트에서 presence 는 유일한 생존 신호다. 끄는 것을 허용하지 않는다.
    "BUZZ_ACP_NO_PRESENCE",
    // 호스트에서 풀린 값들. 그대로 넘기면 원격에 없는 경로를 가리킨다.
    "PATH",
    "CLAUDE_CODE_EXECUTABLE",
    "BUZZ_ACP_SETUP_PAYLOAD",
    "BUZZ_ACP_SYSTEM_PROMPT_FILE",
];

/// 지문에서 **값 대신 해시**로 들어가는 키. 시크릿을 디스크에 남기지 않으면서도
/// 「키가 바뀌었는가」는 갈라 본다.
const HASHED_IN_FINGERPRINT: &[&str] = &[
    "BUZZ_PRIVATE_KEY",
    "NOSTR_PRIVATE_KEY",
    "BUZZ_AUTH_TAG",
];

// ---------------------------------------------------------------- 작은 도구들

fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    h.update(bytes);
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

const B64: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

fn b64_encode(data: &[u8]) -> String {
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b = [chunk[0], *chunk.get(1).unwrap_or(&0), *chunk.get(2).unwrap_or(&0)];
        let n = (u32::from(b[0]) << 16) | (u32::from(b[1]) << 8) | u32::from(b[2]);
        out.push(B64[(n >> 18) as usize & 63] as char);
        out.push(B64[(n >> 12) as usize & 63] as char);
        out.push(if chunk.len() > 1 { B64[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if chunk.len() > 2 { B64[n as usize & 63] as char } else { '=' });
    }
    out
}

/// 홑따옴표 셸 인용. 값에 무엇이 들어 있든(줄바꿈·따옴표·`$`·백슬래시) 한 낱말로 간다.
///
/// 🔴 **systemd 의 `EnvironmentFile=` 을 쓰지 않는 이유가 이것이다.** 그 파서의 따옴표·이스케이프
/// 규칙이 문서로 확정되지 않아 **줄바꿈 든 시스템 프롬프트가 조용히 잘릴 수 있다.**
/// 대신 셸 파일로 쓰고 `sh -c "set -a; . <파일>; exec <하네스>"` 로 읽는다 —
/// 인용 규칙이 하나뿐이고 여기서 시험할 수 있다. `exec` 라 종료 신호는 하네스가 직접 받는다(L1 3항).
fn shell_quote(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 2);
    out.push('\'');
    for ch in value.chars() {
        if ch == '\'' {
            out.push_str("'\\''");
        } else {
            out.push(ch);
        }
    }
    out.push('\'');
    out
}

/// 환경변수 이름이 POSIX 꼴인가. 규격이 명시적으로 요구한다 — `BUZZ_AUTH_TAG=x` 같은 것을
/// **이름 안에 숨겨** 예약키 제거를 우회하는 길을 막는다.
fn is_posix_env_name(name: &str) -> bool {
    !name.is_empty()
        && !name.starts_with(|c: char| c.is_ascii_digit())
        && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
}

fn as_str(v: &serde_json::Value, key: &str) -> Option<String> {
    v.get(key).and_then(serde_json::Value::as_str).map(str::to_string)
}

/// 값이 비어 있지 않은 문자열일 때만 준다. 규격의 «null 이거나 빈 문자열» 은 같은 뜻이다.
fn as_nonempty(v: &serde_json::Value, key: &str) -> Option<String> {
    as_str(v, key).filter(|s| !s.trim().is_empty())
}

// ---------------------------------------------------------------- 신원

/// nsec -> x-only 공개키 hex. **어떤 substrate 읽기·쓰기보다 먼저** 부른다(§Deploy 0단계).
///
/// 벡터 둘을 자체 검사에 박아 뒀고 **서로 다른 도구로 각각 교차검증했다**(2026-09-15):
/// bech32 해독은 우리 파이썬 디코더로, 공개키 유도는 VPS 의 openssl 로. 한 도구로 둘 다 재면
/// 그 도구가 틀렸을 때 둘이 같이 틀린다.
fn derive_pubkey_hex(nsec: &str) -> Result<String, String> {
    let nsec = nsec.trim();
    if nsec.is_empty() {
        return Err("private_key_nsec is empty (I1: an agent is never launched identityless)".into());
    }
    let (hrp, data) = bech32::decode(nsec).map_err(|_| "private_key_nsec is not valid bech32".to_string())?;
    if hrp.as_str() != "nsec" {
        return Err(format!("private_key_nsec has hrp '{}', expected 'nsec'", hrp.as_str()));
    }
    if data.len() != 32 {
        return Err(format!("private_key_nsec decodes to {} bytes, expected 32", data.len()));
    }
    let secret = k256::SecretKey::from_slice(&data)
        .map_err(|_| "private_key_nsec is not a valid secp256k1 scalar".to_string())?;
    let point = secret.public_key().to_encoded_point(true);
    let bytes = point.as_bytes();
    if bytes.len() != 33 {
        return Err("public key derivation produced an unexpected encoding".into());
    }
    Ok(bytes[1..].iter().map(|b| format!("{b:02x}")).collect())
}

// ---------------------------------------------------------------- 설정

struct Config {
    ssh_host: String,
    ssh_user: String,
    ssh_identity_file: String,
    /// I5. `0` 은 오설정이 아니라 «무기한» 이라는 명시적 선택이라 거부하지 않는다.
    inactivity_seconds: u64,
}

fn parse_config(pc: &serde_json::Value) -> Result<Config, String> {
    let host = as_nonempty(pc, "ssh_host").unwrap_or_else(|| "187.127.100.11".into());
    let user = as_nonempty(pc, "ssh_user").unwrap_or_else(|| "root".into());
    let identity = as_nonempty(pc, "ssh_identity_file").unwrap_or_else(|| "~/.ssh/buzz_vps".into());
    let inactivity = match pc.get("inactivity_seconds") {
        None | Some(serde_json::Value::Null) => 7200,
        Some(v) => v
            .as_u64()
            .or_else(|| v.as_f64().filter(|f| *f >= 0.0).map(|f| f as u64))
            .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
            .ok_or("inactivity_seconds must be a non-negative number")?,
    };
    Ok(Config { ssh_host: host, ssh_user: user, ssh_identity_file: identity, inactivity_seconds: inactivity })
}

// ---------------------------------------------------------------- 환경 조립

/// 세 층을 규격 순서대로 쌓는다(뒤가 앞을 이긴다):
/// 1. `launch.policy_env` — 덮어쓸 수 있는 행동 기본값
/// 2. `launch.env` — 사용자/층 환경. 🔴 **레거시 `env_vars` 를 그 위에 다시 합치지 않는다**
///    (이미 합쳐져서 온다 · §Launch data 2항)
/// 3. 권위값 — 신원·수신 게이트·수명 정책·MCP·세대 토큰. 어느 층도 못 덮는다.
fn build_env(
    payload: &serde_json::Value,
    cfg: &Config,
    pubkey_hex: &str,
    generation: &str,
) -> Result<BTreeMap<String, String>, String> {
    let launch = payload
        .get("launch")
        .filter(|v| v.is_object())
        .ok_or_else(|| {
            "deploy payload carries no `launch` block — this desktop build predates the launch \
             resolver (Known Defect 3). Refusing rather than launching a command line that \
             silently differs from the identical local agent."
                .to_string()
        })?;

    // 규격이 이것 하나는 「통과시키지 말고 닫아라」라고 명시한다 — 메시 전송은 데스크톱
    // localhost 프록시라 원격에서는 아무도 안 듣는다.
    if let Some(p) = as_nonempty(payload, "provider") {
        if p == "relay-mesh" {
            return Err("effective provider is `relay-mesh`, which resolves to a desktop loopback \
                        proxy; a remote agent cannot reach it. Refused before any mutation."
                .into());
        }
    }

    let mut env: BTreeMap<String, String> = BTreeMap::new();

    for layer in ["policy_env", "env"] {
        let Some(map) = launch.get(layer).and_then(serde_json::Value::as_object) else {
            continue;
        };
        for (k, v) in map {
            let Some(v) = v.as_str() else { continue };
            if !is_posix_env_name(k) || DROP_FROM_USER_LAYERS.contains(&k.as_str()) {
                continue;
            }
            env.insert(k.clone(), v.to_string());
        }
    }

    // ---- 3층: 권위값. 여기부터는 어느 사용자 층도 못 덮는다.
    let nsec = as_nonempty(payload, "private_key_nsec")
        .ok_or("deploy payload carries no private_key_nsec")?;
    let relay = as_nonempty(payload, "relay_url").ok_or("deploy payload carries no relay_url")?;
    env.insert("BUZZ_PRIVATE_KEY".into(), nsec.clone());
    env.insert("NOSTR_PRIVATE_KEY".into(), nsec);
    env.insert("BUZZ_RELAY_URL".into(), relay);

    let auth_tag = as_nonempty(payload, "auth_tag");
    let owner = launch.get("owner_pubkey").and_then(serde_json::Value::as_str).filter(|s| !s.is_empty());

    // 소유자 없이는 하네스가 `!shutdown` 을 «자기에게 온 말» 로 읽고 **대답한다** —
    // §Stop 이 설명하는 장치가 통째로 없는 상태가 된다. 그래서 어느 쪽도 없으면 거부한다.
    match (&auth_tag, owner) {
        (None, None) => {
            return Err("deploy payload resolves neither `auth_tag` nor `launch.owner_pubkey`; \
                        without an owner the harness answers `!shutdown` instead of obeying it."
                .into())
        }
        (Some(tag), _) => {
            env.insert("BUZZ_AUTH_TAG".into(), tag.clone());
        }
        (None, Some(o)) => {
            env.insert("BUZZ_ACP_AGENT_OWNER".into(), o.to_string());
        }
    }

    // 수신 저자 게이트. 데스크톱이 이미 정책을 반영한 **투영값**을 보낸다.
    let respond_to = as_nonempty(payload, "respond_to").unwrap_or_else(|| "owner-only".into());
    if respond_to == "allowlist" {
        let list: Vec<String> = payload
            .get("respond_to_allowlist")
            .and_then(serde_json::Value::as_array)
            .map(|a| a.iter().filter_map(serde_json::Value::as_str).map(str::to_string).collect())
            .unwrap_or_default();
        if list.is_empty() {
            return Err("respond_to is 'allowlist' but respond_to_allowlist is empty".into());
        }
        env.insert("BUZZ_ACP_RESPOND_TO_ALLOWLIST".into(), list.join(","));
    }
    if respond_to == "owner-only" {
        // 조이기만 하는 핀이다. 데스크톱이 owner-only 를 강제하는 빌드에서 거는 독립 가드와
        // 같은 값이고, 사용자가 스스로 owner-only 를 고른 경우에도 동작이 안 바뀐다.
        // 🔴 못 잡는 것: 데스크톱의 `enforced_owner_only` 자체는 페이로드에 안 실려서 모른다.
        env.insert("BUZZ_ACP_ALLOWED_RESPOND_TO".into(), "owner-only".into());
    }
    env.insert("BUZZ_ACP_RESPOND_TO".into(), respond_to);

    // I5. 소유자의 **의도된** 수명 정책이지 사용자 env 의 흘러듦이 아니다.
    if cfg.inactivity_seconds > 0 {
        env.insert("BUZZ_ACP_EXIT_AFTER_INACTIVITY".into(), cfg.inactivity_seconds.to_string());
    }

    // 원격에서 다시 푼 값들(호스트 경로를 나르지 않는다).
    let command = launch
        .get("command")
        .and_then(serde_json::Value::as_str)
        .filter(|s| !s.trim().is_empty())
        .ok_or("launch.command is empty; the harness has no agent to spawn")?;
    if command.contains('/') || command.contains('\\') {
        return Err(format!(
            "launch.command must be a command name, not a host path (got '{command}')"
        ));
    }
    env.insert("BUZZ_ACP_AGENT_COMMAND".into(), command.to_string());
    if let Some(args) = launch.get("args").and_then(serde_json::Value::as_array) {
        let args: Vec<String> =
            args.iter().filter_map(serde_json::Value::as_str).map(str::to_string).collect();
        if !args.is_empty() {
            env.insert("BUZZ_ACP_AGENT_ARGS".into(), args.join(" "));
        }
    }
    env.insert("BUZZ_ACP_MCP_COMMAND".into(), MCP_COMMAND.into());
    env.insert("BUZZ_MANAGED_AGENT_START_NONCE".into(), generation.into());

    let _ = pubkey_hex;
    Ok(env)
}

// ---------------------------------------------------------------- 계획

struct Plan {
    instance: String,
    agent_id: String,
    pubkey: String,
    intent: String,
    env_file: String,
    meta_file: String,
    unit_text: String,
    agent_command: String,
}

fn unit_text(instance: &str) -> String {
    let _ = instance;
    format!(
        "[Unit]\n\
         Description=buzz remote agent (%i)\n\
         After=network-online.target\n\
         Wants=network-online.target\n\
         \n\
         [Service]\n\
         Type=simple\n\
         Environment=HOME=/root\n\
         WorkingDirectory={WORK_ROOT}/%i\n\
         ExecStart=/bin/sh -c \"set -a; . {STATE_ROOT}/%i/env; set +a; exec {HARNESS_PATH}\"\n\
         Restart=no\n\
         TimeoutStopSec=60\n\
         \n\
         [Install]\n\
         WantedBy=multi-user.target\n"
    )
}

fn env_file_text(env: &BTreeMap<String, String>) -> String {
    let mut out = String::from("# buzz-backend-jjvps 가 쓴다. 손으로 고치지 않는다.\n");
    for (k, v) in env {
        out.push_str(k);
        out.push('=');
        out.push_str(&shell_quote(v));
        out.push('\n');
    }
    out
}

/// create-intent 지문. **세대 토큰은 뺀다** — 시도마다 바뀌므로 넣으면 모든 재시도가
/// «의도가 갈렸다» 로 읽혀 살아 있는 봇을 계속 갈아엎는다.
fn intent_fingerprint(env: &BTreeMap<String, String>, unit: &str) -> String {
    let mut material = format!("binding_version={BINDING_VERSION}\n");
    for (k, v) in env {
        if k == "BUZZ_MANAGED_AGENT_START_NONCE" {
            continue;
        }
        if HASHED_IN_FINGERPRINT.contains(&k.as_str()) {
            material.push_str(&format!("{k}=sha256:{}\n", sha256_hex(v.as_bytes())));
        } else {
            material.push_str(&format!("{k}={v}\n"));
        }
    }
    material.push_str("---unit---\n");
    material.push_str(unit);
    sha256_hex(material.as_bytes())
}

fn plan(payload: &serde_json::Value, cfg: &Config, generation: &str) -> Result<Plan, String> {
    let nsec = as_nonempty(payload, "private_key_nsec")
        .ok_or("deploy payload carries no private_key_nsec")?;
    let pubkey = derive_pubkey_hex(&nsec)?;
    let instance = pubkey[..12].to_string();
    let env = build_env(payload, cfg, &pubkey, generation)?;
    let unit = unit_text(&instance);
    let intent = intent_fingerprint(&env, &unit);
    let agent_command = env.get("BUZZ_ACP_AGENT_COMMAND").cloned().unwrap_or_default();
    Ok(Plan {
        agent_id: format!("buzz-agent-{instance}"),
        meta_file: meta_json(&pubkey, &intent, generation),
        pubkey,
        instance,
        intent,
        env_file: env_file_text(&env),
        unit_text: unit,
        agent_command,
    })
}

fn meta_json(pubkey: &str, intent: &str, generation: &str) -> String {
    serde_json::json!({
        "managed_by": MANAGED_BY,
        "binding_version": BINDING_VERSION,
        "agent_pubkey_full": pubkey,
        "create_intent": intent,
        "generation": generation,
    })
    .to_string()
}

// ---------------------------------------------------------------- 관측

#[derive(Default, Clone)]
struct Obs {
    has_state: bool,
    meta_sha: String,
    managed_by: String,
    meta_pubkey: String,
    meta_intent: String,
    active_state: String,
    sub_state: String,
    result: String,
    exec_main_status: String,
    uptime_secs: f64,
    agent_cmd_found: bool,
    condition: String,
}

impl Obs {
    /// 「떴다」의 정의. 규격의 `state.running` 자리다 — **단계(phase)가 준비 상태가 아니다.**
    /// 정착 시간을 같이 재는 이유: 떴다가 곧 죽는 것을 「떴다」로 읽지 않기 위해서다.
    fn started(&self) -> bool {
        self.active_state == "active" && self.sub_state == "running" && self.uptime_secs >= SETTLE_SECONDS
    }
    fn condition_line(&self) -> String {
        let head = format!(
            "ActiveState={} SubState={} Result={} ExecMainStatus={}",
            self.active_state, self.sub_state, self.result, self.exec_main_status
        );
        if self.condition.trim().is_empty() {
            head
        } else {
            format!("{head} | {}", self.condition.trim())
        }
    }
}

#[derive(Debug, PartialEq)]
enum Action {
    NoOp,
    Create,
    Replace,
    Observe,
    WaitGone,
    Fail(String),
}

/// §Deploy 2단계의 순서 있는 규칙을 systemd 말로 옮긴 것. 순수 함수라 자체 검사가 이 자리를 그대로 잰다.
fn reconcile(obs: &Obs, pubkey: &str, desired_intent: &str, created_this_call: bool) -> Action {
    // 죽는 중인 것을 「살아 있다」로 읽지 않는다. **단계보다 먼저 본다.**
    if obs.active_state == "deactivating" {
        return Action::WaitGone;
    }
    if !obs.has_state {
        return Action::Create;
    }
    // 1단계: 신원과 **소유권**을 따로 확인한다. 신원이 맞아도 우리가 만든 것이 아니면
    // 파괴적 수리를 하지 않는다 — 못 알아보는 것은 수리하지 않고 보고한다.
    if obs.managed_by != MANAGED_BY {
        return Action::Fail(format!(
            "{STATE_ROOT}/{} exists but is not ours (managed_by='{}'); refusing to repair around \
             state this provider did not author",
            &pubkey[..12],
            obs.managed_by
        ));
    }
    if obs.meta_pubkey != pubkey {
        return Action::Fail(
            "identity collision: existing state carries a different agent pubkey".into(),
        );
    }
    // 살아 있으면 손대지 않는다 — 의도가 갈렸더라도 그렇다. Start 가 돌고 있는 턴을 죽이면 안 된다.
    if obs.started() {
        return Action::NoOp;
    }
    // 이 호출이 스스로 만든 것을 같은 호출 안에서 다시 갈아엎지 않는다.
    // 같은 create 를 다시 돌려도 결과가 달라지지 않고, 기한 내내 지우고-만들기만 반복된다.
    if created_this_call {
        if obs.active_state == "failed" || obs.active_state == "inactive" {
            return Action::Fail(format!("harness exited during startup — {}", obs.condition_line()));
        }
        return Action::Observe;
    }
    // 끝난 잔해 — 평범한 재기동 경로다(reap 되었거나 !shutdown 으로 내려간 봇을 다시 올린다).
    if obs.active_state == "failed" || obs.active_state == "inactive" {
        return Action::Replace;
    }
    // 못 뜨는 것이 증명된 경우. 「이유 문자열」이 아니라 **참조 대상의 부재**를 확인한 것이다.
    if !obs.agent_cmd_found {
        return Action::Replace;
    }
    // 의도가 갈렸으면 사용자가 설정을 바꾼 것이다. 이 행이 없으면 그 변경이 영원히 안 닿는다.
    if obs.meta_intent != desired_intent {
        return Action::Replace;
    }
    // 그 밖(기동 중·아직 정착 전)은 **관찰**이다. 기한이 지나도 아무것도 지우지 않는다.
    Action::Observe
}

// ---------------------------------------------------------------- 원격 실행

const OBSERVE_SH: &str = r#"set -u
ID='@ID@'
CMD='@CMD@'
D=/etc/buzz-remote/$ID
if [ -f "$D/meta.json" ]; then
  echo "HAS_STATE=yes"
  echo "META_SHA=$(sha256sum "$D/meta.json" | cut -d' ' -f1)"
  echo "META_B64=$(base64 -w0 "$D/meta.json")"
else
  echo "HAS_STATE=no"
fi
systemctl show "buzz-remote@$ID.service" -p ActiveState -p SubState -p Result -p ExecMainStatus -p ActiveEnterTimestampMonotonic 2>/dev/null
awk '{ printf "NowMono=%d\n", $1 * 1000000 }' /proc/uptime
if command -v "$CMD" >/dev/null 2>&1; then echo "AGENT_CMD=found"; else echo "AGENT_CMD=missing"; fi
echo "CONDITION_B64=$(journalctl -u "buzz-remote@$ID.service" -n 12 --no-pager -o cat 2>/dev/null | tail -c 900 | base64 -w0)"
"#;

const CREATE_SH: &str = r#"set -eu
ID='@ID@'
D=/etc/buzz-remote/$ID
umask 077
mkdir -p "$D" "/srv/work/remote/$ID"
printf '%s' '@ENV_B64@' | base64 -d > "$D/env.new"
printf '%s' '@META_B64@' | base64 -d > "$D/meta.json.new"
printf '%s' '@UNIT_B64@' | base64 -d > /etc/systemd/system/buzz-remote@.service
chmod 600 "$D/env.new"
chmod 644 "$D/meta.json.new"
mv "$D/env.new" "$D/env"
mv "$D/meta.json.new" "$D/meta.json"
systemctl daemon-reload
systemctl reset-failed "buzz-remote@$ID.service" >/dev/null 2>&1 || true
systemctl enable --now "buzz-remote@$ID.service"
echo CREATE_OK
"#;

const REMOVE_SH: &str = r#"set -u
ID='@ID@'
EXPECT='@FENCE@'
D=/etc/buzz-remote/$ID
if [ ! -f "$D/meta.json" ]; then echo REMOVE_OK; exit 0; fi
CUR=$(sha256sum "$D/meta.json" | cut -d' ' -f1)
if [ "$CUR" != "$EXPECT" ]; then echo FENCE_MISMATCH; exit 0; fi
if ! grep -q '"managed_by":"buzz-backend-jjvps"' "$D/meta.json"; then echo NOT_OURS; exit 0; fi
systemctl disable --now "buzz-remote@$ID.service" >/dev/null 2>&1 || true
systemctl reset-failed "buzz-remote@$ID.service" >/dev/null 2>&1 || true
rm -rf "$D"
echo REMOVE_OK
"#;

fn expand_home(path: &str) -> String {
    if let Some(rest) = path.strip_prefix("~/") {
        if let Ok(home) = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")) {
            return format!("{home}/{rest}");
        }
    }
    path.to_string()
}

/// 유일한 불순한 자리. **스크립트는 stdin 으로 간다** — 그래서 nsec 이 argv 에도,
/// 셸 히스토리에도 남지 않는다.
fn ssh_run(cfg: &Config, script: &str) -> Result<String, String> {
    use std::process::{Command, Stdio};
    let mut child = Command::new("ssh")
        .arg("-i")
        .arg(expand_home(&cfg.ssh_identity_file))
        .args(["-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "StrictHostKeyChecking=accept-new"])
        .arg(format!("{}@{}", cfg.ssh_user, cfg.ssh_host))
        .arg("sh -s")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("could not run ssh: {e}"))?;
    child
        .stdin
        .take()
        .ok_or("ssh stdin unavailable")?
        .write_all(script.as_bytes())
        .map_err(|e| format!("could not send script over ssh: {e}"))?;
    let out = child.wait_with_output().map_err(|e| format!("ssh failed: {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(format!("ssh exited {}: {}", out.status, err.trim()));
    }
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

fn b64_decode_lossy(s: &str) -> String {
    let mut bits = 0u32;
    let mut nbits = 0;
    let mut out = Vec::new();
    for ch in s.bytes() {
        let Some(v) = B64.iter().position(|c| *c == ch) else { continue };
        bits = (bits << 6) | v as u32;
        nbits += 6;
        if nbits >= 8 {
            nbits -= 8;
            out.push((bits >> nbits) as u8);
        }
    }
    String::from_utf8_lossy(&out).to_string()
}

fn parse_observation(raw: &str) -> Obs {
    let mut obs = Obs::default();
    let mut enter_us: f64 = 0.0;
    let mut now_us: f64 = 0.0;
    for line in raw.lines() {
        let Some((k, v)) = line.split_once('=') else { continue };
        match k.trim() {
            "HAS_STATE" => obs.has_state = v == "yes",
            "META_SHA" => obs.meta_sha = v.to_string(),
            "META_B64" => {
                if let Ok(meta) = serde_json::from_str::<serde_json::Value>(&b64_decode_lossy(v)) {
                    obs.managed_by = as_str(&meta, "managed_by").unwrap_or_default();
                    obs.meta_pubkey = as_str(&meta, "agent_pubkey_full").unwrap_or_default();
                    obs.meta_intent = as_str(&meta, "create_intent").unwrap_or_default();
                }
            }
            "ActiveState" => obs.active_state = v.to_string(),
            "SubState" => obs.sub_state = v.to_string(),
            "Result" => obs.result = v.to_string(),
            "ExecMainStatus" => obs.exec_main_status = v.to_string(),
            "ActiveEnterTimestampMonotonic" => enter_us = v.parse().unwrap_or(0.0),
            "NowMono" => now_us = v.parse().unwrap_or(0.0),
            "AGENT_CMD" => obs.agent_cmd_found = v == "found",
            "CONDITION_B64" => obs.condition = b64_decode_lossy(v),
            _ => {}
        }
    }
    if enter_us > 0.0 && now_us >= enter_us {
        obs.uptime_secs = (now_us - enter_us) / 1_000_000.0;
    }
    obs
}

// ---------------------------------------------------------------- deploy

fn generation_token() -> String {
    // 시도마다 유일하면 족하다(§K8s Secrets 의 세대 토큰 자리). 암호학적 난수가 아니어도 되는 이유는
    // 이 값이 **상관용 표식**이지 자격증명이 아니기 때문이다.
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("{now:x}-{:x}", std::process::id())
}

fn deploy(payload: &serde_json::Value, pc: &serde_json::Value) -> Result<String, String> {
    let cfg = parse_config(pc)?;
    let plan = plan(payload, &cfg, &generation_token())?;

    let observe_script = OBSERVE_SH
        .replace("@ID@", &plan.instance)
        .replace("@CMD@", &plan.agent_command);
    let create_script = CREATE_SH
        .replace("@ID@", &plan.instance)
        .replace("@ENV_B64@", &b64_encode(plan.env_file.as_bytes()))
        .replace("@META_B64@", &b64_encode(plan.meta_file.as_bytes()))
        .replace("@UNIT_B64@", &b64_encode(plan.unit_text.as_bytes()));

    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(DEADLINE_SECONDS);
    let mut created_this_call = false;
    let mut last = String::from("no observation yet");

    while std::time::Instant::now() < deadline {
        let obs = parse_observation(&ssh_run(&cfg, &observe_script)?);
        last = obs.condition_line();
        match reconcile(&obs, &plan.pubkey, &plan.intent, created_this_call) {
            Action::NoOp => return Ok(plan.agent_id),
            Action::Fail(message) => return Err(message),
            Action::Create => {
                let out = ssh_run(&cfg, &create_script)?;
                if !out.contains("CREATE_OK") {
                    return Err(format!("create did not confirm: {}", out.trim()));
                }
                created_this_call = true;
            }
            Action::Replace => {
                // 파괴적 쓰기는 **그것을 허가한 관측 그대로에 고정**한다. 사이에 바뀌었으면 실패하고
                // 1단계부터 다시 든다 — 충돌은 재진입으로 수렴한다.
                let remove_script = REMOVE_SH
                    .replace("@ID@", &plan.instance)
                    .replace("@FENCE@", &obs.meta_sha);
                let out = ssh_run(&cfg, &remove_script)?;
                if out.contains("NOT_OURS") {
                    return Err("existing state lost its management marker between read and write; \
                                refusing to delete state this provider may not have authored"
                        .into());
                }
                // FENCE_MISMATCH 는 실패가 아니라 «다시 보라» 다.
            }
            Action::Observe | Action::WaitGone => {}
        }
        std::thread::sleep(std::time::Duration::from_secs(POLL_SECONDS));
    }
    Err(format!("startup not confirmed within the {DEADLINE_SECONDS}s deadline — {last}"))
}

// ---------------------------------------------------------------- 배선

/// `info` 응답. `config_schema` 가 앱의 설정 폼을 만든다.
///
/// 🔴 자격증명 칸이 없다. SSH 키는 이 PC 에 이미 있고(`~/.ssh/buzz_vps`),
/// provider_config 로 받으면 규격 I2 위반이다. 받는 것은 **그 키가 있는 경로**뿐이다.
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
                "ssh_host": { "type": "string", "title": "VPS 주소", "default": "187.127.100.11" },
                "ssh_user": { "type": "string", "title": "SSH 사용자", "default": "root" },
                "ssh_identity_file": {
                    "type": "string",
                    "title": "SSH 신원 파일 경로 (내용이 아니라 경로다)",
                    "default": "~/.ssh/buzz_vps"
                },
                "inactivity_seconds": {
                    "type": "number",
                    "title": "무활동 종료 (초 · 0 = 무기한)",
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

fn handle(request: &serde_json::Value) -> serde_json::Value {
    match request.get("op").and_then(serde_json::Value::as_str) {
        Some("info") => info(),
        Some("deploy") => {
            let empty = serde_json::json!({});
            let payload = request.get("agent").unwrap_or(&empty);
            let pc = request.get("provider_config").unwrap_or(&empty);
            match deploy(payload, pc) {
                Ok(agent_id) => serde_json::json!({ "ok": true, "agent_id": agent_id }),
                Err(message) => err(&message),
            }
        }
        Some(other) => err(&format!("unsupported op: {other}")),
        None => err("request has no string field 'op'"),
    }
}

// ---------------------------------------------------------------- 자체 검사

/// 🔴 아래 nsec 은 **NIP-19 문서에 실린 공개 예시**다. 누구의 실제 신원도 아니다.
/// 두 벡터를 **서로 다른 도구로 각각** 교차검증했다 (2026-09-15):
/// bech32 해독은 우리 파이썬 디코더로, 공개키 유도는 VPS 의 openssl 로.
const NSEC_VECTOR: &str = "nsec1vl029mgpspedva04g90vltkh6fvh240zqtv9k0t9af8935ke9laqsnlfe5";
const PUBKEY_VECTOR: &str = "7e7e9c42a91bfef19fa929e5fda1b72e0ebc1a4c1141673e2794234d86addf4e";
const NPUB_VECTOR: &str = "npub10elfcs4fr0l0r8af98jlmgdh9c8tcxjvz9qkw038js35mp4dma8qzvjptg";
/// 마지막 글자 하나만 바꾼 것. 체크섬이 실제로 일을 하는지 보는 반대쪽 입력이다.
const NSEC_BAD_CHECKSUM: &str = "nsec1vl029mgpspedva04g90vltkh6fvh240zqtv9k0t9af8935ke9laqsnlfe4";

fn test_cfg(inactivity: u64) -> Config {
    Config {
        ssh_host: "h".into(),
        ssh_user: "u".into(),
        ssh_identity_file: "k".into(),
        inactivity_seconds: inactivity,
    }
}

/// 통과하는 기본 페이로드. **축마다 이것을 한 군데씩만 바꿔** 쓴다 —
/// 한 입력에 결함을 둘 넣으면 어느 축이 잡았는지 알 수 없다.
fn test_payload() -> serde_json::Value {
    serde_json::json!({
        "name": "plan",
        "relay_url": "wss://relay.example",
        "private_key_nsec": NSEC_VECTOR,
        "auth_tag": serde_json::Value::Null,
        "respond_to": "owner-only",
        "respond_to_allowlist": [],
        "env_vars": { "FROM_LEGACY_ONLY": "must-not-appear" },
        "launch": {
            "command": "claude-agent-acp",
            "args": ["acp"],
            "env": { "GOOSE_MODE": "custom" },
            "policy_env": { "GOOSE_MODE": "auto", "BUZZ_ACP_LAZY_POOL": "true" },
            "owner_pubkey": "d690e3e5ccbe8a1c56d3deafbe622b1f8d18da77a18bad7b1ee1f31ec66c5a33"
        }
    })
}

fn env_for(payload: &serde_json::Value, cfg: &Config) -> Result<BTreeMap<String, String>, String> {
    build_env(payload, cfg, PUBKEY_VECTOR, "gen-1")
}

fn obs_base(intent: &str) -> Obs {
    Obs {
        has_state: true,
        meta_sha: "sha-1".into(),
        managed_by: MANAGED_BY.into(),
        meta_pubkey: PUBKEY_VECTOR.into(),
        meta_intent: intent.into(),
        active_state: "active".into(),
        sub_state: "running".into(),
        result: "success".into(),
        exec_main_status: "0".into(),
        uptime_secs: 60.0,
        agent_cmd_found: true,
        condition: String::new(),
    }
}

fn self_test() -> i32 {
    let mut failed = 0;
    let mut check = |name: &str, ok: bool| {
        println!("{} {}", if ok { "ok  " } else { "FAIL" }, name);
        if !ok {
            failed += 1;
        }
    };

    // ---- 배선 (info)
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
    check("info: config_schema 가 객체", i["config_schema"].is_object());
    let schema_text = i["config_schema"].to_string().to_lowercase();
    check(
        "I2: config_schema 에 자격증명 낱말이 없다",
        !["password", "secret", "token", "private_key", "nsec", "credential"]
            .iter()
            .any(|needle| schema_text.contains(needle)),
    );
    check(
        "모르는 op 은 거부한다",
        handle(&serde_json::json!({"op": "launch-missiles"}))["ok"] == serde_json::json!(false),
    );
    check(
        "op 이 없으면 거부한다",
        handle(&serde_json::json!({"request_id": "x"}))["ok"] == serde_json::json!(false),
    );

    // ---- 신원 (0단계). 축마다 입력을 따로 둔다.
    check(
        "신원: 공개 벡터 nsec 이 알려진 pubkey 로 유도된다",
        derive_pubkey_hex(NSEC_VECTOR).as_deref() == Ok(PUBKEY_VECTOR),
    );
    check(
        "신원: 체크섬이 깨진 nsec 은 거부한다 (bech32 가 헛돌지 않는다)",
        derive_pubkey_hex(NSEC_BAD_CHECKSUM).is_err(),
    );
    check(
        "신원: npub 은 거부한다 (hrp 를 실제로 본다)",
        derive_pubkey_hex(NPUB_VECTOR).is_err(),
    );
    check("신원: 빈 키는 거부한다 (I1)", derive_pubkey_hex("   ").is_err());

    // ---- base64 (알려진 벡터)
    check(
        "base64: RFC 4648 벡터",
        b64_encode(b"") == "" && b64_encode(b"f") == "Zg==" && b64_encode(b"fo") == "Zm8="
            && b64_encode(b"foo") == "Zm9v" && b64_encode(b"foob") == "Zm9vYg==",
    );
    check(
        "base64: 왕복한다 (관측 파서가 이 역을 쓴다)",
        b64_decode_lossy(&b64_encode("여러 줄\n둘째 줄".as_bytes())) == "여러 줄\n둘째 줄",
    );

    // ---- 셸 인용 (줄바꿈 든 시스템 프롬프트가 조용히 잘리는 자리)
    check("인용: 홑따옴표를 이스케이프한다", shell_quote("a'b") == r"'a'\''b'");
    let multi = env_file_text(&BTreeMap::from([("P".to_string(), "one\ntwo'three".to_string())]));
    check(
        "인용: 줄바꿈과 따옴표가 든 값이 온전히 실린다",
        multi.contains("P='one\ntwo'\\''three'"),
    );

    // ---- 환경 3층
    let env = env_for(&test_payload(), &test_cfg(7200)).expect("기본 페이로드는 통과해야 한다");
    check(
        "3층: launch.env 가 policy_env 를 이긴다",
        env.get("GOOSE_MODE").map(String::as_str) == Some("custom"),
    );
    check(
        "3층: policy_env 의 다른 키는 살아남는다",
        env.get("BUZZ_ACP_LAZY_POOL").map(String::as_str) == Some("true"),
    );
    check(
        "3층: 레거시 env_vars 를 다시 합치지 않는다",
        !env.contains_key("FROM_LEGACY_ONLY"),
    );
    check(
        "권위: 신원은 top-level 에서 온다",
        env.get("BUZZ_PRIVATE_KEY").map(String::as_str) == Some(NSEC_VECTOR)
            && env.get("NOSTR_PRIVATE_KEY").map(String::as_str) == Some(NSEC_VECTOR),
    );
    check(
        "권위: 원격에서 다시 푼 값 — 명령 이름과 MCP",
        env.get("BUZZ_ACP_AGENT_COMMAND").map(String::as_str) == Some("claude-agent-acp")
            && env.get("BUZZ_ACP_AGENT_ARGS").map(String::as_str) == Some("acp")
            && env.get("BUZZ_ACP_MCP_COMMAND").map(String::as_str) == Some(MCP_COMMAND),
    );
    check(
        "권위: 세대 토큰이 실린다",
        env.get("BUZZ_MANAGED_AGENT_START_NONCE").map(String::as_str) == Some("gen-1"),
    );

    // 사용자 층이 예약키를 덮으려 해도 못 덮는다 — 이 축만의 입력.
    let mut p = test_payload();
    p["launch"]["env"]["BUZZ_PRIVATE_KEY"] = serde_json::json!("nsec1ATTACKER");
    p["launch"]["env"]["BUZZ_ACP_AGENT_OWNER"] = serde_json::json!("dead");
    let env2 = env_for(&p, &test_cfg(7200)).expect("통과해야 한다");
    check(
        "예약키: 사용자 층의 신원 덮어쓰기가 안 먹는다",
        env2.get("BUZZ_PRIVATE_KEY").map(String::as_str) == Some(NSEC_VECTOR)
            && env2.get("BUZZ_ACP_AGENT_OWNER").map(String::as_str)
                == Some("d690e3e5ccbe8a1c56d3deafbe622b1f8d18da77a18bad7b1ee1f31ec66c5a33"),
    );

    // presence 끄기와 호스트 경로는 **지운다**(덮는 것으로는 부족하다).
    let mut p = test_payload();
    p["launch"]["env"]["BUZZ_ACP_NO_PRESENCE"] = serde_json::json!("1");
    p["launch"]["env"]["PATH"] = serde_json::json!("C:/Users/ojaej/bin");
    p["launch"]["env"]["CLAUDE_CODE_EXECUTABLE"] = serde_json::json!("C:/x/claude.cmd");
    let env3 = env_for(&p, &test_cfg(7200)).expect("통과해야 한다");
    check(
        "L1 2항: presence 를 끌 수 없다",
        !env3.contains_key("BUZZ_ACP_NO_PRESENCE"),
    );
    check(
        "호스트 경로: PATH·CLAUDE_CODE_EXECUTABLE 는 넘어가지 않는다",
        !env3.contains_key("PATH") && !env3.contains_key("CLAUDE_CODE_EXECUTABLE"),
    );

    let mut p = test_payload();
    p["launch"]["env"]["BAD NAME"] = serde_json::json!("x");
    p["launch"]["env"]["BUZZ_AUTH_TAG=x"] = serde_json::json!("y");
    let env4 = env_for(&p, &test_cfg(7200)).expect("통과해야 한다");
    check(
        "POSIX 이름: 이름에 숨긴 예약키가 안 들어온다",
        !env4.contains_key("BAD NAME") && !env4.contains_key("BUZZ_AUTH_TAG=x"),
    );

    // 수신 게이트 — 양쪽을 따로 본다.
    check(
        "게이트: owner-only 면 allowlist 를 안 싣는다",
        !env.contains_key("BUZZ_ACP_RESPOND_TO_ALLOWLIST")
            && env.get("BUZZ_ACP_RESPOND_TO").map(String::as_str) == Some("owner-only"),
    );
    let mut p = test_payload();
    p["respond_to"] = serde_json::json!("allowlist");
    p["respond_to_allowlist"] = serde_json::json!(["aa", "bb"]);
    let env5 = env_for(&p, &test_cfg(7200)).expect("통과해야 한다");
    check(
        "게이트: allowlist 면 목록을 싣고 owner-only 핀은 안 건다",
        env5.get("BUZZ_ACP_RESPOND_TO_ALLOWLIST").map(String::as_str) == Some("aa,bb")
            && !env5.contains_key("BUZZ_ACP_ALLOWED_RESPOND_TO"),
    );
    let mut p = test_payload();
    p["auth_tag"] = serde_json::json!("tag-1");
    let env6 = env_for(&p, &test_cfg(7200)).expect("통과해야 한다");
    check(
        "게이트: auth_tag 가 있으면 AGENT_OWNER 를 안 건다 (데스크톱과 같은 갈림)",
        env6.get("BUZZ_AUTH_TAG").map(String::as_str) == Some("tag-1")
            && !env6.contains_key("BUZZ_ACP_AGENT_OWNER"),
    );

    // 수명 정책 — 양쪽.
    check(
        "I5: inactivity>0 이면 종료 한도를 건다",
        env.get("BUZZ_ACP_EXIT_AFTER_INACTIVITY").map(String::as_str) == Some("7200"),
    );
    let env7 = env_for(&test_payload(), &test_cfg(0)).expect("0 은 합법이다");
    check(
        "I5: inactivity=0 은 «무기한» 이라 거부하지 않고 한도도 안 건다",
        !env7.contains_key("BUZZ_ACP_EXIT_AFTER_INACTIVITY"),
    );

    // ---- 닫히는 쪽으로 실패하는 자리들. 각각 다른 입력.
    let mut p = test_payload();
    p["launch"] = serde_json::Value::Null;
    check("거부: launch 블록이 없으면 배포하지 않는다", env_for(&p, &test_cfg(7200)).is_err());

    let mut p = test_payload();
    p["provider"] = serde_json::json!("relay-mesh");
    check("거부: relay-mesh 는 원격에서 닿을 수 없다", env_for(&p, &test_cfg(7200)).is_err());

    let mut p = test_payload();
    p["launch"]["owner_pubkey"] = serde_json::Value::Null;
    check(
        "거부: auth_tag 도 owner_pubkey 도 없으면 소유자가 없다",
        env_for(&p, &test_cfg(7200)).is_err(),
    );

    let mut p = test_payload();
    p["launch"]["command"] = serde_json::json!("/usr/local/bin/claude-agent-acp");
    check(
        "거부: launch.command 는 경로가 아니라 이름이어야 한다",
        env_for(&p, &test_cfg(7200)).is_err(),
    );

    let mut p = test_payload();
    p["respond_to"] = serde_json::json!("allowlist");
    check("거부: allowlist 인데 목록이 비면 거부한다", env_for(&p, &test_cfg(7200)).is_err());

    // ---- 지문
    let unit = unit_text("abc");
    let f1 = intent_fingerprint(&env, &unit);
    check("지문: 같은 입력이면 같다", intent_fingerprint(&env, &unit) == f1);
    let mut env_changed = env.clone();
    env_changed.insert("BUZZ_ACP_SYSTEM_PROMPT".into(), "너는 리서처다".into());
    check(
        "지문: 평범한 값이 바뀌면 달라진다",
        intent_fingerprint(&env_changed, &unit) != f1,
    );
    let mut env_nonce = env.clone();
    env_nonce.insert("BUZZ_MANAGED_AGENT_START_NONCE".into(), "gen-999".into());
    check(
        "지문: 세대 토큰만 바뀌면 같다 (안 그러면 재시도마다 살아 있는 봇을 갈아엎는다)",
        intent_fingerprint(&env_nonce, &unit) == f1,
    );
    let mut env_key = env.clone();
    env_key.insert("BUZZ_PRIVATE_KEY".into(), "nsec1OTHER".into());
    check(
        "지문: 키가 바뀌면 달라지되 지문 재료에 키 원문이 안 들어간다",
        intent_fingerprint(&env_key, &unit) != f1,
    );

    // ---- 유닛
    check(
        "유닛: Restart=no (알려진 결함 6 — 고정된 종료코드 계약 전에는 어떤 재시작 정책도 안 건다)",
        unit.contains("Restart=no") && !unit.contains("Restart=always") && !unit.contains("on-failure"),
    );
    check(
        "유닛: exec 라 종료 신호가 하네스에 직접 닿는다 (L1 3항)",
        unit.contains(&format!("exec {HARNESS_PATH}")) && unit.contains("TimeoutStopSec=60"),
    );

    // ---- 관측 파서를 **실물 바이트**에 고정한다.
    // 아래 둘은 2026-09-15 에 VPS 에서 그대로 받아 적은 출력이다(없는 인스턴스 / 35시간째 도는 봇).
    // 내가 상상한 꼴이 아니라 오는 꼴에 맞춘다 — 그 둘이 갈리면 화해 루프가 통째로 엉뚱해진다.
    let absent = parse_observation(
        "HAS_STATE=no\nResult=success\nExecMainStatus=0\nActiveState=inactive\n\
         SubState=dead\nActiveEnterTimestampMonotonic=0\nNowMono=468341460000\n\
         AGENT_CMD=found\nCONDITION_B64=\n",
    );
    check(
        "관측: 없는 인스턴스의 실물 출력을 그대로 읽는다",
        !absent.has_state && absent.active_state == "inactive" && absent.sub_state == "dead"
            && absent.agent_cmd_found && absent.uptime_secs == 0.0,
    );
    check(
        "관측: 그 관측은 «만들어라» 로 간다",
        reconcile(&absent, PUBKEY_VECTOR, "i", false) == Action::Create,
    );
    let live = parse_observation(
        "Result=success\nExecMainStatus=0\nActiveState=active\nSubState=running\n\
         ActiveEnterTimestampMonotonic=342003623344\nNowMono=468357350000\n",
    );
    check(
        "관측: 도는 유닛의 실물 출력에서 가동 시간이 나온다 (단조시계 두 값의 차)",
        (live.uptime_secs - 126353.7).abs() < 1.0 && live.started(),
    );

    // ---- 화해 루프. 행마다 입력을 따로 둔다.
    let intent = "intent-1";
    let mut o = obs_base(intent);
    o.has_state = false;
    check("화해: 상태가 없으면 만든다", reconcile(&o, PUBKEY_VECTOR, intent, false) == Action::Create);
    check(
        "화해: 살아서 정착했으면 손대지 않는다",
        reconcile(&obs_base(intent), PUBKEY_VECTOR, intent, false) == Action::NoOp,
    );
    let mut o = obs_base(intent);
    o.uptime_secs = 1.0;
    check(
        "화해: 떴지만 아직 정착 전이면 관찰이다",
        reconcile(&o, PUBKEY_VECTOR, intent, false) == Action::Observe,
    );
    let mut o = obs_base(intent);
    o.active_state = "activating".into();
    o.sub_state = "start".into();
    check(
        "화해: 기동 중이면 관찰이다 (지우지 않는다)",
        reconcile(&o, PUBKEY_VECTOR, intent, false) == Action::Observe,
    );
    let mut o = obs_base(intent);
    o.active_state = "failed".into();
    o.sub_state = "failed".into();
    check(
        "화해: 죽어 있으면 잔해를 치우고 다시 만든다",
        reconcile(&o, PUBKEY_VECTOR, intent, false) == Action::Replace,
    );
    let mut o = obs_base(intent);
    o.active_state = "deactivating".into();
    check(
        "화해: 내려가는 중이면 사라질 때까지 기다린다 (상태보다 먼저 본다)",
        reconcile(&o, PUBKEY_VECTOR, intent, false) == Action::WaitGone,
    );
    let mut o = obs_base(intent);
    o.managed_by = "someone-else".into();
    check(
        "화해: 우리가 만든 것이 아니면 수리하지 않고 보고한다",
        matches!(reconcile(&o, PUBKEY_VECTOR, intent, false), Action::Fail(_)),
    );
    let mut o = obs_base(intent);
    o.meta_pubkey = "0".repeat(64);
    check(
        "화해: pubkey 가 다르면 충돌로 실패한다 (잘린 이름은 충돌«저항»일 뿐이다)",
        matches!(reconcile(&o, PUBKEY_VECTOR, intent, false), Action::Fail(_)),
    );
    let mut o = obs_base("intent-OLD");
    o.uptime_secs = 1.0;
    check(
        "화해: 의도가 갈렸고 아직 안 떴으면 갈아엎는다",
        reconcile(&o, PUBKEY_VECTOR, intent, false) == Action::Replace,
    );
    check(
        "화해: 의도가 갈려도 **살아 있으면** 손대지 않는다 (반대쪽)",
        reconcile(&obs_base("intent-OLD"), PUBKEY_VECTOR, intent, false) == Action::NoOp,
    );
    let mut o = obs_base(intent);
    o.uptime_secs = 1.0;
    o.agent_cmd_found = false;
    check(
        "화해: 에이전트 명령이 없는 것이 확인되면 갈아엎는다",
        reconcile(&o, PUBKEY_VECTOR, intent, false) == Action::Replace,
    );
    let mut o = obs_base(intent);
    o.active_state = "failed".into();
    check(
        "화해: 이 호출이 만든 것은 같은 호출에서 다시 안 만든다 (한 번의 create)",
        matches!(reconcile(&o, PUBKEY_VECTOR, intent, true), Action::Fail(_)),
    );

    // ---- 시크릿이 새지 않는다
    let mut p = test_payload();
    p["provider"] = serde_json::json!("relay-mesh");
    let leaked = format!("{:?}", env_for(&p, &test_cfg(7200)));
    check("시크릿: 거부 메시지에 nsec 이 안 실린다", !leaked.contains(NSEC_VECTOR));
    let d = handle(&serde_json::json!({
        "op": "deploy",
        "agent": { "private_key_nsec": NSEC_VECTOR }
    }));
    check("시크릿: deploy 실패 응답에 nsec 이 안 실린다", !d.to_string().contains(NSEC_VECTOR));
    let plan = plan(&test_payload(), &test_cfg(7200), "gen-1").expect("계획은 서야 한다");
    check("시크릿: meta.json 에 키가 없다", !plan.meta_file.contains(NSEC_VECTOR));
    check(
        "계획: agent_id 와 인스턴스가 pubkey 앞 12자에서 온다",
        plan.instance == PUBKEY_VECTOR[..12]
            && plan.agent_id == format!("buzz-agent-{}", &PUBKEY_VECTOR[..12]),
    );
    check(
        "계획: meta.json 이 관리 표식과 전체 pubkey 를 든다",
        plan.meta_file.contains(MANAGED_BY) && plan.meta_file.contains(PUBKEY_VECTOR),
    );

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

