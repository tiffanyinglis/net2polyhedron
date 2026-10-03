import { type Vec3 } from "./vec3";
import { type Mesh } from "./mesh";
import { edgeSetup, openRmsMask, positionsToPts, ptsToPositions } from "./edgeSetup";
import { pressureForce, repulsionForce, springForce, REPULSION_STRENGTH } from "./forces";
import { explicitRelaxLoop, STEP_MAX_MULTIPLIER } from "./explicitRelaxLoop";
import { CONVERGENCE_GTOL, positionsAndStretch } from "./convergence";

/** A snapshot of a relaxation in progress, kept for the debug-mode replay. */
export interface ReplayFrame {
  steps: number;
  positions: Map<number, Vec3>;
}

export interface RelaxOnceOptions {
  maxNfev?: number | null;
  gtol?: number;
  repulsionStrength?: number;
  /** Per face: open wedge -- no pressure on it, and its edges are left out of the RMS stat. */
  openFaces?: boolean[];
  /** Restricts repulsion to these vertex ids, each scaled by its multiplier (absent: all vertices). */
  repulsionVertexMultipliers?: Map<number, number>;
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

export interface RelaxOnceResult {
  positions: Map<number, Vec3>;
  stepsTaken: number;
  maxStretchPct: number;
  rmsStretchPct: number;
  optimality: number | null;
  converged: boolean;
}

/** One pressure-driven relaxation pass at a fixed pressure -- no automatic ramp (mirrors
 * stretchy_mesh.relax_once). `mesh` supplies faces and per-edge-id rest lengths (see Mesh). */
export async function relaxOnce(
  positions: Map<number, Vec3>,
  mesh: Mesh,
  pressure: number,
  options: RelaxOnceOptions = {},
): Promise<RelaxOnceResult> {
  const setup = edgeSetup(mesh);
  const facesIdx = mesh.faces.map((face) => face.map((v) => setup.idx.get(v)!));
  const pts0 = positionsToPts(positions, setup.vertexIds);
  const open = options.openFaces?.some(Boolean) ? options.openFaces : undefined;
  const rmsMask = openRmsMask(mesh, setup, options.openFaces);

  let repIndices: number[] | undefined;
  let repMultipliers: number[] | undefined;
  if (options.repulsionVertexMultipliers) {
    const entries = [...options.repulsionVertexMultipliers].filter(([v]) => setup.idx.has(v));
    repIndices = entries.map(([v]) => setup.idx.get(v)!);
    repMultipliers = entries.map(([, m]) => m);
  }

  const forceFn = (pts: Vec3[]) => {
    const spring = springForce(pts, setup.edgeA, setup.edgeB, setup.restLengths);
    const pressureF = pressureForce(pts, facesIdx, pressure, open ? (i) => open[i] : undefined);
    const repulsion = repIndices
      ? repulsionForce(pts, options.repulsionStrength ?? REPULSION_STRENGTH, repIndices, repMultipliers)
      : repulsionForce(pts, options.repulsionStrength ?? REPULSION_STRENGTH);
    return spring.map((f, i) => [
      f[0] + pressureF[i][0] + repulsion[i][0],
      f[1] + pressureF[i][1] + repulsion[i][1],
      f[2] + pressureF[i][2] + repulsion[i][2],
    ] as Vec3);
  };

  const onCheck = options.onProgress
    ? (checkPts: Vec3[], steps: number, optimality: number, converged: boolean) => {
        const { positions: pos, maxStretchPct, rmsStretchPct } = positionsAndStretch(
          checkPts, setup.edgeA, setup.edgeB, setup.restLengths, rmsMask,
        );
        options.onProgress!(
          ptsToPositions(pos, setup.vertexIds), steps, maxStretchPct, rmsStretchPct,
          optimality, converged,
        );
      }
    : undefined;

  const { pts, stepsTaken, optimality, converged } = await explicitRelaxLoop(pts0, setup.scale, forceFn, {
    maxNfev: options.maxNfev ?? null,
    gtol: options.gtol ?? CONVERGENCE_GTOL,
    stepMaxMultiplier: STEP_MAX_MULTIPLIER,
    onCheck,
    shouldStop: options.shouldStop,
  });

  const { positions: finalPts, maxStretchPct, rmsStretchPct } = positionsAndStretch(
    pts, setup.edgeA, setup.edgeB, setup.restLengths, rmsMask,
  );
  return {
    positions: ptsToPositions(finalPts, setup.vertexIds),
    stepsTaken, maxStretchPct, rmsStretchPct, optimality, converged,
  };
}
