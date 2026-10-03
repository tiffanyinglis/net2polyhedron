import { type ColorState } from "../utils/colors";
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

export { UndoStack } from "../utils/undoStack";
