===FILE: index.html===
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>검수 라인 공장</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main class="app">
    <section class="topbar">
      <div>
        <h1>검수 라인 공장</h1>
        <p>벨트를 깔아 정상품은 싱크로, 불량품은 폐기 라인으로 보내세요.</p>
      </div>
      <div class="stats" aria-live="polite">
        <div><span>목표</span><strong id="targetCount">0</strong></div>
        <div><span>정상 처리</span><strong id="goodCount">0</strong></div>
        <div><span>불량률</span><strong id="defectRate">0%</strong></div>
        <div><span>상태</span><strong id="statusText">준비</strong></div>
      </div>
    </section>

    <section class="toolbar" aria-label="도구">
      <button id="buildMode" class="active" type="button">벨트 설치</button>
      <button id="eraseMode" type="button">벨트 제거</button>
      <button id="resetButton" type="button">리셋</button>
      <button id="pauseButton" type="button">일시정지</button>
    </section>

    <section class="play-area">
      <div id="board" class="board" aria-label="공장 격자"></div>

      <aside class="panel">
        <h2>조작법</h2>
        <ul>
          <li><b>벨트 설치</b>: 빈 칸을 누른 채 경로를 따라 드래그합니다.</li>
          <li><b>코너 벨트</b>: 드래그 중 방향을 꺾으면 자동으로 만들어집니다.</li>
          <li><b>벨트 제거</b>: 제거 모드에서 벨트를 누르거나 드래그합니다.</li>
          <li><b>검수기</b>: 정상품은 오른쪽, 불량품은 아래쪽 측면 출구로 나갑니다.</li>
          <li><b>리셋</b>: 벨트, 아이템, 카운트를 모두 초기화합니다.</li>
        </ul>

        <h2>레벨 1 힌트</h2>
        <p>
          소스에서 검수기까지 오른쪽으로 잇고, 검수기 오른쪽 출구를 싱크까지 잇습니다.
          검수기 아래쪽 출구는 아래로 내린 뒤 오른쪽으로 꺾고, 다시 아래로 꺾어 폐기 라인에 연결합니다.
        </p>

        <h2>피드백</h2>
        <div id="messageLog" class="message-log">라인을 설계하세요.</div>
      </aside>
    </section>

    <section id="clearBanner" class="clear-banner hidden" role="status">
      레벨 클리어! 목표 정상품을 모두 처리했습니다.
    </section>
  </main>

  <script src="game.js"></script>
