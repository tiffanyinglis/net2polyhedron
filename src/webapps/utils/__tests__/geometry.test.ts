import { describe, expect, it } from "vitest";
import { pointInPolygon, rectIntersectsPolygon, regularPolygonVertices } from "../geometry";

const SQUARE = regularPolygonVertices(4, 2); // a square of side 2 centred on the origin

describe("regularPolygonVertices", () => {
  it("gives the requested edge length", () => {
    for (const k of [3, 4, 5, 8]) {
      const v = regularPolygonVertices(k, 70);
      const d = Math.hypot(v[1][0] - v[0][0], v[1][1] - v[0][1]);
      expect(d).toBeCloseTo(70, 9);
    }
  });

  it("is centred on the origin", () => {
    const v = regularPolygonVertices(6, 10);
    expect(v.reduce((s, [x]) => s + x, 0) / v.length).toBeCloseTo(0, 9);
    expect(v.reduce((s, [, y]) => s + y, 0) / v.length).toBeCloseTo(0, 9);
  });
});

describe("pointInPolygon", () => {
  it("tells inside from outside", () => {
    expect(pointInPolygon([0, 0], SQUARE)).toBe(true);
    expect(pointInPolygon([1.5, 0], SQUARE)).toBe(false);
  });
});

describe("rectIntersectsPolygon", () => {
  it("catches a rectangle that only overlaps a corner or edge", () => {
    expect(rectIntersectsPolygon(0.5, 0.5, 3, 3, SQUARE)).toBe(true); // corner overlap
    expect(rectIntersectsPolygon(-3, -0.2, 3, 0.2, SQUARE)).toBe(true); // crosses the whole square
  });

  it("rejects a rectangle clear of the polygon", () => {
    expect(rectIntersectsPolygon(5, 5, 6, 6, SQUARE)).toBe(false);
  });
});
