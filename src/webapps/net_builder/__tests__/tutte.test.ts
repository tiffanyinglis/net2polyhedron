import { describe, expect, it } from "vitest";
import { segmentsCross } from "../../utils/geometry";
import type { Connection } from "../joins";
import type { Shape } from "../shapes";
import { tutteEmbedding } from "../tutte";

function square(id: number, cx = 0, cy = 0): Shape {
  return { id, n: 4, cx, cy, rotation: 0, flipped: false };
}

function conn(id: number, aShape: number, aEdge: number, bShape: number, bEdge: number): Connection {
  return { id, aShape, aEdge, bShape, bEdge, aHandle: { t: 0, n: 0 }, bHandle: { t: 0, n: 0 } };
}

describe("tutteEmbedding", () => {
  it("places a simple 4-cycle's pieces on an evenly-spaced convex quadrilateral centred on the origin", () => {
    const shapes = [square(1), square(2), square(3), square(4)];
    const connections = [conn(1, 1, 0, 2, 0), conn(2, 2, 1, 3, 0), conn(3, 3, 1, 4, 0), conn(4, 4, 1, 1, 1)];
    const { positions } = tutteEmbedding(shapes, connections);
    expect(positions.size).toBe(4);
    const radii = [...positions.values()].map(([x, y]) => Math.hypot(x, y));
    for (const r of radii) expect(r).toBeCloseTo(radii[0], 6);
    const centroidX = [...positions.values()].reduce((s, [x]) => s + x, 0) / 4;
    const centroidY = [...positions.values()].reduce((s, [, y]) => s + y, 0) / 4;
    expect(centroidX).toBeCloseTo(0, 6);
    expect(centroidY).toBeCloseTo(0, 6);
  });

  it("is purely structural: two wildly different starting layouts of the same net give the identical result", () => {
    const connections = [conn(1, 1, 0, 2, 0), conn(2, 2, 1, 3, 0), conn(3, 3, 1, 4, 0), conn(4, 4, 1, 1, 1)];
    const pileUp = [square(1, 0, 0), square(2, 0, 0), square(3, 0, 0), square(4, 0, 0)];
    const scattered = [square(1, -500, 300), square(2, 900, -200), square(3, 50, 700), square(4, -300, -600)];
    const fromPileUp = tutteEmbedding(pileUp, connections).positions;
    const fromScattered = tutteEmbedding(scattered, connections).positions;
    for (const id of [1, 2, 3, 4]) expect(fromPileUp.get(id)).toEqual(fromScattered.get(id));
  });

  it("doesn't embed a tree (no cycle, so no face to fix as the boundary)", () => {
    const shapes = [square(1), square(2), square(3)];
    const connections = [conn(1, 1, 0, 2, 0), conn(2, 2, 1, 3, 0)];
    expect(tutteEmbedding(shapes, connections).positions.size).toBe(0);
  });

  it("doesn't embed a component with a cut vertex (two triangles sharing one piece)", () => {
    // A bowtie: A-B-C-A and C-D-E-C, sharing only piece C. Not 2-connected, so there's no single
    // position for C that plays its boundary role on both sides -- this must be left for the caller.
    const shapes = [1, 2, 3, 4, 5].map((id) => square(id));
    const connections = [
      conn(1, 1, 0, 2, 0),
      conn(2, 2, 1, 3, 0),
      conn(3, 3, 1, 1, 1),
      conn(4, 3, 2, 4, 0),
      conn(5, 4, 1, 5, 0),
      conn(6, 5, 1, 3, 3),
    ];
    expect(tutteEmbedding(shapes, connections).positions.size).toBe(0);
  });

  it("embeds a tetrahedron's piece graph (K4: every piece joined to every other) with the odd-one-out piece at the other three's centroid, and no crossings", () => {
    // The real builder_connections of an actual saved tetrahedron.hippo (4 triangles, each pair
    // sharing exactly one edge -- a tetrahedron's own dual is K4), so the edge indices are known-good,
    // not hand-guessed: every face in a real planar embedding of K4 is a triangle, and with 4 pieces
    // and an outer face of 3, the 4th piece is the lone interior vertex.
    const shapes = [1, 2, 3, 4].map((id) => square(id));
    const connections = [
      conn(1, 1, 0, 2, 1),
      conn(2, 1, 1, 4, 0),
      conn(3, 1, 2, 3, 0),
      conn(4, 2, 0, 4, 1),
      conn(5, 2, 2, 3, 2),
      conn(6, 3, 1, 4, 2),
    ];

    const { positions } = tutteEmbedding(shapes, connections);
    expect(positions.size).toBe(4);

    const outer = [1, 2, 4]; // the face traceFaces finds first, in this specific rotation system
    const interior = 3;
    const centroid = outer.reduce(
      (sum, id) => {
        const [x, y] = positions.get(id)!;
        return [sum[0] + x / outer.length, sum[1] + y / outer.length];
      },
      [0, 0],
    );
    const [ix, iy] = positions.get(interior)!;
    expect(ix).toBeCloseTo(centroid[0], 6);
    expect(iy).toBeCloseTo(centroid[1], 6);

    // No two of the graph's own edges (straight line between their two pieces' centres) cross.
    const segments = connections.map((c): [number, number][] => [positions.get(c.aShape)!, positions.get(c.bShape)!]);
    for (let i = 0; i < segments.length; i++) {
      for (let j = i + 1; j < segments.length; j++) {
        expect(segmentsCross(segments[i][0], segments[i][1], segments[j][0], segments[j][1])).toBe(false);
      }
    }
  });
});
