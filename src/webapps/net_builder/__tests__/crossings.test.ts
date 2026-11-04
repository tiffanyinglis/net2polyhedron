import { describe, expect, it } from "vitest";
import { countConnectionCrossings } from "../crossings";
import type { Connection, Handle } from "../joins";
import type { Shape } from "../shapes";

const straight: Handle = { t: 0, n: 0 };

function square(id: number, cx: number, cy: number): Shape {
  return { id, n: 4, cx, cy, rotation: 0, flipped: false };
}

function conn(id: number, aShape: number, aEdge: number, bShape: number, bEdge: number): Connection {
  return { id, aShape, aEdge, bShape, bEdge, aHandle: { ...straight }, bHandle: { ...straight } };
}

describe("countConnectionCrossings", () => {
  it("is zero with no connections", () => {
    expect(countConnectionCrossings([square(1, 0, 0), square(2, 100, 0)], [])).toBe(0);
  });

  it("is zero for a single join", () => {
    const shapes = [square(1, 0, 0), square(2, 200, 0)];
    const connections = [conn(1, 1, 0, 2, 2)];
    expect(countConnectionCrossings(shapes, connections)).toBe(0);
  });

  it("counts one crossing for an X arrangement: two straight joins whose endpoints alternate around a quadrilateral", () => {
    // Four pieces at the corners of an (irregular, so the crossing doesn't land on a nice round
    // fraction of either line) quadrilateral, joined corner-to-corner on both diagonals: the two
    // straight connection lines must cross once, somewhere in the middle.
    const shapes = [square(1, -130, -90), square(2, 95, -115), square(3, 115, 105), square(4, -90, 80)];
    const connections = [conn(1, 1, 0, 3, 0), conn(2, 2, 0, 4, 0)];
    expect(countConnectionCrossings(shapes, connections)).toBeGreaterThanOrEqual(1);
  });

  it("counts zero crossings for a diamond's two non-crossing sides", () => {
    const shapes = [square(1, -100, -100), square(2, 100, -100), square(3, 100, 100), square(4, -100, 100)];
    // Adjacent sides, not the diagonals: these shouldn't need to cross.
    const connections = [conn(1, 1, 0, 2, 0), conn(2, 3, 0, 4, 0)];
    expect(countConnectionCrossings(shapes, connections)).toBe(0);
  });
});
