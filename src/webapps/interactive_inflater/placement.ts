/**
 * Which pieces the solver inflates, and where the rest go. Mirrors the Python app's junction and
 * terminal nodes: a piece with two or more connections is a JUNCTION, and only junctions are
 * inflated. A piece with one connection (a TERMINAL) is left out of the solve and laid flat after
 * it, in the plane of the junction it hangs from, on the outside of the shared edge
 * (flat_face_attacher.reattach_pendant_faces).
 *
 * With fewer than two junctions there is nothing to inflate: the seed piece (the lone junction, or
 * the owner) is laid flat in the plane z = 0 and everything else attaches to it. A self-joined
 * (folded) piece always goes to the solver, since it has no single flat face to lay down.
 *
 * Everything here is pure geometry and ids. The full net's vertex ids are the ids the solver uses
 * for the junction pieces, so a junction's solved positions can be looked up directly.
 */
import { shapeVertices, type Shape } from "../net_builder/shapes";
import { type Connection } from "../net_builder/joins";
import { loadNet, type NetSpec } from "../utils/physics/mesh";
import { fanLevel0To1 } from "../utils/physics/meshLevels";
import { type Vec3 } from "../utils/physics/vec3";
import { netSpecFromBuilder } from "./bridge";
import { type LevelTopology } from "../utils/inflaterRun";

/** One piece laid out without the solver, with the full-net ids of its corners. */
export interface FlatPiece {
  shape: Shape;
  /** Full-net vertex id of each corner, in the builder's corner order. */
  cornerIds: number[];
  /** Index of the piece's face in the full net. */
  fullFace: number;
  /** The junction piece it hangs from; null for the seed. */
  neighbour: number | null;
  /** The piece's own fan (corners 0..n-1, centroid n), with its base edges as ids 0..n-1. */
  fan: ReturnType<typeof fanLevel0To1>;
}

export interface Placement {
  /** The active group's pieces (builder order). */
  shapes: Shape[];
  /** The whole active group, as one spec: used for colours and for each face's source piece. */
  full: NetSpec;
  /** The junction pieces only, as the solver's spec. Null when there is no solve. */
  solve: NetSpec | null;
  /** Solver face index -> full-net face index. */
  solveToFull: number[];
  /** Pieces laid flat around the solve: the terminals, or the seed and the terminals when there is no solve. */
  flats: FlatPiece[];
  /** Positions of the seed's corners when there is no solve (keyed by full-net vertex id); null otherwise. */
  seedPositions: Map<number, Vec3> | null;
  /**
   * Each junction corner's solver vertex id, keyed by its slot "shapeId:corner" (the Python app's
   * atomic slots). Diff Inflate matches a new solve to the old one through these. Null when a folded
   * junction makes a corner's vertex ambiguous.
   */
  slots: Map<string, number> | null;
}

/** An empty topology for a level with no solved mesh (no solve: only the flat seed is drawn). */
export const NO_SOLVE_TOPOLOGY: LevelTopology = {
  faces: [],
  faceOfFine: [],
  faceEdgeIds: [],
  outlineEdgeIds: new Set(),
};

/** Splits the active group into junctions and terminals, and works out how each is laid out. Throws if the net isn't a valid mesh. */
export function planPlacement(shapes: Shape[], connections: Connection[], ownerId: number | null): Placement {
  const full = netSpecFromBuilder(shapes, connections, "net");
  const degree = new Map(shapes.map((s) => [s.id, 0]));
  for (const c of connections) {
    degree.set(c.aShape, degree.get(c.aShape)! + 1);
    degree.set(c.bShape, degree.get(c.bShape)! + 1);
  }
  const junctionIds = shapes.filter((s) => degree.get(s.id)! >= 2).map((s) => s.id);
  const folded = new Set(connections.filter((c) => c.aShape === c.bShape).map((c) => c.aShape));
  const solved = junctionIds.length >= 2 || junctionIds.some((id) => folded.has(id));
  const solveIds = solved ? junctionIds : [];

  const solveToFull = full.faces
    .map((_, f) => f)
    .filter((f) => solveIds.includes(full.source_polygon_id![f]));
  // Dropping the terminals leaves gaps in the edge numbering, and the solver wants ids 0..k-1. Renumber
  // in order of first use, so an edge both junction faces share keeps one shared id.
  const edgeNumber = new Map<number, number>();
  const renumbered = (ids: number[]) =>
    ids.map((e) => {
      if (!edgeNumber.has(e)) edgeNumber.set(e, edgeNumber.size);
      return edgeNumber.get(e)!;
    });
  const solve: NetSpec | null = solved
    ? {
        name: "junctions",
        faces: solveToFull.map((f) => full.faces[f]),
        face_edge_ids: solveToFull.map((f) => renumbered(full.face_edge_ids![f])),
        source_polygon_id: solveToFull.map((f) => full.source_polygon_id![f]),
        net_layout: full.net_layout,
      }
    : null;

  // With no solve, the seed is the lone junction if there is one, else the owner.
  const seedId = solved ? null : (junctionIds[0] ?? ownerId);
  const flatShapes = shapes.filter((s) => !solveIds.includes(s.id));
  const flats = flatShapes.map((shape) => {
    const neighbour =
      shape.id === seedId
        ? null
        : connections
            .filter((c) => c.aShape === shape.id || c.bShape === shape.id)
            .map((c) => (c.aShape === shape.id ? c.bShape : c.aShape))[0] ?? null;
    return flatPiece(shape, full, neighbour);
  });

  const seed = flats.find((f) => f.neighbour === null) ?? null;
  return {
    shapes,
    full,
    solve,
    solveToFull,
    flats,
    seedPositions: solved || !seed ? null : seedPositions(seed),
    // A self-joined (folded) piece is always a Full Inflate, never a Diff: its fan of triangles distorts far
    // too much for a diff to start from, so it gets no slots, which makes every edit involving it a full solve.
    slots: solve && folded.size === 0 ? junctionSlots(shapes, solve, solveToFull, full) : null,
  };
}

