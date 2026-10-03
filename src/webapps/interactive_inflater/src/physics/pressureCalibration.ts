import { type Vec3 } from "./vec3";
import { totalRestArea } from "./forces";
import { relaxOnce, type RelaxOnceResult } from "./relaxOnce";
import { CONVERGENCE_GTOL } from "./convergence";
import { InsideOutChecker } from "./insideOutChecker";
import { positionsToPts } from "./edgeSetup";
import { vertexIdsOf } from "./mesh";

const PRESSURE_AREA_PRODUCT_ESTIMATE = 25.0;
const PRESSURE_RATIO_CLAMP: [number, number] = [0.2, 5.0];
export const DEFAULT_TARGET_RMS_STRETCH_PCT = 5.0;
const INSANE_STRETCH_FLOOR_PCT = 500.0;
const INSANE_STRETCH_TARGET_MULTIPLE = 5.0;

export interface PressureCalibrationOptions {
  targetRmsPct?: number;
  maxIterations?: number;
  tolPct?: number;
  maxNfevPerTrial?: number;
  gtol?: number;
  initialPressureGuess?: number;
  edges?: [number, number][];
  repulsionStrength?: number;
  shouldStop?: () => boolean;
  onProgress?: (cumulativeSteps: number) => void;
}

export interface PressureCalibrationResult {
  pressure: number;
  positions: Map<number, Vec3>;
  stepsTaken: number;
  maxStretchPct: number;
  rmsStretchPct: number;
  optimality: number | null;
  converged: boolean;
  pressureFound: boolean;
}

/** Runs several relaxOnce trials at different pressures to find one whose result lands within
 * `tolPct` of `targetRmsPct` RMS stretch, bracket-then-bisecting once trials land on both sides
 * of target, and excluding any trial that settled into a spurious inside-out equilibrium from
 * ever pulling pressure the wrong way (mirrors multi_trial_inflater.
 * estimate_pressure_for_target_stretch). The winning trial, if not yet converged, is topped up
 * with one further uncapped relaxOnce call. */
export async function estimatePressureForTargetStretch(
  positions: Map<number, Vec3>,
  faces: number[][],
  edgeLength: number | Map<string, number>,
  options: PressureCalibrationOptions = {},
): Promise<PressureCalibrationResult> {
  const targetRmsPct = options.targetRmsPct ?? DEFAULT_TARGET_RMS_STRETCH_PCT;
  const maxIterations = options.maxIterations ?? 8;
  const tolPct = options.tolPct ?? 1.0;
  const maxNfevPerTrial = options.maxNfevPerTrial ?? 5000;
  const gtol = options.gtol ?? CONVERGENCE_GTOL;

  const relaxOnceOpts = {
    edges: options.edges,
    repulsionStrength: options.repulsionStrength,
    shouldStop: options.shouldStop,
    gtol,
  };

  let pressure: number;
  if (options.initialPressureGuess !== undefined) {
    pressure = options.initialPressureGuess;
  } else {
    const totalArea = totalRestArea(faces, edgeLength);
    pressure = (PRESSURE_AREA_PRODUCT_ESTIMATE * (targetRmsPct / 100.0)) / totalArea;
  }
  const insaneCeiling = Math.max(INSANE_STRETCH_FLOOR_PCT, targetRmsPct * INSANE_STRETCH_TARGET_MULTIPLE);

  const vertexIds = vertexIdsOf(faces);
  const idx = new Map(vertexIds.map((v, i) => [v, i]));
  const facesIdx = faces.map((face) => face.map((v) => idx.get(v)!));
  const referencePts = positionsToPts(positions, vertexIds);
  const insideOutChecker = new InsideOutChecker(referencePts, facesIdx);

  let bestError: number | null = null;
  let bestPressure: number | null = null;
  let bestResult: RelaxOnceResult | null = null;
  let loPressure: number | null = null;
  let hiPressure: number | null = null;
  let result: RelaxOnceResult | null = null;
  let cumulativeSteps = 0;
  let pressureFound = true;

  for (let iter = 0; iter < maxIterations; iter++) {
    const trialBase = cumulativeSteps;
    const onProgress = options.onProgress
      ? (_pos: Map<number, Vec3>, steps: number) => options.onProgress!(trialBase + steps)
      : undefined;
    result = await relaxOnce(positions, faces, edgeLength, pressure, {
      ...relaxOnceOpts,
      maxNfev: maxNfevPerTrial,
      onProgress,
    });
    cumulativeSteps += result.stepsTaken;
    const rmsStretch = result.rmsStretchPct;
    const sane = rmsStretch < insaneCeiling;
    const trialPts = positionsToPts(result.positions, vertexIds);
    const insideOut = sane && insideOutChecker.isInsideOut(trialPts);
    const usable = sane && !insideOut;
    let error = Infinity;
    if (usable) {
      error = Math.abs(rmsStretch - targetRmsPct);
      if (bestError === null || error < bestError) {
        bestError = error;
        bestPressure = pressure;
        bestResult = result;
      }
    }
    const stopped = options.shouldStop?.() ?? false;
    if (stopped || (usable && error < tolPct)) break;
    if (insideOut) {
      loPressure = pressure;
      pressure = hiPressure !== null ? (loPressure + hiPressure) / 2 : pressure * PRESSURE_RATIO_CLAMP[1];
      continue;
    }
    if (usable && rmsStretch <= targetRmsPct) {
      loPressure = pressure;
    } else {
      hiPressure = pressure;
    }
    if (loPressure !== null && hiPressure !== null) {
      pressure = (loPressure + hiPressure) / 2;
    } else if (hiPressure !== null) {
      pressure = hiPressure / 2;
    } else if (rmsStretch > 0) {
      const ratio = Math.min(Math.max(targetRmsPct / rmsStretch, PRESSURE_RATIO_CLAMP[0]), PRESSURE_RATIO_CLAMP[1]);
      pressure *= ratio;
    } else {
      break;
    }
  }

  const stopped = options.shouldStop?.() ?? false;
  let finalPressure: number;
  let finalResult: RelaxOnceResult;
  if (bestResult === null) {
    finalPressure = pressure;
    finalResult = result!;
    pressureFound = false;
  } else {
    finalPressure = bestPressure!;
    finalResult = bestResult;
    if (!finalResult.converged && !stopped) {
      const topUp = await relaxOnce(finalResult.positions, faces, edgeLength, finalPressure, {
        ...relaxOnceOpts,
        maxNfev: null,
        onProgress: options.onProgress
          ? (_pos, steps) => options.onProgress!(cumulativeSteps + steps)
          : undefined,
      });
      finalResult = { ...topUp, stepsTaken: finalResult.stepsTaken + topUp.stepsTaken };
    }
  }

  return {
    pressure: finalPressure,
    positions: finalResult.positions,
    stepsTaken: finalResult.stepsTaken,
    maxStretchPct: finalResult.maxStretchPct,
    rmsStretchPct: finalResult.rmsStretchPct,
    optimality: finalResult.optimality,
    converged: finalResult.converged,
    pressureFound,
  };
}
