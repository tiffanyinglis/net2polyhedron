import { describe, expect, it } from "vitest";
import { rigidTransformFrom } from "../kabsch";
import { type Vec3 } from "../vec3";

describe("rigidTransformFrom", () => {
  it("recovers a rotation and translation applied to a point set", () => {
    const before: Vec3[] = [[0, 0, 0], [1, 0, 0], [0, 2, 0], [0, 0, 3], [1, 1, 1]];
    const c = Math.cos(0.7);
    const s = Math.sin(0.7);
    const move = (p: Vec3): Vec3 => [c * p[0] - s * p[1] + 5, s * p[0] + c * p[1] - 2, p[2] + 1];
    const after = before.map(move);
    const back = rigidTransformFrom(before, after);
    before.forEach((p, i) => {
      const q = back(after[i]);
      for (let k = 0; k < 3; k++) expect(q[k]).toBeCloseTo(p[k], 6);
    });
  });
});
