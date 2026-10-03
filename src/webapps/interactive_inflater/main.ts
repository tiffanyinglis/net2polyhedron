import { mountAppNav, revealPage } from "../utils/appNav";
import { regularPolygonVertices } from "../utils/geometry";
import { Builder, POLYGON_NS, shapeCssColor } from "../net_builder/builder";
import { BuilderCanvas } from "../net_builder/canvas";
import { NetValidationError } from "../net_builder/netExport";
import { shapesFrom } from "../net_builder/netFile";
import { SharedCamera, Viewer } from "../static_inflater/viewer";
import { displayColors, type ColorState } from "../utils/colors";
import { fullInflate, type LevelRecord } from "../utils/physics/pipeline";
import { CONVERGENCE_GTOL } from "../utils/physics/convergence";
import { type NetSpec } from "../utils/physics/mesh";
import { type Vec3 } from "../utils/physics/vec3";
import { netSpecFromBuilder } from "./bridge";

mountAppNav("interactive_inflater");

/** Inflation is switched off while the builder is being laid out. Set to true to bring back the Setup row and Run. */
const INFLATE_ENABLED = false;

type StatusKind = "info" | "success" | "error";

/** One level's mesh as the solver reports it: topology from onTopology, positions from onLevelResult. */
interface Topology {
  faces: number[][];
  faceOfFine: number[];
  faceEdgeIds: number[][];
  outlineEdgeIds: Set<number>;
}

/** What the Viewer currently shows, kept so a failed run can put it back. */
interface Shown {
  spec: NetSpec;
  topo: Topology;
  positions: Map<number, Vec3>;
}

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvasEl = $<HTMLCanvasElement>("net-canvas");
const paletteEl = $("palette");
const builderStatusEl = $("builder-status");
const inflaterStatusEl = $("inflater-status");
const inflateBtn = $<HTMLButtonElement>("inflate-btn");
const tolInput = $<HTMLInputElement>("tolerance");
const undoItem = $<HTMLButtonElement>("undo-item");
const redoItem = $<HTMLButtonElement>("redo-item");
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
const viewer = new Viewer($("viewer"), new SharedCamera(), () => viewer.render());
/** Polygon-specific colouring, the default in the Python app. */
const colors: ColorState = { mode: "polygon", multiColors: [] };

let running = false;
let stopRequested = false;
let shown: Shown | null = null;

tolInput.value = String(CONVERGENCE_GTOL);

// ---- status and controls ------------------------------------------------------------------------

function setInflaterStatus(text: string, kind: StatusKind = "info") {
  inflaterStatusEl.textContent = text;
  inflaterStatusEl.style.color = kind === "error" ? "var(--error)" : kind === "success" ? "var(--success)" : "var(--info)";
}

function hintText(): string {
  if (builder.armedN !== null) return "Click the drawing area to place the shape.";
  return "Drag shapes to move them. Click an edge handle, then another, to join them.";
}

/** Keeps menus, palette, the Inflate button and the builder hint in line with the builder. */
function refresh() {
  undoItem.disabled = !builder.canUndo;
  redoItem.disabled = !builder.canRedo;
  for (const button of paletteEl.querySelectorAll<HTMLButtonElement>("button")) {
    button.classList.toggle("armed", Number(button.dataset.n) === builder.armedN);
  }
  inflateBtn.disabled = !INFLATE_ENABLED || (!running && builder.shapes.length === 0);
  builderStatusEl.textContent = hintText();
  builderStatusEl.style.color = "var(--info)";
  canvas.redraw();
}

