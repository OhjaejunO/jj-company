// 검수 라인 공장 — 화면·입력 계층
//
// 시뮬레이션은 sim.js 가 전담한다. 이 파일은 격자를 그리고 드래그를 받아
// 벨트를 놓는 일만 한다. 둘을 가른 이유는 verify.js 가 브라우저 없이 같은
// 엔진으로 레벨 클리어 가능성을 증명할 수 있게 하기 위해서다.
(() => {
  "use strict";

  const { Sim, OPPOSITE, DIR_ORDER, key } = window.Sim;
  const LEVELS = window.LEVELS;
  const PROGRESS_KEY = "gamebuilders.progress";

  class LocalStorageAdapter {
    constructor(k) { this.key = k; }
    load() {
      try {
        const raw = window.localStorage.getItem(this.key);
        return raw ? JSON.parse(raw) : {};
      } catch { return {}; }
    }
    save(value) {
      try { window.localStorage.setItem(this.key, JSON.stringify(value)); } catch { /* 저장 실패가 진행을 막지 않는다 */ }
    }
  }

  // Hive 대응 자리 — SCOPE.md 대로 붙일 수 있는 형태로만 비워 둔다.
  class RankingHook {
    submit(_record) { return Promise.resolve({ ok: true, skipped: true }); }
    list() { return Promise.resolve([]); }
  }

  class Game {
    constructor() {
      this.storage = new LocalStorageAdapter(PROGRESS_KEY);
      this.ranking = new RankingHook();

      this.boardEl = document.getElementById("board");
      this.targetEl = document.getElementById("targetCount");
      this.goodEl = document.getElementById("goodCount");
      this.defectEl = document.getElementById("defectRate");
      this.statusEl = document.getElementById("statusText");
      this.messageEl = document.getElementById("messageLog");
      this.clearEl = document.getElementById("clearBanner");
      this.levelBarEl = document.getElementById("levelBar");
      this.levelNameEl = document.getElementById("levelName");
      this.levelSubEl = document.getElementById("levelSubtitle");
      this.hintEl = document.getElementById("levelHint");
      this.buildButton = document.getElementById("buildMode");
      this.eraseButton = document.getElementById("eraseMode");
      this.resetButton = document.getElementById("resetButton");
      this.pauseButton = document.getElementById("pauseButton");
      this.nextButton = document.getElementById("nextLevelButton");

      const saved = this.storage.load();
      this.unlocked = Math.max(1, Math.min(LEVELS.length, saved.unlocked || 1));

      this.isPointerDown = false;
      this.dragPath = [];
      this.paused = false;
      this.lastFrame = 0;

      this.buildLevelBar();
      this.bindEvents();
      this.loadLevel(this.unlocked);
      requestAnimationFrame(t => this.loop(t));
    }

    // --- 레벨 -------------------------------------------------------------
    buildLevelBar() {
      this.levelBarEl.innerHTML = "";
      this.levelButtons = LEVELS.map(level => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "level-chip";
        b.textContent = String(level.id);
        b.title = level.name;
        b.addEventListener("click", () => {
          if (level.id > this.unlocked) {
            this.setMessage(`레벨 ${level.id}은 아직 잠겨 있습니다. 앞 레벨을 먼저 클리어하세요.`);
            return;
          }
          this.loadLevel(level.id);
        });
        this.levelBarEl.appendChild(b);
        return b;
      });
    }

    refreshLevelBar() {
      this.levelButtons.forEach((b, i) => {
        const id = LEVELS[i].id;
        b.classList.toggle("locked", id > this.unlocked);
        b.classList.toggle("active", id === this.level.id);
        b.disabled = id > this.unlocked;
      });
    }

    loadLevel(id) {
      this.level = LEVELS.find(l => l.id === id) || LEVELS[0];
      this.sim = new Sim(this.level);
      this.cells = new Map();
      this.paused = false;
      this.pauseButton.textContent = "일시정지";
      this.clearEl.classList.add("hidden");
      this.nextButton.classList.add("hidden");

      this.levelNameEl.textContent = `레벨 ${this.level.id} — ${this.level.name}`;
      this.levelSubEl.textContent = this.level.subtitle;
      this.hintEl.textContent = this.level.hint;
      this.targetEl.textContent = String(this.level.target);
      this.defectEl.textContent = `${Math.round(this.level.defectRate * 100)}%`;

      this.initDom();
      this.setMode("build");
      this.setStatus("준비");
      this.setMessage("라인을 설계하세요. 드래그로 코너 벨트를 만들 수 있습니다.");
      this.refreshLevelBar();
      this.render();
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
          this.cells.set(key(x, y), cell);
        }
      }

      for (const machine of this.level.machines) {
        const cell = this.cellAt(machine.x, machine.y);
        cell.classList.add("machine", machine.type);
        cell.innerHTML = `<span class="machine-label">${machine.label}</span>${this.machinePorts(machine)}`;
      }
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

    // --- 입력 -------------------------------------------------------------
    bindEvents() {
      this.boardEl.addEventListener("pointerdown", event => {
        const cell = event.target.closest(".cell");
        if (!cell || event.button !== 0) return;
        const pos = this.posFromCell(cell);
        this.isPointerDown = true;
        this.dragPath = [];
        cell.setPointerCapture(event.pointerId);

        if (this.mode === "erase") {
          this.sim.removeBelt(pos.x, pos.y);
          this.setMessage("벨트를 제거했습니다.");
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
          this.sim.removeBelt(pos.x, pos.y);
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
      this.resetButton.addEventListener("click", () => {
        this.sim.reset();
        this.clearEl.classList.add("hidden");
        this.nextButton.classList.add("hidden");
        this.paused = false;
        this.pauseButton.textContent = "일시정지";
        this.setMode("build");
        this.setStatus("준비");
        this.setMessage("초기화했습니다. 라인을 다시 설계하세요.");
        this.render();
      });
      this.pauseButton.addEventListener("click", () => {
        this.paused = !this.paused;
        this.pauseButton.textContent = this.paused ? "재개" : "일시정지";
        this.setMessage(this.paused ? "시뮬레이션을 멈췄습니다." : "시뮬레이션을 다시 시작했습니다.");
      });
      this.nextButton.addEventListener("click", () => {
        const next = LEVELS.find(l => l.id === this.level.id + 1);
        if (next) this.loadLevel(next.id);
      });

      this.boardEl.addEventListener("contextmenu", event => {
        const cell = event.target.closest(".cell");
        if (!cell) return;
        event.preventDefault();
        const pos = this.posFromCell(cell);
        this.sim.removeBelt(pos.x, pos.y);
        this.render();
      });
    }

    setMode(mode) {
      this.mode = mode;
      this.buildButton.classList.toggle("active", mode === "build");
      this.eraseButton.classList.toggle("active", mode === "erase");
      this.boardEl.classList.toggle("erase-cursor", mode === "erase");
    }

    startBuildPath(x, y) {
      if (!this.sim.canBuildAt(x, y)) return;
      const inferred = this.inferIncomingDirection(x, y);
      const belt = this.sim.belts.get(key(x, y)) || {};
      belt.in = inferred || belt.in || "W";
      belt.out = belt.out || OPPOSITE[belt.in];
      this.sim.setBelt(x, y, belt);
      this.dragPath = [{ x, y }];
      this.setMessage("경로를 드래그하세요. 방향을 꺾으면 코너가 됩니다.");
      this.render();
    }

    extendBuildPath(x, y) {
      if (!this.dragPath.length) return;
      if (!this.sim.canBuildAt(x, y)) return;
      const last = this.dragPath[this.dragPath.length - 1];
      if (last.x === x && last.y === y) return;
      const dir = this.directionBetween(last, { x, y });
      if (!dir) return;

      const lastBelt = this.sim.belts.get(key(last.x, last.y)) || { in: OPPOSITE[dir], out: dir };
      lastBelt.out = dir;
      this.sim.setBelt(last.x, last.y, lastBelt);

      const currentBelt = this.sim.belts.get(key(x, y)) || {};
      currentBelt.in = OPPOSITE[dir];
      currentBelt.out = currentBelt.out || dir;
      this.sim.setBelt(x, y, currentBelt);

      this.dragPath.push({ x, y });
      this.render();
    }

    inferIncomingDirection(x, y) {
      for (const dir of DIR_ORDER) {
        const n = this.sim.neighbor(x, y, dir);
        const machine = this.sim.machineMap.get(key(n.x, n.y));
        if (!machine) continue;
        const travelFromMachine = OPPOSITE[dir];
        if (machine.type === "source" && machine.out === travelFromMachine) return dir;
        if (machine.type === "inspector" &&
            (machine.normalOut === travelFromMachine || machine.defectOut === travelFromMachine)) return dir;
      }
      // 옆 칸 벨트가 이쪽으로 뱉고 있으면 그쪽이 입구다.
      // (구버전은 여기서 OPPOSITE 를 한 번 더 뒤집어 반대편을 입구로 잡았다 —
      //  드래그로 덮어써져 잘 드러나지 않던 버그라 이번에 바로잡는다.)
      for (const dir of DIR_ORDER) {
        const n = this.sim.neighbor(x, y, dir);
        const belt = this.sim.belts.get(key(n.x, n.y));
        if (belt && belt.out === OPPOSITE[dir]) return dir;
      }
      return null;
    }

    // --- 루프 -------------------------------------------------------------
    loop(time) {
      const delta = this.lastFrame ? Math.min(80, time - this.lastFrame) : 0;
      this.lastFrame = time;

      if (!this.paused && !this.sim.cleared) {
        const before = this.sim.cleared;
        this.sim.tick(delta);
        this.drainEvents();
        if (!before && this.sim.cleared) this.completeLevel();
        this.render();
      }
      requestAnimationFrame(t => this.loop(t));
    }

    drainEvents() {
      let status = null;
      for (const ev of this.sim.events) {
        if (ev.type === "good") this.setMessage(`정상품 처리 ${ev.count}/${this.level.target}`);
        else if (ev.type === "badSink") { this.setMessage("불량품이 싱크로 들어갔습니다. 카운트는 오르지 않습니다."); status = "싱크 오류"; }
        else if (ev.type === "wasted") this.setMessage("불량품을 폐기 라인으로 보냈습니다.");
        else if (ev.type === "wastedGood") this.setMessage("정상품이 폐기되었습니다. 목표 카운트는 오르지 않습니다.");
        else if (ev.type === "blocked") status = "소스 막힘";
      }
      this.sim.events.length = 0;

      if (this.sim.cleared) this.setStatus("클리어");
      else if (status) this.setStatus(status);
      else if (this.sim.blockedTicks > 3) this.setStatus("라인 막힘");
      else if (this.sim.items.length) this.setStatus("가동 중");
    }

    completeLevel() {
      this.setStatus("클리어");
      this.setMessage(`목표 달성. 레벨 ${this.level.id} 클리어!`);
      this.clearEl.classList.remove("hidden");

      const saved = this.storage.load();
      const record = {
        level: this.level.id,
        clearedAt: new Date().toISOString(),
        elapsedMs: Math.round(this.sim.elapsedMs),
        badSinkCount: this.sim.badSinkCount
      };
      saved.best = saved.best || {};
      const prev = saved.best[this.level.id];
      if (!prev || record.elapsedMs < prev) saved.best[this.level.id] = record.elapsedMs;
      saved.lastClear = record;
      if (this.level.id + 1 <= LEVELS.length) {
        saved.unlocked = Math.max(saved.unlocked || 1, this.level.id + 1);
        this.unlocked = saved.unlocked;
        this.nextButton.classList.remove("hidden");
      }
      this.storage.save(saved);
      this.ranking.submit(record);
      this.refreshLevelBar();
    }

    // --- 그리기 -----------------------------------------------------------
    render() {
      for (const [k, cell] of this.cells) {
        if (this.sim.machineMap.has(k)) continue;
        const belt = this.sim.belts.get(k);
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

      this.cells.forEach(cell => cell.querySelectorAll(".item").forEach(i => i.remove()));
      for (const item of this.sim.items) {
        const cell = this.cellAt(item.x, item.y);
        if (!cell) continue;
        const el = document.createElement("span");
        el.className = `item ${item.kind}${item.flash ? " blocked" : ""}`;
        el.textContent = item.kind === "good" ? "정" : "불";
        cell.appendChild(el);
      }
      this.goodEl.textContent = String(this.sim.goodCount);
    }

    beltClass(belt) {
      const aliases = {
        "W-E": "line-horizontal", "E-W": "line-horizontal",
        "N-S": "line-vertical", "S-N": "line-vertical",
        "W-S": "corner-w-s", "N-E": "corner-n-e", "E-S": "corner-e-s", "N-W": "corner-n-w",
        "S-E": "corner-s-e", "W-N": "corner-w-n", "S-W": "corner-s-w", "E-N": "corner-e-n"
      };
      return aliases[`${belt.in}-${belt.out}`] || "line-horizontal";
    }

    setMessage(m) { this.messageEl.textContent = m; }
    setStatus(s) { this.statusEl.textContent = s; }

    directionBetween(a, b) {
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      if (dx === 1 && dy === 0) return "E";
      if (dx === -1 && dy === 0) return "W";
      if (dx === 0 && dy === 1) return "S";
      if (dx === 0 && dy === -1) return "N";
      return null;
    }

    posFromCell(cell) {
      return { x: Number(cell.dataset.x), y: Number(cell.dataset.y) };
    }

    cellAt(x, y) { return this.cells.get(key(x, y)); }
  }

  window.addEventListener("DOMContentLoaded", () => { new Game(); });
})();
