import { mountAppNav, revealPage } from "../utils/appNav";
import { regularPolygonVertices } from "../utils/geometry";
import { Builder, POLYGON_NS, shapeCssColor } from "../net_builder/builder";
import { BuilderCanvas } from "../net_builder/canvas";
import { NetValidationError } from "../net_builder/netExport";
import { defaultNetColors, netFileFrom, shapesFrom, type NetColors } from "../net_builder/netFile";
import { parseSession, restoreLevel, serializeSession, snapshotLevel, SESSION_EXTENSION, type SessionData } from "../utils/session";
import { OPEN_EDGE_COLOR, SharedCamera, Viewer, type DebugOverlays } from "../static_inflater/viewer";
import { displayColors, polygonColor, type ColorMode, type ColorState } from "../utils/colors";
import { fillMissingColours, nextPiece, neighboursOf, randomize as randomizeShapes } from "../net_builder/colours";
import { hexAtlasImage, hexAtlasLoaded } from "../static_inflater/hexAtlas";
import { drawAtlasTriangle } from "../utils/atlasDraw";
import { atomCornerUV, cellUV, retargetFaceUV, type AtlasChoice } from "../utils/physics/meshLevels";
import { type ReplayFrame } from "../utils/physics/relaxOnce";
import { defaultTargetRmsPct, repulsionMultipliers } from "../utils/physics/pipeline";
import { loadNet } from "../utils/physics/mesh";
import { type NetSpec } from "../utils/physics/mesh";
import { type Vec3 } from "../utils/physics/vec3";
import {
  LEVELS,
  LevelStore,
  runFullInflate,
  type RunOutcome,
  type StatusKind,
} from "../utils/inflaterRun";
import { activeGroup, structureKey } from "./bridge";
import { buildDisplay, edgePath, junctionKey, NO_SOLVE_TOPOLOGY, planPlacement, type Display, type Placement } from "./placement";
import { edgeGroup } from "../net_builder/joins";
import { countConnectionCrossings } from "../net_builder/crossings";
import { rigidTransformFrom } from "../utils/physics/kabsch";
import { CONVERGENCE_GTOL } from "../utils/physics/convergence";
import { surfaceTriangles } from "./diffInflate";
import { canDiff, diffInflate, type LastSolve } from "./diffInflate";

mountAppNav("interactive_inflater");

/** Highlights: the piece under the pointer (yellow, as in the Python app) and the selected pieces (red). */
const HOVER_HIGHLIGHT = 0xffd400;
const SELECT_HIGHLIGHT = 0xe53935;
/** A press that moves less than this (CSS px) on the 3D view is a click that selects, not an orbit. */
const CLICK_SLOP_PX = 4;
/** How close (CSS px) the pointer must be to an edge in 3D to pick it. Edges are checked before faces. */
const EDGE_PICK_PX = 8;

/** Quiet time after the last net edit before the auto Full Inflate starts, so a drag runs once, not per pixel. */
const AUTO_INFLATE_DELAY_MS = 300;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvasEl = $<HTMLCanvasElement>("net-canvas");
const paletteEl = $("palette-shapes");
const untangleBtn = $<HTMLButtonElement>("untangle-btn");
const slowUntangleBtn = $<HTMLButtonElement>("slow-untangle-btn");
const builderHintEl = $("builder-hint");
const crossingCountEl = $("crossing-count");
const inflaterStatusEl = $("inflater-status");
const inflateBtn = $<HTMLButtonElement>("inflate-btn");
const undoBtn = $<HTMLButtonElement>("undo-btn");
const redoBtn = $<HTMLButtonElement>("redo-btn");
/** The Re-inflate button's icon, and its Stop icon while a run is going (its name is hover text only). */
const REFRESH_ICON_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/></svg>';
const STOP_ICON_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="1.5"/></svg>';
const navRow = $("nav-row");
const undoItem = $<HTMLButtonElement>("undo-item");
const redoItem = $<HTMLButtonElement>("redo-item");
const loadItem = $<HTMLButtonElement>("load-item");
const randomizeItem = $<HTMLButtonElement>("randomize-item");
const colorItems = document.querySelectorAll<HTMLButtonElement>("[data-color-mode]");
const debugRow = $("debug-row");
const replaySlider = $<HTMLInputElement>("replay-slider");
const debugBoxes = {
  faceNormals: $<HTMLInputElement>("show-face-normals"),
  vertexNormals: $<HTMLInputElement>("show-vertex-normals"),
  repulsiveForces: $<HTMLInputElement>("show-repulsive-forces"),
};
const smoothBox = $<HTMLInputElement>("smooth-shading");

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
canvas.onHoverPiece = () => syncHighlights();

/** The one canvas on the right: the finest level computed so far. */
const camera = new SharedCamera();
const viewer = new Viewer($("viewer"), camera, () => viewer.render());

/** The Colour menu's state: the mode, and each piece's Multi-colour and African Flower texture by shape id. Polygon-specific by default, as in the Python app. */
const colors: NetColors = defaultNetColors();
const store = new LevelStore();

let running = false;
let stopRequested = false;
/** A Slow untangle animation is revealing pieces one at a time; the net is locked while it runs. */
let slowUntangling = false;
/** A net edit arrived while a run was going: run again on the new net once this one stops. */
let rerunPending = false;
let debugMode = false;
/** Spec of the result on screen (null when nothing is shown). */
let resultSpec: NetSpec | null = null;
/** The placement (junctions solved, terminals flat) behind the result on screen. */
let resultPlan: Placement | null = null;
/**
 * Python's is_fully_inflated: false at start, true once a solve completes, false when the canvas
 * empties or the net has no junctions to solve. A junction change runs a Full Inflate while it's
 * false and a Diff Inflate once it's true (not yet ported, so both run the Full solve for now).
 */
let fullyInflated = false;
/** The junction structure the shown result (or the solve in progress) is for. */
let junctionTarget: string | null = null;
/** The last finished solve's slots, Level-3 positions and pressure: what the next Diff Inflate starts from. */
let lastSolve: LastSolve | null = null;
/** Key of the net last seen by refresh(); a change schedules an auto Full Inflate. */
let seenKey: string | null = null;
let autoTimer: number | null = null;
/** An edit that needs a new inflate is waiting to start: a spinner shows over the 3D view until it does. */
let inflatePending = false;
/** The red selection: faces (base-face indices of the shown mesh), edge paths, the selected shapes, and every
 * edge path of the selected pieces (world positions, so they stay put when the mesh is redrawn). */
interface RedSelection {
  faces: Set<number>;
  edges: Vec3[][];
  shapes: Set<number>;
  pieces: Vec3[][];
}
/** The red selection as it was last drawn with something selected. Kept while an inflate is pending or running, so a
 * deleted selection stays red until the new result replaces the old one. */
let lastRed: RedSelection | null = null;
/** The display on screen (its piece corners and positions), for picking edges. */
let shownDisplay: Display | null = null;
/** The full net's source piece per face, for the display on screen. */
let shownSource: number[] | null = null;
/** Each edge's real path on the display on screen, by "piece:edge". Filled on demand. */
let shownPaths = new Map<string, Vec3[]>();

/** The replay frames of the result on screen (debug mode's slider), and the level they belong to. */
let replayFrames: ReplayFrame[] = [];
let replayLevel = 3;

// ---- status and controls ------------------------------------------------------------------------

function setInflaterStatus(text: string, kind: StatusKind = "info") {
  inflaterStatusEl.textContent = text;
  inflaterStatusEl.className = `status ${kind}`;
}

