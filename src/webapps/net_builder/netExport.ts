/**
 * Turns the placed shapes and their joins into the mesh a `.poly` file stores: faces (vertex loops), explicit
 * edges, per-face-edge ids, and the vertex identity behind them. A port of the Python builder's export section
 * (`_expand_folded_shapes`, `_validate_shapes_connections`, `_faces_from_shapes`, `_edges_from_shapes`,
 * `_face_edge_ids_from_shapes`), so the Inflater reads the web builder's output exactly as it reads the Python one.
 */
import { type Connection } from "./joins";
import { type Shape } from "./shapes";

/** A shape in the mesh: a placed shape, or one triangle of a folded shape's fan. Ids are strings so a triangle can be "shape.index". */
interface MeshShape {
  id: string;
  n: number;
  flipped: boolean;
}

interface MeshConnection {
  aShape: string;
  aEdge: number;
  bShape: string;
  bEdge: number;
}

/** A corner of a mesh shape, keyed "shape:corner". Union-find roots are slots too. */
type Slot = string;

const slot = (shape: string, corner: number): Slot => `${shape}:${corner}`;

/** Thrown when the joins don't make a valid mesh. The message is written for the user to fix. */
export class NetValidationError extends Error {}

/**
 * A Polygon Fold (a connection whose two ends are on the same shape) can't be a flat face gluing itself, so
 * that shape is cut into triangles fanned from its centre, and the fold becomes a join between two of them.
 */
function expandFoldedShapes(shapes: Shape[], connections: Connection[]) {
  const foldIds = new Set(connections.filter((c) => c.aShape === c.bShape).map((c) => c.aShape));
  const meshShapes: MeshShape[] = [];
  const sourcePolygonId: number[] = [];
  for (const shape of shapes) {
    if (foldIds.has(shape.id)) {
      for (let i = 0; i < shape.n; i++) {
        meshShapes.push({ id: `${shape.id}.${i}`, n: 3, flipped: false });
        sourcePolygonId.push(shape.id);
      }
    } else {
      meshShapes.push({ id: String(shape.id), n: shape.n, flipped: shape.flipped });
      sourcePolygonId.push(shape.id);
    }
  }

  const retarget = (shapeId: number, edge: number): [string, number] =>
    foldIds.has(shapeId) ? [`${shapeId}.${edge}`, 0] : [String(shapeId), edge];
  const meshConnections: MeshConnection[] = connections.map((c) => {
    const [aShape, aEdge] = retarget(c.aShape, c.aEdge);
    const [bShape, bEdge] = retarget(c.bShape, c.bEdge);
    return { aShape, aEdge, bShape, bEdge };
  });
  // Consecutive triangles of a fan share one spoke from the centre.
  for (const shape of shapes) {
    if (!foldIds.has(shape.id)) continue;
    for (let i = 0; i < shape.n; i++) {
      meshConnections.push({
        aShape: `${shape.id}.${i}`,
        aEdge: 1,
        bShape: `${shape.id}.${(i + 1) % shape.n}`,
        bEdge: 2,
      });
    }
  }
  return { meshShapes, meshConnections, sourcePolygonId };
}

/** The two corner pairs a connection unions. A flipped shape's edges run the other way, so each pair is taken in its true direction. */
function trueEdgeSlots(shape: MeshShape, edge: number): [Slot, Slot] {
  const a = slot(shape.id, edge);
  const b = slot(shape.id, (edge + 1) % shape.n);
  return shape.flipped ? [b, a] : [a, b];
}

/** The corner order a shape's face loop is read in: reversed when flipped, so every face comes out counter-clockwise from outside. */
function faceCornerOrder(shape: MeshShape): number[] {
  const order = Array.from({ length: shape.n }, (_, i) => i);
  return shape.flipped ? order.reverse() : order;
}

function connectionPairs(byId: Map<string, MeshShape>, conn: MeshConnection): [[Slot, Slot], [Slot, Slot]] {
  const [aV, aW] = trueEdgeSlots(byId.get(conn.aShape)!, conn.aEdge);
  const [bV, bW] = trueEdgeSlots(byId.get(conn.bShape)!, conn.bEdge);
  return [
    [aV, bW],
    [aW, bV],
  ];
}

