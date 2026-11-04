import { describe, expect, it } from "vitest";
import { Builder } from "../builder";
import { countConnectionCrossings } from "../crossings";
import type { Connection } from "../joins";
import type { Shape } from "../shapes";
import { untangledPositions } from "../untangle";

function square(id: number, n: number, cx: number, cy: number): Shape {
  return { id, n, cx, cy, rotation: 0, flipped: false };
}

function conn(id: number, aShape: number, aEdge: number, bShape: number, bEdge: number): Connection {
  return { id, aShape, aEdge, bShape, bEdge, aHandle: { t: 0, n: 0 }, bHandle: { t: 0, n: 0 } };
}

describe("untangledPositions", () => {
  it("leaves fewer than two shapes untouched", () => {
    const shapes = [square(1, 4, 5, 5)];
    const result = untangledPositions(shapes, []);
    expect(result.get(1)).toEqual([5, 5]);
  });

  it("separates pieces piled on the same point", () => {
    // A 4-cycle (box graph), every piece dropped at the exact same spot.
    const shapes = [square(1, 4, 0, 0), square(2, 4, 0, 0), square(3, 4, 0, 0), square(4, 4, 0, 0)];
    const connections = [conn(1, 1, 0, 2, 0), conn(2, 2, 1, 3, 0), conn(3, 3, 1, 4, 0), conn(4, 4, 1, 1, 1)];
    const result = untangledPositions(shapes, connections);

    for (const [, [x, y]] of result) {
      expect(Number.isFinite(x)).toBe(true);
      expect(Number.isFinite(y)).toBe(true);
    }
    // No two pieces still coincide.
    const points = [...result.values()];
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const dist = Math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1]);
        expect(dist).toBeGreaterThan(10);
      }
    }
  });

  it("pulls a joined pair toward a stable, separated rest length", () => {
    const shapes = [square(1, 4, 0, 0), square(2, 4, 1000, 1000)];
    const connections = [conn(1, 1, 0, 2, 0)];
    const result = untangledPositions(shapes, connections);
    const [ax, ay] = result.get(1)!;
    const [bx, by] = result.get(2)!;
    const dist = Math.hypot(ax - bx, ay - by);
    // A square's circumradius at the default edge length is ~49.5px; the rest length clears both
    // plus a margin, so somewhere well short of the 1414px starting distance but clearly non-zero.
    expect(dist).toBeGreaterThan(20);
    expect(dist).toBeLessThan(400);
  });

  it("ignores a self-fold (nothing on the other end to pull apart)", () => {
    const shapes = [square(1, 6, 0, 0)];
    const connections = [conn(1, 1, 0, 1, 2)];
    const result = untangledPositions(shapes, connections);
    expect(result.get(1)).toEqual([0, 0]);
  });

  it("pushes disconnected pieces apart with no springs pulling them back", () => {
    const shapes = [square(1, 4, 0, 0), square(2, 4, 1, 0)];
    const result = untangledPositions(shapes, []);
    const [ax, ay] = result.get(1)!;
    const [bx, by] = result.get(2)!;
    expect(Math.hypot(ax - bx, ay - by)).toBeGreaterThan(50);
  });

  it("never leaves two pieces overlapping, even a crowded hub whose own spring equilibrium would leave its spokes touching", () => {
    // A hub joined to six neighbours, every piece dropped at the same point: the spring equilibrium
    // alone tends to leave a crowded hub's neighbours packed shoulder to shoulder, some of them closer
    // than their own circumradii -- this is exactly what the hard overlap pass has to clean up.
    const hub = square(1, 8, 0, 0);
    const spokes = Array.from({ length: 6 }, (_, i) => square(i + 2, 4, 0, 0));
    const shapes = [hub, ...spokes];
    const connections = spokes.map((s, i) => conn(i + 1, 1, i, s.id, 0));
    const result = untangledPositions(shapes, connections);

    const circumradius = (n: number) => 70 / (2 * Math.sin(Math.PI / n));
    for (let i = 0; i < shapes.length; i++) {
      for (let j = i + 1; j < shapes.length; j++) {
        const [ax, ay] = result.get(shapes[i].id)!;
        const [bx, by] = result.get(shapes[j].id)!;
        const dist = Math.hypot(ax - bx, ay - by);
        const minDist = circumradius(shapes[i].n) + circumradius(shapes[j].n);
        // A small numerical slack: the pass guarantees clearance past touching, not exact to the pixel.
        expect(dist).toBeGreaterThanOrEqual(minDist - 1e-6);
      }
    }
  });

  it("escapes the exact kind of trap a pure spring-electrical relaxation can settle into: a 4-ring tangled by dragging one piece across it", () => {
    // The same regression this fix was written for: four pieces joined in a ring, then one dragged far
    // across the others (reproducing what the Interactive Inflater's Untangle button left at "3
    // crossings" before Tutte's embedding was added). Builder.untangle() straightens every join's curve
    // afterward (see builder.ts); straight lines are what the crossing count is meaningful for, so this
    // builds them here too, via Builder.join's own default handles.
    const b = new Builder();
    b.combined = true; // as the Interactive Inflater's page sets it: Move and Join both always allowed
    b.loadShapes([
      { id: 1, n: 4, cx: 0, cy: 0, rotation: 0, flipped: false },
      { id: 2, n: 4, cx: 100, cy: 0, rotation: 0, flipped: false },
      { id: 3, n: 4, cx: 100, cy: 100, rotation: 0, flipped: false },
      { id: 4, n: 4, cx: 0, cy: 100, rotation: 0, flipped: false },
    ]);
    expect(b.join(1, 0, 2, 2)).toBe(true);
    expect(b.join(2, 1, 3, 3)).toBe(true);
    expect(b.join(3, 0, 4, 2)).toBe(true);
    expect(b.join(4, 1, 1, 3)).toBe(true);

    // Tangle it: piece 3 dragged far across the other three's connections.
    const piece3 = b.shapes.find((s) => s.id === 3)!;
    piece3.cx = 900;
    piece3.cy = -600;

    b.untangle();

    expect(countConnectionCrossings(b.shapes, b.connections)).toBe(0);
  });
});
