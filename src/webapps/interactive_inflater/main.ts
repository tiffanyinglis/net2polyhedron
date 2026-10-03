import { mountAppNav, revealPage } from "../utils/appNav";
import { regularPolygonVertices } from "../utils/geometry";
import { Builder, POLYGON_NS, shapeCssColor } from "../net_builder/builder";
import { BuilderCanvas } from "../net_builder/canvas";
import { NetValidationError } from "../net_builder/netExport";
import { shapesFrom } from "../net_builder/netFile";
import { SharedCamera, Viewer, type DebugOverlays } from "../static_inflater/viewer";
import { displayColors, fitMultiColors, randomFaceColors, type ColorMode, type ColorState } from "../utils/colors";
import { DEFAULT_TARGET_RMS_PCT } from "../utils/physics/pipeline";
import { type NetSpec } from "../utils/physics/mesh";
import { type Vec3 } from "../utils/physics/vec3";
import {
  LEVELS,
  LevelStore,
  readTargetRmsPct,
  readTolerance,
  runFullInflate,
  wireParamInput,
  type RunOutcome,
  type StatusKind,
} from "../utils/inflaterRun";
import { activeGroup, flatPiece, netSpecFromBuilder, structureKey } from "./bridge";
import { type Shape } from "../net_builder/shapes";

mountAppNav("interactive_inflater");

/** Quiet time after the last net edit before the auto Full Inflate starts, so a drag runs once, not per pixel. */
const AUTO_INFLATE_DELAY_MS = 300;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvasEl = $<HTMLCanvasElement>("net-canvas");
const paletteEl = $("palette");
const builderStatusEl = $("builder-status");
const inflaterStatusEl = $("inflater-status");
const inflateBtn = $<HTMLButtonElement>("inflate-btn");
const toleranceInput = $<HTMLInputElement>("tolerance");
const undoItem = $<HTMLButtonElement>("undo-item");
const redoItem = $<HTMLButtonElement>("redo-item");
const loadItem = $<HTMLButtonElement>("load-item");
const randomizeItem = $<HTMLButtonElement>("randomize-item");
const colorItems = document.querySelectorAll<HTMLButtonElement>("[data-color-mode]");
const debugRow = $("debug-row");
const debugBoxes = {
  faceNormals: $<HTMLInputElement>("show-face-normals"),
  vertexNormals: $<HTMLInputElement>("show-vertex-normals"),
  repulsiveForces: $<HTMLInputElement>("show-repulsive-forces"),
};
const targetInputs = [1, 2, 3].map((level) => $<HTMLInputElement>(`target-${level}`));

const builder = new Builder();
// Combined Move/Join: no mode switch, the canvas picks join or move per press (as the Python builder's Edit mode).
builder.combined = true;
// A refused edit is a one-off: say why in a popup rather than in the status line.
const rejectDialog = $<HTMLDialogElement>("reject-dialog");
builder.onRejected = (message) => {
  $("reject-message").textContent = message;
  rejectDialog.showModal();
};
$("reject-ok").addEventListener("click", () => rejectDialog.close());
const canvas = new BuilderCanvas(canvasEl, builder, () => refresh(), true);

/** The one canvas on the right: the finest level computed so far. */
const camera = new SharedCamera();
const viewer = new Viewer($("viewer"), camera, () => viewer.render());

/** Polygon-specific colouring, the default in the Python app. */
const colors: ColorState = { mode: "polygon", multiColors: [] };
const store = new LevelStore();

let running = false;
let stopRequested = false;
/** A net edit arrived while a run was going: run again on the new net once this one stops. */
let rerunPending = false;
let debugMode = false;
/** Spec of the result on screen (null when nothing is shown). */
let resultSpec: NetSpec | null = null;
/** Key of the net last seen by refresh(); a change schedules an auto Full Inflate. */
let seenKey: string | null = null;
let autoTimer: number | null = null;

// ---- status and controls ------------------------------------------------------------------------

function setInflaterStatus(text: string, kind: StatusKind = "info") {
  inflaterStatusEl.textContent = text;
  inflaterStatusEl.className = `status ${kind}`;
}

function hintText(): string {
  if (running) return "The net is locked while it inflates.";
  if (builder.armedN !== null) return "Click the drawing area to place the shape.";
  return "Drag shapes to move them. Click an edge handle, then another, to join them.";
}

