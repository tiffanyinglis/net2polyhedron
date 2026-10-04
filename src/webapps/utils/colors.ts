import { type NetLayoutEntry, type NetSpec } from "./physics/mesh";

export type ColorMode = "polygon" | "multi" | "african";

/** The Colour menu's state for one view: the mode, plus the Multi-colour palette (one colour per base face). */
export interface ColorState {
  mode: ColorMode;
  multiColors: number[];
}

/** Multi-colour palette, one colour per piece (56, from the Colour chart). Sampled by eye; mirrored by the Python apps' palette only if updated there too. */
export const FACE_COLORS = [
  0xf1f5e1, 0xf3e0aa, 0xe2c98e, 0xe4b99a, 0xd6af8a, 0xd1a06e, 0xc49c6e, 0xb49578,
  0x6a6150, 0x4a4a42, 0x45453c, 0x8b4513, 0x80461b, 0x6b4422, 0x4e3224, 0x430d0d,
  0x5bb0c8, 0x55b0be, 0x0b7685, 0x00827f, 0x29619a, 0x2c4e80, 0x283860, 0x45408e,
  0xb2b15f, 0x8c9a5c, 0x7e7b3e, 0x4d5322, 0x94ca79, 0x517d3f, 0x264d35, 0x00401f,
  0xd9c21d, 0xdba424, 0xa87b00, 0x9b6617, 0xbb7434, 0xa65230, 0xffa500, 0xff7a1a,
  0xe0572a, 0xe05a2a, 0xd5652a, 0xbe5504, 0xb63d0a, 0xf89a8a, 0xf77f82, 0xf6827c,
  0xe2725e, 0xd83520, 0xb22027, 0xa52a2a, 0x800000, 0x800000, 0x8b0020, 0x640f25,
];
/** African Flower draws its own texture over every polygon, so the base colour is just white under it. */
const AFRICAN_BASE_COLOR = 0xffffff;

/** Two base faces are neighbors iff they share an edge (mirrors mesh_topology.base_face_neighbors). */
export function baseFaceNeighbors(baseFaces: number[][]): Map<number, Set<number>> {
  const edgeOwners = new Map<string, number[]>();
  baseFaces.forEach((face, i) => {
    face.forEach((v, k) => {
      const w = face[(k + 1) % face.length];
      const key = v < w ? `${v},${w}` : `${w},${v}`;
      const owners = edgeOwners.get(key);
      if (owners) owners.push(i);
      else edgeOwners.set(key, [i]);
    });
  });
  const neighbors = new Map<number, Set<number>>(baseFaces.map((_, i) => [i, new Set<number>()]));
  for (const owners of edgeOwners.values()) {
    for (const a of owners) for (const b of owners) if (a !== b) neighbors.get(a)!.add(b);
  }
  return neighbors;
}

/**
 * Picks one of `count` items for each base face, spreading them out: a face avoids the items its
 * neighbours already have where it can, then takes the item used least so far, so as many different
 * items as possible appear. Random order and random tie-breaks. Returns the item index per face.
 */
export function spreadPick(baseFaces: number[][], count: number): number[] {
  const neighbors = baseFaceNeighbors(baseFaces);
  const order = baseFaces.map((_, i) => i);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  const picked: number[] = new Array(baseFaces.length);
  const uses = new Array<number>(count).fill(0);
  for (const i of order) {
    const clash = new Set([...neighbors.get(i)!].map((j) => picked[j]).filter((c) => c !== undefined));
    const all = [...uses.keys()];
    const free = all.filter((c) => !clash.has(c));
    const pool = free.length ? free : all;
    const least = Math.min(...pool.map((c) => uses[c]));
    const best = pool.filter((c) => uses[c] === least);
    const choice = best[Math.floor(Math.random() * best.length)];
    picked[i] = choice;
    uses[choice]++;
  }
  return picked;
}

/** One palette color per base face, spread out so neighbours differ and as many colors as possible appear. */
export function randomFaceColors(baseFaces: number[][], palette: number[] = FACE_COLORS): number[] {
  return spreadPick(baseFaces, palette.length).map((k) => palette[k]);
}

