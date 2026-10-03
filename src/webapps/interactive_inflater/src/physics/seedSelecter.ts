export const DEFAULT_MAX_ATTEMPTS = 5;
export const DEFAULT_MAX_SEARCH_TIME = 5.0;

/** Runs up to `maxAttempts` seeded attempts (seed, seed+1, ...), stopping at the first one
 * `scoreFn` accepts, or keeping whichever scored best otherwise. Time-bounded: the first attempt
 * always runs in full; every attempt after that only starts if the cumulative time so far is
 * still under `maxSearchTime` (mirrors seed_selecter.SeedSelecter). */
export class SeedSelecter {
  constructor(
    private maxAttempts = DEFAULT_MAX_ATTEMPTS,
    private maxSearchTime = DEFAULT_MAX_SEARCH_TIME,
  ) {}

  async select<T>(
    seed: number,
    attemptFn: (attemptSeed: number) => Promise<T>,
    scoreFn: (result: T) => [boolean, number],
    options: {
      onAttempt?: (index: number, attemptSeed: number, result: T, accepted: boolean, rank: number) => void;
      shouldStop?: () => boolean;
    } = {},
  ): Promise<{ result: T; seedUsed: number; accepted: boolean; attemptsTried: number }> {
    let best: { rank: number; result: T; seedUsed: number } | null = null;
    let elapsedTotal = 0;
    let attemptsTried = 0;
    for (let i = 0; i < this.maxAttempts; i++) {
      const attemptSeed = seed + i;
      const start = performance.now();
      const result = await attemptFn(attemptSeed);
      elapsedTotal += (performance.now() - start) / 1000;
      attemptsTried += 1;

      const [accepted, rank] = scoreFn(result);
      options.onAttempt?.(i, attemptSeed, result, accepted, rank);
      if (accepted) return { result, seedUsed: attemptSeed, accepted: true, attemptsTried };
      if (best === null || rank < best.rank) best = { rank, result, seedUsed: attemptSeed };

      if (elapsedTotal >= this.maxSearchTime) break;
      if (options.shouldStop?.()) break;
    }
    return { result: best!.result, seedUsed: best!.seedUsed, accepted: false, attemptsTried };
  }
}
