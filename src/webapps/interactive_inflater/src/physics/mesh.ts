import { type Vec3 } from "./vec3";

export interface NetSpec {
  faces: number[][];
}

export const EDGE_LENGTH = 1.0;

function faceEdges(face: number[]): [number, number][] {
  const k = face.length;
  return face.map((v, i) => [v, face[(i + 1) % k]] as [number, number]);
}

export function edgeKey(a: number, b: number): string {
  return a < b ? `${a}_${b}` : `${b}_${a}`;
}

/** Validates winding (mirrors stretchy_mesh._load_stretchy_mesh_spec's directed-edge check) and
 * returns the face loops unchanged. Throws if a directed edge appears more than once. */
export function loadNet(spec: NetSpec): { faces: number[][] } {
  const faces = spec.faces ?? [];
  if (!faces.length) throw new Error("no faces declared");
  for (const face of faces) {
    if (face.length < 3) throw new Error(`a face needs at least 3 vertices, got ${face}`);
  }
  const counts = new Map<string, number>();
  for (const face of faces) {
    for (const [v, w] of faceEdges(face)) {
      const key = `${v}->${w}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  const problems = [...counts.entries()].filter(([, c]) => c > 1);
  if (problems.length) {
    throw new Error(
      `not a consistently-oriented mesh:\n  ${problems
        .map(([e, c]) => `edge ${e} appears ${c} times (need exactly once)`)
        .join("\n  ")}`,
    );
  }
  return { faces };
}

/** Undirected edges (a, b) with a < b, deduplicated (mirrors stretchy_mesh.mesh_edges' plain-set
 * fallback -- fine here since we never carry an explicit "face_edge_ids" field). */
export function meshEdges(faces: number[][]): [number, number][] {
  const seen = new Map<string, [number, number]>();
  for (const face of faces) {
    for (const [v, w] of faceEdges(face)) {
      const a = Math.min(v, w);
      const b = Math.max(v, w);
      seen.set(edgeKey(a, b), [a, b]);
    }
  }
  return [...seen.values()].sort((x, y) => (x[0] - y[0]) || (x[1] - y[1]));
}

export function vertexIdsOf(faces: number[][]): number[] {
  const ids = new Set<number>();
  for (const face of faces) for (const v of face) ids.add(v);
  return [...ids].sort((a, b) => a - b);
}

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function next(): number {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Independent uniform-random position for every vertex `faces` references -- deliberately not a
 * meaningful embedding, just a starting cloud for relaxInitialConfiguration's spring force to
 * pull apart (mirrors stretchy_mesh.random_initial_positions; not bit-compatible with its numpy
 * RNG, just the same idea, since this is a from-scratch reimplementation). */
export function randomInitialPositions(
  faces: number[][],
  spread = 5.0,
  seed = 0,
): Map<number, Vec3> {
  const rand = mulberry32(seed * 2654435761 + 1);
  const positions = new Map<number, Vec3>();
  for (const v of vertexIdsOf(faces)) {
    positions.set(v, [
      (rand() - 0.5) * spread,
      (rand() - 0.5) * spread,
      (rand() - 0.5) * spread,
    ]);
  }
  return positions;
}
