import { describe, expect, it } from "vitest";
import { parseSession, restoreLevel, serializeSession, snapshotLevel, type SessionData } from "../session";

const TETRAHEDRON = { faces: [[0, 1, 2], [3, 1, 0], [0, 2, 3], [2, 1, 3]] };

function sampleSession(): SessionData {
  return {
    netName: "tetrahedron",
    netSpec: TETRAHEDRON,
    colorMode: "multi",
    multiColors: [1, 2, 3, 4],
    targetRmsPct: [10, 12, 14],
    tolerance: 1e-4,
    camera: { orientation: [0.1, 0.2, 0.3, 0.9], zoom: 1.5, pan: [0.25, -0.5] },
    history: [null, null, null, null],
    levels: [null, null, null, null],
  };
}

describe("session file round trip", () => {
  it("parses back exactly what serializeSession wrote", () => {
    const data = sampleSession();
    expect(parseSession(serializeSession(data))).toEqual(data);
  });

  it("tags the file so it can be told apart from a plain net", () => {
    const parsed = JSON.parse(serializeSession(sampleSession()));
    expect(parsed.format).toBe("hippo-session");
    expect(parsed.version).toBe(1);
  });
});

describe("level snapshots", () => {
  it("round-trips topology (including the outline set) and positions", () => {
    const topology = {
      faces: [[0, 1, 2]],
      faceOfFine: [0],
      faceEdgeIds: [[0, 1, 2]],
      outlineEdgeIds: new Set([1, 2]),
    };
    const positions = new Map<number, [number, number, number]>([
      [0, [0, 0, 0]],
      [1, [1, 0, 0]],
      [2, [0, 1, 0]],
    ]);
    const json = JSON.parse(JSON.stringify(snapshotLevel(topology, positions)));
    const restored = restoreLevel(json);
    expect(restored.topology.outlineEdgeIds).toEqual(new Set([1, 2]));
    expect(restored.topology.faces).toEqual(topology.faces);
    expect(restored.positions).toEqual(positions);
  });
});

describe("parseSession rejects bad input", () => {
  it("rejects invalid JSON", () => {
    expect(() => parseSession("{not json")).toThrow(/invalid JSON/);
  });

  it("rejects a plain net file (no format tag)", () => {
    expect(() => parseSession(JSON.stringify(TETRAHEDRON))).toThrow(/wrong format/);
  });

  it("rejects an unsupported version", () => {
    const raw = { ...JSON.parse(serializeSession(sampleSession())), version: 99 };
    expect(() => parseSession(JSON.stringify(raw))).toThrow(/version 99/);
  });

  it("rejects a session with no net faces", () => {
    const raw = { ...JSON.parse(serializeSession(sampleSession())), netSpec: {} };
    expect(() => parseSession(JSON.stringify(raw))).toThrow(/no net faces/);
  });
});

describe("replay frames", () => {
  const topology = { faces: [[0, 1, 2]], faceOfFine: [0], faceEdgeIds: [[0, 1, 2]], outlineEdgeIds: new Set([0]) };
  const final = new Map<number, [number, number, number]>([
    [0, [0, 0, 0]],
    [1, [1, 0, 0]],
    [2, [0, 1, 0]],
  ]);
  const frames = [
    { steps: 0, positions: new Map<number, [number, number, number]>([[0, [0, 0, 0]], [1, [2, 0, 0]], [2, [0, 2, 0]]]) },
    { steps: 10, positions: final },
  ];

  it("round-trips every frame's steps and positions through JSON", () => {
    const json = JSON.parse(JSON.stringify(snapshotLevel(topology, final, frames)));
    const restored = restoreLevel(json);
    expect(restored.frames.map((f) => f.steps)).toEqual([0, 10]);
    expect(restored.frames[0].positions).toEqual(frames[0].positions);
    expect(restored.frames[1].positions).toEqual(final);
  });

  it("omits the replay field entirely when no frames are given", () => {
    const snap = snapshotLevel(topology, final);
    expect(snap).not.toHaveProperty("replay");
    expect(restoreLevel(JSON.parse(JSON.stringify(snap))).frames).toEqual([]);
  });

  it("loads a level saved without frames (older or frame-less files)", () => {
    const data = sampleSession();
    data.levels[1] = JSON.parse(JSON.stringify(snapshotLevel(topology, final)));
    const parsed = parseSession(serializeSession(data));
    const restored = restoreLevel(parsed.levels[1]!);
    expect(restored.positions).toEqual(final);
    expect(restored.frames).toEqual([]);
  });

  it("rejects replay frames whose length doesn't match the vertex list", () => {
    const snap = JSON.parse(JSON.stringify(snapshotLevel(topology, final, frames)));
    snap.replay.frames[0].xyz.pop();
    expect(() => restoreLevel(snap)).toThrow(/replay frames/);
  });
});
