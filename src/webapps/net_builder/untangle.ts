import { greedyPlacement } from "./greedyPlace";
import type { Connection } from "./joins";
import { circumradius, type Shape } from "./shapes";

/**
 * Untangles the net's layout with a breadth-first greedy placement (see greedyPlace.ts): it builds the
 * layout up one ring of pieces at a time, each one tried at several candidate positions and rotations and
 * kept at whichever adds the fewest crossings against everything placed so far -- a crossings tie going to
 * whichever leaves its own joins shortest and squarest to their edges (see connectorQuality in joins.ts).
 * A hard pass (resolveOverlaps) then makes sure no two pieces are left overlapping (greedy placement
 * already avoids this on its own, but this is a guarantee rather than a best effort).
 *
 * untangledLayout returns greedy's own rotations alongside its positions, rather than recomputing rotation
 * from scratch afterward (as a separate, crossing-blind pass over the finished positions would have to --
 * see rotate.ts's own doc comment for why that's worth avoiding): greedy already chose each piece's
 * rotation for exactly this layout, with the same crossing-awareness that chose its position, so there's
 * nothing a later pass could improve on without risking that work. untangledPositions is a thin wrapper
 * for callers that only need positions.
 */

/** Clearance kept between two pieces' circumradii by the hard overlap pass, past touching. */
const OVERLAP_MARGIN = 4;
/** Passes of the hard overlap-resolution pass. A pass only ever pushes pieces apart, so it's safe to run
 * more than usually needed just to be sure it settles. */
const OVERLAP_PASSES = 80;
/** Below this centre-to-centre distance, a pair is treated as coincident: real division blows up, so
 * they're nudged apart along a fixed (deterministic) direction instead. */
const MIN_DISTANCE = 1e-3;

/**
 * Pushes every overlapping pair of pieces apart (each by half the overlap, along the line between their
 * centres) until none overlap, mutating `positions` in place. A regular polygon never reaches past its own
 * circumradius from its centre, so keeping every pair's centres at least `ra + rb` apart is sufficient --
 * not just likely -- to keep the two pieces themselves from overlapping, whatever they're rotated to.
 */
function resolveOverlaps(ids: number[], radius: Map<number, number>, positions: Map<number, [number, number]>) {
  for (let pass = 0; pass < OVERLAP_PASSES; pass++) {
    let anyOverlap = false;
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = ids[i];
        const b = ids[j];
        const [ax, ay] = positions.get(a)!;
        const [bx, by] = positions.get(b)!;
        let dx = ax - bx;
        let dy = ay - by;
        let dist = Math.hypot(dx, dy);
        const minDist = radius.get(a)! + radius.get(b)! + OVERLAP_MARGIN;
        if (dist >= minDist) continue;
        anyOverlap = true;
        if (dist < MIN_DISTANCE) {
          const angle = ((i + 1) * (j + 1) * 2.399963) % (2 * Math.PI);
          dx = Math.cos(angle);
          dy = Math.sin(angle);
          dist = MIN_DISTANCE;
        }
        const push = (minDist - dist) / 2;
        const ux = dx / dist;
        const uy = dy / dist;
        const pa = positions.get(a)!;
        const pb = positions.get(b)!;
        pa[0] += ux * push;
        pa[1] += uy * push;
        pb[0] -= ux * push;
        pb[1] -= uy * push;
      }
    }
    if (!anyOverlap) break;
  }
}

/**
 * New centres and rotations for every shape (keyed by id), breadth-first greedily placed (see the module
 * doc comment) and never overlapping. Flipped side and n are left for the caller to keep as they are.
 * `order` is the same breadth-first placement order greedyPlacement produced it in, for a caller that
 * wants to reveal the net being built up one piece at a time rather than apply the finished result at once.
 */
export function untangledLayout(
  shapes: Shape[],
  connections: Connection[],
): { positions: Map<number, [number, number]>; rotations: Map<number, number>; order: number[] } {
  if (shapes.length < 2) {
    return {
      positions: new Map(shapes.map((s) => [s.id, [s.cx, s.cy]])),
      rotations: new Map(shapes.map((s) => [s.id, s.rotation])),
      order: shapes.map((s) => s.id),
    };
  }

  const { positions, rotations, order } = greedyPlacement(shapes, connections);

  // A hard guarantee past what greedy placement already does as it goes: no two pieces left overlapping.
  const radius = new Map(shapes.map((s) => [s.id, circumradius(s.n)]));
  const ids = shapes.map((s) => s.id);
  resolveOverlaps(ids, radius, positions);

  return { positions, rotations, order };
}

/** Positions only, for callers that don't also need rotations -- see untangledLayout. */
export function untangledPositions(shapes: Shape[], connections: Connection[]): Map<number, [number, number]> {
  return untangledLayout(shapes, connections).positions;
}
