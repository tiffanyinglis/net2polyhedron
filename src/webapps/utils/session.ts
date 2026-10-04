import type { NetSpec } from "./physics/mesh";
import type { ColorMode } from "./colors";
import type { LevelRecord } from "./physics/pipeline";
import type { ReplayFrame } from "./physics/relaxOnce";
import type { Vec3 } from "./physics/vec3";

/** File > Save Session writes this as JSON with the ".hippo" extension. */
export const SESSION_FORMAT = "hippo-session";
export const SESSION_VERSION = 1;
export const SESSION_EXTENSION = ".hippo";

/** A level's replay frames, stored compactly: vertex ids once, then flat [x,y,z,...] per frame in that order. */
export interface ReplaySnapshot {
  vertexIds: number[];
  frames: { steps: number; xyz: number[] }[];
}

/** One level's mesh, as stored in a session: enough to redraw it without re-solving. */
export interface LevelSnapshot {
  faces: number[][];
  faceOfFine: number[];
  faceEdgeIds: number[][];
  outlineEdgeIds: number[];
  /** Absent in sessions saved before the texture coordinates were stored. */
  faceUV?: number[][];
  positions: [number, Vec3][];
  /** Absent when the session was saved without replay frames (or the level has none). */
  replay?: ReplaySnapshot;
}

/** Everything File > Save Session writes and File > Load Session restores. */
export interface SessionData {
  netName: string;
  netSpec: NetSpec;
  colorMode: ColorMode;
  multiColors: number[];
  /** Index 0 is Level 1, matching the Setup box's Target RMS fields. */
  targetRmsPct: number[];
  tolerance: number;
  camera: { orientation: [number, number, number, number]; zoom: number; pan: [number, number] };
  /** Indexed by level (0..3). */
  history: (LevelRecord | null)[];
  /** Indexed by level (0..3); null for a level that was never computed. */
  levels: (LevelSnapshot | null)[];
}

export function snapshotLevel(
  topology: { faces: number[][]; faceOfFine: number[]; faceEdgeIds: number[][]; outlineEdgeIds: Set<number>; faceUV?: number[][] },
  positions: Map<number, Vec3>,
  frames?: ReplayFrame[],
): LevelSnapshot {
  const vertexIds = [...positions.keys()];
  const snap: LevelSnapshot = {
    faces: topology.faces,
    faceOfFine: topology.faceOfFine,
    faceEdgeIds: topology.faceEdgeIds,
    outlineEdgeIds: [...topology.outlineEdgeIds],
    positions: [...positions.entries()],
  };
  if (topology.faceUV) snap.faceUV = topology.faceUV;
  if (frames && frames.length) {
    snap.replay = {
      vertexIds,
      frames: frames.map((f) => ({ steps: f.steps, xyz: vertexIds.flatMap((v) => [...f.positions.get(v)!]) })),
    };
  }
  return snap;
}

export function restoreLevel(snap: LevelSnapshot) {
  const frames: ReplayFrame[] = (snap.replay?.frames ?? []).map(({ steps, xyz }) => {
    const ids = snap.replay!.vertexIds;
    if (xyz.length !== ids.length * 3) throw new Error("Session replay frames don't match the level's vertices.");
    const positions = new Map<number, Vec3>();
    ids.forEach((v, i) => positions.set(v, [xyz[3 * i], xyz[3 * i + 1], xyz[3 * i + 2]]));
    return { steps, positions };
  });
  return {
    topology: {
      faces: snap.faces,
      faceOfFine: snap.faceOfFine,
      faceEdgeIds: snap.faceEdgeIds,
      outlineEdgeIds: new Set(snap.outlineEdgeIds),
      faceUV: snap.faceUV ?? [],
    },
    positions: new Map(snap.positions) as Map<number, Vec3>,
    frames,
  };
}

export function serializeSession(data: SessionData): string {
  return JSON.stringify({ format: SESSION_FORMAT, version: SESSION_VERSION, ...data }, null, 2);
}

/** Parses and checks a .hippo file's text. Throws an Error naming the first problem found. */
export function parseSession(text: string): SessionData {
  let raw: any;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new Error("Not a valid session file (invalid JSON).");
  }
  if (raw?.format !== SESSION_FORMAT) throw new Error("Not a session file (missing or wrong format tag).");
  if (raw.version !== SESSION_VERSION) throw new Error(`Unsupported session version ${raw.version}.`);
  if (!Array.isArray(raw.netSpec?.faces)) throw new Error("Session file has no net faces.");
  if (raw.colorMode !== "polygon" && raw.colorMode !== "multi") throw new Error("Session file has an unknown colour mode.");
  if (!Array.isArray(raw.multiColors) || !Array.isArray(raw.targetRmsPct) || !Array.isArray(raw.history) || !Array.isArray(raw.levels)) {
    throw new Error("Session file is missing required fields.");
  }
  if (raw.levels.length !== raw.history.length) throw new Error("Session file has mismatched level data.");
  const { format: _format, version: _version, ...data } = raw;
  return data as SessionData;
}
