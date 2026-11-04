import { describe, expect, it } from "vitest";
import { countConnectionCrossings } from "../crossings";
import { defaultHandles, type Connection } from "../joins";
import type { Shape } from "../shapes";
import { tutteEmbedding } from "../tutte";
import { untangledLayout, untangledPositions } from "../untangle";

/**
 * The real piece graph of klein_bottle_bag.hippo (ids, each piece's n, and every builder_connections
 * entry), trimmed to just what Tutte-embedding cares about. This net closes into a handle (its own name
 * says as much) -- its piece-adjacency graph is NOT planar, which is exactly the case this regression
 * guards: forcing Tutte's embedding onto it used to collapse dozens of pieces on top of each other
 * (confirmed via its Euler characteristic: V - E + F = 0, a torus, not the 2 a planar graph needs).
 */
const KLEIN_IDS = [
  51, 55, 56, 59, 64, 65, 66, 67, 82, 83, 84, 85, 86, 87, 89, 90, 91, 93, 94, 95, 106, 107, 108, 109, 110, 111, 115,
  116, 117, 135, 136, 147, 148, 149, 164, 165, 172, 174, 185, 188, 189, 192, 193, 194, 195, 201, 205, 207, 213, 218,
  219, 220, 221, 222, 223, 224, 225, 226, 227,
];
const KLEIN_NS = [
  4, 3, 3, 4, 4, 4, 4, 4, 4, 3, 3, 4, 4, 4, 4, 4, 4, 3, 4, 3, 3, 4, 3, 4, 4, 4, 5, 5, 4, 6, 6, 5, 5, 5, 5, 5, 4, 4, 7,
  6, 6, 5, 5, 5, 5, 6, 6, 4, 8, 5, 5, 5, 5, 8, 4, 4, 8, 8, 4,
];
const KLEIN_CONNS: [number, number, number, number][] = [
  [51, 2, 55, 0], [56, 2, 59, 0], [55, 2, 64, 3], [64, 1, 56, 0], [64, 2, 65, 0], [66, 3, 65, 2], [66, 1, 67, 0],
  [67, 2, 64, 0], [83, 1, 82, 2], [82, 0, 84, 1], [83, 2, 85, 3], [66, 0, 85, 2], [82, 1, 86, 3], [86, 2, 85, 0],
  [84, 0, 87, 0], [86, 0, 87, 3], [87, 1, 66, 2], [89, 1, 84, 2], [91, 1, 65, 1], [91, 0, 83, 0], [91, 2, 93, 2],
  [93, 0, 59, 3], [93, 1, 90, 2], [82, 3, 94, 2], [94, 0, 90, 1], [89, 2, 94, 1], [94, 3, 91, 3], [89, 0, 65, 3],
  [51, 3, 95, 1], [95, 0, 90, 0], [89, 3, 95, 2], [87, 2, 106, 0], [106, 1, 107, 1], [107, 2, 67, 3], [85, 1, 108, 1],
  [109, 1, 108, 0], [67, 1, 109, 0], [86, 1, 110, 3], [110, 2, 108, 2], [110, 0, 106, 2], [110, 1, 111, 0],
  [107, 0, 111, 1], [111, 3, 109, 2], [59, 1, 115, 1], [116, 4, 51, 1], [90, 3, 117, 1], [117, 0, 51, 0],
  [117, 2, 59, 2], [136, 2, 135, 0], [147, 2, 135, 4], [148, 0, 135, 5], [148, 4, 136, 3], [147, 1, 148, 1],
  [149, 1, 136, 4], [149, 2, 148, 3], [172, 3, 115, 0], [172, 1, 116, 0], [117, 3, 172, 2], [172, 0, 174, 0],
  [135, 1, 185, 5], [185, 6, 136, 1], [185, 2, 111, 2], [188, 4, 116, 3], [188, 3, 55, 1], [188, 2, 107, 3],
  [188, 1, 185, 3], [115, 2, 189, 2], [189, 3, 56, 1], [189, 4, 109, 3], [189, 5, 185, 1], [188, 0, 192, 0],
  [192, 4, 185, 4], [192, 3, 135, 2], [192, 2, 193, 4], [193, 2, 147, 3], [193, 3, 135, 3], [189, 0, 194, 1],
  [194, 2, 185, 0], [194, 3, 136, 0], [195, 1, 194, 4], [195, 2, 136, 5], [195, 3, 149, 0], [201, 3, 195, 4],
  [201, 4, 149, 4], [164, 2, 201, 0], [205, 0, 165, 0], [205, 2, 147, 4], [205, 3, 193, 1], [174, 2, 207, 1],
  [213, 7, 115, 3], [213, 0, 189, 1], [213, 1, 194, 0], [213, 2, 195, 0], [213, 3, 201, 2], [201, 1, 218, 3],
  [218, 4, 164, 1], [218, 2, 213, 4], [218, 1, 219, 3], [213, 5, 219, 2], [219, 0, 207, 2], [205, 5, 220, 4],
  [220, 3, 165, 1], [220, 1, 221, 4], [207, 0, 221, 2], [221, 0, 222, 6], [222, 7, 220, 0], [222, 0, 205, 4],
  [222, 1, 193, 0], [222, 2, 192, 1], [222, 3, 188, 5], [222, 4, 116, 2], [174, 3, 223, 1], [174, 1, 224, 3],
  [224, 0, 115, 4], [224, 1, 213, 6], [224, 2, 219, 1], [223, 2, 221, 1], [223, 3, 222, 5], [223, 0, 116, 1],
  [148, 2, 225, 6], [225, 7, 147, 0], [225, 5, 149, 3], [225, 4, 201, 5], [225, 0, 205, 1], [225, 1, 165, 4],
  [164, 3, 225, 3], [207, 3, 226, 3], [226, 4, 219, 4], [226, 5, 218, 0], [226, 2, 221, 3], [226, 1, 220, 2],
  [226, 0, 165, 2], [226, 6, 164, 0], [226, 7, 227, 0], [227, 1, 164, 4], [227, 2, 225, 2], [165, 3, 227, 3],
];

