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
