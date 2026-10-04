import { describe, expect, it } from "vitest";
import { fullInflate } from "../../utils/physics/pipeline";
import { type Vec3 } from "../../utils/physics/vec3";
import { type NetSpec } from "../../utils/physics/mesh";
import { canDiff, diffInflate, type LastSolve } from "../diffInflate";

// A closed tetrahedron, each face its own shape with corner k at loop position k.
const TETRAHEDRON: NetSpec = {
  name: "tetrahedron",
  faces: [[0, 1, 2], [3, 1, 0], [0, 2, 3], [2, 1, 3]],
  source_polygon_id: [0, 1, 2, 3],
};

function slotsOf(spec: NetSpec): Map<string, number> {
  const slots = new Map<string, number>();
  spec.faces.forEach((face, f) => face.forEach((v, k) => slots.set(`${spec.source_polygon_id![f]}:${k}`, v)));
  return slots;
}

describe("Diff Inflate", () => {
  it("re-solves an unchanged net from its own Level-3 result and pressure", async () => {
    let level3: Map<number, Vec3> | null = null;
    let pressure: number | null = null;
    await fullInflate(TETRAHEDRON, {
      targetRmsPctByLevel: { 1: 10, 2: 10, 3: 10 },
      onRecord: (r) => {
        if (r.level === 3 && r.state !== "running") pressure = r.pressure;
      },
      onLevelResult: (level, positions) => {
        if (level === 3) level3 = positions;
      },
    });
    expect(level3).not.toBeNull();
    const slots = slotsOf(TETRAHEDRON);
    const last: LastSolve = { slots, positions: level3!, pressure: pressure!, triangles: [] };
    expect(canDiff(slots, last)).toBe(true);
    const result = await diffInflate(TETRAHEDRON, slots, last, { targetRmsPct: 10, gtol: 1e-4, shouldStop: () => false, sourceOfFace: [0, 1, 2, 3] });
    expect(result.rmsStretchPct).toBeGreaterThan(9);
    expect(result.rmsStretchPct).toBeLessThan(11);
    // Each triangle fans into 3, then two quarterings: 4 faces x 3 x 16 fine triangles.
    expect(result.topo.faces.length).toBe(TETRAHEDRON.faces.length * 3 * 16);
  }, 120_000);

  it("has nothing to diff from when no corner matches", () => {
    expect(canDiff(new Map([["9:0", 0]]), { slots: new Map([["0:0", 0]]), positions: new Map(), pressure: 1, triangles: [] })).toBe(false);
  });
});
