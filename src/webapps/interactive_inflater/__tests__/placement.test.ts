import { describe, expect, it } from "vitest";
import { planPlacement, buildDisplay, NO_SOLVE_TOPOLOGY } from "../placement";
import { shapesFrom } from "../../net_builder/netFile";
import { type Connection } from "../../net_builder/joins";
import { type Shape } from "../../net_builder/shapes";
import { type Vec3 } from "../../utils/physics/vec3";
import { loadNet } from "../../utils/physics/mesh";

/** The saved nets under data/inputs. */
const saved = import.meta.glob("../../data/inputs/*.poly", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

const joined = Object.entries(saved)
  .map(([path, text]) => ({ name: path.split("/").pop()!, raw: JSON.parse(text) }))
  .filter(
    ({ raw }) =>
      Array.isArray(raw.builder_connections) &&
      raw.builder_connections.length > 0 &&
      raw.builder_connections.every((c: object) => "a_shape_id" in c),
  );

/** Connection degree per shape, as the planner counts it. */
function degrees(shapes: Shape[], connections: Connection[]) {
  const deg = new Map(shapes.map((s) => [s.id, 0]));
  for (const c of connections) {
    deg.set(c.aShape, deg.get(c.aShape)! + 1);
    deg.set(c.bShape, deg.get(c.bShape)! + 1);
  }
  return deg;
}

describe("junction and terminal placement", () => {
  for (const { name, raw } of joined) {
    it(`${name}: solves only the junctions and lays every terminal flat around them`, () => {
      const { shapes, connections } = shapesFrom(raw);
      const plan = planPlacement(shapes, connections, shapes[0].id);
      const deg = degrees(shapes, connections);
      const junctions = shapes.filter((s) => deg.get(s.id)! >= 2);
      const terminals = shapes.filter((s) => deg.get(s.id)! < 2);
      const folded = connections.some((c) => c.aShape === c.bShape);
      if (junctions.length >= 2 || folded) {
        expect(plan.solve).not.toBeNull();
        expect(new Set(plan.solve!.source_polygon_id)).toEqual(new Set(junctions.map((s) => s.id)));
        expect(() => loadNet(plan.solve!)).not.toThrow();
        // Folded (self-joined) nets are always full solves, so they get no slots for a diff to start from.
        expect(plan.slots === null).toBe(folded);
        // The solver wants edge ids 0..k-1 with no gaps, even after the terminals are dropped.
        const edgeIds = new Set(plan.solve!.face_edge_ids!.flat());
        expect([...edgeIds].sort((a, b) => a - b)).toEqual([...edgeIds].map((_, i) => i));
      } else {
        expect(plan.solve).toBeNull();
      }
      expect(plan.flats.map((f) => f.shape.id).sort()).toEqual(
        (plan.solve ? terminals : shapes).map((s) => s.id).sort(),
      );
    });
  }

  it("lays a lone piece flat in the plane z = 0 at unit edge length", () => {
    const square: Shape = { id: 7, n: 4, cx: 10, cy: 20, rotation: 0, flipped: false };
    const plan = planPlacement([square], [], 7);
    expect(plan.solve).toBeNull();
    const display = buildDisplay(plan, NO_SOLVE_TOPOLOGY, plan.seedPositions!);
    expect(display.faces).toHaveLength(4);
    for (const p of display.positions.values()) expect(p[2]).toBe(0);
    const [a, b] = [0, 1].map((id) => display.positions.get(id)!);
    expect(Math.hypot(b[0] - a[0], b[1] - a[1])).toBeCloseTo(1);
  });

  it("textures a lone piece with its own African Flower hexagon, one set of corner UVs per triangle", () => {
    const square: Shape = { id: 7, n: 4, cx: 10, cy: 20, rotation: 0, flipped: false };
    const plan = planPlacement([square], [], 7, { 7: { cell: 5, start: 2 } });
    const display = buildDisplay(plan, NO_SOLVE_TOPOLOGY, plan.seedPositions!);
    expect(display.faceUV).toHaveLength(display.faces.length);
    for (const uv of display.faceUV) expect(uv).toHaveLength(6);
    // Cell 5 is column 1, row 1 of the 4 x 4 atlas, so every corner of the piece lies inside that cell.
    for (const uv of display.faceUV) for (let k = 0; k < 6; k += 2) {
      expect(uv[k]).toBeGreaterThanOrEqual(0.25);
      expect(uv[k]).toBeLessThanOrEqual(0.5);
    }
  });

  it("attaches a second square on the far side of the shared edge, in the same plane", () => {
    const left: Shape = { id: 0, n: 4, cx: 0, cy: 0, rotation: 0, flipped: false };
    const right: Shape = { id: 1, n: 4, cx: 100, cy: 0, rotation: 0, flipped: false };
    const join: Connection = {
      id: 0, aShape: 0, aEdge: 1, bShape: 1, bEdge: 3,
      aHandle: { t: 0.5, n: 0 }, bHandle: { t: 0.5, n: 0 },
    } as Connection;
    const plan = planPlacement([left, right], [join], 0);
    expect(plan.solve).toBeNull();
    const display = buildDisplay(plan, NO_SOLVE_TOPOLOGY, plan.seedPositions!);
    // Every corner is in the plane z = 0.
    for (const p of display.positions.values()) expect(p[2]).toBeCloseTo(0);
    // Unit edge length: a square of side 1 sits within a couple of units of the shared edge, not tens of pixels away.
    for (const p of display.positions.values()) expect(Math.hypot(p[0], p[1])).toBeLessThan(3);

    // The seed's centroid and the new piece's centroid sit on opposite sides of their shared edge.
    const seedFace = plan.full.source_polygon_id!.indexOf(0);
    const seedIds = plan.full.faces[seedFace];
    const seedCentre = centroidOf(seedIds.map((id) => plan.seedPositions!.get(id)!));
    const terminalFaces = display.faces.filter((_, f) => display.faceOfFine[f] !== seedFace);
    const terminalIds = [...new Set(terminalFaces.flat())];
    const shared = terminalIds.filter((id) => seedIds.includes(id));
    expect(shared).toHaveLength(2);
    const A = plan.seedPositions!.get(shared[0])!;
    const B = plan.seedPositions!.get(shared[1])!;
    const terminalCentre = centroidOf(terminalIds.filter((id) => !shared.includes(id)).map((id) => display.positions.get(id)!));
    const side = (p: Vec3) => (B[0] - A[0]) * (p[1] - A[1]) - (B[1] - A[1]) * (p[0] - A[0]);
    expect(Math.sign(side(seedCentre))).not.toBe(Math.sign(side(terminalCentre)));
  });
});

function centroidOf(points: Vec3[]): Vec3 {
  const n = points.length;
  return [0, 1, 2].map((k) => points.reduce((s, p) => s + p[k], 0) / n) as Vec3;
}