/** Live count of where the net's join curves cross each other, always shown under the 2D view. Counted
 * over only what's currently drawn (see Builder.isRevealed) -- mid Slow untangle, a piece not yet placed
 * is still sitting at its old position, and counting it in would show crossings for joins no one can see. */
function updateCrossingCount() {
  const shapes = builder.shapes.filter((s) => builder.isRevealed(s.id));
  const connections = builder.connections.filter((c) => builder.isRevealed(c.aShape) && builder.isRevealed(c.bShape));
  const n = countConnectionCrossings(shapes, connections);
  crossingCountEl.textContent = n === 1 ? "1 crossing" : `${n} crossings`;
  crossingCountEl.className = n === 0 ? "zero" : "nonzero";
}

function hintText(): string {
  if (running) return "The net is locked while it inflates.";
  if (slowUntangleStep) return "Press Space to place the next piece.";
  if (builder.armedN !== null) return "Click the drawing area to place the shape.";
  return "Drag shapes to move them. Drag from an edge handle to another, then release, to join them.";
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
  ensureColors();
  updatePalette();
  const key = currentKey();
  if (key !== seenKey) {
    seenKey = key;
    netChanged(key);
  }
  const editable = !running && !slowUntangling;
  undoItem.disabled = undoBtn.disabled = !editable || !builder.canUndo;
  redoItem.disabled = redoBtn.disabled = !editable || !builder.canRedo;
  loadItem.disabled = !editable;
  newItem.disabled = !editable;
  load3dItem.disabled = !editable;
  save3dItem.disabled = !editable || builder.shapes.length === 0;
  // The 2D canvas stays interactive even when locked: panning and zooming are still allowed (see
  // BuilderCanvas.locked), only edit gestures are refused.
  canvas.locked = !editable;
  for (const button of paletteEl.querySelectorAll<HTMLButtonElement>("button")) {
    button.disabled = !editable;
    button.classList.toggle("armed", Number(button.dataset.n) === builder.armedN);
  }
  inflateBtn.disabled = !running && activeNet().shapes.length === 0;
  untangleBtn.disabled = slowUntangleBtn.disabled = !editable || builder.shapes.length < 2;
  builderHintEl.textContent = hintText();
  builderHintEl.style.color = "var(--info)";
  updateCrossingCount();
  if (builder.selected.size) canvas.selectedEdge = null;
  refreshColorMenu();
  canvas.redraw();
  syncHighlights();
}

/**
 * The net changed. An empty or invalid net drops the picture. A valid net either changes only its
 * terminals (re-placed flat, no solve), changes its junctions (a solve, see inflate), or has no
 * junctions to solve (the seed is laid flat).
 */
function netChanged(key: string | null) {
  cancelAutoInflate();
  // A queued solve that never started is dropped; whatever this change needs is decided again below.
  if (!running) inflatePending = false;
  if (key === null) {
    if (running) {
      stopRequested = true;
      rerunPending = false;
    }
    // An emptied canvas forgets its solve (Python's rule); an invalid net just clears the picture.
    if (activeNet().shapes.length === 0) fullyInflated = false;
    clearResults();
    // A lone piece has nothing to inflate yet, and that needs no message.
    setInflaterStatus(activeNet().shapes.length < 2 ? "" : "The net is not a valid mesh yet.", "info");
    return;
  }
  const plan = tryPlan();
  if (!plan) return;
  if (plan.solve === null) {
    showNoSolve(plan);
    return;
  }
  if (junctionKey(plan) === junctionTarget && store.topology.some((t) => t !== null)) {
    // Only terminals changed: the junctions' solve still stands, so just re-place the flat pieces.
    showPlan(plan);
    return;
  }
  scheduleAutoInflate();
}

/** The active group's placement, or null after reporting why it isn't a valid mesh. */
function tryPlan(): Placement | null {
  const active = activeNet();
  try {
    return planPlacement(active.shapes, active.connections, builder.ownerShapeId(), colors.african);
  } catch (err) {
    const message = err instanceof NetValidationError ? err.message : String(err);
    setInflaterStatus(`The net is not a valid mesh yet: ${message}`, "error");
    return null;
  }
}

/**
 * The Level target fields take the net's default target RMS stretch (5% for an open net, 10% for a
 * closed one, as the Python app and the Static Inflater do). They're reset when the open/closed status
 * changes or a file is loaded, so a value typed in between is kept.
 */
function defaultTargetFor(full: NetSpec): number {
  return defaultTargetRmsPct(loadNet(full));
}

/** Shows a placement over the stored solve, without running anything. */
function showPlan(plan: Placement) {
  resultPlan = plan;
  resultSpec = plan.full;
  redrawFinest();
  refreshColorMenu();
}

/** No junctions to solve: the seed is laid flat (Python's place mode), and the flag is cleared. */
function showNoSolve(plan: Placement) {
  fullyInflated = false;
  inflatePending = false;
  junctionTarget = null;
  store.clear();
  store.topology[0] = NO_SOLVE_TOPOLOGY;
  store.positions[0] = plan.seedPositions;
  showPlan(plan);
  setInflaterStatus("");
}

function scheduleAutoInflate() {
  cancelAutoInflate();
  inflatePending = true;
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
  inflateBtn.innerHTML = on ? STOP_ICON_SVG : REFRESH_ICON_SVG;
  inflateBtn.title = on ? "Stop" : "Re-inflate (full inflate)";
  updateReplayControl();
  refresh();
}

// ---- palette ------------------------------------------------------------------------------------

/** Palette icons share one circumradius whatever their side count, so the row reads as evenly sized. */
const ICON_SIZE = 54;
const ICON_RADIUS = 20;

/** The deck's icons, each repainted as the piece the deck would pull now (see paintIcon). */
const icons: { n: number; canvas: HTMLCanvasElement }[] = [];

/** Paints one deck icon for `n` sides, as the next piece would look in the current colour mode. */
function paintIcon(icon: HTMLCanvasElement, n: number) {
  const ctx = icon.getContext("2d")!;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, icon.width, icon.height);
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  const edge = 2 * ICON_RADIUS * Math.sin(Math.PI / n);
  // Centre the icon on its bounding box, not its circumcentre: a triangle's visual middle is below its circumcentre.
  const verts = regularPolygonVertices(n, edge);
  const xs = verts.map(([x]) => x);
  const ys = verts.map(([, y]) => y);
  const offsetX = -(Math.min(...xs) + Math.max(...xs)) / 2;
  const offsetY = -(Math.min(...ys) + Math.max(...ys)) / 2;
  const points = verts.map(([x, y]) => [ICON_SIZE / 2 + x + offsetX, ICON_SIZE / 2 + y + offsetY] as [number, number]);
  const piece = pending;
  const atlas = hexAtlasImage();
  if (colors.mode === "african" && atlas) {
    drawAfrican(ctx, atlas, piece.african, points);
  } else {
    ctx.beginPath();
    points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.fillStyle = colors.mode === "multi" ? cssColour(piece.multi) : shapeCssColor(n);
    ctx.fill();
  }
  if (colors.mode === "african" || colors.mode === "multi") {
    // A white outline keeps the textured icons, and the Multi-colour ones, readable against the palette.
    ctx.beginPath();
    points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 1.25;
    ctx.lineJoin = "round";
    ctx.stroke();
  }
}

function updatePalette() {
  for (const { n, canvas: icon } of icons) paintIcon(icon, n);
}

