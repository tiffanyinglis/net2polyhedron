import { displayColors, fitMultiColors, randomFaceColors, type ColorMode, type ColorState } from "../utils/colors";
import { copyCamera, copyColors, copyEdit, sameCamera, sameColors, UndoStack, type EditSnapshot } from "./editState";
import { loadNet } from "../utils/physics/mesh";
import { parseSession, restoreLevel, serializeSession, type SessionData } from "../utils/session";
import { SharedCamera, Viewer, type CameraHooks, type CameraState } from "./viewer";

const LEVELS = [0, 1, 2, 3];
/** How long a file may take to load before the spinner appears. */
const SPINNER_DELAY_MS = 150;

/** Resolves once the browser has painted the frame that was pending. */
function nextPaint(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 0)));
}
export const VIEWER_NEEDS_DEV_SERVER = "The Viewer needs the dev server (npm run dev) to read data/outputs/.";

/** One saved .hippo session as the Viewer holds it: its own live camera and Colour state, plus the on-disk copy to compare against. */
interface ViewedFile {
  name: string;
  data: SessionData;
  baseFaces: number[][];
  camera: CameraState;
  colors: ColorState;
  saved: EditSnapshot;
}

/** What the Viewer reports back to its owner. */
export interface ViewerHost {
  /** Something the user can see (camera, colours, dirty state, or the file on screen) changed. */
  onChange(): void;
  onError(message: string): void;
}

/**
 * View > Viewer: browses every .hippo session in data/outputs/, four levels at once in a 2x2 grid,
 * all sharing one camera per file. Mirrors inflate_polyhedron_app's ViewerPane: camera and Colour
 * changes are per file and undoable (one stack, reset when the file on screen changes), and nothing
 * is written back until the user saves.
 */
export class ViewerPane {
  private files = new Map<string, ViewedFile>();
  private names: string[] = [];
  private index = 0;
  private viewers: Viewer[] | null = null;
  private camera = new SharedCamera();
  private history = new UndoStack<EditSnapshot>();
  private gestureStart: EditSnapshot | null = null;
  private showSeq = 0;
  private listError: string | null = null;
  private loadingTimer: number | undefined;

  private cameraHooks: CameraHooks = {
    onGestureStart: () => (this.gestureStart = this.snapshot()),
    onGestureEnd: () => {
      const start = this.gestureStart;
      this.gestureStart = null;
      // A click without any movement leaves no undo step, same as the Python app.
      if (start && !sameCamera(start.camera, this.camera.snapshot())) this.history.push(start);
      this.host.onChange();
    },
    onBeforeDiscreteEdit: () => {
      this.history.push(this.snapshot());
      this.host.onChange();
    },
  };

  constructor(
    private grid: HTMLElement[],
    private message: HTMLElement,
    private host: ViewerHost,
  ) {}

  /** Re-reads the file list. Called every time the Viewer is entered, so a session saved since then shows up. */
  async rescan() {
    const current = this.currentName();
    try {
      const res = await fetch("/api/output-names");
      if (!res.ok) throw new Error(String(res.status));
      this.names = (await res.json()) as string[];
      this.listError = null;
    } catch {
      this.names = [];
      this.listError = VIEWER_NEEDS_DEV_SERVER;
    }
    this.index = Math.max(0, this.names.indexOf(current ?? ""));
    if (this.currentName() !== current) this.history.clear();
    await this.show();
  }

  /** The file on screen, or undefined if there are none (or it hasn't finished loading yet). */
  private current(): ViewedFile | undefined {
    const name = this.currentName();
    return name === undefined ? undefined : this.files.get(name);
  }

  private currentName(): string | undefined {
    return this.names[this.index];
  }

