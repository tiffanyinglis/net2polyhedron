/**
 * Diff Inflate (the Python app's on_diff_inflate_clicked / _diff_reexport_and_relax). Instead of a
 * Full Inflate from Level 0, the new junction net starts from the last solve's Level-3 positions:
 * each corner that existed before keeps its old position (matched by its slot, shape and corner),
 * the new corners are filled in from their neighbours, the mesh is subdivided to Level 3 as pure
 * interpolation, and one pressure calibration runs there, starting from the last pressure.
 */
import { loadNet, type NetSpec } from "../utils/physics/mesh";
import { fanLevel0To1, groupingOfSpec, polygonOutlineEdgeIds, quarterTriangles, type AtlasChoice, type MeshState } from "../utils/physics/meshLevels";
import { repulsionMultipliers } from "../utils/physics/pipeline";
import { type ReplayFrame } from "../utils/physics/relaxOnce";
import { estimatePressureForTargetStretch } from "../utils/physics/pressureCalibration";
import { type Vec3 } from "../utils/physics/vec3";
import { type LevelTopology } from "../utils/inflaterRun";
import { type Shape } from "../net_builder/shapes";
import { attachFlat, cornerIdsOf } from "./placement";

/** Python's DIFF_PRESSURE_GUESS_TOL_PCT: how close the Level-3 calibration must land. */
export const DIFF_PRESSURE_TOL_PCT = 5.0;

/** One triangle of a solved Level-3 surface, with the piece it belongs to. */
export interface Triangle {
  a: Vec3;
  b: Vec3;
  c: Vec3;
  source: number;
}

/**
 * What a finished solve leaves for the next Diff Inflate: its slots, Level-3 positions, pressure, and its
 * surface triangles (so new subdivision points can sit on the curved surface, not on the chords between).
 */
export interface LastSolve {
  slots: Map<string, number>;
  positions: Map<number, Vec3>;
  pressure: number;
  triangles: Triangle[];
}

/** The solved Level-3 surface as triangles, each tagged with its piece (sourceOfFace: per solve face, its piece). */
export function surfaceTriangles(topo: LevelTopology, positions: Map<number, Vec3>, sourceOfFace: number[]): Triangle[] {
  const out: Triangle[] = [];
  topo.faces.forEach((face, f) => {
    const a = positions.get(face[0]);
    const b = positions.get(face[1]);
    const c = positions.get(face[2]);
    if (a && b && c) out.push({ a, b, c, source: sourceOfFace[topo.faceOfFine[f]] });
  });
  return out;
}

export interface DiffResult {
  topo: LevelTopology;
  positions: Map<number, Vec3>;
  pressure: number;
  rmsStretchPct: number;
  /** The calibration's replay snapshots, for the debug replay slider. */
  frames: ReplayFrame[];
}

/** True when some corner of `slots` also exists in `last`, so a diff has something to start from. */
export function canDiff(slots: Map<string, number> | null, last: LastSolve | null): boolean {
  if (!slots || !last) return false;
  for (const key of slots.keys()) if (last.slots.has(key)) return true;
  return false;
}

/**
 * Runs the Diff Inflate of `spec` (a junction net) against `last`. Throws if the calibration finds no
 * usable pressure, or the run is stopped (estimatePressure returns without a pressure).
 */