/** Fixed colour per polygon side count (mirrors utils/polygon_colors.POLYGON_COLORS); sides >8 reuse 8's. */
const POLYGON_COLORS: Record<number, number> = {
  3: 0x30914a, 4: 0x24a897, 5: 0x2d85d2, 6: 0x584eda, 7: 0x692dd2, 8: 0x9b2dd2,
};

export function polygonColor(sides: number): number {
  return POLYGON_COLORS[Math.min(8, Math.max(3, sides))];
}

/** Per-face colour by the ORIGINAL polygon's side count, so a hexagon fanned into triangles keeps
 * hexagon colour. A face's polygon is `sourcePolygonIds[f]` (the file's own list); its side count
 * is that shape's `n` in `netLayout`, else the number of faces it was split into. Without
 * sourcePolygonIds (a plain net), each face is its own polygon. */
export function polygonFaceColors(
  baseFaces: number[][],
  sourcePolygonIds?: number[],
  netLayout?: NetLayoutEntry[],
): number[] {
  if (!sourcePolygonIds || sourcePolygonIds.length !== baseFaces.length) {
    return baseFaces.map((f) => polygonColor(f.length));
  }
  const faceCount = new Map<number, number>();
  for (const id of sourcePolygonIds) faceCount.set(id, (faceCount.get(id) ?? 0) + 1);
  const sidesOf = new Map<number, number>();
  for (const entry of netLayout ?? []) {
    if (entry.shape_id !== undefined && entry.n !== undefined) sidesOf.set(entry.shape_id, entry.n);
  }
  return sourcePolygonIds.map((id) => polygonColor(sidesOf.get(id) ?? faceCount.get(id) ?? 3));
}

/** The colour each base face draws with under `colors` -- the one place Inflater and Viewer both get it. */
export function displayColors(
  colors: ColorState,
  baseFaces: number[][],
  spec: Pick<NetSpec, "source_polygon_id" | "net_layout"> | null,
): number[] {
  if (colors.mode === "african") return baseFaces.map(() => AFRICAN_BASE_COLOR);
  return colors.mode === "polygon"
    ? polygonFaceColors(baseFaces, spec?.source_polygon_id, spec?.net_layout)
    : colors.multiColors;
}

/** Regenerates the Multi-colour palette when it's missing or doesn't match the net's face count
 * (mirrors inflate_polyhedron_app's lazy regeneration in _apply_color_mode). */
export function fitMultiColors(colors: ColorState, baseFaces: number[][]) {
  if (colors.multiColors.length !== baseFaces.length) colors.multiColors = randomFaceColors(baseFaces);
}

/**
 * The colour state a `.poly` saved (the net builder's `colors` block), mapped onto each base face through its source
 * polygon. Null if the file has no colours or they don't cover every face.
 */
export function colorsFromFile(
  spec: NetSpec,
  baseFaces: number[][],
): { mode: ColorMode; multiColors: number[]; choice: { cell: number; start: number }[] } | null {
  const block = spec.colors;
  if (!block) return null;
  const layout = spec.net_layout ?? [];
  const shapeOf = (f: number) => spec.source_polygon_id?.[f] ?? layout[f]?.shape_id ?? f;
  const layoutIndexOf = (shape: number) => layout.findIndex((entry, i) => (entry.shape_id ?? i) === shape);
  const multiColors: number[] = [];
  const choice: { cell: number; start: number }[] = [];
  for (let f = 0; f < baseFaces.length; f++) {
    const shape = shapeOf(f);
    const index = layoutIndexOf(shape);
    const multi = index >= 0 ? block.multi_colors?.[index] : undefined;
    const african = block.african?.find((a) => a.shape_id === shape);
    if (typeof multi !== "number" || !african) return null;
    multiColors.push(multi);
    choice.push({ cell: african.cell, start: african.start });
  }
  const mode: ColorMode = block.mode === "multi" || block.mode === "african" ? block.mode : "polygon";
  return { mode, multiColors, choice };
}
