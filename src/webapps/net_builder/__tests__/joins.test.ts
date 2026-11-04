import { describe, expect, it } from "vitest";
import { connectorQuality } from "../joins";
import { DEFAULT_SHAPE_EDGE_LENGTH, type Shape } from "../shapes";

function square(id: number, cx: number, cy: number, rotation = 0): Shape {
  return { id, n: 4, cx, cy, rotation, flipped: false };
}

describe("connectorQuality", () => {
  it("is perfectly square (0) when two edges face each other head-on, parallel and opposite", () => {
    // Piece 2 sits due north of piece 1 (edge 0's own facing direction at rotation 0), and faces back
    // with its own edge 2 (the opposite side) -- the textbook fold-line case.
    const a = square(1, 0, 0);
    const b = square(2, 0, -200);
    const { squareness } = connectorQuality(a, 0, b, 2);
    expect(squareness).toBeCloseTo(0, 6);
  });

  it("is at its worst (close to its 2-per-edge-pair ceiling) when the connector runs along both edges' own tangents instead of across them", () => {
    // Piece 2 sits due south of piece 1, but the edges used (1 and 3) face east/west -- the straight line
    // between their midpoints runs parallel to both edges' own tangents, not perpendicular to either.
    const a = square(1, 0, 0);
    const b = square(2, 0, 400);
    const { squareness } = connectorQuality(a, 1, b, 3);
    expect(squareness).toBeGreaterThan(1.9);
  });

  it("reports a length close to the gap between two squares placed to nearly touch edge-to-edge", () => {
    const a = square(1, 0, 0);
    const b = square(2, 0, -(DEFAULT_SHAPE_EDGE_LENGTH + 10));
    const { length } = connectorQuality(a, 0, b, 2);
    expect(length).toBeCloseTo(10, 6);
  });

  it("is symmetric: swapping which shape is a and which is b doesn't change the result", () => {
    const a = square(1, 0, 0);
    const b = square(2, 150, 80);
    const forward = connectorQuality(a, 1, b, 3);
    const backward = connectorQuality(b, 3, a, 1);
    expect(backward.length).toBeCloseTo(forward.length, 6);
    expect(backward.squareness).toBeCloseTo(forward.squareness, 6);
  });
});
