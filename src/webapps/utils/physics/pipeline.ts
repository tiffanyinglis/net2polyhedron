import { type Vec3 } from "./vec3";
import { isOpenMesh, loadNet, type Mesh, type NetSpec } from "./mesh";
import { fanLevel0To1, polygonOutlineEdgeIds, quarterTriangles, type MeshState } from "./meshLevels";
import { relaxInitialConfigurationWithOrientationRetry } from "./orientationRetry";
import { type ReplayFrame } from "./relaxOnce";
import { estimatePressureForTargetStretch } from "./pressureCalibration";
import { CONVERGENCE_GTOL } from "./convergence";

export const LEVEL0_SEED = 0;
export const LEVEL0_SAFETY_STEP_CAP = 50_000;
export const DEFAULT_TARGET_RMS_PCT = 10.0;
/** Open (boundary) nets default lower, matching the Python app. */
export const OPEN_TARGET_RMS_PCT = 5.0;

/**
 * Per-corner repulsion multipliers for a level (the Python app's _repulsion_vertex_multipliers). A
 * corner that touches a free base edge is "open" and keeps 1; a "closed" corner is scaled by
 * 1 / 2^(level - 1), halved each level past Level 1, so the subdivided vertices don't swamp the springs.
 */
export function repulsionMultipliers(base: Mesh, level: number): Map<number, number> {
  const uses = new Map<number, number>();
  for (const id of base.faceEdgeIds.flat()) uses.set(id, (uses.get(id) ?? 0) + 1);
  const open = new Set<number>();
  for (const [id, count] of uses) {
    if (count === 1) for (const v of base.edgeEnds[id]) open.add(v);
  }
  const factor = 1 / 2 ** Math.max(0, level - 1);
  const multipliers = new Map<number, number>();
  for (const v of new Set(base.faces.flat())) multipliers.set(v, open.has(v) ? 1 : factor);
  return multipliers;
}

export function defaultTargetRmsPct(mesh: Mesh): number {
  return isOpenMesh(mesh) ? OPEN_TARGET_RMS_PCT : DEFAULT_TARGET_RMS_PCT;
}
export const MAX_LEVEL = 3;

/** One Convergence History row (one per level visited). */
export interface LevelRecord {
  level: number;
  state: "running" | "converged" | "not_converged";
  steps: number;
  optimality: number | null;
  gtol: number;
  rmsStretchPct: number | null;
  /** null for Level 0 (no calibrated pressure). */
  pressure: number | null;
  simTimeS: number;
}

export interface InflateResult {
  faces: number[][];
  /** The original (un-subdivided) faces, and which of them each entry of `faces` came from. */
  baseFaces: number[][];
  faceOfFine: number[];
  positions: Map<number, Vec3>;
  rmsStretchPct: number;
  maxStretchPct: number;
  pressure: number;
}

type Calibration = Awaited<ReturnType<typeof estimatePressureForTargetStretch>>;

interface CalibratedLevel {
  level: number;
  pressure: number;
  rmsStretchPct: number;
}

/** Mirrors pressure_history_guess.guess_pressure_from_history: the prior level whose achieved RMS
 * landed closest to the new target, its pressure doubled per level of resolution difference. */
function guessPressureFromHistory(history: CalibratedLevel[], level: number, targetRmsPct: number): number | undefined {
  let best: CalibratedLevel | undefined;
  let bestError = Infinity;
  for (const prior of history) {
    if (prior.level >= level || !prior.pressure) continue;
    const error = Math.abs(prior.rmsStretchPct - targetRmsPct);
    if (error < bestError) {
      bestError = error;
      best = prior;
    }
  }
  return best ? best.pressure * 2 ** (level - best.level) : undefined;
}

/** Full "Full Inflate" pipeline for a single closed net, mirroring interactive_inflater_app's own
 * on_full_inflate_clicked: fan-triangulate -> Level 0 relax (with orientation-consistency seed
 * retry) -> Levels 1..MAX_LEVEL, each a pressure calibration to its own target RMS stretch %,
 * with every level after the first subdivided from the previous solved mesh. Open wedges are
 * excluded from pressure and RMS at every level, as in the Python app. */