</body>
</html>
===END===
===FILE: game.js===
(() => {
  "use strict";

  const DIRS = {
    N: { dx: 0, dy: -1, label: "위" },
    E: { dx: 1, dy: 0, label: "오른쪽" },
    S: { dx: 0, dy: 1, label: "아래" },
    W: { dx: -1, dy: 0, label: "왼쪽" }
  };

  const OPPOSITE = { N: "S", E: "W", S: "N", W: "E" };
  const DIR_ORDER = ["N", "E", "S", "W"];

  const LEVEL = {
    width: 12,
    height: 8,
    target: 12,
    defectRate: 0.3,
    spawnEveryMs: 1150,
    moveEveryMs: 330,
    machines: [
      { id: "source-1", type: "source", x: 1, y: 3, out: "E", label: "소스" },
      { id: "inspector-1", type: "inspector", x: 5, y: 3, input: "W", normalOut: "E", defectOut: "S", label: "검수기" },
      { id: "sink-1", type: "sink", x: 10, y: 3, input: "W", label: "싱크" },
      { id: "waste-1", type: "waste", x: 8, y: 6, input: "N", label: "폐기" }
    ]
  };

  class LocalStorageAdapter {
    constructor(key) {
      this.key = key;
    }

    load() {
      try {
        const raw = window.localStorage.getItem(this.key);
        return raw ? JSON.parse(raw) : {};
      } catch {
        return {};
      }
    }

    save(value) {
      try {
        window.localStorage.setItem(this.key, JSON.stringify(value));
      } catch {
        // 저장 실패는 게임 진행을 막지 않는다.
      }
    }
  }

  class RankingHook {
    submit(_record) {
      return Promise.resolve({ ok: true, skipped: true });
    }

    list() {
      return Promise.resolve([]);
    }
  }

  class Game {
    constructor(level) {
      this.level = level;
      this.storage = new LocalStorageAdapter("gamebuilders.level1");
      this.ranking = new RankingHook();

      this.boardEl = document.getElementById("board");
      this.targetEl = document.getElementById("targetCount");
      this.goodEl = document.getElementById("goodCount");
      this.defectEl = document.getElementById("defectRate");
      this.statusEl = document.getElementById("statusText");
      this.messageEl = document.getElementById("messageLog");
      this.clearEl = document.getElementById("clearBanner");
      this.buildButton = document.getElementById("buildMode");
      this.eraseButton = document.getElementById("eraseMode");
      this.resetButton = document.getElementById("resetButton");
      this.pauseButton = document.getElementById("pauseButton");

      this.machineMap = new Map();
      this.level.machines.forEach(machine => {
        this.machineMap.set(this.key(machine.x, machine.y), machine);
      });

      this.cells = new Map();
      this.mode = "build";
      this.isPointerDown = false;
      this.dragPath = [];
      this.items = [];
      this.belts = new Map();
      this.goodCount = 0;
      this.badSinkCount = 0;
      this.blockedTicks = 0;
      this.elapsedMs = 0;
      this.spawnClock = 0;
      this.moveClock = 0;
      this.itemSeq = 0;
      this.cleared = false;
      this.paused = false;
      this.lastFrame = 0;

      this.initDom();
      this.bindEvents();
      this.reset();
      requestAnimationFrame(time => this.loop(time));
    }

    initDom() {
      this.boardEl.style.setProperty("--cols", String(this.level.width));
      this.boardEl.style.setProperty("--rows", String(this.level.height));
      this.boardEl.innerHTML = "";

      for (let y = 0; y < this.level.height; y += 1) {
        for (let x = 0; x < this.level.width; x += 1) {
          const cell = document.createElement("button");
          cell.type = "button";
          cell.className = "cell";
          cell.dataset.x = String(x);
          cell.dataset.y = String(y);
          cell.setAttribute("aria-label", `${x}, ${y}`);
          this.boardEl.appendChild(cell);
          this.cells.set(this.key(x, y), cell);
        }
      }

      for (const machine of this.level.machines) {
        const cell = this.cellAt(machine.x, machine.y);
        cell.classList.add("machine", machine.type);
        cell.innerHTML = `<span class="machine-label">${machine.label}</span>${this.machinePorts(machine)}`;
      }

      this.targetEl.textContent = String(this.level.target);
      this.defectEl.textContent = `${Math.round(this.level.defectRate * 100)}%`;
    }

    machinePorts(machine) {
      if (machine.type === "source") {
        return `<span class="port port-${machine.out.toLowerCase()}">출구</span>`;
      }

      if (machine.type === "inspector") {
        return [
          `<span class="port port-${machine.input.toLowerCase()}">입구</span>`,
          `<span class="port port-${machine.normalOut.toLowerCase()}">정상</span>`,
          `<span class="port port-${machine.defectOut.toLowerCase()}">불량</span>`
        ].join("");
      }

      return `<span class="port port-${machine.input.toLowerCase()}">입구</span>`;
    }

    bindEvents() {
      this.boardEl.addEventListener("pointerdown", event => {
        const cell = event.target.closest(".cell");
        if (!cell || event.button !== 0) return;

        const pos = this.posFromCell(cell);
        this.isPointerDown = true;
        this.dragPath = [];
        cell.setPointerCapture(event.pointerId);

        if (this.mode === "erase") {
          this.eraseAt(pos.x, pos.y);
          this.render();
          return;
        }

        this.startBuildPath(pos.x, pos.y);
      });

      this.boardEl.addEventListener("pointerenter", event => {
        if (!this.isPointerDown) return;
        const cell = event.target.closest(".cell");
        if (!cell) return;

        const pos = this.posFromCell(cell);
        if (this.mode === "erase") {
          this.eraseAt(pos.x, pos.y);
          this.render();
          return;
        }

        this.extendBuildPath(pos.x, pos.y);
      }, true);

      window.addEventListener("pointerup", () => {
        this.isPointerDown = false;
        this.dragPath = [];
      });

      this.buildButton.addEventListener("click", () => this.setMode("build"));
      this.eraseButton.addEventListener("click", () => this.setMode("erase"));
      this.resetButton.addEventListener("click", () => this.reset());
      this.pauseButton.addEventListener("click", () => {
        this.paused = !this.paused;
        this.pauseButton.textContent = this.paused ? "재개" : "일시정지";
        this.setMessage(this.paused ? "시뮬레이션을 멈췄습니다." : "시뮬레이션을 다시 시작했습니다.");
        this.render();
      });

      this.boardEl.addEventListener("contextmenu", event => {
        const cell = event.target.closest(".cell");
        if (!cell) return;
        event.preventDefault();
        const pos = this.posFromCell(cell);
        this.eraseAt(pos.x, pos.y);
        this.render();
      });
    }

    reset() {
      this.items = [];
      this.belts = new Map();
      this.goodCount = 0;
      this.badSinkCount = 0;
      this.blockedTicks = 0;
      this.elapsedMs = 0;
      this.spawnClock = 0;
      this.moveClock = 0;
      this.itemSeq = 0;
      this.cleared = false;
      this.paused = false;
      this.pauseButton.textContent = "일시정지";
      this.clearEl.classList.add("hidden");
      this.setMode("build");
      this.setMessage("라인을 설계하세요. 드래그로 코너 벨트를 만들 수 있습니다.");
      this.render();
    }

    setMode(mode) {
      this.mode = mode;
      this.buildButton.classList.toggle("active", mode === "build");
      this.eraseButton.classList.toggle("active", mode === "erase");
      this.boardEl.classList.toggle("erase-cursor", mode === "erase");
    }

    loop(time) {
      const delta = this.lastFrame ? Math.min(80, time - this.lastFrame) : 0;
      this.lastFrame = time;

      if (!this.paused && !this.cleared) {
        this.tick(delta);
      }

      requestAnimationFrame(nextTime => this.loop(nextTime));
    }

    tick(delta) {
      this.elapsedMs += delta;
      this.spawnClock += delta;
      this.moveClock += delta;

      if (this.spawnClock >= this.level.spawnEveryMs) {
        this.spawnClock = 0;
        this.spawnItem();
      }

      if (this.moveClock >= this.level.moveEveryMs) {
        this.moveClock = 0;
        this.advanceItems();
      }
    }

    spawnItem() {
      const source = this.level.machines.find(machine => machine.type === "source");
      if (this.itemAt(source.x, source.y)) {
        this.blockedTicks += 1;
        this.setStatus("소스 막힘");
        return;
      }

      const kind = Math.random() < this.level.defectRate ? "bad" : "good";
      this.items.push({
        id: `item-${this.itemSeq += 1}`,
        x: source.x,
        y: source.y,
        kind,
        flash: 0
      });

      this.render();
    }

    advanceItems() {
      const occupied = new Map();
      for (const item of this.items) {
        occupied.set(this.key(item.x, item.y), item);
      }

      const survivors = [];
      let moved = false;
      let blocked = false;
      let failure = false;

      for (const item of this.items) {
        occupied.delete(this.key(item.x, item.y));
        const step = this.nextStep(item);

        if (step.consume === "sink") {
          if (item.kind === "good") {
            this.goodCount += 1;
            this.setMessage(`정상품 처리 ${this.goodCount}/${this.level.target}`);
          } else {
            this.badSinkCount += 1;
            failure = true;
            this.setMessage("불량품이 싱크로 들어갔습니다. 카운트는 오르지 않습니다.");
          }
          moved = true;
          continue;
        }

        if (step.consume === "waste") {
          if (item.kind === "bad") {
            this.setMessage("불량품을 폐기 라인으로 보냈습니다.");
          } else {
            this.setMessage("정상품이 폐기되었습니다. 목표 카운트는 오르지 않습니다.");
          }
          moved = true;
          continue;
        }

        if (!step.ok) {
          item.flash = 2;
          survivors.push(item);
          occupied.set(this.key(item.x, item.y), item);
          blocked = true;
          continue;
        }

        const destinationKey = this.key(step.x, step.y);
        if (occupied.has(destinationKey)) {
          item.flash = 2;
          survivors.push(item);
          occupied.set(this.key(item.x, item.y), item);
          blocked = true;
          continue;
        }

        item.x = step.x;
        item.y = step.y;
        item.flash = Math.max(0, item.flash - 1);
        survivors.push(item);
        occupied.set(destinationKey, item);
        moved = true;
      }

      this.items = survivors;

      if (this.goodCount >= this.level.target) {
        this.completeLevel();
      } else if (failure) {
        this.setStatus("싱크 오류");
      } else if (blocked) {
        this.blockedTicks += 1;
        this.setStatus(this.blockedTicks > 3 ? "라인 막힘" : "대기");
      } else if (moved) {
        this.blockedTicks = 0;
        this.setStatus("가동 중");
      }

      this.render();
    }

    nextStep(item) {
      const machine = this.machineMap.get(this.key(item.x, item.y));
      if (machine) {
        return this.stepFromMachine(item, machine);
      }

      const belt = this.belts.get(this.key(item.x, item.y));
      if (!belt) return { ok: false };

      const next = this.neighbor(item.x, item.y, belt.out);
      return this.resolveEntry(item, next.x, next.y, belt.out);
    }

    stepFromMachine(item, machine) {
      if (machine.type === "source") {
        const next = this.neighbor(machine.x, machine.y, machine.out);
        return this.resolveEntry(item, next.x, next.y, machine.out);
      }

      if (machine.type === "inspector") {
        const out = item.kind === "bad" ? machine.defectOut : machine.normalOut;
        const next = this.neighbor(machine.x, machine.y, out);
        return this.resolveEntry(item, next.x, next.y, out);
      }

      return { ok: false };
    }

    resolveEntry(item, x, y, travelDir) {
      if (!this.inBounds(x, y)) return { ok: false };

      const machine = this.machineMap.get(this.key(x, y));
      if (machine) {
        if (machine.type === "inspector" && machine.input === OPPOSITE[travelDir]) {
          return { ok: true, x, y };
        }

        if (machine.type === "sink" && machine.input === OPPOSITE[travelDir]) {
          return { consume: "sink" };
        }

        if (machine.type === "waste" && machine.input === OPPOSITE[travelDir]) {
          return { consume: "waste" };
        }

        return { ok: false };
      }

      const belt = this.belts.get(this.key(x, y));
      if (!belt) return { ok: false };
      if (belt.in !== OPPOSITE[travelDir]) return { ok: false };

      return { ok: true, x, y };
    }

    completeLevel() {
      this.cleared = true;
      this.setStatus("클리어");
      this.setMessage("목표 달성. 레벨 1 클리어!");
      this.clearEl.classList.remove("hidden");

      const saved = this.storage.load();
      const record = {
        level: 1,
        clearedAt: new Date().toISOString(),
        elapsedMs: Math.round(this.elapsedMs),
        badSinkCount: this.badSinkCount
      };

      if (!saved.bestMs || record.elapsedMs < saved.bestMs) {
        saved.bestMs = record.elapsedMs;
      }
      saved.lastClear = record;
      this.storage.save(saved);
      this.ranking.submit(record);
    }

    startBuildPath(x, y) {
      if (!this.canBuildAt(x, y)) return;

      const inferred = this.inferIncomingDirection(x, y);
      const belt = this.belts.get(this.key(x, y)) || {};
      belt.in = inferred || belt.in || "W";
      belt.out = belt.out || OPPOSITE[belt.in];
      this.belts.set(this.key(x, y), belt);
      this.dragPath = [{ x, y }];
      this.setMessage("경로를 드래그하세요. 방향을 꺾으면 코너가 됩니다.");
      this.render();
    }

    extendBuildPath(x, y) {
      if (!this.dragPath.length) return;
      if (!this.canBuildAt(x, y)) return;

      const last = this.dragPath[this.dragPath.length - 1];
      if (last.x === x && last.y === y) return;

      const dir = this.directionBetween(last, { x, y });
      if (!dir) return;

      const lastKey = this.key(last.x, last.y);
      const currentKey = this.key(x, y);
      const lastBelt = this.belts.get(lastKey) || { in: OPPOSITE[dir], out: dir };
      lastBelt.out = dir;
      this.belts.set(lastKey, lastBelt);

      const currentBelt = this.belts.get(currentKey) || {};
      currentBelt.in = OPPOSITE[dir];
      currentBelt.out = currentBelt.out || dir;
      this.belts.set(currentKey, currentBelt);

      this.dragPath.push({ x, y });
      this.render();
    }

    inferIncomingDirection(x, y) {
      for (const dir of DIR_ORDER) {
        const neighbor = this.neighbor(x, y, dir);
        const machine = this.machineMap.get(this.key(neighbor.x, neighbor.y));
        if (!machine) continue;

        const travelFromMachine = OPPOSITE[dir];

        if (machine.type === "source" && machine.out === travelFromMachine) {
          return dir;
        }

        if (machine.type === "inspector") {
          if (machine.normalOut === travelFromMachine || machine.defectOut === travelFromMachine) {
            return dir;
          }
        }
      }

      const adjacentBelt = this.findAdjacentBeltFeeding(x, y);
      return adjacentBelt ? OPPOSITE[adjacentBelt.dir] : null;
    }

    findAdjacentBeltFeeding(x, y) {
      for (const dir of DIR_ORDER) {
        const neighbor = this.neighbor(x, y, dir);
        const belt = this.belts.get(this.key(neighbor.x, neighbor.y));
        if (belt && belt.out === OPPOSITE[dir]) {
          return { dir };
        }
      }
      return null;
    }

    eraseAt(x, y) {
      if (!this.canBuildAt(x, y)) return;
      this.belts.delete(this.key(x, y));
      this.setMessage("벨트를 제거했습니다.");
    }

    render() {
      for (const [key, cell] of this.cells) {
        const [x, y] = key.split(",").map(Number);
        if (this.machineMap.has(key)) continue;

        const belt = this.belts.get(key);
        cell.className = "cell";
        cell.innerHTML = "";

        if (belt) {
          const isCorner = belt.in !== OPPOSITE[belt.out];
          cell.classList.add("belt", isCorner ? "corner" : "straight");
          cell.dataset.in = belt.in;
          cell.dataset.out = belt.out;
          cell.innerHTML = `<span class="belt-line ${this.beltClass(belt)}"></span><span class="arrow arrow-${belt.out.toLowerCase()}">➜</span>`;
        } else {
          delete cell.dataset.in;
          delete cell.dataset.out;
        }
      }

      this.cells.forEach(cell => {
        cell.querySelectorAll(".item").forEach(item => item.remove());
      });

      for (const item of this.items) {
        const cell = this.cellAt(item.x, item.y);
        const itemEl = document.createElement("span");
        itemEl.className = `item ${item.kind}${item.flash ? " blocked" : ""}`;
        itemEl.textContent = item.kind === "good" ? "정" : "불";
        cell.appendChild(itemEl);
      }

      this.goodEl.textContent = String(this.goodCount);
    }

    beltClass(belt) {
      const pair = `${belt.in}-${belt.out}`;
      const aliases = {
        "W-E": "line-horizontal",
        "E-W": "line-horizontal",
        "N-S": "line-vertical",
        "S-N": "line-vertical",
        "W-S": "corner-w-s",
        "N-E": "corner-n-e",
        "E-S": "corner-e-s",
        "N-W": "corner-n-w",
        "S-E": "corner-s-e",
        "W-N": "corner-w-n",
        "S-W": "corner-s-w",
        "E-N": "corner-e-n"
      };
      return aliases[pair] || "line-horizontal";
    }

    setMessage(message) {
      this.messageEl.textContent = message;
    }

    setStatus(status) {
      this.statusEl.textContent = status;
    }

    canBuildAt(x, y) {
      return this.inBounds(x, y) && !this.machineMap.has(this.key(x, y));
    }

    directionBetween(a, b) {
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      if (dx === 1 && dy === 0) return "E";
      if (dx === -1 && dy === 0) return "W";
      if (dx === 0 && dy === 1) return "S";
      if (dx === 0 && dy === -1) return "N";
      return null;
    }

    neighbor(x, y, dir) {
      return {
        x: x + DIRS[dir].dx,
        y: y + DIRS[dir].dy
      };
    }

    itemAt(x, y) {
      return this.items.find(item => item.x === x && item.y === y);
    }

    posFromCell(cell) {
      return {
        x: Number(cell.dataset.x),
        y: Number(cell.dataset.y)
      };
    }

    cellAt(x, y) {
      return this.cells.get(this.key(x, y));
    }

    key(x, y) {
      return `${x},${y}`;
    }

    inBounds(x, y) {
      return x >= 0 && y >= 0 && x < this.level.width && y < this.level.height;
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    new Game(LEVEL);
  });
})();
===END===
===FILE: style.css===
:root {
  color-scheme: light;
  --bg: #eef2f5;
  --ink: #17202a;
  --muted: #607080;
  --panel: #ffffff;
  --line: #c8d2dc;
  --grid: #dfe6ed;
  --belt: #2f6f73;
  --belt-dark: #214d50;
  --good: #2f8f5b;
  --bad: #c94b4b;
  --source: #d99a32;
  --inspector: #5e6fb5;
  --sink: #2f8f5b;
  --waste: #7b8791;
  --focus: #1677ff;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

button {
  font: inherit;
}

.app {
  width: min(1180px, calc(100vw - 28px));
  margin: 0 auto;
  padding: 22px 0 28px;
}

.topbar {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: end;
  margin-bottom: 14px;
}

h1 {
  margin: 0;
  font-size: 30px;
  line-height: 1.15;
  letter-spacing: 0;
}

p {
  margin: 7px 0 0;
  color: var(--muted);
  line-height: 1.55;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(92px, 1fr));
  gap: 8px;
  min-width: 430px;
}

