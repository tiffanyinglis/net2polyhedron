/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import { fullInflate } from "../pipeline";
import spiderLegText from "../../../public/nets/spider_leg.poly?raw";
import cannoliOpenText from "../../../public/nets/cannoli_open.poly?raw";
import cannoliSemiclosedText from "../../../public/nets/cannoli_semiclosed.poly?raw";
import { loadNet, meshFromPairs } from "../mesh";
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
    const positions = new Map<number, [number, number, number]>([
      [0, [0, 0, 0]],
      [1, [1, 0, 0]],
      [2, [0, 1, 0]],
    ]);
    const out = quarterTriangles({ mesh: meshFromPairs([[0, 1, 2]]), positions, faceOfFine: [0], faceOpen: [false], outlineEdgeIds: new Set() });
    expect(out.mesh.faces).toHaveLength(4);
    expect(out.positions.get(3)).toEqual([0.5, 0, 0]);
    // Every edge the quartered triangle uses is half-length: halves of the three parent edges,
    // plus three internal midsegments, each half its opposite parent edge.
    const used = new Set(out.mesh.faceEdgeIds.flat());
    expect(used.size).toBe(9);
    for (const id of used) expect(out.mesh.restLengths[id]).toBe(0.5);
  });
});

describe("self-joined nets", () => {
  // A hexagon whose corner 3 is glued onto corner 1 and corner 4 onto corner 0 (a pinched leg).
  const PINCHED_HEXAGON = { faces: [[0, 1, 3, 1, 0, 4]] };

  it("splits a self-joined face instead of rejecting it", () => {
    const mesh = loadNet(PINCHED_HEXAGON);
    expect(mesh.faces).toHaveLength(6);
    expect(mesh.faces.every((f) => new Set(f).size === f.length)).toBe(true);
  });

  it("loads the shipped spider_leg net by its explicit face_edge_ids", () => {
    const spec = JSON.parse(spiderLegText);
    const mesh = loadNet(spec);
    expect(mesh.faces).toHaveLength(18);
    // Two distinct edges join vertices 1 and 2 in spider_leg: they must keep separate identities.
    const edgesBetween12 = mesh.edgeEnds.filter(([a, b]) => Math.min(a, b) === 1 && Math.max(a, b) === 2);
    expect(edgesBetween12.length).toBeGreaterThan(1);
  });
});

describe("bundled self-joined nets", () => {
  // spider_leg/cannoli carry explicit face_edge_ids, so their repeated vertex pairs stay distinct.
  it.each([
    ["spider_leg", spiderLegText],
    ["cannoli_open", cannoliOpenText],
    ["cannoli_semiclosed", cannoliSemiclosedText],
  ])("inflates %s to its target RMS stretch", async (_name, text) => {
    const result = await fullInflate(JSON.parse(text), { targetRmsPctByLevel: { 1: 10, 2: 10, 3: 10 } });
    expect(result.rmsStretchPct).toBeGreaterThan(8);
    expect(result.rmsStretchPct).toBeLessThan(12);
  }, 120_000);

  it("inflates a single pinched hexagon split from a raw self-joined face", async () => {
    const result = await fullInflate({ faces: [[0, 1, 3, 1, 0, 4]] }, { targetRmsPctByLevel: { 1: 10, 2: 10, 3: 10 } });
    expect(result.rmsStretchPct).toBeGreaterThan(8);
    expect(result.rmsStretchPct).toBeLessThan(12);
  }, 120_000);
});
