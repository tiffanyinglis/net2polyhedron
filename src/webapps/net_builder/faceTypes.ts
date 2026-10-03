import { type Connection } from "./joins";
import { type Shape } from "./shapes";

/**
 * The part a reachable piece plays. The owner is the anchor the net grows from (the Python app's anchor
 * piece). A junction has two or more joins, a terminal has one or none, as in the Python app's node classifier.
 */
export type FaceRole = "owner" | "junction" | "terminal";

export interface FaceInfo {
  /** Connected to the owner through joins. An unreachable piece is drawn translucent with a dashed outline. */
  reachable: boolean;
  /** Set only for reachable pieces. */
  role: FaceRole | null;
  /** Joins to other pieces; a piece joined to itself doesn't count. */
  joins: number;
}

/**
 * Classifies every shape for drawing. Reachable means in the owner's connected group; the role then says
 * whether it is the owner itself, a junction, or a terminal. Pure: no canvas or builder state.
 */
export function faceInfo(shapes: Shape[], connections: Connection[], ownerId: number | null): Map<number, FaceInfo> {
  const reachable = reachableIds(connections, ownerId);
  const joins = new Map<number, number>();
  for (const c of connections) {
    // A piece joined to itself (a Polygon Fold) doesn't count as one of its connections.
    if (c.aShape === c.bShape) continue;
    joins.set(c.aShape, (joins.get(c.aShape) ?? 0) + 1);
    joins.set(c.bShape, (joins.get(c.bShape) ?? 0) + 1);
  }
  const info = new Map<number, FaceInfo>();
  for (const shape of shapes) {
    const count = joins.get(shape.id) ?? 0;
    if (!reachable.has(shape.id)) {
      info.set(shape.id, { reachable: false, role: null, joins: count });
      continue;
    }
    const role: FaceRole = shape.id === ownerId ? "owner" : count >= 2 ? "junction" : "terminal";
    info.set(shape.id, { reachable: true, role, joins: count });
  }
  return info;
}

/** Shape ids connected to `ownerId` through joins, the owner included. Empty if there is no owner. */
function reachableIds(connections: Connection[], ownerId: number | null): Set<number> {
  const reached = new Set<number>();
  if (ownerId === null) return reached;
  reached.add(ownerId);
  const queue = [ownerId];
  while (queue.length) {
    const id = queue.shift()!;
    for (const c of connections) {
      const other = c.aShape === id ? c.bShape : c.bShape === id ? c.aShape : null;
      if (other !== null && !reached.has(other)) {
        reached.add(other);
        queue.push(other);
      }
    }
  }
  return reached;
}

/**
 * The owner after an edit: the current owner if it's still a piece, otherwise the most-joined piece (the first
 * one on a tie). Null when there are no pieces.
 */
export function pickOwner(shapes: Shape[], connections: Connection[], current: number | null): number | null {
  if (current !== null && shapes.some((s) => s.id === current)) return current;
  if (!shapes.length) return null;
  const joins = new Map<number, number>();
  for (const c of connections) {
    if (c.aShape === c.bShape) continue;
    joins.set(c.aShape, (joins.get(c.aShape) ?? 0) + 1);
    joins.set(c.bShape, (joins.get(c.bShape) ?? 0) + 1);
  }
  let best = shapes[0];
  for (const s of shapes) if ((joins.get(s.id) ?? 0) > (joins.get(best.id) ?? 0)) best = s;
  return best.id;
}

/**
 * The net's rule: at most one group of more than one piece, and the owner is in it. A group is a set of pieces
 * joined to each other, directly or through other pieces. Single pieces don't count as a group.
 */
export function isValidNet(shapes: Shape[], connections: Connection[], ownerId: number | null): boolean {
  const parent = new Map(shapes.map((s) => [s.id, s.id]));
  const find = (id: number): number => {
    let root = id;
    while (parent.get(root) !== root) root = parent.get(root)!;
    return root;
  };
  for (const c of connections) {
    if (!parent.has(c.aShape) || !parent.has(c.bShape)) continue;
    parent.set(find(c.aShape), find(c.bShape));
  }
  const sizes = new Map<number, number>();
  for (const s of shapes) sizes.set(find(s.id), (sizes.get(find(s.id)) ?? 0) + 1);
  const multi = [...sizes.entries()].filter(([, size]) => size > 1).map(([root]) => root);
  if (multi.length === 0) return true;
  return multi.length === 1 && ownerId !== null && find(ownerId) === multi[0];
}
