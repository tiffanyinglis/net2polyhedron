/**
 * A bit-exact port of numpy's `np.random.default_rng(seed).random()`: SeedSequence -> PCG64 ->
 * 53-bit doubles. Lets a seed here produce the same starting positions as the Python app's
 * random_initial_positions, so a seed that converges in Python converges here too. (mulberry32,
 * which this replaces, gave different positions for the same seed.)
 */

const MASK32 = 0xffffffffn;
const MASK64 = 0xffffffffffffffffn;
const MASK128 = (1n << 128n) - 1n;

// SeedSequence constants (numpy/random/bit_generator.pyx).
const INIT_A = 0x43b0d7e5n;
const MULT_A = 0x931e8875n;
const INIT_B = 0x8b51f9ddn;
const MULT_B = 0x58f38dedn;
const MIX_MULT_L = 0xca01f9ddn;
const MIX_MULT_R = 0x4973f715n;
const XSHIFT = 16n;
const POOL_SIZE = 4;

// PCG64's 128-bit LCG multiplier.
const PCG_MULT = 0x2360ED051FC65DA44385DF649FCCF645n;

function hashmix(value: bigint, state: { hashConst: bigint }): bigint {
  value ^= state.hashConst;
  state.hashConst = (state.hashConst * MULT_A) & MASK32;
  value = (value * state.hashConst) & MASK32;
  return value ^ (value >> XSHIFT);
}

function mix(x: bigint, y: bigint): bigint {
  let result = ((MIX_MULT_L * x) - (MIX_MULT_R * y)) & MASK32;
  return result ^ (result >> XSHIFT);
}

/** SeedSequence(entropy).generate_state(nWords, uint32) for a non-negative integer seed. */
function seedSequenceState(seed: number, nWords: number): bigint[] {
  // numpy splits an integer entropy into 32-bit little-endian words.
  let e = BigInt(seed);
  const entropy: bigint[] = [];
  do {
    entropy.push(e & MASK32);
    e >>= 32n;
  } while (e > 0n);

  const pool: bigint[] = new Array(POOL_SIZE).fill(0n);
  const hc = { hashConst: INIT_A };
  for (let i = 0; i < POOL_SIZE; i++) {
    pool[i] = hashmix(i < entropy.length ? entropy[i] : 0n, hc);
  }
  for (let src = 0; src < POOL_SIZE; src++) {
    for (let dst = 0; dst < POOL_SIZE; dst++) {
      if (src !== dst) pool[dst] = mix(pool[dst], hashmix(pool[src], hc));
    }
  }
  for (let src = POOL_SIZE; src < entropy.length; src++) {
    for (let dst = 0; dst < POOL_SIZE; dst++) {
      pool[dst] = mix(pool[dst], hashmix(entropy[src], hc));
    }
  }

  const out: bigint[] = [];
  const gc = { hashConst: INIT_B };
  for (let i = 0; i < nWords; i++) {
    let word = pool[i % POOL_SIZE] ^ gc.hashConst;
    gc.hashConst = (gc.hashConst * MULT_B) & MASK32;
    word = (word * gc.hashConst) & MASK32;
    out.push(word ^ (word >> XSHIFT));
  }
  return out;
}

/** numpy's default_rng(seed) as a stream of uniform doubles in [0, 1). */
export function numpyRandom(seed: number): () => number {
  // generate_state(4, uint64): each 64-bit word is two consecutive 32-bit words, low first.
  const w = seedSequenceState(seed, 8);
  const word = (i: number) => (w[2 * i] | (w[2 * i + 1] << 32n)) & MASK64;
  const initState = (word(0) << 64n) | word(1);
  const initSeq = (word(2) << 64n) | word(3);

  let state = 0n;
  let inc = ((initSeq << 1n) | 1n) & MASK128;
  const step = () => {
    state = (state * PCG_MULT + inc) & MASK128;
  };
  step();
  state = (state + initState) & MASK128;
  step();

  const next64 = (): bigint => {
    step();
    const hi = state >> 64n;
    const lo = state & MASK64;
    const rot = hi >> 58n;
    const v = (hi ^ lo) & MASK64;
    // rotr64(v, rot)
    return ((v >> rot) | (v << ((64n - rot) & 63n))) & MASK64;
  };

  return () => Number(next64() >> 11n) * 2 ** -53;
}