/** The owner's connected group: the only pieces that are inflated (the Python app's "active group"). */
function activeNet() {
  return activeGroup(builder.shapes, builder.connections, builder.ownerShapeId());
}

/** The active group's structure (see structureKey); null if there is no group or it isn't a valid mesh. */
function currentKey(): string | null {
  const active = activeNet();
  if (active.shapes.length === 0) return null;
  return structureKey(active.shapes, active.connections);
}

/** Keeps menus, palette, the Reinflate button and the builder hint in line with the builder. */
function refresh() {
  const key = currentKey();
  if (key !== seenKey) {
    seenKey = key;
    netChanged(key);
  }
  const editable = !running;
  undoItem.disabled = !editable || !builder.canUndo;
  redoItem.disabled = !editable || !builder.canRedo;
  loadItem.disabled = !editable;
  canvasEl.style.pointerEvents = editable ? "" : "none";
  for (const button of paletteEl.querySelectorAll<HTMLButtonElement>("button")) {
    button.disabled = !editable;
    button.classList.toggle("armed", Number(button.dataset.n) === builder.armedN);
  }
  inflateBtn.disabled = !running && activeNet().shapes.length === 0;
  builderStatusEl.textContent = hintText();
  builderStatusEl.style.color = "var(--info)";
  refreshColorMenu();
  canvas.redraw();
}

/**
 * The net changed. A valid net schedules a Full Inflate (Python's Auto Inflate). An empty or
 * invalid net drops the picture, since there is nothing to inflate.
 */
function netChanged(key: string | null) {
  cancelAutoInflate();
  if (key === null) {
    if (running) {
      stopRequested = true;
      rerunPending = false;
    }
    clearResults();
    // A lone piece has nothing to inflate yet, and that needs no message.
    setInflaterStatus(activeNet().shapes.length < 2 ? "" : "The net is not a valid mesh yet.", "info");
    return;
  }
  scheduleAutoInflate();
}

function scheduleAutoInflate() {
  cancelAutoInflate();
  autoTimer = window.setTimeout(() => {
    autoTimer = null;
    if (running) {
      // Stop the run in progress; it reruns on the new net when it stops.
      stopRequested = true;
      rerunPending = true;
    } else {
      void inflate();
    }
  }, AUTO_INFLATE_DELAY_MS);
}

function cancelAutoInflate() {
  if (autoTimer !== null) window.clearTimeout(autoTimer);
  autoTimer = null;
}

function setRunning(on: boolean) {
  running = on;
  inflateBtn.textContent = on ? "Stop" : "Reinflate";
  refresh();
}

// ---- palette ------------------------------------------------------------------------------------

/** Palette icons share one circumradius whatever their side count, so the row reads as evenly sized. */
const ICON_SIZE = 42;
const ICON_RADIUS = 16;

function drawIcon(n: number): HTMLCanvasElement {
  const icon = document.createElement("canvas");
  icon.width = ICON_SIZE * devicePixelRatio;
  icon.height = ICON_SIZE * devicePixelRatio;
  icon.style.width = `${ICON_SIZE}px`;
  icon.style.height = `${ICON_SIZE}px`;
  const ctx = icon.getContext("2d")!;
  ctx.scale(devicePixelRatio, devicePixelRatio);
  const edge = 2 * ICON_RADIUS * Math.sin(Math.PI / n);
  // Centre the icon on its bounding box, not its circumcentre: a triangle's visual middle is below its circumcentre.
  const verts = regularPolygonVertices(n, edge);
  const xs = verts.map(([x]) => x);
  const ys = verts.map(([, y]) => y);
  const offsetX = -(Math.min(...xs) + Math.max(...xs)) / 2;
  const offsetY = -(Math.min(...ys) + Math.max(...ys)) / 2;
  ctx.beginPath();
  verts.forEach(([x, y], i) => {
    const px = ICON_SIZE / 2 + x + offsetX;
    const py = ICON_SIZE / 2 + y + offsetY;
    if (i) ctx.lineTo(px, py);
    else ctx.moveTo(px, py);
  });
  ctx.closePath();
  ctx.fillStyle = shapeCssColor(n);
  ctx.fill();
  return icon;
}

