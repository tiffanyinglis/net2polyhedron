import * as THREE from "three";

/**
 * The African Flower motif for an n-sided polygon, drawn onto canvases in the style of a crocheted
 * hexagon. From the outside in: a black boundary that follows the polygon's own edges, an inner
 * background, n petals that just touch each other, a star in the middle with a dot on it, and a
 * crochet stitch texture over the background and petals. Two textures come out of it: the colour
 * map, and a bump map (white where the stitches and petals rise, dark between them).
 *
 * The textures are square and span -R..+R on both axes, where R is the polygon's corner radius
 * (see viewer.ts), so the polygon's corners sit at radius 1 and its edges at cos(pi/n).
 */

/** The colours of one flower. Random colours later means passing a different palette per polygon. */
export interface FlowerPalette {
  background: string;
  petal: string;
  star: string;
  centre: string;
}

export const DEFAULT_FLOWER_PALETTE: FlowerPalette = {
  background: "#efe8da",
  petal: "#f0399a",
  star: "#ffb62e",
  centre: "#35d3e6",
};

export interface FlowerTextures {
  map: THREE.CanvasTexture;
  bump: THREE.CanvasTexture;
}

const SIZE = 512;
const C = SIZE / 2;
const BLACK = "#000000";
const EDGE_SHADE = "rgba(0, 0, 0, 0.5)";
/** Width of the black boundary, across the polygon's edge, as a fraction of R. */
const BORDER = 0.16;
const STITCH_DARK = "rgba(0, 0, 0, 0.35)";
const STITCH_LIGHT = "rgba(255, 255, 255, 0.25)";

const cache = new Map<string, FlowerTextures>();