/**
 * Each junction corner's vertex id in the solve, by slot. Null if a junction piece's faces don't match its
 * corners. (Folded pieces never reach this: planPlacement gives them no slots, so they are always full solves.)
 */
function junctionSlots(shapes: Shape[], solve: NetSpec, solveToFull: number[], full: NetSpec): Map<string, number> | null {
  const slots = new Map<string, number>();
  const facesOf = new Map<number, number[]>();
  solveToFull.forEach((_, k) => {
    const shapeId = full.source_polygon_id![solveToFull[k]];
    facesOf.set(shapeId, [...(facesOf.get(shapeId) ?? []), k]);
  });
  for (const [shapeId, faces] of facesOf) {
    const shape = shapes.find((s) => s.id === shapeId)!;
    if (faces.length === 1 && solve.faces[faces[0]].length === shape.n) {
      // Loop position p reads corner order[p]: a flipped piece's loop runs in reverse (netExport's faceCornerOrder).
      solve.faces[faces[0]].forEach((vertex, p) => {
        const corner = shape.flipped ? shape.n - 1 - p : p;
        slots.set(`${shapeId}:${corner}`, vertex);
      });
    } else {
      return null;
    }
  }
  return slots;
}

/** The piece's own face in the full net, its corner ids, and its fan. */
function flatPiece(shape: Shape, full: NetSpec, neighbour: number | null): FlatPiece {
  const n = shape.n;
  const fullFace = full.faces.findIndex((face, f) => full.source_polygon_id![f] === shape.id && face.length === n);
  if (fullFace < 0) throw new Error(`piece ${shape.id} has no face in the net`);
  const loop = full.faces[fullFace];
  // Loop position p runs corner order[p]; a flipped piece's loop is read in reverse (netExport's faceCornerOrder).
  const cornerIds = Array.from({ length: n }, (_, k) => loop[shape.flipped ? n - 1 - k : k]);
  const own = loadNet({
    faces: [Array.from({ length: n }, (_, k) => k)],
    face_edge_ids: [Array.from({ length: n }, (_, k) => k)],
  });
  return { shape, cornerIds, fullFace, neighbour, fan: fanLevel0To1(own) };
}

/**
 * A piece's own corners as full-net vertex ids, in the builder's corner order (null for a folded piece,
 * whose corners don't sit on one face). A flipped piece's loop runs in reverse, as in flatPiece.
 */
export function cornerIdsOf(full: NetSpec, shape: Shape): number[] | null {
  const n = shape.n;
  const fullFace = full.faces.findIndex((face, f) => full.source_polygon_id![f] === shape.id && face.length === n);
  if (fullFace < 0) return null;
  const loop = full.faces[fullFace];
  return Array.from({ length: n }, (_, k) => loop[shape.flipped ? n - 1 - k : k]);
}

/** A lone piece's corners, scaled so one edge is unit length (as the solver's output is), in the plane z = 0. */
function seedPositions(seed: FlatPiece): Map<number, Vec3> {
  const corners = shapeVertices(seed.shape);
  const [[x0, y0], [x1, y1]] = corners;
  const scale = 1 / Math.hypot(x1 - x0, y1 - y0);
  return new Map(seed.cornerIds.map((id, k) => [id, [corners[k][0] * scale, corners[k][1] * scale, 0]]));
}

