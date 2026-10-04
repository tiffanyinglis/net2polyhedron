import { SharedCamera, Viewer, type CameraHooks, type DebugOverlays } from "./viewer";
import { NetPanel } from "./netPanel";
import { displayColors, fitMultiColors, randomFaceColors, type ColorMode, type ColorState } from "../utils/colors";
import { copyColors, sameCamera, sameNetView, UndoStack, type EditSnapshot } from "./editState";
import { ViewerPane } from "./viewerPane";
import { mountAppNav, revealPage } from "../utils/appNav";
import { defaultTargetRmsPct } from "../utils/physics/pipeline";
import { type ReplayFrame } from "../utils/physics/relaxOnce";
import { loadNet, type NetSpec } from "../utils/physics/mesh";
import { repulsionMultipliers } from "../utils/physics/pipeline";
import { type Vec3 } from "../utils/physics/vec3";
import {
  LEVELS,
  LevelStore,
  renderHistoryTable,
  readTargetRmsPct,
  readTolerance,
  runFullInflate,
  wireParamInput,
  type RunOutcome,
  type StatusKind,
} from "../utils/inflaterRun";
import {
  SESSION_EXTENSION,
  parseSession,
  restoreLevel,
  serializeSession,
  snapshotLevel,
  type SessionData,
} from "../utils/session";

let defaultTargetRms = 10;

/** The slice of the File System Access API used for Save Session (not in every TS DOM lib). */
interface SaveHandle {
  name: string;
  createWritable(): Promise<{ write(data: string): Promise<void>; close(): Promise<void> }>;
}
type SaveWindow = Window & {
  showSaveFilePicker?: (options: {
    suggestedName: string;
    startIn: "downloads";
    types: { description: string; accept: Record<string, string[]> }[];
  }) => Promise<SaveHandle>;
};

const netSelect = document.getElementById("net-select") as HTMLSelectElement;
const inflateBtn = document.getElementById("inflate-btn") as HTMLButtonElement;
const loadModelItem = document.getElementById("load-model-item") as HTMLButtonElement;
const loadSessionItem = document.getElementById("load-session-item") as HTMLButtonElement;
const saveSessionItem = document.getElementById("save-session-item") as HTMLButtonElement;
const runAllItem = document.getElementById("run-all-item") as HTMLButtonElement;
const debugAllItem = document.getElementById("debug-all-item") as HTMLButtonElement;
const undoItem = document.getElementById("undo-item") as HTMLButtonElement;
const redoItem = document.getElementById("redo-item") as HTMLButtonElement;
const modelFileInput = document.getElementById("model-file") as HTMLInputElement;
const sessionFileInput = document.getElementById("session-file") as HTMLInputElement;
const randomizeItem = document.getElementById("randomize-item") as HTMLButtonElement;
const colorItems = document.querySelectorAll<HTMLButtonElement>("[data-color-mode]");
const viewItems = document.querySelectorAll<HTMLButtonElement>("[data-view]");
const statusEl = document.getElementById("status")!;
const statusRowEl = document.getElementById("status-row")!;
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
/** Shown in both modes; not reset when debug mode is toggled. */
const layerBoxes = {
  polygonOutlines: document.getElementById("show-polygon-outlines") as HTMLInputElement,
  subdivisions: document.getElementById("show-subdivisions") as HTMLInputElement,
};
const inflaterView = document.getElementById("inflater-view")!;
const viewerView = document.getElementById("viewer-view")!;
const viewerCounterEl = document.getElementById("viewer-counter")!;
const viewerMessageEl = document.getElementById("viewer-message")!;
const unsavedDialog = document.getElementById("unsaved-dialog") as HTMLDialogElement;
const unsavedText = document.getElementById("unsaved-text")!;

// ---- Views ---------------------------------------------------------------------------------

/** View > Inflater (the live net and its levels) or View > Viewer (saved sessions, read-only). */
type View = "inflater" | "viewer";
let view: View = "inflater";

