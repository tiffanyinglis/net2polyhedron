import { describe, expect, it } from "vitest";
import { Builder, PASTE_OFFSET, shapeVertices, type Shape } from "../builder";
import { netFileFrom, shapesFrom } from "../netFile";

function withShapes(...shapes: Partial<Shape>[]): Builder {
  const b = new Builder();
  b.loadShapes(shapes.map((s, i) => ({ id: i + 1, n: 4, cx: 0, cy: 0, rotation: 0, flipped: false, ...s })));
  return b;
}

describe("Builder: placing and selecting", () => {
  it("drops the armed shape, selects it and disarms", () => {
    const b = new Builder();
    b.toggleArmed(5);
    b.drop(10, 20);
    expect(b.shapes).toHaveLength(1);
    expect(b.shapes[0]).toMatchObject({ n: 5, cx: 10, cy: 20 });
    expect(b.selected.has(b.shapes[0].id)).toBe(true);
    expect(b.armedN).toBeNull();
  });

  it("Ctrl+click toggles membership, a plain click replaces the selection", () => {
    const b = withShapes({ cx: 0 }, { cx: 100 });
    const [a, c] = b.shapes;
    b.clickShape(a, false);
    b.clickShape(c, true);
    expect([...b.selected].sort()).toEqual([a.id, c.id].sort());
    b.clickShape(a, false); // already selected: the group stays selected
    expect(b.selected.size).toBe(2);
    b.clickShape(c, false); // a shape outside the group would replace it; c is in it, so it stays
    expect(b.selected.size).toBe(2);
  });
});

describe("Builder: undo and redo", () => {
  it("undoes and redoes a delete", () => {
    const b = withShapes({}, {});
    b.clickShape(b.shapes[0], false);
    b.deleteSelected();
    expect(b.shapes).toHaveLength(1);
    b.undoStep();
    expect(b.shapes).toHaveLength(2);
    b.redoStep();
    expect(b.shapes).toHaveLength(1);
  });

  it("records a drag only if the shapes actually moved", () => {
    const b = withShapes({});
    const [s] = b.shapes;
    b.clickShape(s, false);
    b.beginGesture();
    b.commitGesture(); // nothing moved
    expect(b.canUndo).toBe(false);
    b.beginGesture();
    b.dragSelection(new Map([[s.id, [s.cx, s.cy]]]), 5, 0);
    b.commitGesture();
    expect(b.canUndo).toBe(true);
    b.undoStep();
    expect(b.shapes[0].cx).toBe(0);
  });

  it("forgets redo history after a fresh edit", () => {
    const b = withShapes({});
    b.clickShape(b.shapes[0], false);
    b.toggleFlipSelected();
    b.undoStep(); // undo clears the selection, so reselect before the next edit
    expect(b.canRedo).toBe(true);
    b.clickShape(b.shapes[0], false);
    b.toggleFlipSelected();
    expect(b.canRedo).toBe(false);
  });
});

describe("Builder: flip, mirror, copy and paste", () => {
  it("mirroring a shape keeps its vertex set (reflected)", () => {
    const b = withShapes({ cx: 30, cy: 10, rotation: 0.4, n: 5 });
    const before = shapeVertices(b.shapes[0]);
    // The mirror axis is the centre of the vertices' bounding box, as in the Python builder.
    const xs = before.map(([x]) => x);
    const axis = (Math.min(...xs) + Math.max(...xs)) / 2;
    b.clickShape(b.shapes[0], false);
    b.mirrorSelection("horizontal");
    const after = shapeVertices(b.shapes[0]);
    for (const [x, y] of after) {
      const hit = before.some(([bx, by]) => Math.abs(2 * axis - bx - x) < 1e-6 && Math.abs(by - y) < 1e-6);
      expect(hit).toBe(true);
    }
  });

  it("pastes offset from the original and selects the copies", () => {
    const b = withShapes({ cx: 0, cy: 0 });
    b.clickShape(b.shapes[0], false);
    b.copy();
    b.paste();
    expect(b.shapes).toHaveLength(2);
    expect(b.shapes[1].cx).toBeCloseTo(PASTE_OFFSET, 9);
    expect([...b.selected]).toEqual([b.shapes[1].id]);
  });
});

