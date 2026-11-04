import type { Connection } from "./joins";
import { circumradius, type Shape } from "./shapes";

/**
 * Tutte's barycentric embedding: a deterministic, crossing-free straight-line layout for a planar graph,
 * with no local minima to get stuck in. Fix the graph's outer face on a convex polygon, then every other
 * vertex is placed at the average of its neighbours' positions -- a linear system, solved once, not
 * iterated. Tutte's theorem guarantees this is crossing-free for a 3-connected PLANAR graph; this module
 * applies it wherever the net's own piece-adjacency graph (pieces as nodes, joins as edges) qualifies --
 * has a cycle, passes an Euler's-formula check for planarity (V - E + F = 2; see tutteEmbedding), and its
 * largest face visits no piece twice (a practical stand-in for the "3-connected" half of the precondition)
 * -- and leaves the rest (trees, lone pieces, a component that isn't planar in the first place, anything
 * else that doesn't qualify) for the caller to place some other way. The planarity check matters: most
 * nets in this project ARE the dual graph of an actual sphere-like polyhedron (always planar, by
 * Steinitz's theorem), but a net that closes into a handle, or this module's own namesake, a genuinely
 * non-orientable Klein bottle, is not -- forcing a flat embedding onto a non-planar graph collapses
 * several pieces on top of each other instead of spacing them out, which is worse than doing nothing.
 *
 * This only needs the net's combinatorics, not any existing layout: each piece's own edges are already in
 * a fixed cyclic order (0, 1, ..., n-1 round the polygon), which is exactly the "rotation system" a planar
 * embedding is built from -- so the embedding here is derived from the net's structure, not inferred from
 * a (possibly already-crossed) drawing.
 */

interface HalfEdge {
  from: number;
  to: number;
  twin: HalfEdge;
  /** The outgoing half-edge at `from` one step back (cyclically) in ascending own-edge-index order --
   * i.e. the rotation system's sigma-inverse, which is the direction that keeps a face trace on a
   * consistent side of each edge; sigma itself traces the same faces, just walked the other way round. */
  rotationPrev: HalfEdge;
  /** Next half-edge of the same face, walking its boundary: twin's rotationPrev (standard DCEL face trace,
   * i.e. phi = sigma^-1 . alpha on this module's half-edges). */
  faceNext: HalfEdge;
  visited: boolean;
}

/** One outgoing half-edge per (shape, edge) end of every non-self-fold connection, linked into each
 * shape's rotation (sorted by its own edge index) and across to its twin. */
function buildHalfEdges(connections: Connection[]): HalfEdge[] {
  const outgoing = new Map<number, { edgeIndex: number; he: HalfEdge }[]>();
  const add = (from: number, edgeIndex: number, he: HalfEdge) => {
    if (!outgoing.has(from)) outgoing.set(from, []);
    outgoing.get(from)!.push({ edgeIndex, he });
  };
  const halfEdges: HalfEdge[] = [];
  for (const c of connections) {
    if (c.aShape === c.bShape) continue; // a self-fold has no other piece to route a face through
    const ab = { from: c.aShape, to: c.bShape, visited: false } as HalfEdge;
    const ba = { from: c.bShape, to: c.aShape, visited: false } as HalfEdge;
    ab.twin = ba;
    ba.twin = ab;
    halfEdges.push(ab, ba);
    add(c.aShape, c.aEdge, ab);
    add(c.bShape, c.bEdge, ba);
  }
  for (const list of outgoing.values()) {
    list.sort((a, b) => a.edgeIndex - b.edgeIndex);
    list.forEach(({ he }, i) => {
      he.rotationPrev = list[(i - 1 + list.length) % list.length].he;
    });
  }
  for (const he of halfEdges) he.faceNext = he.twin.rotationPrev;
  return halfEdges;
}

/** Every face of the rotation system, each as the cyclic sequence of piece ids on its boundary walk. */
function traceFaces(halfEdges: HalfEdge[]): number[][] {
  const faces: number[][] = [];
  for (const start of halfEdges) {
    if (start.visited) continue;
    const face: number[] = [];
    let current = start;
    do {
      current.visited = true;
      face.push(current.from);
      current = current.faceNext;
    } while (current !== start);
    faces.push(face);
  }
  return faces;
}

/** Union-find over every id in `ids`, merged along `edges`; returns each id's component root. */
function connectedComponents(ids: number[], edges: [number, number][]): Map<number, number> {
  const parent = new Map(ids.map((id) => [id, id]));
  const find = (x: number): number => {
    let r = x;
    while (parent.get(r) !== r) r = parent.get(r)!;
    while (parent.get(x) !== r) {
      const next = parent.get(x)!;
      parent.set(x, r);
      x = next;
    }
    return r;
  };
  for (const [a, b] of edges) {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  }
  const root = new Map<number, number>();
  for (const id of ids) root.set(id, find(id));
  return root;
}

/** Gauss-Jordan elimination with partial pivoting. Null if `a` is (numerically) singular. */
function solveLinearSystem(a: Float64Array[], b: Float64Array): Float64Array | null {
  const n = b.length;
  const m = a.map((row, i) => Float64Array.from([...row, b[i]]));
  for (let col = 0; col < n; col++) {
    let pivot = col;
    for (let row = col + 1; row < n; row++) {
      if (Math.abs(m[row][col]) > Math.abs(m[pivot][col])) pivot = row;
    }
    if (Math.abs(m[pivot][col]) < 1e-9) return null;
    [m[col], m[pivot]] = [m[pivot], m[col]];
    const pivotVal = m[col][col];
    for (let k = col; k <= n; k++) m[col][k] /= pivotVal;
    for (let row = 0; row < n; row++) {
      if (row === col) continue;
      const factor = m[row][col];
      if (factor === 0) continue;
      for (let k = col; k <= n; k++) m[row][k] -= factor * m[col][k];
    }
  }
  return Float64Array.from(m.map((row) => row[n]));
}

