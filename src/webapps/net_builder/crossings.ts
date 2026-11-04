import { segmentsCross, type Point } from "../utils/geometry";
import { connectionGeometry, sampleCubic, type Connection } from "./joins";
import type { Shape } from "./shapes";

/** Sample resolution for crossing detection: coarser than the curve's own draw resolution (good
 * enough to count crossings, and cheap enough to run on every drag frame). A straight connection
 * (as Builder.untangle leaves every connection) is exact at any resolution. */
const CROSSING_SAMPLE_STEPS = 10;

function bbox(points: Point[]): [number, number, number, number] {
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function bboxesOverlap(a: [number, number, number, number], b: [number, number, number, number]): boolean {
  return a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3];
}

function countPolylineCrossings(a: Point[], b: Point[]): number {
  let count = 0;
  for (let i = 0; i + 1 < a.length; i++) {
    for (let k = 0; k + 1 < b.length; k++) {
      if (segmentsCross(a[i], a[i + 1], b[k], b[k + 1])) count++;
    }
  }
  return count;
}

/** One connection's drawn curve, sampled and bounding-boxed once so repeated crossing checks against
 * it (see countCurveCrossings) don't redo either step. */
export interface ConnectionCurve {
  points: Point[];
  bbox: [number, number, number, number];
}

/** Samples a connection's curve as it's drawn (null if either end's shape is missing). */
export function connectionCurve(conn: Connection, shapeById: (id: number) => Shape | undefined): ConnectionCurve | null {
  const g = connectionGeometry(conn, shapeById);
  if (!g) return null;
  const points = sampleCubic(...g, CROSSING_SAMPLE_STEPS);
  return { points, bbox: bbox(points) };
}

/** Proper-intersection count between two already-sampled curves (0 fast-rejected by bounding box). */
export function countCurveCrossings(a: ConnectionCurve, b: ConnectionCurve): number {
  if (!bboxesOverlap(a.bbox, b.bbox)) return 0;
  return countPolylineCrossings(a.points, b.points);
}

/**
 * Total crossings among the net's join curves: every pair of distinct connections' curves (sampled
 * as they're drawn, not the pieces' own outlines), counted by proper line-segment intersections. A
 * straight connection crosses another at most once; a curve dragged into an S-shape can cross it more
 * than once, each one counted. Two connections of the same piece (sharing a corner) don't falsely
 * count: their curves start/end at distinct edge midpoints, so they touch only if actually crossing.
 */
export function countConnectionCrossings(shapes: Shape[], connections: Connection[]): number {
  const byId = new Map(shapes.map((s) => [s.id, s]));
  const shapeById = (id: number) => byId.get(id);
  const curves = connections
    .map((conn) => connectionCurve(conn, shapeById))
    .filter((c): c is ConnectionCurve => c !== null);

  let crossings = 0;
  for (let i = 0; i < curves.length; i++) {
    for (let j = i + 1; j < curves.length; j++) {
      crossings += countCurveCrossings(curves[i], curves[j]);
    }
  }
  return crossings;
}
