import type { AtlasChoice } from "./physics/meshLevels";
/**
 * The Setup-box, Convergence History and Full Inflate run shared by static_inflater and
 * interactive_inflater. Both pages draw the same Level 0-3 results and table, so the per-level
 * store, the table renderer, the parameter parsing and the solver run live here once.
 *
 * Pages supply the parts that differ: where a level is drawn, how status text is shown, and how a
 * "loading" panel looks. Mirrors the Python app's release-mode Setup and Convergence History.
 */
import { fullInflate, type LevelRecord } from "./physics/pipeline";
import { type ReplayFrame } from "./physics/relaxOnce";
import { type NetSpec } from "./physics/mesh";
import { CONVERGENCE_GTOL } from "./physics/convergence";
import { type Vec3 } from "./physics/vec3";

export const LEVELS = [0, 1, 2, 3];

/** How often the history table re-renders while a level runs, so its time ticks live. */
const HISTORY_REFRESH_MS = 100;

export type RunOutcome = "done" | "stopped" | "error";
export type StatusKind = "info" | "success" | "error" | "warn";

/** One level's mesh topology: faces from the solver, positions live in the store separately. */
export interface LevelTopology {
  faces: number[][];
  faceOfFine: number[];
  faceEdgeIds: number[][];
  outlineEdgeIds: Set<number>;
  /** Per fine triangle: its corners' texture coordinates (see Level1Topology.faceUV). */
  faceUV?: number[][];
  /** The African Flower choice the faceUV were made with (per solve face), so a colour change can re-point them. */
  atlas?: AtlasChoice;
}

/** Everything a Level 0-3 panel and its history row need, indexed by level. */
export class LevelStore {
  readonly topology: (LevelTopology | null)[] = LEVELS.map(() => null);
  readonly positions: (Map<number, Vec3> | null)[] = LEVELS.map(() => null);
  readonly history: (LevelRecord | null)[] = LEVELS.map(() => null);
  /** performance.now() when the running level started; null when nothing is running. */
  runningSince: number | null = null;

  clear() {
    this.topology.fill(null);
    this.positions.fill(null);
    this.history.fill(null);
    this.runningSince = null;
  }

  /**
   * A shallow copy of the three arrays. Safe because the solver reassigns each level's result
   * rather than mutating it, so the snapshot's references never change underneath it.
   */
  snapshot(): LevelStoreSnapshot {
    return { topology: [...this.topology], positions: [...this.positions], history: [...this.history] };
  }

  restore(snap: LevelStoreSnapshot) {
    this.topology.splice(0, this.topology.length, ...snap.topology);
    this.positions.splice(0, this.positions.length, ...snap.positions);
    this.history.splice(0, this.history.length, ...snap.history);
  }
}

export interface LevelStoreSnapshot {
  topology: (LevelTopology | null)[];
  positions: (Map<number, Vec3> | null)[];
  history: (LevelRecord | null)[];
}

/** Page-specific callbacks: the run reports through these and never touches the DOM itself. */
export interface RunHooks {
  status(text: string, kind: StatusKind): void;
  /** Turns a level panel's loading overlay on or off. */
  loading(level: number, on: boolean): void;
  /** Draws one level's finished positions and its replay frames. */
  showLevel(level: number, positions: Map<number, Vec3>, frames: ReplayFrame[]): void;
  /** Called on every record change and on the live timer; the page re-renders its history table. */
  historyChanged(): void;
}

export interface RunOptions {
  /** Status-line prefix, e.g. "Full Inflate". */
  label: string;
  targetRmsPctByLevel: Record<number, number>;
  gtol: number;
  /** Level 0's starting seed; defaults to LEVEL0_SEED. */
  seed?: number;
  /** The African Flower texture choice for the net (see fullInflate). */
  atlasChoice?: AtlasChoice;
  store: LevelStore;
  /** Polled by the solver between steps. True ends the run as "stopped". */
  shouldStop: () => boolean;
  hooks: RunHooks;
}

/**
 * Runs Full Inflate on `spec`, filling `store` and calling `hooks` as levels finish. Clears the
 * store first. Resolves to "done", "stopped" (shouldStop was true when it ended), or "error".
 * The caller decides whether to keep or restore the store on a non-"done" outcome.
 */
