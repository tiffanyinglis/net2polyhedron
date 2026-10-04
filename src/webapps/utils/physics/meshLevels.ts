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
  /** Per fine triangle: its rim edge is an open boundary edge (see fanLevel0To1). */
  faceOpen: boolean[];
  /** Per fine triangle: the texture coordinates of its three corners, as [u0, v0, u1, v1, u2, v2]. */
  faceUV: number[][];
}

/** Texture coordinates of a base polygon's corner k (of n): on the flower's edge, on its spoke. The
 * centre of the texture is the polygon's centroid, so a triangle's wedge runs from the centre out to
 * its two corners. */
function wedgeCornerUV(k: number, n: number): [number, number] {
  const a = (2 * Math.PI * k) / n;
  return [0.5 + 0.5 * Math.cos(a), 0.5 + 0.5 * Math.sin(a)];
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
  const faceOpen: boolean[] = [];
  const faceUV: number[][] = [];
  const uses = new Map<number, number>();
  for (const id of base.faceEdgeIds.flat()) uses.set(id, (uses.get(id) ?? 0) + 1);
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
      faceUV.push([...wedgeCornerUV(p, n), ...wedgeCornerUV(q, n), 0.5, 0.5]);
      faceEdgeIds.push([baseIds[p], spokeOf(q), spokeOf(p)]);
      faceOfFine.push(faceIdx);
      // A wedge is open when its own rim (base edge p) has only one face using it, as in
      // Python's _level1_is_open. Open wedges get no pressure and are left out of RMS.
      faceOpen.push(uses.get(baseIds[p]) === 1);
    }
  });
  return { mesh: { faces, faceEdgeIds, edgeEnds, restLengths }, faceOfFine, faceOpen, faceUV };
}

export interface MeshState {
  mesh: Mesh;
  positions: Map<number, Vec3>;
  faceOfFine: number[];
  faceOpen: boolean[];
  /** Per fine triangle: its corners' texture coordinates (see Level1Topology.faceUV); absent when not tracked. */
  faceUV?: number[][];
  /** Edge ids lying on an original polygon's outer boundary (see polygonOutlineEdgeIds); halves of
   * a subdivided outline edge stay in the set. */
  outlineEdgeIds: Set<number>;
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
  const outlineEdgeIds = new Set<number>();
  const halfAt = (edge: number, endpoint: number): number => {
    const key = `${edge}:${endpoint}`;
    const existing = halfOf.get(key);
    if (existing !== undefined) return existing;
    const id = addEdge(endpoint, midpoint(edge), mesh.restLengths[edge] / 2);
    if (state.outlineEdgeIds.has(edge)) outlineEdgeIds.add(id);
    halfOf.set(key, id);
    return id;
  };

  const faces: number[][] = [];
  const faceEdgeIds: number[][] = [];
  const faceOfFine: number[] = [];
  const faceUV: number[][] = [];
  const faceOpen: boolean[] = [];
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
    // Each child's texture corners are the midpoints of its parent's, so a wedge is quartered along with its triangle.
    const parentUV = state.faceUV?.[f];
    if (!parentUV) faceUV.push([], [], [], []);
    else {
      const [uvA, uvB, uvC] = [0, 1, 2].map((i) => [parentUV[2 * i], parentUV[2 * i + 1]]);
      const mid = (p: number[], q: number[]) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
      const uvAB = mid(uvA, uvB);
      const uvBC = mid(uvB, uvC);
      const uvCA = mid(uvC, uvA);
      faceUV.push(
        [...uvA, ...uvAB, ...uvCA],
        [...uvAB, ...uvB, ...uvBC],
        [...uvCA, ...uvBC, ...uvC],
        [...uvAB, ...uvBC, ...uvCA],
      );
    }
    faceEdgeIds.push(
      [halfAt(eab, a), Z, halfAt(eca, a)],
      [halfAt(eab, b), halfAt(ebc, b), X],
      [Y, halfAt(ebc, c), halfAt(eca, c)],
      [X, Y, Z],
    );
    for (let i = 0; i < 4; i++) {
      faceOfFine.push(state.faceOfFine[f]);
      faceOpen.push(state.faceOpen[f]);
    }
  });
  return {
    mesh: { faces, faceEdgeIds, edgeEnds, restLengths },
    positions,
    faceOfFine,
    faceOpen,
    faceUV,
    outlineEdgeIds,
  };
}

/** Edge ids on each original polygon's outer boundary, by id (a glued seam shares one id, so it
 * counts as outer on both of its sides). A Polygon-Fold polygon is one or more triangles fanned
 * from a centroid vertex shared by all of them, so its outer edges are the ones not touching that
 * centroid. Any other face is a whole polygon: all of its edges are outer. `groupOfBase[f]` is the
 * polygon that base face f belongs to (its source_polygon_id, or f itself). */
export function polygonOutlineEdgeIds(base: Mesh, groupOfBase: number[]): Set<number> {
  const facesOfGroup = new Map<number, number[]>();
  groupOfBase.forEach((group, f) => facesOfGroup.set(group, [...(facesOfGroup.get(group) ?? []), f]));
  const out = new Set<number>();
  for (const faces of facesOfGroup.values()) {
    if (faces.length === 1) {
      for (const id of base.faceEdgeIds[faces[0]]) out.add(id);
      continue;
    }
    let shared = new Set(base.faces[faces[0]]);
    for (const f of faces.slice(1)) shared = new Set([...shared].filter((v) => base.faces[f].includes(v)));
    const centroid = [...shared][0];
    for (const f of faces) {
      const face = base.faces[f];
      face.forEach((v, i) => {
        const w = face[(i + 1) % face.length];
        if (v !== centroid && w !== centroid) out.add(base.faceEdgeIds[f][i]);
      });
    }
  }
  return out;
}
