/** Multi-colour support (mirrors common/ui_theme.FACE_COLORS and utils/graph_face_coloring). */
const BRIGHT = [0x003a7d, 0x008dff, 0xff73b6, 0xc701ff, 0x4ecb8d, 0xff9d3a, 0xf9e858, 0xd83034];
const ALTERNATING_LIGHT_DARK = [0x8fd7d7, 0x00b0be, 0xff8ca1, 0xf45f74, 0xbdd373, 0x98c127, 0xffcd8e, 0xffb255];
export const FACE_COLORS = [...BRIGHT, ...ALTERNATING_LIGHT_DARK];

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

/** One palette color per base face, random order, avoiding already-colored neighbors where possible
 * (mirrors graph_face_coloring.random_graph_coloring). */
export function randomFaceColors(baseFaces: number[][], palette: number[] = FACE_COLORS): number[] {
  const neighbors = baseFaceNeighbors(baseFaces);
  const order = baseFaces.map((_, i) => i);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  const colors: number[] = new Array(baseFaces.length);
  for (const i of order) {
    const used = new Set([...neighbors.get(i)!].map((j) => colors[j]).filter((c) => c !== undefined));
    const free = palette.filter((c) => !used.has(c));
    const candidates = free.length ? free : palette;
    colors[i] = candidates[Math.floor(Math.random() * candidates.length)];
  }
  return colors;
}

/** Fixed colour per polygon side count (mirrors utils/polygon_colors.POLYGON_COLORS); sides >8 reuse 8's. */
const POLYGON_COLORS: Record<number, number> = {
  3: 0x30914a, 4: 0x24a897, 5: 0x2d85d2, 6: 0x584eda, 7: 0x692dd2, 8: 0x9b2dd2,
};

export function polygonColor(sides: number): number {
  return POLYGON_COLORS[Math.min(8, Math.max(3, sides))];
}

export function polygonFaceColors(baseFaces: number[][]): number[] {
  return baseFaces.map((f) => polygonColor(f.length));
}
