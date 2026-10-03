import { type Vec3 } from "./vec3";
import { type Mesh, vertexIdsOf } from "./mesh";

export interface EdgeSetup {
  vertexIds: number[];
  idx: Map<number, number>;
  edges: [number, number][];
  edgeA: number[];
  edgeB: number[];
  restLengths: number[];
  scale: number;
}

/** Shared setup for relaxOnce/relaxInitialConfiguration: vertex index arrays plus one spring per
 * edge id the mesh's faces actually reference, sorted by vertex pair (mirrors stretchy_mesh.
 * _edge_setup's ordering). Two distinct ids joining the same vertex pair stay two springs. */
export function edgeSetup(mesh: Mesh): EdgeSetup {
  const vertexIds = vertexIdsOf(mesh.faces);
  const idx = new Map(vertexIds.map((v, i) => [v, i]));
  const used = [...new Set(mesh.faceEdgeIds.flat())];
  const ends = (id: number): [number, number] => {
    const [a, b] = mesh.edgeEnds[id];
    return a < b ? [a, b] : [b, a];
  };
  used.sort((x, y) => {
    const [ax, bx] = ends(x);
    const [ay, by] = ends(y);
    return ax - ay || bx - by || x - y;
  });
  const edges = used.map(ends);
  const edgeA = edges.map(([a]) => idx.get(a)!);
  const edgeB = edges.map(([, b]) => idx.get(b)!);
  const restLengths = used.map((id) => mesh.restLengths[id]);
  const scale = restLengths.length ? Math.min(...restLengths) : 1.0;
  return { vertexIds, idx, edges, edgeA, edgeB, restLengths, scale };
}

export function positionsToPts(positions: Map<number, Vec3>, vertexIds: number[]): Vec3[] {
  return vertexIds.map((v) => {
    const p = positions.get(v);
    if (!p) throw new Error(`missing position for vertex ${v}`);
    return p;
  });
}

export function ptsToPositions(pts: Vec3[], vertexIds: number[]): Map<number, Vec3> {
  const positions = new Map<number, Vec3>();
  vertexIds.forEach((v, i) => positions.set(v, pts[i]));
  return positions;
}
