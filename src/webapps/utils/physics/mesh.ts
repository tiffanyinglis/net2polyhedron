import { type Vec3 } from "./vec3";
import { numpyRandom } from "./numpyRng";

/** One placed polygon of the builder's flat layout (pixels, y down; edge length 70). */
export interface NetLayoutEntry {
  shape_id?: number;
  n?: number;
  cx: number;
  cy: number;
  rotation: number;
}

/** Bezier handle offset from an edge midpoint, in builder pixels (along the edge tangent / outward normal). */
export interface BuilderHandle {
  t: number;
  n: number;
}

/** One saved bezier connection between two placed polygons' edges (interactive_builder_app's format). */
export interface BuilderConnection {
  /** Current format keys by shape_id; legacy files key by a_face/b_face (position in net_layout). */
  a_shape_id?: number;
  a_face?: number;
  a_edge: number;
  b_shape_id?: number;
  b_face?: number;
  b_edge: number;
  a_handle?: BuilderHandle;
  b_handle?: BuilderHandle;
}

export interface NetSpec {
  name?: string;
  faces: number[][];
  /** Explicit per-face edge identities, parallel to `faces` (see Mesh.faceEdgeIds). */
  face_edge_ids?: number[][];
  net_layout?: NetLayoutEntry[];
  source_polygon_id?: number[];
  /** Each source polygon's vertex ids in its net_layout corner order. */
  source_polygon?: number[][];
  builder_connections?: BuilderConnection[];
}

export const EDGE_LENGTH = 1.0;

/** A mesh whose edges have IDENTITY separate from their vertex pair, mirroring stretchy_mesh's
 * face_edge_ids. Two distinct edges can join the same two vertex ids (a self-joined polygon, e.g.
 * spider_leg's pinched legs), so every edge is referenced by id, never by its vertex pair.
 * faceEdgeIds[f][i] is the id of face f's edge faces[f][i] -> faces[f][i+1]; edgeEnds/restLengths
 * are indexed by that id. Ids not referenced by any face are harmless leftovers. */
export interface Mesh {
  faces: number[][];
  faceEdgeIds: number[][];
  edgeEnds: [number, number][];
  restLengths: number[];
}

function spokeRestLength(n: number, edgeLength: number): number {
  return edgeLength / (2 * Math.sin(Math.PI / n));
}

function hasSelfJoin(face: number[]): boolean {
  return new Set(face).size < face.length;
}

/** Builds a Mesh from vertex loops alone, identifying each edge by its undirected vertex pair
 * (every edge gets `edgeLength`). Enforces the winding check: a directed edge may appear at most
 * once. A self-joined face (repeated vertex id) is first fan-triangulated from a fresh centroid,
 * mirroring self_join_triangulator.split_self_joined_faces, with each spoke given its own id. */
export function meshFromPairs(faces: number[][], edgeLength = EDGE_LENGTH): Mesh {
  const pairIds = new Map<string, number>();
  const edgeEnds: [number, number][] = [];
  const restLengths: number[] = [];
  const pairId = (a: number, b: number): number => {
    const key = a < b ? `${a}_${b}` : `${b}_${a}`;
    let id = pairIds.get(key);
    if (id === undefined) {
      id = edgeEnds.length;
      pairIds.set(key, id);
      edgeEnds.push([Math.min(a, b), Math.max(a, b)]);
      restLengths.push(edgeLength);
    }
    return id;
  };
  const freshId = (a: number, b: number, len: number): number => {
    edgeEnds.push([a, b]);
    restLengths.push(len);
    return edgeEnds.length - 1;
  };

  let nextVertex = Math.max(...faces.flat()) + 1;
  const outFaces: number[][] = [];
  const faceEdgeIds: number[][] = [];
  for (const face of faces) {
    const n = face.length;
    if (!hasSelfJoin(face)) {
      outFaces.push(face);
      faceEdgeIds.push(face.map((v, i) => pairId(v, face[(i + 1) % n])));
      continue;
    }
    const centroid = nextVertex++;
    const spokeLen = spokeRestLength(n, edgeLength);
    const spokes = face.map((v) => freshId(centroid, v, spokeLen));
    face.forEach((v, i) => {
      const w = face[(i + 1) % n];
      outFaces.push([centroid, v, w]);
      faceEdgeIds.push([spokes[i], pairId(v, w), spokes[(i + 1) % n]]);
    });
  }
  checkDirectedEdgesUnique(outFaces, faceEdgeIds);
  return { faces: outFaces, faceEdgeIds, edgeEnds, restLengths };
}

