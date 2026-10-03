import "./style.css";
import { SharedCamera, Viewer, type DebugOverlays } from "./viewer";
import { NetPanel } from "./netPanel";
import { polygonFaceColors, randomFaceColors } from "./colors";
import { fullInflate, type LevelRecord } from "./physics/pipeline";
import { type ReplayFrame } from "./physics/relaxOnce";
import { loadNet, type NetSpec } from "./physics/mesh";
import { type Vec3 } from "./physics/vec3";
import { CONVERGENCE_GTOL } from "./physics/convergence";

const LEVELS = [0, 1, 2, 3];
const DEFAULT_TARGET_RMS_PCT = 10;

const netSelect = document.getElementById("net-select") as HTMLSelectElement;
const inflateBtn = document.getElementById("inflate-btn") as HTMLButtonElement;
const randomizeItem = document.getElementById("randomize-item") as HTMLButtonElement;
const colorItems = document.querySelectorAll<HTMLButtonElement>("[data-color-mode]");
const statusEl = document.getElementById("status")!;
const spinnerEl = document.getElementById("spinner")!;
const targetInputs = [1, 2, 3].map((level) => document.getElementById(`target-${level}`) as HTMLInputElement);
const toleranceInput = document.getElementById("tolerance") as HTMLInputElement;
const historyBody = document.querySelector<HTMLTableSectionElement>("#history tbody")!;
const debugRow = document.getElementById("debug-row")!;
const debugBoxes = {
  faceNormals: document.getElementById("show-face-normals") as HTMLInputElement,
  vertexNormals: document.getElementById("show-vertex-normals") as HTMLInputElement,
  repulsiveForces: document.getElementById("show-repulsive-forces") as HTMLInputElement,
};

const camera = new SharedCamera();
const viewers: Viewer[] = LEVELS.map(
  (level) => new Viewer(document.getElementById(`panel-${level}`)!, camera, renderAll),
);
const levelMessages = LEVELS.map((level) => document.querySelector<HTMLElement>(`#panel-${level} .panel-msg`)!);
const netPanel = new NetPanel(document.getElementById("panel-net")!);

function renderAll() {
  viewers.forEach((v) => v.render());
}

interface NetIndexEntry {
  label: string;
  file: string;
}

type ColorMode = "polygon" | "multi";
type StatusKind = "info" | "success" | "error" | "warn";

let currentNet: NetIndexEntry | null = null;
let currentSpec: NetSpec | null = null;
let baseFaces: number[][] = [];
let colorMode: ColorMode = "polygon";
let multiColors: number[] = [];
let running = false;
let stopRequested = false;
let debugMode = false;
let busyCount = 0;

// Shown mesh topology per level (Level 1 reuses Level 0's triangulation; 2 and 3 are subdivisions).
const levelTopology: ({ faces: number[][]; faceOfFine: number[] } | null)[] = LEVELS.map(() => null);
const levelPositions: (Map<number, Vec3> | null)[] = LEVELS.map(() => null);
const history: (LevelRecord | null)[] = LEVELS.map(() => null);

interface Replay {
  wrap: HTMLDivElement;
  input: HTMLInputElement;
  frames: ReplayFrame[];
}

const replays: Replay[] = LEVELS.map((level) => {
  const wrap = document.createElement("div");
  wrap.className = "replay";
  wrap.hidden = true;
  const input = document.createElement("input");
  input.type = "range";
  input.min = "0";
  input.max = "0";
  input.value = "0";
  wrap.append(input);
  document.getElementById(`panel-${level}`)!.parentElement!.appendChild(wrap);
  input.addEventListener("input", () => showReplayFrame(level, Number(input.value)));
  return { wrap, input, frames: [] };
});

function setStatus(text: string, kind: StatusKind = "info") {
  statusEl.textContent = text;
  statusEl.className = kind;
}

