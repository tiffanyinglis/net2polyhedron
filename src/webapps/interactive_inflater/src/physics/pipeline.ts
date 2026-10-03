import { type Vec3 } from "./vec3";
import { EDGE_LENGTH, loadNet, type NetSpec } from "./mesh";
import { fanLevel0To1 } from "./meshLevels";
import { relaxInitialConfigurationWithOrientationRetry } from "./orientationRetry";
import { estimatePressureForTargetStretch } from "./pressureCalibration";
import { CONVERGENCE_GTOL } from "./convergence";

export const LEVEL0_SEED = 0;
export const LEVEL0_SAFETY_STEP_CAP = 50_000;
export const DEFAULT_TARGET_RMS_PCT = 10.0;

export interface InflateStatus {
  stage: "level0" | "level1";
  steps: number;
  rmsStretchPct?: number;
  pressure?: number;
}

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

/** Full "Full Inflate" pipeline for a single closed net, mirroring interactive_inflater_app's own
 * on_full_inflate_clicked: fan-triangulate -> Level 0 relax (with orientation-consistency seed
 * retry) -> Level 1 pressure calibration to a target RMS stretch %. v1 scope: closed meshes only
 * (no pressure_exclude_faces/rms_exclude_edges handling for an open/boundary net yet). */
export async function fullInflate(
  spec: NetSpec,
  options: {
    targetRmsPct?: number;
    gtol?: number;
    /** Live mesh positions for a level (Level 0 on every convergence check, Level 1 once solved). */
    onLevelPositions?: (level: number, positions: Map<number, Vec3>) => void;
    onRecord?: (record: LevelRecord) => void;
    /** Called once the shared Level 0/1 mesh topology is known, before any positions arrive. */
    onTopology?: (faces: number[][], faceOfFine: number[]) => void;
    onStatus?: (status: InflateStatus) => void;
    shouldStop?: () => boolean;
  } = {},
): Promise<InflateResult> {
  const { faces: baseFaces } = loadNet(spec);
  const gtol = options.gtol ?? CONVERGENCE_GTOL;
  const elapsed = (since: number) => (performance.now() - since) / 1000;
  const topology = fanLevel0To1(baseFaces, new Map(baseFaces.flat().map((v) => [v, [0, 0, 0] as Vec3])), EDGE_LENGTH);

  options.onTopology?.(topology.faces, topology.faceOfFine);
  const t0 = performance.now();
  const level0 = await relaxInitialConfigurationWithOrientationRetry(
    topology.faces,
    topology.restLengths,
    LEVEL0_SEED,
    baseFaces,
    {
      maxNfev: LEVEL0_SAFETY_STEP_CAP,
      gtol,
      shouldStop: options.shouldStop,
      onProgress: (positions, steps, _max, rms, optimality) => {
        options.onStatus?.({ stage: "level0", steps });
        options.onLevelPositions?.(0, positions);
        options.onRecord?.({
          level: 0, state: "running", steps, optimality, gtol,
          rmsStretchPct: rms, pressure: null, simTimeS: elapsed(t0),
        });
      },
    },
  );
  options.onLevelPositions?.(0, level0.positions);
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

  const targetRmsPct = options.targetRmsPct ?? DEFAULT_TARGET_RMS_PCT;
  const t1 = performance.now();
  let level1Steps = 0;
  options.onRecord?.({
    level: 1, state: "running", steps: 0, optimality: null, gtol,
    rmsStretchPct: null, pressure: null, simTimeS: 0,
  });
  const calibration = await estimatePressureForTargetStretch(level0.positions, topology.faces, topology.restLengths, {
    targetRmsPct,
    gtol,
    shouldStop: options.shouldStop,
    onProgress: (steps) => {
      level1Steps = steps;
      options.onStatus?.({ stage: "level1", steps });
      options.onRecord?.({
        level: 1, state: "running", steps, optimality: null, gtol,
        rmsStretchPct: null, pressure: null, simTimeS: elapsed(t1),
      });
    },
  });
  options.onRecord?.({
    level: 1,
    state: calibration.pressureFound && calibration.converged ? "converged" : "not_converged",
    steps: Math.max(level1Steps, calibration.stepsTaken),
    optimality: calibration.optimality, gtol,
    rmsStretchPct: calibration.pressureFound ? calibration.rmsStretchPct : null,
    pressure: calibration.pressureFound ? calibration.pressure : null,
    simTimeS: elapsed(t1),
  });
  if (!calibration.pressureFound) {
    throw new Error(`No pressure tried produced a usable result at target RMS ${targetRmsPct}%.`);
  }

  options.onLevelPositions?.(1, calibration.positions);
  return {
    faces: topology.faces,
    baseFaces,
    faceOfFine: topology.faceOfFine,
    positions: calibration.positions,
    rmsStretchPct: calibration.rmsStretchPct,
    maxStretchPct: calibration.maxStretchPct,
    pressure: calibration.pressure,
  };
}