function setRunning(on: boolean) {
  inflateBtn.textContent = on ? "Stop Simulation" : "Run Simulation";
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

// ---- Edit and File menus ------------------------------------------------------------------------

undoItem.addEventListener("click", () => {
  builder.undoStep();
  refresh();
});
redoItem.addEventListener("click", () => {
  builder.redoStep();
  refresh();
});

const netFileInput = $<HTMLInputElement>("net-file");
$("load-item").addEventListener("click", () => netFileInput.click());
netFileInput.addEventListener("change", async () => {
  const file = netFileInput.files?.[0];
  netFileInput.value = "";
  if (!file) return;
  try {
    const { shapes, connections } = shapesFrom(JSON.parse(await file.text()));
    builder.loadShapes(shapes, connections);
    shown = null;
    viewer.clear();
    setInflaterStatus(`Loaded ${file.name}.`);
  } catch (err) {
    setInflaterStatus(`Could not load ${file.name}: ${err instanceof Error ? err.message : String(err)}`, "error");
  }
  refresh();
});

window.addEventListener("keydown", (e) => {
  // While the refusal popup is up, keys belong to it, not to the builder.
  if (rejectDialog.open) return;
  const key = e.key.toLowerCase();
  if (e.ctrlKey || e.metaKey) {
    if (key === "z") {
      builder.undoStep();
      refresh();
    } else if (key === "y") {
      builder.redoStep();
      refresh();
    }
    return;
  }
  if (key === "delete" || key === "backspace") {
    builder.deleteSelected();
    refresh();
  } else if (key === "d" && !(e.target instanceof HTMLInputElement)) {
    setDebugMode(!canvas.debug);
  }
});

/** Debug mode (D): shows the owner's anchor glyph. The title says so, as in the Python app. */
function setDebugMode(on: boolean) {
  canvas.debug = on;
  document.title = on ? "Interactive Inflater (debug mode)" : "Interactive Inflater";
  canvas.redraw();
}

// ---- Inflate ------------------------------------------------------------------------------------

/** Reads one level's target RMS stretch %, or null if it isn't a positive number. */
function readTargetRms(input: HTMLInputElement): number | null {
  const value = Number(input.value);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function draw(current: Shown) {
  viewer.setMesh(
    current.topo.faces,
    current.topo.faceEdgeIds,
    current.positions,
    current.topo.faceOfFine,
    displayColors(colors, current.spec.faces, current.spec),
    current.topo.outlineEdgeIds,
  );
}

async function inflate() {
  if (running) {
    stopRequested = true;
    setInflaterStatus("Stopping after the current step...");
    return;
  }

  let spec: NetSpec;
  try {
    spec = netSpecFromBuilder(builder.shapes, builder.connections, "net");
  } catch (err) {
    const message = err instanceof NetValidationError ? err.message : String(err);
    setInflaterStatus(`The net is not a valid mesh yet: ${message}`, "error");
    return;
  }

  const targetRmsPctByLevel: Record<number, number> = {};
  for (const [i, input] of targetInputs.entries()) {
    const value = readTargetRms(input);
    if (value === null) {
      setInflaterStatus(`Target RMS stretch for level ${i + 1} must be a positive number.`, "error");
      return;
    }
    targetRmsPctByLevel[i + 1] = value;
  }
  const gtol = Number(tolInput.value);
  if (!(gtol > 0)) {
    setInflaterStatus("Tolerance must be a positive number.", "error");
    return;
  }

  const before = shown;
  const topologies = new Map<number, Topology>();
  running = true;
  stopRequested = false;
  setRunning(true);
  setInflaterStatus("Inflating...");
  try {
    const result = await fullInflate(spec, {
      targetRmsPctByLevel,
      gtol,
      onRecord: (record: LevelRecord) =>
        setInflaterStatus(`Level ${record.level}: ${record.state.replace("_", " ")} after ${record.steps} steps.`),
      onTopology: (level, faces, faceOfFine, faceEdgeIds, outlineEdgeIds) =>
        topologies.set(level, { faces, faceOfFine, faceEdgeIds, outlineEdgeIds }),
      onLevelResult: (level, positions) => {
        const topo = topologies.get(level);
        if (!topo) return;
        shown = { spec, topo, positions };
        draw(shown);
      },
      shouldStop: () => stopRequested,
    });
    setInflaterStatus(
      `Done. RMS stretch ${result.rmsStretchPct.toFixed(1)}%, pressure ${result.pressure.toFixed(2)}.`,
      "success",
    );
  } catch (err) {
    console.error(err);
    // A run that failed or was stopped never shows a half-solved level: put back what was on screen.
    shown = before;
    if (shown) draw(shown);
    else viewer.clear();
    const message = err instanceof Error ? err.message : String(err);
    if (stopRequested) setInflaterStatus("Stopped. The previous view is restored.");
    else setInflaterStatus(`Failed: ${message} The previous view is restored.`, "error");
  } finally {
    running = false;
    setRunning(false);
  }
}

inflateBtn.addEventListener("click", () => {
  if (INFLATE_ENABLED) void inflate();
});

refresh();
revealPage();
