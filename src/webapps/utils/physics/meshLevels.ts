import { type Vec3 } from "./vec3";
import { EDGE_LENGTH, type Mesh, type NetSpec } from "./mesh";
import { add, scale } from "./vec3";
import { spreadPick } from "../colors";

type FanEntry = [number | "C", number | "C", number | "C"];

/** Centroid-fan triangulation for n = 3..8 (mirrors utils.subdivisions.polygon_subdivisions.
 * SUBDIVISIONS), plus mesh_levels.py's own local n=3 override (_TRIANGLE_FAN): a plain triangle
 * is otherwise perfectly rigid at the vertex level, so it's fanned too, giving it the same
 * spoke-based freedom to dome under pressure that a quad/pentagon/etc. already has. Every entry is
 * [i, i+1, "C"], so its base edge is face edge i. */
const SUBDIVISIONS: Record<number, FanEntry[]> = {
  3: [[0, 1, "C"], [1, 2, "C"], [2, 0, "C"]],
  4: [[0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 0, "C"]],
  5: [[0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 4, "C"], [4, 0, "C"]],
  6: [[0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 4, "C"], [4, 5, "C"], [5, 0, "C"]],
  7: [[0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 4, "C"], [4, 5, "C"], [5, 6, "C"], [6, 0, "C"]],
  8: [
    [0, 1, "C"], [1, 2, "C"], [2, 3, "C"], [3, 4, "C"],
    [4, 5, "C"], [5, 6, "C"], [6, 7, "C"], [7, 0, "C"],
  ],
};

function spokeRestLength(n: number, edgeLength: number): number {
  return edgeLength / (2 * Math.sin(Math.PI / n));
}

export interface Level1Topology {
  mesh: Mesh;
  faceOfFine: number[];
  /** Per fine triangle: its rim edge is an open boundary edge (see fanLevel0To1). */
  faceOpen: boolean[];
  /** Per fine triangle: the texture coordinates of its three corners, as [u0, v0, u1, v1, u2, v2]. */
  faceUV: number[][];
}

/** The hexagon texture atlas: a grid of HEX_CELLS hexagons, cell h at column h % ATLAS_GRID and row
 * floor(h / ATLAS_GRID) counted from the top. Each hexagon splits into HEX_ATOMS triangle atoms. */
export const HEX_CELLS = 16;
const ATLAS_GRID = 4;
const HEX_ATOMS = 6;

/** Texture coordinates of a point (u, v in the hexagon's own square, v up) inside atlas cell `cell`. */
function cellUV(cell: number, u: number, v: number): [number, number] {
  const col = cell % ATLAS_GRID;
  const row = Math.floor(cell / ATLAS_GRID);
  return [(col + u) / ATLAS_GRID, (ATLAS_GRID - 1 - row + v) / ATLAS_GRID];
}

/** A hexagon's corner number m (of 6, at angle 60 degrees * m) inside atlas cell `cell`. */
function atomCornerUV(cell: number, m: number): [number, number] {
  const a = (Math.PI / 3) * (m % HEX_ATOMS);
  return cellUV(cell, 0.5 + 0.5 * Math.cos(a), 0.5 + 0.5 * Math.sin(a));
}

/** Triangulates every base face via a centroid fan (mirrors mesh_levels._fan_level_0_to_1). Base
 * edges keep their ids; each face corner gets its own spoke id, so a self-joined face's two
 * spokes to the same vertex stay distinct. Centroid positions are not returned -- a real relax
 * starts fresh from random positions. */
/** Per base face: which hexagon it takes its atoms from, and the first atom. */
export type AtlasChoice = { cell: number; start: number }[];

/** A fresh choice for a net: hexagons spread out across neighbours (see spreadPick), starting atoms random. */
/**
 * Which base faces make up one source polygon, and how a self-joined polygon's triangles sit in it. groupOf[f] is
 * the face's source polygon id (its own index when the file has none). For a triangle of a self-joined group,
 * hubIdx[f] is the position of the polygon's centre vertex in the face, and wedgeOf[f] is the wedge (rim edge)
 * it takes: the n triangles of an n-gon texture its n wedges, the same hexagon wedge per rim edge.
 */
export interface Grouping {
  groupOf: number[];
  hubIdx: (number | null)[];
  wedgeOf: (number | null)[];
}

/**
 * Groups base faces by source polygon. A source polygon split into several triangles (a self-joined shape) gets
 * its wedges from `outlines` (its corner ids in order, keyed by source id): the centre is the face vertex not on the
 * outline, and each wedge is the outline edge the triangle's rim edge matches.
 */
