import { mountAppNav, revealPage } from "../utils/appNav";
import { regularPolygonVertices } from "../utils/geometry";
import { Builder, POLYGON_NS, type BuilderMode } from "./builder";
import { BuilderCanvas } from "./canvas";
import { netFileFrom, shapesFrom } from "./netFile";
import { shapeCssColor } from "./shapes";

mountAppNav("net_builder");

/** The slice of the File System Access API used for Save (not in every TS DOM lib). */
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

const canvasEl = document.getElementById("net-canvas") as HTMLCanvasElement;
const paletteEl = document.getElementById("palette")!;
const statusEl = document.getElementById("builder-status")!;
const newItem = document.getElementById("new-item") as HTMLButtonElement;
const loadItem = document.getElementById("load-item") as HTMLButtonElement;
const saveItem = document.getElementById("save-item") as HTMLButtonElement;
const saveAsItem = document.getElementById("save-as-item") as HTMLButtonElement;
const undoItem = document.getElementById("undo-item") as HTMLButtonElement;
const redoItem = document.getElementById("redo-item") as HTMLButtonElement;
const modeButtons = [...document.querySelectorAll<HTMLButtonElement>("#toolbar [data-mode]")];
const flipH = document.getElementById("flip-h") as HTMLButtonElement;
const flipV = document.getElementById("flip-v") as HTMLButtonElement;
const netFileInput = document.getElementById("net-file") as HTMLInputElement;

const builder = new Builder();
/** The file the canvas was last loaded from or saved to, without its extension; null for an untitled net. */
let fileName: string | null = null;
/** Where Save writes, once the user has picked a file (File System Access API browsers only). */
let saveHandle: SaveHandle | null = null;
/** A result message (saved, load failed, ...) that stays on the status line until the next interaction. */
let notice: { text: string; kind: "info" | "error" | "success" } | null = null;

/** Shows a message on the status line, until the next interaction clears it. */
function setStatus(text: string, kind: "info" | "error" | "success" = "info") {
  notice = { text, kind };
  refresh(true);
}

function hintText(hasSelection: boolean): string {
  if (builder.mode === "join") {
    if (canvas.isPending) return "Click a free edge handle to join it, or press Escape to cancel.";
    if (builder.selectedConnection !== null) return "Join selected. Drag its red handles to bend it, Delete to remove.";
    return "Click an edge handle, then another free edge handle, to join them.";
  }
  if (builder.armedN !== null) return "Click the drawing area to place the shape.";
  if (hasSelection) return `${builder.selected.size} selected. Drag to move, right-drag to rotate, Delete to remove.`;
  return "Pick a shape, then click the drawing area.";
}

/**
 * Keeps the menus, palette, tools, title and status line in line with the builder. Called after every change.
 * A notice stays up until the next interaction, which calls this without `keepNotice`.
 */
