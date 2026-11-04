import { connectionCurve, countCurveCrossings, type ConnectionCurve } from "./crossings";
import { faceGeomOf, faceOverlap, type FaceGeom } from "./curve";
import { connectorQuality, defaultHandles, edgeMidpoints, type Connection } from "./joins";
import { rotationFacingNeighbors } from "./rotate";
import { circumradius, DEFAULT_SHAPE_EDGE_LENGTH, type Shape } from "./shapes";

/**
 * Builds the net's layout up breadth-first, one ring of pieces at a time, instead of solving or settling
 * into it all at once. Starting from the net's single most-joined piece (standing in for "a random piece"
 * -- this module picks it deterministically so the result is reproducible, but any starting piece works,
 * just with its own crossing count), the whole first ring of its direct neighbours is placed next, then
 * the ring of THEIR unplaced neighbours, and so on outward -- so a piece is never placed before anything
 * closer to the root that could still anchor it. Within a ring, whichever piece is most connected to what's
 * already down goes first (ties go to the piece that's more joined overall, then to the lower id), the same
 * growing-pull that mattered when this was a single flat priority queue -- only now it only ever reaches
 * into the current ring, not pieces several rings further out. Each piece is tried at a ring of candidate
 * positions and, at each position, the rotation that best faces the already-placed neighbours it joins to
 * -- the candidate that adds the fewest crossings against every curve placed so far wins; a tie (most often
 * both zero) goes to whichever candidate leaves its own joins shortest and squarest to their edges (see
 * connectorQuality in joins.ts) -- the fold-line ideal a real paper join needs, and never worth trading a
 * single crossing for. Its joins are then drawn as straight lines before the next piece is chosen. A piece
 * with nothing already placed to connect to (a separate component) seeds a new area clear of everything so
 * far, and becomes that area's own root
 * for the same breadth-first walk. Doesn't guarantee zero crossings (nothing greedy can, especially on a
 * non-planar piece graph), but it minimises crossings as it goes rather than only afterward. The `pinned`
 * parameter lets a caller hand in positions it has already committed to by some other means: those pieces
 * are left exactly where they are, but still seed the very first ring, same as a root normally would.
 */

/** Evenly spaced placement angles tried around each candidate ring. */
const ANGLE_CANDIDATES = 24;
/** Multiples of a piece's own base clearance tried, growing until some candidate ring has room. */
const RADIUS_GROWTH = [1, 1.3, 1.6, 2, 2.6, 3.4, 4.5, 6];
/** Extra clearance added to two joined pieces' circumradii, matching untangle.ts's own spring rest length. */
const JOIN_MARGIN = 20;
/** Clearance kept between two pieces' circumradii when checking a candidate for overlap. */
const OVERLAP_MARGIN = 4;
/** Weight that makes a join's squareness penalty (0-1 per join) comparable to its length penalty (in the
 * same px units as every other distance here), so neither dominates the other when they trade off. */
const SQUARENESS_WEIGHT = DEFAULT_SHAPE_EDGE_LENGTH;

export interface GreedyLayout {
  positions: Map<number, [number, number]>;
  rotations: Map<number, number>;
  /** Every id in the order this placed it: the breadth-first walk itself, pinned pieces first (see the
   * module doc comment) -- a caller that wants to show the net being built up, not just the result it
   * ends at, replays positions/rotations in this order. */
  order: number[];
}

interface Neighbor {
  /** This piece's own edge the join uses. */
  edge: number;
  otherId: number;
  otherEdge: number;
  conn: Connection;
}

/** Greedily places every piece this module is asked to (i.e. every id not already in `pinned`), one at a
 * time, to minimise the crossings each addition creates. See the module doc comment. `pinned` lets a
 * caller hand in positions it has already committed to by some other means (Tutte's embedding, say): those
 * pieces are left exactly where they are, but still count as already-placed -- their own joins to each
 * other are drawn and treated as curves the rest of this net must dodge, and their footprint is something
 * a fresh, otherwise-disconnected piece is seeded clear of, same as any other already-placed piece. Doesn't
 * mutate `shapes` or `connections`; join handles on the connections passed in are read for identity only
 * (aShape/aEdge/bShape/bEdge), never for their existing curve. */