.stats div {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
}

.stats span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 3px;
}

.stats strong {
  font-size: 20px;
  line-height: 1.1;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.toolbar button {
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--ink);
  border-radius: 7px;
  min-height: 38px;
  padding: 0 14px;
  cursor: pointer;
}

.toolbar button:hover,
.toolbar button:focus-visible {
  border-color: var(--focus);
  outline: none;
}

.toolbar button.active {
  background: var(--ink);
  border-color: var(--ink);
  color: white;
}

.play-area {
  display: grid;
  grid-template-columns: minmax(620px, 1fr) 310px;
  gap: 16px;
  align-items: start;
}

.board {
  display: grid;
  grid-template-columns: repeat(var(--cols), minmax(42px, 1fr));
  grid-template-rows: repeat(var(--rows), minmax(42px, 1fr));
  gap: 4px;
  width: 100%;
  aspect-ratio: 12 / 8;
  background: #bac7d2;
  border: 1px solid #a9b7c3;
  border-radius: 8px;
  padding: 6px;
  touch-action: none;
  user-select: none;
}

.cell {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--grid);
  border-radius: 6px;
  background: #f8fafc;
  min-width: 0;
  min-height: 0;
  cursor: crosshair;
}

.cell:hover {
  outline: 2px solid rgba(22, 119, 255, 0.32);
  outline-offset: -2px;
}

