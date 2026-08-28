# ep35~38 원본 재료 전수 재점검 (2026-08-28)

> **왜 다시 봤나.** ep36 에서 **개별 X 포스트는 「영상 없음」인데 스레드 루트로 받으니 5개가 나왔다.**
> 조회 경로 하나로 «없다»를 판정하면 있는 것을 못 본다. 네 편 전부 같은 방법으로 다시 훑고,
> **공식 블로그·문서·모델 페이지 안의 임베드 영상·이미지까지** 전수로 봤다.
>
> **결론 한 줄** — ep36·ep38 에서 **실을 만한 공식 재료가 각각 나왔다.** ep35 는 블로그 원문에
> 카드 후보가 셋 있고 **`_facts.py` 의 사실 오기 1건**이 같이 나왔다. ep37 은 하나 나왔다.

## 방법 (네 편 공통)

| 경로 | 도구 | 왜 |
|---|---|---|
| X 스레드 **루트** | `py -m yt_dlp <루트 URL>` | 개별 포스트 조회는 스레드 안 영상을 못 본다(ep36 실측) |
| X 스레드 **답글 전수** | `conversation_id:<id> from:<계정>` | 루트에 없는 첨부 이미지가 답글에 있다 |
| X 첨부 이미지 | `cdn.syndication.twimg.com/tweet-result` → `pbs.twimg.com` | `yt-dlp` 는 영상만 본다 |
| 공식 페이지 | Playwright 로 열어 `img`/`video`/`source`/`iframe` **DOM 전수** | 블로그·모델 페이지의 임베드는 어떤 X 조회로도 안 나온다 |
| 탭이 있는 페이지 | 탭을 **눌러 가며** 영상 src 수집 | 안 누른 탭의 `<video>` 는 DOM 에 없다 |

🔴 **마지막 두 줄이 이번 회차의 수확이다.** 종전 회차는 X 만 봤고, 그래서 **공식 페이지 안의 제품 UI 영상을 통째로 놓쳤다.**

---

## ep38 — Meta Muse Image

### 🔴 있는데 안 실은 것 — **공식 모델 페이지에 제품 UI 영상 4편**

`developer.meta.com/ai/models/muse-image/` 의 «Muse Image in action» 은 탭 4개이고 **각 탭에 영상이 붙어 있다.**
편 조사(8/27)는 X 만 봤고, X 영상은 **전 구간 브랜드 애니메이션**이라 «영상 미포함»으로 판정했다.
**모델 페이지 쪽은 성격이 정반대다** — 전부 실제 제품 UI·호출·결과다.

| 탭 | 길이 | 크기 | 무엇이 보이는가 | 채택 견적 |
|---|---|---|---|---|
| **Precise editing** | **22.13초** | 1280x720 | 캔 사진 한 장에 `POST /images/edits` 를 세 번 — 「add a hibiscus bloom」 → 「add fresh peach halves」 → 「make the band match the hibiscus」. **호출·프롬프트·참고 이미지 칩·결과가 한 화면에** 있고 「three edits, same photo.」로 끝난다 | 🟢 **최우선.** 이 편이 **못 써 본 편집 엔드포인트**(404)를 공식이 보여 주는 자리다 |
| **Anchored composition** | 12.80초 | 1280x720 | Brand Kit 4종(Model·Bottle·Ridge·Palette) → 「COMPOSED FROM 4 REFERENCES」 → 결과. 「four references, one on-brand image.」 | 🟢 카드 02(앵커)의 **움직이는 근거**. 이 편이 못 써 본 합성이다 |
| Multi-turn refinement (fal) | 28.00초 | 1280x720 | fal 화면에서 책 표지를 4회 편집 — 「4 EDITS SAME COVER」 | 🟡 **fal 배지**가 붙어 있어 크레딧이 «Meta 공식»이 아니라 «fal 데모»다. 쓰면 그렇게 적어야 한다 |
| Image generation | 14.53초 | 1280x720 | 「Persona Forge」 앱에서 소 한 마리를 6가지 화풍으로 — `endpoint /images/edits · identity held` | 🟡 서드파티 앱 화면 |

- **§7 규칙 9 기준**: 넷 다 **정보 프레임이 전 구간**이다(제품 UI·조작·결과). 브랜드 애니메이션 구간이 없다.
- **X 영상(10.176초)의 미포함 판정은 그대로 유효하다** — 그건 여전히 해바라기 브랜드 연출이다.
  두 판정이 충돌하지 않는다: **«이 소재에 공식 영상이 없다»가 아니라 «X 에 있는 그 영상이 정보 구간이 아니다»**였다.
  🔴 **그런데 발행팩 절 제목이 「공식 영상 미포함 사유」라 전자로 읽힌다.** 문구를 고쳐 두었다.
