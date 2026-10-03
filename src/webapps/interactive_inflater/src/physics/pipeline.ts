import { type Vec3 } from "./vec3";
import { EDGE_LENGTH, loadNet, type NetSpec } from "./mesh";
import { fanLevel0To1 } from "./meshLevels";
import { relaxInitialConfigurationWithOrientationRetry } from "./orientationRetry";
import { estimatePressureForTargetStretch } from "./pressureCalibration";

export const LEVEL0_SEED = 0;
export const LEVEL0_SAFETY_STEP_CAP = 50_000;
export const DEFAULT_TARGET_RMS_PCT = 10.0;

export interface InflateStatus {
  stage: "level0" | "level1";
  steps: number;
  rmsStretchPct?: number;
  pressure?: number;
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
    onStatus?: (status: InflateStatus) => void;
    shouldStop?: () => boolean;
  } = {},
): Promise<InflateResult> {
  const { faces: baseFaces } = loadNet(spec);
  const topology = fanLevel0To1(baseFaces, new Map(baseFaces.flat().map((v) => [v, [0, 0, 0] as Vec3])), EDGE_LENGTH);

  const level0 = await relaxInitialConfigurationWithOrientationRetry(
    topology.faces,
    topology.restLengths,
    LEVEL0_SEED,
    baseFaces,
    {
      maxNfev: LEVEL0_SAFETY_STEP_CAP,
      shouldStop: options.shouldStop,
      onProgress: (_positions, steps) => options.onStatus?.({ stage: "level0", steps }),
    },
  );
  if (!level0.converged) {
    throw new Error(
      `Level 0 failed to converge (max stretch ${level0.maxStretchPct.toFixed(1)}%, ` +
        `RMS ${level0.rmsStretchPct.toFixed(1)}% after ${level0.stepsTaken} steps).`,
    );
  }

  const targetRmsPct = options.targetRmsPct ?? DEFAULT_TARGET_RMS_PCT;
  const calibration = await estimatePressureForTargetStretch(level0.positions, topology.faces, topology.restLengths, {
    targetRmsPct,
    shouldStop: options.shouldStop,
    onProgress: (steps) => options.onStatus?.({ stage: "level1", steps }),
  });
  if (!calibration.pressureFound) {
    throw new Error(`No pressure tried produced a usable result at target RMS ${targetRmsPct}%.`);
  }

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
