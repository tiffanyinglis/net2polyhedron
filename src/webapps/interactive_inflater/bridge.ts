import { exportMesh } from "../net_builder/netExport";
import { type Connection } from "../net_builder/joins";
import { type Shape } from "../net_builder/shapes";
import { type NetSpec } from "../utils/physics/mesh";

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
    source_polygon: mesh.source_polygon,
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