- **견적**: 카드 1장 추가(덱 8 → 9)거나, 카드 03(공식 데모) 자리를 **정지 → 영상 카드**로 교체.
  후자면 덱 길이가 그대로다. **JJ 판정 자리.**

### 🔴 있는데 안 실은 것 — 블로그 이미지의 **«전» 절반**

공식 블로그의 그림은 대부분 **짝**이다. 편은 그중 «후»만 실었다. 이번 회차에 **셋을 짝으로 되돌렸다**(C-6).

| 짝 | 전 | 후 | 처리 |
|---|---|---|---|
| 다단계 편집 | `Busy listing photo` 1920x1280 | `Updated listing - boots removed, $12→$8` | ✅ **이번에 카드 03 을 전/후 + 값표 확대 2단으로** |
| 앵커 합성 | `Hero character sheet and city location plate` 1652x840 | `Anchored comic panels` 1800x600 | ✅ **이번에 카드 02 를 위/아래 2단으로** |
| 편집(여우) | `Watercolor fox` | `Fox with red wool hat` | ⚪ 미사용 — 위 짝과 논지가 겹친다 |
| 합성(여우·머그·화병) | `Input set - fox mug vase` 1999x474 | `Composed fox mug vase` | 🟡 **합성은 이 편이 못 재 본 자리**라 후보. Anchored composition 영상과 택일 |
| 값표 생성 | `Item photos - lamp guitar books` 1800x600 | `For-sale grid with price tags` | ⚪ 미사용 |

- 🟢 **부수 소득**: 전·후 원본을 **공식 CDN 에서 1920x1280 로** 받아 `_official/` 에 두었다.
  종전 카드는 `webshot` 크롭본이었다 — **원본이 더 크고 잘림 위험이 없다.**
- ⚪ **안 쓰기로 유지**: `Muse Image quality comparison` 2306x1468 — Meta 가 고른 예시라
  «품질이 좋다»로 읽힌다(검증로그 §6 판정 그대로).

### 없는 것

- **ep38 X 스레드에 다른 영상은 없다.** `MetaforDevs` 두 포스트 모두 같은 10.176초 클립이다(재확인).
- fal 파트너십 포스트(`2092754469964730552`)는 X 에서 `No video formats found` 인데,
  🟢 **같은 28초 클립을 모델 페이지에서 받을 수 있다**(위 표 3행). 「받히지 않는다」는 **X 경로 한정**이었다.

---

## ep36 — Google 음성 묶음

### 🔴 있는데 안 실은 것 — 공식 블로그의 **Transcribe 영상 6편**

편 조사는 X 7건을 훑고 «@Google 10.00초는 로고 애니메이션이라 뺀다»로 닫았다.
**공식 블로그(`blog.google/.../gemini-3-5-transcribe/`)에는 다른 영상이 6편 있다.**

| 파일 | 길이 | 크기 | 무엇이 보이는가 | 견적 |
|---|---|---|---|---|
| **`Copy_of_SxS-Transcribe_Blog_Border_V1.mp4`** | **36.42초** | 1920x1080 | 🟢 **VERBATIM MODE ↔ SMART TRANSCRIPTION 을 좌우로 동시에** 띄우고 같은 발화를 실시간으로 받아쓴다. 왼쪽은 「um」·말 고침을 전부 남기고, 오른쪽은 「Actually, make the hazelnut into caramel, remove the extra shot」을 **정리해 반영한다** | 🟢 **최우선.** 카드 02 의 논지(「음…」 지우고 고쳐 말한 것도 알아들음)를 **그대로 보여 준다.** 지금 카드 02 는 **블로그 기능 목록 스크린샷**이라 주장만 있고 근거가 없다 |
| `GoogleDemoLab_Transcribo.mp4` | 44.87초 | 1920x1080 | 데모 랩 | 🟡 |
| `3.5_Transcribe_Live.mp4` | 35.80초 | 1920x1080 | 라이브 받아쓰기 | 🟡 |
| `Rambler_Blog.mp4` | 29.00초 | 2784x1566 | Rambler(안드로이드) | ⚪ 이 편 범위 밖 |
| `GeminiApp_Mac.mp4` | 128.07초 | 1920x1080 | macOS 워크스루 | ⚪ 편이 이미 «말만 나오는 구간»으로 기각 |
| `Demo_Phonos_A2A_Whiteboard.mp4` | 36.70초 | 3840x2160 | 화이트보드 데모 | ⚪ |

