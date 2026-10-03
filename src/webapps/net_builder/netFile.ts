import { countPieces, exportMesh, type MeshExport } from "./netExport";
import { defaultHandles, type Connection, type Handle } from "./joins";
import { POLYGON_NS, type Shape } from "./shapes";

/** A `.poly` net file, in the same layout the Python builder writes. */
export interface NetFile extends MeshExport {
  name: string;
  net_layout: { shape_id: number; n: number; cx: number; cy: number; rotation: number; flipped: boolean }[];
  builder_connections: {
    a_shape_id: number;
    a_edge: number;
    b_shape_id: number;
    b_edge: number;
    a_handle: Handle;
    b_handle: Handle;
  }[];
  view: { scale: number };
}

/**
 * Serialises the net. Only one connected piece can be saved: a plain net file has no way to say which piece
 * is the centre, so separate pieces are refused. Validation of the joins happens in exportMesh.
 */
export function netFileFrom(shapes: Shape[], connections: Connection[], name: string, viewScale: number): NetFile {
  if (shapes.length === 0) throw new Error("There's nothing to save yet.");
  const pieces = countPieces(shapes, connections);
  if (pieces > 1) {
    throw new Error(`This net has ${pieces} disconnected pieces. Only a single connected net can be saved. Join the pieces first.`);
  }
  return {
    name,
    ...exportMesh(shapes, connections),
    net_layout: shapes.map((s) => ({
      shape_id: s.id,
      n: s.n,
      cx: s.cx,
      cy: s.cy,
      rotation: s.rotation,
      flipped: s.flipped,
    })),
    builder_connections: connections.map((c) => ({
      a_shape_id: c.aShape,
      a_edge: c.aEdge,
      b_shape_id: c.bShape,
      b_edge: c.bEdge,
      a_handle: { ...c.aHandle },
      b_handle: { ...c.bHandle },
    })),
    view: { scale: viewScale },
  };
}

/**
 * Reads a net back. Shape ids are kept as saved, since the joins refer to them. Joins without handles get the
 * straight-line defaults, as in the Python builder.
 */
export function shapesFrom(raw: unknown): { shapes: Shape[]; connections: Connection[]; viewScale: number | null } {
  const file = raw as { faces?: unknown; net_layout?: unknown; builder_connections?: unknown; view?: { scale?: unknown } };
  if (!Array.isArray(file?.net_layout)) throw new Error("This file has no net layout to load.");
  const faces = Array.isArray(file.faces) ? (file.faces as unknown[]) : [];
  // Older files have no shape_id or n: their layout entries and joins are indexed by face, and each face is one shape.
  const shapes: Shape[] = (file.net_layout as Record<string, unknown>[]).map((entry, index) => {
    const n = Number(entry.n ?? (Array.isArray(faces[index]) ? (faces[index] as unknown[]).length : NaN));
    if (!POLYGON_NS.includes(n)) throw new Error(`Unsupported polygon with ${n} sides.`);
    return {
      id: entry.shape_id !== undefined ? Number(entry.shape_id) : index + 1,
      n,
      cx: Number(entry.cx),
      cy: Number(entry.cy),
      rotation: Number(entry.rotation ?? 0),
      flipped: Boolean(entry.flipped),
    };
  });
  const byId = new Map(shapes.map((s) => [s.id, s]));

  const rawJoins = Array.isArray(file.builder_connections) ? (file.builder_connections as Record<string, unknown>[]) : [];
  const connections: Connection[] = rawJoins.map((c, i) => {
    const a = byId.get(Number(c.a_shape_id ?? (Number(c.a_face) + 1)));
    const b = byId.get(Number(c.b_shape_id ?? (Number(c.b_face) + 1)));
    if (!a || !b) throw new Error("A join refers to a shape that isn't in this net.");
    const aEdge = Number(c.a_edge);
    const bEdge = Number(c.b_edge);
    const fallback = defaultHandles(a, aEdge, b, bEdge);
    return {
      id: i + 1,
      aShape: a.id,
      aEdge,
      bShape: b.id,
      bEdge,
      aHandle: (c.a_handle as Handle | undefined) ?? fallback.aHandle,
      bHandle: (c.b_handle as Handle | undefined) ?? fallback.bHandle,
    };
  });

  const scale = file.view?.scale;
  return { shapes, connections, viewScale: typeof scale === "number" ? scale : null };
}
