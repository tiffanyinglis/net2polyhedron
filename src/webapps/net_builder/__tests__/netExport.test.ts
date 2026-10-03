import { describe, expect, it } from "vitest";
import { exportMesh } from "../netExport";
import { shapesFrom } from "../netFile";

/** The saved nets under data/inputs. */
const saved = import.meta.glob("../../data/inputs/*.poly", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

/** Only nets saved in the current format (joins by shape id, with a mesh) can be checked against the port. */
const joined = Object.entries(saved)
  .map(([path, text]) => ({ name: path.split("/").pop()!, raw: JSON.parse(text) }))
  .filter(
    ({ raw }) =>
      Array.isArray(raw.builder_connections) &&
      raw.builder_connections.length > 0 &&
      raw.builder_connections.every((c: object) => "a_shape_id" in c) &&
      Array.isArray(raw.edges),
  );

describe("net export matches the Python builder's saved meshes", () => {
  it("finds joined nets to check against", () => {
    expect(joined.length).toBeGreaterThan(0);
  });

  for (const { name, raw } of joined) {
    it(`reproduces ${name}`, () => {
      const { shapes, connections } = shapesFrom(raw);
      const mesh = exportMesh(shapes, connections);
      expect(mesh.faces).toEqual(raw.faces);
      expect(mesh.edges).toEqual(raw.edges);
      expect(mesh.face_edge_ids).toEqual(raw.face_edge_ids);
      expect(mesh.source_polygon_id).toEqual(raw.source_polygon_id);
    });
  }
});