- 🟢 **SxS 영상은 C-6(전·후 한 카드) 원칙에도 정확히 맞는다** — 전/후가 **한 프레임 안에** 있다.
- 🔴 **이 편은 「우리가 잰 화면이 0장」이라 릴스를 포기한 편이다**(C-1). SxS 영상이 들어가면
  **남의 데모라는 성격은 그대로**지만, 지금 캐러셀의 가장 약한 카드(02)가 근거를 얻는다.
- 이미지 1건도 안 실렸다 — `Graph of streaming speech recognition accuracy` 1000x562.
  🟡 **자기 보고 수치**라 `[5-5]` 라벨이 필요하다.

### 없는 것

- **X 쪽은 전수 재확인 완료** — `GeminiApp` 루트 5편(6.48·23.0·23.73·16.03·15.0초)·`Google` 10.0초·
  `GoogleAI` 128.13초·`antigravity` 32.07초. **편 검증로그의 표와 일치한다.**
- `ai.google.dev/gemini-api/docs/transcribe` — `<video>` 2개가 **전부 빈 src** 다. 실질 영상 **무**.
- 🔴 **검증로그의 소스 URL 이 `blog.google/…/` 로 줄여져 있다.** 그 주소로는 다시 조회할 수 없다
  (실제로 이번에 404 를 맞고 검색으로 되찾았다). 정관 §0 «실물이 정본» 계열 — **URL 은 전문으로 적는다.**

---

## ep37 — Claude Code 피드백 초안

### 🔴 있는데 안 실은 것 — **공식 발표 이미지 1장**

`x.com/ClaudeDevs/status/2092695038270775647` 첨부(`pbs.twimg.com/media/HQq-wI9acAAg50q.jpg`, **2048x1075**).

- **무엇이 보이는가**: 터미널 실물. 사용자 불평 → Claude 답 → `Worked for 31s` →
  주황 테두리 상자에 **`Bug report drafted: Sandbox image pull fails behind proxy`** ·
  `What happened: image pull returned 403 via corporate proxy; mirror fallback was never attempted…` ·
  **`1 to review · 2 to send · 0 to dismiss`**.
- **왜 중요한가**: **이 편 덱에 공식 제품 화면이 한 장도 없다.** 카드 02·05 는 GitHub 텍스트 캡처이고
  03·04·06 은 우리 도해다. 기능이 실제로 어떻게 보이는지 보여 주는 판이 **하나도 없다.**
- 🟡 **단서**: 이미지 헤드라인이 「Claude Code now drafts the **bug** report for you.」다.
  편 검증로그는 「공식 표현은 feedback 이고 종류는 셋(bug·idea·missing_capability)이라
  «버그»만 쓰면 좁힌 것」이라고 이미 못박았다. **이미지를 쓰면 그 긴장을 카드가 다뤄야 한다** —
  오히려 «공식 홍보문도 버그라고 부르지만 실제로는 셋이다»가 이 편의 차별점이 된다.
- **견적**: 카드 02 의 상단 실물을 릴리스 노트 캡처 → 이 이미지로 **교체**(덱 길이 불변).
  크레딧 `X / @ClaudeDevs`.

### 없는 것

- 영상 **무** 재확인 — 스레드 루트 `yt-dlp` `No video`, 답글 2건도 영상 없음,
  `code.claude.com/docs/en/settings` 임베드 영상 0.

---

## ep35 — GLM-5.3-Flash / Ox Alpha (블로그 전수 열람)

`z.ai/blog/glm-5.3-flash` 는 JS 렌더라 `WebFetch` 가 **빈 문서**를 돌려준다. Playwright 로 열어
**본문 13,004자 · 이미지 14(실질 8) · 영상 0 · 표 2** 를 전수로 읽었다.

### 🔴 사실 오기 1건 — `_facts.py` `LAYERS`

```python
LAYERS = (45, 92)                     # Flash · GLM-5.3     ← 주석이 틀렸다
```

블로그 원문: “**Compared with the GLM-4.5 series** … it nearly halves both the activated parameter
count (18B vs. 32B) and the number of layers (**45 vs. 92**).”
→ **45 vs 92 는 GLM-4.5 대비**다. `REDUCE = (3.0, 4.4)` 쪽이 GLM-5.3 대비다.
**같은 문장이 `docs.z.ai/guides/llm/glm-5.3-flash` 에도 그대로 있다**(두 출처 대조 완료).

