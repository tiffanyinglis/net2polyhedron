import { pointInPolygon, rectIntersectsPolygon, type Point } from "../utils/geometry";
import { UndoStack } from "../utils/undoStack";
import { defaultHandles, handleFromWorld, type Connection, type End } from "./joins";
import { DEFAULT_SHAPE_EDGE_LENGTH, shapeVertices, type Shape } from "./shapes";

export { DEFAULT_SHAPE_EDGE_LENGTH, POLYGON_NS, shapeCssColor, shapeVertices, type Shape } from "./shapes";

/** How far each paste moves the copied shapes, so repeated pastes cascade instead of stacking. */
export const PASTE_OFFSET = DEFAULT_SHAPE_EDGE_LENGTH * 0.4;
/** Most undo steps kept, as in the Python builder. */
const UNDO_STACK_LIMIT = 100;

/** Move edits shapes; Join edits connections. Only one is active at a time, as in the Python builder. */
export type BuilderMode = "move" | "join";

interface Snapshot {
  shapes: Shape[];
  connections: Connection[];
  nextId: number;
  nextConnectionId: number;
}

/** Plain copies of shapes and connections, safe to hold in snapshots and the clipboard. */
function copyState(shapes: Shape[], connections: Connection[]): { shapes: Shape[]; connections: Connection[] } {
  return {
    shapes: shapes.map((s) => ({ ...s })),
    connections: connections.map((c) => ({ ...c, aHandle: { ...c.aHandle }, bHandle: { ...c.bHandle } })),
  };
}

/** Whether a canvas-level point (already in world coordinates) falls on the shape. */
function shapeContains(shape: Shape, point: Point): boolean {
  return pointInPolygon(point, shapeVertices(shape));
}

/**
 * The net being built: shapes, joins, the selection, the armed palette shape, copy/paste, and undo/redo.
 * Pure model (no DOM); the canvas and page call into it.
 */
export class Builder {
  shapes: Shape[] = [];
  connections: Connection[] = [];
  mode: BuilderMode = "move";
  /** Ids of the selected shapes. A drag, rotate or delete acts on all of them. */
  selected = new Set<number>();
  /** The selected join, in Join mode, or null. */
  selectedConnection: number | null = null;
  /** The palette shape waiting to be dropped, or null. */
  armedN: number | null = null;
  private nextId = 1;
  private nextConnectionId = 1;
  private undo = new UndoStack<Snapshot>(UNDO_STACK_LIMIT);
  private clipboard: { shapes: Shape[]; connections: Connection[] } | null = null;
  /** Snapshot taken at the start of a drag, rotate or handle drag, committed to undo only if something moved. */
  private pendingGesture: Snapshot | null = null;
  /** The net as last saved or loaded, to tell whether there are unsaved changes. */
  private savedKey: string | null = Builder.stateKey([], []);

  get canUndo(): boolean {
    return this.undo.canUndo;
  }

  get canRedo(): boolean {
    return this.undo.canRedo;
  }

  get selectedShapes(): Shape[] {
    return this.shapes.filter((s) => this.selected.has(s.id));
  }

  get isDirty(): boolean {
    return Builder.stateKey(this.shapes, this.connections) !== this.savedKey;
  }

  shapeById(id: number): Shape | undefined {
    return this.shapes.find((s) => s.id === id);
  }

  /** "shape:edge" for every edge already the end of a join. An edge can be joined only once. */
  joinedEdges(): Set<string> {
    const joined = new Set<string>();
    for (const c of this.connections) {
      joined.add(`${c.aShape}:${c.aEdge}`);
      joined.add(`${c.bShape}:${c.bEdge}`);
    }
    return joined;
  }

  markSaved() {
    this.savedKey = Builder.stateKey(this.shapes, this.connections);
  }


  /**
   * Replaces the whole canvas, as File > New and File > Load do: a fresh document, so undo starts over and it
   * counts as saved.
   */
  loadShapes(shapes: Shape[], connections: Connection[] = []) {
    const copy = copyState(shapes, connections);
    this.shapes = copy.shapes;
    this.connections = copy.connections;
    this.nextId = Math.max(0, ...shapes.map((s) => s.id)) + 1;
    this.nextConnectionId = Math.max(0, ...connections.map((c) => c.id)) + 1;
    this.selected.clear();
    this.selectedConnection = null;
    this.armedN = null;
    this.undo.clear();
    this.pendingGesture = null;
    this.markSaved();
  }

  /** Switches between Move and Join. Anything that only made sense in the mode being left is cleared. */
  setMode(mode: BuilderMode) {
    if (mode === this.mode) return;
    this.mode = mode;
    this.armedN = null;
    this.selected.clear();
    this.selectedConnection = null;
  }

  /** Arms or disarms a palette shape: clicking the armed one again disarms it. Arming clears the selection. Move mode only. */
  toggleArmed(n: number) {
    if (this.mode !== "move") return;
    this.armedN = this.armedN === n ? null : n;
    if (this.armedN !== null) this.selected.clear();
  }

