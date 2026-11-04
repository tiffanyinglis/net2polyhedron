import { describe, expect, it } from "vitest";
import { connectorQuality, edgeMidpoints, type Connection } from "../joins";
import { relaxSprings } from "../relax";
import { circumradius, DEFAULT_SHAPE_EDGE_LENGTH, shapeVertices, type Shape } from "../shapes";

/** Separating Axis Theorem for two convex polygons: true if some axis perpendicular to an edge of
 * either polygon separates their projections, i.e. the polygons (as filled regions, not just their
 * circumradius circles) don't overlap. Touching exactly at an edge/vertex counts as not overlapping. */
function polygonsOverlap(a: Shape, b: Shape): boolean {
  const va = shapeVertices(a);
  const vb = shapeVertices(b);
  for (const verts of [va, vb]) {
    for (let i = 0; i < verts.length; i++) {
      const [x1, y1] = verts[i];
      const [x2, y2] = verts[(i + 1) % verts.length];
      const axisX = -(y2 - y1);
      const axisY = x2 - x1;
      const projA = va.map(([x, y]) => x * axisX + y * axisY);
      const projB = vb.map(([x, y]) => x * axisX + y * axisY);
      if (Math.max(...projA) <= Math.min(...projB) || Math.max(...projB) <= Math.min(...projA)) return false;
    }
  }
  return true;
}

function square(id: number, cx: number, cy: number, rotation = 0): Shape {
  return { id, n: 4, cx, cy, rotation, flipped: false };
}

function conn(id: number, aShape: number, aEdge: number, bShape: number, bEdge: number): Connection {
  return { id, aShape, aEdge, bShape, bEdge, aHandle: { t: 0, n: 0 }, bHandle: { t: 0, n: 0 } };
}

function edgeGap(a: Shape, aEdge: number, b: Shape, bEdge: number): number {
  const [ax, ay] = edgeMidpoints(a)[aEdge];
  const [bx, by] = edgeMidpoints(b)[bEdge];
  return Math.hypot(bx - ax, by - ay);
}

/** Runs relaxSprings and returns the shapes updated to its result, for assertions on the settled geometry. */
function relaxed(shapes: Shape[], ids: number[], connections: Connection[]): Shape[] {
  const positions = new Map<number, [number, number]>(shapes.map((s) => [s.id, [s.cx, s.cy]]));
  const rotations = new Map<number, number>(shapes.map((s) => [s.id, s.rotation]));
  relaxSprings(shapes, ids, positions, rotations, connections);
  return shapes.map((s) => ({ ...s, cx: positions.get(s.id)![0], cy: positions.get(s.id)![1], rotation: rotations.get(s.id)! }));
}

