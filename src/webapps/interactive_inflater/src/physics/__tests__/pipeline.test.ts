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
  // Deliberately NOT asserting an exact target match here. The stretch-vs-pressure response
  // isn't always monotonic (multi_trial_inflater.estimate_pressure_for_target_stretch's own
  // docstring documents this on the Python side too: "stretch isn't always monotonic in
  // pressure (three_squares.poly stretches LESS as pressure rises)") -- confirmed directly here:
  // at near-zero pressure this topology's own Level 0 output settles to a residual ~7% RMS
  // stretch floor (repulsion-vs-spring equilibrium, independent of pressure), dips to a local
  // minimum around pressure~1.5, then rises again toward a buckling ceiling where the plain-
  // linear-spring force law has no equilibrium at all (pressure push ~area, spring pull only
  // ~length -- physics.md's Force model section; test_stretchy_mesh.py's own
  // test_relax_once_pressure_increases_stretch_over_a_normal_working_range documents the same
  // ceiling in Python: "a range comfortably below the pressure where a plain cube stops having
  // any equilibrium at all... no runaway guard"). Which target is reachable from Level 0's own
  // random starting cloud is therefore genuinely seed-dependent in BOTH languages -- this JS
  // port uses an uncorrelated PRNG from Python's numpy, so a specific target that happens to
  // work for one seed in one language has no reason to work for an unrelated seed in the other.
  // The actual correctness check against Python lives in pythonParity.test.ts (identical fixed
  // inputs, no RNG, matching Python's reference values bit-for-bit) -- this test is just an
  // end-to-end smoke test that the full random-seeded pipeline runs to completion and produces a
  // sane, positive, finite result.
  it("inflates a tetrahedron end-to-end without throwing", async () => {
    const result = await fullInflate(TETRAHEDRON, { targetRmsPct: 10 });
    expect(Number.isFinite(result.rmsStretchPct)).toBe(true);
    expect(result.rmsStretchPct).toBeGreaterThan(0);
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
