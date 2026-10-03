import { describe, expect, it } from "vitest";
import { CONVERGENCE_GTOL } from "../physics/convergence";
import { LEVELS, LevelStore, readTargetRmsPct, readTolerance, runFullInflate, type StatusKind } from "../inflaterRun";
import { type NetSpec } from "../physics/mesh";

const TETRAHEDRON: NetSpec = { name: "tetrahedron", faces: [[0, 1, 2], [3, 1, 0], [0, 2, 3], [2, 1, 3]] };

/** A minimal stand-in for an HTMLInputElement: the helpers only read and write `value`. */
const field = (value: string) => ({ value }) as HTMLInputElement;

describe("readTargetRmsPct", () => {
  it("reads a percent with or without the sign and writes it back as N%", () => {
    const input = field("12.4%");
    expect(readTargetRmsPct(input, 10)).toBe(12);
    expect(input.value).toBe("12%");
  });

  it("clamps to 0-100", () => {
    expect(readTargetRmsPct(field("150"), 10)).toBe(100);
    expect(readTargetRmsPct(field("-3"), 10)).toBe(0);
  });

  it("falls back to the given default for junk", () => {
    const input = field("abc");
    expect(readTargetRmsPct(input, 7)).toBe(7);
    expect(input.value).toBe("7%");
  });
});

describe("readTolerance", () => {
  it("writes the value back in the 1e-04 form", () => {
    const input = field("1e-4");
    expect(readTolerance(input)).toBeCloseTo(1e-4);
    expect(input.value).toBe("1e-04");
  });

  it("falls back to CONVERGENCE_GTOL for junk or non-positive values", () => {
    expect(readTolerance(field("nope"))).toBe(CONVERGENCE_GTOL);
    expect(readTolerance(field("-1"))).toBe(CONVERGENCE_GTOL);
  });
});

describe("LevelStore", () => {
  it("restores exactly what a snapshot held, even after clear()", () => {
    const store = new LevelStore();
    store.positions[0] = new Map([[0, [0, 0, 0]]]);
    const snap = store.snapshot();
    store.clear();
    expect(store.positions[0]).toBeNull();
    store.restore(snap);
    expect(store.positions[0]).toEqual(new Map([[0, [0, 0, 0]]]));
  });

  it("starts empty for every level", () => {
    const store = new LevelStore();
    expect(store.history).toHaveLength(LEVELS.length);
    expect(store.history.every((r) => r === null)).toBe(true);
  });
});

/** Records every hook call so a run can be checked without a DOM. */
function recordingHooks() {
  const statuses: { text: string; kind: StatusKind }[] = [];
  const shown: number[] = [];
  let historyChanges = 0;
  return {
    statuses,
    shown,
    historyChanges: () => historyChanges,
    hooks: {
      status: (text: string, kind: StatusKind) => statuses.push({ text, kind }),
      loading: () => {},
      showLevel: (level: number) => shown.push(level),
      historyChanged: () => historyChanges++,
    },
  };
}

describe("runFullInflate", () => {
  it("inflates a tetrahedron through every level", async () => {
    const store = new LevelStore();
    const rec = recordingHooks();
    const outcome = await runFullInflate(TETRAHEDRON, {
      label: "Full Inflate",
      targetRmsPctByLevel: { 1: 10, 2: 10, 3: 10 },
      gtol: CONVERGENCE_GTOL,
      store,
      shouldStop: () => false,
      hooks: rec.hooks,
    });
    expect(outcome).toBe("done");
    expect(rec.shown).toEqual(LEVELS);
    expect(LEVELS.every((level) => store.positions[level] !== null)).toBe(true);
    expect(store.history[3]?.state).toBe("converged");
    expect(rec.statuses[rec.statuses.length - 1]?.kind).toBe("success");
    expect(store.runningSince).toBeNull();
  });

  it("reports 'stopped' when shouldStop is already true", async () => {
    const store = new LevelStore();
    const rec = recordingHooks();
    const outcome = await runFullInflate(TETRAHEDRON, {
      label: "Full Inflate",
      targetRmsPctByLevel: { 1: 10, 2: 10, 3: 10 },
      gtol: CONVERGENCE_GTOL,
      store,
      shouldStop: () => true,
      hooks: rec.hooks,
    });
    expect(outcome).toBe("stopped");
    expect(rec.statuses[rec.statuses.length - 1]).toEqual({ text: "Full Inflate -- Stopped.", kind: "warn" });
  });

  it("reports 'error' for a net the solver cannot load", async () => {
    const store = new LevelStore();
    const rec = recordingHooks();
    const outcome = await runFullInflate({ name: "empty", faces: [] }, {
      label: "Full Inflate",
      targetRmsPctByLevel: { 1: 10, 2: 10, 3: 10 },
      gtol: CONVERGENCE_GTOL,
      store,
      shouldStop: () => false,
      hooks: rec.hooks,
    });
    expect(outcome).toBe("error");
    expect(rec.statuses[rec.statuses.length - 1]?.kind).toBe("error");
  });
});
