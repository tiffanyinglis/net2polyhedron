import { type Mesh, randomInitialPositions } from "./mesh";
import { orientationSigns } from "./forces";
import { relaxInitialConfiguration, type RelaxInitialOptions, type RelaxInitialResult } from "./relaxInitial";
import { type ReplayFrame } from "./relaxOnce";
import { DEFAULT_MAX_ATTEMPTS, DEFAULT_MAX_SEARCH_TIME, SeedSelecter } from "./seedSelecter";

/** An attempt whose share of inward-facing faces is above this is retried with the next seed. */
const MAX_INWARD_FRACTION = 0.3;

function fractionFlipped(signs: number[]): number {
  const nonzero = signs.filter((s) => s !== 0);
  if (!nonzero.length) return 0;
  return nonzero.filter((s) => s < 0).length / nonzero.length;
}

export interface OrientationRetryResult extends RelaxInitialResult {
  seedUsed: number;
  /** Replay snapshots of the accepted attempt only. */
  frames: ReplayFrame[];
}

/** Runs relaxInitialConfiguration up to `maxRetries` times from fresh random starts, stopping at
 * the first attempt that comes back fully orientation-consistent (mirrors pre_inflation_relaxer.
 * relax_initial_configuration_with_orientation_retry). `baseFaces`, if given, is checked instead
 * of `mesh`'s faces (the fan-triangulated mesh) -- a fan hub vertex can bulge out on its own even
 * while the real macro polygon is caved in, see physics.md's Level 0 orientation-retry section. */
export async function relaxInitialConfigurationWithOrientationRetry(
  mesh: Mesh,
  seed: number,
  baseFaces: number[][] | undefined,
  options: RelaxInitialOptions & { maxRetries?: number; maxSearchTime?: number } = {},
): Promise<OrientationRetryResult> {
  const faces = mesh.faces;
  const orientationFaces = baseFaces ?? faces;
  const selecter = new SeedSelecter(
    options.maxRetries ?? DEFAULT_MAX_ATTEMPTS,
    options.maxSearchTime ?? DEFAULT_MAX_SEARCH_TIME,
  );

  const attemptFn = async (attemptSeed: number) => {
    const pos0 = randomInitialPositions(faces, 5.0, attemptSeed);
    const frames: ReplayFrame[] = [];
    const relaxResult = await relaxInitialConfiguration(pos0, mesh, {
      ...options,
      onProgress: (positions, steps) => frames.push({ steps, positions }),
    });
    frames.push({ steps: relaxResult.stepsTaken, positions: relaxResult.positions });
    const vertexIds = [...relaxResult.positions.keys()].sort((a, b) => a - b);
    const pts = vertexIds.map((v) => relaxResult.positions.get(v)!);
    const idx = new Map(vertexIds.map((v, i) => [v, i]));
    const remapped = orientationFaces.map((face) => face.map((v) => idx.get(v)!));
    const signs = orientationSigns(pts, remapped);
    return { relaxResult, signs, frames };
  };

  const scoreFn = (attempt: { relaxResult: RelaxInitialResult; signs: number[]; frames: ReplayFrame[] }): [boolean, number] => {
    // Accepted when converged and at most MAX_INWARD_FRACTION of faces point inward. This is looser
    // than Python's all-outward rule (stretchy_mesh._is_orientation_consistent); a few inward faces
    // are tolerated. An unconverged attempt never counts, so the retry moves on to the next seed.
    const inward = fractionFlipped(attempt.signs);
    const converged = attempt.relaxResult.converged;
    const accepted = converged && inward <= MAX_INWARD_FRACTION;
    // Lower rank is better. A converged attempt always outranks an unconverged one, so when the
    // time or count budget runs out the fallback is the best converged attempt, if there is one.
    return [accepted, (converged ? 0 : 1) + inward];
  };

  const { result, seedUsed } = await selecter.select(seed, attemptFn, scoreFn, {
    shouldStop: options.shouldStop,
  });

  return { ...result.relaxResult, seedUsed, frames: result.frames };
}
