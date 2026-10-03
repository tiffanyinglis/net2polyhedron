import { type Vec3 } from "./vec3";
import { edgeKey, meshEdges, vertexIdsOf } from "./mesh";

export interface EdgeSetup {
  vertexIds: number[];
  idx: Map<number, number>;
  edges: [number, number][];
  edgeA: number[];
  edgeB: number[];
  restLengths: number[];
  scale: number;
}

/** Shared setup for relaxOnce/relaxInitialConfiguration: vertex/edge index arrays plus each
 * edge's own rest length, resolved from either a uniform scalar or a per-edge map (mirrors
 * stretchy_mesh._edge_setup). */
export function edgeSetup(
  faces: number[][],
  edgeLength: number | Map<string, number>,
  explicitEdges?: [number, number][],
): EdgeSetup {
  const vertexIds = vertexIdsOf(faces);
  const idx = new Map(vertexIds.map((v, i) => [v, i]));
  const edges = explicitEdges ?? meshEdges(faces);
  const edgeA = edges.map(([a]) => idx.get(a)!);
  const edgeB = edges.map(([, b]) => idx.get(b)!);
  let restLengths: number[];
  let scale: number;
  if (typeof edgeLength === "number") {
    restLengths = edges.map(() => edgeLength);
    scale = edgeLength;
  } else {
    restLengths = edges.map(([a, b]) => {
      const len = edgeLength.get(edgeKey(a, b));
      if (len === undefined) throw new Error(`missing rest length for edge ${a}-${b}`);
      return len;
    });
    scale = restLengths.length ? Math.min(...restLengths) : 1.0;
  }
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