const camera = new SharedCamera();
let inflaterGestureStart: EditSnapshot | null = null;
/** Camera gestures in the Inflater view record undo steps the same way the Python app does. */
const inflaterCameraHooks: CameraHooks = {
  onGestureStart: () => (inflaterGestureStart = inflaterSnapshot()),
  onGestureEnd: () => {
    const start = inflaterGestureStart;
    inflaterGestureStart = null;
    // A click without any movement leaves no undo step.
    if (start && !sameCamera(start.camera, camera.snapshot())) inflaterUndo.push(start);
    refreshMenus();
  },
  onBeforeDiscreteEdit: () => {
    inflaterUndo.push(inflaterSnapshot());
    refreshMenus();
  },
};
const viewers: Viewer[] = LEVELS.map(
  (level) => new Viewer(document.getElementById(`panel-${level}`)!, camera, renderAll, inflaterCameraHooks),
);
const levelPanels = LEVELS.map((level) => document.getElementById(`panel-${level}`)!);
const netPanelEl = document.getElementById("panel-net")!;
let netGestureStart: EditSnapshot | null = null;
/** Pan/zoom of the net panel is undoable, like the Level cameras. */
const netHooks: CameraHooks = {
  onGestureStart: () => (netGestureStart = inflaterSnapshot()),
  onGestureEnd: () => {
    const start = netGestureStart;
    netGestureStart = null;
    if (start?.net && !sameNetView(start.net, netPanel.view())) inflaterUndo.push(start);
    refreshMenus();
  },
  onBeforeDiscreteEdit: () => {
    inflaterUndo.push(inflaterSnapshot());
    refreshMenus();
  },
};
const netPanel = new NetPanel(netPanelEl, netHooks);

const viewer = new ViewerPane(
  [0, 1, 2, 3].map((i) => document.getElementById(`vpanel-${i}`)!),
  viewerMessageEl,
  {
    onChange: () => refreshMenus(),
    onError: (message) => window.alert(message),
  },
);

/** Shows the counter under the Viewer grid (m / n), refreshed whenever the Viewer's file changes. */
function refreshViewerCounter() {
  viewerCounterEl.textContent = viewer.counterText();
}

function setLoading(el: HTMLElement, on: boolean) {
  el.classList.toggle("loading", on);
}

function renderAll() {
  viewers.forEach((v) => v.render());
}

interface NetIndexEntry {
  label: string;
  file: string;
}

let currentNet: NetIndexEntry | null = null;
let currentSpec: NetSpec | null = null;
let baseFaces: number[][] = [];
let running = false;
let stopRequested = false;
let debugMode = false;
let busyCount = 0;

/** The Inflater view's Colour state (the Viewer keeps its own per file). */
const inflaterColors: ColorState = { mode: "polygon", multiColors: [] };
/** Inflater's undo/redo: its Colour state plus its camera, as in the Python app. */
const inflaterUndo = new UndoStack<EditSnapshot>();

/** Topology, positions and convergence record per level (Level 1 reuses Level 0's triangulation; 2 and 3 are subdivisions). */
const store = new LevelStore();

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
  input.disabled = true; // enabled once the level has replay frames to scrub
  wrap.append(input);
  document.getElementById(`panel-${level}`)!.parentElement!.appendChild(wrap);
  input.addEventListener("input", () => showReplayFrame(level, Number(input.value)));
  return { wrap, input, frames: [] };
});

let lastStatus: { text: string; kind: StatusKind } = { text: "", kind: "info" };

function setStatus(text: string, kind: StatusKind = "info") {
  lastStatus = { text, kind };
  applyStatus();
}

/** Info (blue) messages are debug-only; errors, warnings, and success always show. */
function applyStatus() {
  statusEl.textContent = lastStatus.text;
  statusEl.className = lastStatus.kind;
  // Release mode: only errors stay visible; the row is hidden entirely otherwise (no empty gap).
  statusRowEl.hidden = lastStatus.kind !== "error" && !debugMode;
}

function setBusy(delta: number) {
  busyCount += delta;
  applySpinner();
}

