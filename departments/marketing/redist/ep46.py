# -*- coding: utf-8 -*-
r"""ep46 재유통 보충 선언 (2026-09-12 신설).

🔴 **왜 편 폴더가 아니라 여기인가.** ep46 은 릴스 단독 편이라 빌더가 없고 `_facts.py` 도
   **아예 없다** — 선언이 어디에도 없어 유통 워커가 첫 줄에서 섰다(「릴스 편에 선언이 없다」).
   편은 이미 `01_발행완료` 에 있고 그 폴더는 정관 §2 어느 예외로도 못 고치므로 **본사에 둔다.**

값의 출처는 전부 실물이다 — 편 폴더의 `assemble_reel.py`(소스 파일·킷 칸)와
`_official\fx_2096536703330918831.json`(원 포스트 주소·영상 주소·길이), 발행로그 ep46 행.
"""

EP = 46

#: Threads 에 붙일 공식 원본 — 편이 쓴 그 영상 하나.
ATTACH_OFFICIAL = ("_official/higgsfield_wacom_ps_2096536703330918831.mp4",)

#: 릴스 재료가 된 공식 영상. `dur` 는 fxtwitter 가 준 값이다(22.416 → 소수 둘째 자리).
OFFICIAL_VIDEO = {
    "url": "https://video.twimg.com/amplify_video/2096536479480893440/vid/avc1/1440x1440/oRZxlSDp5FEoI226.mp4?tag=29",
    "dur": 22.42,
}

#: 킷은 ep43 것을 다시 쓴다 (assemble_reel.py 37행 · 발행로그 킷 칸과 같은 파일).
KIT = {
    "html": "gpt6-astra-try-kit.html",
    "url": "https://tomangchi-lab.github.io/kits/gpt6-astra-try-kit.html",
    "title": "GPT-6 Astra 첫날 써보기 킷",
}

# ── 인용 정본 (2026-09-12 신설) ──────────────────────────────────────────────
#: 🔴 **이 값들은 우리가 적은 것이라 그 자체로는 근거가 아니다.** 편 폴더에 `_facts.py` 가 없어
#:    여기 두는 것뿐인데, 두는 순간 «우리가 베껴 적고 우리가 그것과 대조하는» 자기 서명이 된다.
#:    그래서 게이트 `[1-1]` 이 **편 검증로그 원문에 이 문자열이 그대로 있는지** 되잰다 —
#:    검증로그는 `01_발행완료` 안이라 우리가 못 고친다(정관 §2). 한 글자만 다듬어도 선다.
#: 🔴 **꼴이 곧 검사 대상이다** — `[1-1]` 이 보는 것은 **(인용문, 출처) 2-튜플**뿐이다.
#:    `KIT`·`ATTACH_OFFICIAL`·`OFFICIAL_VIDEO` 는 인용이 아니라 지목이라 대상이 아니다.
SRC_X = "x.com/higgsfield_ai/status/2096536703330918831"
SRC_LOG = "ep46 검증로그 — 프레임 시트 실측 (1/3/6/9/13/20s)"

#: X 본문 첫 문장. 🔴 **힉스필드 자기 보고다** (검증로그 «귀속 판정») — 출처 줄이 진다.
PAINTING = ("GPT-6 Astra makes amazing background painting.",
            SRC_X)
#: X 본문 둘째 문장 — «Cintiq 22»·«Higgsfield Plugin»·«end-to-end» 가 여기 있다.
DRAW = ("It takes full control of a Wacom Cintiq 22, professional drawing tablet, then plugs "
        "straight into Photoshop through the Higgsfield Plugin, and draws a nighttime cityscape "
        "in comic book style end-to-end.",
        SRC_X)
#: 힉스필드 changelog 2026-09-04.
SUPERCOMPUTER = ("GPT-6 Astra, OpenAI's new flagship model, is now available in Supercomputer.",
                 SRC_X)
#: 그리는 차례 — X 본문이 아니라 **우리 프레임 시트 실측**이 근거다(검증로그 인용 대조 표).
ORDER = ("흰 캔버스 → 연필 선 → 검은 실루엣 → 밤하늘·가로등 → 창문 불빛·간판 → 차·횡단보도",
         SRC_LOG)