.erase-cursor .cell {
  cursor: not-allowed;
}

.machine {
  cursor: default;
  border-color: rgba(0, 0, 0, 0.2);
  color: white;
  display: grid;
  place-items: center;
  text-align: center;
}

.machine.source {
  background: var(--source);
}

.machine.inspector {
  background: var(--inspector);
}

.machine.sink {
  background: var(--sink);
}

.machine.waste {
  background: var(--waste);
}

.machine-label {
  position: relative;
  z-index: 2;
  font-weight: 800;
  font-size: clamp(11px, 1.2vw, 15px);
}

.port {
  position: absolute;
  z-index: 3;
  background: rgba(255, 255, 255, 0.95);
  color: #111820;
  border: 1px solid rgba(0, 0, 0, 0.18);
  border-radius: 999px;
  font-size: 10px;
  font-weight: 800;
  line-height: 1;
  padding: 3px 5px;
  white-space: nowrap;
}

.port-e {
  right: -2px;
  top: 50%;
  transform: translateY(-50%);
}

.port-w {
  left: -2px;
  top: 50%;
  transform: translateY(-50%);
}

.port-s {
  bottom: -2px;
  left: 50%;
  transform: translateX(-50%);
}

.port-n {
  top: -2px;
  left: 50%;
  transform: translateX(-50%);
}