- **어디까지 샜나**: `_facts.py` 주석과 **검증로그 §사양 표 70행**(「45 (GLM-5.3 은 92)」).
  🟢 **카드·킷·캡션에는 안 들어갔다** — 이 값을 싣는 판이 없다. 발행물 오류는 아니다.
- ✅ **이번 회차에 고쳤다** — 주석과 표를 「GLM-4.5 는 92」로 정정하고 근거를 「블로그·docs 원문」으로 바꿨다.
  ep35 재빌드·게이트 27항 재실행 `STATUS: OK`.
- **왜 새는가**: 검증로그의 «사양» 표가 **비교 대상을 안 적는 칸**을 갖고 있다. 「45」만 적으면
  다음 사람이 «무엇 대비 45인가»를 채워 넣게 되고, 그때 가장 가까운 이름(GLM-5.3)을 집는다.

### 있는데 안 쓴 것 — 카드 후보 셋

| 후보 | 원본 | 왜 후보인가 | 견적 |
|---|---|---|---|
| **시각 자기검증 전/후** | `Initial Version with Layout Issues` 1412x788 ↔ `After Visual Self-Verification` 2318x1298 | 🟢 **깨진 레이아웃 → 고친 레이아웃**이 **짝으로** 있다. 글자가 겹치고 차트 라벨이 뭉개진 판이 정상으로 바뀐다. 블로그의 머리 주장(**GLM-5 계열 첫 네이티브 멀티모달**)을 **눈으로 확인시키는 유일한 그림**이고, C-6 «전·후 한 카드»에 그대로 맞는다 | 🟢 **최우선.** 지금 덱에 멀티모달·시각 카드가 **0장**이다 |
| **AAI Pareto 도표** | 2306x1468 상당 `Pareto frontier of the AAI Index v4.1.1` | «GLM-5.3-Flash (discounted) **$0.045 · 57 pts**» 가 점 하나로 찍히고, 같은 높이의 다른 모델들이 **10배 오른쪽**에 있다. 편의 축(싸다)을 한 장으로 말한다 | 🟡 **자기 보고 인용**(출처는 Artificial Analysis). `[5-5]` 라벨 필요 |
| **OpenCode 사용량** | `Top Models. Usage of models across OpenCode.` 2528x1302 | ox-alpha **43T** · 2위 22T. 지금 `_facts` 는 **OpenRouter 23.2T 만** 갖고 있다 — **두 번째 유통처에서도 1위**라는 독립 데이터 | 🟡 카드 추가보다 **킷 한 줄**이 맞다 |

### FACTS 보강 후보 (블로그에만 있고 `_facts.py` 에 없는 값)

- **AAI 57 점이 `$0.045/task`(할인가)** — “a level of intelligence previously only available at roughly **10× the cost**”.
- **Z.ai Code Bench v1.0**(Claude Code 2.1.207) **max 29.0 vs Opus 4.8 29.5** — X 스레드 이미지에도 있다.
  🔴 같은 도표에 **Claude Fable 5 가 39.5** 로 훨씬 위다. 「Opus 4.8 근처」는 맞지만 **최상단은 아니다** — 카드 04 문구가 이미 그렇게 적혀 있다(문제 없음).
- **AutomationBench 48.8 vs 26.2**(GLM-5.2 대비 가장 큰 폭).
- **베이스 모델 표** — MMLU 88.1 · BBH 86.6 · HellaSwag 87.1 · LiveCodeBench-Base 37.6 · SimpleQA 33.5.
- 🟢 **공식이 스스로 적은 한계**: “The KV cache size is still **slightly larger than Kimi-K3 and
  DeepSeek-V4-Flash**, leaving further room for improvement.” — **자기 약점을 적은 자리**라
  우리 «자랑과 단서» 축에 맞는다.
- 아키텍처 고유명사: hybrid sparse+linear attention · **mHC**(Manifold-Constrained Hyper-Connections) ·
  **IndexPool**(indexer key 4개 → 1개 pooling) · EPD 분리 아키텍처 · SGLang 기반 엔진 · W8A8 ·
  INT8/FP8/BF16 캐시 양자화 · Layer Split · ReplaySSM.
- 서빙: 중국산 칩 클러스터에서 **초기 대비 3배** 개선, “per-token cost comparable to mainstream NVIDIA GPUs”.
- 로컬 추론: **SGLang · vLLM · TokenSpeed**. Coding Plan **3배 쿼터**. ZCode 의 Browser Use / Computer Use.

### 없는 것

- **영상 0** — 블로그 DOM 에 `<video>`·`<source>`·iframe **0개**(편 검증로그와 일치).
- X 스레드 답글 3건 중 **2건에 첨부 이미지**가 있다(«intelligence with less compute» 도표 · Code Bench 도표).
  둘 다 위 표의 블로그 이미지와 **같은 그림**이다 — 새 재료가 아니다.

