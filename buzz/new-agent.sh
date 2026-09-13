#!/usr/bin/env bash
# 새 Buzz 봇 하나를 세운다. VPS 에서 돈다.
#
#   bash /srv/company/buzz/new-agent.sh <역할이름> "<표시이름>" "<소개>" [에이전트CLI]
#
# 다섯 단계를 묶은 이유: 손으로 하면 4단계(reconcile)를 빠뜨리기 쉬운데,
# 빠뜨려도 아무 오류가 안 나고 봇이 «discovered 0 channel(s)» 로 조용히 앉아 있는다
# (2026-09-10 실측). 정관 §0 «조용히 실패하는 코드를 남기지 않는다».
set -euo pipefail

die() { printf '\n[new-agent] 중단: %s\n' "$1" >&2; exit 1; }
say() { printf '[new-agent] %s\n' "$1"; }

NAME="${1:-}"
DISPLAY="${2:-${NAME}}"
ABOUT="${3:-JJ Company ${NAME}}"
AGENT_CMD="${4:-claude-agent-acp}"

RELAY_C=buzz-lku2-relay-1
PG_C=buzz-lku2-postgres-1
COMMUNITY=b5985445-8712-4c93-9836-fc6a0436f9ee
CHANNEL=ad2b0814-2ba6-506e-8b5d-3254dec9f27d   # #general
REPO=/srv/company
KEYDIR=/root/buzz-keys
ENVDIR=/etc/buzz-acp
PERSONA="${REPO}/buzz/agents/${NAME}.md"
UNIT_SRC="${REPO}/buzz/buzz-acp@.service"
UNIT_DST=/etc/systemd/system/buzz-acp@.service

# --- 0. 가드 (전부 통과해야 한 글자도 쓰지 않는다) -------------------------
[ -n "$NAME" ] || die "역할 이름이 없다. 사용법: new-agent.sh <이름> \"<표시이름>\" \"<소개>\" [CLI]"
printf '%s' "$NAME" | grep -Eq '^[a-z][a-z0-9-]{1,20}$' \
  || die "이름은 소문자/숫자/하이픈 2~21자여야 한다: ${NAME}"
[ -f "$PERSONA" ] || die "역할 정의가 없다: ${PERSONA}
  레포에 buzz/agents/${NAME}.md 를 먼저 넣고 머지한 뒤, 미러가 동기화되면 다시 부른다."
[ ! -e "${KEYDIR}/${NAME}.env" ] || die "이미 신원이 있다: ${KEYDIR}/${NAME}.env
  다시 만들려면 사람이 직접 지운다 - 지우면 그 봇의 과거 발화와 신원이 끊긴다."
command -v docker >/dev/null || die "docker 가 없다"
docker ps --format '{{.Names}}' | grep -qx "$RELAY_C" || die "릴레이 컨테이너가 안 보인다: ${RELAY_C}"
[ -f "${ENVDIR}/common.env" ] || die "공통 env 가 없다: ${ENVDIR}/common.env"

# 🔴 reconcile 이 릴레이 키 없이 돌면 «임시 키로 서명» 하고 성공한 척한다 -
#    그 이벤트는 릴레이가 재시작하면 검증 불가가 된다(--help 실측). 미리 막는다.
docker exec "$RELAY_C" sh -c 'test -n "$BUZZ_RELAY_PRIVATE_KEY"' \
  || die "릴레이 컨테이너에 BUZZ_RELAY_PRIVATE_KEY 가 없다 - reconcile 이 임시 키로 서명한다"

RELAY_HTTPS="$(sed -n 's/^BUZZ_RELAY_URL=wss:/https:/p' "${ENVDIR}/common.env")"
[ -n "$RELAY_HTTPS" ] || die "common.env 에서 릴레이 주소를 못 읽었다"

say "정의 ${PERSONA} · CLI ${AGENT_CMD} · 표시이름 ${DISPLAY}"

# --- 1. 유닛 템플릿 (없으면 깐다) -----------------------------------------
if ! cmp -s "$UNIT_SRC" "$UNIT_DST"; then
  install -m 0644 "$UNIT_SRC" "$UNIT_DST"
  systemctl daemon-reload
  say "유닛 템플릿 설치/갱신"
fi

# --- 2. 신원 --------------------------------------------------------------
# 🔴 여기서부터는 실물이 생긴다. 도중에 죽으면 «반쪽 상태»가 남아 다음 실행이
#    0단계 가드에 걸려 영영 못 돈다 - 그래서 만든 것을 되돌리고 무엇이 남았는지 말한다.
KEY_MADE=""
cleanup() {
  [ -n "$KEY_MADE" ] || return 0
  systemctl disable --now "buzz-acp@${NAME}" >/dev/null 2>&1 || true
  rm -f "${KEYDIR}/${NAME}.env" "${ENVDIR}/${NAME}.env"
  printf '[new-agent] 되돌림: 키·역할 env 를 지웠다. 다시 부르면 새 신원으로 처음부터 간다.\n' >&2
  printf '[new-agent] 🔴 남았을 수 있는 것: 릴레이 멤버 %s\n' "$KEY_MADE" >&2
  printf '[new-agent]    지우려면: docker exec %s buzz-admin remove-member --pubkey %s\n' "$RELAY_C" "$KEY_MADE" >&2
}
trap cleanup EXIT