.belt {
  background: #e9f4f3;
}

.belt-line {
  position: absolute;
  inset: 13%;
  border-color: var(--belt);
  border-style: solid;
}

.line-horizontal {
  top: calc(50% - 5px);
  bottom: auto;
  left: 6%;
  right: 6%;
  height: 10px;
  border-width: 0;
  background: var(--belt);
  border-radius: 999px;
}

.line-vertical {
  left: calc(50% - 5px);
  right: auto;
  top: 6%;
  bottom: 6%;
  width: 10px;
  border-width: 0;
  background: var(--belt);
  border-radius: 999px;
}

.corner-w-s,
.corner-n-e,
.corner-e-s,
.corner-n-w,
.corner-s-e,
.corner-w-n,
.corner-s-w,
.corner-e-n {
  width: 44%;
  height: 44%;
  border-width: 0;
  background: transparent;
}

.corner-w-s {
  left: 8%;
  top: 48%;
  border-top-width: 10px;
  border-right-width: 10px;
  border-top-right-radius: 16px;
}

.corner-n-e {
  left: 48%;
  top: 8%;
  border-left-width: 10px;
  border-bottom-width: 10px;
  border-bottom-left-radius: 16px;
}

.corner-e-s {
  right: 8%;
  top: 48%;
  border-top-width: 10px;
  border-left-width: 10px;
  border-top-left-radius: 16px;
}

