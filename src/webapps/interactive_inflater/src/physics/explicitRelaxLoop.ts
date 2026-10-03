import { type Vec3, add, scale } from "./vec3";
import { CONVERGENCE_CHECK_INTERVAL, checkConvergence } from "./convergence";
import { removeRigidMotion } from "./kabsch";

export const STEP_MAX_MULTIPLIER = 0.05;
export const MAX_UNBOUNDED_STEPS = 200_000;

export interface RelaxLoopResult {
  pts: Vec3[];
  stepsTaken: number;
  optimality: number | null;
  converged: boolean;
}

export interface RelaxLoopOptions {
  maxNfev?: number | null;
  gtol: number;
  stepMaxMultiplier?: number;
  onCheck?: (pts: Vec3[], steps: number, optimality: number, converged: boolean) => void;
  shouldStop?: () => boolean;
}

function yieldToUi(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/** Shared explicit-relaxation driver for relaxOnce/relaxInitialConfiguration (mirrors
 * stretchy_mesh._explicit_relax_loop, minus the optional random-kick/`rng` path -- this app never
 * enables it, matching both Python apps' own Relax/Inflate calls). Repeatedly nudges `pts` a
 * small step along `forceFn(pts)` until either the worst vertex's own displacement over the last
 * CONVERGENCE_CHECK_INTERVAL steps drops below `CONVERGENCE_CHECK_INTERVAL * gtol`, or `maxNfev`/
 * `shouldStop` cuts it off first. Yields to the event loop once per block so the UI stays
 * responsive during a long run -- there is no worker thread here, unlike the Python apps'
 * background-thread pattern. */
export async function explicitRelaxLoop(
  pts0: Vec3[],
  scaleLength: number,
  forceFn: (pts: Vec3[]) => Vec3[],
  options: RelaxLoopOptions,
): Promise<RelaxLoopResult> {
  const stepMaxMultiplier = options.stepMaxMultiplier ?? STEP_MAX_MULTIPLIER;
  const stepCap = options.maxNfev ?? MAX_UNBOUNDED_STEPS;
  let pts = pts0;
  const ptsAtRunStart = pts0;
  let ptsAtLastCheck = pts0;
  let stepsTaken = 0;
  let optimality: number | null = null;
  let converged = false;
  // A plain `for (stepsTaken = 1; stepsTaken <= stepCap; stepsTaken++)` would leave stepsTaken at
  // stepCap+1 after a normal (non-break) exit, since JS increments past the last valid iteration
  // -- unlike Python's `for steps_taken in range(1, step_cap+1)`, which leaves the loop variable
  // at its last USED value (step_cap). Looping on a separate counter and only assigning
  // stepsTaken inside the body keeps the reported count exactly matching Python's.
  for (let step = 1; step <= stepCap; step++) {
    if (options.shouldStop?.()) break;
    stepsTaken = step;
    const force = forceFn(pts);
    const dt = stepMaxMultiplier * scaleLength;
    pts = pts.map((p, i) => add(p, scale(force[i], dt)));
    if (stepsTaken % CONVERGENCE_CHECK_INTERVAL === 0) {
      const checked = checkConvergence(pts, ptsAtRunStart, ptsAtLastCheck, CONVERGENCE_CHECK_INTERVAL, options.gtol);
      pts = checked.pts;
      optimality = checked.optimality;
      converged = checked.converged;
      ptsAtLastCheck = pts;
      options.onCheck?.(pts, stepsTaken, optimality, converged);
      await yieldToUi();
      if (converged) break;
    }
  }
  if (stepsTaken % CONVERGENCE_CHECK_INTERVAL !== 0) {
    pts = removeRigidMotion(ptsAtRunStart, pts);
  }
  return { pts, stepsTaken, optimality, converged };
}
