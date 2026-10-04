/**
 * Diff Inflate (the Python app's on_diff_inflate_clicked / _diff_reexport_and_relax). Instead of a
 * Full Inflate from Level 0, the new junction net starts from the last solve's Level-3 positions:
 * each corner that existed before keeps its old position (matched by its slot, shape and corner),
 * the new corners are filled in from their neighbours, the mesh is subdivided to Level 3 as pure
 * interpolation, and one pressure calibration runs there, starting from the last pressure.
 */
import { loadNet, type NetSpec } from "../utils/physics/mesh";
import { fanLevel0To1, polygonOutlineEdgeIds, quarterTriangles, type MeshState } from "../utils/physics/meshLevels";
import { repulsionMultipliers } from "../utils/physics/pipeline";
import { type ReplayFrame } from "../utils/physics/relaxOnce";
import { estimatePressureForTargetStretch } from "../utils/physics/pressureCalibration";
import { type Vec3 } from "../utils/physics/vec3";
import { type LevelTopology } from "../utils/inflaterRun";

/** Python's DIFF_PRESSURE_GUESS_TOL_PCT: how close the Level-3 calibration must land. */
export const DIFF_PRESSURE_TOL_PCT = 5.0;

/** What a finished solve leaves for the next Diff Inflate: its slots and Level-3 positions, and its pressure. */
export interface LastSolve {
  slots: Map<string, number>;
  positions: Map<number, Vec3>;
  pressure: number;
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
  options: { targetRmsPct: number; gtol: number; shouldStop: () => boolean },
): Promise<DiffResult> {
  const base = loadNet(spec);
  const fan = fanLevel0To1(base);
  const positions = seedPositions(base.faces, slots, last);

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
    outlineEdgeIds: polygonOutlineEdgeIds(base, spec.source_polygon_id ?? base.faces.map((_, f) => f)),
  };
  state = quarterTriangles(quarterTriangles(state));

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
    },
    positions: calibration.positions,
    pressure: calibration.pressure,
    rmsStretchPct: calibration.rmsStretchPct,
    frames: calibration.frames,
  };
}

/**
 * Level-0 positions for the new net's own corners: a corner whose slot existed keeps its old position;
 * any other corner takes the average of its already-placed neighbours, nudged apart so no two coincide.
 */
function seedPositions(faces: number[][], slots: Map<string, number>, last: LastSolve): Map<number, Vec3> {
  const slotsOf = new Map<number, string[]>();
  for (const [slot, vertex] of slots) {
    const list = slotsOf.get(vertex) ?? [];
    list.push(slot);
    slotsOf.set(vertex, list);
  }
  const positions = new Map<number, Vec3>();
  for (const vertex of new Set(faces.flat())) {
    for (const slot of slotsOf.get(vertex) ?? []) {
      const old = last.slots.get(slot);
      const p = old === undefined ? undefined : last.positions.get(old);
      if (p) {
        positions.set(vertex, [...p] as Vec3);
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
  return positions;
}