describe("relaxSprings", () => {
  it("pulls a stretched join back towards one edge length apart", () => {
    const a = square(1, 0, 0);
    const b = square(2, 0, 400); // edge 2 of a (south) to edge 0 of b (north), way too far apart
    const shapes = [a, b];
    const connections = [conn(1, 1, 2, 2, 0)];
    const before = edgeGap(a, 2, b, 0);
    const result = relaxed(shapes, [1, 2], connections);
    const after = edgeGap(result[0], 2, result[1], 0);
    expect(after).toBeLessThan(before);
    expect(after).toBeCloseTo(DEFAULT_SHAPE_EDGE_LENGTH, 0);
  });

  it("pulls a too-close join back out towards one edge length apart", () => {
    // Centres 110 apart: past the two circumradii (so nothing here is also an overlap to resolve), but
    // short of the gap this join would ideally settle at -- exactly the gap greedy placement's own
    // overlap-avoiding candidates can leave behind.
    const a = square(1, 0, 0);
    const b = square(2, 0, 110);
    const shapes = [a, b];
    const connections = [conn(1, 1, 2, 2, 0)];
    const before = edgeGap(a, 2, b, 0);
    const result = relaxed(shapes, [1, 2], connections);
    const after = edgeGap(result[0], 2, result[1], 0);
    expect(after).toBeGreaterThan(before);
    expect(after).toBeCloseTo(DEFAULT_SHAPE_EDGE_LENGTH, 0);
  });

  it("never lets two pieces (joined or not) end up overlapping", () => {
    const a = square(1, 0, 0);
    const b = square(2, 0, 90); // joined, and starting well inside each other's circumradius
    const c = square(3, 200, 0); // not joined to anything -- only repulsion could move it
    const shapes = [a, b, c];
    const connections = [conn(1, 1, 2, 2, 0)];
    const result = relaxed(shapes, [1, 2, 3], connections);
    const r = circumradius(4);
    for (let i = 0; i < result.length; i++) {
      for (let j = i + 1; j < result.length; j++) {
        expect(Math.hypot(result[i].cx - result[j].cx, result[i].cy - result[j].cy)).toBeGreaterThanOrEqual(2 * r - 1e-6);
      }
    }
  });

  it("leaves everything untouched when nothing in `ids` is connected to anything else in it", () => {
    const a = square(1, 0, 0);
    const b = square(2, 1000, 1000); // far away and unconnected
    const shapes = [a, b];
    const result = relaxed(shapes, [1, 2], []);
    expect([result[0].cx, result[0].cy]).toEqual([0, 0]);
    expect([result[1].cx, result[1].cy]).toEqual([1000, 1000]);
  });

  it("never lets the actual polygon faces overlap, even with mixed sizes and a lot of forced rotation", () => {
    // A triangle, a square and a hexagon, starting stacked on top of each other with wildly mismatched
    // rotations -- circumradius-based repulsion must keep the shapes themselves apart (not just their
    // bounding circles coincidentally missing each other), whatever torque the springs apply meanwhile.
    const tri: Shape = { id: 1, n: 3, cx: 0, cy: 0, rotation: 0.3, flipped: false };
    const sq: Shape = { id: 2, n: 4, cx: 10, cy: -5, rotation: 1.1, flipped: false };
    const hex: Shape = { id: 3, n: 6, cx: -10, cy: 8, rotation: 2.4, flipped: false };
    const shapes = [tri, sq, hex];
    const connections = [conn(1, 1, 0, 2, 2), conn(2, 2, 1, 3, 4)];
    const result = relaxed(shapes, [1, 2, 3], connections);
    for (let i = 0; i < result.length; i++) {
      for (let j = i + 1; j < result.length; j++) {
        expect(polygonsOverlap(result[i], result[j])).toBe(false);
      }
    }
  });

  it("squares up a join that's already at rest length but twisted, not just stretched or compressed ones", () => {
    // b's edge 0 lands exactly DEFAULT_SHAPE_EDGE_LENGTH from a's edge 1 (so the spring itself carries no
    // force, nothing to stretch or compress) but b is rotated 0.5 rad off facing a squarely -- a join a real
    // paper piece would need twisted straight even though its two faces are already the right distance apart.
    const a = square(1, 0, 0);
    const theta = 0.5;
    const target: [number, number] = [105, 0]; // 70 past a's edge-1 midpoint at (35, 0)
    const localEdge0Offset: [number, number] = [0, -35];
    const c = Math.cos(theta);
    const s = Math.sin(theta);
    const worldOffset: [number, number] = [localEdge0Offset[0] * c - localEdge0Offset[1] * s, localEdge0Offset[0] * s + localEdge0Offset[1] * c];
    const b = square(2, target[0] - worldOffset[0], target[1] - worldOffset[1], theta);
    const shapes = [a, b];
    const connections = [conn(1, 1, 1, 2, 0)];
    const before = connectorQuality(a, 1, b, 0);
    expect(before.length).toBeCloseTo(DEFAULT_SHAPE_EDGE_LENGTH, 5); // confirms the spring starts untensioned
    const result = relaxed(shapes, [1, 2], connections);
    const after = connectorQuality(result[0], 1, result[1], 0);
    expect(after.squareness).toBeLessThan(before.squareness);
  });

  it("rotates a piece to square its joined edge up to its fixed neighbour", () => {
    // b's edge 0 (north, local) starts rotated 90 degrees away from facing a at all -- pure translation
    // can slide b around but can never make this join square, only turning b can.
    const a = square(1, 0, 0); // fixed by having nothing else pulling on it
    const b = square(2, 0, 200, Math.PI / 2);
    const shapes = [a, b];
    const connections = [conn(1, 1, 2, 2, 0)]; // a's edge 1 (east) to b's edge 0 (north, pre-rotation)
    const beforeSquareness = (() => {
      const [ax, ay] = edgeMidpoints(a)[1];
      const [bx, by] = edgeMidpoints(b)[0];
      return Math.hypot(bx - ax, by - ay);
    })();
    const result = relaxed(shapes, [1, 2], connections);
    expect(result[1].rotation).not.toBeCloseTo(Math.PI / 2, 1);
    const after = edgeGap(result[0], 1, result[1], 0);
    expect(after).toBeLessThan(beforeSquareness);
  });
});