  /** Drops a new shape at (wx, wy), selects it, and disarms the palette. */
  drop(wx: number, wy: number) {
    if (this.armedN === null || this.mode !== "move") return;
    this.pushUndo();
    const shape: Shape = { id: this.nextId++, n: this.armedN, cx: wx, cy: wy, rotation: 0, flipped: false };
    this.shapes.push(shape);
    this.selected = new Set([shape.id]);
    this.armedN = null;
  }

  /** The topmost shape under a world point, or null. Later shapes are drawn on top, so they win. */
  hitTest(wx: number, wy: number): Shape | null {
    for (let i = this.shapes.length - 1; i >= 0; i--) {
      if (shapeContains(this.shapes[i], [wx, wy])) return this.shapes[i];
    }
    return null;
  }

  /**
   * A click on a shape: Ctrl toggles it in or out of the selection; otherwise a shape that's not already
   * selected replaces the selection, and one that is keeps the whole group selected (ready to drag).
   */
  clickShape(shape: Shape, ctrl: boolean) {
    if (ctrl) {
      if (this.selected.has(shape.id)) this.selected.delete(shape.id);
      else this.selected.add(shape.id);
    } else if (!this.selected.has(shape.id)) {
      this.selected = new Set([shape.id]);
    }
  }

  /** A click on empty space: deselects everything, unless Ctrl is held (which keeps the selection). */
  clickEmpty(ctrl: boolean) {
    if (!ctrl) this.selected.clear();
  }

  /** Marquee select: every shape the world rectangle touches. Ctrl adds them; otherwise they replace the selection. */
  marqueeSelect(x0: number, y0: number, x1: number, y1: number, additive: boolean) {
    const hits = this.shapes.filter((s) => rectIntersectsPolygon(x0, y0, x1, y1, shapeVertices(s))).map((s) => s.id);
    this.selected = additive ? new Set([...this.selected, ...hits]) : new Set(hits);
  }

  /** Selects a join (Join mode), or clears the join selection with null. */
  selectConnection(id: number | null) {
    this.selectedConnection = id;
  }

  /** Starts a drag, rotate or handle-drag gesture: remembers the current state so undo can return to it. */
  beginGesture() {
    this.pendingGesture = this.snapshot();
  }

  /** Ends a gesture: keeps it as an undo step only if the net actually changed. */
  commitGesture() {
    const start = this.pendingGesture;
    this.pendingGesture = null;
    if (start && Builder.stateKey(start.shapes, start.connections) !== Builder.stateKey(this.shapes, this.connections)) {
      this.undo.push(start);
    }
  }

  /** Moves the shapes in `starts` (id -> centre when the drag began) by the same offset. */
  dragSelection(starts: Map<number, [number, number]>, dx: number, dy: number) {
    for (const shape of this.shapes) {
      const start = starts.get(shape.id);
      if (start) {
        shape.cx = start[0] + dx;
        shape.cy = start[1] + dy;
      }
    }
  }

  /** Rotates the selection rigidly about `center`: every shape turns by `delta` and revolves around it. */
  rotateSelection(center: Point, delta: number) {
    const cos = Math.cos(delta);
    const sin = Math.sin(delta);
    for (const shape of this.selectedShapes) {
      const dx = shape.cx - center[0];
      const dy = shape.cy - center[1];
      shape.cx = center[0] + dx * cos - dy * sin;
      shape.cy = center[1] + dx * sin + dy * cos;
      shape.rotation += delta;
    }
  }

  /** Centre of the selected shapes' centres: the pivot for a group rotation. */
  selectionCentre(): Point | null {
    const shapes = this.selectedShapes;
    if (!shapes.length) return null;
    return [
      shapes.reduce((sum, s) => sum + s.cx, 0) / shapes.length,
      shapes.reduce((sum, s) => sum + s.cy, 0) / shapes.length,
    ];
  }

  /**
   * Delete: in Move mode removes every selected shape and the joins touching them; in Join mode removes the
   * selected join.
   */
  deleteSelected() {
    if (this.mode === "join") {
      if (this.selectedConnection === null) return;
      this.pushUndo();
      this.connections = this.connections.filter((c) => c.id !== this.selectedConnection);
      this.selectedConnection = null;
      return;
    }
    if (!this.selected.size) return;
    this.pushUndo();
    this.shapes = this.shapes.filter((s) => !this.selected.has(s.id));
    this.connections = this.connections.filter((c) => !this.selected.has(c.aShape) && !this.selected.has(c.bShape));
    this.selected.clear();
  }

  /** F: toggles the "flipped" side of every selected shape. */
  toggleFlipSelected() {
    if (!this.selected.size || this.mode !== "move") return;
    this.pushUndo();
    for (const shape of this.selectedShapes) shape.flipped = !shape.flipped;
  }