KEYOUT="$(docker exec "$RELAY_C" buzz-admin generate-key)"
PUB="$(printf '%s' "$KEYOUT" | sed -n 's/.*Public key:[[:space:]]*\([0-9a-f]\{64\}\).*/\1/p')"
SEC="$(printf '%s' "$KEYOUT" | sed -n 's/.*Secret key:[[:space:]]*\([0-9a-f]\{64\}\).*/\1/p')"
[ ${#PUB} -eq 64 ] && [ ${#SEC} -eq 64 ] || die "키 생성 출력이 예상과 다르다 (값은 찍지 않는다)"

KEY_MADE="$PUB"
( umask 077; printf 'BUZZ_PRIVATE_KEY=%s\nBUZZ_PUBKEY=%s\n' "$SEC" "$PUB" > "${KEYDIR}/${NAME}.env" )
chmod 600 "${KEYDIR}/${NAME}.env"
say "신원 발급 · 공개키 ${PUB}"   # 🔴 비밀키는 어디에도 찍지 않는다

# --- 3. 릴레이 멤버 -------------------------------------------------------
docker exec "$RELAY_C" buzz-admin add-member --pubkey "$PUB" >/dev/null
say "릴레이 멤버 등록"

# --- 4. 채널 멤버 ---------------------------------------------------------
# 🔴 role 은 반드시 'member' 다. 'bot' 으로 넣으면 앱이 «관리형 에이전트»로 분류해
#    @ 멘션 목록에서 통째로 숨긴다 (2026-09-10 실측 · 그 반대로 고쳤다).
OWNER="$(sed -n 's/^BUZZ_ACP_AGENT_OWNER=//p' "${ENVDIR}/common.env")"
docker exec -i "$PG_C" psql -U buzz -d buzz -v ON_ERROR_STOP=1 -q <<SQL
INSERT INTO channel_members (community_id, channel_id, pubkey, role, invited_by)
VALUES ('${COMMUNITY}', '${CHANNEL}', decode('${PUB}','hex'), 'member', decode('${OWNER}','hex'))
ON CONFLICT (community_id, channel_id, pubkey) DO NOTHING;
SQL
say "채널 멤버 삽입"

# --- 5. 🔴 reconcile — 이것을 빼면 위 행이 있어도 봇은 채널을 0개로 본다 ----
docker exec "$RELAY_C" buzz-admin reconcile-channels --channel "$CHANNEL" >/dev/null
say "채널 로스터 재발행"

# --- 6. 프로필 — 없으면 @ 목록에 안 뜬다 ----------------------------------
BUZZ_PRIVATE_KEY="$SEC" BUZZ_RELAY_URL="$RELAY_HTTPS" \
  buzz users set-profile --name "$DISPLAY" --about "$ABOUT" >/dev/null
say "프로필 등록"

# --- 7. 역할 env + 기동 ---------------------------------------------------
cat > "${ENVDIR}/${NAME}.env" <<ENV
BUZZ_ACP_AGENT_COMMAND=${AGENT_CMD}
BUZZ_ACP_SYSTEM_PROMPT_FILE=${REPO}/buzz/agents/${NAME}.md
BUZZ_ACP_SESSION_TITLE=${DISPLAY}
ENV
chmod 644 "${ENVDIR}/${NAME}.env"
systemctl enable --now "buzz-acp@${NAME}" >/dev/null 2>&1
say "유닛 기동"

# --- 8. 검증 — 「깔았다」로 끝내지 않는다 (정관 §0) -------------------------
sleep 10
STATE="$(systemctl is-active "buzz-acp@${NAME}" || true)"
LOG="$(journalctl -u "buzz-acp@${NAME}" --since '-2 min' --no-pager 2>/dev/null || true)"
CH="$(printf '%s' "$LOG" | sed -n 's/.*discovered \([0-9]\+\) channel.*/\1/p' | tail -1)"

printf '\n'
say "상태: ${STATE}"
say "채널: ${CH:-(로그에서 못 읽음)}"
[ "$STATE" = active ] || die "유닛이 active 가 아니다. journalctl -u buzz-acp@${NAME} -n 50"
case "${CH:-0}" in
  ''|0) die "채널을 0개로 본다 - 4단계(reconcile)나 3단계가 안 먹었다.
  이 상태의 봇은 멘션을 받지 못하면서도 살아 있는 것처럼 보인다." ;;
esac
KEY_MADE=""   # 여기까지 왔으면 되돌리지 않는다
say "완료. #general 에서 @${DISPLAY} 로 불러 실제로 답하는지 확인한다."