  async show() {
    const seq = ++this.showSeq;
    const name = this.currentName();
    this.clearGrid(); // the previous file's drawings never linger while the next one loads
    this.setMessage("");
    if (name === undefined) {
      this.endLoading();
      this.setMessage(this.listError ?? "No saved sessions in data/outputs/ yet. Run All (or File > Save) creates them.");
      this.host.onChange();
      return;
    }
    this.beginLoading();
    this.setMessage(`Loading ${name}...`);
    let file: ViewedFile;
    try {
      file = await this.load(name);
    } catch (err) {
      if (seq !== this.showSeq) return;
      this.endLoading();
      this.setMessage(`Could not read ${name}: ${err instanceof Error ? err.message : String(err)}`);
      this.host.onChange();
      return;
    }
    if (seq !== this.showSeq) return; // a later navigation has taken over

    // Drawing blocks the page, so show the spinner and let it paint before the work starts.
    this.grid.forEach((el) => el.classList.add("loading"));
    await nextPaint();
    if (seq !== this.showSeq) return;
    this.ensureViewers(); // first use creates the WebGL viewers, which is slow
    this.setMessage("");
    this.camera.apply(file.camera);
    LEVELS.forEach((level) => {
      const snap = file.data.levels[level];
      if (!snap) {
        this.viewers![level].clear();
        return;
      }
      const { topology, positions } = restoreLevel(snap);
      this.viewers![level].setMesh(
        topology.faces,
        topology.faceEdgeIds,
        positions,
        topology.faceOfFine,
        this.colorsOf(file),
        topology.outlineEdgeIds,
        topology.faceUV,
      );
      this.styleViewer(this.viewers![level], file.colors.mode === "african");
    });
    this.renderAll();
    this.endLoading();
    this.host.onChange();
  }

  /** Steps to the previous (-1) or next (+1) file, wrapping around. The undo stack resets, same as the Python app. */
  async navigate(step: number) {
    if (this.names.length < 2) return;
    this.index = (this.index + step + this.names.length) % this.names.length;
    this.history.clear();
    await this.show();
  }

  /** The Colour state of the file on screen (the Colour menu acts on it while the Viewer is showing). */
  colors(): ColorState | undefined {
    return this.current()?.colors;
  }

  hasFile(): boolean {
    return this.current() !== undefined;
  }

  /** "m / n" under the grid: which file is on screen out of how many were found. */
  counterText(): string {
    return this.names.length ? `${this.index + 1} / ${this.names.length}` : "";
  }

  /** "name.hippo*" while the file on screen has unsaved changes, for the window title. */
  title(): string {
    const file = this.current();
    return file ? `${file.name}${this.isDirty(file) ? "*" : ""} -- HIPPO Viewer` : "HIPPO Viewer";
  }

  canUndo(): boolean {
    return this.history.canUndo && this.hasFile();
  }

  canRedo(): boolean {
    return this.history.canRedo && this.hasFile();
  }

  undo() {
    this.stepHistory("undo");
  }

  redo() {
    this.stepHistory("redo");
  }

  setColorMode(mode: ColorMode) {
    const file = this.current();
    if (!file || file.colors.mode === mode) return;
    this.history.push(this.snapshot());
    file.colors.mode = mode;
    fitMultiColors(file.colors, file.baseFaces);
    this.applyColors(file);
    this.host.onChange();
  }

  /** Colour > Randomize: re-rolls this file's own Multi-colour palette (Multi-colour mode only). */
  randomize() {
    const file = this.current();
    if (!file || file.colors.mode !== "multi") return;
    this.history.push(this.snapshot());
    file.colors.multiColors = randomFaceColors(file.baseFaces);
    this.applyColors(file);
    this.host.onChange();
  }

  /** Names of every file with unsaved changes (camera or Colour), for the save prompt. */
  dirtyNames(): string[] {
    return [...this.files.values()].filter((f) => this.isDirty(f)).map((f) => f.name);
  }

  /** Saves the file on screen. Ctrl+S in the Viewer, same as the Python app. */
  async saveCurrent(): Promise<boolean> {
    const file = this.current();
    return file ? this.save(file) : false;
  }

  /** Saves every dirty file, stopping at the first failure. */
  async saveAll(): Promise<boolean> {
    for (const file of [...this.files.values()].filter((f) => this.isDirty(f))) {
      if (!(await this.save(file))) return false;
    }
    return true;
  }

