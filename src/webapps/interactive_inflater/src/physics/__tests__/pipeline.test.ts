import { describe, expect, it } from "vitest";
import { fullInflate } from "../pipeline";
import { loadNet } from "../mesh";

const TETRAHEDRON = { faces: [[0, 1, 2], [3, 1, 0], [0, 2, 3], [2, 1, 3]] };
const CUBE = {
  faces: [
    [0, 1, 2, 3],
    [4, 1, 0, 5],
    [5, 0, 3, 6],
    [2, 1, 4, 7],
    [3, 2, 7, 6],
    [7, 4, 5, 6],
  ],
};

describe("loadNet", () => {
  it("accepts a valid vertex-loop mesh", () => {
    expect(loadNet(TETRAHEDRON).faces).toHaveLength(4);
  });

  it("rejects a repeated directed edge", () => {
    expect(() => loadNet({ faces: [[0, 1, 2], [0, 1, 3]] })).toThrow();
  });

  it("rejects a degenerate face", () => {
    expect(() => loadNet({ faces: [[0, 1]] })).toThrow();
  });
});

describe("fullInflate", () => {
  // Regression: orientationRetry once accepted an all-inward (inside-out) Level 0, which left
  // the tetrahedron's pressure response near-flat (~2.6% RMS) and blowing up at higher pressure.
  // With the fix it lands near the target, as the Python solver does (9.7% for target 10).
  // Exact cross-language values live in pythonParity.test.ts.
  it("inflates a tetrahedron end-to-end without throwing", async () => {
    const result = await fullInflate(TETRAHEDRON, { targetRmsPct: 10 });
    expect(Number.isFinite(result.rmsStretchPct)).toBe(true);
    expect(result.rmsStretchPct).toBeGreaterThan(8);
    expect(result.rmsStretchPct).toBeLessThan(12);
    expect(result.positions.size).toBeGreaterThan(4);
    expect(result.faces.length).toBe(12); // 4 base faces, fanned into 3 triangles each
  }, 30_000);

  it("inflates a cube end-to-end without throwing", async () => {
    const result = await fullInflate(CUBE, { targetRmsPct: 10 });
    expect(Number.isFinite(result.rmsStretchPct)).toBe(true);
    expect(result.rmsStretchPct).toBeGreaterThan(0);
    expect(result.faces.length).toBe(24); // 6 base faces, fanned into 4 triangles each
  }, 30_000);
});