/** Newell normal of a polygon given by its 3D points (unnormalised). */
function newellNormal(points: Vec3[]): Vec3 {
  const n: Vec3 = [0, 0, 0];
  points.forEach((p, i) => {
    const q = points[(i + 1) % points.length];
    n[0] += (p[1] - q[1]) * (p[2] + q[2]);
    n[1] += (p[2] - q[2]) * (p[0] + q[0]);
    n[2] += (p[0] - q[0]) * (p[1] + q[1]);
  });
  return n;
}

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: Vec3, b: Vec3): Vec3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const scaleBy = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k];
const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const norm = (a: Vec3) => Math.hypot(a[0], a[1], a[2]);
const unit = (a: Vec3): Vec3 => scaleBy(a, 1 / norm(a));

/**
 * Places a terminal's corners that aren't shared with its neighbour, given the neighbour's solved
 * positions. It lies in the neighbour's plane, on the far side of the shared edge, and keeps its own
 * 2D shape, scaled to the solved edge length. Returns the new corner positions by corner index.
 */
export function attachFlat(
  flat: Pick<FlatPiece, "shape" | "cornerIds" | "neighbour">,
  full: NetSpec,
  positions: Map<number, Vec3>,
): Map<number, Vec3> {
  const ids = flat.cornerIds;
  const neighbourFaces = full.faces.filter((_, f) => full.source_polygon_id![f] === flat.neighbour);
  const neighbourIds = new Set(neighbourFaces.flat());
  const shared = ids.map((id, k) => (neighbourIds.has(id) ? k : -1)).filter((k) => k >= 0);
  if (shared.length !== 2) throw new Error(`piece ${flat.shape.id} shares ${shared.length} corners with its neighbour, expected 2`);
  const [i, j] = shared;
  const face = neighbourFaces.find((f) => ids[i] !== undefined && f.includes(ids[i]) && f.includes(ids[j]));
  if (!face) throw new Error(`piece ${flat.shape.id}: no neighbour face holds its shared edge`);

  const corners = shapeVertices(flat.shape);
  const P = corners[i];
  const Q = corners[j];
  const A = positions.get(ids[i]);
  const B = positions.get(ids[j]);
  if (!A || !B) throw new Error(`piece ${flat.shape.id}: its shared corners are not solved`);

  // In the builder: e along P->Q, f into the piece. In the solve: u along A->B, w out of the neighbour.
  const ex = Q[0] - P[0];
  const ey = Q[1] - P[1];
  const L = Math.hypot(ex, ey);
  let fx = -ey / L;
  let fy = ex / L;
  const cx = corners.reduce((sum, [x]) => sum + x, 0) / corners.length - P[0];
  const cy = corners.reduce((sum, [, y]) => sum + y, 0) / corners.length - P[1];
  if (cx * fx + cy * fy < 0) {
    fx = -fx;
    fy = -fy;
  }
  const m = norm(sub(B, A));
  const u = unit(sub(B, A));
  const facePoints = face.map((id) => positions.get(id)!);
  const faceCentre = scaleBy(facePoints.reduce((s, p) => add(s, p), [0, 0, 0] as Vec3), 1 / facePoints.length);
  let w = unit(cross(newellNormal(facePoints), u));
  if (dot(sub(faceCentre, A), w) > 0) w = scaleBy(w, -1);

  const placed = new Map<number, Vec3>();
  corners.forEach(([x, y], k) => {
    if (k === i || k === j) return;
    const dx = x - P[0];
    const dy = y - P[1];
    // e is unnormalised (length L), so this projection is divided by L twice: once for e, once for the unit of L.
    const s = (dx * ex + dy * ey) / (L * L);
    const t = (dx * fx + dy * fy) / L;
    placed.set(k, add(A, add(scaleBy(u, s * m), scaleBy(w, t * m))));
  });
  return placed;
}

/**
 * The actual path of one edge of a piece (corner e to corner e+1) through the display's subdivisions:
 * the walk along the piece's own outline edges from one corner to the other. Falls back to the straight
 * chord if the outline can't be walked. `sourceOf` is the full net's source piece per face.
 */