export function groupingOf(baseFaces: number[][], sourceIds?: number[], outlines?: Map<number, number[]>): Grouping {
  const groupOf = baseFaces.map((_, f) => sourceIds?.[f] ?? f);
  const hubIdx: (number | null)[] = baseFaces.map(() => null);
  const wedgeOf: (number | null)[] = baseFaces.map(() => null);
  const members = new Map<number, number[]>();
  groupOf.forEach((g, f) => members.set(g, [...(members.get(g) ?? []), f]));
  for (const [g, faces] of members) {
    const outline = outlines?.get(g);
    if (faces.length < 2 || !outline) continue;
    const n = outline.length;
    faces.forEach((f, i) => {
      const face = baseFaces[f];
      if (face.length !== 3) return;
      const h = face.findIndex((v) => !outline.includes(v));
      if (h < 0) return;
      const a = face[(h + 1) % 3];
      const b = face[(h + 2) % 3];
      const k = outline.findIndex((v, idx) => v === a && outline[(idx + 1) % n] === b);
      hubIdx[f] = h;
      wedgeOf[f] = k >= 0 ? k : i;
    });
  }
  return { groupOf, hubIdx, wedgeOf };
}

/** The grouping of a net file: its source ids and each self-joined polygon's outline (from `source_polygon`). */
export function groupingOfSpec(spec: NetSpec, baseFaces: number[][]): Grouping {
  const outlines = new Map<number, number[]>();
  (spec.net_layout ?? []).forEach((entry, i) => {
    const outline = spec.source_polygon?.[i];
    if (outline) outlines.set(entry.shape_id ?? i, outline);
  });
  return groupingOf(baseFaces, spec.source_polygon_id, outlines);
}

/**
 * One atlas choice per source polygon: its faces share a hexagon and a starting atom, and a triangle of a
 * self-joined group takes atom start + its wedge.
 */
export function randomAtlasChoice(baseFaces: number[][], grouping?: Grouping): AtlasChoice {
  const groupOf = grouping?.groupOf ?? baseFaces.map((_, f) => f);
  const groups = [...new Set(groupOf)];
  const cells = spreadPick(groups.map((g) => baseFaces[groupOf.indexOf(g)]), HEX_CELLS);
  const cellOf = new Map(groups.map((g, i) => [g, cells[i]]));
  const startOf = new Map(groups.map((g) => [g, Math.floor(Math.random() * HEX_ATOMS)]));
  return baseFaces.map((_, f) => ({ cell: cellOf.get(groupOf[f])!, start: startOf.get(groupOf[f])! }));
}

/**
 * Re-points existing texture coordinates from one atlas choice to another, without re-running the
 * mesh. Changing a face's starting atom turns its hexagon by 60 degrees per step (about the cell's
 * centre); changing its hexagon moves it to another cell. Both are affine, so the midpoints of the
 * quartered levels stay consistent.
 */
export function retargetFaceUV(faceUV: number[][], faceOfFine: number[], from: AtlasChoice, to: AtlasChoice): number[][] {
  return faceUV.map((uv, f) => {
    const b = faceOfFine[f];
    const o = from[b];
    const n = to[b];
    const turns = (((n.start - o.start) % HEX_ATOMS) + HEX_ATOMS) % HEX_ATOMS;
    const a = (Math.PI / 3) * turns;
    const [cos, sin] = [Math.cos(a), Math.sin(a)];
    const oldCol = o.cell % ATLAS_GRID;
    const oldRow = Math.floor(o.cell / ATLAS_GRID);
    const out: number[] = [];
    for (let i = 0; i < 3; i++) {
      // Back to the hexagon's own square (0..1), turn it, then place it in the new cell.
      const x = uv[2 * i] * ATLAS_GRID - oldCol - 0.5;
      const y = uv[2 * i + 1] * ATLAS_GRID - (ATLAS_GRID - 1 - oldRow) - 0.5;
      out.push(...cellUV(n.cell, 0.5 + x * cos - y * sin, 0.5 + x * sin + y * cos));
    }
    return out;
  });
}