for (const n of POLYGON_NS) {
  const button = document.createElement("button");
  button.dataset.n = String(n);
  button.title = `${n}-gon`;
  button.append(drawIcon(n));
  button.addEventListener("click", () => {
    builder.toggleArmed(n);
    refresh();
  });
  paletteEl.append(button);
}

// ---- Edit, File and Colour menus ----------------------------------------------------------------

undoItem.addEventListener("click", () => {
  builder.undoStep();
  refresh();
});
redoItem.addEventListener("click", () => {
  builder.redoStep();
  refresh();
});

const netFileInput = $<HTMLInputElement>("net-file");
loadItem.addEventListener("click", () => netFileInput.click());
netFileInput.addEventListener("change", async () => {
  const file = netFileInput.files?.[0];
  netFileInput.value = "";
  if (!file) return;
  try {
    const { shapes, connections } = shapesFrom(JSON.parse(await file.text()));
    builder.loadShapes(shapes, connections);
    // A load always inflates, even when the active group is unchanged (as the Python app does).
    seenKey = null;
    setInflaterStatus(`Loaded ${file.name}.`);
  } catch (err) {
    setInflaterStatus(`Could not load ${file.name}: ${err instanceof Error ? err.message : String(err)}`, "error");
  }
  refresh();
});

/** Colour > Polygon-specific / Multi-colour (and P / M). Recolours the shown result. */
function setColorMode(mode: ColorMode) {
  colors.mode = mode;
  applyColors();
  refreshColorMenu();
}

/** Colour > Randomize (and R): re-rolls the Multi-colour palette. */
function randomize() {
  if (colors.mode !== "multi" || !resultSpec) return;
  colors.multiColors = randomFaceColors(resultSpec.faces);
  applyColors();
}

function refreshColorMenu() {
  for (const item of colorItems) item.classList.toggle("selected", item.dataset.colorMode === colors.mode);
  randomizeItem.disabled = colors.mode !== "multi" || !resultSpec || running;
}

colorItems.forEach((item) => item.addEventListener("click", () => setColorMode(item.dataset.colorMode as ColorMode)));
randomizeItem.addEventListener("click", randomize);

window.addEventListener("keydown", (e) => {
  // While the refusal popup is up, keys belong to it, not to the builder.
  if (rejectDialog.open) return;
  // Typing in the Setup fields must not delete shapes or switch colours.
  if (e.target instanceof HTMLInputElement) return;
  const key = e.key.toLowerCase();
  if (e.ctrlKey || e.metaKey) {
    if (running) return;
    if (key === "z") {
      builder.undoStep();
      refresh();
    } else if (key === "y") {
      builder.redoStep();
      refresh();
    }
    return;
  }
  if (e.altKey) return;
  if (key === "d") {
    setDebugMode(!debugMode);
  } else if (key === "p") {
    setColorMode("polygon");
  } else if (key === "m") {
    setColorMode("multi");
  } else if (key === "r") {
    randomize();
  } else if (key === "delete" || key === "backspace") {
    if (running) return;
    builder.deleteSelected();
    refresh();
  }
});

// ---- Debug mode ---------------------------------------------------------------------------------

/** Debug mode (D): the builder's owner anchor glyph, plus the Setup fields and overlays. Titles say so, as in the Python app. */
function setDebugMode(on: boolean) {
  debugMode = on;
  canvas.debug = on;
  document.title = on ? "Interactive Inflater (debug mode)" : "Interactive Inflater";
  debugRow.hidden = !on;
  // Leaving debug mode clears the overlays, as in the Static Inflater.
  for (const box of Object.values(debugBoxes)) box.checked = false;
  applyOverlays();
  canvas.redraw();
}

function applyOverlays() {
  const flags: DebugOverlays = debugMode
    ? {
        faceNormals: debugBoxes.faceNormals.checked,
        vertexNormals: debugBoxes.vertexNormals.checked,
        repulsiveForces: debugBoxes.repulsiveForces.checked,
      }
    : { faceNormals: false, vertexNormals: false, repulsiveForces: false };
  viewer.setOverlays(flags);
}

for (const box of Object.values(debugBoxes)) box.addEventListener("change", applyOverlays);

// ---- Setup fields -------------------------------------------------------------------------------

for (const input of targetInputs) {
  wireParamInput(
    input,
    () => readTargetRmsPct(input, DEFAULT_TARGET_RMS_PCT),
    () => (input.value = String(parseFloat(input.value))),
  );
}
wireParamInput(toleranceInput, () => readTolerance(toleranceInput));

