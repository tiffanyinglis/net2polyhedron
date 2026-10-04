import { describe, expect, it } from "vitest";
import { activeGroup, netSpecFromBuilder, structureKey } from "../bridge";
import { exportMesh } from "../../net_builder/netExport";
import { shapesFrom } from "../../net_builder/netFile";
import { loadNet } from "../../utils/physics/mesh";
import { displayColors, polygonColor } from "../../utils/colors";

/** The saved nets under data/inputs. */
const saved = import.meta.glob("../../data/inputs/*.poly", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

/** Only nets saved with joins by shape id can be rebuilt in the builder. */
const joined = Object.entries(saved)
  .map(([path, text]) => ({ name: path.split("/").pop()!, raw: JSON.parse(text) }))
  .filter(
    ({ raw }) =>
      Array.isArray(raw.builder_connections) &&
      raw.builder_connections.length > 0 &&
      raw.builder_connections.every((c: object) => "a_shape_id" in c),
  );

describe("builder to solver bridge", () => {
  it("finds joined nets to check against", () => {
    expect(joined.length).toBeGreaterThan(0);
  });

  for (const { name, raw } of joined) {
    it(`gives ${name} a spec the solver loads with the builder's own faces`, () => {
      const { shapes, connections } = shapesFrom(raw);
      const spec = netSpecFromBuilder(shapes, connections, name);
      expect(spec.faces).toEqual(exportMesh(shapes, connections).faces);
      const mesh = loadNet(spec);
      expect(mesh.faces.length).toBe(spec.faces.length);
    });
  }

  for (const { name, raw } of joined) {
    it(`colours every face of ${name} by its own shape, as the builder draws it`, () => {
      const { shapes, connections } = shapesFrom(raw);
      const spec = netSpecFromBuilder(shapes, connections, name);
      const colors = displayColors({ mode: "polygon", multiColors: [] }, spec.faces, spec);
      const sideOf = new Map(shapes.map((shape) => [shape.id, shape.n]));
      const expected = spec.source_polygon_id!.map((id) => polygonColor(sideOf.get(id)!));
      expect(colors).toEqual(expected);
    });
  }

  for (const { name, raw } of joined.slice(0, 1)) {
    it(`inflates only the owner's group: a loose piece beside ${name} is left out`, () => {
      const { shapes, connections } = shapesFrom(raw);
      const owner = shapes[0].id;
      const loose = { id: 99999, n: 3, cx: 1000, cy: 1000, rotation: 0, flipped: false };
      const whole = activeGroup([...shapes, loose], connections, owner);
      expect(whole.shapes.map((s) => s.id)).not.toContain(99999);
      expect(whole.shapes.length).toBe(shapes.length);
      expect(netSpecFromBuilder(whole.shapes, whole.connections, name).faces).toEqual(
        netSpecFromBuilder(shapes, connections, name).faces,
      );
    });
  }

  it("has no group without an owner", () => {
    expect(activeGroup([], [], null)).toEqual({ shapes: [], connections: [] });
  });

  for (const { name, raw } of joined.slice(0, 1)) {
    it(`moving or rotating a piece in ${name} keeps its structure key`, () => {
      const { shapes, connections } = shapesFrom(raw);
      const before = structureKey(shapes, connections);
      expect(before).not.toBeNull();
      const moved = shapes.map((s, i) => (i === 1 ? { ...s, cx: s.cx + 50, rotation: s.rotation + 0.7 } : s));
      expect(structureKey(moved, connections)).toBe(before);
    });
  }

  it("changes the structure key when pieces are joined or split", () => {
    const { shapes, connections } = shapesFrom(joined[0].raw);
    expect(structureKey(shapes, connections.slice(1))).not.toBe(structureKey(shapes, connections));
  });
});
