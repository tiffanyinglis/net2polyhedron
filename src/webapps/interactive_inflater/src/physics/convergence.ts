import { type Vec3, norm, sub } from "./vec3";
import { removeRigidMotion } from "./kabsch";

export const CONVERGENCE_GTOL = 1e-4;
export const CONVERGENCE_CHECK_INTERVAL = 200;

/** Realigns `pts` against the run's fixed starting positions and compares the worst vertex's own
 * displacement since the last check to `interval * gtol` (mirrors convergence_checker.
 * check_convergence). Returns the realigned points plus `optimality` (that displacement, divided
 * back down by `interval` so it's directly comparable to a bare gtol) and whether it converged. */
export function checkConvergence(
  pts: Vec3[],
  ptsAtRunStart: Vec3[],
  ptsAtLastCheck: Vec3[],
  interval: number,
  gtol: number,
): { pts: Vec3[]; optimality: number; converged: boolean } {
  const aligned = removeRigidMotion(ptsAtRunStart, pts);
  let blockDisplacement = 0;
  for (let i = 0; i < aligned.length; i++) {
    blockDisplacement = Math.max(blockDisplacement, norm(sub(aligned[i], ptsAtLastCheck[i])));
  }
  const optimality = blockDisplacement / interval;
  return { pts: aligned, optimality, converged: blockDisplacement < interval * gtol };
}

export interface StretchResult {
  positions: Vec3[];
  maxStretchPct: number;
  rmsStretchPct: number;
}

/** Turns solved flat positions into max/RMS edge-stretch percentages (mirrors
 * mesh_stretch_checker.positions_and_stretch). `positions` here stays index-aligned with `pts`
 * (vertex-id lookups happen at the relax_once/relaxInitialConfiguration call boundary). */
export function positionsAndStretch(
  pts: Vec3[],
  edgeA: number[],
  edgeB: number[],
  restLengths: number[],
): StretchResult {
  let sumSq = 0;
  let maxAbs = 0;
  for (let i = 0; i < edgeA.length; i++) {
    const length = norm(sub(pts[edgeA[i]], pts[edgeB[i]]));
    const stretchPct = (100 * (length - restLengths[i])) / restLengths[i];
    sumSq += stretchPct * stretchPct;
    maxAbs = Math.max(maxAbs, Math.abs(stretchPct));
  }
  const rmsStretchPct = Math.sqrt(sumSq / (edgeA.length || 1));
  return { positions: pts, maxStretchPct: maxAbs, rmsStretchPct };
}