function refresh(keepNotice = false) {
  if (!keepNotice) notice = null;
  undoItem.disabled = !builder.canUndo;
  redoItem.disabled = !builder.canRedo;
  const hasSelection = builder.selected.size > 0;
  flipH.disabled = !hasSelection;
  flipV.disabled = !hasSelection;
  for (const button of paletteEl.querySelectorAll<HTMLButtonElement>("button")) {
    button.classList.toggle("armed", Number(button.dataset.n) === builder.armedN);
  }
  for (const button of modeButtons) {
    const active = button.dataset.mode === builder.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  saveItem.disabled = builder.shapes.length === 0;
  saveAsItem.disabled = builder.shapes.length === 0;
  if (notice) {
    statusEl.textContent = notice.text;
    statusEl.style.color = notice.kind === "error" ? "var(--error)" : notice.kind === "success" ? "var(--success)" : "var(--info)";
  } else {
    statusEl.textContent = hintText(hasSelection);
    statusEl.style.color = "var(--info)";
  }
  canvas.redraw();
}

const canvas = new BuilderCanvas(canvasEl, builder, () => refresh());

// ---- palette ----------------------------------------------------------------------------------

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
  ctx.beginPath();
  regularPolygonVertices(n, edge).forEach(([x, y], i) => {
    const px = ICON_SIZE / 2 + x;
    const py = ICON_SIZE / 2 + y;
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
  button.type = "button";
  button.dataset.n = String(n);
  button.title = `${n}-gon`;
  button.append(drawIcon(n));
  button.addEventListener("click", () => {
    builder.toggleArmed(n);
    refresh();
  });
  paletteEl.appendChild(button);
}

// ---- tools and selection actions -----------------------------------------------------------------

function setMode(mode: BuilderMode) {
  builder.setMode(mode);
  canvas.cancelPending();
  refresh();
}

for (const button of modeButtons) {
  button.addEventListener("click", () => setMode(button.dataset.mode as BuilderMode));
}

flipH.addEventListener("click", () => {
  builder.mirrorSelection("horizontal");
  refresh();
});
flipV.addEventListener("click", () => {
  builder.mirrorSelection("vertical");
  refresh();
});

// ---- edit --------------------------------------------------------------------------------------

function undo() {
  builder.undoStep();
  refresh();
}

function redo() {
  builder.redoStep();
  refresh();
}

undoItem.addEventListener("click", undo);
redoItem.addEventListener("click", redo);

// ---- files -------------------------------------------------------------------------------------

/** Asks before throwing away unsaved work (New, Load). Returns false if the user backs out. */
function confirmDiscard(): boolean {
  return !builder.isDirty || window.confirm("Discard unsaved changes?");
}

function newNet() {
  if (!confirmDiscard()) return;
  builder.loadShapes([], []);
  fileName = null;
  saveHandle = null;
  setStatus("New net.");
}

async function loadNet(name: string, text: string) {
  try {
    const { shapes, connections, viewScale } = shapesFrom(JSON.parse(text));
    builder.loadShapes(shapes, connections);
    if (viewScale !== null) canvas.setViewScale(viewScale);
    fileName = name.replace(/\.[^.]+$/, "");
    saveHandle = null;
    setStatus(`Loaded ${name}.`, "success");
  } catch (err) {
    setStatus(`Could not load ${name}: ${err instanceof Error ? err.message : String(err)}`, "error");
  }
}


/** Writes the net. Save reuses the file it last wrote (or loaded), Save As always asks. */
async function saveNet(askForFile: boolean) {
  let text: string;
  try {
    const name = fileName ?? "net";
    text = JSON.stringify(netFileFrom(builder.shapes, builder.connections, name, canvas.viewScale), null, 2);
  } catch (err) {
    setStatus(err instanceof Error ? err.message : String(err), "error");
    return;
  }
  const suggestedName = `${fileName ?? "net"}.poly`;
  try {
    let savedName = suggestedName;
    if (askForFile || !saveHandle) {
      const picker = (window as SaveWindow).showSaveFilePicker;
      if (picker) {
        saveHandle = await picker({
          suggestedName,
          startIn: "downloads",
          types: [{ description: "Net", accept: { "application/json": [".poly"] } }],
        });
        savedName = saveHandle.name;
        const writable = await saveHandle.createWritable();
        await writable.write(text);
        await writable.close();
      } else {
        // No native save dialog here, so ask for the name, then download the file under it.
        const typed = askForFile || !fileName ? window.prompt("Save net as", suggestedName)?.trim() : suggestedName;
        if (!typed) return;
        savedName = typed.endsWith(".poly") ? typed : `${typed}.poly`;
        const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = savedName;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
      }
    } else {
      savedName = saveHandle.name;
      const writable = await saveHandle.createWritable();
      await writable.write(text);
      await writable.close();
    }
    fileName = savedName.replace(/\.[^.]+$/, "");
    builder.markSaved();
    setStatus(`Saved ${fileName}.poly.`, "success");
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return; // cancelled in the save dialog
    setStatus(`Could not save: ${err instanceof Error ? err.message : String(err)}`, "error");
  }
}

newItem.addEventListener("click", newNet);
loadItem.addEventListener("click", () => netFileInput.click());
saveItem.addEventListener("click", () => void saveNet(false));
saveAsItem.addEventListener("click", () => void saveNet(true));
netFileInput.addEventListener("change", async () => {
  const file = netFileInput.files?.[0];
  netFileInput.value = ""; // so picking the same file again still fires "change"
  if (file && confirmDiscard()) await loadNet(file.name, await file.text());
});

// ---- leaving the page ----------------------------------------------------------------------------

const leaveDialog = document.getElementById("leave-dialog") as HTMLDialogElement;

/** Asks what to do with unsaved work. Resolves to "save", "discard" or "cancel" (Escape counts as cancel). */
function askBeforeLeaving(): Promise<string> {
  return new Promise((resolve) => {
    leaveDialog.addEventListener("close", () => resolve(leaveDialog.returnValue || "cancel"), { once: true });
    leaveDialog.returnValue = "";
    leaveDialog.showModal();
  });
}

// Following a link to another app (the hamburger panel) leaves this page, so unsaved work is offered a save first.
document.addEventListener(
  "click",
  async (e) => {
    const link = (e.target as Element).closest<HTMLAnchorElement>("a.app-tab");
    if (!link || !builder.isDirty) return;
    e.preventDefault();
    const choice = await askBeforeLeaving();
    if (choice === "save") {
      await saveNet(false);
      if (builder.isDirty) return; // the save was cancelled or failed, so stay here
    } else if (choice !== "discard") {
      return;
    }
    window.location.href = link.href;
  },
  true,
);

// Closing or reloading the tab with unsaved work gets the browser's own prompt.
window.addEventListener("beforeunload", (e) => {
  if (builder.isDirty) e.preventDefault();
});

// ---- keyboard ----------------------------------------------------------------------------------

window.addEventListener("keydown", (e) => {
  const key = e.key.toLowerCase();
  if (e.ctrlKey || e.metaKey) {
    if (key === "z") undo();
    else if (key === "y") redo();
    else if (key === "c") builder.copy();
    else if (key === "v") {
      builder.paste();
      refresh();
    } else if (key === "s") {
      e.preventDefault();
      void saveNet(false);
    }
    return;
  }
  if (e.altKey) return;
  if (key === "delete" || key === "backspace") {
    builder.deleteSelected();
  } else if (key === "m") {
    setMode("move");
  } else if (key === "j") {
    setMode("join");
  } else if (key === "f") {
    builder.toggleFlipSelected();
  } else if (key === "h") {
    builder.mirrorSelection("horizontal");
  } else if (key === "v") {
    builder.mirrorSelection("vertical");
  } else if (key === "escape") {
    builder.armedN = null;
    canvas.cancelPending();
  } else {
    return;
  }
  e.preventDefault();
  refresh();
});

// Initial state: an untitled, empty net.
builder.loadShapes([], []);
refresh();
revealPage();