.corner-n-w {
  left: 8%;
  top: 8%;
  border-right-width: 10px;
  border-bottom-width: 10px;
  border-bottom-right-radius: 16px;
}

.corner-s-e {
  left: 48%;
  bottom: 8%;
  border-left-width: 10px;
  border-top-width: 10px;
  border-top-left-radius: 16px;
}

.corner-w-n {
  left: 8%;
  top: 8%;
  border-right-width: 10px;
  border-bottom-width: 10px;
  border-bottom-right-radius: 16px;
}

.corner-s-w {
  left: 8%;
  bottom: 8%;
  border-right-width: 10px;
  border-top-width: 10px;
  border-top-right-radius: 16px;
}

.corner-e-n {
  right: 8%;
  top: 8%;
  border-left-width: 10px;
  border-bottom-width: 10px;
  border-bottom-left-radius: 16px;
}

.arrow {
  position: absolute;
  z-index: 2;
  left: 50%;
  top: 50%;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  margin-left: -11px;
  margin-top: -11px;
  border-radius: 999px;
  background: var(--belt-dark);
  color: white;
  font-size: 14px;
  font-weight: 900;
  line-height: 1;
}

.arrow-e {
  transform: rotate(0deg);
}

.arrow-s {
  transform: rotate(90deg);
}

