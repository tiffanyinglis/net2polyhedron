import { edgeMidpoints, type Connection } from "./joins";
import { rotationFacingNeighbors } from "./rotate";
import { circumradius, DEFAULT_SHAPE_EDGE_LENGTH, type Shape } from "./shapes";

/** Passes the relaxation runs each time it's asked to settle a set of pieces. */
const ITERATIONS = 40;
/** How much of each iteration's spring correction is actually applied, below 1 for stability: every
 * piece's own edge midpoints move too as its neighbours pull on it, so applying a full correction in one
 * go overshoots and oscillates instead of settling. Kept well below REPULSION_STEP_FRACTION so repulsion
 * dominates springs: two unrelated pieces crowded together by a spring elsewhere should separate before
 * the springs pull them back close, not settle into an equilibrium that still looks crowded. */
const STEP_FRACTION = 0.15;
/** Same idea as STEP_FRACTION, for the rotation nudge towards rotationFacingNeighbors' target each
 * iteration: below 1 so several joins on one piece (a junction) settle towards their shared compromise
 * gradually, rather than each iteration's target angle being applied outright. */
const ANGULAR_STEP_FRACTION = 0.3;
/** Clearance kept between two pieces' circumradii by the repulsion term. Bigger than resolveOverlaps'
 * own margin (untangle.ts) on purpose: that pass only has to guarantee no overlap, where this one also
 * has to keep unrelated, un-joined pieces from visually crowding right up against each other as the
 * springs pull everything else together around them. */
const OVERLAP_MARGIN = 10;
/** Repulsion's own share of each iteration's correction, bigger than STEP_FRACTION so two pieces pushed
 * together mostly by their springs (rather than by actually starting the relaxation overlapped) still
 * separate at roughly the margin above, instead of the two forces settling into equilibrium somewhere
 * short of it. */
const REPULSION_STEP_FRACTION = 0.6;

/** `angle - from`, wrapped to (-pi, pi] -- the short way around, whichever direction that is. */
function angleDiff(angle: number, from: number): number {
  const twoPi = 2 * Math.PI;
  let d = (angle - from) % twoPi;
  if (d > Math.PI) d -= twoPi;
  if (d < -Math.PI) d += twoPi;
  return d;
}

/**
 * Settles `ids` (typically everything currently visible) like a mass-spring model: every real connection
 * between two of them acts as a spring pulling its two edges' midpoints towards sitting exactly one
 * polygon edge apart (DEFAULT_SHAPE_EDGE_LENGTH) -- the gap a real paper join leaves -- while a soft
 * repulsion keeps any two pieces' centres from drifting closer than their circumradii allow. Separately,
 * each piece also nudges its own rotation towards rotationFacingNeighbors' pick (see rotate.ts) -- the
 * angle that best squares its joined edges up to wherever its neighbours currently sit. This is kept
 * independent of the spring force on purpose: a join already sitting at (or past) its rest length pulls
 * with little or no force, so a force-driven torque alone would never turn a piece whose only problem is
 * being twisted, not stretched -- exactly the case a real paper join left crooked needs fixed. Mutates
 * `positions` and `rotations` in place; `shapes` are read-only, only used for each piece's polygon (n).
 *
 * This runs on top of whatever layout `positions`/`rotations` already hold -- greedy placement's own
 * crossing-aware choice, or a previous relax -- as a physical correction, not a replacement for it:
 * nothing here is crossing-aware, so a large correction could reintroduce a crossing greedy placement
 * just avoided. Small, damped nudges (see STEP_FRACTION/ANGULAR_STEP_FRACTION) make that unlikely in
 * practice, but it's never guaranteed.
 */
export function relaxSprings(
  shapes: Shape[],
  ids: number[],
  positions: Map<number, [number, number]>,
  rotations: Map<number, number>,
  connections: Connection[],
): void {
  const idSet = new Set(ids);
  const byId = new Map(shapes.map((s) => [s.id, s]));
  const active = ids.map((id) => byId.get(id)).filter((s): s is Shape => !!s && positions.has(s.id));
  if (active.length < 2) return;

  const radius = new Map(active.map((s) => [s.id, circumradius(s.n)]));
  const springs = connections.filter((c) => c.aShape !== c.bShape && idSet.has(c.aShape) && idSet.has(c.bShape));
  if (!springs.length) return;

  // Which edge of which piece each of its springs joins to which other piece -- fixed for the whole
  // relaxation, used every iteration to look up rotationFacingNeighbors' current target for that piece.
  const joinsOf = new Map<number, { edge: number; otherId: number }[]>(active.map((s) => [s.id, []]));
  for (const c of springs) {
    joinsOf.get(c.aShape)!.push({ edge: c.aEdge, otherId: c.bShape });
    joinsOf.get(c.bShape)!.push({ edge: c.bEdge, otherId: c.aShape });
  }

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const posDelta = new Map<number, [number, number]>(active.map((s) => [s.id, [0, 0]]));

    for (const c of springs) {
      const a = byId.get(c.aShape)!;
      const b = byId.get(c.bShape)!;
      const pa = positions.get(c.aShape)!;
      const pb = positions.get(c.bShape)!;
      const [ax, ay] = edgeMidpoints({ ...a, cx: pa[0], cy: pa[1], rotation: rotations.get(c.aShape)! })[c.aEdge];
      const [bx, by] = edgeMidpoints({ ...b, cx: pb[0], cy: pb[1], rotation: rotations.get(c.bShape)! })[c.bEdge];
      const dx = bx - ax;
      const dy = by - ay;
      const dist = Math.hypot(dx, dy) || 1e-6;
      const force = (dist - DEFAULT_SHAPE_EDGE_LENGTH) * STEP_FRACTION * 0.5;
      const ux = dx / dist;
      const uy = dy / dist;

      const da = posDelta.get(c.aShape)!;
      da[0] += ux * force;
      da[1] += uy * force;
      const db = posDelta.get(c.bShape)!;
      db[0] -= ux * force;
      db[1] -= uy * force;
    }

    for (let i = 0; i < active.length; i++) {
      for (let j = i + 1; j < active.length; j++) {
        const a = active[i];
        const b = active[j];
        const pa = positions.get(a.id)!;
        const pb = positions.get(b.id)!;
        const dx = pa[0] - pb[0];
        const dy = pa[1] - pb[1];
        const dist = Math.hypot(dx, dy) || 1e-6;
        const minDist = radius.get(a.id)! + radius.get(b.id)! + OVERLAP_MARGIN;
        if (dist >= minDist) continue;
        const push = (minDist - dist) * REPULSION_STEP_FRACTION;
        const ux = dx / dist;
        const uy = dy / dist;
        const da = posDelta.get(a.id)!;
        da[0] += ux * push;
        da[1] += uy * push;
        const db = posDelta.get(b.id)!;
        db[0] -= ux * push;
        db[1] -= uy * push;
      }
    }

    for (const s of active) {
      const d = posDelta.get(s.id)!;
      const p = positions.get(s.id)!;
      p[0] += d[0];
      p[1] += d[1];
    }

    for (const s of active) {
      const joins = joinsOf.get(s.id)!;
      if (!joins.length) continue;
      const current = rotations.get(s.id)!;
      const resolved = joins.map(({ edge, otherId }) => ({ edge, position: positions.get(otherId)! }));
      const target = rotationFacingNeighbors(s.n, current, resolved, positions.get(s.id)!);
      rotations.set(s.id, current + angleDiff(target, current) * ANGULAR_STEP_FRACTION);
    }
  }
}