export async function runFullInflate(spec: NetSpec, opts: RunOptions): Promise<RunOutcome> {
  const { store, hooks, label } = opts;
  store.clear();
  hooks.historyChanged();
  // Re-render the table on a timer so the running level's time (and the cumulative total) tick live.
  const timer = setInterval(() => hooks.historyChanged(), HISTORY_REFRESH_MS);
  try {
    const result = await fullInflate(spec, {
      targetRmsPctByLevel: opts.targetRmsPctByLevel,
      gtol: opts.gtol,
      seed: opts.seed,
      atlasChoice: opts.atlasChoice,
      onRecord: (record) => onRecord(record, opts),
      onTopology: (level, faces, faceOfFine, faceEdgeIds, outlineEdgeIds, faceUV) => {
        store.topology[level] = { faces, faceOfFine, faceEdgeIds, outlineEdgeIds, faceUV, atlas: opts.atlasChoice };
      },
      onLevelResult: (level, positions, frames) => {
        store.positions[level] = positions;
        hooks.showLevel(level, positions, frames);
      },
      shouldStop: opts.shouldStop,
    });
    hooks.status(
      `${label} -- Done. RMS stretch ${result.rmsStretchPct.toFixed(1)}%, pressure ${result.pressure.toFixed(2)}.`,
      "success",
    );
    return "done";
  } catch (err) {
    console.error(err);
    for (const level of LEVELS) hooks.loading(level, false);
    const stopped = opts.shouldStop();
    const message = err instanceof Error ? err.message : String(err);
    hooks.status(stopped ? `${label} -- Stopped.` : `${label} -- ${message}`, stopped ? "warn" : "error");
    return stopped ? "stopped" : "error";
  } finally {
    clearInterval(timer);
    store.runningSince = null;
    hooks.historyChanged();
  }
}

function onRecord(record: LevelRecord, opts: RunOptions) {
  const { store, hooks, label } = opts;
  store.history[record.level] = record;
  if (record.state === "running") {
    store.runningSince = performance.now();
    hooks.loading(record.level, true);
    hooks.status(`${label} -- Computing Level ${record.level}...`, "info");
  } else {
    store.runningSince = null;
    hooks.loading(record.level, false);
  }
  hooks.historyChanged();
}

/** "mm:ss" for a duration in seconds, rounded to the nearest second. */
export function mmss(seconds: number): string {
  const total = Math.round(seconds);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** Rebuilds the Convergence History rows from `store`. A running level's time is live elapsed time. */
export function renderHistoryTable(tbody: HTMLTableSectionElement, store: LevelStore, now = performance.now()) {
  let cumulative = 0;
  tbody.replaceChildren(
    ...LEVELS.map((level) => {
      const rec = store.history[level];
      const simTimeS =
        rec && rec.state === "running" && store.runningSince !== null
          ? (now - store.runningSince) / 1000
          : rec?.simTimeS ?? 0;
      if (rec) cumulative += simTimeS;
      const cells = rec
        ? [
            rec.pressure === null ? "--" : rec.pressure.toFixed(2),
            String(rec.steps),
            rec.rmsStretchPct === null ? "--" : rec.rmsStretchPct.toFixed(1),
            mmss(simTimeS),
            mmss(cumulative),
            rec.optimality === null
              ? "--"
              : `${rec.optimality.toExponential(2)} ${rec.optimality < rec.gtol ? "<" : "≥"} ${rec.gtol.toExponential(0)}` +
                (rec.state === "converged" ? " ✓" : ""),
          ]
        : ["--", "--", "--", "--", "--", "--"];
      const tr = document.createElement("tr");
      if (rec) tr.className = rec.state;
      for (const text of [String(level), ...cells]) {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      }
      return tr;
    }),
  );
}

/**
 * Reads a target RMS stretch field ("10%", "10" or junk) as a whole percent in [0, 100], and writes
 * the cleaned value back as "N%". Junk falls back to `fallback`.
 */
export function readTargetRmsPct(input: HTMLInputElement, fallback: number): number {
  const parsed = parseFloat(input.value);
  const value = Number.isFinite(parsed) ? Math.min(100, Math.max(0, Math.round(parsed))) : fallback;
  input.value = `${value}%`;
  return value;
}

/** Reads the tolerance (gtol) field, writes it back in "1e-04" form, and falls back to CONVERGENCE_GTOL. */
export function readTolerance(input: HTMLInputElement): number {
  const parsed = parseFloat(input.value);
  const value = Number.isFinite(parsed) && parsed > 0 ? parsed : CONVERGENCE_GTOL;
  input.value = value.toExponential(0).replace(/e([+-])(\d)$/, (_m, sign, d) => `e${sign}0${d}`);
  return value;
}

/**
 * Wires a Setup-box field: `onBlur` cleans it up, Enter leaves the field, and keystrokes stop
 * propagating so typing never triggers the P/M/R shortcuts. `onFocus` runs before editing starts.
 */
export function wireParamInput(input: HTMLInputElement, onBlur: () => void, onFocus?: () => void) {
  if (onFocus) input.addEventListener("focus", onFocus);
  input.addEventListener("blur", onBlur);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") input.blur();
    e.stopPropagation();
  });
}
