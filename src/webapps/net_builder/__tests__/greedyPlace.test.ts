import { describe, expect, it } from "vitest";
import { connectionCurve, countConnectionCrossings } from "../crossings";
import { faceGeomOf, faceOverlap } from "../curve";
import { greedyPlacement } from "../greedyPlace";
import { connectorQuality, defaultHandles, type Connection } from "../joins";
import { circumradius, DEFAULT_SHAPE_EDGE_LENGTH, type Shape } from "../shapes";

function square(id: number): Shape {
  return { id, n: 4, cx: 0, cy: 0, rotation: 0, flipped: false };
}

function conn(id: number, aShape: number, aEdge: number, bShape: number, bEdge: number): Connection {
  return { id, aShape, aEdge, bShape, bEdge, aHandle: { t: 0, n: 0 }, bHandle: { t: 0, n: 0 } };
}

/** Lays `shapes` out at a greedy placement's result and straightens every join, the same way
 * Builder.untangle() finishes a layout, so crossing counts and overlap checks mean what they say. */
function apply(shapes: Shape[], connections: Connection[]): { shapes: Shape[]; connections: Connection[] } {
  const { positions, rotations } = greedyPlacement(shapes, connections);
  const placed = shapes.map((s) => ({ ...s, cx: positions.get(s.id)![0], cy: positions.get(s.id)![1], rotation: rotations.get(s.id)! }));
  const byId = new Map(placed.map((s) => [s.id, s]));
  const straightened = connections.map((c) => {
    const a = byId.get(c.aShape)!;
    const b = byId.get(c.bShape)!;
    const handles = defaultHandles(a, c.aEdge, b, c.bEdge);
    return { ...c, aHandle: handles.aHandle, bHandle: handles.bHandle };
  });
  return { shapes: placed, connections: straightened };
}

