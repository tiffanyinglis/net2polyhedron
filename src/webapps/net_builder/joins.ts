import { type Point } from "../utils/geometry";
import { shapeVertices, type Shape } from "./shapes";

/**
 * A connection endpoint's bezier control point, as offsets along its edge's own tangent (t) and outward
 * normal (n) from the edge's midpoint. Relative to the edge, not the far end, so it follows its shape when
 * that shape moves or turns.
 */
export interface Handle {
  t: number;
  n: number;
}

/** Which end of a join: its A end or its B end. */
export type End = "a" | "b";

/** A join between edge `aEdge` of shape `aShape` and edge `bEdge` of shape `bShape` (the same shape for a fold). */
export interface Connection {
  id: number;
  aShape: number;
  aEdge: number;
  bShape: number;
  bEdge: number;
  aHandle: Handle;
  bHandle: Handle;
}

/**
 * The edges that light up together for one edge: if it's joined, its join and both edges the join connects;
 * if it's open, just that edge (connection null).
 */
export function edgeGroup(
  connections: Connection[],
  shape: number,
  edge: number,
): { connection: Connection | null; edges: { shape: number; edge: number }[] } {
  const conn = connections.find(
    (c) => (c.aShape === shape && c.aEdge === edge) || (c.bShape === shape && c.bEdge === edge),
  );
  if (!conn) return { connection: null, edges: [{ shape, edge }] };
  return {
    connection: conn,
    edges: [
      { shape: conn.aShape, edge: conn.aEdge },
      { shape: conn.bShape, edge: conn.bEdge },
    ],
  };
}

/** Bezier samples per connection, as the Python builder draws them. */
const CURVE_STEPS = 24;

/** Edge i runs from vertex i to vertex (i+1) % n, so its index is a stable handle for that edge. */
export function edgeMidpoints(shape: Shape): Point[] {
  const verts = shapeVertices(shape);
  const n = verts.length;
  return verts.map((v, i) => {
    const w = verts[(i + 1) % n];
    return [(v[0] + w[0]) / 2, (v[1] + w[1]) / 2];
  });
}

/** The edge's midpoint (origin), unit tangent from its first corner to its second, and unit normal pointing away from the centroid. */
export function edgeFrame(shape: Shape, edge: number): { origin: Point; tangent: Point; normal: Point } {
  const verts = shapeVertices(shape);
  const n = verts.length;
  const v1 = verts[edge];
  const v2 = verts[(edge + 1) % n];
  const origin: Point = [(v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2];
  const length = Math.hypot(v2[0] - v1[0], v2[1] - v1[1]) || 1;
  const tx = (v2[0] - v1[0]) / length;
  const ty = (v2[1] - v1[1]) / length;
  let nx = -ty;
  let ny = tx;
  const cx = verts.reduce((sum, p) => sum + p[0], 0) / n;
  const cy = verts.reduce((sum, p) => sum + p[1], 0) / n;
  if ((origin[0] - cx) * nx + (origin[1] - cy) * ny < 0) {
    nx = -nx;
    ny = -ny;
  }
  return { origin, tangent: [tx, ty], normal: [nx, ny] };
}

/** World position of a control point. */
export function handleWorld(shape: Shape, edge: number, handle: Handle): Point {
  const { origin, tangent, normal } = edgeFrame(shape, edge);
  return [
    origin[0] + handle.t * tangent[0] + handle.n * normal[0],
    origin[1] + handle.t * tangent[1] + handle.n * normal[1],
  ];
}

/** The handle that puts a control point at `world` on this edge. Inverse of handleWorld. */
export function handleFromWorld(shape: Shape, edge: number, world: Point): Handle {
  const { origin, tangent, normal } = edgeFrame(shape, edge);
  const dx = world[0] - origin[0];
  const dy = world[1] - origin[1];
  return { t: dx * tangent[0] + dy * tangent[1], n: dx * normal[0] + dy * normal[1] };
}

/**
 * Starting handles for a new join: the two control points sit a third and two thirds of the way along the
 * straight line between the edges' midpoints, so a fresh connection draws as that straight line.
 */
export function defaultHandles(a: Shape, aEdge: number, b: Shape, bEdge: number): { aHandle: Handle; bHandle: Handle } {
  const aMid = edgeMidpoints(a)[aEdge];
  const bMid = edgeMidpoints(b)[bEdge];
  const third: Point = [aMid[0] + (bMid[0] - aMid[0]) / 3, aMid[1] + (bMid[1] - aMid[1]) / 3];
  const twoThirds: Point = [aMid[0] + ((bMid[0] - aMid[0]) * 2) / 3, aMid[1] + ((bMid[1] - aMid[1]) * 2) / 3];
  return { aHandle: handleFromWorld(a, aEdge, third), bHandle: handleFromWorld(b, bEdge, twoThirds) };
}

/** The four world points of a connection's cubic bezier: end A, its control point, B's control point, end B. */
export function connectionGeometry(conn: Connection, shapeById: (id: number) => Shape | undefined): [Point, Point, Point, Point] | null {
  const a = shapeById(conn.aShape);
  const b = shapeById(conn.bShape);
  if (!a || !b) return null;
  return [
    edgeMidpoints(a)[conn.aEdge],
    handleWorld(a, conn.aEdge, conn.aHandle),
    handleWorld(b, conn.bEdge, conn.bHandle),
    edgeMidpoints(b)[conn.bEdge],
  ];
}

/** A cubic bezier sampled into a polyline. */
export function sampleCubic(p0: Point, p1: Point, p2: Point, p3: Point): Point[] {
  const points: Point[] = [];
  for (let i = 0; i <= CURVE_STEPS; i++) {
    const t = i / CURVE_STEPS;
    const u = 1 - t;
    const w0 = u * u * u;
    const w1 = 3 * u * u * t;
    const w2 = 3 * u * t * t;
    const w3 = t * t * t;
    points.push([
      w0 * p0[0] + w1 * p1[0] + w2 * p2[0] + w3 * p3[0],
      w0 * p0[1] + w1 * p1[1] + w2 * p2[1] + w3 * p3[1],
    ]);
  }
  return points;
}

/** Distance from point p to the segment ab. */
export function distanceToSegment(p: Point, a: Point, b: Point): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSq = dx * dx + dy * dy;
  const t = lengthSq ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lengthSq)) : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}
