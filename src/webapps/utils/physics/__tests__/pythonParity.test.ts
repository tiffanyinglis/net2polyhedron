import { describe, expect, it } from "vitest";
import { type Vec3 } from "../vec3";
import { totalRestArea } from "../forces";
import { removeRigidMotion } from "../kabsch";
import { relaxOnce } from "../relaxOnce";
import { relaxInitialConfiguration } from "../relaxInitial";
import { estimatePressureForTargetStretch } from "../pressureCalibration";
import { fanLevel0To1 } from "../meshLevels";
import { EDGE_LENGTH, type Mesh, meshFromPairs } from "../mesh";
import { mean } from "../vec3";

/** Rest length of the (single) edge joining vertices a and b. */
function restBetween(mesh: Mesh, a: number, b: number): number {
  const id = mesh.edgeEnds.findIndex(([x, y]) => (x === a && y === b) || (x === b && y === a));
  return mesh.restLengths[id];
}

/**
 * Cross-language parity tests: every input here is FIXED (no RNG anywhere), and every expected
 * value was computed directly from the real Python implementation -- see
 * tests/unit/inflate_polyhedron/test_web_port_reference_values.py in the main project, which
 * pins the exact same inputs/outputs on the Python side. Because every function under test is
 * pure given its inputs, a fixed input must produce the same output in both languages -- unlike
 * a random-seeded comparison, which can never agree across two uncorrelated RNGs (numpy vs this
 * module's own mulberry32). This is the strongest correctness check in this test suite: it
 * caught a real bug (totalRestArea assuming every face was a regular polygon) before any of
 * these existed.
 */

const RIGID_TETRAHEDRON_VERTICES: Vec3[] = [
  [1, 1, 1],
  [1, -1, -1],
  [-1, 1, -1],
  [-1, -1, 1],
];
const RIGID_TETRAHEDRON_FACES = [[2, 0, 1], [3, 0, 2], [2, 1, 3], [1, 0, 3]];

function dist(a: Vec3, b: Vec3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

function unitEdgeTetrahedron(): Map<number, Vec3> {
  const edgeLen = dist(
    RIGID_TETRAHEDRON_VERTICES[RIGID_TETRAHEDRON_FACES[0][0]],
    RIGID_TETRAHEDRON_VERTICES[RIGID_TETRAHEDRON_FACES[0][1]],
  );
  return new Map(RIGID_TETRAHEDRON_VERTICES.map((v, i) => [i, v.map((x) => x / edgeLen) as Vec3]));
}

describe("fanLevel0To1 (single triangle)", () => {
  it("matches Python's fan_level_0_to_1 exactly", () => {
    const topo = fanLevel0To1(meshFromPairs([[0, 1, 2]], EDGE_LENGTH));

    expect(topo.mesh.faces).toEqual([[0, 1, 3], [1, 2, 3], [2, 0, 3]]);
    expect(topo.faceOfFine).toEqual([0, 0, 0]);
    expect(restBetween(topo.mesh, 0, 1)).toBeCloseTo(1.0, 9);
    expect(restBetween(topo.mesh, 0, 2)).toBeCloseTo(1.0, 9);
    expect(restBetween(topo.mesh, 1, 2)).toBeCloseTo(1.0, 9);
    expect(restBetween(topo.mesh, 0, 3)).toBeCloseTo(0.5773502691896258, 9);
    expect(restBetween(topo.mesh, 1, 3)).toBeCloseTo(0.5773502691896258, 9);
    expect(restBetween(topo.mesh, 2, 3)).toBeCloseTo(0.5773502691896258, 9);
  });
});

describe("totalRestArea (dict branch)", () => {
  it("matches the original unfanned triangle's closed-form area", () => {
    const topo = fanLevel0To1(meshFromPairs([[0, 1, 2]], EDGE_LENGTH));
    const area = totalRestArea(topo.mesh);
    expect(area).toBeCloseTo(0.43301270189221913, 9);
  });
});

describe("removeRigidMotion", () => {
  it("recovers a known rotation and translation", () => {
    const before: Vec3[] = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]];
    const theta = 0.4;
    const c = Math.cos(theta);
    const s = Math.sin(theta);
    const rotate = (p: Vec3): Vec3 => [c * p[0] - s * p[1], s * p[0] + c * p[1], p[2]];
    const translation: Vec3 = [2.0, -1.0, 0.5];
    const after: Vec3[] = before.map((p) => {
      const r = rotate(p);
      return [r[0] + translation[0], r[1] + translation[1], r[2] + translation[2]];
    });

    const realigned = removeRigidMotion(before, after);
    realigned.forEach((p, i) => {
      expect(p[0]).toBeCloseTo(before[i][0], 8);
      expect(p[1]).toBeCloseTo(before[i][1], 8);
      expect(p[2]).toBeCloseTo(before[i][2], 8);
    });
  });
});