export function greedyPlacement(
  shapes: Shape[],
  connections: Connection[],
  pinned: Map<number, [number, number]> = new Map(),
): GreedyLayout {
  const positions = new Map<number, [number, number]>();
  const rotations = new Map(shapes.map((s) => [s.id, s.rotation]));
  const order: number[] = [];
  if (!shapes.length) return { positions, rotations, order };

  // A working copy: this module places pieces by mutating cx/cy/rotation as it goes (so the geometry
  // helpers below, which all take a Shape, read the layout being built), without touching the caller's own.
  const working = shapes.map((s) => {
    const p = pinned.get(s.id);
    return p ? { ...s, cx: p[0], cy: p[1] } : { ...s };
  });
  const byId = new Map(working.map((s) => [s.id, s]));
  const shapeById = (id: number) => byId.get(id);

  const real = connections.filter((c) => c.aShape !== c.bShape); // a self-fold has no other piece to place
  const neighborsOf = new Map<number, Neighbor[]>(working.map((s) => [s.id, []]));
  for (const c of real) {
    neighborsOf.get(c.aShape)!.push({ edge: c.aEdge, otherId: c.bShape, otherEdge: c.bEdge, conn: c });
    neighborsOf.get(c.bShape)!.push({ edge: c.bEdge, otherId: c.aShape, otherEdge: c.aEdge, conn: c });
  }
  const degree = new Map(working.map((s) => [s.id, neighborsOf.get(s.id)!.length]));
  const radius = new Map(working.map((s) => [s.id, circumradius(s.n)]));

  const placed = new Set<number>();
  const remaining = new Set(working.map((s) => s.id));
  const placedCurves: ConnectionCurve[] = [];
  /** Every already-placed piece's own face, for faceOverlap -- grows alongside placedCurves in commit(). */
  const placedFaces: FaceGeom[] = [];

  const strengthenHandles = (conn: Connection) => {
    const a = byId.get(conn.aShape)!;
    const b = byId.get(conn.bShape)!;
    const handles = defaultHandles(a, conn.aEdge, b, conn.bEdge);
    conn.aHandle = handles.aHandle;
    conn.bHandle = handles.bHandle;
  };

  /** Settles `id` at its current (already decided) working position: records it, and draws straight
   * lines for every join to an already-placed neighbour, adding them to what later placements dodge. */
  const commit = (id: number) => {
    const shape = byId.get(id)!;
    positions.set(id, [shape.cx, shape.cy]);
    rotations.set(id, shape.rotation);
    order.push(id);
    placed.add(id);
    remaining.delete(id);
    placedFaces.push(faceGeomOf(shape));
    for (const nb of neighborsOf.get(id)!) {
      if (!placed.has(nb.otherId)) continue;
      strengthenHandles(nb.conn);
      const curve = connectionCurve(nb.conn, shapeById);
      if (curve) placedCurves.push(curve);
    }
  };

  /** This piece's total connectorQuality penalty across `neighbors`, at its current (candidate) position
   * and rotation: the sum of each join's length plus its squareness weighted into the same units -- lower
   * is better, and it bottoms out near each join's edge length once every join is both short and square. */
  const connectionPenalty = (shape: Shape, neighbors: Neighbor[]): number => {
    let penalty = 0;
    for (const nb of neighbors) {
      const other = byId.get(nb.otherId)!;
      const { length, squareness } = connectorQuality(shape, nb.edge, other, nb.otherEdge);
      penalty += length + SQUARENESS_WEIGHT * squareness;
    }
    return penalty;
  };

  /** Lexicographic: fewer crossings wins outright; a tie goes to less face overlap, and a further tie
   * to the shorter, squarer connectionPenalty -- the same crossings-first, never-traded-away ordering
   * curve.ts's own bow search uses, extended with a third level for this module's own tie-breaks. */
  const better = (
    a: { crossings: number; overlap: number; penalty: number },
    b: { crossings: number; overlap: number; penalty: number },
  ): boolean => {
    if (a.crossings !== b.crossings) return a.crossings < b.crossings;
    if (a.overlap !== b.overlap) return a.overlap < b.overlap;
    return a.penalty < b.penalty;
  };

  /** Tries a ring of candidate positions (growing outward until some are overlap-free) around `anchor`,
   * each at the rotation that best faces `neighbors`, and settles the piece on whichever adds the fewest
   * crossings against every curve already placed; a crossings tie goes to whichever candidate cuts across
   * the fewest other pieces' own faces (see faceOverlap in curve.ts), and a further tie to whichever
   * leaves its own joins shortest and squarest (see connectionPenalty). Once some candidate in a ring
   * reaches zero crossings, growth stops there rather than trying a larger (and so longer-jointed) ring
   * for no gain. */
  const placeAt = (id: number, anchor: [number, number], baseRadius: number, neighbors: Neighbor[]) => {
    const shape = byId.get(id)!;
    const selfR = radius.get(id)!;
    let best: { x: number; y: number; rotation: number; crossings: number; overlap: number; penalty: number } | null = null;

    outer: for (const growth of RADIUS_GROWTH) {
      const r = baseRadius * growth;
      let ringHadZeroCrossings = false;
      for (let i = 0; i < ANGLE_CANDIDATES; i++) {
        const angle = (2 * Math.PI * i) / ANGLE_CANDIDATES;
        const x = anchor[0] + r * Math.cos(angle);
        const y = anchor[1] + r * Math.sin(angle);

        let pieceOverlaps = false;
        for (const pid of placed) {
          const p = byId.get(pid)!;
          if (Math.hypot(x - p.cx, y - p.cy) < selfR + radius.get(pid)! + OVERLAP_MARGIN) {
            pieceOverlaps = true;
            break;
          }
        }
        if (pieceOverlaps) continue;

        const resolvedJoins = neighbors.map((nb) => {
          const p = byId.get(nb.otherId)!;
          return { edge: nb.edge, position: edgeMidpoints(p)[nb.otherEdge] };
        });
        const rotation = resolvedJoins.length
          ? rotationFacingNeighbors(shape.n, shape.rotation, resolvedJoins, [x, y])
          : shape.rotation;

        shape.cx = x;
        shape.cy = y;
        shape.rotation = rotation;

        let crossings = 0;
        let overlap = 0;
        const candidateCurves: ConnectionCurve[] = [];
        for (const nb of neighbors) {
          strengthenHandles(nb.conn);
          const curve = connectionCurve(nb.conn, shapeById);
          if (!curve) continue;
          for (const other of placedCurves) crossings += countCurveCrossings(curve, other);
          for (const existing of candidateCurves) crossings += countCurveCrossings(curve, existing);
          overlap += faceOverlap(curve.points, placedFaces, nb.conn.aShape, nb.conn.bShape);
          candidateCurves.push(curve);
        }
        if (crossings === 0) ringHadZeroCrossings = true;

        const penalty = connectionPenalty(shape, neighbors);
        const candidate = { x, y, rotation, crossings, overlap, penalty };
        if (!best || better(candidate, best)) best = candidate;
      }
      if (ringHadZeroCrossings) break outer;
    }

    // Every tried ring overlapped something -- shouldn't happen once growth is large enough, but this
    // guarantees progress rather than leaving the piece unplaced.
    if (!best) {
      const r = Math.max(baseRadius, selfR) * RADIUS_GROWTH[RADIUS_GROWTH.length - 1] * 2;
      best = { x: anchor[0] + r, y: anchor[1], rotation: shape.rotation, crossings: Infinity, overlap: Infinity, penalty: Infinity };
    }

    shape.cx = best.x;
    shape.cy = best.y;
    shape.rotation = best.rotation;
  };

  const placeNext = (id: number) => {
    const shape = byId.get(id)!;
    const neighbors = neighborsOf.get(id)!.filter((nb) => placed.has(nb.otherId));

    if (neighbors.length) {
      let sx = 0;
      let sy = 0;
      let rSum = 0;
      for (const nb of neighbors) {
        const p = byId.get(nb.otherId)!;
        const mid = edgeMidpoints(p)[nb.otherEdge];
        sx += mid[0];
        sy += mid[1];
        rSum += radius.get(nb.otherId)!;
      }
      const anchor: [number, number] = [sx / neighbors.length, sy / neighbors.length];
      const baseRadius = radius.get(id)! + rSum / neighbors.length + JOIN_MARGIN;
      placeAt(id, anchor, baseRadius, neighbors);
      return;
    }

    if (!placed.size) {
      shape.cx = 0;
      shape.cy = 0;
      return;
    }

    // A separate component: seed it clear of the bounding circle of everything placed so far.
    let sx = 0;
    let sy = 0;
    for (const pid of placed) {
      const p = byId.get(pid)!;
      sx += p.cx;
      sy += p.cy;
    }
    const anchor: [number, number] = [sx / placed.size, sy / placed.size];
    let maxExtent = 0;
    for (const pid of placed) {
      const p = byId.get(pid)!;
      const d = Math.hypot(p.cx - anchor[0], p.cy - anchor[1]) + radius.get(pid)!;
      if (d > maxExtent) maxExtent = d;
    }
    const baseRadius = maxExtent + radius.get(id)! + JOIN_MARGIN * 2;
    placeAt(id, anchor, baseRadius, neighbors);
  };

  for (const [id, pos] of pinned) {
    const shape = byId.get(id);
    if (!shape) continue;
    shape.cx = pos[0];
    shape.cy = pos[1];
    commit(id);
  }

  /** Picks the best next piece from a specific pool (a BFS ring, or the whole remaining set when starting
   * a fresh component): most links to the already-placed set, then most joined overall, then lowest id. */
  const pickBest = (pool: Iterable<number>): number => {
    let bestId = -1;
    let bestLinks = -1;
    let bestDegree = -1;
    for (const id of pool) {
      const links = neighborsOf.get(id)!.filter((nb) => placed.has(nb.otherId)).length;
      const d = degree.get(id)!;
      if (
        links > bestLinks ||
        (links === bestLinks && (d > bestDegree || (d === bestDegree && (bestId === -1 || id < bestId))))
      ) {
        bestId = id;
        bestLinks = links;
        bestDegree = d;
      }
    }
    return bestId;
  };

  /** Every unplaced, not-yet-queued neighbour of `ids`, in no particular order -- the next BFS ring. */
  const nextRing = (ids: Iterable<number>, queued: Set<number>): number[] => {
    const ring: number[] = [];
    for (const id of ids) {
      for (const nb of neighborsOf.get(id)!) {
        if (placed.has(nb.otherId) || queued.has(nb.otherId)) continue;
        queued.add(nb.otherId);
        ring.push(nb.otherId);
      }
    }
    return ring;
  };

  const queued = new Set<number>(placed);
  let ring = nextRing(placed, queued);

  while (remaining.size) {
    if (!ring.length) {
      // Nothing left to grow outward from: either the very first piece, or a fresh, disconnected
      // component -- either way, pick a new root the same way the original piece was chosen.
      const root = pickBest(remaining);
      ring = [root];
      queued.add(root);
    }

    const pool = new Set(ring);
    while (pool.size) {
      const id = pickBest(pool);
      pool.delete(id);
      placeNext(id);
      commit(id);
    }

    ring = nextRing(ring, queued);
  }

  return { positions, rotations, order };
}
