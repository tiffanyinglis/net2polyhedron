/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import gooseText from "../../../data/inputs/goose.poly?raw";
import { loadNet } from "../mesh";
import { repulsionMultipliers } from "../pipeline";

describe("repulsion on open vs closed corners", () => {
  const base = loadNet(JSON.parse(gooseText));
  const uses = new Map<number, number>();
  for (const id of base.faceEdgeIds.flat()) uses.set(id, (uses.get(id) ?? 0) + 1);
  const open = new Set<number>();
  for (const [id, n] of uses) if (n === 1) for (const v of base.edgeEnds[id]) open.add(v);
  const closed = [...new Set(base.faces.flat())].filter((v) => !open.has(v));

  it("goose has both open and closed corners", () => {
    expect(open.size).toBeGreaterThan(0);
    expect(closed.length).toBeGreaterThan(0);
  });

  it("open corners keep full strength at every level; closed halve per level past 1", () => {
    for (const [level, factor] of [[0, 1], [1, 1], [2, 0.5], [3, 0.25]] as const) {
      const m = repulsionMultipliers(base, level);
      for (const v of open) expect(m.get(v)).toBe(1);
      for (const v of closed) expect(m.get(v)).toBe(factor);
    }
  });
});
