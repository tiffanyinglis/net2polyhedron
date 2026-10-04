/**
 * The net builder's colour rules, kept pure so the builder and the bulk re-save use the same ones.
 *
 * A new piece takes the least-used Multi-colour and hexagon cell among the shapes already in the net (ties are
 * random). Randomize goes shape by shape and avoids the colours and cells that joined neighbours already have,
 * so it spreads over as many colours as it can without touching a neighbour of the same colour.
 */
import { FACE_COLORS, type ColorMode } from "../utils/colors";
import { HEX_CELLS } from "../utils/physics/meshLevels";
import type { NetColors } from "./netFile";

/** Shape id -> ids of the shapes it's joined to. */
export type Neighbours = Map<number, Set<number>>;

export function neighboursOf(connections: { aShape: number; bShape: number }[]): Neighbours {
  const out: Neighbours = new Map();
  const link = (a: number, b: number) => {
    if (a === b) return;
    out.set(a, (out.get(a) ?? new Set()).add(b));
  };
  for (const c of connections) {
    link(c.aShape, c.bShape);
    link(c.bShape, c.aShape);
  }
  return out;
}

/** A random option among those used least, given how often each option is used so far. */
function leastUsed<T>(options: T[], uses: Map<T, number>): T {
  const counts = options.map((o) => uses.get(o) ?? 0);
  const fewest = Math.min(...counts);
  const best = options.filter((_, i) => counts[i] === fewest);
  return best[Math.floor(Math.random() * best.length)];
}

const CELLS = Array.from({ length: HEX_CELLS }, (_, i) => i);
const randomStart = () => Math.floor(Math.random() * 6);

/** The colour and texture the next new piece will get: the least used among the shapes in `shapeIds`. */
export function nextPiece(shapeIds: number[], colors: NetColors): { multi: number; african: { cell: number; start: number } } {
  const multiUse = new Map<number, number>();
  const cellUse = new Map<number, number>();
  for (const id of shapeIds) {
    const m = colors.multi[id];
    if (m !== undefined) multiUse.set(m, (multiUse.get(m) ?? 0) + 1);
    const a = colors.african[id];
    if (a !== undefined) cellUse.set(a.cell, (cellUse.get(a.cell) ?? 0) + 1);
  }
  return { multi: leastUsed(FACE_COLORS, multiUse), african: { cell: leastUsed(CELLS, cellUse), start: randomStart() } };
}

/** Gives every shape that has no colour or texture yet the next piece's, one at a time, so each new one differs from the last. */
export function fillMissingColours(shapeIds: number[], colors: NetColors) {
  for (const id of shapeIds) {
    if (colors.multi[id] !== undefined && colors.african[id] !== undefined) continue;
    const piece = nextPiece(
      shapeIds.filter((s) => colors.multi[s] !== undefined),
      colors,
    );
    colors.multi[id] ??= piece.multi;
    colors.african[id] ??= piece.african;
  }
}

/**
 * Randomize: a fresh Multi-colour (mode "multi") or African Flower choice (mode "african") for every shape. Each shape
 * takes the least-used option its already-chosen neighbours don't have; if they have all of them, it takes the least used.
 */
export function randomize(shapeIds: number[], neighbours: Neighbours, colors: NetColors, mode: ColorMode) {
  if (mode === "polygon") return;
  const chosenMulti = new Map<number, number>();
  const chosenCell = new Map<number, number>();
  const multiOf = new Map<number, number>();
  const cellOf = new Map<number, number>();
  for (const id of shapeIds) {
    const adjacent = neighbours.get(id) ?? new Set<number>();
    if (mode === "multi") {
      const taken = new Set([...adjacent].map((n) => multiOf.get(n)).filter((c): c is number => c !== undefined));
      const allowed = FACE_COLORS.filter((c) => !taken.has(c));
      const colour = leastUsed(allowed.length ? allowed : FACE_COLORS, chosenMulti);
      multiOf.set(id, colour);
      chosenMulti.set(colour, (chosenMulti.get(colour) ?? 0) + 1);
      colors.multi[id] = colour;
    } else {
      const taken = new Set([...adjacent].map((n) => cellOf.get(n)).filter((c): c is number => c !== undefined));
      const allowed = CELLS.filter((c) => !taken.has(c));
      const cell = leastUsed(allowed.length ? allowed : CELLS, chosenCell);
      cellOf.set(id, cell);
      chosenCell.set(cell, (chosenCell.get(cell) ?? 0) + 1);
      colors.african[id] = { cell, start: randomStart() };
    }
  }
}
