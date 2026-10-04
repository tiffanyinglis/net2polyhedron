import { type NetLayoutEntry, type NetSpec } from "./physics/mesh";

export type ColorMode = "polygon" | "multi" | "african";

/** The Colour menu's state for one view: the mode, plus the Multi-colour palette (one colour per base face). */
export interface ColorState {
  mode: ColorMode;
  multiColors: number[];
}

/** Multi-colour support (mirrors common/ui_theme.FACE_COLORS and utils/graph_face_coloring). */
const BRIGHT = [0x003a7d, 0x008dff, 0xff73b6, 0xc701ff, 0x4ecb8d, 0xff9d3a, 0xf9e858, 0xd83034];
const ALTERNATING_LIGHT_DARK = [0x8fd7d7, 0x00b0be, 0xff8ca1, 0xf45f74, 0xbdd373, 0x98c127, 0xffcd8e, 0xffb255];
export const FACE_COLORS = [...BRIGHT, ...ALTERNATING_LIGHT_DARK];
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
