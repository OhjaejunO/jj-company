// 검수 라인 공장 — 순수 시뮬레이션 엔진 (DOM 의존 없음)
//
// game.js 에서 떼어냈다. 이유는 하나 — **레벨이 실제로 클리어 가능한지 증명하려면
// 브라우저 없이 돌릴 수 있어야 한다.** verify.js 가 이 파일을 그대로 가져다 쓴다.
// 화면에서 도는 로직과 검증에서 도는 로직이 같은 코드여야 증명이 의미가 있다.
//
// 규칙은 SCOPE.md 고정: 소스 / 검수기 / 싱크 / 폐기 라인 4종뿐. 신규 메카닉 없음.
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Sim = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const DIRS = {
    N: { dx: 0, dy: -1, label: "위" },
    E: { dx: 1, dy: 0, label: "오른쪽" },
    S: { dx: 0, dy: 1, label: "아래" },
    W: { dx: -1, dy: 0, label: "왼쪽" }
  };
  const OPPOSITE = { N: "S", E: "W", S: "N", W: "E" };
  const DIR_ORDER = ["N", "E", "S", "W"];

  const key = (x, y) => `${x},${y}`;

  function directionBetween(a, b) {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    if (dx === 1 && dy === 0) return "E";
    if (dx === -1 && dy === 0) return "W";
    if (dx === 0 && dy === 1) return "S";
    if (dx === 0 && dy === -1) return "N";
    return null;
  }

  // 재현 가능한 난수. 검증이 매번 같은 결과를 내야 "실증"이 된다.
  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  class Sim {
    constructor(level, rng) {
      this.level = level;
      this.rng = rng || Math.random;
      this.machineMap = new Map();
      level.machines.forEach(m => this.machineMap.set(key(m.x, m.y), m));
      this.sources = level.machines.filter(m => m.type === "source");
      this.reset();
    }

    reset() {
      this.items = [];
      this.belts = new Map();
      this.goodCount = 0;
      this.badSinkCount = 0;
      this.wastedGoodCount = 0;
      this.blockedTicks = 0;
      this.elapsedMs = 0;
      this.spawnClock = 0;
      this.moveClock = 0;
      this.itemSeq = 0;
      this.cleared = false;
      this.events = [];
    }

    // --- 격자 조회 -------------------------------------------------------
    inBounds(x, y) {
      return x >= 0 && y >= 0 && x < this.level.width && y < this.level.height;
    }

    canBuildAt(x, y) {
      return this.inBounds(x, y) && !this.machineMap.has(key(x, y));
    }

    neighbor(x, y, dir) {
      return { x: x + DIRS[dir].dx, y: y + DIRS[dir].dy };
    }

    itemAt(x, y) {
      return this.items.find(i => i.x === x && i.y === y);
    }

    setBelt(x, y, belt) {
      if (!this.canBuildAt(x, y)) return false;
      this.belts.set(key(x, y), belt);
      return true;
    }

    removeBelt(x, y) {
      if (!this.canBuildAt(x, y)) return false;
      return this.belts.delete(key(x, y));
    }

    // --- 시간 진행 -------------------------------------------------------
    tick(delta) {
      if (this.cleared) return;
      this.elapsedMs += delta;
      this.spawnClock += delta;
      this.moveClock += delta;

      if (this.spawnClock >= this.level.spawnEveryMs) {
        this.spawnClock = 0;
        this.spawnItems();
      }
      if (this.moveClock >= this.level.moveEveryMs) {
        this.moveClock = 0;
        this.advanceItems();
      }
    }

    // 소스가 여럿일 수 있다 (레벨 4~5). 각 소스가 독립적으로 뱉는다.
    spawnItems() {
      for (const source of this.sources) {
        if (this.itemAt(source.x, source.y)) {
          this.blockedTicks += 1;
          this.events.push({ type: "blocked", where: source.id });
          continue;
        }
        const kind = this.rng() < this.level.defectRate ? "bad" : "good";
        this.items.push({
          id: `item-${(this.itemSeq += 1)}`,
          x: source.x,
          y: source.y,
          kind,
          flash: 0,
          from: source.id
        });
      }
    }

    advanceItems() {
      const occupied = new Map();
      for (const item of this.items) occupied.set(key(item.x, item.y), item);

      const survivors = [];
      let moved = false;
      let blocked = false;

      for (const item of this.items) {
        occupied.delete(key(item.x, item.y));
        const step = this.nextStep(item);

        if (step.consume === "sink") {
          if (item.kind === "good") {
            this.goodCount += 1;
            this.events.push({ type: "good", count: this.goodCount });
          } else {
            this.badSinkCount += 1;
            this.events.push({ type: "badSink" });
          }
          moved = true;
          continue;
        }

        if (step.consume === "waste") {
          if (item.kind === "bad") {
            this.events.push({ type: "wasted" });
          } else {
            this.wastedGoodCount += 1;
            this.events.push({ type: "wastedGood" });
          }
          moved = true;
          continue;
        }

        if (!step.ok || occupied.has(key(step.x, step.y))) {
          item.flash = 2;
          survivors.push(item);
          occupied.set(key(item.x, item.y), item);
          blocked = true;
          continue;
        }

        item.x = step.x;
        item.y = step.y;
        item.flash = Math.max(0, item.flash - 1);
        survivors.push(item);
        occupied.set(key(step.x, step.y), item);
        moved = true;
      }

      this.items = survivors;

      if (this.goodCount >= this.level.target) this.cleared = true;
      else if (blocked) this.blockedTicks += 1;
      else if (moved) this.blockedTicks = 0;

      return { moved, blocked };
    }

    // --- 경로 판정 -------------------------------------------------------
    nextStep(item) {
      const machine = this.machineMap.get(key(item.x, item.y));
      if (machine) return this.stepFromMachine(item, machine);

      const belt = this.belts.get(key(item.x, item.y));
      if (!belt) return { ok: false };

      const next = this.neighbor(item.x, item.y, belt.out);
      return this.resolveEntry(next.x, next.y, belt.out);
    }

    stepFromMachine(item, machine) {
      if (machine.type === "source") {
        const next = this.neighbor(machine.x, machine.y, machine.out);
        return this.resolveEntry(next.x, next.y, machine.out);
      }
      if (machine.type === "inspector") {
        const out = item.kind === "bad" ? machine.defectOut : machine.normalOut;
        const next = this.neighbor(machine.x, machine.y, out);
        return this.resolveEntry(next.x, next.y, out);
      }
      return { ok: false };
    }

    resolveEntry(x, y, travelDir) {
      if (!this.inBounds(x, y)) return { ok: false };
      const entrySide = OPPOSITE[travelDir];

      const machine = this.machineMap.get(key(x, y));
      if (machine) {
        if (machine.type === "inspector" && machine.input === entrySide) return { ok: true, x, y };
        if (machine.type === "sink" && machine.input === entrySide) return { consume: "sink" };
        if (machine.type === "waste" && machine.input === entrySide) return { consume: "waste" };
        return { ok: false };
      }

      const belt = this.belts.get(key(x, y));
      if (!belt || belt.in !== entrySide) return { ok: false };
      return { ok: true, x, y };
    }
  }

  // 폴리라인(기계칸 → 벨트칸들 → 기계칸)을 벨트 in/out 으로 편다.
  // 레벨 정답과 힌트를 같은 표기로 쓰기 위한 헬퍼다.
  function pathToBelts(points) {
    const belts = [];
    for (let i = 1; i < points.length - 1; i += 1) {
      const inDir = directionBetween(points[i - 1], points[i]);
      const outDir = directionBetween(points[i], points[i + 1]);
      if (!inDir || !outDir) throw new Error("경로가 인접하지 않다: " + JSON.stringify(points[i]));
      belts.push({ x: points[i][0], y: points[i][1], in: OPPOSITE[inDir], out: outDir });
    }
    return belts;
  }

  return { Sim, DIRS, OPPOSITE, DIR_ORDER, key, directionBetween, pathToBelts, mulberry32 };
});