function setBusy(delta: number) {
  busyCount += delta;
  spinnerEl.hidden = busyCount <= 0;
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status} ${res.statusText}`);
  return res.json();
}

// ---- Colours -------------------------------------------------------------------------------

function currentBaseColors(): number[] {
  return colorMode === "polygon" ? polygonFaceColors(baseFaces) : multiColors;
}

function applyColors() {
  const colors = currentBaseColors();
  viewers.forEach((v, level) => levelPositions[level] && v.setBaseColors(colors));
  netPanel.setColors(colorMode, multiColors);
}

function setColorMode(mode: ColorMode) {
  colorMode = mode;
  colorItems.forEach((item) => item.classList.toggle("selected", item.dataset.colorMode === mode));
  randomizeItem.disabled = mode !== "multi"; // Randomize only does something in Multi-colour mode
  applyColors();
}

function randomize() {
  if (colorMode !== "multi" || !baseFaces.length) return;
  multiColors = randomFaceColors(baseFaces);
  applyColors();
}

// ---- Debug mode ----------------------------------------------------------------------------

function applyDebugOverlays() {
  const flags: DebugOverlays = debugMode
    ? {
        faceNormals: debugBoxes.faceNormals.checked,
        vertexNormals: debugBoxes.vertexNormals.checked,
        repulsiveForces: debugBoxes.repulsiveForces.checked,
      }
    : { faceNormals: false, vertexNormals: false, repulsiveForces: false };
  viewers.forEach((v) => v.setOverlays(flags));
}

function setDebugMode(on: boolean) {
  debugMode = on;
  debugRow.hidden = !on;
  document.title = on ? "Interactive Inflater (debug mode)" : "Interactive Inflater";
  if (!on) for (const box of Object.values(debugBoxes)) box.checked = false;
  applyDebugOverlays();
  replays.forEach((r, level) => {
    r.wrap.hidden = !on || r.frames.length < 2;
    if (!on && r.frames.length) showReplayFrame(level, r.frames.length - 1);
  });
}

// ---- Replay --------------------------------------------------------------------------------

function showReplayFrame(level: number, index: number) {
  const r = replays[level];
  const frame = r.frames[index];
  if (!frame) return;
  r.input.value = String(index);
  viewers[level].showPositions(frame.positions);
}

function setReplayFrames(level: number, frames: ReplayFrame[]) {
  const r = replays[level];
  r.frames = frames;
  r.input.max = String(Math.max(0, frames.length - 1));
  r.wrap.hidden = !debugMode || frames.length < 2;
  showReplayFrame(level, Math.max(0, frames.length - 1));
}

function clearReplays() {
  for (const r of replays) {
    r.frames = [];
    r.wrap.hidden = true;
    r.input.max = "0";
    r.input.value = "0";
  }
}

// ---- Panels --------------------------------------------------------------------------------

function showLevel(level: number, positions: Map<number, Vec3>) {
  const topo = levelTopology[level];
  if (!topo) return;
  levelPositions[level] = positions;
  viewers[level].setMesh(topo.faces, positions, topo.faceOfFine, currentBaseColors());
}

function onLevelResult(level: number, positions: Map<number, Vec3>, frames: ReplayFrame[]) {
  showLevel(level, positions);
  setReplayFrames(level, frames);
}

function clearComputedLevels() {
  for (const level of LEVELS) {
    levelPositions[level] = null;
    viewers[level].clear();
    levelMessages[level].textContent = "";
    history[level] = null;
  }
  clearReplays();
  renderHistory();
}

// ---- Convergence history -------------------------------------------------------------------

function mmss(seconds: number): string {
  const total = Math.round(seconds);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function renderHistory() {
  let cumulative = 0;
  historyBody.replaceChildren(
    ...LEVELS.map((level) => {
      const rec = history[level];
      if (rec) cumulative += rec.simTimeS;
      const cells = rec
        ? [
            rec.pressure === null ? "--" : rec.pressure.toFixed(2),
            String(rec.steps),
            rec.rmsStretchPct === null ? "--" : rec.rmsStretchPct.toFixed(1),
            mmss(rec.simTimeS),
            mmss(cumulative),
            rec.optimality === null
              ? "--"
              : `${rec.optimality.toExponential(2)} ${rec.optimality < rec.gtol ? "<" : "≥"} ${rec.gtol.toExponential(0)}` +
                (rec.state === "converged" ? " ✓" : ""),
          ]
        : ["--", "--", "--", "--", "--", "--"];
      const tr = document.createElement("tr");
      if (rec) tr.className = rec.state;
      for (const text of [String(level), ...cells]) {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      }
      return tr;
    }),
  );
}

// ---- Parameters ----------------------------------------------------------------------------

function readTargetRms(input: HTMLInputElement): number {
  const parsed = parseFloat(input.value);
  const value = Number.isFinite(parsed) ? Math.min(100, Math.max(0, Math.round(parsed))) : DEFAULT_TARGET_RMS_PCT;
  input.value = `${value}%`;
  return value;
}

function readTolerance(): number {
  const parsed = parseFloat(toleranceInput.value);
  const value = Number.isFinite(parsed) && parsed > 0 ? parsed : CONVERGENCE_GTOL;
  toleranceInput.value = value.toExponential(0).replace(/e([+-])(\d)$/, (_m, sign, d) => `e${sign}0${d}`);
  return value;
}

for (const input of targetInputs) {
  input.addEventListener("focus", () => (input.value = String(parseFloat(input.value))));
  input.addEventListener("blur", () => readTargetRms(input));
}
toleranceInput.addEventListener("blur", readTolerance);
for (const input of [...targetInputs, toleranceInput]) {
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") input.blur();
    e.stopPropagation(); // keep typing from triggering the P/M/R shortcuts
  });
}

// ---- Inflate -------------------------------------------------------------------------------

function setRunning(value: boolean) {
  running = value;
  inflateBtn.textContent = value ? "Stop Simulation" : "Run Simulation";
  inflateBtn.disabled = !value && !currentNet;
}

function onRecord(record: LevelRecord) {
  history[record.level] = record;
  if (record.state === "running") {
    levelMessages[record.level].textContent = "Computing...";
    setStatus(`Full Inflate -- Computing Level ${record.level}...`);
  } else {
    levelMessages[record.level].textContent = "";
  }
  renderHistory();
}

async function inflate() {
  if (running || !currentSpec) return;
  stopRequested = false;
  const targetRmsPctByLevel = Object.fromEntries(targetInputs.map((input, i) => [i + 1, readTargetRms(input)]));
  const gtol = readTolerance();
  setRunning(true);
  clearComputedLevels();
  setBusy(1);
  try {
    const result = await fullInflate(currentSpec, {
      targetRmsPctByLevel,
      gtol,
      onRecord,
      onTopology: (level, faces, faceOfFine) => (levelTopology[level] = { faces, faceOfFine }),
      onLevelResult,
      shouldStop: () => stopRequested,
    });
    setStatus(
      `Full Inflate -- Done. RMS stretch ${result.rmsStretchPct.toFixed(1)}%, pressure ${result.pressure.toFixed(2)}.`,
      "success",
    );
  } catch (err) {
    console.error(err);
    for (const level of LEVELS) levelMessages[level].textContent = "";
    setStatus(
      stopRequested ? "Full Inflate -- Stopped." : `Full Inflate -- ${err instanceof Error ? err.message : String(err)}`,
      stopRequested ? "warn" : "error",
    );
  } finally {
    setBusy(-1);
    setRunning(false);
  }
}

async function selectNet(net: NetIndexEntry) {
  currentNet = net;
  currentSpec = null;
  setRunning(false);
  setBusy(1);
  setStatus(`Loading ${net.label}...`);
  try {
    const spec = await fetchJson<NetSpec>(`nets/${net.file}`);
    baseFaces = loadNet(spec).faces;
    currentSpec = spec;
    multiColors = randomFaceColors(baseFaces);
    levelTopology.fill(null);
    netPanel.setNet(spec);
    netPanel.setColors(colorMode, multiColors);
    clearComputedLevels();
    setStatus(`Loaded ${net.label}.`);
  } catch (err) {
    console.error(err);
    setStatus(err instanceof Error ? err.message : String(err), "error");
  } finally {
    setBusy(-1);
  }
}

function onInflateButton() {
  if (running) stopRequested = true;
  else void inflate();
}

function isTypingTarget(e: KeyboardEvent) {
  return e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
}

async function init() {
  renderHistory();
  inflateBtn.addEventListener("click", onInflateButton);
  colorItems.forEach((item) => item.addEventListener("click", () => setColorMode(item.dataset.colorMode as ColorMode)));
  randomizeItem.addEventListener("click", randomize);
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(e)) return;
    const key = e.key.toLowerCase();
    if (key === "p") setColorMode("polygon");
    else if (key === "m") setColorMode("multi");
    else if (key === "r") randomize();
    else if (key === "d") setDebugMode(!debugMode);
  });
  for (const box of Object.values(debugBoxes)) box.addEventListener("change", applyDebugOverlays);
  setColorMode("polygon");

  setBusy(1);
  try {
    const nets = await fetchJson<NetIndexEntry[]>("nets/index.json");
    for (const net of nets) {
      const option = document.createElement("option");
      option.value = net.file;
      option.textContent = net.label;
      netSelect.appendChild(option);
    }
    netSelect.addEventListener("change", () => {
      const net = nets.find((n) => n.file === netSelect.value);
      if (running) {
        netSelect.value = currentNet?.file ?? "";
      } else if (net) {
        void selectNet(net);
      }
    });
    setStatus("Choose a net, then Run Simulation.");
  } catch (err) {
    console.error(err);
    setStatus(err instanceof Error ? err.message : String(err), "error");
  } finally {
    setBusy(-1);
  }
}

void init();