/** Barycentric-embeds one connected component (already known to have a cycle): fixes `outer`'s pieces on
 * an evenly-spaced convex polygon, sized to clear their own circumradii, then solves every other piece's
 * position as the average of its neighbours'. Returns null only if the linear system turns out singular
 * (shouldn't happen for a connected graph with a non-empty fixed boundary, but the caller falls back). */
function embedComponent(
  members: number[],
  outer: number[],
  compConns: Connection[],
  byId: Map<number, Shape>,
): Map<number, [number, number]> | null {
  const positions = new Map<number, [number, number]>();
  const n = outer.length;
  const gap = 12;
  const circumference = outer.reduce((sum, id) => sum + 2 * circumradius(byId.get(id)!.n) + gap, 0);
  const radius = Math.max(circumference / (2 * Math.PI), circumradius(byId.get(outer[0])!.n) * 2);
  outer.forEach((id, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    positions.set(id, [radius * Math.cos(angle), radius * Math.sin(angle)]);
  });

  const boundary = new Set(outer);
  const interior = members.filter((id) => !boundary.has(id));
  if (!interior.length) return positions;

  const neighborsOf = new Map<number, number[]>(members.map((id) => [id, []]));
  for (const c of compConns) {
    neighborsOf.get(c.aShape)!.push(c.bShape);
    neighborsOf.get(c.bShape)!.push(c.aShape);
  }
  const index = new Map(interior.map((id, i) => [id, i]));
  const size = interior.length;
  const a = Array.from({ length: size }, () => new Float64Array(size));
  const bx = new Float64Array(size);
  const by = new Float64Array(size);
  interior.forEach((id, row) => {
    const neighbors = neighborsOf.get(id)!;
    a[row][row] = neighbors.length;
    for (const other of neighbors) {
      const col = index.get(other);
      if (col !== undefined) {
        a[row][col] -= 1;
      } else {
        const [px, py] = positions.get(other)!;
        bx[row] += px;
        by[row] += py;
      }
    }
  });
  const xs = solveLinearSystem(a, bx);
  const ys = solveLinearSystem(a, by);
  if (!xs || !ys) return null;
  interior.forEach((id, i) => positions.set(id, [xs[i], ys[i]]));
  return positions;
}

export interface TutteEmbedding {
  /** Every piece's centre this method placed. */
  positions: Map<number, [number, number]>;
}

/**
 * Tutte-embeds whichever of the net's connected piece-groups qualify (see module doc): returns a centre
 * for every piece it could place that way. A piece left out (a tree, a lone piece, a component whose
 * boundary isn't simple) isn't in the result at all -- the caller places those some other way.
 */
export function tutteEmbedding(shapes: Shape[], connections: Connection[]): TutteEmbedding {
  const positions = new Map<number, [number, number]>();
  const byId = new Map(shapes.map((s) => [s.id, s]));
  const ids = shapes.map((s) => s.id);
  const realConns = connections.filter((c) => c.aShape !== c.bShape);
  const roots = connectedComponents(
    ids,
    realConns.map((c): [number, number] => [c.aShape, c.bShape]),
  );

  const byRoot = new Map<number, number[]>();
  for (const id of ids) {
    const root = roots.get(id)!;
    if (!byRoot.has(root)) byRoot.set(root, []);
    byRoot.get(root)!.push(id);
  }

  for (const members of byRoot.values()) {
    if (members.length < 3) continue; // nothing to form a polygon boundary from
    const memberSet = new Set(members);
    const compConns = realConns.filter((c) => memberSet.has(c.aShape));
    if (compConns.length < members.length) continue; // a tree: no cycle, so no face to fix as the boundary

    const faces = traceFaces(buildHalfEdges(compConns));
    if (!faces.length) continue;
    // Tutte's embedding assumes the piece graph is PLANAR -- true for any net whose pieces glue up into
    // a topological sphere or disc (the dual of an actual polyhedron, or any net cut open from one, is
    // always planar), but this project's nets aren't all spheres: a net that closes into a handle or a
    // genuinely non-orientable surface (this module's own namesake, a Klein bottle) has a NON-planar
    // piece graph, and forcing a flat embedding onto it collapses several pieces on top of each other
    // instead of spacing them out -- worse than doing nothing. Euler's formula (V - E + F = 2) holds for
    // a connected planar graph's own rotation system and fails for every higher-genus or non-orientable
    // one, so it's checked before trusting any of this component's faces.
    if (members.length - compConns.length + faces.length !== 2) continue;
    let outer = faces[0];
    for (const face of faces) if (face.length > outer.length) outer = face;
    // A face that visits a piece twice means this component isn't 3-connected (there's a piece whose
    // removal would split it): no single fixed position for that piece to play both boundary roles, so
    // this component doesn't qualify -- the caller falls back to greedy placement for it.
    if (outer.length < 3 || new Set(outer).size !== outer.length) continue;

    const embedded = embedComponent(members, outer, compConns, byId);
    if (embedded) for (const [id, p] of embedded) positions.set(id, p);
  }

  return { positions };
}
