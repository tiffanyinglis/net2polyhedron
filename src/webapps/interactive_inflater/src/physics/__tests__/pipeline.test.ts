import { describe, expect, it } from "vitest";
import { fullInflate } from "../pipeline";
import { loadNet } from "../mesh";
import { quarterTriangles } from "../meshLevels";

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
    const result = await fullInflate(TETRAHEDRON, { targetRmsPctByLevel: { 1: 10, 2: 10, 3: 10 } });
    expect(Number.isFinite(result.rmsStretchPct)).toBe(true);
    expect(result.rmsStretchPct).toBeGreaterThan(8);
    expect(result.rmsStretchPct).toBeLessThan(12);
    expect(result.positions.size).toBeGreaterThan(4);
    expect(result.faces.length).toBe(192); // 4 base faces fanned to 12 at Level 1, quartered twice more
  }, 120_000);

  it("inflates a cube end-to-end without throwing", async () => {
    const result = await fullInflate(CUBE, { targetRmsPctByLevel: { 1: 10, 2: 10, 3: 10 } });
    expect(Number.isFinite(result.rmsStretchPct)).toBe(true);
    expect(result.rmsStretchPct).toBeGreaterThan(0);
    expect(result.faces.length).toBe(384); // 6 base faces fanned to 24 at Level 1, quartered twice more
  }, 120_000);

  it("reports a history record for every level", async () => {
    const records = new Map<number, string>();
    await fullInflate(TETRAHEDRON, {
      onRecord: (r) => records.set(r.level, r.state),
    });
    expect([...records.keys()].sort()).toEqual([0, 1, 2, 3]);
  }, 120_000);
});

describe("quarterTriangles", () => {
  it("halves each parent edge and gives new internal edges half the opposite edge", () => {
    const restLengths = new Map([["0_1", 1], ["1_2", 1], ["0_2", 1]]);
    const positions = new Map<number, [number, number, number]>([
      [0, [0, 0, 0]],
      [1, [1, 0, 0]],
      [2, [0, 1, 0]],
    ]);
    const out = quarterTriangles({ faces: [[0, 1, 2]], positions, restLengths, faceOfFine: [0] });
    expect(out.faces).toHaveLength(4);
    expect(out.positions.get(3)).toEqual([0.5, 0, 0]);
    expect(out.restLengths.get("0_3")).toBe(0.5);
    expect(out.restLengths.get("3_4")).toBe(0.5);
    expect(out.restLengths.has("0_1")).toBe(false);
    for (const len of out.restLengths.values()) expect(len).toBe(0.5);
  });
});
