// 레벨 정의 + 참조 해답
//
// **스코프 락 준수**: 기계는 SCOPE.md 의 4종(소스/검수기/싱크/폐기)뿐이다.
// 레벨 2~5 에서 새로 생긴 메카닉은 없다 — 바뀌는 것은 배치·불량률·목표·소스 개수뿐.
//
// 난이도 곡선
//   L1 직선 기본기 → L2 코너 활용 → L3 불량 비율 상승 → L4 복수 소스 교차 → L5 종합
//
// `solution` 은 힌트가 아니라 **클리어 가능 증명용**이다. verify.js 가 이 경로를
// 그대로 깔고 시뮬레이션을 돌려 목표 달성을 확인한다. 레벨을 손대면 여기도 같이
// 고쳐야 하고, 안 고치면 검증이 깨져서 바로 드러난다.
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.LEVELS = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const LEVELS = [
    {
      id: 1,
      name: "첫 라인",
      subtitle: "직선으로 잇고, 불량은 아래로 빼낸다",
      width: 12,
      height: 8,
      target: 12,
      defectRate: 0.3,
      spawnEveryMs: 1150,
      moveEveryMs: 330,
      hint: "소스에서 검수기까지 오른쪽으로 잇습니다. 검수기 오른쪽 출구는 싱크로, 아래쪽 출구는 내렸다가 오른쪽으로 꺾어 폐기 라인 위로 보냅니다.",
      machines: [
        { id: "source-1", type: "source", x: 1, y: 3, out: "E", label: "소스" },
        { id: "inspector-1", type: "inspector", x: 5, y: 3, input: "W", normalOut: "E", defectOut: "S", label: "검수기" },
        { id: "sink-1", type: "sink", x: 10, y: 3, input: "W", label: "싱크" },
        { id: "waste-1", type: "waste", x: 8, y: 6, input: "N", label: "폐기" }
      ],
      solution: [
        [[1, 3], [2, 3], [3, 3], [4, 3], [5, 3]],
        [[5, 3], [6, 3], [7, 3], [8, 3], [9, 3], [10, 3]],
        [[5, 3], [5, 4], [5, 5], [6, 5], [7, 5], [8, 5], [8, 6]]
      ]
    },

    {
      id: 2,
      name: "꺾어 보내기",
      subtitle: "직선으로는 닿지 않는다 — 코너로 돌린다",
      width: 12,
      height: 8,
      target: 14,
      defectRate: 0.3,
      spawnEveryMs: 1150,
      moveEveryMs: 330,
      hint: "소스는 아래로 뱉고 싱크는 아래에서만 받습니다. 세 경로 모두 최소 한 번은 꺾어야 합니다.",
      machines: [
        { id: "source-1", type: "source", x: 1, y: 1, out: "S", label: "소스" },
        { id: "inspector-1", type: "inspector", x: 4, y: 5, input: "W", normalOut: "N", defectOut: "E", label: "검수기" },
        { id: "sink-1", type: "sink", x: 9, y: 1, input: "S", label: "싱크" },
        { id: "waste-1", type: "waste", x: 7, y: 7, input: "W", label: "폐기" }
      ],
      solution: [
        [[1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [2, 5], [3, 5], [4, 5]],
        [[4, 5], [4, 4], [4, 3], [4, 2], [5, 2], [6, 2], [7, 2], [8, 2], [9, 2], [9, 1]],
        [[4, 5], [5, 5], [5, 6], [5, 7], [6, 7], [7, 7]]
      ]
    },

    {
      id: 3,
      name: "불량 폭주",
      subtitle: "절반 가까이가 불량이다 — 폐기 라인이 병목이 된다",
      width: 12,
      height: 8,
      target: 16,
      defectRate: 0.45,
      spawnEveryMs: 1000,
      moveEveryMs: 320,
      hint: "불량률이 45%입니다. 폐기 경로가 길면 그 줄에서 막혀 라인 전체가 멈춥니다. 폐기 라인을 최단으로 뽑으세요.",
      machines: [
        { id: "source-1", type: "source", x: 1, y: 4, out: "E", label: "소스" },
        { id: "inspector-1", type: "inspector", x: 4, y: 4, input: "W", normalOut: "E", defectOut: "N", label: "검수기" },
        { id: "sink-1", type: "sink", x: 10, y: 4, input: "W", label: "싱크" },
        { id: "waste-1", type: "waste", x: 1, y: 1, input: "E", label: "폐기" }
      ],
      solution: [
        [[1, 4], [2, 4], [3, 4], [4, 4]],
        [[4, 4], [5, 4], [6, 4], [7, 4], [8, 4], [9, 4], [10, 4]],
        [[4, 4], [4, 3], [4, 2], [4, 1], [3, 1], [2, 1], [1, 1]]
      ]
    },

    {
      id: 4,
      name: "두 줄 교차",
      subtitle: "소스가 둘이다 — 폐기 경로가 한가운데서 만난다",
      width: 13,
      height: 9,
      target: 20,
      defectRate: 0.35,
      spawnEveryMs: 1100,
      moveEveryMs: 320,
      hint: "위아래 두 라인이 독립적으로 돕니다. 정상품은 각자 오른쪽 싱크로 가지만, 폐기 지점 둘이 가운데 붙어 있어 두 불량 경로가 서로를 피해 들어가야 합니다.",
      machines: [
        { id: "source-a", type: "source", x: 0, y: 1, out: "E", label: "소스A" },
        { id: "inspector-a", type: "inspector", x: 4, y: 1, input: "W", normalOut: "E", defectOut: "S", label: "검수A" },
        { id: "sink-a", type: "sink", x: 12, y: 1, input: "W", label: "싱크A" },
        { id: "waste-a", type: "waste", x: 8, y: 4, input: "N", label: "폐기A" },
        { id: "source-b", type: "source", x: 0, y: 7, out: "E", label: "소스B" },
        { id: "inspector-b", type: "inspector", x: 4, y: 7, input: "W", normalOut: "E", defectOut: "N", label: "검수B" },
        { id: "sink-b", type: "sink", x: 12, y: 7, input: "W", label: "싱크B" },
        { id: "waste-b", type: "waste", x: 9, y: 4, input: "S", label: "폐기B" }
      ],
      solution: [
        [[0, 1], [1, 1], [2, 1], [3, 1], [4, 1]],
        [[4, 1], [5, 1], [6, 1], [7, 1], [8, 1], [9, 1], [10, 1], [11, 1], [12, 1]],
        [[4, 1], [4, 2], [4, 3], [5, 3], [6, 3], [7, 3], [8, 3], [8, 4]],
        [[0, 7], [1, 7], [2, 7], [3, 7], [4, 7]],
        [[4, 7], [5, 7], [6, 7], [7, 7], [8, 7], [9, 7], [10, 7], [11, 7], [12, 7]],
        [[4, 7], [4, 6], [4, 5], [5, 5], [6, 5], [7, 5], [8, 5], [9, 5], [9, 4]]
      ]
    },

    {
      id: 5,
      name: "종합 검수",
      subtitle: "두 소스 · 절반이 불량 · 정상 라인 둘이 나란히 지난다",
      width: 13,
      height: 9,
      target: 24,
      defectRate: 0.5,
      spawnEveryMs: 950,
      moveEveryMs: 300,
      hint: "지금까지 전부 나옵니다. 검수기가 정상품을 위아래로 뱉으므로 두 정상 라인이 가운데 두 줄을 나란히 써야 하고, 불량은 각각 바깥으로 빼냅니다.",
      machines: [
        { id: "source-a", type: "source", x: 0, y: 1, out: "E", label: "소스A" },
        { id: "inspector-a", type: "inspector", x: 3, y: 1, input: "W", normalOut: "S", defectOut: "E", label: "검수A" },
        { id: "sink-a", type: "sink", x: 11, y: 4, input: "W", label: "싱크A" },
        { id: "waste-a", type: "waste", x: 7, y: 0, input: "S", label: "폐기A" },
        { id: "source-b", type: "source", x: 0, y: 7, out: "E", label: "소스B" },
        { id: "inspector-b", type: "inspector", x: 3, y: 7, input: "W", normalOut: "N", defectOut: "E", label: "검수B" },
        { id: "sink-b", type: "sink", x: 11, y: 5, input: "W", label: "싱크B" },
        { id: "waste-b", type: "waste", x: 7, y: 8, input: "N", label: "폐기B" }
      ],
      solution: [
        [[0, 1], [1, 1], [2, 1], [3, 1]],
        [[3, 1], [3, 2], [3, 3], [3, 4], [4, 4], [5, 4], [6, 4], [7, 4], [8, 4], [9, 4], [10, 4], [11, 4]],
        [[3, 1], [4, 1], [5, 1], [6, 1], [7, 1], [7, 0]],
        [[0, 7], [1, 7], [2, 7], [3, 7]],
        [[3, 7], [3, 6], [3, 5], [4, 5], [5, 5], [6, 5], [7, 5], [8, 5], [9, 5], [10, 5], [11, 5]],
        [[3, 7], [4, 7], [5, 7], [6, 7], [7, 7], [7, 8]]
      ]
    }
  ];

  return LEVELS;
});