// ---- Drawing the result -------------------------------------------------------------------------

/** Draws one level's mesh. Uses the run's own spec, so it is right before the run is accepted. */
function drawLevel(level: number, positions: Map<number, Vec3>, spec: NetSpec) {
  const topo = store.topology[level];
  if (!topo) return;
  fitMultiColors(colors, spec.faces);
  const faceColors = displayColors(colors, spec.faces, spec);
  viewer.setMesh(topo.faces, topo.faceEdgeIds, positions, topo.faceOfFine, faceColors, topo.outlineEdgeIds);
  viewer.render();
}

/** Recolours the shown result in place, so a colour change keeps the camera where it is. */
function applyColors() {
  if (running || !resultSpec) return;
  fitMultiColors(colors, resultSpec.faces);
  viewer.setBaseColors(displayColors(colors, resultSpec.faces, resultSpec));
  viewer.render();
  refreshColorMenu();
}

/** Shows the finest level still in the store, or clears the viewer if there is none. */
function redrawFinest() {
  for (const level of [...LEVELS].reverse()) {
    const positions = store.positions[level];
    if (positions && resultSpec) {
      drawLevel(level, positions, resultSpec);
      return;
    }
  }
  viewer.clear();
}

/** A lone piece has nothing to solve: it is drawn flat at once, with no Full Inflate. */
function showFlatPiece(shape: Shape) {
  const flat = flatPiece(shape);
  store.clear();
  store.topology[0] = flat.topology;
  store.positions[0] = flat.positions;
  resultSpec = flat.spec;
  drawLevel(0, flat.positions, flat.spec);
  refreshColorMenu();
  setInflaterStatus("");
}

function clearResults() {
  store.clear();
  resultSpec = null;
  viewer.clear();
  refreshColorMenu();
}

// ---- Full Inflate -------------------------------------------------------------------------------

/**
 * One Full Inflate of the builder's net. Each level is drawn as it finishes, so the finest one
 * on screen is always the newest. Stop, or any failure, puts back the previous result (Python's
 * MeshSnapshotManager). An edit made during the run is picked up when the run stops.
 */
async function inflate() {
  const active = activeNet();
  if (active.shapes.length === 0) return;
  if (active.shapes.length === 1) {
    showFlatPiece(active.shapes[0]);
    return;
  }
  let spec: NetSpec;
  try {
    spec = netSpecFromBuilder(active.shapes, active.connections, "net");
  } catch (err) {
    const message = err instanceof NetValidationError ? err.message : String(err);
    setInflaterStatus(`The net is not a valid mesh yet: ${message}`, "error");
    return;
  }
  const runKey = structureKey(active.shapes, active.connections);

  const targetRmsPctByLevel = Object.fromEntries(
    targetInputs.map((input, i) => [i + 1, readTargetRmsPct(input, DEFAULT_TARGET_RMS_PCT)]),
  );
  const gtol = readTolerance(toleranceInput);

  const before = store.snapshot();
  const beforeSpec = resultSpec;
  stopRequested = false;
  rerunPending = false;
  setRunning(true);
  let outcome: RunOutcome = "error";
  try {
    outcome = await runFullInflate(spec, {
      label: "Full Inflate",
      targetRmsPctByLevel,
      gtol,
      store,
      shouldStop: () => stopRequested,
      hooks: {
        status: setInflaterStatus,
        loading: () => {},
        showLevel: (level, positions) => drawLevel(level, positions, spec),
        historyChanged: () => {},
      },
    });
  } finally {
    setRunning(false);
  }
  if (outcome === "done") {
    resultSpec = spec;
    refreshColorMenu();
  } else {
    store.restore(before);
    resultSpec = beforeSpec;
    redrawFinest();
  }
  // An edit that landed during the run, or a rerun the run asked for, goes next.
  const current = currentKey();
  if (rerunPending || (current !== null && current !== runKey)) {
    scheduleAutoInflate();
  }
}

inflateBtn.addEventListener("click", () => {
  if (running) {
    // A user Stop ends this run and does not restart it for the same net.
    stopRequested = true;
    rerunPending = false;
    setInflaterStatus("Stopping after the current step...", "warn");
  } else {
    cancelAutoInflate();
    void inflate();
  }
});

setDebugMode(false);
refresh();
revealPage();
