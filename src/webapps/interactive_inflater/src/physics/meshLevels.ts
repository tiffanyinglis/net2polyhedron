import { type Vec3, mean } from "./vec3";
import { edgeKey } from "./mesh";

type FanEntry = [number | "C", number | "C", number | "C"];

/** Centroid-fan triangulation for n = 3..8 (mirrors utils.subdivisions.polygon_subdivisions.
 * SUBDIVISIONS), plus mesh_levels.py's own local n=3 override (_TRIANGLE_FAN): a plain triangle
 * is otherwise perfectly rigid at the vertex level, so it's fanned too, giving it the same
 * spoke-based freedom to dome under pressure that a quad/pentagon/etc. already has. */
const SUBDIVISIONS: Record<number, FanEntry[]> = {
  3: [[0, 1, "C"], [1, 2, "C"], [2, 0, "C"]],
  4: [[0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 0, "C"]],
  5: [[0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 4, "C"], [4, 0, "C"]],
  6: [[0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 4, "C"], [4, 5, "C"], [5, 0, "C"]],
  7: [[0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 4, "C"], [4, 5, "C"], [5, 6, "C"], [6, 0, "C"]],
  8: [
    [0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 4, "C"],
    [4, 5, "C"], [5, 6, "C"], [6, 7, "C"], [7, 0, "C"],
  ],
};

export function baseRestLengths(faces: number[][], edgeLength: number): Map<string, number> {
  const lengths = new Map<string, number>();
  for (const face of faces) {
    const n = face.length;
    for (let i = 0; i < n; i++) lengths.set(edgeKey(face[i], face[(i + 1) % n]), edgeLength);
  }
  return lengths;
}

function spokeRestLength(n: number, edgeLength: number): number {
  return edgeLength / (2 * Math.sin(Math.PI / n));
}

export interface Level1Topology {
  faces: number[][];
  restLengths: Map<string, number>;
  faceOfFine: number[];
}

/** Triangulates every base face via a centroid fan (mirrors mesh_levels._fan_level_0_to_1).
 * `positions` only needs to cover `faces`' own vertex ids (a dummy placeholder is fine -- see
 * mesh_topology.build_level1_topology, which only wants the faces/restLengths/faceOfFine shape
 * out of this, discarding the interpolated centroid positions since a real relax starts fresh). */
export function fanLevel0To1(
  faces: number[][],
  positions: Map<number, Vec3>,
  edgeLength: number,
): Level1Topology {
  const restLengths = baseRestLengths(faces, edgeLength);
  let nextId = Math.max(...positions.keys()) + 1;
  const newFaces: number[][] = [];
  const faceOfFine: number[] = [];
  faces.forEach((face, faceIdx) => {
    const n = face.length;
    const entries = SUBDIVISIONS[n];
    if (!entries) throw new Error(`no hardcoded subdivision for a ${n}-gon`);
    let centroidId: number | null = null;
    const spokeLen = spokeRestLength(n, edgeLength);
    for (const tri of entries) {
      const ids: number[] = [];
      for (const ref of tri) {
        if (ref === "C") {
          if (centroidId === null) {
            centroidId = nextId++;
            positions.set(centroidId, mean(face.map((v) => positions.get(v)!)));
          }
          ids.push(centroidId);
        } else {
          ids.push(face[ref]);
        }
      }
      newFaces.push(ids);
      faceOfFine.push(faceIdx);
      if (centroidId !== null) {
        for (const v of ids) {
          if (v !== centroidId) {
            const key = edgeKey(v, centroidId);
            if (!restLengths.has(key)) restLengths.set(key, spokeLen);
          }
        }
      }
    }
  });
  return { faces: newFaces, restLengths, faceOfFine };
}