for (const n of POLYGON_NS) {
  const button = document.createElement("button");
  button.dataset.n = String(n);
  button.title = `${n}-gon`;
  const icon = document.createElement("canvas");
  icon.width = ICON_SIZE * devicePixelRatio;
  icon.height = ICON_SIZE * devicePixelRatio;
  icons.push({ n, canvas: icon });
  button.append(icon);
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
untangleBtn.addEventListener("click", () => {
  builder.untangle();
  refresh();
});

/** A Slow untangle in progress: the order it's revealing, and how many pieces are down so far. */
let slowUntangleStep: { order: number[]; placed: number } | null = null;

slowUntangleBtn.addEventListener("click", () => {
  const order = builder.beginSlowUntangle();
  if (!order) return;
  slowUntangling = true;
  builder.applyUntangleStep(0);
  if (order.length > 1) {
    slowUntangleStep = { order, placed: 1 };
  } else {
    builder.finishSlowUntangle();
    slowUntangling = false;
  }
  refresh();
});

/** Space, mid Slow untangle: places the next piece, or finishes up (the crossing-minimising bow-out,
 * see Builder.finishSlowUntangle) once the last one is down. */
function advanceSlowUntangle() {
  if (!slowUntangleStep) return;
  builder.applyUntangleStep(slowUntangleStep.placed);
  slowUntangleStep.placed++;
  if (slowUntangleStep.placed >= slowUntangleStep.order.length) {
    builder.finishSlowUntangle();
    slowUntangleStep = null;
    slowUntangling = false;
  }
  refresh();
}

const netFileInput = $<HTMLInputElement>("net-file");
loadItem.addEventListener("click", () => netFileInput.click());
netFileInput.addEventListener("change", async () => {
  const file = netFileInput.files?.[0];
  netFileInput.value = "";
  if (!file) return;
  try {
    const { shapes, connections, colors: fileColors } = shapesFrom(JSON.parse(await file.text()));
    builder.loadShapes(shapes, connections);
    // The file's own colours (its Colour menu state), or the defaults for a file saved without them.
    const saved = fileColors ?? defaultNetColors();
    colors.mode = saved.mode;
    colors.multi = saved.multi;
    colors.african = saved.african;
    // A load always runs a Full Inflate (Python's on_load_success): a new net has nothing to diff against.
    fullyInflated = false;
    // A load always inflates, even when the active group is unchanged (as the Python app does).
    seenKey = null;
    setInflaterStatus(`Loaded ${file.name}.`);
  } catch (err) {
    setInflaterStatus(`Could not load ${file.name}: ${err instanceof Error ? err.message : String(err)}`, "error");
  }
  refresh();
});

/** The piece the deck pulls next: the least used colour and texture among the pieces on the canvas. Kept until those change, so the deck doesn't reshuffle. */
let pending = nextPiece([], colors);
let pendingKey = "";
/** The held piece (drawn as a ghost with id -1) is coloured as the next pull, not as a placed shape. */
const GHOST_ID = -1;

/** Gives every piece without a colour or texture the deck's next piece, and drops the colours of pieces that are gone. */
function ensureColors() {
  const ids = builder.shapes.map((shape) => shape.id);
  const live = new Set(ids);
  const maps: Record<number, unknown>[] = [colors.multi, colors.african];
  for (const map of maps) for (const key of Object.keys(map)) if (!live.has(Number(key))) delete map[Number(key)];
  // A newly placed piece takes the piece the deck was showing, so the one pulled is the one placed.
  const unpainted = ids.filter((id) => colors.multi[id] === undefined || colors.african[id] === undefined);
  if (unpainted.length === 1) {
    colors.multi[unpainted[0]] ??= pending.multi;
    colors.african[unpainted[0]] ??= pending.african;
  }
  fillMissingColours(ids, colors);
  const key = ids.map((id) => `${id}:${colors.multi[id]}:${colors.african[id]?.cell}`).join(",");
  if (key !== pendingKey) {
    pending = nextPiece(ids, colors);
    pendingKey = key;
  }
}

const cssColour = (value: number) => `#${value.toString(16).padStart(6, "0")}`;

// The 2D pieces use the Colour menu too: the polygon colour, each piece's own Multi-colour, or its African Flower texture.
canvas.fillOf = (shape) => {
  const multi = shape.id === GHOST_ID ? pending.multi : colors.multi[shape.id];
  return colors.mode === "multi" && multi !== undefined ? cssColour(multi) : cssColour(polygonColor(shape.n));
};
canvas.fillTexture = (shape, verts, ctx) => {
  const atlas = hexAtlasImage();
  const choice = shape.id === GHOST_ID ? pending.african : colors.african[shape.id];
  if (colors.mode !== "african" || !atlas || !choice) return false;
  drawAfrican(ctx, atlas, choice, verts);
  return true;
};

/** Paints a polygon's African Flower texture: one hexagon wedge per side, starting at atom `choice.start`, meeting at the centre. */
function drawAfrican(ctx: CanvasRenderingContext2D, atlas: HTMLImageElement | HTMLCanvasElement, choice: AtlasChoice[number], points: [number, number][]) {
  const n = points.length;
  const centre: [number, number] = [
    points.reduce((sum, [x]) => sum + x, 0) / n,
    points.reduce((sum, [, y]) => sum + y, 0) / n,
  ];
  points.forEach((p, k) => {
    const m = choice.start + k;
    const uv = [...atomCornerUV(choice.cell, m), ...atomCornerUV(choice.cell, m + 1), ...cellUV(choice.cell, 0.5, 0.5)];
    drawAtlasTriangle(ctx, atlas, uv, [p, points[(k + 1) % n], centre], devicePixelRatio);
  });
}

/** Colour > Polygon-specific / Multi-colour / African Flower (and P / M / A). Recolours the 2D pieces and the shown result. */
function setColorMode(mode: ColorMode) {
  colors.mode = mode;
  colourEdited = true;
  refresh();
  applyColors();
}

/** Colour > Randomize (and R): a fresh Multi-colour or African Flower texture for every piece, spread out and clear of its neighbours. */
function randomize() {
  if (colors.mode === "polygon" || running) return;
  colourEdited = true;
  randomizeShapes(builder.shapes.map((shape) => shape.id), neighboursOf(builder.connections), colors, colors.mode);
  refresh();
  applyColors();
}

function refreshColorMenu() {
  for (const item of colorItems) item.classList.toggle("selected", item.dataset.colorMode === colors.mode);
  randomizeItem.disabled = colors.mode === "polygon" || running;
}

colorItems.forEach((item) => item.addEventListener("click", () => setColorMode(item.dataset.colorMode as ColorMode)));
randomizeItem.addEventListener("click", randomize);

window.addEventListener("keydown", (e) => {
  // While the refusal popup is up, keys belong to it, not to the builder.
  if (rejectDialog.open) return;
  // Typing in the Setup fields must not delete shapes or switch colours.
  if (e.target instanceof HTMLInputElement) return;
  if (e.key === " " && slowUntangleStep) {
    e.preventDefault(); // space otherwise scrolls the page, or re-clicks a focused button
    advanceSlowUntangle();
    return;
  }
  const key = e.key.toLowerCase();
  if (e.ctrlKey || e.metaKey) {
    if (running || slowUntangling) return;
    if (key === "z") {
      builder.undoStep();
      refresh();
    } else if (key === "y") {
      builder.redoStep();
      refresh();
    } else if (key === "c") {
      // Only one piece at a time: a copy needs exactly one selected piece.
      if (builder.selected.size === 1) builder.copy();
    } else if (key === "v") {
      builder.paste();
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
  } else if (key === "a") {
    setColorMode("african");
  } else if (key === "r") {
    randomize();
  } else if (key === "delete" || key === "backspace") {
    if (running || slowUntangling) return;
    builder.deleteSelected();
    refresh();
  }
});

// ---- Hover and selection, synced between the 2D and 3D views ------------------------------------

/** The full-net faces of the given pieces, as base-face indices (the 3D view's own indexing). */
function facesOfPieces(ids: Iterable<number>): Set<number> {
  const wanted = new Set(ids);
  const faces = new Set<number>();
  if (!resultPlan) return faces;
  resultPlan.full.source_polygon_id!.forEach((source, f) => {
    if (wanted.has(source)) faces.add(f);
  });
  return faces;
}

/** An edge's real path on the shown display (its subdivision points, end to end), cached. */
function pathOf(shape: number, edge: number): Vec3[] | null {
  if (!shownDisplay || !shownSource) return null;
  const key = `${shape}:${edge}`;
  const cached = shownPaths.get(key);
  if (cached) return cached;
  const ids = shownDisplay.corners.get(shape);
  if (!ids) return null;
  const path = edgePath(shownDisplay, shownSource, shape, ids, edge);
  shownPaths.set(key, path);
  return path;
}

/** The edge under a client point in 3D (within EDGE_PICK_PX of its real path, and facing the camera), or null. */
function pickEdge(clientX: number, clientY: number): { shape: number; edge: number } | null {
  if (!shownDisplay) return null;
  let best: { shape: number; edge: number } | null = null;
  let bestDist = EDGE_PICK_PX;
  for (const shape of builder.shapes) {
    const ids = shownDisplay.corners.get(shape.id);
    if (!ids) continue;
    for (let e = 0; e < ids.length; e++) {
      const path = pathOf(shape.id, e);
      if (!path || path.length < 2) continue;
      let d = Infinity;
      for (let i = 0; i + 1 < path.length; i++) d = Math.min(d, viewer.edgeDistance(clientX, clientY, path[i], path[i + 1]));
      if (d >= bestDist) continue;
      if (!viewer.isVisible(path[Math.floor(path.length / 2)])) continue;
      bestDist = d;
      best = { shape: shape.id, edge: e };
    }
  }
  return best;
}

/** The edge group's 3D paths: every edge of the group, as paths on the shown display. */
function groupPaths(edge: { shape: number; edge: number }): Vec3[][] {
  const group = edgeGroup(builder.connections, edge.shape, edge.edge);
  return group.edges.filter((e) => !isOpenEdge(e.shape, e.edge)).map((e) => pathOf(e.shape, e.edge)).filter((p): p is Vec3[] => p !== null);
}

/** An edge no join uses: a free edge of the net. */
function isOpenEdge(shape: number, edge: number): boolean {
  return !builder.connections.some((c) => (c.aShape === shape && c.aEdge === edge) || (c.bShape === shape && c.bEdge === edge));
}

/** Every free edge on the shown display, as "shape:edge" keys. */
function openEdgeKeys(): string[] {
  if (!shownDisplay) return [];
  const keys: string[] = [];
  for (const [shape, ids] of shownDisplay.corners) {
    for (let e = 0; e < ids.length; e++) if (isOpenEdge(shape, e)) keys.push(`${shape}:${e}`);
  }
  return keys;
}

/** The "shape:edge" keys of an edge's group (the edge alone when it's open). */
function groupKeys(edge: { shape: number; edge: number }): Set<string> {
  return new Set(edgeGroup(builder.connections, edge.shape, edge.edge).edges.map((e) => `${e.shape}:${e.edge}`));
}

/**
 * The free edges as tubes. Each is red if it or its piece is selected, yellow if it or its piece is hovered, and dark
 * otherwise. The edge's own selection or hover wins over its piece's, so pointing at one tube still shows that one.
 */
function openEdgePaths(skip: Set<number>): { path: Vec3[]; color: number }[] {
  const hoverKeys = canvas.hoverEdge ? groupKeys(canvas.hoverEdge) : new Set<string>();
  const selected = selectedEdgeGroup();
  const selectKeys = selected ? groupKeys(selected) : new Set<string>();
  if (pressEdge) selectKeys.add(`${pressEdge.shape}:${pressEdge.edge}`);
  const out: { path: Vec3[]; color: number }[] = [];
  for (const key of openEdgeKeys()) {
    const [shape, edge] = key.split(":").map(Number);
    if (skip.has(shape)) continue;
    const path = pathOf(shape, edge);
    if (!path || path.length < 2) continue;
    let color = OPEN_EDGE_COLOR;
    if (selectKeys.has(key)) color = SELECT_HIGHLIGHT;
    else if (hoverKeys.has(key)) color = HOVER_HIGHLIGHT;
    else if (builder.selected.has(shape)) color = SELECT_HIGHLIGHT;
    else if (canvas.hoverPiece === shape && !canvas.hoverEdge) color = HOVER_HIGHLIGHT;
    out.push({ path, color });
  }
  return out;
}

/**
 * Shows the hovered edge group in yellow and the selected one in red, in both views: a 3D tube along each
 * edge, and the faces of the pieces the selection covers. Selection is a join (both of its edges), an open
 * edge, or a set of pieces.
 */
function syncHighlights() {
  // A solve queued but not started freezes the picture: no highlight or tube changes until it starts or is dropped.
  if (inflatePending && !running) {
    viewerEl.classList.add("loading");
    return;
  }
  const hovered = canvas.hoverEdge
    ? { baseFaces: new Set<number>(), color: HOVER_HIGHLIGHT }
    : { baseFaces: facesOfPieces(canvas.hoverPiece === null || builder.selected.has(canvas.hoverPiece) ? [] : [canvas.hoverPiece]), color: HOVER_HIGHLIGHT };

  // The red selection: the selected pieces' faces, the selected edge group's tubes, and a selected join's red
  // line between the middles of its two edges.
  const redEdges: Vec3[][] = [];
  const selected = selectedEdgeGroup();
  if (selected) for (const path of groupPaths(selected)) redEdges.push(path);
  const conn = builder.connections.find((c) => c.id === builder.selectedConnection);
  if (conn) {
    if (joinLine && joinLine.conn === conn.id) {
      const a = pointOnEdge(joinLine.a);
      const b = pointOnEdge(joinLine.b);
      if (a && b) redEdges.push([a, b]);
    } else {
      const pa = pathOf(conn.aShape, conn.aEdge);
      const pb = pathOf(conn.bShape, conn.bEdge);
      if (pa && pb && pa.length && pb.length) redEdges.push([middleOf(pa), middleOf(pb)]);
    }
  }
  let red: RedSelection = { faces: facesOfPieces(builder.selected), edges: redEdges, shapes: new Set(builder.selected), pieces: [] };
  const empty = red.faces.size === 0 && red.edges.length === 0;
  // A deleted selection stays red while a solve is pending or running: its last edge paths, not the old face indices
  // (those no longer match the mesh once a new solve is drawn).
  const restored = inflatePending && empty && lastRed !== null;
  if (restored) {
    red = { faces: new Set(), edges: lastRed!.edges, shapes: lastRed!.shapes, pieces: lastRed!.pieces };
  } else {
    red.pieces = [...builder.selected].flatMap((shape) =>
      (shownDisplay?.corners.get(shape) ?? []).map((_, e) => pathOf(shape, e)).filter((p): p is Vec3[] => p !== null && p.length > 1),
    );
    lastRed = red;
  }

  viewer.setHighlights([
    { baseFaces: red.faces, color: SELECT_HIGHLIGHT },
    hovered,
  ]);
  const edges: { path: Vec3[]; color: number }[] = [];
  if (canvas.hoverEdge) for (const path of groupPaths(canvas.hoverEdge)) edges.push({ path, color: HOVER_HIGHLIGHT });
  // The edge a drag started on stays red until the drag ends.
  if (pressEdge && !isOpenEdge(pressEdge.shape, pressEdge.edge)) {
    const path = pathOf(pressEdge.shape, pressEdge.edge);
    if (path) edges.push({ path, color: SELECT_HIGHLIGHT });
  }
  for (const path of red.edges) edges.push({ path, color: SELECT_HIGHLIGHT });
  if (colors.mode === "african") {
    // While restored, the deleted pieces' edges are red tubes in place of their dark ones.
    const restoredRed = restored ? red.pieces.map((path) => ({ path, color: SELECT_HIGHLIGHT })) : [];
    viewer.setOpenEdges([...openEdgePaths(restored ? red.shapes : new Set()), ...restoredRed]);
  } else {
    viewer.setOpenEdges([]);
    if (restored) for (const path of red.pieces) edges.push({ path, color: SELECT_HIGHLIGHT });
  }
  viewer.setEdgeHighlights(edges);
  viewerEl.classList.toggle("loading", inflatePending || running);
}

/**
 * The anchor of the point on an edge nearest the pointer, found on the edge as it's drawn on screen: the
 * closest point of its path in screen space, so the end is where the user actually pointed at the edge.
 */
function anchorOnEdge(shape: number, edge: number, clientX: number, clientY: number): EdgeAnchor {
  const path = pathOf(shape, edge);
  if (!path || path.length < 2) return { shape, edge, t: 0.5 };
  const screen = path.map((p) => viewer.clientPoint(p));
  const lens: number[] = [];
  for (let i = 0; i + 1 < path.length; i++) lens.push(Math.hypot(...sub3(path[i + 1], path[i])));
  const total = lens.reduce((a, b) => a + b, 0) || 1;
  let best = { d: Infinity, t: 0.5 };
  let acc = 0;
  for (let i = 0; i + 1 < path.length; i++) {
    const [ax, ay] = screen[i];
    const [bx, by] = screen[i + 1];
    const [dx, dy] = [bx - ax, by - ay];
    const len2 = dx * dx + dy * dy;
    const u = len2 ? Math.max(0, Math.min(1, ((clientX - ax) * dx + (clientY - ay) * dy) / len2)) : 0;
    const d = Math.hypot(clientX - (ax + u * dx), clientY - (ay + u * dy));
    if (d < best.d) best = { d, t: (acc + u * lens[i]) / total };
    acc += lens[i];
  }
  return { shape, edge, t: best.t };
}

/** The point at an anchor's fraction along its edge's current path, or null if the edge isn't shown. */
function pointOnEdge(anchor: EdgeAnchor): Vec3 | null {
  const path = pathOf(anchor.shape, anchor.edge);
  if (!path || path.length < 2) return null;
  const lens: number[] = [];
  for (let i = 0; i + 1 < path.length; i++) lens.push(Math.hypot(...sub3(path[i + 1], path[i])));
  const total = lens.reduce((a, b) => a + b, 0) || 1;
  let target = anchor.t * total;
  for (let i = 0; i + 1 < path.length; i++) {
    if (target <= lens[i] || i === path.length - 2) {
      const u = lens[i] ? Math.max(0, Math.min(1, target / lens[i])) : 0;
      const a = path[i];
      const ab = sub3(path[i + 1], a);
      return [a[0] + u * ab[0], a[1] + u * ab[1], a[2] + u * ab[2]];
    }
    target -= lens[i];
  }
  return null;
}

function sub3(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

/** The point halfway along an edge path (the middle of its subdivision points). */
function middleOf(path: Vec3[]): Vec3 {
  return path[Math.floor(path.length / 2)];
}

/** The selected edge: the selected join's first edge, or the selected open edge. */
function selectedEdgeGroup(): { shape: number; edge: number } | null {
  if (builder.selectedConnection !== null) {
    const conn = builder.connections.find((c) => c.id === builder.selectedConnection);
    return conn ? { shape: conn.aShape, edge: conn.aEdge } : null;
  }
  return canvas.selectedEdge;
}

/** Selects an edge's group: its join if it's joined, otherwise the open edge alone. */
function selectEdge(edge: { shape: number; edge: number }) {
  const group = edgeGroup(builder.connections, edge.shape, edge.edge);
  builder.selected = new Set();
  if (group.connection) {
    builder.selectedConnection = group.connection.id;
    canvas.selectedEdge = null;
  } else {
    builder.selectedConnection = null;
    canvas.selectedEdge = edge;
  }
  refresh();
}

/** The piece a 3D point belongs to, or null if it is off the mesh. */
function pieceAt(clientX: number, clientY: number): number | null {
  const base = viewer.pick(clientX, clientY);
  if (base === null || !resultPlan) return null;
  return resultPlan.full.source_polygon_id![base];
}

canvas.onHoverEdge = () => syncHighlights();
canvas.onSelectEdge = (edge) => selectEdge(edge);

const viewerEl = $("viewer");
let pressAt: [number, number] | null = null;
/** The edge a 3D press started on: a drag from it to another edge makes a join. */
let pressEdge: { shape: number; edge: number } | null = null;
/**
 * A point on an edge, as a fraction t of its length along its path. The line a drag made is kept as two of
 * these, so it stays on its edges when a re-solve moves the mesh.
 */
type EdgeAnchor = { shape: number; edge: number; t: number };
/** The line a drag made, kept while its join is selected: from where the drag began to where it ended. */
let joinLine: { conn: number; a: EdgeAnchor; b: EdgeAnchor } | null = null;
/** The red line a join drag draws from its start edge to the pointer (an SVG over the 3D view). */
const SVG_NS = "http://www.w3.org/2000/svg";
const dragSvg = document.createElementNS(SVG_NS, "svg");
dragSvg.setAttribute("class", "drag-line");
const dragLineEl = document.createElementNS(SVG_NS, "line");
dragLineEl.setAttribute("stroke", "#e53935");
dragLineEl.setAttribute("stroke-width", "3");
dragLineEl.setAttribute("stroke-linecap", "round");
dragSvg.append(dragLineEl);
dragSvg.style.display = "none";
viewerEl.append(dragSvg);

/** Draws the join drag: the red line from the start edge's middle to the pointer, and the edge under the pointer in yellow. */
function updateDrag(e: PointerEvent) {
  const start = pressEdge;
  if (!start) return;
  const rect = viewerEl.getBoundingClientRect();
  // The line starts where the press was, so it reads as dragged out from that point of the edge.
  if (pressAt) {
    dragLineEl.setAttribute("x1", String(pressAt[0] - rect.left));
    dragLineEl.setAttribute("y1", String(pressAt[1] - rect.top));
  }
  dragLineEl.setAttribute("x2", String(e.clientX - rect.left));
  dragLineEl.setAttribute("y2", String(e.clientY - rect.top));
  dragSvg.style.display = "";
  const target = pickEdge(e.clientX, e.clientY);
  const other = target && !(target.shape === start.shape && target.edge === start.edge) ? target : null;
  canvas.setHoverEdge(other);
}
// Capture phase, so the orbit is turned off before the viewer's own press handler runs.
viewerEl.addEventListener(
  "pointerdown",
  (e) => {
    if (e.button !== 0) return;
    pressEdge = pickEdge(e.clientX, e.clientY);
    viewer.setOrbitEnabled(pressEdge === null);
    if (pressEdge) syncHighlights();
  },
  { capture: true },
);
viewerEl.addEventListener("pointermove", (e) => {
  if (pressAt) {
    if (pressEdge) updateDrag(e);
    return;
  }
  // Edges first: if one is under the pointer, it wins over the face behind it.
  const edge = pickEdge(e.clientX, e.clientY);
  canvas.setHoverEdge(edge);
  canvas.setHoverPiece(edge ? null : pieceAt(e.clientX, e.clientY));
});
viewerEl.addEventListener("pointerleave", () => {
  canvas.setHoverEdge(null);
  canvas.setHoverPiece(null);
});
viewerEl.addEventListener("pointerdown", (e) => {
  pressAt = [e.clientX, e.clientY];
});
viewerEl.addEventListener("pointerup", (e) => {
  const start = pressAt;
  const from = pressEdge;
  pressAt = null;
  pressEdge = null;
  viewer.setOrbitEnabled(true);
  dragSvg.style.display = "none";
  if (!start) return;
  if (Math.hypot(e.clientX - start[0], e.clientY - start[1]) > CLICK_SLOP_PX) {
    // A drag that began on an edge joins it to the edge it's released on, and the new join is selected so
    // both of its edges and the join read as one red connection (as in the 2D view).
    const to = from ? pickEdge(e.clientX, e.clientY) : null;
    canvas.setHoverEdge(null);
    if (from && to && !(to.shape === from.shape && to.edge === from.edge)) {
      if (builder.join(from.shape, from.edge, to.shape, to.edge)) {
        const conn = builder.connections[builder.connections.length - 1];
        builder.selectConnection(conn.id);
        // The line the drag drew stays, from where it began to where it ended, as anchors on those edges.
        joinLine = {
          conn: conn.id,
          a: anchorOnEdge(from.shape, from.edge, start[0], start[1]),
          b: anchorOnEdge(to.shape, to.edge, e.clientX, e.clientY),
        };
      }
    }
    refresh();
    return;
  }
  const edge = pickEdge(e.clientX, e.clientY);
  if (edge) {
    selectEdge(edge);
    return;
  }
  // A click on a piece selects it alone; a click on empty space clears the selection.
  const piece = pieceAt(e.clientX, e.clientY);
  builder.selected = piece === null ? new Set() : new Set([piece]);
  builder.selectedConnection = null;
  canvas.selectedEdge = null;
  refresh();
});

// ---- Debug mode ---------------------------------------------------------------------------------

/** Debug mode (D): the builder's owner anchor glyph, plus the Setup fields and overlays. Titles say so, as in the Python app. */
function setDebugMode(on: boolean) {
  debugMode = on;
  canvas.debug = on;
  document.title = on ? "Interactive Inflater (debug mode)" : "Interactive Inflater";
  debugRow.hidden = !on;
  // Debug mode: Reinflate moves to after the replay slider, and undo/redo are left to the Edit menu.
  (on ? debugRow : navRow).append(inflateBtn);
  navRow.hidden = on;
  undoBtn.hidden = redoBtn.hidden = on;
  // Leaving debug mode clears the overlays, as in the Static Inflater, and goes back to the finished result.
  for (const box of Object.values(debugBoxes)) box.checked = false;
  // Smooth shading is the default; leaving debug mode keeps whatever the box says.
  viewer.setSmoothShading(smoothBox.checked);
  applyOverlays();
  if (!on) redrawFinest();
  updateReplayControl();
  canvas.redraw();
}

/** The replay slider: shown in debug mode, enabled once the shown result has frames to scrub, and never while running. */
function updateReplayControl() {
  replaySlider.max = String(Math.max(0, replayFrames.length - 1));
  replaySlider.value = replaySlider.max;
  replaySlider.disabled = running || replayFrames.length < 2;
  replaySlider.closest<HTMLElement>(".replay-control")!.hidden = !debugMode;
}

/** Shows replay frame `index` of the level on screen, as the relaxation left it at that step. */
function showReplayFrame(index: number) {
  const frame = replayFrames[index];
  if (!frame || !resultPlan) return;
  drawLevel(resultPlan, replayLevel, frame.positions);
}

function setReplay(level: number, frames: ReplayFrame[]) {
  replayLevel = level;
  replayFrames = frames;
  updateReplayControl();
}

replaySlider.addEventListener("input", () => showReplayFrame(Number(replaySlider.value)));

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
smoothBox.addEventListener("change", () => viewer.setSmoothShading(smoothBox.checked));

// ---- Setup fields -------------------------------------------------------------------------------


// ---- Drawing the result -------------------------------------------------------------------------

/** Draws one level: the solved junction pieces plus the flat terminals around them. */
function drawLevel(plan: Placement, level: number, positions: Map<number, Vec3>) {
  const topo = store.topology[level];
  if (!topo) return;
  const display = buildDisplay(plan, topo, positions);
  shownDisplay = display;
  shownSource = plan.full.source_polygon_id!;
  shownPaths = new Map();
  viewer.setMesh(display.faces, display.faceEdgeIds, display.positions, display.faceOfFine, faceColorsOf(plan), display.outlineEdgeIds, display.faceUV);
  // African Flower hides the polygon outlines (they'd read as gaps between textured polygons), as in the Static Inflater.
  viewer.setTextured(colors.mode === "african");
  viewer.setLayers(colors.mode !== "african", false);
  // Repulsion arrows only where the solver repels: the junction corners, with the level's multipliers.
  viewer.setRepulsion(plan.solve ? repulsionMultipliers(loadNet(plan.solve), level) : null);
  viewer.render();
  syncHighlights();
}

/** Each face's colour under the current mode: a face takes its own piece's colour, as the 2D view shows it. */
function faceColorsOf(plan: Placement): number[] {
  const state: ColorState = {
    mode: colors.mode,
    multiColors: plan.full.source_polygon_id!.map((id) => colors.multi[id] ?? polygonColor(3)),
  };
  return displayColors(state, plan.full.faces, plan.full);
}

/**
 * Recolours the shown result, so a colour change keeps the camera where it is. The African Flower textures are baked
 * into the solve, so the shown result is re-pointed at the current choices first, and its mesh is rebuilt from them.
 */
function applyColors() {
  if (running || !resultPlan) return;
  const fresh = tryPlan();
  if (fresh && junctionKey(fresh) === junctionTarget) {
    resultPlan = fresh;
    resultSpec = fresh.full;
    retexture(fresh.solveChoice);
    redrawFinest();
  }
  viewer.setBaseColors(faceColorsOf(resultPlan));
  viewer.render();
  refreshColorMenu();
}

/** Re-points each shown level's texture from the choice it was baked with to `next` (no re-solve needed). */
function retexture(next: AtlasChoice) {
  for (const level of LEVELS) {
    const topo = store.topology[level];
    if (!topo?.faceUV || !topo.atlas || topo.atlas.length !== next.length) continue;
    store.topology[level] = { ...topo, faceUV: retargetFaceUV(topo.faceUV, topo.faceOfFine, topo.atlas, next), atlas: next };
  }
}

/** Shows the finest level still in the store, or clears the viewer if there is none. */
function redrawFinest() {
  for (const level of [...LEVELS].reverse()) {
    const positions = store.positions[level];
    if (positions && resultPlan) {
      drawLevel(resultPlan, level, positions);
      return;
    }
  }
  viewer.clear();
}

function clearResults() {
  setReplay(3, []);
  shownDisplay = null;
  shownPaths = new Map();
  store.clear();
  resultSpec = null;
  resultPlan = null;
  viewer.clear();
  refreshColorMenu();
}

// ---- Full Inflate -------------------------------------------------------------------------------

/**
 * Keeps a new level where the old result was: the rigid motion (rotation and translation, Kabsch) that best
 * maps the corners both solves share onto their old positions is applied to the level's positions. A re-solve
 * then reads as the same shape moving a little, not a jump. Null if there are fewer than three shared corners.
 */
function alignPositions(prev: LastSolve, slots: Map<string, number>, positions: Map<number, Vec3>): Map<number, Vec3> | null {
  const before: Vec3[] = [];
  const after: Vec3[] = [];
  for (const [slot, id] of slots) {
    const oldId = prev.slots.get(slot);
    if (oldId === undefined) continue;
    const p = prev.positions.get(oldId);
    const q = positions.get(id);
    if (p && q) {
      before.push(p);
      after.push(q);
    }
  }
  if (before.length < 3) return null;
  const transform = rigidTransformFrom(before, after);
  return new Map([...positions].map(([id, p]) => [id, transform(p)]));
}

/** The piece each solve face belongs to, in the solve's face order. */
function sourceOfFace(plan: Placement): number[] {
  return plan.solveToFull.map((f) => plan.full.source_polygon_id![f]);
}

/**
 * One Diff Inflate: a single Level-3 calibration from the last solve's positions and pressure (see
 * diffInflate.ts). Leaves Levels 0-2 empty, since they no longer describe this net.
 */
async function runDiff(plan: Placement, targetRmsPct: number, gtol: number): Promise<RunOutcome> {
  setInflaterStatus("Diff Inflate -- Level 3: Step 0.", "info");
  try {
    const result = await diffInflate(plan.solve!, plan.slots!, lastSolve!, {
      targetRmsPct,
      gtol,
      shouldStop: () => stopRequested,
      sourceOfFace: sourceOfFace(plan),
      shapes: plan.shapes,
      atlasChoice: plan.solveChoice,
    });
    store.clear();
    store.topology[3] = result.topo;
    const aligned = alignPositions(lastSolve!, plan.slots!, result.positions) ?? result.positions;
    store.positions[3] = aligned;
    store.history[3] = {
      level: 3, state: "converged", steps: 0, optimality: null, gtol,
      rmsStretchPct: result.rmsStretchPct, pressure: result.pressure, simTimeS: 0,
    };
    drawLevel(plan, 3, aligned);
    setReplay(3, result.frames);
    setInflaterStatus(
      `Diff Inflate -- Done. RMS stretch ${result.rmsStretchPct.toFixed(1)}%, pressure ${result.pressure.toFixed(2)}.`,
      "success",
    );
    return "done";
  } catch (err) {
    console.error(err);
    if (stopRequested) {
      setInflaterStatus("Diff Inflate -- Stopped.", "warn");
      return "stopped";
    }
    setInflaterStatus(`Diff Inflate -- ${err instanceof Error ? err.message : String(err)}`, "error");
    return "error";
  }
}

/**
 * One solve of the active group's junctions (terminals are laid flat around them, see placement.ts).
 * Each level is drawn as it finishes, so the finest one on screen is always the newest. Stop, or any
 * failure, puts back the previous result (Python's MeshSnapshotManager). Edits made during the run
 * are picked up when it stops: a junction change solves again, a terminal-only change re-places.
 */
async function inflate(forceFull = false) {
  const plan = tryPlan();
  if (!plan) return;
  if (plan.solve === null) {
    showNoSolve(plan);
    return;
  }
  const solve = plan.solve;
  const runJunction = junctionKey(plan);
  // A Diff Inflate once a solve has finished and its corners still match; otherwise a Full Inflate.
  // Reinflate always runs a Full Inflate; an edit runs a Diff when one is possible.
  const useDiff = !forceFull && fullyInflated && canDiff(plan.slots, lastSolve);

  // Every level uses the net's default target (5% open, 10% closed) and the default tolerance.
  const defaultPct = defaultTargetFor(plan.full);
  const targetRmsPctByLevel = { 1: defaultPct, 2: defaultPct, 3: defaultPct };
  const gtol = CONVERGENCE_GTOL;

  const before = store.snapshot();
  const beforePlan = resultPlan;
  const beforeSpec = resultSpec;
  const beforeTarget = junctionTarget;
  const beforeLast = lastSolve;
  stopRequested = false;
  rerunPending = false;
  junctionTarget = runJunction;
  setRunning(true);
  let outcome: RunOutcome = "error";
  try {
    outcome = useDiff
      ? await runDiff(plan, targetRmsPctByLevel[3], gtol)
      : await runFullInflate(solve, {
          label: "Full Inflate",
          targetRmsPctByLevel,
          gtol,
          atlasChoice: plan.solveChoice,
          store,
          shouldStop: () => stopRequested,
          hooks: {
            status: setInflaterStatus,
            loading: () => {},
            showLevel: (level, positions, frames) => {
              // Each level lands where the previous result was, so the picture moves smoothly through the solve.
              const aligned = beforeLast && plan.slots ? alignPositions(beforeLast, plan.slots, positions) : null;
              if (aligned) store.positions[level] = aligned;
              drawLevel(plan, level, aligned ?? positions);
              setReplay(level, frames);
            },
            historyChanged: () => {},
          },
        });
  } finally {
    setRunning(false);
  }
  if (outcome === "done") {
    fullyInflated = true;
    resultPlan = plan;
    resultSpec = plan.full;
    lastSolve = plan.slots && store.positions[3] && store.topology[3] && store.history[3]?.pressure != null
      ? {
          slots: plan.slots,
          positions: store.positions[3]!,
          pressure: store.history[3]!.pressure!,
          triangles: surfaceTriangles(store.topology[3]!, store.positions[3]!, sourceOfFace(plan)),
        }
      : null;
    refreshColorMenu();
  } else {
    store.restore(before);
    resultPlan = beforePlan;
    resultSpec = beforeSpec;
    junctionTarget = beforeTarget;
    lastSolve = beforeLast;
    setReplay(3, []);
    redrawFinest();
  }

  // The solve is over, so nothing is waiting any more. A change made during the run re-arms it below.
  inflatePending = false;
  // What changed while the run was going. A junction change, or a rerun the run asked for, solves again.
  // A terminal-only change just re-places the flat pieces on the result that's now on screen.
  const now = tryPlan();
  if (!now) return;
  if (now.solve === null) {
    showNoSolve(now);
  } else if (rerunPending || junctionKey(now) !== runJunction) {
    scheduleAutoInflate();
  } else if (outcome === "done") {
    showPlan(now);
  }
  syncHighlights();
}

// ---- File: New, Load 3D Model, Save 3D Model ----------------------------------------------------

const newItem = $<HTMLButtonElement>("new-item");
const load3dItem = $<HTMLButtonElement>("load-3d-item");
const save3dItem = $<HTMLButtonElement>("save-3d-item");
const unsavedDialog = $<HTMLDialogElement>("unsaved-dialog");
const modelFileInput = $<HTMLInputElement>("model-file");

/** The slice of the File System Access API used for Save 3D Model (not in every TS DOM lib). */
type SaveWindow = Window & {
  showSaveFilePicker?: (options: {
    suggestedName: string;
    startIn: "downloads";
    types: { description: string; accept: Record<string, string[]> }[];
  }) => Promise<{ name: string; createWritable(): Promise<{ write(data: string): Promise<void>; close(): Promise<void> }> }>;
};

/** The model's name (its file name without the extension). "untitled" until one is saved or loaded. */
let modelName = "untitled";
/** Set when a colour changes after the last save or load. The builder tracks the net itself; colours it doesn't. */
let colourEdited = false;

/** The model on screen differs from the one last saved or loaded (the net, or its colours). */
function hasUnsavedChanges(): boolean {
  return builder.isDirty || colourEdited;
}

/** Asks Save / Don't save / Cancel before throwing away unsaved changes. Resolves true when it's safe to go on. */
async function confirmSaved(): Promise<boolean> {
  if (!hasUnsavedChanges()) return true;
  const choice = await new Promise<string>((resolve) => {
    unsavedDialog.addEventListener("close", () => resolve(unsavedDialog.returnValue), { once: true });
    unsavedDialog.showModal();
  });
  if (choice === "save") return saveModel();
  return choice === "discard";
}

/**
 * The model as a .hippo session: the active group's net (as a .poly, so it reloads into the 2D view), its colours, and
 * each solved level with its positions, topology and history (the pressure a Diff Inflate starts from).
 */
function buildModel(): string {
  const plan = tryPlan();
  if (!plan) throw new Error("The net is not a valid mesh yet.");
  const active = activeNet();
  const levels = LEVELS.map((level) => {
    const topo = store.topology[level];
    const positions = store.positions[level];
    if (!topo || !positions || topo.faces.length === 0) return null;
    return snapshotLevel(topo, positions);
  });
  const atlasChoice = LEVELS.map((level) => store.topology[level]?.atlas).find((choice) => choice !== undefined);
  const target = defaultTargetFor(plan.full);
  const data: SessionData = {
    netName: modelName,
    netSpec: plan.full,
    netFile: netFileFrom(active.shapes, active.connections, modelName, canvas.viewScale, colors),
    colorMode: colors.mode,
    atlasChoice,
    multiColors: [],
    targetRmsPct: [target, target, target],
    tolerance: CONVERGENCE_GTOL,
    camera: camera.snapshot(),
    view2d: { scale: canvas.viewScale, offset: canvas.viewOffset },
    history: LEVELS.map((level) => store.history[level]),
    levels,
  };
  return serializeSession(data);
}

/** File > Save 3D Model: writes the .hippo through the save dialog (a download where there's none). True once saved. */
async function saveModel(): Promise<boolean> {
  let text: string;
  try {
    text = buildModel();
  } catch (err) {
    setInflaterStatus(`Could not save: ${err instanceof Error ? err.message : String(err)}`, "error");
    return false;
  }
  const suggestedName = `${modelName}${SESSION_EXTENSION}`;
  try {
    const picker = (window as SaveWindow).showSaveFilePicker;
    if (picker) {
      const handle = await picker({
        suggestedName,
        startIn: "downloads",
        types: [{ description: "Inflate Polyhedron model", accept: { "application/json": [SESSION_EXTENSION] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(text);
      await writable.close();
      modelName = handle.name.replace(/\.[^.]+$/, "");
    } else {
      // No save dialog here, so ask for the name; a download can't be named any other way.
      const name = window.prompt("Name for the model:", modelName);
      if (name === null) return false;
      modelName = name.trim() || modelName;
      const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${modelName}${SESSION_EXTENSION}`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return false; // cancelled in the save dialog
    setInflaterStatus(`Could not save: ${err instanceof Error ? err.message : String(err)}`, "error");
    return false;
  }
  builder.markSaved();
  colourEdited = false;
  setInflaterStatus(`Saved ${modelName}${SESSION_EXTENSION}.`, "success");
  refresh();
  return true;
}

/** File > New: asks about unsaved changes, then clears the canvas and forgets the solve (so the next net runs a Full Inflate). */
async function newNet() {
  if (running || !(await confirmSaved())) return;
  cancelAutoInflate();
  builder.loadShapes([], []);
  Object.assign(colors, defaultNetColors());
  colourEdited = false;
  modelName = "untitled";
  fullyInflated = false;
  inflatePending = false;
  junctionTarget = null;
  lastSolve = null;
  seenKey = null;
  clearResults();
  setInflaterStatus("");
  refresh();
}

/**
 * File > Load 3D Model: a .hippo's net goes into the 2D view and its solved levels into the 3D view, with the pressure and
 * history a Diff Inflate needs. Nothing is re-solved, so the shown result is the saved one.
 */
async function loadModel(file: File) {
  if (running) return;
  try {
    const data = parseSession(await file.text());
    // A Static Inflater session keeps the net's layout and joins in its netSpec (the same keys as a .poly); ours in netFile.
    const { shapes, connections, colors: fileColors } = shapesFrom(data.netFile ?? data.netSpec);
    builder.loadShapes(shapes, connections);
    if (data.view2d) {
      canvas.setViewScale(data.view2d.scale);
      canvas.setViewOffset(...data.view2d.offset);
    }
    if (data.camera) camera.apply(data.camera);
    Object.assign(colors, fileColors ?? defaultNetColors());
    colourEdited = false;
    modelName = file.name.replace(/\.[^.]+$/, "");
    const plan = tryPlan();
    if (!plan) throw new Error("its net is not a valid mesh.");
    store.clear();
    LEVELS.forEach((level) => {
      store.history[level] = data.history[level];
      const snap = data.levels[level];
      if (!snap) return;
      const restored = restoreLevel(snap);
      store.topology[level] = { ...restored.topology, atlas: data.atlasChoice };
      store.positions[level] = restored.positions;
    });
    setReplay(3, []);
    // A Diff Inflate needs the level-3 solve, its corner slots, and its pressure, all from the file.
    const solved = store.positions[3] && store.topology[3] && store.history[3]?.pressure != null ? store.positions[3]! : null;
    fullyInflated = solved !== null;
    junctionTarget = plan.solve ? junctionKey(plan) : null;
    lastSolve = plan.slots && solved
      ? {
          slots: plan.slots,
          positions: solved,
          pressure: store.history[3]!.pressure!,
          triangles: surfaceTriangles(store.topology[3]!, solved, sourceOfFace(plan)),
        }
      : null;
    inflatePending = false;
    // The net and its solve are already in place, so the refresh below must not start a new run.
    seenKey = currentKey();
    if (plan.solve) showPlan(plan);
    else showNoSolve(plan);
    setInflaterStatus(`Loaded ${file.name}.`, "success");
  } catch (err) {
    setInflaterStatus(`Could not load ${file.name}: ${err instanceof Error ? err.message : String(err)}`, "error");
  }
  refresh();
}

newItem.addEventListener("click", () => void newNet());
load3dItem.addEventListener("click", () => modelFileInput.click());
modelFileInput.addEventListener("change", () => {
  const file = modelFileInput.files?.[0];
  modelFileInput.value = "";
  if (file) void loadModel(file);
});
save3dItem.addEventListener("click", () => void saveModel());

inflateBtn.addEventListener("click", () => {
  if (running) {
    // A user Stop ends this run and does not restart it for the same net.
    stopRequested = true;
    rerunPending = false;
    setInflaterStatus("Stopping after the current step...", "warn");
  } else {
    cancelAutoInflate();
    void inflate(true);
  }
});
undoBtn.addEventListener("click", () => undoItem.click());
redoBtn.addEventListener("click", () => redoItem.click());

setDebugMode(false);
refresh();
revealPage();
// The hexagon atlas loads after the first draw; redraw once it's there so African pieces and icons appear.
void hexAtlasLoaded().then(() => refresh());
