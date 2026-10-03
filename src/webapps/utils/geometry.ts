export type Point = [number, number];

/** CCW vertices of a regular k-gon centred on the origin, with edge 0 running from vertex 0 to vertex 1
 * (mirrors utils/geometry/polygon_geom.regular_polygon_vertices). */
export function regularPolygonVertices(k: number, edgeLength: number): Point[] {
  const radius = edgeLength / (2 * Math.sin(Math.PI / k));
  const start = -Math.PI / 2 - Math.PI / k;
  return Array.from({ length: k }, (_, j) => {
    const a = start + (2 * Math.PI * j) / k;
    return [radius * Math.cos(a), radius * Math.sin(a)];
  });
}

/** Ray-casting point-in-polygon test (mirrors interactive_builder_app's _point_in_polygon). */
export function pointInPolygon([x, y]: Point, verts: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = verts.length - 1; i < verts.length; j = i++) {
    const [xi, yi] = verts[i];
    const [xj, yj] = verts[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function orientation(a: Point, b: Point, c: Point): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function segmentsCross(a: Point, b: Point, c: Point, d: Point): boolean {
  const d1 = orientation(c, d, a);
  const d2 = orientation(c, d, b);
  const d3 = orientation(a, b, c);
  const d4 = orientation(a, b, d);
  return d1 * d2 < 0 && d3 * d4 < 0;
}

/** Whether the axis-aligned rectangle (x0,y0)-(x1,y1) overlaps the polygon at all (mirrors _rect_intersects_polygon). */
export function rectIntersectsPolygon(x0: number, y0: number, x1: number, y1: number, verts: Point[]): boolean {
  if (verts.some(([x, y]) => x >= x0 && x <= x1 && y >= y0 && y <= y1)) return true;
  const corners: Point[] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
  if (corners.some((c) => pointInPolygon(c, verts))) return true;
  for (let i = 0; i < verts.length; i++) {
    const a = verts[i];
    const b = verts[(i + 1) % verts.length];
    for (let k = 0; k < 4; k++) {
      if (segmentsCross(a, b, corners[k], corners[(k + 1) % 4])) return true;
    }
  }
  return false;
}
