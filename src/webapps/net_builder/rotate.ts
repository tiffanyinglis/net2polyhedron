import type { Connection } from "./joins";
import type { Shape } from "./shapes";

/**
 * The rotation that turns an n-gon's joined edges to face their neighbours as closely as possible: each
 * join's own edge, at rotation 0, matched against the straight line from `position` to that join's other
 * piece. One join can be faced exactly; several (a junction) generally can't all be satisfied at once, so
 * this is the rotation that minimises the total squared angular miss -- the circular mean of each join's
 * own perfectly-facing angle. Falls back to `fallback` if every join's other piece sits exactly on
 * `position` (nothing to face) or there are no joins at all.
 */
export function rotationFacingNeighbors(
  n: number,
  fallback: number,
  joins: { edge: number; position: [number, number] }[],
  position: [number, number],
): number {
  const [px, py] = position;
  let sx = 0;
  let sy = 0;
  for (const { edge, position: other } of joins) {
    const [qx, qy] = other;
    if (qx === px && qy === py) continue; // coincident centres: no direction to face
    const facingAngle = Math.atan2(qy - py, qx - px);
    const localEdgeAngle = -Math.PI / 2 + (2 * Math.PI * edge) / n;
    const rotationThatFacesIt = facingAngle - localEdgeAngle;
    sx += Math.cos(rotationThatFacesIt);
    sy += Math.sin(rotationThatFacesIt);
  }
  return sx === 0 && sy === 0 ? fallback : Math.atan2(sy, sx);
}

/**
 * Each piece's best rotation once the layout is untangled (see rotationFacingNeighbors). A piece with no
 * joins (or only a self-fold, which has no other piece to face) keeps its rotation.
 *
 * This faces every join's other PIECE, not its specific joined edge -- rotation-independent, so every
 * piece's best rotation can be resolved from the others' (fixed) positions alone, with no risk of a
 * crossing-blind pass undoing another step's crossing-avoidance. untangledLayout (untangle.ts) uses
 * greedy placement's own rotations instead of this, for exactly that reason -- greedy already chooses each
 * piece's rotation and position together, trading a little facing precision for crossing-awareness this
 * function doesn't have. This stays as the simple, positions-only fallback other rotation needs can lean on.
 */
export function optimalRotations(
  shapes: Shape[],
  connections: Connection[],
  positions: Map<number, [number, number]>,
): Map<number, number> {
  const rotations = new Map(shapes.map((s) => [s.id, s.rotation]));
  const joinsOf = new Map<number, { edge: number; otherId: number }[]>(shapes.map((s) => [s.id, []]));
  for (const conn of connections) {
    if (conn.aShape === conn.bShape) continue; // a self-fold has no other piece to face
    joinsOf.get(conn.aShape)?.push({ edge: conn.aEdge, otherId: conn.bShape });
    joinsOf.get(conn.bShape)?.push({ edge: conn.bEdge, otherId: conn.aShape });
  }

  for (const shape of shapes) {
    const joins = joinsOf.get(shape.id)!;
    if (!joins.length) continue;
    const position = positions.get(shape.id)!;
    const resolved = joins
      .map(({ edge, otherId }) => ({ edge, position: positions.get(otherId) }))
      .filter((j): j is { edge: number; position: [number, number] } => j.position !== undefined);
    if (!resolved.length) continue;
    rotations.set(shape.id, rotationFacingNeighbors(shape.n, shape.rotation, resolved, position));
  }

  return rotations;
}