describe("relaxOnce (fixed unit tetrahedron)", () => {
  it("matches Python's relax_once reference to high precision", async () => {
    const positions = unitEdgeTetrahedron();
    const result = await relaxOnce(positions, meshFromPairs(RIGID_TETRAHEDRON_FACES), 0.5, {
      maxNfev: 200,
      gtol: 1e-4,
    });

    expect(result.stepsTaken).toBe(200);
    expect(result.converged).toBe(false);
    expect(result.rmsStretchPct).toBeCloseTo(4.594339496868712, 9);
    expect(result.maxStretchPct).toBeCloseTo(result.rmsStretchPct, 9);
    expect(result.optimality).toBeCloseTo(0.0001406723434055446, 9);

    const expectedScale = 0.3697968336598191;
    for (const [, p] of result.positions) {
      expect(Math.abs(p[0])).toBeCloseTo(expectedScale, 8);
      expect(Math.abs(p[1])).toBeCloseTo(expectedScale, 8);
      expect(Math.abs(p[2])).toBeCloseTo(expectedScale, 8);
    }
  });
});

describe("relaxInitialConfiguration (fixed perturbed start)", () => {
  it("matches Python's relax_initial_configuration reference", async () => {
    const basePositions = new Map<number, Vec3>(
      RIGID_TETRAHEDRON_VERTICES.map((v, i) => [i, v]),
    );
    const topo = fanLevel0To1(meshFromPairs(RIGID_TETRAHEDRON_FACES, EDGE_LENGTH));
    // Each fan centroid sits at its own face's vertex mean (the centroid id is the 3rd entry of
    // that face's first fan triangle), added here so the perturbed start covers every vertex.
    RIGID_TETRAHEDRON_FACES.forEach((face, f) => {
      basePositions.set(topo.mesh.faces[3 * f][2], mean(face.map((v) => RIGID_TETRAHEDRON_VERTICES[v])));
    });
    const perturbed = new Map<number, Vec3>();
    for (const [v, p] of basePositions) {
      perturbed.set(v, [p[0] + 0.05 * (v % 3), p[1] - 0.03 * (v % 2), p[2] + 0.02]);
    }

    const result = await relaxInitialConfiguration(perturbed, topo.mesh, {
      maxNfev: 400,
      gtol: 1e-4,
    });

    expect(result.stepsTaken).toBe(400);
    expect(result.converged).toBe(true);
    expect(result.rmsStretchPct).toBeCloseTo(7.791307986563624, 4);
    expect(result.maxStretchPct).toBeCloseTo(9.354775223621571, 4);
  });
});

describe("estimatePressureForTargetStretch (fixed unit tetrahedron)", () => {
  it("matches Python's bracket-search reference pressure bit-for-bit", async () => {
    const positions = unitEdgeTetrahedron();
    const result = await estimatePressureForTargetStretch(positions, meshFromPairs(RIGID_TETRAHEDRON_FACES), {
      targetRmsPct: 5.0,
      maxNfevPerTrial: 2000,
    });

    expect(result.pressureFound).toBe(true);
    expect(result.converged).toBe(true);
    expect(result.stepsTaken).toBe(400);
    expect(result.pressure).toBeCloseTo(0.541265877365274, 9);
    expect(result.rmsStretchPct).toBeCloseTo(4.871642155742525, 9);
    expect(result.maxStretchPct).toBeCloseTo(result.rmsStretchPct, 9);
  });
});