describe("Builder: join mode", () => {
  /** Two squares side by side, in Join mode. */
  function twoSquares(): Builder {
    const b = withShapes({ cx: 0 }, { cx: 100 });
    b.setMode("join");
    return b;
  }

  it("joins two free edges and refuses an edge that's already joined", () => {
    const b = twoSquares();
    expect(b.join(1, 1, 2, 3)).toBe(true);
    expect(b.connections).toHaveLength(1);
    expect(b.join(1, 1, 2, 0)).toBe(false); // edge 1 of shape 1 is joined already
    expect(b.join(2, 3, 1, 3)).toBe(false); // so is edge 3 of shape 2
  });

  it("allows a polygon fold: two edges of the same shape", () => {
    const b = withShapes({ n: 6 });
    b.setMode("join");
    expect(b.join(1, 0, 1, 3)).toBe(true);
    expect(b.connections[0]).toMatchObject({ aShape: 1, bShape: 1, aEdge: 0, bEdge: 3 });
  });

  it("can't join outside Join mode, and can't join an edge to itself", () => {
    const b = withShapes({}, {});
    expect(b.join(1, 0, 2, 0)).toBe(false);
    b.setMode("join");
    expect(b.join(1, 0, 1, 0)).toBe(false);
  });

  it("deletes the selected join in Join mode, and shapes in Move mode", () => {
    const b = twoSquares();
    b.join(1, 1, 2, 3);
    b.selectConnection(b.connections[0].id);
    b.deleteSelected();
    expect(b.connections).toHaveLength(0);
    expect(b.shapes).toHaveLength(2);
    b.setMode("move");
    b.clickShape(b.shapes[0], false);
    b.deleteSelected();
    expect(b.shapes).toHaveLength(1);
  });

  it("removes joins with their shapes, and undo brings them back", () => {
    const b = twoSquares();
    b.setMode("join");
    b.join(1, 1, 2, 3);
    b.setMode("move");
    b.clickShape(b.shapes[1], false);
    b.deleteSelected();
    expect(b.connections).toHaveLength(0);
    b.undoStep();
    expect(b.shapes).toHaveLength(2);
    expect(b.connections).toHaveLength(1);
  });

  it("copies the joins between selected shapes and pastes them onto the new copies", () => {
    const b = twoSquares();
    b.setMode("join");
    b.join(1, 1, 2, 3);
    b.setMode("move");
    b.marqueeSelect(-100, -100, 300, 100, false);
    b.copy();
    b.paste();
    expect(b.shapes).toHaveLength(4);
    expect(b.connections).toHaveLength(2);
    const copied = b.connections[1];
    expect(copied.aShape).toBe(b.shapes[2].id);
    expect(copied.bShape).toBe(b.shapes[3].id);
  });
});

describe("net files", () => {
  it("round-trips a single shape", () => {
    const shapes: Shape[] = [{ id: 1, n: 6, cx: 3, cy: -4, rotation: 0.5, flipped: true }];
    const file = netFileFrom(shapes, [], "hex", 1.5);
    expect(file.faces).toEqual([[0, 1, 2, 3, 4, 5]]);
    expect(file.edges).toHaveLength(6);
    expect(file.face_edge_ids).toEqual([[0, 1, 2, 3, 4, 5]]);
    const back = shapesFrom(JSON.parse(JSON.stringify(file)));
    expect(back.shapes).toEqual(shapes);
    expect(back.connections).toEqual([]);
    expect(back.viewScale).toBe(1.5);
  });

  it("refuses shapes that aren't joined into one piece", () => {
    const two: Shape[] = [
      { id: 1, n: 3, cx: 0, cy: 0, rotation: 0, flipped: false },
      { id: 2, n: 3, cx: 80, cy: 0, rotation: 0, flipped: false },
    ];
    expect(() => netFileFrom(two, [], "x", 1)).toThrow(/disconnected pieces/);
  });

  it("joins two squares into one mesh: six vertices, seven edges, seven distinct face-edge ids", () => {
    const b = withShapes({ cx: 0 }, { cx: 100 });
    b.setMode("join");
    b.join(1, 1, 2, 3);
    const file = netFileFrom(b.shapes, b.connections, "pair", 1);
    expect(new Set(file.faces.flat()).size).toBe(6);
    expect(file.edges).toHaveLength(7);
    expect(new Set(file.face_edge_ids.flat()).size).toBe(7);
    expect(file.builder_connections).toHaveLength(1);
  });

  it("round-trips joins with their bezier handles", () => {
    const b = withShapes({ cx: 0 }, { cx: 100 });
    b.setMode("join");
    b.join(1, 1, 2, 3);
    b.setHandle(b.connections[0].id, "a", [10, 20]);
    const file = netFileFrom(b.shapes, b.connections, "pair", 1);
    const back = shapesFrom(JSON.parse(JSON.stringify(file)));
    // JSON turns -0 into 0, so compare the saved form.
    expect(back.connections).toEqual(JSON.parse(JSON.stringify(b.connections)));
  });

  it("refuses to load a join that refers to a missing shape", () => {
    expect(() =>
      shapesFrom({
        net_layout: [{ shape_id: 1, n: 3, cx: 0, cy: 0, rotation: 0, flipped: false }],
        builder_connections: [{ a_shape_id: 1, a_edge: 0, b_shape_id: 9, b_edge: 0 }],
      }),
    ).toThrow(/isn't in this net/);
  });
});

describe("older net files", () => {
  it("loads a face-indexed net (no shape_id or n in its layout)", () => {
    const back = shapesFrom({
      faces: [
        [0, 1, 2],
        [1, 3, 2, 4],
      ],
      net_layout: [
        { cx: 0, cy: 0, rotation: 0, flipped: false },
        { cx: 90, cy: 0, rotation: 0, flipped: false },
      ],
      builder_connections: [{ a_face: 0, a_edge: 1, b_face: 1, b_edge: 3 }],
    });
    expect(back.shapes.map((s) => [s.id, s.n])).toEqual([
      [1, 3],
      [2, 4],
    ]);
    expect(back.connections).toMatchObject([{ aShape: 1, aEdge: 1, bShape: 2, bEdge: 3 }]);
  });
});