export async function fullInflate(
  spec: NetSpec,
  options: {
    /** Target RMS stretch % per level (1..MAX_LEVEL); missing levels use DEFAULT_TARGET_RMS_PCT. */
    targetRmsPctByLevel?: Record<number, number>;
    gtol?: number;
    /** Level 0's starting seed (the orientation retry tries seed, seed+1, ...). Defaults to LEVEL0_SEED. */
    seed?: number;
    /** A level's solved positions, plus the replay snapshots of the trial that produced them. */
    onLevelResult?: (level: number, positions: Map<number, Vec3>, frames: ReplayFrame[]) => void;
    onRecord?: (record: LevelRecord) => void;
    /** Called once a level's mesh topology is known, before its result arrives. */
    onTopology?: (
      level: number,
      faces: number[][],
      faceOfFine: number[],
      faceEdgeIds: number[][],
      outlineEdgeIds: Set<number>,
    ) => void;
    shouldStop?: () => boolean;
  } = {},
): Promise<InflateResult> {
  const base = loadNet(spec);
  const baseFaces = base.faces;
  const gtol = options.gtol ?? CONVERGENCE_GTOL;
  const elapsed = (since: number) => (performance.now() - since) / 1000;
  const topology = fanLevel0To1(base);
  const outlineEdgeIds = polygonOutlineEdgeIds(base, spec.source_polygon_id ?? baseFaces.map((_, i) => i));

  options.onTopology?.(0, topology.mesh.faces, topology.faceOfFine, topology.mesh.faceEdgeIds, outlineEdgeIds);
  const t0 = performance.now();
  options.onRecord?.({
    level: 0, state: "running", steps: 0, optimality: null, gtol,
    rmsStretchPct: null, pressure: null, simTimeS: 0,
  });
  const level0 = await relaxInitialConfigurationWithOrientationRetry(
    topology.mesh,
    options.seed ?? LEVEL0_SEED,
    baseFaces,
    {
      maxNfev: LEVEL0_SAFETY_STEP_CAP,
      gtol,
      openFaces: topology.faceOpen,
      shouldStop: options.shouldStop,
    },
  );
  options.onLevelResult?.(0, level0.positions, level0.frames);
  options.onRecord?.({
    level: 0, state: level0.converged ? "converged" : "not_converged", steps: level0.stepsTaken,
    optimality: level0.optimality, gtol, rmsStretchPct: level0.rmsStretchPct, pressure: null,
    simTimeS: elapsed(t0),
  });
  if (!level0.converged) {
    throw new Error(
      `Level 0 failed to converge (max stretch ${level0.maxStretchPct.toFixed(1)}%, ` +
        `RMS ${level0.rmsStretchPct.toFixed(1)}% after ${level0.stepsTaken} steps).`,
    );
  }

  let state: MeshState = {
    mesh: topology.mesh,
    positions: level0.positions,
    faceOfFine: topology.faceOfFine,
    faceOpen: topology.faceOpen,
    outlineEdgeIds,
  };
  const history: CalibratedLevel[] = [];
  let calibration: Calibration | undefined;
  for (let level = 1; level <= MAX_LEVEL; level++) {
    if (level > 1) state = quarterTriangles(state);
    const repulsionVertexMultipliers = repulsionMultipliers(base, level);
    options.onTopology?.(level, state.mesh.faces, state.faceOfFine, state.mesh.faceEdgeIds, state.outlineEdgeIds);

    const targetRmsPct = options.targetRmsPctByLevel?.[level] ?? defaultTargetRmsPct(base);
    const t = performance.now();
    options.onRecord?.({
      level, state: "running", steps: 0, optimality: null, gtol,
      rmsStretchPct: null, pressure: null, simTimeS: 0,
    });
    calibration = await estimatePressureForTargetStretch(state.positions, state.mesh, {
      targetRmsPct,
      gtol,
      initialPressureGuess: guessPressureFromHistory(history, level, targetRmsPct),
      openFaces: state.faceOpen,
      repulsionVertexMultipliers,
      shouldStop: options.shouldStop,
    });
    options.onRecord?.({
      level,
      state: calibration.pressureFound && calibration.converged ? "converged" : "not_converged",
      steps: calibration.stepsTaken,
      optimality: calibration.optimality, gtol,
      rmsStretchPct: calibration.pressureFound ? calibration.rmsStretchPct : null,
      pressure: calibration.pressureFound ? calibration.pressure : null,
      simTimeS: elapsed(t),
    });
    if (!calibration.pressureFound) {
      throw new Error(`No pressure tried produced a usable result at Level ${level}, target RMS ${targetRmsPct}%.`);
    }

    options.onLevelResult?.(level, calibration.positions, calibration.frames);
    history.push({ level, pressure: calibration.pressure, rmsStretchPct: calibration.rmsStretchPct });
    state = { ...state, positions: calibration.positions };
  }

  return {
    faces: state.mesh.faces,
    baseFaces,
    faceOfFine: state.faceOfFine,
    positions: calibration!.positions,
    rmsStretchPct: calibration!.rmsStretchPct,
    maxStretchPct: calibration!.maxStretchPct,
    pressure: calibration!.pressure,
  };
}
