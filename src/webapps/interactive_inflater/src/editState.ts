import { type ColorState } from "./colors";
import { type CameraState } from "./viewer";

/** The net panel's own pan (CSS pixels) and zoom. Only the Inflater view has one. */
export interface NetView {
  pan: [number, number];
  zoom: number;
}

/** One undo/redo entry: a view's camera plus its Colour-menu state (and, in the Inflater, the net panel's view), as they were before a change. */
export interface EditSnapshot {
  camera: CameraState;
  colors: ColorState;
  net?: NetView;
}

/** Positions/rotations closer than this count as unchanged (the Python app's np.allclose tolerance, roughly). */
const SAME_EPSILON = 1e-8;

export function copyCamera(c: CameraState): CameraState {
  return { orientation: [...c.orientation], zoom: c.zoom, pan: [...c.pan] };
}

export function copyColors(c: ColorState): ColorState {
  return { mode: c.mode, multiColors: [...c.multiColors] };
}

export function copyEdit(s: EditSnapshot): EditSnapshot {
  const copy: EditSnapshot = { camera: copyCamera(s.camera), colors: copyColors(s.colors) };
  if (s.net) copy.net = { pan: [s.net.pan[0], s.net.pan[1]], zoom: s.net.zoom };
  return copy;
}

export function sameNetView(a: NetView, b: NetView): boolean {
  return (
    a.zoom === b.zoom &&
    Math.abs(a.pan[0] - b.pan[0]) <= SAME_EPSILON &&
    Math.abs(a.pan[1] - b.pan[1]) <= SAME_EPSILON
  );
}

export function sameCamera(a: CameraState, b: CameraState): boolean {
  return (
    a.zoom === b.zoom &&
    Math.abs(a.pan[0] - b.pan[0]) <= SAME_EPSILON &&
    Math.abs(a.pan[1] - b.pan[1]) <= SAME_EPSILON &&
    a.orientation.every((v, i) => Math.abs(v - b.orientation[i]) <= SAME_EPSILON)
  );
}

export function sameColors(a: ColorState, b: ColorState): boolean {
  return (
    a.mode === b.mode &&
    a.multiColors.length === b.multiColors.length &&
    a.multiColors.every((c, i) => c === b.multiColors[i])
  );
}

/**
 * A plain undo/redo stack, same rules as the Python app's: `push` records the state from BEFORE a
 * change and drops any redo history; `undo`/`redo` take the current state, hand back the one to
 * restore, and park the current state on the other stack.
 */
export class UndoStack<T> {
  private undoItems: T[] = [];
  private redoItems: T[] = [];

  get canUndo(): boolean {
    return this.undoItems.length > 0;
  }

  get canRedo(): boolean {
    return this.redoItems.length > 0;
  }

  push(before: T) {
    this.undoItems.push(before);
    this.redoItems.length = 0;
  }

  undo(current: T): T | undefined {
    if (!this.undoItems.length) return undefined;
    this.redoItems.push(current);
    return this.undoItems.pop();
  }

  redo(current: T): T | undefined {
    if (!this.redoItems.length) return undefined;
    this.undoItems.push(current);
    return this.redoItems.pop();
  }

  clear() {
    this.undoItems = [];
    this.redoItems = [];
  }
}
