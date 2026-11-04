import { pointInPolygon, type Point } from "../utils/geometry";
import { connectionCurve, countCurveCrossings, type ConnectionCurve } from "./crossings";
import { edgeMidpoints, handleFromWorld, type Connection, type Handle } from "./joins";
import { circumradius, shapeVertices, type Shape } from "./shapes";

/**
 * How far, as a fraction of the straight-line distance between a join's two edge midpoints, each bow
 * candidate below bends that join's curve away from the straight line (both of its control points
 * the same way, so it bows as one simple arc rather than an S). 0 is the straight line itself, always
 * tried first so it wins every tie.
 */
const BOW_FRACTIONS = [0, 0.15, -0.15, 0.3, -0.3, 0.5, -0.5, 0.8, -0.8, 1.1, -1.1, 1.5, -1.5];
/** Coordinate-descent passes: each one revisits every connection once. A pass that improves nothing
 * means the search has settled, so later passes are skipped. */
const MAX_PASSES = 4;

/** The handles that bow a join's curve by `bow` (see BOW_FRACTIONS) instead of leaving it straight. */
function bowHandles(a: Shape, aEdge: number, b: Shape, bEdge: number, bow: number): { aHandle: Handle; bHandle: Handle } {
  const aMid = edgeMidpoints(a)[aEdge];
  const bMid = edgeMidpoints(b)[bEdge];
  const dx = bMid[0] - aMid[0];
  const dy = bMid[1] - aMid[1];
  const dist = Math.hypot(dx, dy) || 1;
  const offset = bow * dist;
  const px = (-dy / dist) * offset;
  const py = (dx / dist) * offset;
  const third: Point = [aMid[0] + dx / 3 + px, aMid[1] + dy / 3 + py];
  const twoThirds: Point = [aMid[0] + (dx * 2) / 3 + px, aMid[1] + (dy * 2) / 3 + py];
  return { aHandle: handleFromWorld(a, aEdge, third), bHandle: handleFromWorld(b, bEdge, twoThirds) };
}

/** A piece's own polygon, pre-sampled once so repeated face-overlap checks against it (see
 * faceOverlap) only need a cheap bounding-circle reject, not a fresh pointInPolygon every time. */
export interface FaceGeom {
  id: number;
  verts: Point[];
  cx: number;
  cy: number;
  r: number;
}

/** faceGeom for a single shape -- see FaceGeom. */
export function faceGeomOf(s: Shape): FaceGeom {
  return { id: s.id, verts: shapeVertices(s), cx: s.cx, cy: s.cy, r: circumradius(s.n) };
}

/** How many of a curve's sample points land inside some OTHER piece's own face -- a cheap stand-in
 * for "this join visibly runs across a piece it has nothing to do with". The two pieces the join
 * itself connects are excluded: it's expected to touch them near their own edges. */
export function faceOverlap(points: Point[], faces: FaceGeom[], excludeA: number, excludeB: number): number {
  let count = 0;
  for (const p of points) {
    for (const f of faces) {
      if (f.id === excludeA || f.id === excludeB) continue;
      const dx = p[0] - f.cx;
      const dy = p[1] - f.cy;
      if (dx * dx + dy * dy > f.r * f.r) continue; // outside the face's own bounding circle
      if (pointInPolygon(p, f.verts)) count++;
    }
  }
  return count;
}

interface Score {
  /** How many other joins' curves this one crosses -- the primary thing a bow is chosen to reduce. */
  crossings: number;
  /** How many of this curve's sample points land inside some face that isn't one of its own two
   * pieces -- a secondary thing to reduce, but never at the cost of a worse crossing count. */
  overlap: number;
}

/** Lexicographic: fewer crossings wins outright; a tie is broken by less face overlap. */
function better(a: Score, b: Score): boolean {
  if (a.crossings !== b.crossings) return a.crossings < b.crossings;
  return a.overlap < b.overlap;
}

/**
 * Bends each join's curve, one at a time over a few passes (greedy coordinate descent), first to
 * dodge around whichever other curves it would otherwise cross, and -- wherever that leaves a choice
 * -- to also keep clear of pieces it has nothing to do with, rather than visibly cutting across their
 * faces. Crossing count always comes first: a bow is only picked over a straight line (or over
 * another bow) for running across fewer faces when it doesn't cost any extra crossings. The only
 * lever left to improve a join's curve once Untangle has already settled on a layout and each piece's
 * rotation. Mutates every connection's handles in place; positions, rotations and the joins
 * themselves are untouched.
 */
export function curveConnectionsToMinimizeCrossings(shapes: Shape[], connections: Connection[]): void {
  const real = connections.filter((c) => c.aShape !== c.bShape);
  if (!real.length) return;
  const byId = new Map(shapes.map((s) => [s.id, s]));
  const shapeById = (id: number) => byId.get(id);
  const faces: FaceGeom[] = shapes.map(faceGeomOf);

  const curveOf = new Map<Connection, ConnectionCurve>();
  for (const c of real) {
    const curve = connectionCurve(c, shapeById);
    if (curve) curveOf.set(c, curve);
  }
  if (!curveOf.size) return;

  const crossingsAgainstOthers = (conn: Connection, curve: ConnectionCurve): number => {
    let total = 0;
    for (const other of real) {
      if (other === conn) continue;
      const oc = curveOf.get(other);
      if (oc) total += countCurveCrossings(curve, oc);
    }
    return total;
  };

  const scoreOf = (conn: Connection, curve: ConnectionCurve): Score => ({
    crossings: crossingsAgainstOthers(conn, curve),
    overlap: faceOverlap(curve.points, faces, conn.aShape, conn.bShape),
  });

  for (let pass = 0; pass < MAX_PASSES; pass++) {
    let improved = false;
    for (const conn of real) {
      const a = shapeById(conn.aShape);
      const b = shapeById(conn.bShape);
      const ownCurve = curveOf.get(conn);
      if (!a || !b || !ownCurve) continue;

      const baseline = scoreOf(conn, ownCurve);
      if (baseline.crossings === 0 && baseline.overlap === 0) continue; // nothing left to gain

      let best = baseline;
      let bestHandles: { aHandle: Handle; bHandle: Handle } = { aHandle: conn.aHandle, bHandle: conn.bHandle };
      let bestCurve = ownCurve;
      for (const bow of BOW_FRACTIONS) {
        if (bow === 0) continue; // the baseline above already covers the straight line
        const handles = bowHandles(a, conn.aEdge, b, conn.bEdge, bow);
        conn.aHandle = handles.aHandle;
        conn.bHandle = handles.bHandle;
        const curve = connectionCurve(conn, shapeById)!;
        const score = scoreOf(conn, curve);
        if (better(score, best)) {
          best = score;
          bestHandles = handles;
          bestCurve = curve;
        }
      }
      conn.aHandle = bestHandles.aHandle;
      conn.bHandle = bestHandles.bHandle;
      curveOf.set(conn, bestCurve);
      if (better(best, baseline)) improved = true;
    }
    if (!improved) break;
  }
}