/** Union-find over every shape's corners. Each root is a corner that stands for the merged vertex, and stays stable under unrelated edits. */
function vertexRoots(shapes: MeshShape[], connections: MeshConnection[]): Map<Slot, Slot> {
  const parent = new Map<Slot, Slot>();
  for (const s of shapes) for (let c = 0; c < s.n; c++) parent.set(slot(s.id, c), slot(s.id, c));
  const find = (x: Slot): Slot => {
    let cur = x;
    while (parent.get(cur) !== cur) cur = parent.get(cur)!;
    return cur;
  };
  const byId = new Map(shapes.map((s) => [s.id, s]));
  for (const conn of connections) {
    for (const [u, v] of connectionPairs(byId, conn)) {
      const rootU = find(u);
      const rootV = find(v);
      if (rootU !== rootV) parent.set(rootU, rootV);
    }
  }
  const roots = new Map<Slot, Slot>();
  for (const s of parent.keys()) roots.set(s, find(s));
  return roots;
}

/** Sequential vertex ids (first seen, in shape and corner order), shared by faces and edges so the two agree. */
function vertexIdsFor(roots: Map<Slot, Slot>) {
  const ids = new Map<Slot, number>();
  const idOf = (s: Slot) => {
    const root = roots.get(s)!;
    if (!ids.has(root)) ids.set(root, ids.size);
    return ids.get(root)!;
  };
  return { idOf };
}

/** Each face's vertex-id loop, ready to store as `faces`. */
function facesFromShapes(shapes: MeshShape[], idOf: (s: Slot) => number): number[][] {
  return shapes.map((shape) => faceCornerOrder(shape).map((corner) => idOf(slot(shape.id, corner))));
}

/**
 * Each source polygon's vertex ids in its own corner order (its net_layout corners): a plain shape's own corners, or for a
 * folded shape the rim corner of each of its triangles, so the square reads as its four corners.
 */
function sourcePolygonsFrom(shapes: Shape[], foldIds: Set<number>, idOf: (s: Slot) => number): number[][] {
  return shapes.map((shape) => {
    const corners = Array.from({ length: shape.n }, (_, k) =>
      foldIds.has(shape.id) ? idOf(slot(`${shape.id}.${k}`, 0)) : idOf(slot(String(shape.id), k)),
    );
    return corners;
  });
}

/** Every genuine mesh edge as a vertex-id pair: each join once, then each free edge. Duplicate pairs are deliberate. */
function edgesFromShapes(shapes: MeshShape[], connections: MeshConnection[]): number[][] {
  const roots = vertexRoots(shapes, connections);
  const { idOf } = vertexIdsFor(roots);
  // Assign ids in face order first, so they match facesFromShapes.
  for (const shape of shapes) for (const corner of faceCornerOrder(shape)) idOf(slot(shape.id, corner));

  const byId = new Map(shapes.map((s) => [s.id, s]));
  const glued = new Set<Slot>();
  for (const c of connections) {
    glued.add(slot(c.aShape, c.aEdge));
    glued.add(slot(c.bShape, c.bEdge));
  }

  const edges: number[][] = [];
  const seen = new Set<string>();
  for (const c of connections) {
    const key = [slot(c.aShape, c.aEdge), slot(c.bShape, c.bEdge)].sort().join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    const n = byId.get(c.aShape)!.n;
    edges.push([idOf(slot(c.aShape, c.aEdge)), idOf(slot(c.aShape, (c.aEdge + 1) % n))]);
  }
  for (const shape of shapes) {
    for (let e = 0; e < shape.n; e++) {
      if (glued.has(slot(shape.id, e))) continue;
      edges.push([idOf(slot(shape.id, e)), idOf(slot(shape.id, (e + 1) % shape.n))]);
    }
  }
  return edges;
}

/** For each face-edge, an id shared by the two faces a join glues and unique otherwise, so subdivision can tell free edges apart. */
function faceEdgeIdsFor(shapes: MeshShape[], connections: MeshConnection[]): number[][] {
  const partner = new Map<Slot, Slot>();
  for (const c of connections) {
    const a = slot(c.aShape, c.aEdge);
    const b = slot(c.bShape, c.bEdge);
    partner.set(a, b);
    partner.set(b, a);
  }
  let nextId = 0;
  const idOf = new Map<Slot, number>();
  return shapes.map((shape) => {
    // Loop position k runs corner order[k] -> order[k+1], which for a flipped shape is raw edge (n - 2 - k) mod n.
    return Array.from({ length: shape.n }, (_, k) => {
      const raw = shape.flipped ? (shape.n - 2 - k + shape.n) % shape.n : k;
      const s = slot(shape.id, raw);
      let cid = idOf.get(s);
      if (cid === undefined) {
        cid = nextId++;
        idOf.set(s, cid);
        const other = partner.get(s);
        if (other !== undefined) idOf.set(other, cid);
      }
      return cid;
    });
  });
}