.arrow-w {
  transform: rotate(180deg);
}

.arrow-n {
  transform: rotate(270deg);
}

.item {
  position: absolute;
  z-index: 5;
  left: 50%;
  top: 50%;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin-left: -14px;
  margin-top: -14px;
  border-radius: 999px;
  color: white;
  font-size: 12px;
  font-weight: 900;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.24);
}

.item.good {
  background: var(--good);
}

.item.bad {
  background: var(--bad);
}

.item.blocked {
  animation: blockedPulse 0.34s ease-in-out infinite alternate;
}

@keyframes blockedPulse {
  from {
    transform: scale(1);
  }
  to {
    transform: scale(1.13);
  }
}

.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
}

.panel h2 {
  margin: 0 0 8px;
  font-size: 16px;
}

.panel h2:not(:first-child) {
  margin-top: 18px;
}

.panel ul {
  margin: 0;
  padding-left: 20px;
  color: var(--muted);
  line-height: 1.55;
}

.panel li + li {
  margin-top: 5px;
}

.message-log {
  min-height: 56px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #f7f9fb;
  padding: 11px;
  color: var(--ink);
  line-height: 1.45;
}

.clear-banner {
  margin-top: 16px;
  border-radius: 8px;
  background: #173f2b;
  color: white;
  padding: 15px 18px;
  font-weight: 800;
  text-align: center;
}