export function fanLevel0To1(base: Mesh, choice?: AtlasChoice, grouping?: Grouping): Level1Topology {
  choice ??= randomAtlasChoice(base.faces, grouping);
  const edgeEnds = [...base.edgeEnds];
  const restLengths = [...base.restLengths];
  let nextVertex = Math.max(...base.faces.flat()) + 1;
  const faces: number[][] = [];
  const faceEdgeIds: number[][] = [];
  const faceOfFine: number[] = [];
  const faceOpen: boolean[] = [];
  const faceUV: number[][] = [];
  const uses = new Map<number, number>();
  // Texture: one random hexagon per base face, and its triangles take consecutive atoms from a random
  // starting atom (a pentagon uses five of a hexagon's six). Atoms that meet at a spoke line up.
  const faceVariants = choice;
  for (const id of base.faceEdgeIds.flat()) uses.set(id, (uses.get(id) ?? 0) + 1);
  base.faces.forEach((face, faceIdx) => {
    const n = face.length;
    const { cell, start } = faceVariants[faceIdx];
    const baseIds = base.faceEdgeIds[faceIdx];
    const hub = grouping?.hubIdx[faceIdx];
    const wedge = grouping?.wedgeOf[faceIdx];
    if (hub !== null && hub !== undefined && wedge !== null && wedge !== undefined) {
      // A wedge of a self-joined polygon is already a fan triangle: its own vertices and spokes, one fine triangle.
      const m = start + wedge;
      const rimA = (hub + 1) % 3;
      const rimB = (hub + 2) % 3;
      const uvOf = (corner: number): [number, number] =>
        corner === rimA ? atomCornerUV(cell, m) : corner === rimB ? atomCornerUV(cell, m + 1) : cellUV(cell, 0.5, 0.5);
      // The hub spokes get the same rest length as a fan's spokes for this polygon's size.
      const size = grouping!.groupOf.filter((g) => g === grouping!.groupOf[faceIdx]).length;
      const spokeLen = spokeRestLength(size, EDGE_LENGTH);
      face.forEach((v, i) => {
        if (v === face[hub] || face[(i + 1) % 3] === face[hub]) restLengths[baseIds[i]] = spokeLen;
      });
      faces.push([...face]);
      faceEdgeIds.push([...baseIds]);
      faceUV.push([0, 1, 2].flatMap((corner) => [...uvOf(corner)]));
      faceOfFine.push(faceIdx);
      // Open like the fan's wedges: its rim edge (the one not touching the hub) has only one face using it.
      faceOpen.push(uses.get(baseIds[rimA]) === 1);
      return;
    }
    const entries = SUBDIVISIONS[n];
    if (!entries) throw new Error(`no hardcoded subdivision for a ${n}-gon`);
    const spokeLen = spokeRestLength(n, EDGE_LENGTH);
    let centroid: number | null = null;
    const spokeIds: number[] = new Array(n);
    const spokeOf = (k: number): number => {
      if (spokeIds[k] === undefined) {
        edgeEnds.push([centroid!, face[k]]);
        restLengths.push(spokeLen);
        spokeIds[k] = edgeEnds.length - 1;
      }
      return spokeIds[k];
    };
    entries.map((e) => [e[0], e[1]] as [number, number]).forEach(([p, q], i) => {
      if (centroid === null) centroid = nextVertex++;
      faces.push([face[p], face[q], centroid]);
      const m = start + i; // this triangle's atom: the hexagon's wedge m, between corners m and m + 1
      faceUV.push([...atomCornerUV(cell, m), ...atomCornerUV(cell, m + 1), ...cellUV(cell, 0.5, 0.5)]);
      faceEdgeIds.push([baseIds[p], spokeOf(q), spokeOf(p)]);
      faceOfFine.push(faceIdx);
      // A wedge is open when its own rim (base edge p) has only one face using it, as in
      // Python's _level1_is_open. Open wedges get no pressure and are left out of RMS.
      faceOpen.push(uses.get(baseIds[p]) === 1);
    });
  });
  return { mesh: { faces, faceEdgeIds, edgeEnds, restLengths }, faceOfFine, faceOpen, faceUV };
}

export interface MeshState {
  mesh: Mesh;
  positions: Map<number, Vec3>;
  faceOfFine: number[];
  faceOpen: boolean[];
  /** Per fine triangle: its corners' texture coordinates (see Level1Topology.faceUV); absent when not tracked. */
  faceUV?: number[][];
  /** Edge ids lying on an original polygon's outer boundary (see polygonOutlineEdgeIds); halves of
   * a subdivided outline edge stay in the set. */
  outlineEdgeIds: Set<number>;
}

/** Splits every triangle into 4 via edge midpoints (mirrors mesh_levels._quarter_triangles for a
 * closed mesh). Each original edge id gets one midpoint, shared by both faces that use it; its two
 * halves are fresh edge ids, each with half the rest length. Each parent triangle's three new
 * internal edges take half their opposite edge's rest length (midsegment theorem). */