/** The shortest chain of joins linking slot a to slot b, for explaining a vertex merge. Null if they aren't linked. */
function connectionChain(shapes: MeshShape[], connections: MeshConnection[], a: Slot, b: Slot): MeshConnection[] | null {
  const byId = new Map(shapes.map((s) => [s.id, s]));
  const adjacency = new Map<Slot, [Slot, MeshConnection][]>();
  const link = (u: Slot, v: Slot, conn: MeshConnection) => {
    if (!adjacency.has(u)) adjacency.set(u, []);
    adjacency.get(u)!.push([v, conn]);
  };
  for (const conn of connections) {
    for (const [u, v] of connectionPairs(byId, conn)) {
      link(u, v, conn);
      link(v, u, conn);
    }
  }
  const cameFrom = new Map<Slot, [Slot, MeshConnection] | null>([[a, null]]);
  const queue = [a];
  for (let head = 0; head < queue.length; head++) {
    const cur = queue[head];
    if (cur === b) break;
    for (const [next, conn] of adjacency.get(cur) ?? []) {
      if (!cameFrom.has(next)) {
        cameFrom.set(next, [cur, conn]);
        queue.push(next);
      }
    }
  }
  if (!cameFrom.has(b)) return null;
  const chain: MeshConnection[] = [];
  let cur = b;
  let step = cameFrom.get(cur);
  while (step) {
    chain.push(step[1]);
    cur = step[0];
    step = cameFrom.get(cur);
  }
  return chain.reverse();
}

/** Throws a NetValidationError listing every problem: a face whose own corners merge, or an edge joined twice. */
function validateConnections(shapes: MeshShape[], connections: MeshConnection[]) {
  const roots = vertexRoots(shapes, connections);
  const problems: string[] = [];
  for (const shape of shapes) {
    for (let i = 0; i < shape.n; i++) {
      const [v, w] = trueEdgeSlots(shape, i);
      const rootV = roots.get(v)!;
      if (rootV === roots.get(w)) {
        const chain = connectionChain(shapes, connections, v, w) ?? [];
        const traced = chain.length
          ? ` (traced through: ${chain
              .map((c) => `shape ${c.aShape} edge ${c.aEdge} <-> shape ${c.bShape} edge ${c.bEdge}`)
              .join(" -> ")})`
          : "";
        problems.push(
          `shape ${shape.id} edge ${i} (corners ${v.split(":")[1]}->${w.split(":")[1]}) already merges to the same vertex v${rootV.replace(":", ".")}${traced}`,
        );
      }
    }
  }
  const owners = new Set<Slot>();
  for (const c of connections) {
    for (const s of [slot(c.aShape, c.aEdge), slot(c.bShape, c.bEdge)]) {
      if (owners.has(s)) problems.push(`shape ${s.split(":")[0]} edge ${s.split(":")[1]} is joined by more than one connection`);
      owners.add(s);
    }
  }
  if (problems.length) {
    throw new NetValidationError(`Not a valid net, refusing to save:\n  ${problems.join("\n  ")}`);
  }
}

/** How many separate pieces the shapes form once joined. Zero for an empty net. */
export function countPieces(shapes: Shape[], connections: Connection[]): number {
  if (!shapes.length) return 0;
  const parent = new Map(shapes.map((s) => [s.id, s.id]));
  const find = (x: number): number => {
    let cur = x;
    while (parent.get(cur) !== cur) cur = parent.get(cur)!;
    return cur;
  };
  for (const c of connections) {
    const a = find(c.aShape);
    const b = find(c.bShape);
    if (a !== b) parent.set(a, b);
  }
  return new Set(shapes.map((s) => find(s.id))).size;
}

/** The mesh part of a `.poly` file, as the Python builder writes it. */
export interface MeshExport {
  faces: number[][];
  edges: number[][];
  face_edge_ids: number[][];
  source_polygon_id: number[];
  /** Each source polygon's vertex ids in corner order, one list per source polygon (same order as net_layout). */
  source_polygon: number[][];
}

/** Builds the mesh for a net. Throws NetValidationError if the joins don't form a valid mesh. */
export function exportMesh(shapes: Shape[], connections: Connection[]): MeshExport {
  const { meshShapes, meshConnections, sourcePolygonId } = expandFoldedShapes(shapes, connections);
  validateConnections(meshShapes, meshConnections);
  // Faces take their ids first, so the source polygons (which only look ids up) agree with them.
  const { idOf } = vertexIdsFor(vertexRoots(meshShapes, meshConnections));
  const foldIds = new Set(connections.filter((c) => c.aShape === c.bShape).map((c) => c.aShape));
  return {
    faces: facesFromShapes(meshShapes, idOf),
    edges: edgesFromShapes(meshShapes, meshConnections),
    face_edge_ids: faceEdgeIdsFor(meshShapes, meshConnections),
    source_polygon_id: sourcePolygonId,
    source_polygon: sourcePolygonsFrom(shapes, foldIds, idOf),
  };
}