export function edgePath(display: Display, sourceOf: number[], shapeId: number, corners: number[], e: number): Vec3[] {
  const n = corners.length;
  const a = corners[e];
  const b = corners[(e + 1) % n];
  const chord = () => [display.positions.get(a)!, display.positions.get(b)!];
  const adj = new Map<number, number[]>();
  const outline = display.outlineEdgeIds;
  display.faces.forEach((face, f) => {
    if (sourceOf[display.faceOfFine[f]] !== shapeId) return;
    face.forEach((u, i) => {
      if (!outline.has(display.faceEdgeIds[f][i])) return;
      const v = face[(i + 1) % face.length];
      (adj.get(u) ?? adj.set(u, []).get(u)!).push(v);
      (adj.get(v) ?? adj.set(v, []).get(v)!).push(u);
    });
  });
  // Walk the outline both ways from corner a until b. The edge is the shorter way round: the polygon's
  // other edges all lie on the longer one.
  const walk = (start: number): number[] | null => {
    const path = [a, start];
    let prev = a;
    let cur = start;
    for (let guard = 0; cur !== b && guard < 100000; guard++) {
      const next = (adj.get(cur) ?? []).find((w) => w !== prev);
      if (next === undefined) return null;
      path.push(next);
      prev = cur;
      cur = next;
    }
    return cur === b ? path : null;
  };
  const candidates = (adj.get(a) ?? []).map(walk).filter((p): p is number[] => p !== null);
  if (!candidates.length) return chord();
  const shortest = candidates.reduce((best, p) => (p.length < best.length ? p : best));
  return shortest.map((id) => display.positions.get(id)!);
}

/** One mesh for the Viewer: the solved junctions and every flat piece, colours indexed by full-net face. */
export interface Display {
  /** Each piece's corner vertex ids in this display, by piece id (only pieces with a single face). */
  corners: Map<number, number[]>;
  faces: number[][];
  faceEdgeIds: number[][];
  positions: Map<number, Vec3>;
  faceOfFine: number[];
  outlineEdgeIds: Set<number>;
}

/** The largest value in `values`, or -1 when there are none (no spread, so a big mesh can't overflow the stack). */
function maxOf(values: Iterable<number>): number {
  let best = -1;
  for (const v of values) if (v > best) best = v;
  return best;
}

/**
 * Builds what a level shows: the solved junction mesh (`topo`, with `positions`) plus each flat piece.
 * A terminal's shared corners keep the junction's ids; its other corners and its fan get fresh ids,
 * so they can't clash with the solver's own subdivision ids.
 */
export function buildDisplay(plan: Placement, topo: LevelTopology, positions: Map<number, Vec3>): Display {
  const pos = new Map(positions);
  const faces: number[][] = [];
  const faceEdgeIds: number[][] = [];
  const faceOfFine: number[] = [];
  const outlineEdgeIds = new Set<number>();
  let nextVertex = Math.max(maxOf(pos.keys()), maxOf(topo.faces.flat())) + 1;
  let nextEdge = Math.max(maxOf(topo.faceEdgeIds.flat()), maxOf(topo.outlineEdgeIds)) + 1;

  topo.faces.forEach((face, f) => {
    faces.push(face);
    faceEdgeIds.push(topo.faceEdgeIds[f]);
    faceOfFine.push(plan.solveToFull[topo.faceOfFine[f]]);
  });
  for (const e of topo.outlineEdgeIds) outlineEdgeIds.add(e);

  const corners = new Map<number, number[]>();
  for (const flat of plan.flats) {
    const n = flat.shape.n;
    const ids = [...flat.cornerIds];
    if (flat.neighbour !== null) {
      for (const [k, p] of attachFlat(flat, plan.full, positions)) {
        ids[k] = nextVertex;
        pos.set(nextVertex++, p);
      }
    }
    corners.set(flat.shape.id, ids);
    // The fan's centroid: the average of this piece's corners.
    const centre = scaleBy(ids.reduce((s, id) => add(s, pos.get(id)!), [0, 0, 0] as Vec3), 1 / n);
    const centroid = nextVertex++;
    pos.set(centroid, centre);

    const vertexOf = (v: number) => (v < n ? ids[v] : centroid);
    const edgeBase = nextEdge;
    flat.fan.mesh.faces.forEach((face, f) => {
      faces.push(face.map(vertexOf));
      faceEdgeIds.push(flat.fan.mesh.faceEdgeIds[f].map((e) => edgeBase + e));
      faceOfFine.push(flat.fullFace);
    });
    for (let k = 0; k < n; k++) outlineEdgeIds.add(edgeBase + k);
    nextEdge += flat.fan.mesh.edgeEnds.length;
  }
  if (plan.solve) {
    for (const shape of plan.shapes) {
      if (corners.has(shape.id)) continue;
      const ids = cornerIdsOf(plan.full, shape);
      if (ids) corners.set(shape.id, ids);
    }
  }
  return { corners, faces, faceEdgeIds, positions: pos, faceOfFine, outlineEdgeIds };
}

/**
 * The junction pieces' own structure (their faces and joins). A change to it is what the Python app
 * calls a change to the insiders: it decides between a Full and a Diff Inflate. A terminal-only change
 * leaves it alone. Null when there is no solve.
 */
export function junctionKey(plan: Placement): string | null {
  const solve = plan.solve;
  if (!solve) return null;
  return JSON.stringify({ faces: solve.faces, face_edge_ids: solve.face_edge_ids, source_polygon_id: solve.source_polygon_id });
}
