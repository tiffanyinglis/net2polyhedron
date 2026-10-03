import { describe, expect, it } from "vitest";
import { copyEdit, sameCamera, sameColors, UndoStack, type EditSnapshot } from "../editState";

const CAMERA = { orientation: [0, 0, 0, 1] as [number, number, number, number], zoom: 1, pan: [0, 0] as [number, number] };
const snap = (zoom: number, mode: "polygon" | "multi" = "polygon"): EditSnapshot => ({
  camera: { ...CAMERA, zoom },
  colors: { mode, multiColors: [1, 2] },
});

describe("UndoStack", () => {
  it("undoes to the state recorded before each change, newest first", () => {
    const stack = new UndoStack<number>();
    stack.push(1); // state before change 1
    stack.push(2); // state before change 2 (current is now 3)
    expect(stack.undo(3)).toBe(2);
    expect(stack.undo(2)).toBe(1);
    expect(stack.canUndo).toBe(false);
  });

  it("redoes what was undone, and a fresh change drops the redo history", () => {
    const stack = new UndoStack<number>();
    stack.push(1);
    expect(stack.undo(2)).toBe(1);
    expect(stack.canRedo).toBe(true);
    expect(stack.redo(1)).toBe(2);
    stack.push(1);
    expect(stack.canRedo).toBe(false);
  });

  it("does nothing when there's nothing on the stack", () => {
    const stack = new UndoStack<number>();
    expect(stack.undo(5)).toBeUndefined();
    expect(stack.redo(5)).toBeUndefined();
    expect(stack.canRedo).toBe(false);
  });

  it("clear empties both stacks", () => {
    const stack = new UndoStack<number>();
    stack.push(1);
    stack.undo(2);
    stack.clear();
    expect(stack.canUndo).toBe(false);
    expect(stack.canRedo).toBe(false);
  });
});

describe("sameCamera / sameColors", () => {
  it("treats a tiny float difference as unchanged, but a real move as changed", () => {
    expect(sameCamera(CAMERA, { ...CAMERA, pan: [1e-12, 0] })).toBe(true);
    expect(sameCamera(CAMERA, { ...CAMERA, pan: [0.1, 0] })).toBe(false);
    expect(sameCamera(CAMERA, { ...CAMERA, zoom: 1.1 })).toBe(false);
  });

  it("compares colour mode and the Multi-colour palette", () => {
    expect(sameColors({ mode: "multi", multiColors: [1, 2] }, { mode: "multi", multiColors: [1, 2] })).toBe(true);
    expect(sameColors({ mode: "multi", multiColors: [1, 2] }, { mode: "polygon", multiColors: [1, 2] })).toBe(false);
    expect(sameColors({ mode: "multi", multiColors: [1, 2] }, { mode: "multi", multiColors: [1, 3] })).toBe(false);
  });
});

describe("copyEdit", () => {
  it("copies arrays, so a later change can't rewrite a stored snapshot", () => {
    const original = snap(1);
    const copy = copyEdit(original);
    copy.camera.pan[0] = 9;
    copy.colors.multiColors[0] = 9;
    expect(original.camera.pan[0]).toBe(0);
    expect(original.colors.multiColors[0]).toBe(1);
  });
});
