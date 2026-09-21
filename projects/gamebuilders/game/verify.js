// 레벨 클리어 가능 실증 (헤드리스)
//
//   node game/verify.js
//
// 화면에서 도는 것과 **같은 엔진**(sim.js)에 levels.js 의 참조 해답을 깔고
// 끝까지 돌린다. "설계상 될 것 같다"가 아니라 실제로 목표 카운트에 도달하는지 본다.
//
// 함께 확인하는 것:
//   · 해답 경로가 서로 겹치지 않는가 (같은 칸에 다른 방향 벨트를 요구하면 설계 결함)
//   · 폐기 라인을 빼면 **클리어가 불가능해지는가** — SCOPE.md 가 주장한 긴장의 출처가
//     실제로 작동하는지 반증으로 확인한다. 여기서 클리어되면 불량 메카닉이 무의미하다는 뜻이다.
"use strict";

const path = require("path");
const { Sim, pathToBelts, mulberry32, key } = require(path.join(__dirname, "sim.js"));
const LEVELS = require(path.join(__dirname, "levels.js"));

const STEP_MS = 10;
const MAX_SIM_MS = 400000;

function buildBelts(level) {
  const cells = new Map();
  const conflicts = [];
  for (const poly of level.solution) {
    for (const belt of pathToBelts(poly)) {
      const k = key(belt.x, belt.y);
      const prev = cells.get(k);
      if (prev && (prev.in !== belt.in || prev.out !== belt.out)) {
        conflicts.push({ cell: k, a: `${prev.in}->${prev.out}`, b: `${belt.in}->${belt.out}` });
      }
      cells.set(k, belt);
    }
  }
  return { cells, conflicts };
}

function run(level, belts, seed) {
  const sim = new Sim(level, mulberry32(seed));
  for (const [, b] of belts) sim.setBelt(b.x, b.y, { in: b.in, out: b.out });

  let ticks = 0;
  while (!sim.cleared && sim.elapsedMs < MAX_SIM_MS) {
    sim.tick(STEP_MS);
    ticks += 1;
  }
  return sim;
}

function countCorners(belts) {
  const OPP = { N: "S", E: "W", S: "N", W: "E" };
  let n = 0;
  for (const [, b] of belts) if (b.in !== OPP[b.out]) n += 1;
  return n;
}

let allOk = true;
const rows = [];

for (const level of LEVELS) {
  const { cells, conflicts } = buildBelts(level);

  // 1) 정상 해답으로 클리어되는가 — 시드 여러 개로 돌린다.
  //    불량 발생이 난수라 한 판만 돌리면 운으로 통과했을 수 있다.
  const SEEDS = [12345, 777, 2026, 8, 99991];
  const runs = SEEDS.map(s => run(level, cells, s));
  const ok = runs[0];
  const allCleared = runs.every(r => r.cleared);
  const secs = runs.map(r => r.elapsedMs / 1000);

  // 2) 폐기 라인을 끊으면 정말 막히는가 (반증 테스트)
  //    마지막 폴리라인 = 불량 경로. 그 벨트만 빼고 같은 조건으로 돌린다.
  const noWaste = new Map(cells);
  for (const poly of level.solution) {
    const first = poly[0];
    const machine = level.machines.find(m => m.x === first[0] && m.y === first[1]);
    if (!machine || machine.type !== "inspector") continue;
    const last = poly[poly.length - 1];
    const endMachine = level.machines.find(m => m.x === last[0] && m.y === last[1]);
    if (endMachine && endMachine.type === "waste") {
      for (const b of pathToBelts(poly)) noWaste.delete(key(b.x, b.y));
    }
  }
  const broken = run(level, noWaste, 12345);

  const pass = allCleared && !broken.cleared && conflicts.length === 0;
  if (!pass) allOk = false;

  rows.push({
    id: level.id,
    name: level.name,
    grid: `${level.width}x${level.height}`,
    sources: level.machines.filter(m => m.type === "source").length,
    defect: `${Math.round(level.defectRate * 100)}%`,
    target: level.target,
    belts: cells.size,
    corners: countCorners(cells),
    cleared: allCleared,
    seeds: `${runs.filter(r => r.cleared).length}/${SEEDS.length}`,
    sec: `${Math.min(...secs).toFixed(1)}~${Math.max(...secs).toFixed(1)}`,
    good: ok.goodCount,
    badSink: ok.badSinkCount,
    wastedGood: ok.wastedGoodCount,
    brokenCleared: broken.cleared,
    brokenGood: broken.goodCount,
    conflicts: conflicts.length,
    pass
  });
}

const pad = (s, n) => String(s).padEnd(n);
console.log("");
console.log("레벨 | 이름       | 격자  | 소스 | 불량 | 목표 | 벨트 | 코너 | 시드통과 | 소요초      | 폐기끊음:클리어 | 판정");
console.log("-".repeat(118));
for (const r of rows) {
  console.log(
    [
      pad(r.id, 4), pad(r.name, 10), pad(r.grid, 5), pad(r.sources, 4), pad(r.defect, 4),
      pad(r.target, 4), pad(r.belts, 4), pad(r.corners, 4),
      pad(r.seeds, 8), pad(r.sec, 11),
      pad(r.brokenCleared ? "클리어됨(문제)" : `막힘(${r.brokenGood}개)`, 15),
      r.pass ? "PASS" : "FAIL"
    ].join(" | ")
  );
}
console.log("");
for (const r of rows) {
  if (r.conflicts) console.log(`레벨 ${r.id}: 해답 경로 충돌 ${r.conflicts}건`);
}
console.log(allOk ? "STATUS: OK — 전 레벨 클리어 실증 완료" : "STATUS: FAIL");
process.exit(allOk ? 0 : 1);