/** The status-row spinner is debug-only, like the blue info message it sits beside. */
function applySpinner() {
  spinnerEl.hidden = busyCount <= 0 || !debugMode;
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status} ${res.statusText}`);
  return res.json();
}

// ---- Colours -------------------------------------------------------------------------------

function currentBaseColors(): number[] {
  return displayColors(inflaterColors, baseFaces, currentSpec);
}

function applyInflaterColors() {
  fitMultiColors(inflaterColors, baseFaces);
  const colors = currentBaseColors();
  viewers.forEach((v, level) => store.positions[level] && v.setBaseColors(colors));
  netPanel.setColors(inflaterColors.mode, inflaterColors.multiColors);
}

/** Colour > Polygon-specific / Multi-colour (and P / M). Undoable, and in the Viewer it applies to the file on screen. */
function setColorMode(mode: ColorMode) {
  if (view === "viewer") {
    viewer.setColorMode(mode);
  } else if (inflaterColors.mode !== mode) {
    inflaterUndo.push(inflaterSnapshot());
    inflaterColors.mode = mode;
    applyInflaterColors();
  }
  refreshMenus();
}

/** Colour > Randomize (and R): re-rolls the Multi-colour palette. Only does anything in Multi-colour mode. */
function randomize() {
  if (view === "viewer") {
    viewer.randomize();
  } else if (inflaterColors.mode === "multi" && baseFaces.length) {
    inflaterUndo.push(inflaterSnapshot());
    inflaterColors.multiColors = randomFaceColors(baseFaces);
    applyInflaterColors();
  }
  refreshMenus();
}

// ---- Undo / redo ---------------------------------------------------------------------------

function inflaterSnapshot(): EditSnapshot {
  return { camera: camera.snapshot(), colors: copyColors(inflaterColors), net: netPanel.view() };
}

function restoreInflater(snap: EditSnapshot) {
  camera.apply(snap.camera);
  if (snap.net) netPanel.setView(snap.net);
  inflaterColors.mode = snap.colors.mode;
  inflaterColors.multiColors = [...snap.colors.multiColors];
  applyInflaterColors();
  renderAll();
}

/** Edit > Undo / Ctrl+Z: the Viewer's own stack in the Viewer, Inflater's otherwise. */
function undo() {
  if (view === "viewer") {
    viewer.undo();
  } else {
    const target = inflaterUndo.undo(inflaterSnapshot());
    if (target) restoreInflater(target);
  }
  refreshMenus();
}

/** Edit > Redo / Ctrl+Y. */
function redo() {
  if (view === "viewer") {
    viewer.redo();
  } else {
    const target = inflaterUndo.redo(inflaterSnapshot());
    if (target) restoreInflater(target);
  }
  refreshMenus();
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
  viewers.forEach((v) => v.setLayers(layerBoxes.polygonOutlines.checked, layerBoxes.subdivisions.checked));
}

function setDebugMode(on: boolean) {
  debugMode = on;
  applyStatus();
  applySpinner();
  debugRow.hidden = !on;
  netSpacer.hidden = !on;
  // Leaving debug mode clears the overlays; the layer checkboxes keep their state.
  debugBoxes.faceNormals.checked = false;
  debugBoxes.vertexNormals.checked = false;
  debugBoxes.repulsiveForces.checked = false;
  applyDebugOverlays();
  replays.forEach((r, level) => {
    r.wrap.hidden = !on;
    if (!on && r.frames.length) showReplayFrame(level, r.frames.length - 1);
  });
  refreshMenus();
}

/** Invisible stand-in for a Level panel's replay bar, so the Net panel is the same height as the rest in debug mode. */
const netSpacer = document.createElement("div");
netSpacer.className = "replay spacer";
netSpacer.hidden = true;
netSpacer.innerHTML = '<input type="range" disabled />';
netPanelEl.parentElement!.appendChild(netSpacer);

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
  r.input.disabled = frames.length < 2;
  r.wrap.hidden = !debugMode;
  showReplayFrame(level, Math.max(0, frames.length - 1));
}

function clearReplays() {
  for (const r of replays) {
    r.frames = [];
    r.wrap.hidden = !debugMode;
    r.input.disabled = true;
    r.input.max = "0";
    r.input.value = "0";
  }
}

// ---- Panels --------------------------------------------------------------------------------

function showLevel(level: number, positions: Map<number, Vec3>) {
  const topo = store.topology[level];
  if (!topo) return;
  viewers[level].setMesh(topo.faces, topo.faceEdgeIds, positions, topo.faceOfFine, currentBaseColors(), topo.outlineEdgeIds);
  if (currentSpec) viewers[level].setRepulsion(repulsionMultipliers(loadNet(currentSpec), level));
}

function onLevelResult(level: number, positions: Map<number, Vec3>, frames: ReplayFrame[]) {
  showLevel(level, positions);
  setReplayFrames(level, frames);
}

function clearComputedLevels() {
  for (const level of LEVELS) {
    viewers[level].clear();
    setLoading(levelPanels[level], false);
  }
  store.clear();
  clearReplays();
  renderHistory();
}

// ---- Convergence history -------------------------------------------------------------------

/** Redraws the Convergence History table from the shared store. */
function renderHistory() {
  renderHistoryTable(historyBody, store);
}

// ---- Parameters ----------------------------------------------------------------------------

function readTargetRms(input: HTMLInputElement): number {
  return readTargetRmsPct(input, defaultTargetRms);
}

for (const input of targetInputs) {
  wireParamInput(
    input,
    () => readTargetRms(input),
    () => (input.value = String(parseFloat(input.value))),
  );
}
wireParamInput(toleranceInput, () => readTolerance(toleranceInput));

// ---- Inflate -------------------------------------------------------------------------------

function setRunning(value: boolean) {
  running = value;
  inflateBtn.textContent = value ? "Stop Simulation" : "Run Simulation";
  // Enabled while running (so it can be stopped) or once the selected net file has loaded.
  inflateBtn.disabled = !value && !currentSpec;
  refreshMenus();
}

/** One Full Inflate of the current net. Doesn't touch `running` -- the caller (inflate / runAll) owns it. */
async function runSimulation(): Promise<RunOutcome> {
  const targetRmsPctByLevel = Object.fromEntries(targetInputs.map((input, i) => [i + 1, readTargetRms(input)]));
  const gtol = readTolerance(toleranceInput);
  clearComputedLevels();
  setBusy(1);
  try {
    return await runFullInflate(currentSpec!, {
      label: "Full Inflate",
      targetRmsPctByLevel,
      gtol,
      store,
      shouldStop: runInterrupted,
      hooks: {
        status: setStatus,
        loading: (level, on) => setLoading(levelPanels[level], on),
        showLevel: onLevelResult,
        historyChanged: renderHistory,
      },
    });
  } finally {
    setBusy(-1);
  }
}

async function inflate() {
  if (running || !currentSpec) return;
  stopRequested = false;
  setRunning(true);
  await runSimulation();
  setRunning(false);
}

// ---- Run All -------------------------------------------------------------------------------

/** A batch run in progress. Debug All (`pause`) waits after each net for Right (next) or Left (previous);
 * Right/Left pressed mid-run abandon that net and jump the same way. Both set `jumpTo`. */
interface Batch {
  pause: boolean;
  index: number;
  awaiting: boolean;
  jumpTo: number | null;
  wake: (() => void) | null;
}
let batch: Batch | null = null;

/** The current net's run should cut short: Stop was pressed, or a Debug All jump was requested. */
function runInterrupted(): boolean {
  return stopRequested || (batch !== null && batch.jumpTo !== null);
}

/** Right/Left during Debug All: moves to the net `dir` away from the one on screen. */
function onBatchKey(dir: 1 | -1) {
  if (!batch?.pause) return;
  batch.jumpTo = batch.index + dir;
  if (batch.awaiting) {
    batch.awaiting = false;
    batch.wake?.();
  }
}

/** Every .poly in data/inputs/ through Full Inflate, one after another. Run All saves each result to
 * data/outputs/<name>.hippo; Debug All (`pause`) saves nothing and waits for Right after each net.
 * Stop stops the batch after the current net. A failed net is skipped and reported. */
async function runBatch(save: boolean, pause: boolean) {
  if (running || view === "viewer") return;
  let files: string[];
  try {
    files = await fetchJson<string[]>("/api/inputs");
  } catch {
    setStatus("Run All needs the dev server (npm run dev) to read inputs/ and write outputs/.", "error");
    return;
  }
  stopRequested = false;
  const run: Batch = { pause, index: 0, awaiting: false, jumpTo: null, wake: null };
  batch = run;
  setRunning(true);
  const label = save ? "Run All" : "Debug All";
  const saved: string[] = [];
  const failed: string[] = [];
  let stopped = false;
  try {
    let i = 0;
    while (i < files.length) {
      if (stopRequested) {
        stopped = true;
        break;
      }
      const name = files[i].replace(/\.poly$/, "");
      run.index = i;
      run.jumpTo = null;
      setStatus(`${label} -- ${i + 1} of ${files.length}: ${name}`);
      try {
        installNet(await fetchJson<NetSpec>(`../inputs/${files[i]}`), { label: name, file: "" });
      } catch (err) {
        console.error(err);
        failed.push(name);
        i++;
        continue;
      }
      const outcome = await runSimulation();
      if (run.jumpTo !== null) {
        i = Math.max(0, run.jumpTo);
        continue;
      }
      if (stopRequested) {
        stopped = true;
        break;
      }
      if (outcome === "error") {
        failed.push(name);
      } else if (save) {
        try {
          await saveToOutputs(name);
          saved.push(name);
        } catch (err) {
          console.error(err);
          failed.push(name);
        }
      }
      if (pause) {
        run.awaiting = true;
        setStatus(`${label} -- ${name} done. Right: next net, Left: previous net.`);
        await new Promise<void>((resolve) => (run.wake = resolve));
        run.wake = null;
        if (stopRequested) {
          stopped = true;
          break;
        }
        i = run.jumpTo ?? i + 1;
        continue;
      }
      i++;
    }
  } finally {
    batch = null;
    setRunning(false);
  }
  const summary = save
    ? `Run All -- ${stopped ? "Stopped. " : "Done. "}Saved ${saved.length} of ${files.length} to data/outputs`
    : `Debug All -- ${stopped ? "Stopped. " : "Done. "}Nothing saved (${files.length} nets)`;
  setStatus(failed.length ? `${summary}; failed: ${failed.join(", ")}.` : `${summary}.`, failed.length ? "error" : "success");
}

/** POSTs the current session to the dev server as data/outputs/<name>.hippo. */
async function saveToOutputs(name: string) {
  const res = await fetch(`/api/outputs/${encodeURIComponent(name + SESSION_EXTENSION)}`, {
    method: "POST",
    body: serializeSession(buildSessionData()),
  });
  if (!res.ok) throw new Error(`save failed: ${res.status}`);
}

async function selectNet(net: NetIndexEntry) {
  currentNet = net;
  currentSpec = null;
  setRunning(false);
  setBusy(1);
  netPanel.setNet(null);
  clearComputedLevels();
  setStatus(`Loading ${net.label}...`);
  setLoading(netPanelEl, true);
  try {
    installNet(await fetchJson<NetSpec>(`../inputs/${net.file}`), net);
  } catch (err) {
    console.error(err);
    setStatus(err instanceof Error ? err.message : String(err), "error");
  } finally {
    setLoading(netPanelEl, false);
    setBusy(-1);
  }
}

/** Makes `spec` the current net and resets everything tied to the previous one. Throws (leaving
 * the previous net in place) if `spec` isn't a valid net. */
function installNet(spec: NetSpec, net: NetIndexEntry) {
  const mesh = loadNet(spec);
  currentNet = net;
  baseFaces = mesh.faces;
  currentSpec = spec;
  if (!running) setRunning(false); // Run All installs each net while `running` is held for the whole batch
  defaultTargetRms = defaultTargetRmsPct(mesh);
  for (const input of targetInputs) input.value = `${defaultTargetRms}%`;
  inflaterColors.multiColors = randomFaceColors(baseFaces);
  netPanel.setNet(spec);
  applyInflaterColors();
  clearComputedLevels();
  showNetInSelect(net);
  setStatus(`Loaded ${net.label}.`);
  refreshMenus();
}

// ---- Files ---------------------------------------------------------------------------------

/** Option value for a net loaded from disk (File > Load Model / a session), not in the catalogue. */
const CUSTOM_NET_VALUE = "__custom__";

function showNetInSelect(net: NetIndexEntry) {
  netSelect.querySelector(`option[value="${CUSTOM_NET_VALUE}"]`)?.remove();
  if (net.file) {
    netSelect.value = net.file;
    return;
  }
  const option = document.createElement("option");
  option.value = CUSTOM_NET_VALUE;
  option.textContent = net.label;
  netSelect.appendChild(option);
  netSelect.value = CUSTOM_NET_VALUE;
}

/** The Choose-a-net value that matches `net` (or "(none)" when there isn't one). */
function netSelectValueOf(net: NetIndexEntry | null): string {
  if (!net) return "";
  return net.file || CUSTOM_NET_VALUE;
}

async function loadModelFile(file: File) {
  setBusy(1);
  setLoading(netPanelEl, true);
  try {
    const spec = JSON.parse(await file.text()) as NetSpec;
    installNet(spec, { label: file.name.replace(/\.[^.]+$/, ""), file: "" });
  } catch (err) {
    console.error(err);
    setStatus(`Could not load ${file.name}: ${err instanceof Error ? err.message : String(err)}`, "error");
  } finally {
    setLoading(netPanelEl, false);
    setBusy(-1);
  }
}

async function loadSessionFile(file: File) {
  setBusy(1);
  try {
    restoreSession(parseSession(await file.text()), file.name);
  } catch (err) {
    console.error(err);
    setStatus(`Could not load ${file.name}: ${err instanceof Error ? err.message : String(err)}`, "error");
  } finally {
    setBusy(-1);
  }
}

function restoreSession(data: SessionData, fileName: string) {
  installNet(data.netSpec, { label: data.netName, file: "" });
  inflaterColors.mode = data.colorMode;
  inflaterColors.multiColors = [...data.multiColors];
  applyInflaterColors();
  targetInputs.forEach((input, i) => (input.value = `${data.targetRmsPct[i]}%`));
  toleranceInput.value = String(data.tolerance);
  readTolerance(toleranceInput);

  LEVELS.forEach((level) => {
    const snap = data.levels[level];
    store.history[level] = data.history[level] ?? null;
    if (!snap) return;
    const { topology, positions, frames } = restoreLevel(snap);
    store.topology[level] = topology;
    store.positions[level] = positions;
    showLevel(level, positions);
    if (frames.length) setReplayFrames(level, frames); // sessions saved without frames just skip this
  });
  renderHistory();

  camera.apply(data.camera);
  renderAll();
  setStatus(`Loaded session ${fileName}.`, "success");
  refreshMenus();
}

function sessionFileName(): string {
  const base = currentNet!.file ? currentNet!.file.replace(/\.[^.]+$/, "") : currentNet!.label;
  return `${base}${SESSION_EXTENSION}`;
}

/** The whole current session. Replay frames are always included -- they're small enough to keep. */
function buildSessionData(): SessionData {
  return {
    netName: sessionFileName().replace(SESSION_EXTENSION, ""),
    netSpec: currentSpec!,
    colorMode: inflaterColors.mode,
    multiColors: inflaterColors.multiColors,
    targetRmsPct: targetInputs.map((input) => readTargetRms(input)),
    tolerance: readTolerance(toleranceInput),
    camera: camera.snapshot(),
    history: [...store.history],
    levels: LEVELS.map((level) => {
      const topology = store.topology[level];
      const positions = store.positions[level];
      return topology && positions
        ? snapshotLevel(topology, positions, replays[level].frames)
        : null;
    }),
  };
}

/** Writes the session through the system save dialog, starting in Downloads with the default name.
 * Browsers without the File System Access API fall back to a plain download (no dialog). */
async function saveSession() {
  if (!currentSpec || !currentNet || running) return;
  const suggestedName = sessionFileName();
  const text = serializeSession(buildSessionData());
  try {
    const picker = (window as SaveWindow).showSaveFilePicker;
    if (picker) {
      const handle = await picker({
        suggestedName,
        startIn: "downloads",
        types: [{ description: "Inflate Polyhedron session", accept: { "application/json": [SESSION_EXTENSION] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(text);
      await writable.close();
      setStatus(`Saved session ${handle.name}.`, "success");
    } else {
      const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = suggestedName;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      setStatus(`Saved session ${suggestedName}.`, "success");
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return; // cancelled in the save dialog
    console.error(err);
    setStatus(`Could not save session: ${err instanceof Error ? err.message : String(err)}`, "error");
  }
}

/** File > Save / Ctrl+S: saves the file on screen in the Viewer, the Inflater session otherwise. */
function save() {
  if (view === "viewer") void viewer.saveCurrent();
  else void saveSession();
}

// ---- Views & the unsaved-changes prompt ----------------------------------------------------

type UnsavedChoice = "save" | "discard" | "cancel";

/** Asks what to do with the Viewer's unsaved files: Save (all of them), Don't Save, or Cancel. */
function askUnsaved(count: number): Promise<UnsavedChoice> {
  unsavedText.textContent = `Save changes to ${count} Viewer file(s) before leaving the Viewer?`;
  unsavedDialog.returnValue = "";
  return new Promise((resolve) => {
    unsavedDialog.addEventListener(
      "close",
      () => resolve((unsavedDialog.returnValue || "cancel") as UnsavedChoice),
      { once: true },
    );
    unsavedDialog.showModal();
  });
}

/** Switches view. Leaving the Viewer with unsaved files prompts first; Cancel keeps the Viewer open. */
async function setView(next: View): Promise<boolean> {
  if (next === view) return true;
  if (view === "viewer") {
    const dirty = viewer.dirtyNames();
    if (dirty.length) {
      const choice = await askUnsaved(dirty.length);
      if (choice === "cancel" || (choice === "save" && !(await viewer.saveAll()))) {
        refreshMenus();
        return false;
      }
    }
  }
  view = next;
  inflaterView.hidden = next !== "inflater";
  viewerView.hidden = next !== "viewer";
  refreshMenus();
  if (next === "viewer") await viewer.rescan();
  refreshMenus();
  return true;
}

/** File > Load: the Viewer has no net of its own, so loading switches back to the Inflater view first. */
async function thenInInflater(action: () => void) {
  if (await setView("inflater")) action();
}

// ---- Menus ---------------------------------------------------------------------------------

/** Brings every menu item's enabled/selected state in line with the current view and run state. */
function refreshMenus() {
  const colors = view === "viewer" ? viewer.colors() : inflaterColors;
  colorItems.forEach((item) => item.classList.toggle("selected", item.dataset.colorMode === colors?.mode));
  randomizeItem.disabled = colors?.mode !== "multi";
  viewItems.forEach((item) => item.classList.toggle("selected", item.dataset.view === view));

  const canUndo = view === "viewer" ? viewer.canUndo() : inflaterUndo.canUndo;
  const canRedo = view === "viewer" ? viewer.canRedo() : inflaterUndo.canRedo;
  undoItem.disabled = !canUndo;
  redoItem.disabled = !canRedo;

  // Run All is an Inflater-only job; the other file items are disabled while a run is using the net.
  runAllItem.disabled = running || view === "viewer";
  debugAllItem.hidden = !debugMode; // a debugging aid, like the Python app's Run > Debug All
  debugAllItem.disabled = running || view === "viewer";
  loadModelItem.disabled = running;
  loadSessionItem.disabled = running;
  saveSessionItem.textContent = view === "viewer" ? "Save" : "Save Session...";
  saveSessionItem.disabled = view === "viewer" ? !viewer.hasFile() : running || !currentSpec;

  document.title =
    view === "viewer"
      ? viewer.title()
      : debugMode
        ? "Static Inflater (debug mode)"
        : "Static Inflater";
  refreshViewerCounter();
}

// ---- Keyboard & startup --------------------------------------------------------------------

function isTypingTarget(e: KeyboardEvent) {
  return e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement;
}

function onInflateButton() {
  if (running) {
    stopRequested = true;
    batch?.wake?.(); // a Debug All run paused between nets wakes up to stop
  } else {
    void inflate();
  }
}

function onKeydown(e: KeyboardEvent) {
  if (isTypingTarget(e)) return; // typing in a field keeps its own undo, and P/M/R/D/arrows as text
  const key = e.key.toLowerCase();
  if (e.ctrlKey && !e.altKey && !e.metaKey) {
    if (key === "z") {
      e.preventDefault();
      undo();
    } else if (key === "y") {
      e.preventDefault();
      redo();
    } else if (key === "s") {
      e.preventDefault();
      save();
    }
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (key === "p") setColorMode("polygon");
  else if (key === "m") setColorMode("multi");
  else if (key === "r") randomize();
  else if (view === "viewer" && (key === "a" || e.key === "ArrowLeft")) void viewer.navigate(-1);
  else if (view === "viewer" && (key === "d" || e.key === "ArrowRight")) void viewer.navigate(1);
  else if (e.key === "ArrowLeft") onBatchKey(-1);
  else if (e.key === "ArrowRight") onBatchKey(1);
  else if (key === "d") setDebugMode(!debugMode);
}

async function init() {
  mountAppNav("static_inflater");
  renderHistory();
  inflateBtn.addEventListener("click", onInflateButton);
  colorItems.forEach((item) => item.addEventListener("click", () => setColorMode(item.dataset.colorMode as ColorMode)));
  randomizeItem.addEventListener("click", randomize);
  undoItem.addEventListener("click", undo);
  redoItem.addEventListener("click", redo);
  viewItems.forEach((item) => item.addEventListener("click", () => void setView(item.dataset.view as View)));
  runAllItem.addEventListener("click", () => void runBatch(true, false));
  debugAllItem.addEventListener("click", () => void runBatch(false, true));
  loadModelItem.addEventListener("click", () => void thenInInflater(() => modelFileInput.click()));
  loadSessionItem.addEventListener("click", () => void thenInInflater(() => sessionFileInput.click()));
  saveSessionItem.addEventListener("click", save);
  modelFileInput.addEventListener("change", () => {
    const file = modelFileInput.files?.[0];
    modelFileInput.value = ""; // so picking the same file again still fires "change"
    if (file) void loadModelFile(file);
  });
  sessionFileInput.addEventListener("change", () => {
    const file = sessionFileInput.files?.[0];
    sessionFileInput.value = "";
    if (file) void loadSessionFile(file);
  });
  // Close the menus after picking an item (their dropdown otherwise stays open while focused).
  document.querySelectorAll<HTMLButtonElement>(".menu-item").forEach((item) =>
    item.addEventListener("click", () => item.blur()),
  );
  window.addEventListener("keydown", onKeydown);
  window.addEventListener("beforeunload", (e) => {
    if (viewer.dirtyNames().length) e.preventDefault(); // the browser's own "leave page?" prompt
  });
  for (const box of [...Object.values(debugBoxes), ...Object.values(layerBoxes)]) {
    box.addEventListener("change", applyDebugOverlays);
  }
  // Set the layer checkboxes from their intended defaults, not whatever the browser restored on reload,
  // and push them to the viewers so the checkboxes always match what's drawn.
  layerBoxes.polygonOutlines.checked = true;
  layerBoxes.subdivisions.checked = false;
  applyDebugOverlays();
  applyInflaterColors();
  refreshMenus();

  setBusy(1);
  try {
    const nets = (await fetchJson<NetIndexEntry[]>("../inputs/index.json")).sort((a, b) =>
      a.label.localeCompare(b.label),
    );
    for (const net of nets) {
      const option = document.createElement("option");
      option.value = net.file;
      option.textContent = net.label;
      netSelect.appendChild(option);
    }
    netSelect.addEventListener("change", () => {
      const net = nets.find((n) => n.file === netSelect.value);
      if (running) {
        netSelect.value = netSelectValueOf(currentNet);
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
    revealPage();
  }
}

void init();