  /**
   * H / V: mirrors the whole selection together about the shared centre of its vertices' bounding box.
   * A mirror keeps each regular polygon's own vertex set, but reverses its handedness, so the new rotation
   * is -r for a horizontal flip and (pi - r) for a vertical one (see the Python builder's docstring).
   */
  mirrorSelection(axis: "horizontal" | "vertical") {
    const shapes = this.selectedShapes;
    if (!shapes.length || this.mode !== "move") return;
    this.pushUndo();
    const points = shapes.flatMap((s) => shapeVertices(s));
    const coord = axis === "horizontal" ? 0 : 1;
    const low = Math.min(...points.map((p) => p[coord]));
    const high = Math.max(...points.map((p) => p[coord]));
    const axisAt = (low + high) / 2;
    for (const shape of shapes) {
      if (axis === "horizontal") {
        shape.cx = 2 * axisAt - shape.cx;
        shape.rotation = -shape.rotation;
      } else {
        shape.cy = 2 * axisAt - shape.cy;
        shape.rotation = Math.PI - shape.rotation;
      }
    }
  }

  /**
   * Joins edge `aEdge` of shape `aShape` to edge `bEdge` of shape `bShape`. The two may be the same shape
   * (a Polygon Fold). Each edge can be joined only once. Returns false if the join isn't allowed.
   */
  join(aShape: number, aEdge: number, bShape: number, bEdge: number): boolean {
    if (this.mode !== "join") return false;
    if (aShape === bShape && aEdge === bEdge) return false;
    const joined = this.joinedEdges();
    if (joined.has(`${aShape}:${aEdge}`) || joined.has(`${bShape}:${bEdge}`)) return false;
    const a = this.shapeById(aShape);
    const b = this.shapeById(bShape);
    if (!a || !b) return false;
    this.pushUndo();
    const handles = defaultHandles(a, aEdge, b, bEdge);
    this.connections.push({
      id: this.nextConnectionId++,
      aShape,
      aEdge,
      bShape,
      bEdge,
      aHandle: handles.aHandle,
      bHandle: handles.bHandle,
    });
    this.selected.clear();
    this.selectedConnection = null;
    return true;
  }

  /** Moves one end of a join's bezier control point to `world`. Used live while a handle is dragged. */
  setHandle(connectionId: number, end: End, world: Point) {
    const conn = this.connections.find((c) => c.id === connectionId);
    if (!conn) return;
    const shape = this.shapeById(end === "a" ? conn.aShape : conn.bShape);
    if (!shape) return;
    const edge = end === "a" ? conn.aEdge : conn.bEdge;
    const handle = handleFromWorld(shape, edge, world);
    if (end === "a") conn.aHandle = handle;
    else conn.bHandle = handle;
  }

  /** Ctrl+C: remembers the selected shapes, and the joins between them. */
  copy() {
    if (!this.selected.size || this.mode !== "move") return;
    const shapes = this.selectedShapes;
    const connections = this.connections.filter((c) => this.selected.has(c.aShape) && this.selected.has(c.bShape));
    this.clipboard = copyState(shapes, connections);
  }

  /**
   * Ctrl+V: pastes the copied shapes and their joins, offset from the originals, and selects the new shapes.
   * Move mode only.
   */
  paste() {
    if (!this.clipboard?.shapes.length || this.mode !== "move") return;
    this.pushUndo();
    // Each paste moves the clipboard itself, so repeated pastes cascade instead of stacking.
    for (const shape of this.clipboard.shapes) {
      shape.cx += PASTE_OFFSET;
      shape.cy += PASTE_OFFSET;
    }
    const pasted = copyState(this.clipboard.shapes, this.clipboard.connections);
    const idMap = new Map<number, number>();
    for (const shape of pasted.shapes) {
      idMap.set(shape.id, this.nextId);
      shape.id = this.nextId++;
    }
    for (const c of pasted.connections) {
      c.aShape = idMap.get(c.aShape)!;
      c.bShape = idMap.get(c.bShape)!;
      c.id = this.nextConnectionId++;
    }
    this.shapes.push(...pasted.shapes);
    this.connections.push(...pasted.connections);
    this.selected = new Set(pasted.shapes.map((s) => s.id));
    this.selectedConnection = null;
  }

  undoStep() {
    const target = this.undo.undo(this.snapshot());
    if (target) this.restore(target);
  }

  redoStep() {
    const target = this.undo.redo(this.snapshot());
    if (target) this.restore(target);
  }

  private snapshot(): Snapshot {
    const copy = copyState(this.shapes, this.connections);
    return { ...copy, nextId: this.nextId, nextConnectionId: this.nextConnectionId };
  }

  private restore(snap: Snapshot) {
    const copy = copyState(snap.shapes, snap.connections);
    this.shapes = copy.shapes;
    this.connections = copy.connections;
    this.nextId = snap.nextId;
    this.nextConnectionId = snap.nextConnectionId;
    this.selected.clear();
    this.selectedConnection = null;
    this.pendingGesture = null;
  }

  /** Records the state before an instantaneous edit. */
  private pushUndo() {
    this.undo.push(this.snapshot());
  }

  private static stateKey(shapes: Shape[], connections: Connection[]): string {
    return JSON.stringify({ shapes, connections });
  }
}
