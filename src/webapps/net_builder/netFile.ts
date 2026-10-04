import { countPieces, exportMesh, type MeshExport } from "./netExport";
import { defaultHandles, type Connection, type Handle } from "./joins";
import { POLYGON_NS, type Shape } from "./shapes";
import { FACE_COLORS, type ColorMode } from "../utils/colors";

/** The Colour menu state: the mode, each shape's Multi-colour (0xRRGGBB), and its African Flower choice (hexagon cell and starting atom), keyed by shape id. */
export interface NetColors {
  mode: ColorMode;
  multi: Record<number, number>;
  african: Record<number, { cell: number; start: number }>;
}

export function defaultNetColors(): NetColors {
  return { mode: "polygon", multi: {}, african: {} };
}

/** The `colors` block of a `.poly`: the mode and the colours in use, in net_layout order (one entry per shape). */
export interface NetColorsFile {
  mode: ColorMode;
  multi_colors: number[];
  african: { shape_id: number; cell: number; start: number }[];
}

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
  colors: NetColorsFile;
}

/**
 * Serialises the net. Only one connected piece can be saved: a plain net file has no way to say which piece
 * is the centre, so separate pieces are refused. Validation of the joins happens in exportMesh.
 */
export function netFileFrom(
  shapes: Shape[],
  connections: Connection[],
  name: string,
  viewScale: number,
  colors: NetColors = defaultNetColors(),
): NetFile {
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
    colors: colorsFileFrom(shapes, colors),
  };
}

/**
 * Reads a net back. Shape ids are kept as saved, since the joins refer to them. Joins without handles get the
 * straight-line defaults, as in the Python builder.
 */
export function shapesFrom(raw: unknown): {
  shapes: Shape[];
  connections: Connection[];
  viewScale: number | null;
  colors: NetColors | null;
} {
  const file = raw as {
    faces?: unknown;
    net_layout?: unknown;
    builder_connections?: unknown;
    view?: { scale?: unknown };
    colors?: unknown;
  };
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
  return { shapes, connections, viewScale: typeof scale === "number" ? scale : null, colors: colorsFrom(file.colors, shapes) };
}

/** The colour block for a file: one multi-colour per shape in net_layout order, and every shape's African choice. */
function colorsFileFrom(shapes: Shape[], colors: NetColors): NetColorsFile {
  return {
    mode: colors.mode,
    multi_colors: shapes.map((s, i) => colors.multi[s.id] ?? FACE_COLORS[i % FACE_COLORS.length]),
    african: shapes.map((s) => ({ shape_id: s.id, ...(colors.african[s.id] ?? { cell: 0, start: 0 }) })),
  };
}

/** Reads a file's colour block back, or null if it has none (an older file). */
function colorsFrom(raw: unknown, shapes: Shape[]): NetColors | null {
  if (!raw || typeof raw !== "object") return null;
  const block = raw as Partial<NetColorsFile>;
  const modes: ColorMode[] = ["polygon", "multi", "african"];
  const colors = defaultNetColors();
  colors.mode = modes.includes(block.mode as ColorMode) ? (block.mode as ColorMode) : "polygon";
  shapes.forEach((s, i) => {
    const multi = block.multi_colors?.[i];
    if (typeof multi === "number") colors.multi[s.id] = multi;
  });
  for (const entry of block.african ?? []) {
    colors.african[Number(entry.shape_id)] = { cell: Number(entry.cell), start: Number(entry.start) };
  }
  return colors;
}
