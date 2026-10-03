import { type Vec3, add, scale as scaleVec } from "./vec3";
import { edgeSetup, positionsToPts, ptsToPositions } from "./edgeSetup";
import { pressureForce, repulsionForce, springForce, vertexOutwardNormals } from "./forces";
import { explicitRelaxLoop } from "./explicitRelaxLoop";
import { CONVERGENCE_GTOL, positionsAndStretch } from "./convergence";

export const LEVEL0_STEP_MAX_MULTIPLIER = 0.1;
export const LEVEL0_INITIAL_BURST_PRESSURE = 0.1;
export const LEVEL0_INITIAL_BURST_STEPS = 200;
export const LEVEL0_PERIODIC_BURST_INTERVAL_STEPS = 50;
export const LEVEL0_PERIODIC_BURST_DISTANCE_FRACTION = 0.6;

export interface RelaxInitialOptions {
  maxNfev?: number | null;
  gtol?: number;
  edges?: [number, number][];
  shouldStop?: () => boolean;
  onProgress?: (
    positions: Map<number, Vec3>,
    steps: number,
    maxStretchPct: number,
    rmsStretchPct: number,
    optimality: number,
    converged: boolean,
  ) => void;
}

export interface RelaxInitialResult {
  positions: Map<number, Vec3>;
  stepsTaken: number;
  maxStretchPct: number;
  rmsStretchPct: number;
  optimality: number | null;
  converged: boolean;
}

/** Level 0's "Relax" step: pure spring + all-pairs repulsion (no calibrated pressure), with a
 * one-time initial burst (spring + a little real pressure, before repulsion starts) and a
 * periodic outward-normal displacement kick while not yet converged (mirrors
 * pre_inflation_relaxer.relax_initial_configuration; the repulsion gate it also supports is
 * currently disabled upstream -- LEVEL0_REPULSION_GATE_ENABLED=False -- so it's omitted here). */
export async function relaxInitialConfiguration(
  positions: Map<number, Vec3>,
  faces: number[][],
  edgeLength: number | Map<string, number>,
  options: RelaxInitialOptions = {},
): Promise<RelaxInitialResult> {
  const setup = edgeSetup(faces, edgeLength, options.edges);
  const facesIdx = faces.map((face) => face.map((v) => setup.idx.get(v)!));
  const gtol = options.gtol ?? CONVERGENCE_GTOL;
  let pts0 = positionsToPts(positions, setup.vertexIds);

  const initialBurstForce = (pts: Vec3[]) => {
    const spring = springForce(pts, setup.edgeA, setup.edgeB, setup.restLengths);
    const pressure = pressureForce(pts, facesIdx, LEVEL0_INITIAL_BURST_PRESSURE);
    return spring.map((f, i) => add(f, pressure[i]));
  };
  const burstResult = await explicitRelaxLoop(pts0, setup.scale, initialBurstForce, {
    maxNfev: LEVEL0_INITIAL_BURST_STEPS,
    gtol,
    stepMaxMultiplier: LEVEL0_STEP_MAX_MULTIPLIER,
    shouldStop: options.shouldStop,
  });
  pts0 = burstResult.pts;

  const burstDistance = LEVEL0_PERIODIC_BURST_DISTANCE_FRACTION * setup.scale;
  const burstDt = LEVEL0_STEP_MAX_MULTIPLIER * setup.scale;
  let stepCount = 0;
  let shouldBurstNext = false;

  const forceFn = (pts: Vec3[]) => {
    stepCount += 1;
    const spring = springForce(pts, setup.edgeA, setup.edgeB, setup.restLengths);
    const repulsion = repulsionForce(pts);
    let force = spring.map((f, i) => add(f, repulsion[i]));
    if (shouldBurstNext && stepCount % LEVEL0_PERIODIC_BURST_INTERVAL_STEPS === 1) {
      const outward = vertexOutwardNormals(pts, facesIdx);
      force = force.map((f, i) => add(f, scaleVec(outward[i], burstDistance / burstDt)));
    }
    return force;
  };

  const onCheck = (checkPts: Vec3[], steps: number, optimality: number, converged: boolean) => {
    shouldBurstNext = !converged;
    if (options.onProgress) {
      const { positions: pos, maxStretchPct, rmsStretchPct } = positionsAndStretch(
        checkPts, setup.edgeA, setup.edgeB, setup.restLengths,
      );
      options.onProgress(
        ptsToPositions(pos, setup.vertexIds), steps, maxStretchPct, rmsStretchPct,
        optimality, converged,
      );
    }
  };

  const { pts, stepsTaken, optimality, converged } = await explicitRelaxLoop(pts0, setup.scale, forceFn, {
    maxNfev: options.maxNfev ?? null,
    gtol,
    stepMaxMultiplier: LEVEL0_STEP_MAX_MULTIPLIER,
    onCheck,
    shouldStop: options.shouldStop,
  });

  const { positions: finalPts, maxStretchPct, rmsStretchPct } = positionsAndStretch(
    pts, setup.edgeA, setup.edgeB, setup.restLengths,
  );
  return {
    positions: ptsToPositions(finalPts, setup.vertexIds),
    stepsTaken, maxStretchPct, rmsStretchPct, optimality, converged,
  };
}
