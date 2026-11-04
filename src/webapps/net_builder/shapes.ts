import { polygonColor } from "../utils/colors";
import { regularPolygonVertices, type Point } from "../utils/geometry";

/** Polygon sizes on the palette, in display order. */
export const POLYGON_NS = [3, 4, 5, 6, 7, 8];
/** Every placed shape shares this edge length (like every net in this project). */
export const DEFAULT_SHAPE_EDGE_LENGTH = 70;

const LOCAL_VERTICES = new Map(POLYGON_NS.map((n) => [n, regularPolygonVertices(n, DEFAULT_SHAPE_EDGE_LENGTH)]));

export interface Shape {
  id: number;
  n: number;
  cx: number;
  cy: number;
  /** Radians, applied about the shape's own centre. */
  rotation: number;
  /** Flipped shapes read as their other side (hatched), see the Python builder's "Flip" section. */
  flipped: boolean;
}

/** The shape's vertices in world coordinates: its local vertices rotated, then moved to (cx, cy). */
export function shapeVertices(shape: Shape): Point[] {
  const local = LOCAL_VERTICES.get(shape.n)!;
  const c = Math.cos(shape.rotation);
  const s = Math.sin(shape.rotation);
  return local.map(([x, y]) => [shape.cx + x * c - y * s, shape.cy + x * s + y * c]);
}

/** Fill colour of a shape, as a CSS hex string. */
export function shapeCssColor(n: number): string {
  return `#${polygonColor(n).toString(16).padStart(6, "0")}`;
}

/** Radius of the circle every n-gon's corners sit on, at the shared default edge length. A piece never
 * reaches further than this from its own centre, whatever it's rotated to (used by untangle.ts and
 * tutte.ts to guarantee pieces can't overlap from centre distance alone). */
export function circumradius(n: number): number {
  return DEFAULT_SHAPE_EDGE_LENGTH / (2 * Math.sin(Math.PI / n));
}
