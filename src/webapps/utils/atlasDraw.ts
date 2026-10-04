/**
 * Paints one hexagon-atlas triangle onto a net triangle. Shared by the Inflater's net panel and the net builder.
 */
type Point = [number, number];

/**
 * Draws atlas triangle `uv` (three corners, u/v pairs in the atlas) onto `dst` (three points in CSS pixels). The
 * triangle is clipped to itself grown by a pixel, so neighbouring triangles overlap and no background shows through a seam.
 * `dpr` is the device pixel ratio the caller's transform is scaled by.
 */
export function drawAtlasTriangle(ctx: CanvasRenderingContext2D, atlas: HTMLImageElement, uv: number[], dst: Point[], dpr: number) {
  const { width: W, height: H } = atlas;
  const src: Point[] = [0, 1, 2].map((k) => [uv[2 * k] * W, (1 - uv[2 * k + 1]) * H] as Point);
  const [s0, s1, s2] = src;
  const [d0, d1, d2] = dst;
  const e1x = s1[0] - s0[0], e1y = s1[1] - s0[1], e2x = s2[0] - s0[0], e2y = s2[1] - s0[1];
  const f1x = d1[0] - d0[0], f1y = d1[1] - d0[1], f2x = d2[0] - d0[0], f2y = d2[1] - d0[1];
  const det = e1x * e2y - e2x * e1y || 1e-9;
  const a = (f1x * e2y - f2x * e1y) / det;
  const b = (f1y * e2y - f2y * e1y) / det;
  const c = (f2x * e1x - f1x * e2x) / det;
  const d = (f2y * e1x - f1y * e2x) / det;
  const e = d0[0] - a * s0[0] - c * s0[1];
  const g = d0[1] - b * s0[0] - d * s0[1];
  const mid: Point = [(d0[0] + d1[0] + d2[0]) / 3, (d0[1] + d1[1] + d2[1]) / 3];
  const grown = dst.map(([x, y]) => {
    const dx = x - mid[0];
    const dy = y - mid[1];
    const len = Math.hypot(dx, dy) || 1;
    return [x + (dx / len) * 1.5, y + (dy / len) * 1.5] as Point;
  });
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(grown[0][0], grown[0][1]);
  ctx.lineTo(grown[1][0], grown[1][1]);
  ctx.lineTo(grown[2][0], grown[2][1]);
  ctx.closePath();
  ctx.clip();
  ctx.setTransform(dpr * a, dpr * b, dpr * c, dpr * d, dpr * e, dpr * g);
  ctx.drawImage(atlas, 0, 0);
  ctx.restore();
}