/** Each directed edge (edge id + direction) may be used by at most one face; the edge's two
 * sides must traverse it in opposite directions. Throws otherwise. */
function checkDirectedEdgesUnique(faces: number[][], faceEdgeIds: number[][]): void {
  const counts = new Map<string, number>();
  faces.forEach((face, f) => {
    face.forEach((v, i) => {
      const w = face[(i + 1) % face.length];
      const key = `${faceEdgeIds[f][i]}:${v}->${w}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    });
  });
  const problems = [...counts.entries()].filter(([, c]) => c > 1);
  if (problems.length) {
    throw new Error(
      `not a consistently-oriented mesh:\n  ${problems
        .map(([e, c]) => `edge ${e} appears ${c} times (need exactly once)`)
        .join("\n  ")}`,
    );
  }
}

/** Loads a net file's spec into a Mesh. With explicit `face_edge_ids` (every Save from
 * interactive_builder_app writes them) those ids ARE the edge identities, so a self-joined net
 * loads as-is; without them, edges are identified by vertex pair (see meshFromPairs). */
export function loadNet(spec: NetSpec): Mesh {
  const faces = spec.faces ?? [];
  if (!faces.length) throw new Error("no faces declared");
  for (const face of faces) {
    if (face.length < 3) throw new Error(`a face needs at least 3 vertices, got ${face}`);
  }
  if (!spec.face_edge_ids) return meshFromPairs(faces);
  if (spec.face_edge_ids.length !== faces.length) {
    throw new Error(`face_edge_ids has ${spec.face_edge_ids.length} entries for ${faces.length} faces`);
  }
  const edgeEnds: [number, number][] = [];
  const restLengths: number[] = [];
  faces.forEach((face, f) => {
    face.forEach((v, i) => {
      const id = spec.face_edge_ids![f][i];
      if (edgeEnds[id] === undefined) {
        edgeEnds[id] = [v, face[(i + 1) % face.length]];
        restLengths[id] = EDGE_LENGTH;
      }
    });
  });
  for (let id = 0; id < edgeEnds.length; id++) {
    if (edgeEnds[id] === undefined) throw new Error(`face_edge_ids skips edge id ${id}`);
  }
  checkDirectedEdgesUnique(faces, spec.face_edge_ids);
  return { faces, faceEdgeIds: spec.face_edge_ids, edgeEnds, restLengths };
}

/** True if some edge has only one face using it (an open boundary net, e.g. goose or tube). */
export function isOpenMesh(mesh: Mesh): boolean {
  const uses = new Map<number, number>();
  for (const id of mesh.faceEdgeIds.flat()) uses.set(id, (uses.get(id) ?? 0) + 1);
  return [...uses.values()].some((count) => count === 1);
}

export function vertexIdsOf(faces: number[][]): number[] {
  const ids = new Set<number>();
  for (const face of faces) for (const v of face) ids.add(v);
  return [...ids].sort((a, b) => a - b);
}

/** Independent uniform-random position for every vertex `faces` references -- deliberately not a
 * meaningful embedding, just a starting cloud for relaxInitialConfiguration's spring force to
 * pull apart. Bit-compatible with stretchy_mesh.random_initial_positions: same numpy RNG
 * (numpyRng.ts), same sorted vertex order, same draws, so a seed gives the same cloud here as in
 * the Python app. */
export function randomInitialPositions(
  faces: number[][],
  spread = 5.0,
  seed = 0,
): Map<number, Vec3> {
  const rand = numpyRandom(seed);
  const positions = new Map<number, Vec3>();
  for (const v of vertexIdsOf(faces)) {
    positions.set(v, [
      -spread / 2 + spread * rand(),
      -spread / 2 + spread * rand(),
      -spread / 2 + spread * rand(),
    ]);
  }
  return positions;
}