---

## ✅ 처분 (2026-08-28 · JJ 승인 — 넷 다 편입)

| 편 | 무엇 | 어떻게 | 덱 |
|---|---|---|---|
| ep38 | 모델 페이지 **Precise editing** 22.13초 | **새 카드**(뱃지 05) — `POST /images/edits` 3회. 이 편이 «못 써 봤다»고 적은 자리다 | 8 → **9장** |
| ep36 | 블로그 **SxS** 36.42초 | 카드 01 상단 실물 **교체** — VERBATIM ↔ SMART 좌우 동시 | 8장 유지 |
| ep37 | 공식 발표 이미지 2048x1075 | 카드 01 상단 실물 **교체** — 터미널 실물·초안 상자 | 8장 유지 |
| ep35 | 시각 자기검증 **전/후 짝** | **새 카드**(뱃지 05) — 전체 짝 + 겹침 확대 2단 | 8 → **9장** |

**게이트 27항 전수 재실행 — 네 편 다 `STATUS: OK`.**

### 영상 둘은 **자르지 않고 여백을 넣었다**

`videocard` 의 «덮기»는 판 비율(1.392)보다 납작한 영상의 **좌우를 깎는다.** 두 소재 모두 그 자리에
읽어야 할 것이 있었다 — ep36 은 두 단 중 한쪽 글자, ep38 은 오른쪽 호출 패널의 프롬프트.
🔴 **ep38 은 1차 시도에서 실제로 잘렸다**(프롬프트가 «add a hibiscus bloom at the bas…» 로 끊김).
판 비율에 맞게 **위아래 여백**을 넣어 다시 만들었다 — ep36 1920x1080 → 1920x1380,
ep38 1280x720 → 1280x920. §6 크롭 규칙과 같은 선택이다.

### 편입이 **검사 셋을 깨뜨렸다** — 내용은 그대로인데

`REQUIRED` 람다가 카드를 **자리**(`CARDS["05"]`)로 가리키고 있었다. 카드를 하나 끼우자
ep35 하나·ep38 둘이 깨졌다. 내용으로 찾도록 고쳤고 조문 안건 **C-8** 로 등재했다.
SKILL §6.8 «자리 기반 이름은 순서가 바뀌면 전부 거짓이 된다»가 씬 이름에만 적혀 있고
람다에는 안 적혀 있던 자리다.

### 유통 워커가 **빈 지시서**를 내고 있었다

`shot`/`dur` 이 `F.VIDEO_SRC` 를 가리키는 편은 `CARDS` 파싱이 실패하는데 **조용히 `{}` 로 떨어졌다.**
ep36 은 처음부터 그 상태였다(주장 0건). 참조를 풀도록 고치고 **못 읽으면 죽게** 했다 —
ep36 주장 **0 → 24건**. 인프라 백로그 **9번**.

### 다시 판정이 필요한 자리 하나 (ep36)

이 편은 «우리가 잰 화면이 0장»이라 릴스를 포기했다(C-1). 영상 카드가 하나에서 **둘**로 늘어
캐러셀 8장 중 둘이 남의 데모가 됐다. **카드는 정확해졌고 채널 결은 반대로 갔다** —
그대로 갈지, 카드 01 을 종전 캡처로 되돌릴지, 카드 03 을 뺄지는 발행 전 판정 자리다.
되돌리는 방법은 ep36 발행팩에 적어 두었고 **파일은 둘 다 남아 있다.**

---

## 남은 판정 (JJ)

1. **ep38** — 모델 페이지 «Precise editing» 22초를 넣는가. 넣으면 카드 03 교체인가 덱 9장인가.
2. **ep36** — 블로그 SxS 36초를 넣는가. 카드 02 의 상단 실물을 교체하는가.
3. **ep37** — 공식 발표 이미지로 카드 02 상단을 교체하는가.
4. **ep35** — 시각 자기검증 전/후를 카드로 넣는가. **`LAYERS` 주석 오기는 판정과 무관하게 고쳐야 한다.**

> 🔴 **넷 다 «넣으면 더 좋다»이지 «없으면 틀렸다»가 아니다.** 이번 회차에서 **실제로 고친 것은
> ep38 세 판**(전/후 복원)이고, 나머지는 목록과 견적까지다 — 발행 순서와 마감(ep35 9/9 16:00 UTC)이
> 걸려 있어 덱 구조 변경은 지목 승인 자리로 남긴다.
