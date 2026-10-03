import { exportMesh } from "../net_builder/netExport";
import { type Connection } from "../net_builder/joins";
import { shapeVertices, type Shape } from "../net_builder/shapes";
import { loadNet, type NetSpec } from "../utils/physics/mesh";
import { fanLevel0To1, polygonOutlineEdgeIds } from "../utils/physics/meshLevels";
import { type Vec3 } from "../utils/physics/vec3";
import { type LevelTopology } from "../utils/inflaterRun";

/**
 * The owner's connected group (the Python app's "active group"): the only shapes and connections
 * the solver sees. Pieces outside it stay on the builder canvas but are not inflated.
 */
export function activeGroup(
  shapes: Shape[],
  connections: Connection[],
  ownerId: number | null,
): { shapes: Shape[]; connections: Connection[] } {
  if (ownerId === null) return { shapes: [], connections: [] };
  const reached = new Set<number>([ownerId]);
  const pending = [ownerId];
  while (pending.length) {
    const id = pending.pop()!;
    for (const c of connections) {
      const other = c.aShape === id ? c.bShape : c.bShape === id ? c.aShape : null;
      if (other !== null && !reached.has(other)) {
        reached.add(other);
        pending.push(other);
      }
    }
  }
  return {
    shapes: shapes.filter((s) => reached.has(s.id)),
    connections: connections.filter((c) => reached.has(c.aShape) && reached.has(c.bShape)),
  };
}

/**
 * The solver's NetSpec for the builder's current shapes and joins, built in memory. The Python app
 * writes a throwaway .poly for this because its parser needs a path; the web port passes the object
 * straight to loadNet. Throws NetValidationError if the joins don't form a valid mesh.
 */
export function netSpecFromBuilder(shapes: Shape[], connections: Connection[], name = "net"): NetSpec {
  const mesh = exportMesh(shapes, connections);
  return {
    name,
    faces: mesh.faces,
    face_edge_ids: mesh.face_edge_ids,
    source_polygon_id: mesh.source_polygon_id,
    // Side count per shape, so the solver colours each face by its own polygon, as the builder draws it.
    net_layout: shapes.map((shape) => ({ shape_id: shape.id, n: shape.n, cx: shape.cx, cy: shape.cy, rotation: shape.rotation })),
  };
}

/**
 * What the solver depends on: the faces and how they are joined. Moving or rotating pieces leaves
 * it unchanged, so it doesn't trigger a new inflate. Null if the net isn't a valid mesh.
 */
export function structureKey(shapes: Shape[], connections: Connection[]): string | null {
  try {
    const spec = netSpecFromBuilder(shapes, connections, "net");
    return JSON.stringify({ faces: spec.faces, face_edge_ids: spec.face_edge_ids, source_polygon_id: spec.source_polygon_id });
  } catch {
    return null;
  }
}

/**
 * A lone piece has nothing to solve, so it is shown flat, as the Python app does: its own polygon,
 * fanned into triangles, lying in the plane z = 0. Scaled to unit edge length like the solver's
 * output, since the Viewer's camera clips anything tens of units away.
 */
export function flatPiece(shape: Shape): { spec: NetSpec; topology: LevelTopology; positions: Map<number, Vec3> } {
  const spec = netSpecFromBuilder([shape], [], "piece");
  const base = loadNet(spec);
  const fan = fanLevel0To1(base);
  const corners = shapeVertices(shape);
  const [[x0, y0], [x1, y1]] = corners;
  const scale = 1 / Math.hypot(x1 - x0, y1 - y0);
  const positions = new Map<number, Vec3>(corners.map(([x, y], i) => [i, [x * scale, y * scale, 0]]));
  // A single face's fan centroid is the next vertex id after its corners, at their average.
  const cx = corners.reduce((sum, [x]) => sum + x, 0) / corners.length;
  const cy = corners.reduce((sum, [, y]) => sum + y, 0) / corners.length;
  positions.set(corners.length, [cx * scale, cy * scale, 0]);
  return {
    spec,
    topology: {
      faces: fan.mesh.faces,
      faceOfFine: fan.faceOfFine,
      faceEdgeIds: fan.mesh.faceEdgeIds,
      outlineEdgeIds: polygonOutlineEdgeIds(base, spec.source_polygon_id ?? [0]),
    },
    positions,
  };
}
