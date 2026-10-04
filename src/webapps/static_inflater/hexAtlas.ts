import * as THREE from "three";

/**
 * The hexagon texture atlas (hexatlas.png): 16 crocheted hexagons in a 4 x 4 grid, cut from the
 * sample photo. Shared by every viewer; it loads once, and listeners are told when it's ready so the
 * views can redraw.
 */
const ATLAS_URL = new URL("./hexatlas.png", import.meta.url).href;

const ATLAS_GRID = 4;
let texture: THREE.Texture | null = null;
let normalTexture: THREE.Texture | null = null;
let loaded = false;
/** The atlas after darkening (see darkenBlackCells), the picture both the 3D texture and the 2D canvas draw from. */
let processed: HTMLCanvasElement | null = null;
const listeners = new Set<() => void>();

/** The black rim is the band between a hexagon's outer edge (radius 1/2 of the cell) and this inset hexagon. */
const RIM_INNER = 0.925;
/** A rim pixel brighter than this multiple of its cell's median rim brightness is pulled down to that cap. */
const RIM_CAP = 1.25;

/** True if a point (relative to the cell centre, cell units) lies inside a regular hexagon of circumradius `r`, corners at 0, 60, ... degrees. */
function insideHex(px: number, py: number, r: number): boolean {
  for (let k = 0; k < 6; k++) {
    const a = ((30 + 60 * k) * Math.PI) / 180;
    if (px * Math.cos(a) + py * Math.sin(a) > r * Math.cos(Math.PI / 6)) return false;
  }
  return true;
}

/**
 * Caps the brightness of the black rim: a mask of each cell's rim (inside the hexagon, outside its inset copy) and
 * any rim pixel brighter than RIM_CAP times the cell's median rim brightness is pulled down to that cap. Nothing
 * outside the rim is touched.
 */
function darkenRim(image: HTMLImageElement): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(image, 0, 0);
  const W = canvas.width;
  const H = canvas.height;
  const img = ctx.getImageData(0, 0, W, H);
  const d = img.data;
  const cellW = W / ATLAS_GRID;
  const cellH = H / ATLAS_GRID;
  for (let cell = 0; cell < ATLAS_GRID * ATLAS_GRID; cell++) {
    const x0 = Math.floor((cell % ATLAS_GRID) * cellW);
    const y0 = Math.floor(Math.floor(cell / ATLAS_GRID) * cellH);
    const x1 = Math.floor(x0 + cellW);
    const y1 = Math.floor(y0 + cellH);
    const rim: { p: number; lum: number }[] = [];
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) {
        const px = (x + 0.5 - x0) / cellW - 0.5;
        const py = (y + 0.5 - y0) / cellH - 0.5;
        if (!insideHex(px, py, 0.5) || insideHex(px, py, 0.5 * RIM_INNER)) continue;
        const p = y * W + x;
        rim.push({ p, lum: 0.299 * d[p * 4] + 0.587 * d[p * 4 + 1] + 0.114 * d[p * 4 + 2] });
      }
    }
    if (rim.length === 0) continue;
    const sorted = rim.map((r) => r.lum).sort((a, b) => a - b);
    const cap = sorted[Math.floor(sorted.length / 2)] * RIM_CAP;
    for (const { p, lum } of rim) {
      if (lum <= cap) continue;
      const k = cap / lum;
      d[p * 4] *= k;
      d[p * 4 + 1] *= k;
      d[p * 4 + 2] *= k;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

/** How steeply the stitch relief tilts: the normal map's slope per unit of brightness change between neighbouring pixels. */
const RELIEF_SLOPE = 4;

/**
 * A normal map for the atlas, laid out exactly like the colour atlas so the same UVs pick it. Brightness is
 * read as height (lit stitch tops are high, shadowed gaps low), smoothed over 3 x 3 so the photo's grain
 * doesn't show, and each pixel's slope becomes its normal. The result is faked bump mapping, not measured relief.
 */
function reliefNormalMap(source: HTMLCanvasElement): HTMLCanvasElement {
  const W = source.width;
  const H = source.height;
  const src = source.getContext("2d", { willReadFrequently: true })!.getImageData(0, 0, W, H).data;
  const clampX = (x: number) => Math.min(W - 1, Math.max(0, x));
  const clampY = (y: number) => Math.min(H - 1, Math.max(0, y));
  const height = new Float32Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      let sum = 0;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const p = (clampY(y + dy) * W + clampX(x + dx)) * 4;
          sum += 0.299 * src[p] + 0.587 * src[p + 1] + 0.114 * src[p + 2];
        }
      }
      height[y * W + x] = sum / 9 / 255;
    }
  }
  const out = document.createElement("canvas");
  out.width = W;
  out.height = H;
  const octx = out.getContext("2d")!;
  const img = octx.createImageData(W, H);
  const d = img.data;
  const at = (x: number, y: number) => height[clampY(y) * W + clampX(x)];
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const gx = ((at(x + 1, y) - at(x - 1, y)) * RELIEF_SLOPE) / 2;
      const gy = ((at(x, y + 1) - at(x, y - 1)) * RELIEF_SLOPE) / 2;
      // Image rows run downward while texture v runs upward, so the green (y) slope keeps its sign and x flips.
      const nx = -gx;
      const ny = gy;
      const len = Math.hypot(nx, ny, 1);
      const p = (y * W + x) * 4;
      d[p] = ((nx / len) * 0.5 + 0.5) * 255;
      d[p + 1] = ((ny / len) * 0.5 + 0.5) * 255;
      d[p + 2] = (0.5 / len + 0.5) * 255;
      d[p + 3] = 255;
    }
  }
  octx.putImageData(img, 0, 0);
  return out;
}

export function hexAtlasTexture(): THREE.Texture {
  if (!texture) {
    // The normal map is created with the colour texture and filled in when the atlas loads, like it.
    normalTexture = new THREE.Texture();
    texture = new THREE.TextureLoader().load(ATLAS_URL, (loadedTexture) => {
      processed = darkenRim(loadedTexture.image as HTMLImageElement);
      texture!.image = processed;
      texture!.needsUpdate = true;
      normalTexture!.image = reliefNormalMap(processed);
      normalTexture!.needsUpdate = true;
      loaded = true;
      listeners.forEach((listener) => listener());
    });
    texture.colorSpace = THREE.SRGBColorSpace;
  }
  return texture;
}

/** The atlas's fake stitch relief as a normal map, for the African Flower material to light with. */
export function hexAtlasNormalMap(): THREE.Texture {
  hexAtlasTexture();
  return normalTexture!;
}

export function hexAtlasReady(): boolean {
  return loaded;
}

/** Resolves once the atlas has loaded (starts loading it if needed). */
export function hexAtlasLoaded(): Promise<void> {
  hexAtlasTexture();
  if (loaded) return Promise.resolve();
  return new Promise((resolve) => {
    const off = onHexAtlasLoaded(() => {
      off();
      resolve();
    });
  });
}

/** The atlas's pixels, for drawing with canvas 2D; null until it has loaded. */
export function hexAtlasImage(): HTMLCanvasElement | null {
  return loaded ? processed : null;
}

/** Calls `listener` once the atlas has loaded (or straight away if it already has). Returns an unsubscribe. */
export function onHexAtlasLoaded(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
