import { describe, expect, it } from "vitest";
import type { Connection } from "../joins";
import { optimalRotations } from "../rotate";
import type { Shape } from "../shapes";

function square(id: number, cx: number, cy: number, rotation = 0): Shape {
  return { id, n: 4, cx, cy, rotation, flipped: false };
}

function conn(id: number, aShape: number, aEdge: number, bShape: number, bEdge: number): Connection {
  return { id, aShape, aEdge, bShape, bEdge, aHandle: { t: 0, n: 0 }, bHandle: { t: 0, n: 0 } };
}

/** Local (rotation-0) outward angle of edge `edge` of an n-gon, matching rotate.ts's own formula. */
function localEdgeAngle(n: number, edge: number): number {
  return -Math.PI / 2 + (2 * Math.PI * edge) / n;
}

describe("optimalRotations", () => {
  it("leaves an unconnected piece's rotation alone", () => {
    const shapes = [square(1, 0, 0, 1.23)];
    const result = optimalRotations(shapes, [], new Map([[1, [0, 0]]]));
    expect(result.get(1)).toBe(1.23);
  });

  it("leaves a piece with only a self-fold alone (nothing else to face)", () => {
    const shapes = [square(1, 0, 0, 0.5)];
    const connections = [conn(1, 1, 0, 1, 2)];
    const result = optimalRotations(shapes, connections, new Map([[1, [0, 0]]]));
    expect(result.get(1)).toBe(0.5);
  });

  it("faces its one join's edge exactly at the neighbour, whatever direction that is", () => {
    const shapes = [square(1, 0, 0), square(2, 0, 0)];
    const positions = new Map<number, [number, number]>([
      [1, [0, 0]],
      [2, [300, 400]], // an arbitrary, non-axis-aligned direction
    ]);
    const connections = [conn(1, 1, 2, 2, 0)]; // piece 1 faces piece 2 with its edge 2
    const rotation = optimalRotations(shapes, connections, positions).get(1)!;
    const facingAngle = Math.atan2(400, 300);
    const actualEdgeAngle = localEdgeAngle(4, 2) + rotation;
    // Angles wrap, so compare via the unit vector rather than the raw numbers.
    expect(Math.cos(actualEdgeAngle - facingAngle)).toBeCloseTo(1, 6);
  });

  it("picks the rotation that globally maximises facing-alignment for a junction piece that can't face every neighbour exactly", () => {
    // A hub with two joins, 90 degrees apart on the piece itself, pointed at two neighbours only 45
    // degrees apart: no single rotation faces both exactly, so this checks the closed-form answer
    // against a brute-force search of the same objective (total cosine alignment) it's meant to maximise.
    const shapes = [square(1, 0, 0), square(2, 0, 0), square(3, 0, 0)];
    const positions = new Map<number, [number, number]>([
      [1, [0, 0]],
      [2, [100, 0]], // due "east", 0 rad
      [3, [100, 100]], // 45 degrees (pi/4 rad)
    ]);
    const connections = [conn(1, 1, 0, 2, 0), conn(2, 1, 1, 3, 0)];
    const rotation = optimalRotations(shapes, connections, positions).get(1)!;

    const want = [Math.atan2(0, 100), Math.atan2(100, 100)];
    const local = [localEdgeAngle(4, 0), localEdgeAngle(4, 1)];
    const objective = (theta: number) => want.reduce((sum, w, i) => sum + Math.cos(local[i] + theta - w), 0);

    let best = -Infinity;
    for (let i = 0; i < 3600; i++) best = Math.max(best, objective((i / 3600) * 2 * Math.PI - Math.PI));
    expect(objective(rotation)).toBeGreaterThanOrEqual(best - 1e-3);
  });
});