  private async load(name: string): Promise<ViewedFile> {
    const cached = this.files.get(name);
    if (cached) return cached;
    const res = await fetch(`../outputs/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data = parseSession(await res.text());
    const colors: ColorState = { mode: data.colorMode, multiColors: [...data.multiColors] };
    const camera: CameraState = {
      orientation: [...data.camera.orientation],
      zoom: data.camera.zoom,
      pan: [...data.camera.pan],
    };
    const baseFaces = loadNet(data.netSpec).faces;
    fitMultiColors(colors, baseFaces);
    const file: ViewedFile = {
      name,
      data,
      baseFaces,
      camera,
      colors,
      saved: copyEdit({ camera, colors }),
    };
    this.files.set(name, file);
    return file;
  }

  private async save(file: ViewedFile): Promise<boolean> {
    const data: SessionData = {
      ...file.data,
      camera: {
        orientation: [...file.camera.orientation],
        zoom: file.camera.zoom,
        pan: [...file.camera.pan],
      },
      colorMode: file.colors.mode,
      multiColors: [...file.colors.multiColors],
    };
    try {
      const res = await fetch(`/api/outputs/${encodeURIComponent(file.name)}`, {
        method: "POST",
        body: serializeSession(data),
      });
      if (!res.ok) throw new Error(`save failed: ${res.status}`);
    } catch (err) {
      this.host.onError(`Could not save ${file.name}: ${err instanceof Error ? err.message : String(err)}`);
      return false;
    }
    file.data = data;
    file.saved = copyEdit({ camera: file.camera, colors: file.colors });
    this.host.onChange();
    return true;
  }

  private isDirty(file: ViewedFile): boolean {
    return !sameCamera(file.camera, file.saved.camera) || !sameColors(file.colors, file.saved.colors);
  }

  private snapshot(): EditSnapshot {
    return { camera: this.camera.snapshot(), colors: copyColors(this.current()!.colors) };
  }

  private stepHistory(direction: "undo" | "redo") {
    const file = this.current();
    if (!file) return;
    const current = this.snapshot();
    const target = direction === "undo" ? this.history.undo(current) : this.history.redo(current);
    if (!target) return;
    file.camera = copyCamera(target.camera);
    file.colors = copyColors(target.colors);
    this.camera.apply(file.camera);
    this.applyColors(file);
    this.host.onChange();
  }

  /** Recolours all four quadrants of the file on screen, and redraws them. */
  private applyColors(file: ViewedFile) {
    if (!this.viewers) return;
    const colors = this.colorsOf(file);
    this.viewers.forEach((v) => {
      this.styleViewer(v, file.colors.mode === "african");
      v.setBaseColors(colors);
    });
    this.renderAll();
  }

  /** African Flower hides the polygon outlines (they'd read as gaps between textured polygons). The Viewer has no subdivision toggle, so subdivisions stay off. */
  private styleViewer(v: Viewer, african: boolean) {
    v.setTextured(african);
    v.setLayers(!african, false);
  }

  private colorsOf(file: ViewedFile): number[] {
    return displayColors(file.colors, file.baseFaces, file.data.netSpec);
  }

  private onCameraInput = () => {
    const file = this.current();
    if (file) file.camera = this.camera.snapshot();
    this.renderAll();
    this.host.onChange();
  };

  private ensureViewers() {
    if (this.viewers) return;
    this.viewers = this.grid.map((el) => new Viewer(el, this.camera, this.onCameraInput, this.cameraHooks));
  }

  private renderAll() {
    this.viewers?.forEach((v) => v.render());
  }

  private clearGrid() {
    this.viewers?.forEach((v) => v.clear());
  }

  /** Spinner over the grid, but only if loading takes noticeably long (a quick file never flashes it). */
  private beginLoading() {
    this.endLoading();
    this.loadingTimer = window.setTimeout(() => this.grid.forEach((el) => el.classList.add("loading")), SPINNER_DELAY_MS);
  }

  private endLoading() {
    window.clearTimeout(this.loadingTimer);
    this.grid.forEach((el) => el.classList.remove("loading"));
  }

  /** Text laid over the empty grid (no files yet, the dev server missing, an unreadable file); "" hides it. */
  private setMessage(text: string) {
    this.message.textContent = text;
    this.message.hidden = !text;
  }
}
