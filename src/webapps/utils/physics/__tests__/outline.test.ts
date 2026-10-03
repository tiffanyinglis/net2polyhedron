import { describe, expect, it } from "vitest";
import { polygonOutlineEdgeIds } from "../meshLevels";
import { type Mesh } from "../mesh";

// cannoli_open.poly: one hexagon, fanned from centroid vertex 2 into six triangles. Sides 0-1 and
// 1-0 are glued (both id 0), so the seam must stay on the outline.
const cannoli: Mesh = {
  faces: [[0, 1, 2], [1, 3, 2], [3, 1, 2], [1, 0, 2], [0, 4, 2], [4, 0, 2]],
  faceEdgeIds: [[0, 1, 2], [3, 4, 1], [5, 6, 4], [0, 7, 6], [8, 9, 7], [10, 2, 9]],
  edgeEnds: [],
  restLengths: [],
};

describe("polygonOutlineEdgeIds", () => {
  it("outlines a folded polygon's outer sides, including glued seams, and not its spokes", () => {
    const ids = polygonOutlineEdgeIds(cannoli, [1, 1, 1, 1, 1, 1]);
    expect([...ids].sort((a, b) => a - b)).toEqual([0, 3, 5, 8, 10]);
  });

  it("outlines every edge of an ordinary (unfolded) face", () => {
    const ids = polygonOutlineEdgeIds(
      { faces: [[0, 1, 2], [2, 3, 0]], faceEdgeIds: [[0, 1, 2], [3, 4, 5]], edgeEnds: [], restLengths: [] },
      [0, 1],
    );
    expect([...ids].sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5]);
  });
});
