import "./style.css";
import { SharedCamera, Viewer } from "./viewer";
import { NetPanel } from "./netPanel";
import { polygonFaceColors, randomFaceColors } from "./colors";
import { fullInflate, type InflateStatus, type LevelRecord } from "./physics/pipeline";
import { loadNet, type NetSpec } from "./physics/mesh";
import { type Vec3 } from "./physics/vec3";
import { CONVERGENCE_GTOL } from "./physics/convergence";

const LEVELS = [0, 1, 2, 3];
const IMPLEMENTED_LEVELS = [0, 1];
const DEFAULT_TARGET_RMS_PCT = 10;

const netSelect = document.getElementById("net-select") as HTMLSelectElement;
const inflateBtn = document.getElementById("inflate-btn") as HTMLButtonElement;
const randomizeItem = document.getElementById("randomize-item") as HTMLButtonElement;
const colorItems = document.querySelectorAll<HTMLButtonElement>("[data-color-mode]");
const statusEl = document.getElementById("status")!;
const targetInput = document.getElementById("target-1") as HTMLInputElement;
const toleranceInput = document.getElementById("tolerance") as HTMLInputElement;
const historyBody = document.querySelector<HTMLTableSectionElement>("#history tbody")!;

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

// Shown mesh topology, shared by Levels 0 and 1 (Level 1 reuses Level 0's topology).
let topology: { faces: number[][]; faceOfFine: number[] } | null = null;
const levelPositions: (Map<number, Vec3> | null)[] = LEVELS.map(() => null);
const history: (LevelRecord | null)[] = LEVELS.map(() => null);

function setStatus(text: string, kind: StatusKind = "info") {
  statusEl.textContent = text;
  statusEl.className = kind;
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

// ---- Panels --------------------------------------------------------------------------------

function showLevel(level: number, positions: Map<number, Vec3>) {
  if (!topology) return;
  levelPositions[level] = positions;
  viewers[level].setMesh(topology.faces, positions, topology.faceOfFine, currentBaseColors());
}

function clearComputedLevels() {
  for (const level of IMPLEMENTED_LEVELS) {
    levelPositions[level] = null;
    viewers[level].clear();
    levelMessages[level].textContent = "";
    history[level] = null;
  }
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

function readTargetRms(): number {
  const parsed = parseFloat(targetInput.value);
  const value = Number.isFinite(parsed) ? Math.min(100, Math.max(0, Math.round(parsed))) : DEFAULT_TARGET_RMS_PCT;
  targetInput.value = `${value}%`;
  return value;
}

function readTolerance(): number {
  const parsed = parseFloat(toleranceInput.value);
  const value = Number.isFinite(parsed) && parsed > 0 ? parsed : CONVERGENCE_GTOL;
  toleranceInput.value = value.toExponential(0).replace(/e([+-])(\d)$/, (_m, sign, d) => `e${sign}0${d}`);
  return value;
}

targetInput.addEventListener("focus", () => (targetInput.value = String(parseFloat(targetInput.value))));
targetInput.addEventListener("blur", readTargetRms);
toleranceInput.addEventListener("blur", readTolerance);
for (const input of [targetInput, toleranceInput]) {
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

function onProgress(status: InflateStatus) {
  const level = status.stage === "level0" ? 0 : 1;
  setStatus(`Full Inflate -- Level ${level}: Step ${status.steps}.`);
}

function onRecord(record: LevelRecord) {
  history[record.level] = record;
  if (record.level === 1) {
    levelMessages[1].textContent = record.state === "running" ? "Computing..." : "";
  }
  renderHistory();
}

async function inflate() {
  if (running || !currentSpec) return;
  stopRequested = false;
  const targetRmsPct = readTargetRms();
  const gtol = readTolerance();
  setRunning(true);
  clearComputedLevels();
  setStatus("Full Inflate -- Level 0: Step 0.");
  try {
    const result = await fullInflate(currentSpec, {
      targetRmsPct,
      gtol,
      onStatus: onProgress,
      onRecord,
      onTopology: (faces, faceOfFine) => (topology = { faces, faceOfFine }),
      onLevelPositions: showLevel,
      shouldStop: () => stopRequested,
    });
    setStatus(
      `Full Inflate -- Done. RMS stretch ${result.rmsStretchPct.toFixed(1)}%, pressure ${result.pressure.toFixed(2)}.`,
      "success",
    );
  } catch (err) {
    console.error(err);
    levelMessages[1].textContent = "";
    setStatus(
      stopRequested ? "Full Inflate -- Stopped." : `Full Inflate -- ${err instanceof Error ? err.message : String(err)}`,
      stopRequested ? "warn" : "error",
    );
  } finally {
    setRunning(false);
  }
}

async function selectNet(net: NetIndexEntry) {
  currentNet = net;
  currentSpec = null;
  setRunning(false);
  try {
    const spec = await fetchJson<NetSpec>(`nets/${net.file}`);
    baseFaces = loadNet(spec).faces;
    currentSpec = spec;
    multiColors = randomFaceColors(baseFaces);
    topology = null;
    netPanel.setNet(spec);
    netPanel.setColors(colorMode, multiColors);
    clearComputedLevels();
    setStatus(`Loaded ${net.label}.`);
  } catch (err) {
    console.error(err);
    setStatus(err instanceof Error ? err.message : String(err), "error");
    return;
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
  });
  setColorMode("polygon");

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
  }
}

void init();
