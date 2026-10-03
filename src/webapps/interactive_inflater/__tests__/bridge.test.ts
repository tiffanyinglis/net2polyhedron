import { describe, expect, it } from "vitest";
import { netSpecFromBuilder } from "../bridge";
import { exportMesh } from "../../net_builder/netExport";
import { shapesFrom } from "../../net_builder/netFile";
import { loadNet } from "../../utils/physics/mesh";

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
});