.hidden {
  display: none;
}

@media (max-width: 940px) {
  .topbar {
    align-items: stretch;
    flex-direction: column;
  }

  .stats {
    min-width: 0;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .play-area {
    grid-template-columns: 1fr;
  }

  .board {
    grid-template-columns: repeat(var(--cols), minmax(28px, 1fr));
    grid-template-rows: repeat(var(--rows), minmax(28px, 1fr));
    gap: 3px;
    padding: 4px;
  }

  .machine-label {
    font-size: 10px;
  }

  .port {
    font-size: 8px;
    padding: 2px 3px;
  }

  .item {
    width: 22px;
    height: 22px;
    margin-left: -11px;
    margin-top: -11px;
    font-size: 10px;
  }

  .arrow {
    width: 18px;
    height: 18px;
    margin-left: -9px;
    margin-top: -9px;
    font-size: 12px;
  }
}
===END===

구현 내용: 단일 HTML/JS/CSS 웹 게임으로 격자, 벨트 설치/제거, 드래그 기반 코너 벨트, 소스 생성, 검수기 분기, 싱크/폐기 처리, 막힘 피드백, 클리어 표시, 리셋을 넣었습니다.

설계 결정: 레벨 1은 소스 `(1,3)`, 검수기 `(5,3)`, 싱크 `(10,3)`, 폐기 `(8,6)` 배치라 불량 라인은 반드시 코너 2개를 써야 클리어됩니다. 저장 계층은 `LocalStorageAdapter`, 서버 랭킹 확장은 빈 `RankingHook`으로 분리했습니다.

사람이 정해야 할 것: 목표 수, 불량률, 생성/이동 속도, 이후 레벨 배치와 랭킹 서버 연동 방식입니다.