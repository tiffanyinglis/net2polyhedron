import { randomInitialPositions } from "./mesh";
import { orientationSigns } from "./forces";
import { relaxInitialConfiguration, type RelaxInitialOptions, type RelaxInitialResult } from "./relaxInitial";
import { DEFAULT_MAX_ATTEMPTS, DEFAULT_MAX_SEARCH_TIME, SeedSelecter } from "./seedSelecter";

function fractionFlipped(signs: number[]): number {
  const nonzero = signs.filter((s) => s !== 0);
  if (!nonzero.length) return 0;
  return nonzero.filter((s) => s < 0).length / nonzero.length;
}

export interface OrientationRetryResult extends RelaxInitialResult {
  seedUsed: number;
}

/** Runs relaxInitialConfiguration up to `maxRetries` times from fresh random starts, stopping at
 * the first attempt that comes back fully orientation-consistent (mirrors pre_inflation_relaxer.
 * relax_initial_configuration_with_orientation_retry). `baseFaces`, if given, is checked instead
 * of `faces` (the fan-triangulated mesh) -- a fan hub vertex can bulge out on its own even while
 * the real macro polygon is caved in, see physics.md's Level 0 orientation-retry section. */
export async function relaxInitialConfigurationWithOrientationRetry(
  faces: number[][],
  edgeLength: number | Map<string, number>,
  seed: number,
  baseFaces: number[][] | undefined,
  options: RelaxInitialOptions & { maxRetries?: number; maxSearchTime?: number } = {},
): Promise<OrientationRetryResult> {
  const orientationFaces = baseFaces ?? faces;
  const selecter = new SeedSelecter(
    options.maxRetries ?? DEFAULT_MAX_ATTEMPTS,
    options.maxSearchTime ?? DEFAULT_MAX_SEARCH_TIME,
  );

  const attemptFn = async (attemptSeed: number) => {
    const pos0 = randomInitialPositions(faces, 5.0, attemptSeed);
    const relaxResult = await relaxInitialConfiguration(pos0, faces, edgeLength, options);
    const vertexIds = [...relaxResult.positions.keys()].sort((a, b) => a - b);
    const pts = vertexIds.map((v) => relaxResult.positions.get(v)!);
    const idx = new Map(vertexIds.map((v, i) => [v, i]));
    const remapped = orientationFaces.map((face) => face.map((v) => idx.get(v)!));
    const signs = orientationSigns(pts, remapped);
    return { relaxResult, signs };
  };

  const scoreFn = (attempt: { relaxResult: RelaxInitialResult; signs: number[] }): [boolean, number] => {
    const signs = new Set(attempt.signs.filter((s) => s !== 0));
    // Only all-outward (+1) counts: an all-inward (-1) shell is inside-out, not consistent
    // (mirrors stretchy_mesh._is_orientation_consistent: signs <= {+1}).
    const accepted = [...signs].every((s) => s === 1);
    return [accepted, fractionFlipped(attempt.signs)];
  };

  const { result, seedUsed } = await selecter.select(seed, attemptFn, scoreFn, {
    shouldStop: options.shouldStop,
  });

  return { ...result.relaxResult, seedUsed };
}