export async function diffInflate(
  spec: NetSpec,
  slots: Map<string, number>,
  last: LastSolve,
  options: { targetRmsPct: number; gtol: number; shouldStop: () => boolean; sourceOfFace: number[]; shapes?: Shape[]; atlasChoice?: AtlasChoice },
): Promise<DiffResult> {
  const base = loadNet(spec);
  const fan = fanLevel0To1(base, options.atlasChoice, groupingOfSpec(spec, base.faces));
  const { positions, pinned } = seedPositions(base.faces, slots, last);

  // A piece with no corner in the last solve is new to the junctions (it was a terminal). It starts laid flat
  // on its kept neighbour, as a terminal would be, and stays out of the surface projection below.
  const keptPieces = new Set([...slots.keys()].filter((key) => last.slots.has(key)).map((key) => Number(key.split(":")[0])));
  const newPieces = new Set(options.sourceOfFace.filter((p) => !keptPieces.has(p)));
  for (const p of newPieces) {
    const shape = options.shapes?.find((s) => s.id === p);
    const cornerIds = shape ? cornerIdsOf(spec, shape) : null;
    if (!shape || !cornerIds) continue;
    const neighbour = [...keptPieces].find((q) => sharedCorners(spec, cornerIds, q) === 2);
    if (neighbour === undefined) continue;
    for (const [k, p3] of attachFlat({ shape, cornerIds, neighbour }, spec, positions)) {
      if (!pinned.has(cornerIds[k])) positions.set(cornerIds[k], p3);
    }
  }

  // Level 1 (the fan): each base face's centroid sits at the average of its corners, as the fan's own ids do.
  const maxBase = Math.max(...base.faces.flat());
  base.faces.forEach((face, f) => {
    const sum = face.reduce<Vec3>((s, v) => [s[0] + positions.get(v)![0], s[1] + positions.get(v)![1], s[2] + positions.get(v)![2]], [0, 0, 0]);
    positions.set(maxBase + 1 + f, [sum[0] / face.length, sum[1] / face.length, sum[2] / face.length]);
  });
  let state: MeshState = {
    mesh: fan.mesh,
    positions,
    faceOfFine: fan.faceOfFine,
    faceOpen: fan.faceOpen,
    faceUV: fan.faceUV,
    outlineEdgeIds: polygonOutlineEdgeIds(base, spec.source_polygon_id ?? base.faces.map((_, f) => f)),
  };
  state = quarterTriangles(quarterTriangles(state));

  // Every new point that isn't a kept corner is set on the surface the kept pieces had before, instead of on
  // the chord between its neighbours, so the diff starts from the curved shape the user had, not a faceted one.
  const kept = new Set(options.sourceOfFace);
  const surface = last.triangles.filter((t) => kept.has(t.source));
  const flatVertices = new Set<number>();
  state.mesh.faces.forEach((face, g) => {
    if (newPieces.has(options.sourceOfFace[state.faceOfFine[g]])) face.forEach((v) => flatVertices.add(v));
  });
  for (const [id, p] of state.positions) {
    if (pinned.has(id) || flatVertices.has(id)) continue;
    const onSurface = projectOntoSurface(p, surface);
    if (onSurface) state.positions.set(id, onSurface);
  }

  const calibration = await estimatePressureForTargetStretch(state.positions, state.mesh, {
    targetRmsPct: options.targetRmsPct,
    gtol: options.gtol,
    tolPct: DIFF_PRESSURE_TOL_PCT,
    initialPressureGuess: last.pressure,
    openFaces: state.faceOpen,
    repulsionVertexMultipliers: repulsionMultipliers(base, 3),
    shouldStop: options.shouldStop,
  });
  if (!calibration.pressureFound) throw new Error("Diff Inflate found no usable pressure.");
  return {
    topo: {
      faces: state.mesh.faces,
      faceOfFine: state.faceOfFine,
      faceEdgeIds: state.mesh.faceEdgeIds,
      outlineEdgeIds: state.outlineEdgeIds,
      faceUV: state.faceUV ?? [],
      atlas: options.atlasChoice,
    },
    positions: calibration.positions,
    pressure: calibration.pressure,
    rmsStretchPct: calibration.rmsStretchPct,
    frames: calibration.frames,
  };
}

/** How many of `corners` also belong to piece `piece` in the solve. */
function sharedCorners(spec: NetSpec, corners: number[], piece: number): number {
  const own = new Set(spec.faces.filter((_, f) => spec.source_polygon_id![f] === piece).flat());
  return corners.filter((v) => own.has(v)).length;
}

/**
 * Level-0 positions for the new net's own corners: a corner whose slot existed keeps its old position;
 * any other corner takes the average of its already-placed neighbours, nudged apart so no two coincide.
 */