describe("greedyPlacement", () => {
  it("places a single piece at the origin", () => {
    const { positions } = greedyPlacement([square(1)], []);
    expect(positions.get(1)).toEqual([0, 0]);
  });

  it("lays out a simple 4-cycle with no crossings", () => {
    const shapes = [square(1), square(2), square(3), square(4)];
    const connections = [conn(1, 1, 0, 2, 2), conn(2, 2, 1, 3, 3), conn(3, 3, 0, 4, 2), conn(4, 4, 1, 1, 3)];
    const { shapes: placed, connections: straightened } = apply(shapes, connections);
    expect(countConnectionCrossings(placed, straightened)).toBe(0);
  });

  it("never leaves two pieces overlapping", () => {
    // A hub joined to six spokes: nothing to stop a greedy ring of candidates from trying an
    // overlapping one, so this is exactly what the overlap check inside placeAt guards.
    const hub = { ...square(1), n: 8 };
    const spokes = Array.from({ length: 6 }, (_, i) => square(i + 2));
    const shapes = [hub, ...spokes];
    const connections = spokes.map((s, i) => conn(i + 1, 1, i, s.id, 0));
    const { positions } = greedyPlacement(shapes, connections);

    for (let i = 0; i < shapes.length; i++) {
      for (let j = i + 1; j < shapes.length; j++) {
        const [ax, ay] = positions.get(shapes[i].id)!;
        const [bx, by] = positions.get(shapes[j].id)!;
        const minDist = circumradius(shapes[i].n) + circumradius(shapes[j].n);
        expect(Math.hypot(ax - bx, ay - by)).toBeGreaterThanOrEqual(minDist - 1e-6);
      }
    }
  });

  it("is deterministic: the same net placed twice gives the identical layout", () => {
    const shapes = [square(1), square(2), square(3), square(4), square(5)];
    const connections: Connection[] = [];
    let id = 1;
    for (let i = 0; i < shapes.length; i++) {
      for (let j = i + 1; j < shapes.length; j++) {
        connections.push(conn(id++, shapes[i].id, id % 4, shapes[j].id, (id + 1) % 4));
      }
    }
    const first = greedyPlacement(shapes, connections);
    const second = greedyPlacement(shapes, connections);
    for (const s of shapes) {
      expect(second.positions.get(s.id)).toEqual(first.positions.get(s.id));
      expect(second.rotations.get(s.id)).toEqual(first.rotations.get(s.id));
    }
  });

  it("places every piece somewhere finite, even a denser-than-planar K5", () => {
    const shapes = [square(1), square(2), square(3), square(4), square(5)];
    const connections: Connection[] = [];
    let id = 1;
    const edgeUse = new Map(shapes.map((s) => [s.id, 0]));
    for (let i = 0; i < shapes.length; i++) {
      for (let j = i + 1; j < shapes.length; j++) {
        const a = shapes[i];
        const b = shapes[j];
        const aEdge = edgeUse.get(a.id)! % 4;
        const bEdge = edgeUse.get(b.id)! % 4;
        edgeUse.set(a.id, aEdge + 1);
        edgeUse.set(b.id, bEdge + 1);
        connections.push(conn(id++, a.id, aEdge, b.id, bEdge));
      }
    }
    const { positions } = greedyPlacement(shapes, connections);
    for (const s of shapes) {
      const [x, y] = positions.get(s.id)!;
      expect(Number.isFinite(x)).toBe(true);
      expect(Number.isFinite(y)).toBe(true);
    }
  });

  it("places a single joined piece short and square to its neighbour's edge, not just non-overlapping", () => {
    // Nothing else around to force a crossing-avoiding compromise, so the join should land as close to
    // the fold-line ideal (connectorQuality's squareness near 0) as placeAt's candidate ring can manage.
    const hub = square(1);
    const spoke = square(2);
    const shapes = [hub, spoke];
    const connections = [conn(1, 1, 0, 2, 2)];
    const { positions, rotations } = greedyPlacement(shapes, connections);
    const placedHub = { ...hub, cx: positions.get(1)![0], cy: positions.get(1)![1], rotation: rotations.get(1)! };
    const placedSpoke = { ...spoke, cx: positions.get(2)![0], cy: positions.get(2)![1], rotation: rotations.get(2)! };
    const { length, squareness } = connectorQuality(placedHub, 0, placedSpoke, 2);
    expect(squareness).toBeLessThan(0.05);
    expect(length).toBeLessThan(DEFAULT_SHAPE_EDGE_LENGTH * 2);
  });

  it("steers a new piece's join away from a bystander pinned directly on its default path", () => {
    // Piece 2's default (bystander-free) landing spot for this join is due north of piece 1 -- see the
    // sibling test above. Pinning piece 3 right there, in the gap between them, gives placeAt a choice:
    // the same crossing-free spot it would otherwise pick, now cutting across piece 3's own face, or some
    // other crossing-free spot (there are several -- nothing else constrains this join) that doesn't.
    const shapes = [square(1), square(2), square(3)];
    const connections = [conn(1, 1, 0, 2, 2)];
    const pinned = new Map<number, [number, number]>([
      [1, [0, 0]],
      [3, [0, -90]],
    ]);
    const { positions, rotations } = greedyPlacement(shapes, connections, pinned);
    const byId = new Map(
      shapes.map((s) => [s.id, { ...s, cx: positions.get(s.id)![0], cy: positions.get(s.id)![1], rotation: rotations.get(s.id)! }]),
    );
    const conn1 = connections[0];
    const curve = connectionCurve(conn1, (id) => byId.get(id))!;
    const bystanderFace = faceGeomOf(byId.get(3)!);
    expect(faceOverlap(curve.points, [bystanderFace], conn1.aShape, conn1.bShape)).toBe(0);
    expect(countConnectionCrossings([...byId.values()], connections)).toBe(0);
  });

  it("seeds a separate, disconnected component clear of the first", () => {
    const a = square(1);
    const b = square(2);
    const c = square(3);
    const d = square(4);
    const shapes = [a, b, c, d];
    // Two disjoint pairs: 1-2 and 3-4, nothing joining the two pairs to each other.
    const connections = [conn(1, 1, 0, 2, 2), conn(2, 3, 0, 4, 2)];
    const { positions } = greedyPlacement(shapes, connections);
    const minDist = circumradius(4) * 2;
    for (const [i, j] of [
      [1, 3],
      [1, 4],
      [2, 3],
      [2, 4],
    ]) {
      const [ax, ay] = positions.get(i)!;
      const [bx, by] = positions.get(j)!;
      expect(Math.hypot(ax - bx, ay - by)).toBeGreaterThanOrEqual(minDist - 1e-6);
    }
  });
});
