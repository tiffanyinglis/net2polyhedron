import { describe, expect, it } from "vitest";
import { Builder } from "../builder";
import { defaultHandles, type Connection } from "../joins";
import { faceInfo, isValidNet, pickOwner } from "../faceTypes";
import { type Shape } from "../shapes";

function square(id: number, cx: number): Shape {
  return { id, n: 4, cx, cy: 0, rotation: 0, flipped: false };
}

/** A join from edge `aEdge` of `a` to edge `bEdge` of `b`, with the builder's default bezier handles. */
function join(id: number, a: Shape, aEdge: number, b: Shape, bEdge: number): Connection {
  const handles = defaultHandles(a, aEdge, b, bEdge);
  return { id, aShape: a.id, aEdge, bShape: b.id, bEdge, aHandle: handles.aHandle, bHandle: handles.bHandle };
}

describe("faceInfo", () => {
  // A chain A-B-C, with D on its own: A is the owner, B a junction (two joins), C a terminal, D unreachable.
  const a = square(1, 0);
  const b = square(2, 100);
  const c = square(3, 200);
  const d = square(4, 500);
  const joins = [join(1, a, 1, b, 3), join(2, b, 1, c, 3)];

  it("classifies owner, junction, terminal and unreachable pieces", () => {
    const info = faceInfo([a, b, c, d], joins, a.id);
    expect(info.get(a.id)).toMatchObject({ reachable: true, role: "owner", joins: 1 });
    expect(info.get(b.id)).toMatchObject({ reachable: true, role: "junction", joins: 2 });
    expect(info.get(c.id)).toMatchObject({ reachable: true, role: "terminal", joins: 1 });
    expect(info.get(d.id)).toMatchObject({ reachable: false, role: null, joins: 0 });
  });

  it("does not count a piece's join to itself as a connection", () => {
    // B is joined to A and also to itself (a Polygon Fold): one real connection, so it's a terminal.
    const self = join(3, b, 0, b, 2);
    const info = faceInfo([a, b], [join(1, a, 1, b, 3), self], a.id);
    expect(info.get(b.id)).toMatchObject({ reachable: true, role: "terminal", joins: 1 });
  });

  it("marks every piece unreachable when there is no owner", () => {
    const info = faceInfo([a, b, c, d], joins, null);
    for (const shape of [a, b, c, d]) expect(info.get(shape.id)?.reachable).toBe(false);
  });
});

describe("net rule: one group of more than one face, owner in it", () => {
  // A chain A-B-C-D, owner A.
  const a = square(1, 0);
  const b = square(2, 100);
  const c = square(3, 200);
  const d = square(4, 300);
  const chain = [join(1, a, 1, b, 3), join(2, b, 1, c, 3), join(3, c, 1, d, 3)];

  it("accepts the chain itself", () => {
    expect(isValidNet([a, b, c, d], chain, a.id)).toBe(true);
  });

  it("allows deleting the owner when the rest stays one group, and the owner moves to a piece in it", () => {
    const shapes = [b, c, d];
    const conns = [chain[1], chain[2]];
    expect(isValidNet(shapes, conns, pickOwner(shapes, conns, a.id))).toBe(true);
    expect(pickOwner(shapes, conns, a.id)).toBe(c.id);
  });

  it("refuses deleting a middle piece that cuts the owner off from a group of more than one face", () => {
    // Removing B leaves {A} and {C, D}: the owner A is outside the only multi-face group.
    const shapes = [a, c, d];
    const conns = [chain[2]];
    expect(isValidNet(shapes, conns, a.id)).toBe(false);
  });

  it("accepts deleting an end piece that leaves a single piece on its own", () => {
    // Removing D leaves {A, B, C}.
    expect(isValidNet([a, b, c], [chain[0], chain[1]], a.id)).toBe(true);
  });

  it("refuses two separate groups of more than one face", () => {
    expect(isValidNet([a, b, c, d], [join(1, a, 1, b, 3), join(2, c, 1, d, 3)], a.id)).toBe(false);
  });

  it("refuses a join that would fold an edge's two ends onto one vertex, with a message saying so", () => {
    // Joining opposite edges of one square folds it in half, so its middle edge's ends meet.
    const builder = new Builder();
    builder.combined = true;
    builder.loadShapes([square(1, 0)]);
    const refusals: string[] = [];
    builder.onRejected = (message) => refusals.push(message);
    expect(builder.join(1, 0, 1, 2)).toBe(false);
    expect(builder.connections.length).toBe(0);
    expect(refusals[0]).toContain("fold");
  });

  it("refuses a delete through the builder and leaves the net unchanged", () => {
    const builder = new Builder();
    builder.combined = true;
    builder.loadShapes([a, b, c, d], chain);
    const refusals: string[] = [];
    builder.onRejected = (message) => refusals.push(message);
    builder.selected = new Set([b.id]);
    builder.deleteSelected();
    expect(builder.shapes.length).toBe(4);
    expect(refusals.length).toBe(1);
  });
});

describe("Builder owner", () => {
  it("is the first piece loaded, and passes to the best-connected survivor when it is deleted", () => {
    const a = square(1, 0);
    const b = square(2, 100);
    const c = square(3, 200);
    const builder = new Builder();
    builder.combined = true;
    builder.loadShapes([a, b, c], [join(1, a, 1, b, 3), join(2, b, 1, c, 3)]);
    expect(builder.ownerShapeId()).toBe(a.id);

    builder.selected = new Set([a.id]);
    builder.deleteSelected();
    // B and C each keep one join; B comes first, so it takes over.
    expect(builder.ownerShapeId()).toBe(b.id);

    // Undoing the delete brings the original owner back.
    builder.undoStep();
    expect(builder.ownerShapeId()).toBe(a.id);
  });
});