function kleinNet(): { shapes: Shape[]; connections: Connection[] } {
  const shapes = KLEIN_IDS.map((id, i) => ({ id, n: KLEIN_NS[i], cx: 0, cy: 0, rotation: 0, flipped: false }));
  const connections = KLEIN_CONNS.map(([aShape, aEdge, bShape, bEdge], i) => ({
    id: i + 1,
    aShape,
    aEdge,
    bShape,
    bEdge,
    aHandle: { t: 0, n: 0 },
    bHandle: { t: 0, n: 0 },
  }));
  return { shapes, connections };
}

describe("Tutte embedding declines a non-planar (higher-genus) net instead of collapsing it", () => {
  it("doesn't Tutte-embed the klein_bottle_bag piece graph", () => {
    const { shapes, connections } = kleinNet();
    const { positions } = tutteEmbedding(shapes, connections);
    expect(positions.size).toBe(0);
  });

  it("falls back to a layout with no pieces collapsed on top of each other", () => {
    const { shapes, connections } = kleinNet();
    const result = untangledPositions(shapes, connections);
    const points = [...result.values()];
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const dist = Math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1]);
        expect(dist).toBeGreaterThan(10);
      }
    }
  });

  it("doesn't make the net's crossings worse than before Tutte was added: forcing the old (pre-fix) collapse onto this net produced hundreds of crossings; the real fallback should produce far fewer", () => {
    const { shapes, connections } = kleinNet();
    // The same two steps Builder.untangle() runs, in the same order: position+rotation together (greedy
    // placement's own crossing-minimising choices), then straighten every join.
    const { positions, rotations } = untangledLayout(shapes, connections);
    for (const shape of shapes) {
      const p = positions.get(shape.id)!;
      shape.cx = p[0];
      shape.cy = p[1];
      shape.rotation = rotations.get(shape.id) ?? shape.rotation;
    }
    const byId = new Map(shapes.map((s) => [s.id, s]));
    for (const conn of connections) {
      const a = byId.get(conn.aShape)!;
      const b = byId.get(conn.bShape)!;
      const handles = defaultHandles(a, conn.aEdge, b, conn.bEdge);
      conn.aHandle = handles.aHandle;
      conn.bHandle = handles.bHandle;
    }
    expect(countConnectionCrossings(shapes, connections)).toBeLessThan(150);
  });
});