export function quarterTriangles(state: MeshState): MeshState {
  const { mesh } = state;
  const positions = new Map(state.positions);
  const edgeEnds = [...mesh.edgeEnds];
  const restLengths = [...mesh.restLengths];
  let nextVertex = Math.max(...positions.keys()) + 1;
  const midpointOf = new Map<number, number>();
  const halfOf = new Map<string, number>();

  const midpoint = (edge: number): number => {
    const existing = midpointOf.get(edge);
    if (existing !== undefined) return existing;
    const [u, v] = mesh.edgeEnds[edge];
    const mid = nextVertex++;
    positions.set(mid, scale(add(positions.get(u)!, positions.get(v)!), 0.5));
    midpointOf.set(edge, mid);
    return mid;
  };
  const addEdge = (a: number, b: number, len: number): number => {
    edgeEnds.push([a, b]);
    restLengths.push(len);
    return edgeEnds.length - 1;
  };
  /** The half of `edge` running from `endpoint` to its midpoint. */
  const outlineEdgeIds = new Set<number>();
  const halfAt = (edge: number, endpoint: number): number => {
    const key = `${edge}:${endpoint}`;
    const existing = halfOf.get(key);
    if (existing !== undefined) return existing;
    const id = addEdge(endpoint, midpoint(edge), mesh.restLengths[edge] / 2);
    if (state.outlineEdgeIds.has(edge)) outlineEdgeIds.add(id);
    halfOf.set(key, id);
    return id;
  };

  const faces: number[][] = [];
  const faceEdgeIds: number[][] = [];
  const faceOfFine: number[] = [];
  const faceUV: number[][] = [];
  const faceOpen: boolean[] = [];
  mesh.faces.forEach((face, f) => {
    const [a, b, c] = face;
    const [eab, ebc, eca] = mesh.faceEdgeIds[f];
    const mab = midpoint(eab);
    const mbc = midpoint(ebc);
    const mca = midpoint(eca);
    const X = addEdge(mab, mbc, mesh.restLengths[eca] / 2);
    const Y = addEdge(mbc, mca, mesh.restLengths[eab] / 2);
    const Z = addEdge(mca, mab, mesh.restLengths[ebc] / 2);
    faces.push([a, mab, mca], [mab, b, mbc], [mca, mbc, c], [mab, mbc, mca]);
    // Each child's texture corners are the midpoints of its parent's, so a wedge is quartered along with its triangle.
    const parentUV = state.faceUV?.[f];
    if (!parentUV) faceUV.push([], [], [], []);
    else {
      const [uvA, uvB, uvC] = [0, 1, 2].map((i) => [parentUV[2 * i], parentUV[2 * i + 1]]);
      const mid = (p: number[], q: number[]) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
      const uvAB = mid(uvA, uvB);
      const uvBC = mid(uvB, uvC);
      const uvCA = mid(uvC, uvA);
      faceUV.push(
        [...uvA, ...uvAB, ...uvCA],
        [...uvAB, ...uvB, ...uvBC],
        [...uvCA, ...uvBC, ...uvC],
        [...uvAB, ...uvBC, ...uvCA],
      );
    }
    faceEdgeIds.push(
      [halfAt(eab, a), Z, halfAt(eca, a)],
      [halfAt(eab, b), halfAt(ebc, b), X],
      [Y, halfAt(ebc, c), halfAt(eca, c)],
      [X, Y, Z],
    );
    for (let i = 0; i < 4; i++) {
      faceOfFine.push(state.faceOfFine[f]);
      faceOpen.push(state.faceOpen[f]);
    }
  });
  return {
    mesh: { faces, faceEdgeIds, edgeEnds, restLengths },
    positions,
    faceOfFine,
    faceOpen,
    faceUV,
    outlineEdgeIds,
  };
}

/** Edge ids on each original polygon's outer boundary, by id (a glued seam shares one id, so it
 * counts as outer on both of its sides). A Polygon-Fold polygon is one or more triangles fanned
 * from a centroid vertex shared by all of them, so its outer edges are the ones not touching that
 * centroid. Any other face is a whole polygon: all of its edges are outer. `groupOfBase[f]` is the
 * polygon that base face f belongs to (its source_polygon_id, or f itself). */
export function polygonOutlineEdgeIds(base: Mesh, groupOfBase: number[]): Set<number> {
  const facesOfGroup = new Map<number, number[]>();
  groupOfBase.forEach((group, f) => facesOfGroup.set(group, [...(facesOfGroup.get(group) ?? []), f]));
  const out = new Set<number>();
  for (const faces of facesOfGroup.values()) {
    if (faces.length === 1) {
      for (const id of base.faceEdgeIds[faces[0]]) out.add(id);
      continue;
    }
    let shared = new Set(base.faces[faces[0]]);
    for (const f of faces.slice(1)) shared = new Set([...shared].filter((v) => base.faces[f].includes(v)));
    const centroid = [...shared][0];
    for (const f of faces) {
      const face = base.faces[f];
      face.forEach((v, i) => {
        const w = face[(i + 1) % face.length];
        if (v !== centroid && w !== centroid) out.add(base.faceEdgeIds[f][i]);
      });
    }
  }
  return out;
}
