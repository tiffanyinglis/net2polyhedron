import { exportMesh } from "../net_builder/netExport";
import { type Connection } from "../net_builder/joins";
import { type Shape } from "../net_builder/shapes";
import { type NetSpec } from "../utils/physics/mesh";

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
  };
}
