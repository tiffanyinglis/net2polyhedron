import { describe, expect, it } from "vitest";
import { pointInPolygon } from "../../utils/geometry";
import { countConnectionCrossings } from "../crossings";
import { curveConnectionsToMinimizeCrossings } from "../curve";
import { connectionGeometry, defaultHandles, edgeMidpoints, sampleCubic, type Connection } from "../joins";
import { shapeVertices, type Shape } from "../shapes";

function square(id: number, cx: number, cy: number): Shape {
  return { id, n: 4, cx, cy, rotation: 0, flipped: false };
}

/** The edge of `shape` whose midpoint faces `toward` most directly -- so a join built from it reaches
 * as far as this shape's own geometry allows in that direction, for building deliberately crossing
 * test layouts without hand-deriving exact vertex/edge numbering. */
function edgeFacing(shape: Shape, toward: [number, number]): number {
  const mids = edgeMidpoints(shape);
  let best = 0;
  let bestDist = Infinity;
  mids.forEach((m, i) => {
    const d = Math.hypot(m[0] - toward[0], m[1] - toward[1]);
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  });
  return best;
}

function straightConn(id: number, a: Shape, aEdge: number, b: Shape, bEdge: number): Connection {
  const { aHandle, bHandle } = defaultHandles(a, aEdge, b, bEdge);
  return { id, aShape: a.id, aEdge, bShape: b.id, bEdge, aHandle, bHandle };
}

describe("curveConnectionsToMinimizeCrossings", () => {
  it("bows one of two straight joins that cross each other diagonally, until neither does", () => {
    // Four pieces at the corners of a square, joined corner-to-corner across both diagonals: as
    // straight lines these two joins cross exactly once, in the middle.
    const a = square(1, -200, -200);
    const b = square(2, 200, 200);
    const c = square(3, 200, -200);
    const d = square(4, -200, 200);
    const shapes = [a, b, c, d];
    const conns = [
      straightConn(1, a, edgeFacing(a, [b.cx, b.cy]), b, edgeFacing(b, [a.cx, a.cy])),
      straightConn(2, c, edgeFacing(c, [d.cx, d.cy]), d, edgeFacing(d, [c.cx, c.cy])),
    ];
    expect(countConnectionCrossings(shapes, conns)).toBe(1);

    curveConnectionsToMinimizeCrossings(shapes, conns);

    expect(countConnectionCrossings(shapes, conns)).toBe(0);
  });

  it("leaves an already crossing-free join straight", () => {
    const a = square(1, 0, 0);
    const b = square(2, 1000, 0);
    const shapes = [a, b];
    const conns = [straightConn(1, a, 1, b, 3)];
    const before = { aHandle: conns[0].aHandle, bHandle: conns[0].bHandle };

    curveConnectionsToMinimizeCrossings(shapes, conns);

    expect(conns[0].aHandle).toEqual(before.aHandle);
    expect(conns[0].bHandle).toEqual(before.bHandle);
  });

  it("never makes the total crossing count worse than the straight-line layout it started from", () => {
    // A denser tangle: five pieces in a pentagon, every piece joined to every other (K5) -- more
    // joins than any planar layout can keep crossing-free, so some straight lines are forced to
    // cross; bowing must only ever help or do nothing, never add crossings.
    const pts: [number, number][] = [0, 1, 2, 3, 4].map((i) => {
      const angle = (2 * Math.PI * i) / 5 - Math.PI / 2;
      return [300 * Math.cos(angle), 300 * Math.sin(angle)];
    });
    const shapes = pts.map(([x, y], i) => square(i + 1, x, y));
    const conns: Connection[] = [];
    let id = 1;
    let edgeUse = new Map(shapes.map((s) => [s.id, 0]));
    for (let i = 0; i < shapes.length; i++) {
      for (let j = i + 1; j < shapes.length; j++) {
        const a = shapes[i];
        const b = shapes[j];
        const aEdge = edgeUse.get(a.id)! % 4;
        const bEdge = edgeUse.get(b.id)! % 4;
        edgeUse.set(a.id, edgeUse.get(a.id)! + 1);
        edgeUse.set(b.id, edgeUse.get(b.id)! + 1);
        conns.push(straightConn(id++, a, aEdge, b, bEdge));
      }
    }
    const before = countConnectionCrossings(shapes, conns);
    expect(before).toBeGreaterThan(0);

    curveConnectionsToMinimizeCrossings(shapes, conns);

    expect(countConnectionCrossings(shapes, conns)).toBeLessThanOrEqual(before);
  });

  it("bows a straight join off of a bystander piece's face sitting right on its path, when doing so costs no crossings", () => {
    // Just two joined pieces, far enough apart that a third, unrelated piece sits squarely on the
    // straight line between them. There's nothing else for the curve to cross -- this isolates the
    // face-overlap objective from the crossing one.
    const a = square(1, -300, 0);
    const b = square(2, 300, 0);
    const bystander = square(3, 0, 0);
    const shapes = [a, b, bystander];
    const conn = straightConn(1, a, edgeFacing(a, [b.cx, b.cy]), b, edgeFacing(b, [a.cx, a.cy]));
    const conns = [conn];
    const shapeById = (id: number) => shapes.find((s) => s.id === id);

    const samplesOf = (c: Connection) => {
      const g = connectionGeometry(c, shapeById)!;
      return sampleCubic(...g);
    };
    const overlapsBystander = (c: Connection) =>
      samplesOf(c).some((p) => pointInPolygon(p, shapeVertices(bystander)));

    expect(overlapsBystander(conn)).toBe(true);

    curveConnectionsToMinimizeCrossings(shapes, conns);

    expect(overlapsBystander(conn)).toBe(false);
    expect(countConnectionCrossings(shapes, conns)).toBe(0);
  });
});