/** The motif for a polygon with `sides` sides (one petal per side). Cached per side count and palette. */
export function africanFlowerTextures(sides: number, palette: FlowerPalette = DEFAULT_FLOWER_PALETTE): FlowerTextures {
  const key = `${sides}|${palette.background}|${palette.petal}|${palette.star}|${palette.centre}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const textures = {
    map: drawTexture(THREE.SRGBColorSpace, (g) => paint(g, sides, palette, false)),
    bump: drawTexture(THREE.NoColorSpace, (g) => paint(g, sides, palette, true)),
  };
  cache.set(key, textures);
  return textures;
}

/** Sizes of the motif's parts, in fractions of R, for a polygon with `sides` sides. */
function layout(sides: number) {
  const apothem = Math.cos(Math.PI / sides); // the polygon's edge distance from its centre
  const innerApothem = apothem - BORDER;
  const innerCircum = innerApothem / Math.cos(Math.PI / sides);
  // The petal ring is as big as fits inside the background: touching neighbours (centres 2r apart),
  // staying within the background at its corners and along its edges.
  const s = Math.sin(Math.PI / sides);
  const ring = Math.min(innerCircum / (1 + s), innerApothem / (Math.cos(Math.PI / sides) + s));
  const petal = ring * s;
  const star = (ring - petal) * 0.95; // the star fills the gap the petals leave in the middle
  return { innerCircum, innerApothem, ring, petal, star };
}

/** Paints one canvas. `bump` paints greys for the height map; otherwise the real colours. */
function paint(g: CanvasRenderingContext2D, sides: number, palette: FlowerPalette, bump: boolean) {
  const { innerCircum, ring, petal, star } = layout(sides);
  const at = (r: number) => r * C;
  const point = (r: number, angle: number): [number, number] => [C + Math.cos(angle) * at(r), C + Math.sin(angle) * at(r)];

  // Black boundary: the whole texture is black, and the background is drawn inside it.
  g.fillStyle = BLACK;
  g.fillRect(0, 0, SIZE, SIZE);
  polygon(g, sides, innerCircum, 0);
  g.fillStyle = bump ? "#6e6e6e" : palette.background;
  g.fill();

  // Petals: n circles, one per side, pointing at the polygon's corners.
  for (let k = 0; k < sides; k++) {
    const [x, y] = point(ring, (k * 2 * Math.PI) / sides);
    if (bump) radialFill(g, x, y, at(petal), "#ffffff", "#8c8c8c");
    else {
      g.fillStyle = palette.petal;
      g.strokeStyle = EDGE_SHADE;
      g.lineWidth = SIZE * 0.01;
      g.beginPath();
      g.arc(x, y, at(petal), 0, Math.PI * 2);
      g.fill();
      g.stroke();
    }
  }

  // Star: tips toward the petals, with a dot in its middle.
  g.beginPath();
  for (let k = 0; k < 2 * sides; k++) {
    const r = k % 2 === 0 ? star : star * 0.55;
    const [x, y] = point(r, (k * Math.PI) / sides);
    if (k === 0) g.moveTo(x, y);
    else g.lineTo(x, y);
  }
  g.closePath();
  if (bump) {
    g.fillStyle = "#e0e0e0";
  } else {
    g.fillStyle = palette.star;
    g.strokeStyle = EDGE_SHADE;
    g.lineWidth = SIZE * 0.01;
    g.stroke();
  }
  g.fill();

  const [cx, cy] = point(0, 0);
  if (bump) radialFill(g, cx, cy, at(star * 0.3), "#ffffff", "#b0b0b0");
  else {
    g.fillStyle = palette.centre;
    g.beginPath();
    g.arc(cx, cy, at(star * 0.3), 0, Math.PI * 2);
    g.fill();
  }

  // Crochet stitches, clipped to the background so they stay inside the black boundary.
  g.save();
  polygon(g, sides, innerCircum, 0);
  g.clip();
  stitches(g, bump);
  g.restore();
}

/** Traces a regular polygon with the given circumradius (fraction of R), first corner at `rotation`. */
function polygon(g: CanvasRenderingContext2D, sides: number, radius: number, rotation: number) {
  g.beginPath();
  for (let k = 0; k < sides; k++) {
    const a = rotation + (k * 2 * Math.PI) / sides;
    const x = C + Math.cos(a) * radius * C;
    const y = C + Math.sin(a) * radius * C;
    if (k === 0) g.moveTo(x, y);
    else g.lineTo(x, y);
  }
  g.closePath();
}

/** A grid of crochet "V" stitches, each with a light edge, offset every other row like real rows. */
function stitches(g: CanvasRenderingContext2D, bump: boolean) {
  const step = SIZE / 13;
  const w = step * 0.4;
  const h = step * 0.45;
  g.lineCap = "round";
  g.lineWidth = SIZE * 0.012;
  for (let row = -1; row * step < SIZE + step; row++) {
    for (let col = -1; col * step < SIZE + step; col++) {
      const x = col * step + (row % 2 ? step / 2 : 0);
      const y = row * step;
      g.strokeStyle = bump ? "rgba(0,0,0,0.25)" : STITCH_DARK;
      g.beginPath();
      g.moveTo(x - w, y - h);
      g.lineTo(x, y);
      g.lineTo(x + w, y - h);
      g.stroke();
      if (!bump) {
        g.strokeStyle = STITCH_LIGHT;
        g.beginPath();
        g.moveTo(x - w, y - h + 2);
        g.lineTo(x, y + 2);
        g.lineTo(x + w, y - h + 2);
        g.stroke();
      }
    }
  }
}

function radialFill(g: CanvasRenderingContext2D, x: number, y: number, r: number, inner: string, outer: string) {
  const gradient = g.createRadialGradient(x, y, 0, x, y, r);
  gradient.addColorStop(0, inner);
  gradient.addColorStop(1, outer);
  g.fillStyle = gradient;
  g.beginPath();
  g.arc(x, y, r, 0, Math.PI * 2);
  g.fill();
}

/** Draws one canvas with `paint` and wraps it in a texture. `colorSpace` is sRGB for colour, none for data (bump). */
function drawTexture(colorSpace: THREE.ColorSpace, paintFn: (g: CanvasRenderingContext2D) => void): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  paintFn(canvas.getContext("2d")!);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = colorSpace;
  return texture;
}
