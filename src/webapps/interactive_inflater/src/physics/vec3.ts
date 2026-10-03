export type Vec3 = [number, number, number];

export const zero = (): Vec3 => [0, 0, 0];
export const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const scale = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
export const norm = (a: Vec3): number => Math.sqrt(dot(a, a));

/** True direction where resolvable, else a fixed (1,0,0) fallback at an exact zero vector --
 * avoids a naive v/norm(v) division silently shrinking toward zero along with a genuinely-zero
 * force (mirrors stretchy_mesh._safe_unit_vectors). */
export function safeUnit(v: Vec3): Vec3 {
  const n = norm(v);
  if (n > 1e-9) return scale(v, 1 / n);
  return [1, 0, 0];
}

export function mean(points: Vec3[]): Vec3 {
  const m = zero();
  for (const p of points) {
    m[0] += p[0];
    m[1] += p[1];
    m[2] += p[2];
  }
  const n = points.length || 1;
  return [m[0] / n, m[1] / n, m[2] / n];
}