function seedPositions(faces: number[][], slots: Map<string, number>, last: LastSolve): { positions: Map<number, Vec3>; pinned: Set<number> } {
  const slotsOf = new Map<number, string[]>();
  for (const [slot, vertex] of slots) {
    const list = slotsOf.get(vertex) ?? [];
    list.push(slot);
    slotsOf.set(vertex, list);
  }
  const positions = new Map<number, Vec3>();
  const pinned = new Set<number>();
  for (const vertex of new Set(faces.flat())) {
    for (const slot of slotsOf.get(vertex) ?? []) {
      const old = last.slots.get(slot);
      const p = old === undefined ? undefined : last.positions.get(old);
      if (p) {
        positions.set(vertex, [...p] as Vec3);
        pinned.add(vertex);
        break;
      }
    }
  }
  if (positions.size === 0) throw new Error("Diff Inflate has no matching corners to start from.");

  const neighbours = new Map<number, Set<number>>();
  for (const face of faces) {
    face.forEach((v, i) => {
      const w = face[(i + 1) % face.length];
      if (!neighbours.has(v)) neighbours.set(v, new Set());
      if (!neighbours.has(w)) neighbours.set(w, new Set());
      neighbours.get(v)!.add(w);
      neighbours.get(w)!.add(v);
    });
  }
  let progress = true;
  while (progress) {
    progress = false;
    for (const [v, adj] of neighbours) {
      if (positions.has(v)) continue;
      const known = [...adj].map((w) => positions.get(w)).filter((p): p is Vec3 => p !== undefined);
      if (known.length === 0) continue;
      const avg = known.reduce<Vec3>((s, p) => [s[0] + p[0] / known.length, s[1] + p[1] / known.length, s[2] + p[2] / known.length], [0, 0, 0]);
      positions.set(v, [avg[0] + 0.05 * Math.cos(v), avg[1] + 0.05 * Math.sin(v), 0.05]);
      progress = true;
    }
  }
  for (const v of neighbours.keys()) if (!positions.has(v)) throw new Error("Diff Inflate could not place every corner.");
  return { positions, pinned };
}

/** The point on the surface (the given triangles) nearest to p, or null if there are no triangles. Brute force,
 * so it's skipped when there are too many points and triangles to be quick. */
function projectOntoSurface(p: Vec3, tris: Triangle[]): Vec3 | null {
  if (!tris.length) return null;
  let best: Vec3 | null = null;
  let bestD = Infinity;
  for (const t of tris) {
    const q = closestOnTriangle(p, t.a, t.b, t.c);
    const d = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 + (q[2] - p[2]) ** 2;
    if (d < bestD) {
      bestD = d;
      best = q;
    }
  }
  return best;
}

/** The point of triangle abc nearest to p (Ericson, Real-Time Collision Detection, 5.1.5). */
function closestOnTriangle(p: Vec3, a: Vec3, b: Vec3, c: Vec3): Vec3 {
  const sub = (x: Vec3, y: Vec3): Vec3 => [x[0] - y[0], x[1] - y[1], x[2] - y[2]];
  const dot = (x: Vec3, y: Vec3) => x[0] * y[0] + x[1] * y[1] + x[2] * y[2];
  const at = (u: number, v: number, w: number): Vec3 => [
    u * a[0] + v * b[0] + w * c[0],
    u * a[1] + v * b[1] + w * c[1],
    u * a[2] + v * b[2] + w * c[2],
  ];
  const ab = sub(b, a);
  const ac = sub(c, a);
  const ap = sub(p, a);
  const d1 = dot(ab, ap);
  const d2 = dot(ac, ap);
  if (d1 <= 0 && d2 <= 0) return a;
  const bp = sub(p, b);
  const d3 = dot(ab, bp);
  const d4 = dot(ac, bp);
  if (d3 >= 0 && d4 <= d3) return b;
  const vc = d1 * d4 - d3 * d2;
  if (vc <= 0 && d1 >= 0 && d3 <= 0) return at(1 - d1 / (d1 - d3), d1 / (d1 - d3), 0);
  const cp = sub(p, c);
  const d5 = dot(ab, cp);
  const d6 = dot(ac, cp);
  if (d6 >= 0 && d5 <= d6) return c;
  const vb = d5 * d2 - d1 * d6;
  if (vb <= 0 && d2 >= 0 && d6 <= 0) return at(1 - d2 / (d2 - d6), 0, d2 / (d2 - d6));
  const va = d3 * d6 - d5 * d4;
  if (va <= 0 && d4 - d3 >= 0 && d5 - d6 >= 0) {
    const w = (d4 - d3) / (d4 - d3 + (d5 - d6));
    return at(0, 1 - w, w);
  }
  const denom = 1 / (va + vb + vc);
  const v = vb * denom;
  const w = vc * denom;
  return at(1 - v - w, v, w);
}
