import { type Vec3 } from "./vec3";
import { EDGE_LENGTH, type Mesh } from "./mesh";
import { add, scale } from "./vec3";

type FanEntry = [number | "C", number | "C", number | "C"];

/** Centroid-fan triangulation for n = 3..8 (mirrors utils.subdivisions.polygon_subdivisions.
 * SUBDIVISIONS), plus mesh_levels.py's own local n=3 override (_TRIANGLE_FAN): a plain triangle
 * is otherwise perfectly rigid at the vertex level, so it's fanned too, giving it the same
 * spoke-based freedom to dome under pressure that a quad/pentagon/etc. already has. Every entry is
 * [i, i+1, "C"], so its base edge is face edge i. */
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

function spokeRestLength(n: number, edgeLength: number): number {
  return edgeLength / (2 * Math.sin(Math.PI / n));
}

export interface Level1Topology {
  mesh: Mesh;
  faceOfFine: number[];
}

/** Triangulates every base face via a centroid fan (mirrors mesh_levels._fan_level_0_to_1). Base
 * edges keep their ids; each face corner gets its own spoke id, so a self-joined face's two
 * spokes to the same vertex stay distinct. Centroid positions are not returned -- a real relax
 * starts fresh from random positions. */
export function fanLevel0To1(base: Mesh): Level1Topology {
  const edgeEnds = [...base.edgeEnds];
  const restLengths = [...base.restLengths];
  let nextVertex = Math.max(...base.faces.flat()) + 1;
  const faces: number[][] = [];
  const faceEdgeIds: number[][] = [];
  const faceOfFine: number[] = [];
  base.faces.forEach((face, faceIdx) => {
    const n = face.length;
    const entries = SUBDIVISIONS[n];
    if (!entries) throw new Error(`no hardcoded subdivision for a ${n}-gon`);
    const baseIds = base.faceEdgeIds[faceIdx];
    const spokeLen = spokeRestLength(n, EDGE_LENGTH);
    let centroid: number | null = null;
    const spokeIds: number[] = new Array(n);
    const spokeOf = (k: number): number => {
      if (spokeIds[k] === undefined) {
        edgeEnds.push([centroid!, face[k]]);
        restLengths.push(spokeLen);
        spokeIds[k] = edgeEnds.length - 1;
      }
      return spokeIds[k];
    };
    for (const [p, q] of entries.map((e) => [e[0], e[1]] as [number, number])) {
      if (centroid === null) centroid = nextVertex++;
      faces.push([face[p], face[q], centroid]);
      faceEdgeIds.push([baseIds[p], spokeOf(q), spokeOf(p)]);
      faceOfFine.push(faceIdx);
    }
  });
  return { mesh: { faces, faceEdgeIds, edgeEnds, restLengths }, faceOfFine };
}

export interface MeshState {
  mesh: Mesh;
  positions: Map<number, Vec3>;
  faceOfFine: number[];
}

/** Splits every triangle into 4 via edge midpoints (mirrors mesh_levels._quarter_triangles for a
 * closed mesh). Each original edge id gets one midpoint, shared by both faces that use it; its two
 * halves are fresh edge ids, each with half the rest length. Each parent triangle's three new
 * internal edges take half their opposite edge's rest length (midsegment theorem). */
export function quarterTriangles(state: MeshState): MeshState {
  const { mesh } = state;
  const positions = new Map(state.positions);
  const edgeEnds = [...mesh.edgeEnds];
  const restLengths = [...mesh.restLengths];
  let nextVertex = Math.max(...positions.keys()) + 1;
  const midpointOf = new Map<number, number>();
  const halfOf = new Map<string, number>();

  const midpoint = (edge: number): number => {
    const existing = midpointOf.get(edge);
    if (existing !== undefined) return existing;
    const [u, v] = mesh.edgeEnds[edge];
    const mid = nextVertex++;
    positions.set(mid, scale(add(positions.get(u)!, positions.get(v)!), 0.5));
    midpointOf.set(edge, mid);
    return mid;
  };
  const addEdge = (a: number, b: number, len: number): number => {
    edgeEnds.push([a, b]);
    restLengths.push(len);
    return edgeEnds.length - 1;
  };
  /** The half of `edge` running from `endpoint` to its midpoint. */
  const halfAt = (edge: number, endpoint: number): number => {
    const key = `${edge}:${endpoint}`;
    const existing = halfOf.get(key);
    if (existing !== undefined) return existing;
    const id = addEdge(endpoint, midpoint(edge), mesh.restLengths[edge] / 2);
    halfOf.set(key, id);
    return id;
  };

  const faces: number[][] = [];
  const faceEdgeIds: number[][] = [];
  const faceOfFine: number[] = [];
  mesh.faces.forEach((face, f) => {
    const [a, b, c] = face;
    const [eab, ebc, eca] = mesh.faceEdgeIds[f];
    const mab = midpoint(eab);
    const mbc = midpoint(ebc);
    const mca = midpoint(eca);
    const X = addEdge(mab, mbc, mesh.restLengths[eca] / 2);
    const Y = addEdge(mbc, mca, mesh.restLengths[eab] / 2);
    const Z = addEdge(mca, mab, mesh.restLengths[ebc] / 2);
    faces.push([a, mab, mca], [mab, b, mbc], [mca, mbc, c], [mab, mbc, mca]);
    faceEdgeIds.push(
      [halfAt(eab, a), Z, halfAt(eca, a)],
      [halfAt(eab, b), halfAt(ebc, b), X],
      [Y, halfAt(ebc, c), halfAt(eca, c)],
      [X, Y, Z],
    );
    for (let i = 0; i < 4; i++) faceOfFine.push(state.faceOfFine[f]);
  });
  return {
    mesh: { faces, faceEdgeIds, edgeEnds, restLengths },
    positions,
    faceOfFine,
  };
}
